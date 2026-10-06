"""Coleta de hashtags em fontes públicas listadas no PDF (trends24; OneMillionTweetMap encerrado).

Matching ignora acentos e caixa: #Eleicoes2026 ≡ #Eleições2026 ≡ #ELEICOES2026. A forma
original é preservada em `tag` e a chave de comparação fica em `chave_normalizada`.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from sqlmodel import Session, col, select

from app.models._base import agora
from app.models.hashtag import Hashtag, HashtagSnapshot
from app.services.scraper import FONTES_HASHTAGS, EthicalScraper, extrair_hashtags

TOP_N = 50


def normalizar_tag(tag: str) -> str:
    """Forma de exibição: sem espaços e com '#' na frente (acentos preservados)."""
    t = tag.strip().replace(" ", "")
    return t if t.startswith("#") else f"#{t}"


def chave_normalizada(tag: str) -> str:
    """Chave de dedup/matching: NFKD + remoção de combining marks + casefold.

    DECISÃO DELIBERADA — diverge do X/Twitter, não é bug:
    - O X trata #Eleicoes e #eleicoes como a mesma tag (caixa), mas #Eleições e #Eleicoes
      como tags DIFERENTES (acento). Aqui unificamos as duas coisas, para que o analista
      encontre todas as candidatas.
    - Em contrapartida, a forma original coletada é SEMPRE preservada (`Hashtag.tag`) e exibida;
      a UI mostra cada variante em chip e a coleta devolve `variantes_encontradas`, com a
      contagem por forma em `fontes[*].variantes`. Nunca há merge silencioso: a soma vem
      sempre acompanhada das variantes que a compõem.
    """
    decomposta = unicodedata.normalize("NFKD", normalizar_tag(tag))
    return "".join(c for c in decomposta if not unicodedata.combining(c)).casefold()


def variantes(session: Session, tag: str, rede: str | None = None) -> list[Hashtag]:
    """Todas as formas cadastradas que compartilham a chave normalizada de `tag`."""
    stmt = select(Hashtag).where(Hashtag.chave_normalizada == chave_normalizada(tag))
    if rede:
        stmt = stmt.where(Hashtag.rede == rede)
    return list(session.exec(stmt.order_by(col(Hashtag.contagem).desc(), Hashtag.tag)).all())


def upsert_hashtag(session: Session, tag: str, rede: str, contagem: int, fonte: str) -> Hashtag:
    h = session.exec(select(Hashtag).where(Hashtag.tag == tag, Hashtag.rede == rede)).first()
    if h is None:
        h = Hashtag(tag=tag, chave_normalizada=chave_normalizada(tag), rede=rede, contagem=contagem, fonte=fonte)
    else:
        h.contagem = contagem
        h.ultima_vez = agora()
        h.fonte = fonte
        h.chave_normalizada = chave_normalizada(tag)
    session.add(h)
    return h


async def coletar(session: Session, scraper: EthicalScraper, tag_alvo: str, fontes: list[str] | None = None) -> dict[str, Any]:
    """Raspa as fontes; atualiza a tabela com o top N e grava snapshot da tag alvo (somando variantes)."""
    tag_alvo = normalizar_tag(tag_alvo)
    chave_alvo = chave_normalizada(tag_alvo)
    resumo: dict[str, Any] = {"tag": tag_alvo, "chave_normalizada": chave_alvo, "fontes": {}}
    total_alvo = 0
    variantes_vistas: dict[str, int] = {}
    for nome in fontes or ["trends24"]:
        url = FONTES_HASHTAGS.get(nome)
        if url is None:
            resumo["fontes"][nome] = {"erro": "fonte desconhecida"}
            continue
        res = await scraper.buscar(url, usar_js=(nome == "onemilliontweetmap"))
        if not res.ok:
            resumo["fontes"][nome] = {"erro": res.erro, "status": res.status, "url": url}
            continue
        contagens = extrair_hashtags(res.html)
        top = sorted(contagens.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]
        for tag, n in top:
            upsert_hashtag(session, tag, "x", n, nome)
        da_fonte = {t: n for t, n in contagens.items() if chave_normalizada(t) == chave_alvo}
        for t, n in da_fonte.items():
            variantes_vistas[t] = variantes_vistas.get(t, 0) + n
        n_alvo = sum(da_fonte.values())
        total_alvo += n_alvo
        alvo = upsert_hashtag(session, tag_alvo, "x", n_alvo, nome)
        session.flush()
        assert alvo.id is not None
        session.add(HashtagSnapshot(hashtag_id=alvo.id, contagem=n_alvo, fonte=nome, origem_url=url, sha256=res.sha256))
        resumo["fontes"][nome] = {
            "url": url,
            "sha256": res.sha256,
            "coletado_em": res.coletado_em,
            "encontradas": len(contagens),
            "ocorrencias_alvo": n_alvo,
            "variantes": da_fonte,
            "top": top[:10],
        }
    session.commit()
    resumo["ocorrencias_alvo"] = total_alvo
    resumo["variantes_encontradas"] = sorted(variantes_vistas)
    return resumo
