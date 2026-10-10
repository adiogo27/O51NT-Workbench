"""Montagem da query final a partir dos blocos (precisão, temporal, escopo, X) e templates."""

from __future__ import annotations

from urllib.parse import quote_plus

from app.schemas.query import BlocoEscopo, BlocoPrecisao, BlocoTemporal, BlocoX, ComposeRequest
from app.services.operators import OPERADORES_CHAVE, OPERADORES_X_CHAVE

MOTORES: dict[str, str] = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "startpage": "https://www.startpage.com/do/search?query={q}",
}

# Motores adicionais (campo `deeplinks_extra`; o dicionário `deeplinks` original fica intacto).
# X: f=live → "Mais recentes", o mesmo que uma coluna de busca do TweetDeck.
MOTORES_EXTRA: dict[str, str] = {
    "x": "https://x.com/search?q={q}&src=typed_query&f=live",
    "tiktok": "https://www.tiktok.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google_news": "https://news.google.com/search?q={q}&hl=pt-BR&gl=BR&ceid=BR%3Apt-419",
    # 2026-10-10: mais buscadores e redes (decisão do dono). Brave/Yandex/Mojeek honram aspas, - e site:; não honram before:/after:.
    "brave": "https://search.brave.com/search?q={q}&source=web",
    "yandex": "https://yandex.com/search/?text={q}",
    "mojeek": "https://www.mojeek.com/search?q={q}",
    "bing_news": "https://www.bing.com/news/search?q={q}&setlang=pt-BR&cc=BR",
    "bluesky": "https://bsky.app/search?q={q}",
    "threads": "https://www.threads.net/search?q={q}&serp_type=default",
    "reddit": "https://www.reddit.com/search/?q={q}&sort=new",
}

_X_OPS: frozenset[str] = OPERADORES_X_CHAVE
_GOOGLE_OPS: frozenset[str] = OPERADORES_CHAVE

# Operadores que cada motor NÃO suporta (ou suporta de forma inconsistente).
NAO_SUPORTADOS: dict[str, frozenset[str]] = {
    "google": _X_OPS,
    "bing": frozenset({"before", "after", "*"}) | _X_OPS,
    "duckduckgo": frozenset({"before", "after", "*", "intext"}) | _X_OPS,
    "startpage": frozenset({"before", "after"}) | _X_OPS,
}
NAO_SUPORTADOS_EXTRA: dict[str, frozenset[str]] = {
    "x": _GOOGLE_OPS | {"*"},
    "tiktok": _GOOGLE_OPS | _X_OPS | {"*"},
    "youtube": _GOOGLE_OPS | _X_OPS | {"*"},
    "google_news": _X_OPS | {"*", "filetype", "inurl", "intitle", "intext"},
    "brave": _X_OPS | {"before", "after", "*", "intext"},
    "yandex": _X_OPS | {"before", "after", "*", "intext", "filetype"},
    "mojeek": _X_OPS | {"before", "after", "*", "intext", "inurl", "intitle", "filetype"},
    "bing_news": _X_OPS | {"before", "after", "*", "filetype", "inurl", "intitle", "intext"},
    "bluesky": _GOOGLE_OPS | _X_OPS | {"*"},
    "threads": _GOOGLE_OPS | _X_OPS | {"*"},
    "reddit": _GOOGLE_OPS | _X_OPS | {"*"},
}


def _limpar(t: str) -> str:
    return " ".join(t.replace('"', " ").split())


def citar(termo: str) -> str:
    """Coloca entre aspas se tiver espaço; mantém se já estiver entre aspas."""
    t = termo.strip()
    if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
        return '"' + _limpar(t[1:-1]) + '"'
    t = _limpar(t)
    return f'"{t}"' if " " in t else t


def grupo_or(itens: list[str]) -> str:
    partes = [citar(i) for i in itens if i.strip()]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    return "(" + " OR ".join(partes) + ")"


def compor_precisao(b: BlocoPrecisao) -> list[str]:
    partes: list[str] = []
    partes += [f'"{_limpar(f)}"' for f in b.frases_exatas if f.strip()]
    partes += [citar(t) for t in b.termos if t.strip()]
    partes += [g for g in (grupo_or(g) for g in b.grupos_or) if g]
    for par in b.curingas:
        limpos = [_limpar(x) for x in par if x.strip()]
        if len(limpos) >= 2:
            partes.append('"' + " * ".join(limpos) + '"')
    partes += [f"-{citar(e)}" for e in b.excluir if e.strip()]
    return partes


def compor_escopo(b: BlocoEscopo) -> list[str]:
    partes: list[str] = []
    sites = [f"site:{s.strip()}" for s in b.sites if s.strip()]
    if len(sites) == 1:
        partes.append(sites[0])
    elif sites:
        partes.append("(" + " OR ".join(sites) + ")")
    partes += [f"-site:{s.strip()}" for s in b.excluir_sites if s.strip()]
    if b.filetype and b.filetype.strip():
        partes.append(f"filetype:{b.filetype.strip().lstrip('.').lower()}")
    for chave in ("inurl", "intitle", "intext"):
        partes += [f"{chave}:{citar(v)}" for v in getattr(b, chave) if v.strip()]
    return partes


def compor_temporal(b: BlocoTemporal) -> list[str]:
    partes: list[str] = []
    if b.after:
        partes.append(f"after:{b.after.isoformat()}")
    if b.before:
        partes.append(f"before:{b.before.isoformat()}")
    return partes


def _handle(u: str) -> str:
    return u.strip().lstrip("@")


def compor_x(b: BlocoX) -> list[str]:
    """Bloco X/TweetDeck. Ordem: autores → destinatários → menções → filtros → janela since/until."""
    partes: list[str] = []
    autores = [f"from:{_handle(u)}" for u in b.from_ if _handle(u)]
    if len(autores) == 1:
        partes.append(autores[0])
    elif autores:
        partes.append("(" + " OR ".join(autores) + ")")
    partes += [f"to:{_handle(u)}" for u in b.to if _handle(u)]
    mencoes = [f"@{_handle(u)}" for u in b.mencoes if _handle(u)]
    if len(mencoes) == 1:
        partes.append(mencoes[0])
    elif mencoes:
        partes.append("(" + " OR ".join(mencoes) + ")")
    if b.excluir_retweets:
        partes.append("-is:retweet")
    if b.apenas_respostas:
        partes.append("is:reply")
    if b.apenas_verificados:
        partes.append("is:verified")
    partes += [f"has:{h.strip().lower()}" for h in b.has if h.strip()]
    if b.lang and b.lang.strip():
        partes.append(f"lang:{b.lang.strip().lower()}")
    for chave in ("min_faves", "min_retweets", "min_replies"):
        v = getattr(b, chave)
        if v is not None and v > 0:
            partes.append(f"{chave}:{v}")
    if b.since:
        partes.append(f"since:{b.since.isoformat()}")
    if b.until:
        partes.append(f"until:{b.until.isoformat()}")
    return partes


def preencher_template(query: str, valores: dict[str, str]) -> str:
    """Substitui placeholders literais do template (ex.: 'Termo a ser pesquisado') pelos valores."""
    resultado = query
    for chave in sorted(valores, key=len, reverse=True):  # maiores primeiro evita colisão parcial
        valor = valores[chave]
        if chave and valor:
            resultado = resultado.replace(chave, valor)
    return resultado


def compor(req: ComposeRequest, template_query: str | None = None) -> str:
    """Ordem: template → escopo → precisão → extra → temporal (Google) → X."""
    partes: list[str] = []
    if template_query:
        partes.append(preencher_template(template_query, req.valores_template))
    partes += compor_escopo(req.escopo)
    partes += compor_precisao(req.precisao)
    if req.extra.strip():
        partes.append(req.extra.strip())
    partes += compor_temporal(req.temporal)
    partes += compor_x(req.x)
    return " ".join(partes)


def deeplinks(query: str) -> dict[str, str]:
    q = quote_plus(query)
    return {motor: url.format(q=q) for motor, url in MOTORES.items()}


def deeplinks_extra(query: str) -> dict[str, str]:
    q = quote_plus(query)
    return {motor: url.format(q=q) for motor, url in MOTORES_EXTRA.items()}


def _usados(operadores: dict[str, list[str]], query: str) -> set[str]:
    usados = {k.lstrip("-") for k in operadores}
    if "*" in query:
        usados.add("*")
    return usados


def compatibilidade(operadores: dict[str, list[str]], query: str) -> dict[str, list[str]]:
    usados = _usados(operadores, query)
    return {motor: sorted(usados & nao) for motor, nao in NAO_SUPORTADOS.items() if usados & nao}


def compatibilidade_extra(operadores: dict[str, list[str]], query: str) -> dict[str, list[str]]:
    usados = _usados(operadores, query)
    return {motor: sorted(usados & nao) for motor, nao in NAO_SUPORTADOS_EXTRA.items() if usados & nao}
