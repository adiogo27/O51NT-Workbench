"""Persistência de uma análise: Evidence (bytes) + Deteccao (dedup por sha256/pHash) + Alerta + convites achados."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlmodel import Session, col, select

from app.models._base import agora
from app.models.alerta import Alerta
from app.models.convocacao import Deteccao, DeteccaoOcorrencia, ReferenciaCartaz
from app.models.invite import Invite
from app.models.monitor import Monitor
from app.models.settings import Preferencias
from app.services import alertas_db, evidence_store
from app.services.convocacoes import imagem as img_mod
from app.services.convocacoes.analisador import LIMIAR_PHASH_IGUAL, Analise, Entrada, RefCache, compilar_monitores

logger = logging.getLogger("o51nt.convocacoes")


@dataclass(slots=True)
class ResultadoRegistro:
    deteccao: Deteccao
    nova: bool
    ocorrencia: DeteccaoOcorrencia | None
    alerta: Alerta | None
    convites_registrados: int


def carregar_referencias(session: Session) -> list[RefCache]:
    out: list[RefCache] = []
    for r in session.exec(select(ReferenciaCartaz)).all():
        emb = np.frombuffer(r.embedding, dtype=np.float32) if r.embedding else None
        out.append(RefCache(id=r.id or 0, phash=r.phash, embedding=emb, rotulo=r.rotulo))
    return out


def monitores_compilados(session: Session):  # noqa: ANN201
    return compilar_monitores(list(session.exec(select(Monitor).where(Monitor.ativo == True)).all()))  # noqa: E712


def _existente_por_imagem(session: Session, sha256: str, phash: str) -> tuple[Deteccao | None, bool]:
    """(detecção já existente, é_variante). Mesma imagem = sha256 igual ou pHash ≤ 4."""
    if sha256:
        d = session.exec(select(Deteccao).where(Deteccao.sha256 == sha256)).first()
        if d is not None:
            return d, False
    if phash:
        for d in session.exec(select(Deteccao).where(Deteccao.phash != "").order_by(col(Deteccao.id).desc()).limit(5000)).all():
            if img_mod.distancia(phash, d.phash) <= 4:
                return d, True
    return None, False


def _titulo_alerta(an: Analise, entrada: Entrada) -> str:
    partes = []
    if an.lexico.nao_pacifico:
        partes.append("ATO NÃO PACÍFICO")
    elif an.lexico.termos.get("convocacao"):
        partes.append("convocação")
    if an.lexico.data_evento:
        partes.append(an.lexico.data_evento.strftime("%d/%m"))
    if an.lexico.local:
        partes.append(an.lexico.local)
    base = " · ".join(partes) or "possível convocação"
    return f"[{an.severidade}] {base} ({entrada.plataforma})"[:300]


async def registrar_analise(
    session: Session,
    entrada: Entrada,
    an: Analise,
    prefs: Preferencias,
    origem: str = "manual",
    salvar_evidencia: bool = True,
    fonte_id: int | None = None,
) -> ResultadoRegistro:
    """Grava a análise. Imagem já vista → só nova ocorrência (propagação). Alerta se score ≥ limiar."""
    sha = an.imagem.sha256 if an.imagem else ""
    phash = an.imagem.phash if an.imagem else ""
    existente, variante = _existente_por_imagem(session, sha, phash) if an.imagem else (None, False)
    post_url = entrada.post_url or entrada.imagem_url or ""

    if existente is not None:
        oc: DeteccaoOcorrencia | None = None
        if post_url and session.exec(select(DeteccaoOcorrencia).where(DeteccaoOcorrencia.post_url == post_url)).first() is None and post_url != existente.post_url:
            oc = DeteccaoOcorrencia(
                deteccao_id=existente.id or 0, post_url=post_url, imagem_url=entrada.imagem_url, plataforma=entrada.plataforma,
                autor=entrada.autor, publicado_em=entrada.publicado_em, variante=variante, phash=phash, fonte_id=fonte_id,
            )
            session.add(oc)
            existente.ocorrencias = (existente.ocorrencias or 1) + 1
            session.add(existente)
            session.commit()
            session.refresh(existente)
            session.refresh(oc)
        return ResultadoRegistro(deteccao=existente, nova=False, ocorrencia=oc, alerta=None, convites_registrados=0)

    evidencia_id: int | None = None
    if an.imagem is not None and salvar_evidencia and entrada.imagem:
        ext = an.imagem.mime.split("/")[-1].replace("jpeg", "jpg")
        nome = f"cartaz_{an.imagem.sha256[:12]}.{ext}"
        ev = evidence_store.salvar_bytes(entrada.imagem, nome, an.imagem.mime, origem_url=post_url or None, tipo="imagem",
                                         notas=f"Convocações/{origem}: score {an.score} ({an.severidade})")
        session.add(ev)
        session.commit()
        session.refresh(ev)
        evidence_store.registrar_manifesto(ev)
        evidencia_id = ev.id

    det = Deteccao(
        origem=origem,
        plataforma=entrada.plataforma,
        post_url=post_url,
        imagem_url=entrada.imagem_url,
        autor=entrada.autor[:200],
        publicado_em=entrada.publicado_em,
        evidencia_id=evidencia_id,
        sha256=sha,
        phash=phash,
        dhash=an.imagem.dhash if an.imagem else "",
        texto_post=entrada.texto_post[:5000],
        texto_ocr=an.texto_ocr[:5000],
        ocr_confianca=an.ocr.confianca if an.ocr else 0.0,
        ocr_modelo=an.ocr.modelo if an.ocr else "",
        qr_json=json.dumps(an.qr, ensure_ascii=False),
        convites_json=json.dumps([{"plataforma": p, "url": u} for p, u in an.convites], ensure_ascii=False),
        termos_lexico_json=json.dumps(an.lexico.termos, ensure_ascii=False),
        termos_monitor="; ".join(f"{nome}: {' | '.join(ts)}" for _, nome, ts in an.termos_monitor)[:1000],
        monitor_ids=",".join(str(mid) for mid, _, _ in an.termos_monitor),
        tempo=an.lexico.tempo,
        data_evento=an.lexico.data_evento,
        hora_evento=an.lexico.hora_evento,
        local_evento=an.lexico.local or "",
        noticiando=an.lexico.noticiando,
        nao_pacifico=an.lexico.nao_pacifico,
        score=an.score,
        score_detalhe_json=json.dumps({**an.decomposicao, "lexico": an.lexico.resumo(), "visual": an.visual, "referencia": an.referencia, "ms": an.ms, "capacidades": an.capacidades}, ensure_ascii=False, default=str),
        severidade=an.severidade,
        referencia_id=an.referencia[0] if an.referencia and an.referencia[1] >= 50 else None,
    )
    session.add(det)
    session.commit()
    session.refresh(det)

    # convites/QR achados no cartaz → tabela de convites (fonte_url = post)
    registrados = 0
    for plat, url in an.convites:
        inv = session.exec(select(Invite).where(Invite.url == url)).first()
        if inv is None:
            inv = Invite(plataforma=plat, url=url, termo="convocacoes", origem=f"deteccao:{det.id}", fonte_url=post_url, hash_conteudo=sha)
            registrados += 1
        else:
            inv.last_seen = agora()
            if not inv.fonte_url:
                inv.fonte_url = post_url
        session.add(inv)
    if registrados or an.convites:
        session.commit()

    alerta: Alerta | None = None
    if an.score >= prefs.convocacoesLimiarAlerta:
        alerta = Alerta(
            tipo="convocacao",
            severidade=an.severidade,
            titulo=_titulo_alerta(an, entrada),
            resumo=(an.texto_ocr or entrada.texto_post)[:400],
            url=post_url,
            deteccao_id=det.id,
        )
        extra: dict[str, Any] = {
            "score": an.score,
            "plataforma": entrada.plataforma,
            "termos": an.lexico.termos,
            "data_evento": an.lexico.data_evento.isoformat() if an.lexico.data_evento else None,
            "local": an.lexico.local,
            "imagem_sha256": sha,
            "convites": [u for _, u in an.convites],
            "qr": an.qr,
        }
        alerta = await alertas_db.registrar(session, alerta, prefs.convocacoesCanalAlerta, prefs.convocacoesWebhookUrl, extra)
        det.alerta_id = alerta.id
        session.add(det)
        session.commit()
        session.refresh(det)
        try:  # assistente de IA: detecção acima do limiar entra na fila (triagem + extração do evento)
            from app.services.ia import pipeline

            pipeline.enfileirar_deteccao(session, det, prefs)
        except Exception:
            logger.exception("falha ao enfileirar detecção para a IA")
        session.refresh(det)  # o commit da fila expira a instância
    return ResultadoRegistro(deteccao=det, nova=True, ocorrencia=None, alerta=alerta, convites_registrados=registrados)


def criar_referencia(session: Session, det: Deteccao, an_embedding: bytes | None = None, rotulo: str = "") -> ReferenciaCartaz:
    ref = ReferenciaCartaz(
        deteccao_id=det.id, evidencia_id=det.evidencia_id, phash=det.phash, dhash=det.dhash,
        embedding=an_embedding, modelo_embedding="" if an_embedding is None else "clip", rotulo=rotulo or (det.local_evento or det.texto_ocr[:80]),
    )
    session.add(ref)
    det.estado = "confirmada"
    session.add(det)
    session.commit()
    session.refresh(ref)
    session.refresh(det)
    det.referencia_id = ref.id
    session.add(det)
    session.commit()
    return ref


__all__ = ["LIMIAR_PHASH_IGUAL", "ResultadoRegistro", "carregar_referencias", "criar_referencia", "monitores_compilados", "registrar_analise"]
