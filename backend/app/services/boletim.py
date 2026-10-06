"""Boletim diário no formato do documento 'Op. Eleições 2026' + perfis vigiados."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta
from typing import Any, Literal

from app.models.agenda import AgendaEvento
from app.models.boletim import BoletimItem, Perfil
from app.services.agenda import dia_semana, rodovias_lista
from app.services.query_compose import citar, grupo_or

REDES: tuple[str, ...] = ("x", "instagram", "facebook", "tiktok", "youtube", "telegram", "mastodon", "site", "outro")
CATEGORIAS_PERFIL: tuple[str, ...] = ("candidato", "partido", "institucional", "midia", "coletivo", "outro")
SECOES: tuple[str, ...] = ("noticia", "fake_news", "manifestacao", "imagem_institucional", "hashtag", "grupo", "perfil", "outro")

# Ordem e títulos exatamente como no boletim.
ORDEM_SECOES: tuple[str, ...] = ("hashtag", "noticia", "fake_news", "manifestacao", "agenda", "imagem_institucional", "grupo", "perfil", "outro")
SECAO_TITULO: dict[str, str] = {
    "hashtag": "HASHTAGS",
    "noticia": "NOTÍCIAS RELEVANTES",
    "fake_news": "FAKE NEWS",
    "manifestacao": "MANIFESTAÇÕES IDENTIFICADAS",
    "agenda": "AGENDA DOS CANDIDATOS",
    "imagem_institucional": "IMAGEM INSTITUCIONAL",
    "grupo": "LINKS DE GRUPOS IDENTIFICADOS",
    "perfil": "PERFIS PARA ACOMPANHAR",
    "outro": "OUTRAS INFORMAÇÕES",
}
MESES = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")

_URL_HANDLE: dict[str, re.Pattern[str]] = {
    "x": re.compile(r"(?:x\.com|twitter\.com)/(?:#!/)?@?([A-Za-z0-9_]{1,15})"),
    "instagram": re.compile(r"instagram\.com/([A-Za-z0-9_.]+)"),
    "facebook": re.compile(r"facebook\.com/([A-Za-z0-9_.\-]+)"),
    "tiktok": re.compile(r"tiktok\.com/@([A-Za-z0-9_.]+)"),
    "youtube": re.compile(r"youtube\.com/(?:@|c/|channel/|user/)([A-Za-z0-9_.\-]+)"),
    "telegram": re.compile(r"(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]+)"),
    "mastodon": re.compile(r"https?://([^/\s]+)/@([A-Za-z0-9_]+)"),
}
_HANDLE_OK = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def titulo_boletim(d: date) -> str:
    return f"INFORMAÇÕES RELEVANTES - {d.day:02d} {MESES[d.month - 1]} {d.year} ({dia_semana(d)})"


def normalizar_handle(rede: str, valor: str) -> str:
    """Aceita '@usuario', 'usuario' ou a URL do perfil; devolve o handle canônico (site/outro: a URL)."""
    v = (valor or "").strip()
    if not v:
        raise ValueError("informe o usuário ou a URL do perfil")
    if rede in ("site", "outro"):
        if not v.startswith(("http://", "https://")):
            raise ValueError("para 'site'/'outro' informe a URL completa (http/https)")
        return v
    if v.startswith(("http://", "https://")):
        m = _URL_HANDLE[rede].search(v)
        if not m:
            raise ValueError(f"não reconheci um perfil de {rede} nessa URL")
        return f"{m.group(2)}@{m.group(1)}" if rede == "mastodon" else m.group(1)
    v = v.lstrip("@")
    if rede == "mastodon":
        if "@" not in v:
            raise ValueError("mastodon: use usuario@instancia")
        return v
    if not _HANDLE_OK.match(v):
        raise ValueError("usuário inválido (letras, dígitos, ponto, hífen e _)")
    return v


def url_perfil(rede: str, handle: str) -> str:
    if rede == "x":
        return f"https://x.com/{handle}"
    if rede == "instagram":
        return f"https://www.instagram.com/{handle}/"
    if rede == "facebook":
        return f"https://www.facebook.com/{handle}"
    if rede == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if rede == "youtube":
        return f"https://www.youtube.com/@{handle}"
    if rede == "telegram":
        return f"https://t.me/s/{handle}"  # prévia pública de canal (sem login)
    if rede == "mastodon":
        usuario, _, instancia = handle.partition("@")
        return f"https://{instancia}/@{usuario}"
    return handle  # site / outro: handle é a URL


def query_mencoes(p: Perfil, motor: Literal["google", "x"] = "google", referencia: date | None = None) -> str:
    """Query para achar menções/publicações recentes do perfil (véspera em diante)."""
    d = ((referencia or date.today()) - timedelta(days=1)).isoformat()
    termos: list[str] = []
    if p.rotulo.strip():
        termos.append(citar(p.rotulo))
    if p.rede not in ("site", "outro") and p.rede != "mastodon":
        termos.append(p.handle)
    if motor == "x":
        if p.rede == "x":
            return f"(from:{p.handle} OR @{p.handle}) -is:retweet since:{d}"
        base = grupo_or(termos) if termos else citar(p.handle)
        return f"{base} -is:retweet since:{d}"
    base = grupo_or(termos) if termos else citar(p.handle)
    return f"{base} after:{d}"


# ------------------------------------------------------------------ renderização do boletim
def _linha_item(i: BoletimItem) -> str:
    partes = [f"**{i.titulo}**"]
    if i.fonte:
        partes.append(f"({i.fonte})")
    if i.url:
        partes.append(f"— {i.url}")
    linha = "- " + " ".join(partes)
    if i.resumo:
        linha += f"\n  {i.resumo}"
    if i.evidence_id:
        linha += f"\n  [evidência #{i.evidence_id}]"
    return linha


def _linha_evento(e: AgendaEvento) -> str:
    hora = e.hora_inicio + (f"–{e.hora_fim}" if e.hora_fim else "") if e.hora_inicio else "—"
    local = ", ".join(x for x in (e.local, "/".join(x for x in (e.cidade, e.uf) if x)) if x)
    partes = [hora, f"{e.titulo} ({e.tipo})"]
    if local:
        partes.append(local)
    if e.rodovias:
        partes.append(", ".join(rodovias_lista(e)))
    if e.status == "cancelado":
        partes.append("CANCELADO")
    linha = "- " + " — ".join(partes)
    if e.impacto_rodovia:
        linha += " — PODERÁ IMPACTAR O FLUXO VIÁRIO NAS RODOVIAS FEDERAIS"
    if e.fonte_url:
        linha += f" (Fonte: {e.fonte_url})"
    return linha


def gerar_markdown(ctx: dict[str, Any]) -> str:
    """ctx: data, secoes {secao: [BoletimItem]}, agenda [AgendaEvento], perfis [Perfil], hashtags [str], convites [dict]."""
    d: date = ctx["data"]
    secoes: dict[str, list[BoletimItem]] = ctx.get("secoes", {})
    out: list[str] = [f"# {titulo_boletim(d)}", ""]
    for secao in ORDEM_SECOES:
        out.append(f"## {SECAO_TITULO[secao]}")
        corpo: list[str] = []
        if secao == "hashtag":
            tags: list[str] = ctx.get("hashtags", [])
            if tags:
                corpo.append(" ".join(tags))
        if secao == "agenda":
            eventos: list[AgendaEvento] = ctx.get("agenda", [])
            por_cand: dict[str, list[AgendaEvento]] = {}
            for e in eventos:
                por_cand.setdefault(e.candidato, []).append(e)
            for cand, evs in sorted(por_cand.items(), key=lambda kv: kv[0].lower()):
                partido = f" ({evs[0].partido})" if evs[0].partido else ""
                corpo.append(f"**{cand}{partido}**")
                corpo += [_linha_evento(e) for e in evs]
        if secao == "grupo":
            for c in ctx.get("convites", []):
                corpo.append(f"- {c['plataforma']} — {c['url']} (termo: {c['termo']}; visto em {c['last_seen']})")
        if secao == "perfil":
            for p in ctx.get("perfis", []):
                rot = f"{p.rotulo} — " if p.rotulo else ""
                corpo.append(f"- {rot}{p.url} ({p.rede}, {p.categoria})")
        corpo += [_linha_item(i) for i in secoes.get(secao, [])]
        out += corpo if corpo else ["-"]
        out.append("")
    out.append(f"_Gerado pelo O51NT Workbench — dados locais, sem envio a terceiros._")
    return "\n".join(out) + "\n"


def gerar_html(ctx: dict[str, Any]) -> str:
    """Versão imprimível (o navegador gera o PDF com Ctrl+P)."""
    d: date = ctx["data"]
    md = gerar_markdown(ctx)
    corpo: list[str] = []
    for linha in md.splitlines():
        if linha.startswith("# "):
            corpo.append(f"<h1>{html.escape(linha[2:])}</h1>")
        elif linha.startswith("## "):
            corpo.append(f"<h2>{html.escape(linha[3:])}</h2>")
        elif linha.startswith("- "):
            texto = html.escape(linha[2:])
            texto = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)
            texto = re.sub(r"(https?://[^\s)]+)", r'<a href="\1">\1</a>', texto)
            corpo.append(f"<li>{texto}</li>")
        elif linha.startswith("  "):
            corpo.append(f'<p class="sub">{html.escape(linha.strip())}</p>')
        elif linha.startswith("**") and linha.endswith("**"):
            corpo.append(f"<h3>{html.escape(linha.strip('*'))}</h3>")
        elif linha.startswith("_") and linha.endswith("_"):
            corpo.append(f"<footer>{html.escape(linha.strip('_'))}</footer>")
        elif linha.strip() == "-":
            corpo.append('<p class="vazio">—</p>')
        elif linha.strip():
            corpo.append(f"<p>{html.escape(linha)}</p>")
    # agrupa <li> consecutivos em <ul>
    saida: list[str] = []
    aberto = False
    for h in corpo:
        if h.startswith("<li>") and not aberto:
            saida.append("<ul>")
            aberto = True
        elif not h.startswith("<li>") and aberto:
            saida.append("</ul>")
            aberto = False
        saida.append(h)
    if aberto:
        saida.append("</ul>")
    return (
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(titulo_boletim(d))}</title>"
        "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}"
        "h1{font-size:1.25rem;text-align:center}h2{font-size:1rem;margin-top:1.5rem;border-bottom:1px solid #999;padding-bottom:.2rem}"
        "h3{font-size:.95rem;margin:.8rem 0 .2rem}ul{margin:.2rem 0 .2rem 1.2rem;padding:0}li{margin:.25rem 0}"
        ".sub{margin:0 0 .4rem 1.6rem;color:#333}.vazio{color:#777;margin:.2rem 0}footer{margin-top:2rem;font-size:.8rem;color:#555}"
        "a{color:#0645ad;word-break:break-all}@media print{body{margin:0;max-width:none}a{color:#000}}</style></head><body>"
        + "\n".join(saida)
        + "</body></html>"
    )
