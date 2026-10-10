"""Camada de verificação do assistente (referência: OWASP OSINT Verification Standard, OOVS v0.1.0).

Três regras do OOVS implementadas aqui, todas determinísticas (sem custo de IA, exceto o aterramento, que é uma
chamada barata só para itens RELEVANTE):

1. **Independência por origem distinta**: corroboração conta origens, não menções. Fontes do mesmo domínio
   registrável (g1.globo.com e www.g1.globo.com são uma origem) ou com texto quase idêntico (republicação de agência,
   shingles de 3 palavras com Jaccard ≥ limiar) viram um único grupo. A saída automática do sistema (o cartão) nunca
   conta como corroboração das próprias entradas, e a URL do item analisado é a origem, não uma corroboração.
2. **Aterramento**: cada afirmação do cartão é conferida contra os trechos citados pelo pesquisador (agent barato).
3. **Etiqueta de confiança derivada mecanicamente** de (origens distintas, verificação do pesquisador, aterramento):
   um resumo favorável nunca se sobrepõe a um detalhe desfavorável.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.services.radar import normalizar

NORMA = "OOVS 0.1.0"
ETIQUETAS = ("alta", "media", "baixa", "nao_verificada", "refutada")
_ORDEM = {"alta": 3, "media": 2, "baixa": 1}
# sufixos públicos de dois rótulos mais comuns no uso do projeto (sem lista PSL completa: basta para agrupar imprensa/governo)
_SUFIXOS_2 = frozenset(
    {"com.br", "org.br", "gov.br", "leg.br", "jus.br", "net.br", "edu.br", "mil.br", "art.br", "blog.br", "eco.br", "emp.br", "jor.br", "not.br", "tv.br", "rec.br", "esp.br", "ind.br", "inf.br", "psi.br", "adv.br", "eng.br", "far.br", "med.br", "odo.br", "pro.br", "srv.br", "tmp.br", "wiki.br", "co.uk", "org.uk", "gov.uk", "ac.uk", "com.ar", "com.mx", "com.pt", "gov.pt", "com.au", "co.jp", "com.co", "gov.co", "com.uy", "com.py", "com.pe", "gov.ar", "org.ar", "edu.ar"}
)
_PREFIXOS = ("www.", "m.", "amp.", "mobile.", "noticias.", "news.")


def dominio_registravel(url: str) -> str:
    """'https://www.g1.globo.com/x' → 'globo.com'; 'https://agenciabrasil.ebc.com.br/y' → 'ebc.com.br'; 'https://m.folha.uol.com.br' → 'uol.com.br'."""
    host = (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    if not host:
        return ""
    for p in _PREFIXOS:
        if host.startswith(p) and host.count(".") >= 2:
            host = host[len(p) :]
            break
    partes = host.split(".")
    if len(partes) <= 2:
        return host
    if ".".join(partes[-2:]) in _SUFIXOS_2:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def _shingles(texto: str, n: int = 3) -> set[str]:
    palavras = [p for p in re.split(r"[^\w]+", normalizar(texto)) if p]
    if len(palavras) < n:
        return {" ".join(palavras)} if palavras else set()
    return {" ".join(palavras[i : i + n]) for i in range(len(palavras) - n + 1)}


def similaridade(a: str, b: str) -> float:
    """Jaccard entre shingles de 3 palavras (0..1); textos curtos demais (< 5 shingles) não são comparados (0)."""
    sa, sb = _shingles(a), _shingles(b)
    if len(sa) < 5 or len(sb) < 5:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _texto_fonte(f: dict[str, Any]) -> str:
    """Texto comparado entre fontes: o trecho citado (republicações trocam a manchete, não o corpo); título só na falta dele."""
    trecho = str(f.get("trecho") or "").strip()
    if len(_shingles(trecho)) >= 5:
        return trecho
    return " ".join(str(f.get(k) or "") for k in ("titulo", "trecho")).strip()


def agrupar_origens(fontes: list[dict[str, Any]], url_item: str | None = None, limiar: float = 0.85) -> dict[str, Any]:
    """Agrupa fontes em origens distintas (domínio registrável ∪ texto quase idêntico).

    Retorna origens_distintas (nº de grupos), corroboracoes (grupos sem a origem do próprio item), grupos e duplicadas.
    """
    urls = [str(f.get("url") or "").strip() for f in fontes]
    n = len(urls)
    pai = list(range(n))

    def achar(i: int) -> int:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    def unir(i: int, j: int) -> None:
        pai[achar(i)] = achar(j)

    dominios = [dominio_registravel(u) for u in urls]
    textos = [_texto_fonte(f) for f in fontes]
    for i in range(n):
        for j in range(i + 1, n):
            if (dominios[i] and dominios[i] == dominios[j]) or urls[i] == urls[j] or similaridade(textos[i], textos[j]) >= limiar:
                unir(i, j)
    grupos: dict[int, list[int]] = {}
    for i in range(n):
        grupos.setdefault(achar(i), []).append(i)
    dominio_item = dominio_registravel(url_item or "")
    saida = []
    for membros in grupos.values():
        dom = dominios[membros[0]] or "?"
        inclui_item = bool(dominio_item) and any(dominios[m] == dominio_item for m in membros)
        saida.append({"dominio": dom, "fontes": membros, "urls": [urls[m] for m in membros], "inclui_item": inclui_item})
    saida.sort(key=lambda g: (not g["inclui_item"], g["dominio"]))
    distintas = len(saida)
    corroboracoes = sum(1 for g in saida if not g["inclui_item"])
    return {"origens_distintas": distintas, "corroboracoes": corroboracoes, "duplicadas": n - distintas, "grupos": saida}


def etiqueta_confianca(corroboracoes: int, verificacao: str | None, aterramento: dict[str, Any] | None, houve_pesquisa: bool) -> tuple[str, list[str]]:
    """Etiqueta mecânica: base pelas corroborações, limitada pela verificação do pesquisador e pelo aterramento."""
    motivos: list[str] = []
    if not houve_pesquisa:
        return "nao_verificada", ["sem etapa de pesquisa (verificação só sob pedido ou severidade abaixo do mínimo)"]
    if verificacao == "falso":
        return "refutada", ["o pesquisador classificou o item como falso"]
    nivel = 3 if corroboracoes >= 2 else 2 if corroboracoes == 1 else 1
    motivos.append(f"{corroboracoes} origem(ns) distinta(s) além da fonte do item")
    teto = {"confirmado": 3, "parcial": 2, "nao_confirmado": 1, None: 1}.get(verificacao, 1)
    if teto < nivel:
        motivos.append(f"verificação do pesquisador: {verificacao or 'ausente'}")
    nivel = min(nivel, teto)
    if aterramento and aterramento.get("total"):
        s, tot = int(aterramento.get("sustentadas", 0)), int(aterramento["total"])
        if s < tot / 2:
            motivos.append(f"aterramento fraco: {s}/{tot} afirmações sustentadas pelas fontes")
            nivel = 1
        elif s < tot:
            motivos.append(f"aterramento parcial: {s}/{tot} afirmações sustentadas")
            nivel = max(1, nivel - 1)
        else:
            motivos.append(f"aterramento completo: {s}/{tot} afirmações sustentadas")
    for nome, v in _ORDEM.items():
        if v == nivel:
            return nome, motivos
    return "baixa", motivos


def resumo_verificacao(url_item: str | None, pesquisa: dict[str, Any] | None, cartao: dict[str, Any] | None, aterramento: dict[str, Any] | None) -> dict[str, Any]:
    """Objeto gravado em ia_tarefa.verificacao_json e exposto na API (aditivo)."""
    fontes: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for f in (pesquisa or {}).get("fontes") or []:
        if isinstance(f, dict) and f.get("url") and f["url"] not in vistos:
            fontes.append(f)
            vistos.add(f["url"])
    for u in (cartao or {}).get("fontes") or []:  # URLs citadas só no cartão (sem trecho): contam por domínio
        if isinstance(u, str) and u and u not in vistos:
            fontes.append({"url": u})
            vistos.add(u)
    origens = agrupar_origens(fontes, url_item)
    houve_pesquisa = bool(pesquisa and (pesquisa.get("verificacao") or pesquisa.get("resposta")))
    verificacao = (pesquisa or {}).get("verificacao")
    etiqueta, motivos = etiqueta_confianca(origens["corroboracoes"], verificacao, aterramento, houve_pesquisa)
    lacunas = str((pesquisa or {}).get("lacunas") or "").strip()
    if lacunas:
        motivos.append(f"lacunas registradas: {lacunas[:200]}")
    return {
        "norma": NORMA,
        "etiqueta": etiqueta,
        "origens_distintas": origens["origens_distintas"],
        "corroboracoes": origens["corroboracoes"],
        "duplicadas": origens["duplicadas"],
        "grupos": origens["grupos"],
        "verificacao": verificacao,
        "aterramento": {"sustentadas": aterramento.get("sustentadas", 0), "total": aterramento.get("total", 0)} if aterramento else None,
        "motivos": motivos,
    }


def texto_etiqueta(v: dict[str, Any] | None) -> str:
    """Linha curta para Telegram/alerta: 'confiança média · 2 origens distintas · aterramento 3/3'."""
    if not v:
        return ""
    rotulo = {"alta": "alta", "media": "média", "baixa": "baixa", "nao_verificada": "não verificada", "refutada": "REFUTADA"}.get(v.get("etiqueta", ""), "?")
    partes = [f"confiança {rotulo}", f"{v.get('origens_distintas', 0)} origem(ns) distinta(s)"]
    at = v.get("aterramento")
    if at and at.get("total"):
        partes.append(f"aterramento {at['sustentadas']}/{at['total']}")
    return " · ".join(partes)
