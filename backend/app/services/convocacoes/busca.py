"""De um cartaz detectado para buscas: termos (frases, locais, siglas, hashtags) → convites abertos (WhatsApp/Telegram),
menções na web/redes (SearXNG + deeplinks) e monitor contínuo no Radar/assistente.

Extração determinística (regex sobre OCR + legenda); a IA (agent `extrator`) só enriquece quando o analista pedir.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.models.convocacao import Deteccao
from app.services import query_compose

logger = logging.getLogger("o51nt.convocacoes.busca")

MAX_TERMOS = 16
GENERICOS = ("ato", "manifestação", "protesto")
_FRASE = re.compile(r"[“\"]([^”\"]{6,120})[”\"]")
_SIGLA = re.compile(r"(?<![\w-])[A-Z]{3,7}(?![\w-])")
_HASHTAG = re.compile(r"#\w{3,40}")
_MENCAO = re.compile(r"(?<!\w)@\w{3,40}")
_MAIUSC = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w'’\-]+"
_LOCAL = re.compile(rf"\b(?:na|no|em|em frente (?:ao|à|a)|ao|à)\s+((?:{_MAIUSC}(?:\s+(?:de|do|da|dos|das|e|d')\s+{_MAIUSC}|\s+{_MAIUSC}){{0,5}}))")
_DATA = re.compile(r"\b\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", re.I)
_SIGLAS_RUIDO = {"OCR", "HTTP", "HTTPS", "URL", "PDF", "JPG", "PNG", "WWW", "HTML", "HOJE", "AMANHA", "AMANHÃ", "ATO", "ATOS", "GRANDE", "TODOS"}
_LOCAL_RUIDO = {"Horário", "Horario", "Hora", "Auditório", "Praça", "Rua", "Avenida", "Dia", "Ato", "Em", "Na", "No"}


@dataclass(slots=True)
class TermosBusca:
    frases: list[str] = field(default_factory=list)
    locais: list[str] = field(default_factory=list)
    organizacoes: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    mencoes: list[str] = field(default_factory=list)
    datas: list[str] = field(default_factory=list)
    termos: list[str] = field(default_factory=list)  # principais, na ordem de prioridade (frases → locais → siglas → hashtags)
    query_mencoes: str = ""
    deeplinks: dict[str, str] = field(default_factory=dict)
    ia: bool = False
    observacoes: str = ""

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dedupe(valores: list[str], max_len: int = 80) -> list[str]:
    out: list[str] = []
    vistos: set[str] = set()
    for v in valores:
        v = " ".join(str(v).split()).strip(" ,.;:-–—")[:max_len]
        if len(v) < 3:
            continue
        k = v.casefold()
        if k in vistos:
            continue
        vistos.add(k)
        out.append(v)
    return out


def _limpar_local(v: str) -> str:
    v = " ".join(v.split()).strip(" ,.;:")
    partes = v.split(" ")
    while partes and partes[-1].lower() in ("de", "do", "da", "dos", "das", "e", "d'"):
        partes.pop()
    v = " ".join(partes)
    return "" if (not v or v.split(" ")[0] in _LOCAL_RUIDO and len(partes) == 1) else v


def extrair_termos(texto: str, det: Deteccao | None = None) -> TermosBusca:
    """Frases entre aspas, locais ("na Praça X", "em Belo Horizonte"), siglas de entidades, hashtags, menções e datas."""
    t = texto or ""
    tb = TermosBusca()
    tb.frases = _dedupe([m.group(1) for m in _FRASE.finditer(t)], 120)
    locais = [_limpar_local(m.group(1)) for m in _LOCAL.finditer(t)]
    if det is not None and det.local_evento:
        locais = [det.local_evento.split("/")[0], *locais]
    tb.locais = _dedupe([x for x in locais if x and len(x.split()) <= 6])
    tb.organizacoes = _dedupe([s for s in _SIGLA.findall(t) if s not in _SIGLAS_RUIDO and len(s) >= 4 or s in ("PRF", "TSE", "TRE", "MST", "CUT", "UNE")], 20)
    tb.hashtags = _dedupe(_HASHTAG.findall(t), 41)
    tb.mencoes = _dedupe(_MENCAO.findall(t), 41)
    datas = _DATA.findall(t)
    if det is not None and det.data_evento:
        datas = [det.data_evento.strftime("%d/%m/%Y"), *datas]
    tb.datas = _dedupe(datas, 20)
    tb.termos = _dedupe([*tb.frases, *tb.locais, *tb.organizacoes, *tb.hashtags, *tb.mencoes], 120)[:MAX_TERMOS]
    tb.query_mencoes = montar_query_mencoes(tb.termos)
    tb.deeplinks = montar_deeplinks(tb.query_mencoes)
    return tb


def montar_query_mencoes(termos: list[str], genericos: tuple[str, ...] = GENERICOS) -> str:
    """Query na sintaxe do Query Builder/Radar: (termos em OR) + (ato OR manifestação OR protesto)."""
    principais = [t for t in termos if t][:6]
    if not principais:
        return ""
    def q(t: str) -> str:
        return t if t.startswith(("#", "@")) or " " not in t else f'"{t}"'
    grupo = " OR ".join(q(t) for t in principais)
    return f"({grupo}) ({' OR '.join(genericos)})" if len(principais) > 1 else f"{q(principais[0])} ({' OR '.join(genericos)})"


def montar_deeplinks(query: str) -> dict[str, str]:
    if not query:
        return {}
    try:
        return query_compose.deeplinks(query) | query_compose.deeplinks_extra(query)
    except Exception:  # deeplinks são conveniência
        return query_compose.deeplinks(query)


def texto_da_deteccao(det: Deteccao) -> str:
    return "\n".join(p for p in ((det.texto_ocr or "").strip(), (det.texto_post or "").strip()) if p)


async def enriquecer_com_ia(tb: TermosBusca, texto: str) -> TermosBusca:
    """Pede ao agent `extrator` termos de busca adicionais (nomes de atos, coletivos, locais). Falha → termos originais."""
    from app.services.ia import prompts
    from app.services.ia.cliente_openclaw import extrair_json, get_cliente

    cliente = get_cliente()
    if not cliente.configurado:
        tb.observacoes = "assistente de IA sem token do gateway"
        return tb
    try:
        resp = await cliente.perguntar("extrator", prompts.prompt_termos_busca(texto, tb.termos), max_tokens=500)
        dados = extrair_json(resp.texto)
    except Exception as exc:
        tb.observacoes = f"IA indisponível: {str(exc)[:160]}"
        return tb
    novos = [str(x) for x in (dados.get("termos") or []) if isinstance(x, (str, int))]
    tb.hashtags = _dedupe([*tb.hashtags, *[str(h) for h in (dados.get("hashtags") or [])]], 41)
    tb.termos = _dedupe([*tb.frases, *novos, *tb.termos, *tb.hashtags], 120)[:MAX_TERMOS]  # sugestões da IA logo após as frases
    tb.query_mencoes = montar_query_mencoes(tb.termos)
    tb.deeplinks = montar_deeplinks(tb.query_mencoes)
    tb.ia = True
    tb.observacoes = str(dados.get("observacoes") or "")[:300]
    return tb


def resultados_busca(res: Any) -> list[dict[str, Any]]:
    """Normaliza os resultados do SearXNG para a tela (título, url, trecho, motores, data)."""
    out: list[dict[str, Any]] = []
    for r in getattr(res, "resultados", []) or []:
        url = str(r.get("url") or "")
        if not url:
            continue
        out.append({"titulo": str(r.get("title") or r.get("titulo") or url)[:200], "url": url, "trecho": str(r.get("content") or "")[:300], "engines": r.get("engines") or [], "publicado_em": r.get("publishedDate")})
    return out


def serializar(tb: TermosBusca) -> str:
    return json.dumps(tb.como_dict(), ensure_ascii=False)
