"""Convocações: analisar (print/URL), fila de detecções, ações (confirmar/descartar/boletim/agenda), referências, fontes, status."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models.agenda import AgendaEvento
from app.models.boletim import BoletimItem
from app.models.convocacao import Deteccao, DeteccaoOcorrencia, FonteConvocacao, ReferenciaCartaz
from app.models.evidence import Evidence
from app.schemas.agenda import AgendaEventoOut
from app.schemas.boletim import BoletimItemOut
from app.schemas.convocacao import (
    AgendaIn,
    AnaliseOut,
    BoletimIn,
    ConfirmarIn,
    DescartarIn,
    DeteccaoOut,
    DeteccaoPatch,
    FonteConvocacaoIn,
    FonteConvocacaoOut,
    FonteConvocacaoPatch,
    FonteTesteIn,
    FonteTesteOut,
    OcorrenciaOut,
    ReferenciaOut,
    StatusOut,
)
from app.models.monitor import Monitor
from app.schemas.monitor import MonitorOut
from app.services import evidence_store, radar, scheduler
from app.services.convocacoes import busca as busca_mod
from app.services.convocacoes import coleta
from app.services.convocacoes import imagem as img_mod
from app.services.convocacoes.analisador import Analise, Entrada, get_analisador
from app.services.convocacoes.persistencia import carregar_referencias, criar_referencia, monitores_compilados, registrar_analise
from app.services.convocacoes.resolver import plataforma_de, resolver
from app.services.scraper import get_scraper

router = APIRouter(prefix="/api/convocacoes", tags=["convocacoes"])


def _prefs():  # noqa: ANN202
    from app.routers.settings import carregar

    return carregar().preferencias


def _det(session: Session, det_id: int) -> Deteccao:
    d = session.get(Deteccao, det_id)
    if d is None:
        raise HTTPException(404, "Detecção não encontrada")
    return d


def _fonte(session: Session, fonte_id: int) -> FonteConvocacao:
    f = session.get(FonteConvocacao, fonte_id)
    if f is None:
        raise HTTPException(404, "Fonte não encontrada")
    return f


def _json(texto: str, padrao):  # noqa: ANN001, ANN202
    try:
        return json.loads(texto or "")
    except ValueError:
        return padrao


def deteccao_out(d: Deteccao) -> DeteccaoOut:
    base = d.model_dump()
    base.update(
        qr=_json(d.qr_json, []),
        convites=_json(d.convites_json, []),
        termos_lexico=_json(d.termos_lexico_json, {}),
        score_detalhe=_json(d.score_detalhe_json, {}),
    )
    return DeteccaoOut.model_validate(base)


def _resultado(an: Analise) -> dict[str, Any]:
    return {
        "score": an.score,
        "severidade": an.severidade,
        "decomposicao": an.decomposicao,
        "lexico": an.lexico.resumo(),
        "ocr": {"texto": an.ocr.texto, "linhas": an.ocr.linhas, "confianca": an.ocr.confianca, "variante": an.ocr.variante, "ms": an.ocr.ms, "modelo": an.ocr.modelo} if an.ocr else None,
        "qr": an.qr,
        "convites": [{"plataforma": p, "url": u} for p, u in an.convites],
        "visual": an.visual,
        "referencia": {"id": an.referencia[0], "score": an.referencia[1], "motivo": an.referencia[2]} if an.referencia else None,
        "monitores": [{"id": mid, "nome": nome, "termos": ts} for mid, nome, ts in an.termos_monitor],
        "imagem": {"largura": an.imagem.largura, "altura": an.imagem.altura, "sha256": an.imagem.sha256, "phash": an.imagem.phash, "mime": an.imagem.mime} if an.imagem else None,
        "ms": an.ms,
        "capacidades": an.capacidades,
    }


# ------------------------------------------------------------------ analisar
@router.post("/analisar", response_model=AnaliseOut, status_code=201)
async def analisar(
    arquivo: UploadFile | None = File(None),
    url: str | None = Form(None),
    texto: str = Form(""),
    plataforma: str | None = Form(None),
    salvar: bool = Form(True),
    respeitar_robots: bool = Form(True),
    session: Session = Depends(get_session),
) -> AnaliseOut:
    """Analisa um print (upload), uma URL (imagem direta, post do Bluesky, página com og:image) e/ou um texto."""
    entrada = Entrada(texto_post=(texto or "").strip())
    passos: list[str] = []
    if arquivo is not None:
        if not (arquivo.content_type or "").startswith("image/"):
            raise HTTPException(415, "Envie um arquivo de imagem")
        dados = await arquivo.read()
        if len(dados) > get_settings().max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"imagem excede {get_settings().max_upload_mb} MB")
        entrada.imagem = dados
        entrada.plataforma = plataforma or "desconhecida"
        if url:
            entrada.post_url = url.strip()
            entrada.plataforma = plataforma or plataforma_de(url)
    elif url:
        if not url.strip().startswith(("http://", "https://")):
            raise HTTPException(422, "URL deve começar com http:// ou https://")
        res = await resolver(get_scraper(), url, respeitar_robots=respeitar_robots)
        passos = res.passos
        entrada = res.entrada
        if entrada.texto_post and texto:
            entrada.texto_post = f"{texto.strip()}\n{entrada.texto_post}"
        elif texto:
            entrada.texto_post = texto.strip()
        if plataforma:
            entrada.plataforma = plataforma
        if res.erro and not entrada.imagem and not entrada.texto_post:
            raise HTTPException(422, res.erro)
    elif not entrada.texto_post:
        raise HTTPException(422, "Envie uma imagem, uma URL ou um texto")

    refs = carregar_referencias(session)
    mons = monitores_compilados(session)
    try:
        an = await get_analisador().analisar(entrada, refs, mons)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    resultado = _resultado(an)
    if passos:
        resultado["passos"] = passos

    if not salvar:
        return AnaliseOut(deteccao=None, nova=False, duplicada=False, salva=False, score=an.score, severidade=an.severidade, alerta_id=None, ocorrencia_id=None, resultado=resultado)
    origem = "manual" if arquivo is not None else ("url" if url else "texto")
    reg = await registrar_analise(session, entrada, an, _prefs(), origem=origem)
    return AnaliseOut(
        deteccao=deteccao_out(reg.deteccao),
        nova=reg.nova,
        duplicada=not reg.nova,
        salva=True,
        score=reg.deteccao.score if not reg.nova else an.score,
        severidade=reg.deteccao.severidade if not reg.nova else an.severidade,
        alerta_id=reg.alerta.id if reg.alerta else reg.deteccao.alerta_id,
        ocorrencia_id=reg.ocorrencia.id if reg.ocorrencia else None,
        resultado=resultado,
    )


# ------------------------------------------------------------------ fila
@router.get("", response_model=list[DeteccaoOut])
async def listar(
    estado: str | None = None,
    severidade: str | None = None,
    plataforma: str | None = None,
    desde: datetime | None = None,
    score_min: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[DeteccaoOut]:
    stmt = select(Deteccao)
    if estado:
        stmt = stmt.where(Deteccao.estado == estado)
    if severidade:
        stmt = stmt.where(Deteccao.severidade == severidade)
    if plataforma:
        stmt = stmt.where(Deteccao.plataforma == plataforma)
    if desde:
        stmt = stmt.where(Deteccao.criado_em >= desde)
    if score_min is not None:
        stmt = stmt.where(Deteccao.score >= score_min)
    rows = session.exec(stmt.order_by(col(Deteccao.score).desc(), col(Deteccao.criado_em).desc()).limit(limit)).all()
    return [deteccao_out(d) for d in rows]


@router.get("/status", response_model=StatusOut)
async def status(session: Session = Depends(get_session)) -> StatusOut:
    prefs = _prefs()
    job = scheduler.job_convocacoes()
    por_sev = {s: 0 for s in ("baixa", "media", "alta", "critica")}
    for sev, n in session.exec(select(Deteccao.severidade, func.count(Deteccao.id)).where(Deteccao.estado == "nova").group_by(Deteccao.severidade)).all():
        por_sev[sev] = int(n)
    return StatusOut(
        ativo=prefs.convocacoesAtivo,
        intervalo_min=prefs.convocacoesIntervaloMin,
        agendado=job is not None,
        proximo_ciclo=job.next_run_time if job is not None else None,
        ultimo_ciclo=coleta.ULTIMO_CICLO,
        fontes_ativas=session.exec(select(func.count(FonteConvocacao.id)).where(FonteConvocacao.ativa == True)).one(),  # noqa: E712
        fontes_total=session.exec(select(func.count(FonteConvocacao.id))).one(),
        deteccoes_total=session.exec(select(func.count(Deteccao.id))).one(),
        novas=sum(por_sev.values()),
        por_severidade=por_sev,
        referencias=session.exec(select(func.count(ReferenciaCartaz.id))).one(),
        capacidades=get_analisador().capacidades(),
    )


@router.get("/capacidades")
async def capacidades() -> dict[str, Any]:
    return get_analisador().capacidades()


@router.post("/descarregar")
async def descarregar() -> dict[str, Any]:
    liberados = get_analisador().descarregar(forcar=True)
    return {"liberados": liberados, **get_analisador().capacidades()}


@router.post("/ciclo")
async def rodar_ciclo(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Coleta todas as fontes ativas agora, analisa as imagens novas e alerta."""
    from app.services.searxng_client import get_searxng

    return await coleta.ciclo(session, get_scraper(), get_analisador(), get_searxng())


# ------------------------------------------------------------------ fontes (antes de /{id} para não colidir)
@router.get("/fontes", response_model=list[FonteConvocacaoOut])
async def listar_fontes(session: Session = Depends(get_session)) -> list[FonteConvocacao]:
    return list(session.exec(select(FonteConvocacao).order_by(col(FonteConvocacao.ativa).desc(), FonteConvocacao.tipo, FonteConvocacao.nome)).all())


@router.post("/fontes", response_model=FonteConvocacaoOut, status_code=201)
async def criar_fonte(dados: FonteConvocacaoIn, session: Session = Depends(get_session)) -> FonteConvocacao:
    coleta.validar_fonte(dados.tipo, dados.parametro)
    f = FonteConvocacao(**dados.model_dump())
    f.parametro = coleta.normalizar_parametro(f.tipo, f.parametro)
    session.add(f)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Fonte já cadastrada (mesmo tipo e parâmetro)") from exc
    session.refresh(f)
    return f


@router.post("/fontes/testar", response_model=FonteTesteOut)
async def testar_fonte(dados: FonteTesteIn) -> FonteTesteOut:
    """Coleta uma amostra sem gravar; mostra se robots.txt permite e quantos candidatos têm imagem."""
    from app.services.searxng_client import get_searxng

    coleta.validar_fonte(dados.tipo, dados.parametro)
    f = FonteConvocacao(nome="teste", tipo=dados.tipo, parametro=coleta.normalizar_parametro(dados.tipo, dados.parametro), respeitar_robots=dados.respeitar_robots)
    cands, status_http, erro, robots_ok = await coleta.coletar_fonte(get_scraper(), get_searxng(), f, limite=20)
    return FonteTesteOut(
        ok=erro is None,
        status=status_http,
        erro=erro,
        robots_permite=robots_ok,
        candidatos=len(cands),
        com_imagem=sum(1 for c in cands if c.imagens),
        amostra=[{"post_url": c.post_url, "autor": c.autor, "texto": c.texto[:200], "imagens": c.imagens[:3], "publicado_em": c.publicado_em.isoformat() if c.publicado_em else None} for c in cands[:10]],
    )


@router.get("/fontes/{fonte_id}", response_model=FonteConvocacaoOut)
async def obter_fonte(fonte_id: int, session: Session = Depends(get_session)) -> FonteConvocacao:
    return _fonte(session, fonte_id)


@router.patch("/fontes/{fonte_id}", response_model=FonteConvocacaoOut)
async def editar_fonte(fonte_id: int, dados: FonteConvocacaoPatch, session: Session = Depends(get_session)) -> FonteConvocacao:
    f = _fonte(session, fonte_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    if dados.parametro is not None:
        coleta.validar_fonte(f.tipo, f.parametro)
        f.parametro = coleta.normalizar_parametro(f.tipo, f.parametro)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f


@router.delete("/fontes/{fonte_id}", status_code=204)
async def remover_fonte(fonte_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_fonte(session, fonte_id))
    session.commit()


@router.post("/fontes/{fonte_id}/coletar")
async def coletar_fonte_agora(fonte_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    from app.services.searxng_client import get_searxng

    return await coleta.ciclo(session, get_scraper(), get_analisador(), get_searxng(), apenas_fonte=_fonte(session, fonte_id))


# ------------------------------------------------------------------ referências
@router.get("/referencias", response_model=list[ReferenciaOut])
async def listar_referencias(session: Session = Depends(get_session)) -> list[ReferenciaOut]:
    rows = session.exec(select(ReferenciaCartaz).order_by(col(ReferenciaCartaz.criado_em).desc())).all()
    return [ReferenciaOut.model_validate({**r.model_dump(exclude={"embedding"}), "tem_embedding": r.embedding is not None}) for r in rows]


@router.delete("/referencias/{ref_id}", status_code=204)
async def remover_referencia(ref_id: int, session: Session = Depends(get_session)) -> None:
    r = session.get(ReferenciaCartaz, ref_id)
    if r is None:
        raise HTTPException(404, "Referência não encontrada")
    for d in session.exec(select(Deteccao).where(Deteccao.referencia_id == ref_id)).all():
        d.referencia_id = None
        session.add(d)
    session.delete(r)
    session.commit()


# ------------------------------------------------------------------ detecção
@router.get("/{det_id}", response_model=DeteccaoOut)
async def obter(det_id: int, session: Session = Depends(get_session)) -> DeteccaoOut:
    return deteccao_out(_det(session, det_id))


@router.patch("/{det_id}", response_model=DeteccaoOut)
async def editar(det_id: int, dados: DeteccaoPatch, session: Session = Depends(get_session)) -> DeteccaoOut:
    d = _det(session, det_id)
    if dados.estado is not None:
        d.estado = dados.estado
    if dados.notas is not None:
        d.notas = dados.notas
    session.add(d)
    session.commit()
    session.refresh(d)
    return deteccao_out(d)


@router.delete("/{det_id}", status_code=204)
async def remover(det_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_det(session, det_id))
    session.commit()


@router.get("/{det_id}/ocorrencias", response_model=list[OcorrenciaOut])
async def ocorrencias(det_id: int, session: Session = Depends(get_session)) -> list[DeteccaoOcorrencia]:
    _det(session, det_id)
    return list(session.exec(select(DeteccaoOcorrencia).where(DeteccaoOcorrencia.deteccao_id == det_id).order_by(col(DeteccaoOcorrencia.visto_em).desc())).all())


@router.post("/{det_id}/confirmar", response_model=DeteccaoOut)
async def confirmar(det_id: int, dados: ConfirmarIn, session: Session = Depends(get_session)) -> DeteccaoOut:
    """Marca como convocação confirmada e cria a referência (galeria) usada na similaridade das próximas análises."""
    d = _det(session, det_id)
    if d.referencia_id and session.get(ReferenciaCartaz, d.referencia_id) is not None and d.estado == "confirmada":
        raise HTTPException(409, f"Detecção já confirmada (referência #{d.referencia_id})")
    emb: bytes | None = None
    if d.evidencia_id and get_analisador().capacidades()["clip_instalado"] and _prefs().convocacoesPerfilML == "completo":
        ev = session.get(Evidence, d.evidencia_id)
        if ev is not None:
            try:
                dados_img = evidence_store.caminho_absoluto(ev).read_bytes()
                an = await get_analisador().analisar(Entrada(imagem=dados_img, plataforma=d.plataforma))
                if an.embedding is not None:
                    emb = np.asarray(an.embedding, dtype=np.float32).tobytes()
            except (OSError, ValueError):
                emb = None
    criar_referencia(session, d, emb, dados.rotulo)
    session.refresh(d)
    return deteccao_out(d)


# ------------------------------------------------------------------ do cartaz para a busca (convites, menções, monitor)
class BuscaConvitesIn(BaseModel):
    termos: list[str] = Field(min_length=1, max_length=6)
    engines: list[Literal["duckduckgo", "bing", "startpage"]] = ["duckduckgo", "bing", "startpage"]
    max_consultas: int = Field(default=2, ge=1, le=4)


class BuscaMencoesIn(BaseModel):
    query: str = Field(min_length=2, max_length=600)
    engines: list[Literal["duckduckgo", "bing", "startpage"]] = ["duckduckgo", "bing", "startpage"]
    categorias: list[str] | None = None  # ex.: ["news"]; None = geral


class MonitorDeteccaoIn(BaseModel):
    query: str = Field(min_length=2, max_length=600)
    nome: str = Field(default="", max_length=120)


@router.get("/{det_id}/busca")
async def termos_busca(det_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Termos extraídos do cartaz (frases, locais, siglas, hashtags) + query de menções + deeplinks. Não gasta tokens."""
    d = _det(session, det_id)
    return busca_mod.extrair_termos(busca_mod.texto_da_deteccao(d), d).como_dict()


@router.post("/{det_id}/busca/ia")
async def termos_busca_ia(det_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Mesmo que GET /busca, enriquecido pelo agent `extrator` do OpenClaw (uma chamada)."""
    d = _det(session, det_id)
    texto = busca_mod.texto_da_deteccao(d)
    tb = await busca_mod.enriquecer_com_ia(busca_mod.extrair_termos(texto, d), texto)
    return tb.como_dict()


@router.post("/{det_id}/busca/convites")
async def busca_convites(det_id: int, dados: BuscaConvitesIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Procura links abertos de WhatsApp/Telegram ligados aos termos do cartaz (SearXNG) e registra em Convites."""
    from app.routers.invites import executar_scan

    d = _det(session, det_id)
    saidas = []
    novos = atualizados = 0
    for termo in dados.termos:
        termo = " ".join(termo.split())[:120]
        if len(termo) < 3:
            continue
        r = await executar_scan(session, termo, ["whatsapp", "telegram"], list(dados.engines), dados.max_consultas)
        novos += r.novos
        atualizados += r.atualizados
        saidas.append(r.model_dump(mode="json"))
    convites = {c["url"]: c for r in saidas for c in r["convites"]}
    if novos:
        d.notas = (d.notas + "\n" if d.notas else "") + f"busca de convites: {novos} novo(s) ({', '.join(dados.termos[:3])})"
        session.add(d)
        session.commit()
    return {"deteccao_id": det_id, "termos": dados.termos, "novos": novos, "atualizados": atualizados, "convites": list(convites.values()), "execucoes": [e for r in saidas for e in r["execucoes"]]}


@router.post("/{det_id}/busca/mencoes")
async def busca_mencoes(det_id: int, dados: BuscaMencoesIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Menções ao ato na web e nas redes indexadas (SearXNG local) + deeplinks para Google/X/etc."""
    from app.services.searxng_client import SearxngIndisponivel, get_searxng

    _det(session, det_id)
    try:
        res = await get_searxng().buscar(dados.query, tuple(dados.engines), categorias=dados.categorias)
    except SearxngIndisponivel as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"query": dados.query, "url": res.url, "erro": res.erro, "resultados": busca_mod.resultados_busca(res), "engines_sem_resposta": res.engines_sem_resposta, "deeplinks": busca_mod.montar_deeplinks(dados.query)}


@router.post("/{det_id}/monitor", response_model=MonitorOut, status_code=201)
async def criar_monitor_deteccao(det_id: int, dados: MonitorDeteccaoIn, session: Session = Depends(get_session)) -> MonitorOut:
    """Monitor contínuo com os termos do cartaz: o Radar casa as fontes e o assistente de IA tria (se ligado)."""
    d = _det(session, det_id)
    nome = (dados.nome or f"Convocação #{d.id}: {(d.local_evento or d.texto_ocr[:40] or 'cartaz').split('/')[0]}")[:120]
    mon = Monitor(nome=nome, query=dados.query, canal_alerta="nenhum", radar_modo="termos", tipo="query", ia=True)
    mon.proxima_execucao = scheduler.proxima_execucao(mon.cron)
    session.add(mon)
    session.commit()
    session.refresh(mon)
    scheduler.agendar(mon)
    radar.casar_monitor_cache(session, mon)
    d.notas = (d.notas + "\n" if d.notas else "") + f"monitor #{mon.id} criado: {dados.query[:120]}"
    session.add(d)
    session.commit()
    total, novos = radar.contagens_hits(session).get(mon.id or -1, (0, 0))
    return MonitorOut.model_validate(mon, from_attributes=True).model_copy(update={"hits_total": total, "hits_novos": novos})


@router.post("/{det_id}/descartar", response_model=DeteccaoOut)
async def descartar(det_id: int, dados: DescartarIn, session: Session = Depends(get_session)) -> DeteccaoOut:
    d = _det(session, det_id)
    d.estado = "descartada"
    if dados.motivo:
        d.notas = (d.notas + "\n" if d.notas else "") + f"descartada: {dados.motivo}"
    session.add(d)
    session.commit()
    session.refresh(d)
    return deteccao_out(d)


@router.post("/{det_id}/boletim", response_model=BoletimItemOut, status_code=201)
async def para_boletim(det_id: int, dados: BoletimIn, session: Session = Depends(get_session)) -> BoletimItem:
    d = _det(session, det_id)
    if d.boletim_item_id and session.get(BoletimItem, d.boletim_item_id) is not None:
        raise HTTPException(409, f"Detecção já está no boletim (item #{d.boletim_item_id})")
    titulo = " · ".join(p for p in (("ATO NÃO PACÍFICO" if d.nao_pacifico else "Convocação"), d.local_evento, d.data_evento.strftime("%d/%m") if d.data_evento else "") if p)
    item = BoletimItem(
        data=dados.data or d.data_evento or date.today(),
        secao=dados.secao,
        titulo=titulo[:300],
        url=d.post_url,
        fonte=f"Convocações/{d.plataforma}"[:120],
        resumo=(d.texto_ocr or d.texto_post)[:3000],
        evidence_id=d.evidencia_id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    d.boletim_item_id = item.id
    session.add(d)
    session.commit()
    return item


@router.post("/{det_id}/agenda", response_model=AgendaEventoOut, status_code=201)
async def para_agenda(det_id: int, dados: AgendaIn, session: Session = Depends(get_session)) -> AgendaEventoOut:
    """Cria o evento 'ato' na Agenda com data/local extraídos do cartaz."""
    from app.routers.agenda import evento_out

    d = _det(session, det_id)
    if d.agenda_evento_id and session.get(AgendaEvento, d.agenda_evento_id) is not None:
        raise HTTPException(409, f"Detecção já tem evento na agenda (#{d.agenda_evento_id})")
    cidade, uf = "", ""
    if d.local_evento and "/" in d.local_evento:
        cidade, uf = d.local_evento.rsplit("/", 1)
    ev = AgendaEvento(
        candidato=dados.candidato or "—",
        cargo="outro",
        titulo=(dados.titulo or ("Ato não pacífico" if d.nao_pacifico else "Ato/convocação") + (f" — {cidade}" if cidade else ""))[:200],
        tipo="ato",
        data=dados.data or d.data_evento or date.today(),
        hora_inicio=d.hora_evento,
        cidade=dados.cidade if dados.cidade is not None else cidade,
        uf=(dados.uf or uf).upper()[:2],
        descricao=(d.texto_ocr or d.texto_post)[:500],
        fonte_url=d.post_url or None,
        impacto_rodovia=any(t in (d.texto_ocr + d.texto_post).lower() for t in ("bloqueio", "rodovia", "br-", "br ", "trancaço", "trancaco")),
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    d.agenda_evento_id = ev.id
    session.add(d)
    session.commit()
    return evento_out(ev)


@router.get("/{det_id}/miniatura")
async def miniatura(det_id: int, session: Session = Depends(get_session)) -> Response:
    d = _det(session, det_id)
    if not d.evidencia_id:
        raise HTTPException(404, "Detecção sem imagem")
    ev = session.get(Evidence, d.evidencia_id)
    if ev is None:
        raise HTTPException(410, "Evidência removida")
    cache_dir = evidence_store.evidence_dir() / ".thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{ev.sha256}.jpg"
    if not cache.exists():
        p: Path = evidence_store.caminho_absoluto(ev)
        if not p.exists():
            raise HTTPException(410, "Arquivo ausente no disco")
        try:
            cache.write_bytes(img_mod.miniatura_jpeg(img_mod.abrir(p.read_bytes())))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return Response(cache.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
