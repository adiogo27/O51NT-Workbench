"""Pipeline do assistente: fila → sentinela (triagem) → extrator (evento) → pesquisador (verificação) → analista (cartão)
→ saídas (inbox, Telegram, aprovação para Boletim/Agenda).

Regras: só entram hits de monitores (casamento determinístico) e detecções acima do limiar; uma tarefa por URL;
cada etapa é idempotente (a saída JSON gravada não é refeita numa retentativa); nada é escrito em Boletim/Agenda sem
a política de autorização (auto | aprovar | nunca); teto diário de custo; o OpenClaw fora do ar só adia a fila.
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models._base import agora
from app.models.agenda import AgendaEvento
from app.models.alerta import Alerta
from app.models.boletim import BoletimItem
from app.models.ia import IaCusto, IaTarefa
from app.models.monitor import Monitor
from app.models.radar import MonitorHit
from app.models.settings import Preferencias
from app.services import alerts
from app.services.ia import prompts
from app.services.ia.cliente_openclaw import ClienteOpenClaw, OpenClawErro, OpenClawIndisponivel, RespostaInvalida, extrair_json, get_cliente
from app.services.ia.esquemas import ORDEM_SEVERIDADE, CartaoOut, EventoOut, PesquisaOut, TriagemOut

logger = logging.getLogger("o51nt.ia")
ULTIMO_CICLO: dict[str, Any] | None = None
MAX_TENTATIVAS = 3
CAMPO_JSON = {"triagem": "triagem_json", "extracao": "evento_json", "pesquisa": "pesquisa_json", "cartao": "cartao_json"}
# agent do OpenClaw por etapa: sentinela/extrator/redator são enxutos (sem ferramentas, sem raciocínio longo);
# o `analista` fica para a conversa no Telegram
AGENTS = {"triagem": "sentinela", "extracao": "extrator", "pesquisa": "pesquisador", "cartao": "redator"}
MODELO_PADRAO_REF = "anthropic/claude-sonnet-5-5"  # referência de custo quando a preferência iaModeloPadrao está vazia
_PARAMS_RASTREIO = re.compile(r"^(utm_|fbclid$|gclid$|igshid$|mc_cid$|mc_eid$|ref$|ref_src$)", re.I)
_TZ = ZoneInfo("America/Sao_Paulo")
TIPO_EVENTO = {"ato": "ato", "manifestacao": "ato", "manifestação": "ato", "protesto": "ato", "carreata": "carreata", "motociata": "motociata", "caminhada": "caminhada", "comicio": "comicio", "comício": "comicio", "bloqueio": "outro", "greve": "outro", "debate": "debate", "entrevista": "entrevista", "reuniao": "reuniao", "reunião": "reuniao"}


class ErroPipeline(Exception):
    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.detalhe = detalhe


# ------------------------------------------------------------------ utilidades
def _prefs() -> Preferencias:
    from app.routers.settings import carregar  # import tardio: evita ciclo routers ↔ services

    return carregar().preferencias


def hoje_local() -> date:
    return datetime.now(_TZ).date()


def normalizar_url(url: str) -> str:
    """Minúsculas no host, sem fragmento, sem parâmetros de rastreio, sem barra final — chave de dedupe entre monitores."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return u[:2000]
    p = urlsplit(u)
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _PARAMS_RASTREIO.match(k)])
    caminho = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), caminho, query, ""))[:2000]


def _json(obj: BaseModel | dict[str, Any] | None) -> str:
    if obj is None:
        return "{}"
    dados = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    return json.dumps(dados, ensure_ascii=False, default=str)


def _carregar(t: IaTarefa, campo: str) -> dict[str, Any]:
    try:
        d = json.loads(getattr(t, campo) or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def extrair_texto(html_texto: str, max_chars: int = 6000) -> str:
    """Texto principal da página: trafilatura quando instalado; senão BeautifulSoup sem navegação."""
    if not html_texto:
        return ""
    texto = ""
    try:
        import trafilatura  # type: ignore[import-not-found]

        texto = trafilatura.extract(html_texto, include_comments=False, include_tables=False, favor_precision=True) or ""
    except Exception:  # pacote ausente ou falha de parsing: cai no fallback
        texto = ""
    if len(texto) < 200:
        from bs4 import BeautifulSoup

        sopa = BeautifulSoup(html_texto, "lxml")
        for tag in sopa.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript", "form"]):
            tag.decompose()
        alvo = sopa.find("article") or sopa.find("main") or sopa.body or sopa
        texto = alvo.get_text(" ") if alvo else ""
    texto = " ".join(html_mod.unescape(texto).split())
    return texto[:max_chars]


# ------------------------------------------------------------------ fila
def _enfileirar(session: Session, *, origem: str, url: str, titulo: str, resumo: str, fonte_nome: str = "", termos: str = "", publicado_em: datetime | None = None, hit: MonitorHit | None = None, mon: Monitor | None = None, deteccao_id: int | None = None) -> IaTarefa | None:
    url = normalizar_url(url)
    if not url:
        return None
    atual = session.exec(select(IaTarefa).where(IaTarefa.origem == origem, IaTarefa.url == url)).first()
    if atual is not None:
        if mon is not None and mon.nome not in (atual.monitor_nome or ""):  # a mesma URL casou em outro monitor
            atual.monitor_nome = f"{atual.monitor_nome}; {mon.nome}".strip("; ")[:300]
            atual.termos = f"{atual.termos} | {termos}".strip(" |")[:300] if termos else atual.termos
            session.add(atual)
        return None
    t = IaTarefa(
        origem=origem,
        hit_id=hit.id if hit else None,
        deteccao_id=deteccao_id,
        monitor_id=mon.id if mon else None,
        monitor_nome=(mon.nome if mon else "")[:300],
        monitor_query=(mon.query if mon else "")[:500],
        url=url,
        titulo=(titulo or "")[:300],
        resumo=(resumo or "")[:1200],
        fonte_nome=(fonte_nome or "")[:120],
        termos=(termos or "")[:300],
        publicado_em=publicado_em,
    )
    session.add(t)
    return t


def enfileirar_hits(session: Session, por_monitor: dict[int, list[MonitorHit]], monitores: list[Monitor], prefs: Preferencias | None = None) -> int:
    """Chamado após `radar.casar_itens`: hits de monitores com `ia=True` viram tarefas (uma por URL)."""
    prefs = prefs or _prefs()
    if not prefs.iaAtivo:
        return 0
    mons = {m.id: m for m in monitores if m.id is not None}
    novas = 0
    for mid, hits in por_monitor.items():
        mon = mons.get(mid)
        if mon is None or not getattr(mon, "ia", True):
            continue
        for h in hits:
            if _enfileirar(session, origem="hit", url=h.url, titulo=h.titulo, resumo=h.resumo, fonte_nome=h.fonte_nome, termos=h.termos, publicado_em=h.publicado_em, hit=h, mon=mon) is not None:
                novas += 1
    session.commit()
    return novas


def enfileirar_deteccao(session: Session, det: Any, prefs: Preferencias | None = None) -> IaTarefa | None:
    """Detecções do módulo Convocações acima do limiar entram na fila (texto do OCR/post como conteúdo)."""
    prefs = prefs or _prefs()
    if not prefs.iaAtivo or det.id is None:
        return None
    texto = (det.texto_ocr or "").strip() or (det.texto_post or "").strip()
    url = det.post_url or det.imagem_url or f"deteccao:{det.id}"
    resumo = f"score {det.score} ({det.severidade}); local {det.local_evento or '?'}; data {det.data_evento or '?'}\n{texto}"
    t = _enfileirar(session, origem="deteccao", url=url, titulo=(texto[:200] or f"detecção #{det.id}"), resumo=resumo, fonte_nome=det.plataforma, termos=det.termos_monitor or "", publicado_em=det.publicado_em, deteccao_id=det.id)
    session.commit()
    return t


def enfileirar_manual(session: Session, url: str, titulo: str = "", resumo: str = "", por: str = "") -> IaTarefa:
    t = _enfileirar(session, origem="manual", url=url, titulo=titulo, resumo=resumo, fonte_nome=por[:120])
    if t is None:
        raise ErroPipeline(409, "URL já está na fila do assistente")
    session.commit()
    session.refresh(t)
    return t


# ------------------------------------------------------------------ custo
def custo_do_dia(session: Session, dia: date | None = None) -> IaCusto:
    dia = dia or hoje_local()
    c = session.exec(select(IaCusto).where(IaCusto.data == dia)).first()
    if c is None:
        c = IaCusto(data=dia)
        session.add(c)
        session.commit()
        session.refresh(c)
    return c


def teto_atingido(session: Session, prefs: Preferencias) -> bool:
    return bool(prefs.iaCustoDiarioUsd) and custo_do_dia(session).custo_usd >= prefs.iaCustoDiarioUsd


def _contabilizar(session: Session, t: IaTarefa, etapa: str, resp: Any, modelo_ref: str | None = None) -> None:
    if (not resp.modelo or resp.modelo.startswith("openclaw/")) and modelo_ref:
        # o gateway responde model="openclaw/<agent>"; estima o custo pelo modelo configurado para a etapa
        from app.services.ia.cliente_openclaw import estimar_custo

        resp.modelo = modelo_ref
        resp.custo_usd = estimar_custo(modelo_ref, resp.tokens_entrada, resp.tokens_saida)
    t.tokens_entrada += resp.tokens_entrada
    t.tokens_saida += resp.tokens_saida
    t.custo_usd = round(t.custo_usd + resp.custo_usd, 6)
    t.modelos = f"{t.modelos}; {etapa}={resp.modelo}".strip("; ")[:300]
    c = custo_do_dia(session)
    c.chamadas += 1
    c.tokens_entrada += resp.tokens_entrada
    c.tokens_saida += resp.tokens_saida
    c.custo_usd = round(c.custo_usd + resp.custo_usd, 6)
    session.add(c)
    session.add(t)
    session.commit()


# ------------------------------------------------------------------ execução
async def _contexto(session: Session, t: IaTarefa, scraper: Any, prefs: Preferencias) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "origem": t.origem,
        "monitor_nome": t.monitor_nome,
        "monitor_query": t.monitor_query,
        "termos": t.termos,
        "fonte_nome": t.fonte_nome,
        "publicado_em": t.publicado_em.isoformat() if t.publicado_em else None,
        "url": t.url,
        "titulo": t.titulo,
        "resumo": t.resumo,
        "texto": "",
    }
    if t.origem == "deteccao":
        ctx["texto"] = t.resumo
        linha = t.resumo.split("\n", 1)[0]
        m = re.match(r"score (\d+) \((\w+)\)", linha)
        if m:
            ctx["score"], ctx["severidade_detector"] = int(m.group(1)), m.group(2)
        return ctx
    if scraper is not None and t.url.startswith(("http://", "https://")) and prefs.iaTextoMaxChars:
        try:
            res = await scraper.buscar(t.url)
            if res.ok and res.html:
                ctx["texto"] = extrair_texto(res.html, prefs.iaTextoMaxChars)
        except Exception as exc:  # texto da matéria é opcional: segue só com título/resumo
            logger.info("texto da matéria indisponível", extra={"dados": {"tarefa": t.id, "erro": str(exc)[:200]}})
    if not ctx["texto"]:
        ctx["texto"] = t.resumo
    t.texto_chars = len(ctx["texto"])
    return ctx


async def _etapa(session: Session, t: IaTarefa, cliente: ClienteOpenClaw, etapa: str, agent: str, prompt: str, esquema: type[BaseModel], *, modelo: str | None, max_tokens: int, timeout: float | None = None, modelo_ref: str | None = None) -> BaseModel:
    campo = CAMPO_JSON[etapa]
    modelo_ref = modelo_ref or modelo
    atual = _carregar(t, campo)
    if atual:  # retentativa: etapa já concluída antes
        return esquema.model_validate(atual)
    t.etapa = etapa
    session.add(t)
    session.commit()
    erro: Exception | None = None
    for tentativa in (1, 2):
        try:
            resp = await cliente.perguntar(agent, prompt, modelo=modelo, max_tokens=max_tokens, timeout=timeout)
        except OpenClawErro as exc:
            if modelo and exc.status == 400 and "not allowed" in exc.detalhe:
                # o gateway só aceita troca de modelo dentro da lista do agent: segue com o modelo configurado nele
                logger.info("modelo por chamada recusado; usando o modelo do agent", extra={"dados": {"agent": agent, "modelo": modelo}})
                modelo = None
                resp = await cliente.perguntar(agent, prompt, modelo=None, max_tokens=max_tokens, timeout=timeout)
            else:
                raise
        _contabilizar(session, t, etapa, resp, modelo_ref)
        try:
            obj = esquema.model_validate(extrair_json(resp.texto))
            setattr(t, campo, _json(obj))
            session.add(t)
            session.commit()
            return obj
        except (RespostaInvalida, ValidationError) as exc:
            erro = exc
            prompt = prompt + "\n\nATENÇÃO: a resposta anterior não era um JSON válido no esquema pedido. Responda SOMENTE o objeto JSON."
            logger.warning("resposta fora do esquema", extra={"dados": {"tarefa": t.id, "etapa": etapa, "tentativa": tentativa, "erro": str(exc)[:300]}})
    raise RespostaInvalida(f"{agent}: {erro}")


def _pesquisar(prefs: Preferencias, severidade: str) -> bool:
    if prefs.iaPesquisarSeveridadeMin == "nunca":
        return False
    return ORDEM_SEVERIDADE.get(severidade, 0) >= ORDEM_SEVERIDADE.get(prefs.iaPesquisarSeveridadeMin, 2)


async def executar_tarefa(session: Session, t: IaTarefa, cliente: ClienteOpenClaw, scraper: Any, prefs: Preferencias) -> None:
    t.status = "em_processo"
    t.iniciado_em = agora()
    t.tentativas += 1
    session.add(t)
    session.commit()
    try:
        ctx = await _contexto(session, t, scraper, prefs)
        ref_padrao = prefs.iaModeloPadrao or MODELO_PADRAO_REF
        triagem = await _etapa(session, t, cliente, "triagem", AGENTS["triagem"], prompts.prompt_triagem(ctx), TriagemOut, modelo=prefs.iaModeloTriagem or None, max_tokens=900, modelo_ref=prefs.iaModeloTriagem or ref_padrao)
        assert isinstance(triagem, TriagemOut)
        t.veredito, t.severidade, t.justificativa, t.secao_sugerida, t.eh_evento = triagem.veredito, triagem.severidade, triagem.justificativa, triagem.secao, triagem.eh_evento
        evento: EventoOut | None = None
        pesquisa: PesquisaOut | None = None
        cartao: CartaoOut | None = None
        if triagem.veredito != "DESCARTAR":
            tri = triagem.model_dump(mode="json")
            if triagem.eh_evento:
                evento = await _etapa(session, t, cliente, "extracao", AGENTS["extracao"], prompts.prompt_extracao(ctx, tri), EventoOut, modelo=prefs.iaModeloPadrao or None, max_tokens=1200, modelo_ref=ref_padrao)  # type: ignore[assignment]
            ev_d = evento.model_dump(mode="json") if evento else None
            if triagem.veredito == "RELEVANTE" and _pesquisar(prefs, triagem.severidade):
                pesquisa = await _etapa(session, t, cliente, "pesquisa", AGENTS["pesquisa"], prompts.prompt_pesquisa(ctx, tri, ev_d), PesquisaOut, modelo=prefs.iaModeloPadrao or None, max_tokens=3000, timeout=max(cliente.timeout, 420.0), modelo_ref=ref_padrao)  # type: ignore[assignment]
            pq_d = pesquisa.model_dump(mode="json") if pesquisa else None
            cartao = await _etapa(session, t, cliente, "cartao", AGENTS["cartao"], prompts.prompt_cartao(ctx, tri, ev_d, pq_d), CartaoOut, modelo=prefs.iaModeloPadrao or None, max_tokens=1200, modelo_ref=ref_padrao)  # type: ignore[assignment]
        t.etapa = "saidas"
        await aplicar_saidas(session, t, triagem, evento, pesquisa, cartao, prefs)
        t.status, t.etapa, t.erro, t.concluido_em = "concluida", "fim", "", agora()
    except OpenClawIndisponivel:
        t.status = "pendente"
        t.tentativas = max(0, t.tentativas - 1)  # indisponibilidade do gateway não conta como falha da tarefa
        raise
    except (OpenClawErro, RespostaInvalida, ValidationError, ErroPipeline) as exc:
        t.erro = f"{t.etapa}: {exc}"[:500]
        t.status = "pendente" if t.tentativas < MAX_TENTATIVAS else "erro"
        logger.warning("tarefa de IA falhou", extra={"dados": {"tarefa": t.id, "etapa": t.etapa, "erro": t.erro, "tentativas": t.tentativas}})
    finally:
        session.add(t)
        session.commit()


async def processar_fila(session: Session, cliente: ClienteOpenClaw | None = None, scraper: Any = None, limite: int | None = None, prefs: Preferencias | None = None) -> dict[str, Any]:
    """Um ciclo do assistente: processa até `iaMaxItensCiclo` tarefas pendentes, respeitando o teto diário."""
    global ULTIMO_CICLO
    prefs = prefs or _prefs()
    cliente = cliente or get_cliente()
    if scraper is None:
        from app.services.scraper import get_scraper

        try:
            scraper = get_scraper()
        except Exception:
            scraper = None
    t0 = time.monotonic()
    resumo: dict[str, Any] = {"executado_em": agora().isoformat(), "processadas": 0, "concluidas": 0, "erros": 0, "custo_usd": 0.0, "motivo_parada": None}
    if not cliente.configurado:
        resumo["motivo_parada"] = "OPENCLAW_GATEWAY_TOKEN ausente no .env (rode deploy/vps/05_openclaw.sh)"
    else:
        # tarefas presas em em_processo (processo reiniciado no meio) voltam à fila
        limite_orfas = agora() - timedelta(minutes=20)
        for orfa in session.exec(select(IaTarefa).where(IaTarefa.status == "em_processo")).all():
            ini = orfa.iniciado_em.replace(tzinfo=UTC) if orfa.iniciado_em and orfa.iniciado_em.tzinfo is None else orfa.iniciado_em
            if ini is None or ini < limite_orfas:
                orfa.status = "pendente"
                session.add(orfa)
        session.commit()
        pendentes = session.exec(select(IaTarefa).where(IaTarefa.status == "pendente").order_by(col(IaTarefa.id)).limit(limite or prefs.iaMaxItensCiclo)).all()
        for t in pendentes:
            if teto_atingido(session, prefs):
                resumo["motivo_parada"] = f"teto diário de US$ {prefs.iaCustoDiarioUsd:.2f} atingido"
                break
            custo_antes = t.custo_usd
            try:
                await executar_tarefa(session, t, cliente, scraper, prefs)
            except OpenClawIndisponivel as exc:
                resumo["motivo_parada"] = f"OpenClaw indisponível: {exc}"
                break
            resumo["processadas"] += 1
            resumo["custo_usd"] = round(resumo["custo_usd"] + (t.custo_usd - custo_antes), 6)
            if t.status == "concluida":
                resumo["concluidas"] += 1
            elif t.status == "erro":
                resumo["erros"] += 1
    resumo["duracao_s"] = round(time.monotonic() - t0, 2)
    ULTIMO_CICLO = resumo
    logger.info("ciclo do assistente", extra={"dados": resumo})
    return resumo


# ------------------------------------------------------------------ saídas
def _esc(v: Any) -> str:
    return html_mod.escape(str(v), quote=False)


def formatar_cartao_telegram(t: IaTarefa, triagem: TriagemOut, cartao: CartaoOut | None, pesquisa: PesquisaOut | None) -> str:
    emoji = {"critica": "🚨", "alta": "🔴", "media": "🟠", "baixa": "🟡"}.get(triagem.severidade, "🤖")
    titulo = (cartao.titulo if cartao else t.titulo) or t.url
    linhas = [f"{emoji} <b>O51NT · IA</b> · {triagem.veredito} · {_esc(triagem.severidade)}", f"<b>{_esc(titulo)}</b>"]
    if cartao and cartao.resumo:
        linhas.append(_esc(cartao.resumo))
    elif triagem.justificativa:
        linhas.append(_esc(triagem.justificativa))
    if cartao and cartao.impacto_rodovia:
        linhas.append(f"🛣 {_esc(cartao.impacto_rodovia)}")
    if cartao and cartao.acao:
        linhas.append(f"➡️ {_esc(cartao.acao)}")
    if pesquisa and pesquisa.verificacao:
        linhas.append(f"🔎 verificação: {_esc(pesquisa.verificacao)} (confiança {pesquisa.confianca:.0%})")
    if t.monitor_nome:
        linhas.append(f"<i>monitor: {_esc(t.monitor_nome)} · casou: {_esc(t.termos or '—')}</i>")
    if t.url.startswith(("http://", "https://")):
        linhas.append(f'<a href="{html_mod.escape(t.url, quote=True)}">fonte original</a>')
    for u in (cartao.fontes if cartao else [])[:3]:
        if u != t.url:
            linhas.append(f'• <a href="{html_mod.escape(u, quote=True)}">{_esc(u[:90])}</a>')
    if t.aprovacao == "pendente":
        linhas.append(f"#{t.id} · para levar ao boletim/agenda responda: <code>aprovar {t.id}</code> · descartar: <code>rejeitar {t.id}</code>")
    else:
        linhas.append(f"#{t.id}")
    texto = "\n".join(linhas)
    return texto if len(texto) <= alerts.TELEGRAM_MAX else texto[: alerts.TELEGRAM_MAX - 1] + "…"


async def aplicar_saidas(session: Session, t: IaTarefa, triagem: TriagemOut, evento: EventoOut | None, pesquisa: PesquisaOut | None, cartao: CartaoOut | None, prefs: Preferencias) -> None:
    hit = session.get(MonitorHit, t.hit_id) if t.hit_id else None
    if triagem.veredito == "DESCARTAR":
        if prefs.iaMarcarLidos and hit is not None and not hit.lido:
            hit.lido = True
            session.add(hit)
        t.aprovacao = "nao_se_aplica"
        session.add(t)
        session.commit()
        return
    titulo = ((cartao.titulo if cartao else "") or t.titulo or t.url)[:280]
    partes = [triagem.justificativa]
    if cartao:
        partes += [cartao.resumo, f"Impacto: {cartao.impacto_rodovia}" if cartao.impacto_rodovia else "", f"Ação: {cartao.acao}" if cartao.acao else ""]
    severidade = triagem.severidade if triagem.veredito == "RELEVANTE" else ("baixa" if ORDEM_SEVERIDADE.get(triagem.severidade, 0) <= 1 else "media")
    if t.alerta_id is None:
        alerta = Alerta(tipo="ia", severidade=severidade, titulo=f"[{triagem.veredito}] {titulo}", resumo="\n".join(p for p in partes if p)[:1000], url=t.url if t.url.startswith(("http://", "https://")) else "", monitor_id=t.monitor_id, deteccao_id=t.deteccao_id)
        session.add(alerta)
        session.commit()
        session.refresh(alerta)
        t.alerta_id = alerta.id
    # política de escrita
    automaticos: list[str] = []
    pendentes: list[str] = []
    if triagem.veredito == "RELEVANTE":
        if prefs.iaBoletim == "auto":
            automaticos.append("boletim")
        elif prefs.iaBoletim == "aprovar":
            pendentes.append("boletim")
        if t.eh_evento and evento is not None and evento.data:
            if prefs.iaAgenda == "auto":
                automaticos.append("agenda")
            elif prefs.iaAgenda == "aprovar":
                pendentes.append("agenda")
    for destino in automaticos:
        try:
            aprovar(session, t, destino=destino, por="auto")
        except ErroPipeline as exc:
            logger.warning("escrita automática recusada", extra={"dados": {"tarefa": t.id, "destino": destino, "erro": exc.detalhe}})
    if pendentes:
        t.aprovacao = "pendente"
    elif automaticos and t.aprovacao != "aprovada":
        t.aprovacao = "nao_se_aplica"
    session.add(t)
    session.commit()
    evento_log = {"tipo": "ia", "veredito": triagem.veredito, "severidade": triagem.severidade, "titulo": titulo, "url": t.url, "tarefa_id": t.id, "monitor_id": t.monitor_id, "cartao": cartao.model_dump(mode="json") if cartao else None, "executado_em": agora().isoformat()}
    try:
        alerts.gravar_jsonl(evento_log)
    except Exception:
        logger.exception("falha ao gravar JSONL do assistente")
    if triagem.veredito == "RELEVANTE" and prefs.iaTelegramRelevante and alerts.telegram_configurado() and not t.telegram_enviado:
        try:
            r = await alerts.enviar_telegram(formatar_cartao_telegram(t, triagem, cartao, pesquisa))
            t.telegram_enviado = bool(r.get("ok"))
            if not r.get("ok"):
                logger.warning("telegram recusou o cartão", extra={"dados": {"tarefa": t.id, "erro": r.get("erro")}})
        except Exception:
            logger.exception("falha ao enviar cartão ao Telegram")
        session.add(t)
        session.commit()


async def enviar_resumo(session: Session, prefs: Preferencias | None = None, forcar: bool = False) -> dict[str, Any]:
    """Resumo periódico: itens OBSERVAR ainda não resumidos (+ contagem de aprovações pendentes)."""
    prefs = prefs or _prefs()
    itens = session.exec(select(IaTarefa).where(IaTarefa.status == "concluida", IaTarefa.veredito == "OBSERVAR", IaTarefa.resumo_enviado == False).order_by(col(IaTarefa.id)).limit(25)).all()  # noqa: E712
    pendentes = session.exec(select(func.count(IaTarefa.id)).where(IaTarefa.aprovacao == "pendente")).one()
    if not itens and not (forcar and pendentes):
        return {"enviados": 0, "pendentes": int(pendentes)}
    if not alerts.telegram_configurado():
        return {"enviados": 0, "pendentes": int(pendentes), "erro": alerts.TELEGRAM_NAO_CONFIGURADO}
    linhas = [f"🗂 <b>O51NT · IA</b> · resumo: {len(itens)} item(ns) para observar"]
    for t in itens:
        cartao = _carregar(t, "cartao_json")
        tit = (cartao.get("titulo") or t.titulo or t.url)[:100]
        link = f'<a href="{html_mod.escape(t.url, quote=True)}">{_esc(tit)}</a>' if t.url.startswith(("http://", "https://")) else _esc(tit)
        linhas.append(f"• {link} — {_esc((t.justificativa or '')[:120])} <i>[{_esc(t.monitor_nome or t.origem)}]</i>")
    if pendentes:
        linhas.append(f"⏳ {int(pendentes)} item(ns) aguardando aprovação (responda <code>aprovar N</code> ou use o painel).")
    texto = "\n".join(linhas)
    if len(texto) > alerts.TELEGRAM_MAX:
        texto = texto[: alerts.TELEGRAM_MAX - 1] + "…"
    r = await alerts.enviar_telegram(texto)
    if r.get("ok"):
        for t in itens:
            t.resumo_enviado = True
            session.add(t)
        session.commit()
    return {"enviados": len(itens) if r.get("ok") else 0, "pendentes": int(pendentes), "erro": None if r.get("ok") else r.get("erro")}


# ------------------------------------------------------------------ aprovação / escrita
def _secao_valida(s: str | None) -> str:
    return s if s in ("noticia", "fake_news", "manifestacao", "imagem_institucional", "outro") else "noticia"


def _criar_boletim(session: Session, t: IaTarefa, ajustes: dict[str, Any]) -> BoletimItem:
    from app.schemas.boletim import BoletimItemIn

    cartao = _carregar(t, "cartao_json")
    pesquisa = _carregar(t, "pesquisa_json")
    fontes = [u for u in (cartao.get("fontes") or []) if isinstance(u, str)]
    partes = [cartao.get("resumo") or t.justificativa or t.resumo]
    if cartao.get("impacto_rodovia"):
        partes.append(f"Impacto em rodovia federal: {cartao['impacto_rodovia']}")
    if cartao.get("acao"):
        partes.append(f"Ação sugerida: {cartao['acao']}")
    if pesquisa.get("verificacao"):
        partes.append(f"Verificação: {pesquisa['verificacao']} (confiança {float(pesquisa.get('confianca') or 0):.0%})")
    if fontes:
        partes.append("Fontes: " + " ; ".join(fontes[:6]))
    data_item = ajustes.get("data")
    if isinstance(data_item, str):
        data_item = date.fromisoformat(data_item)
    if data_item is None:
        data_item = t.publicado_em.astimezone(_TZ).date() if t.publicado_em and t.publicado_em.tzinfo else (t.publicado_em.date() if t.publicado_em else hoje_local())
    try:
        dados = BoletimItemIn(
            data=data_item,
            secao=_secao_valida(ajustes.get("secao") or t.secao_sugerida),
            titulo=((cartao.get("titulo") or t.titulo or t.url)[:300]),
            url=t.url if t.url.startswith(("http://", "https://")) else "",
            fonte=(t.fonte_nome or t.monitor_nome)[:120],
            resumo="\n".join(p for p in partes if p)[:3000],
        )
    except ValidationError as exc:
        raise ErroPipeline(422, f"item de boletim inválido: {exc.errors()[0].get('msg', exc)}") from exc
    item = BoletimItem(**dados.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _criar_agenda(session: Session, t: IaTarefa, ajustes: dict[str, Any]) -> AgendaEvento:
    from app.schemas.agenda import UFS, AgendaEventoIn
    from app.services.agenda import normalizar_rodovia

    ev = _carregar(t, "evento_json")
    cartao = _carregar(t, "cartao_json")
    data_ev = ajustes.get("data") or ev.get("data")
    if not data_ev:
        raise ErroPipeline(422, "o evento extraído não tem data; informe 'data' (AAAA-MM-DD) na aprovação")
    rodovias = [r for r in (normalizar_rodovia(x) for x in (ev.get("rodovias") or [])) if r]
    uf = str(ev.get("uf") or "").strip().upper()
    hora = ev.get("hora") if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(ev.get("hora") or "")) else None
    descricao = "; ".join(p for p in (ev.get("pauta"), ev.get("rota") and f"rota: {ev['rota']}", ev.get("notas") and f"notas: {ev['notas']}", cartao.get("resumo")) if p)
    try:
        dados = AgendaEventoIn(
            candidato=(ajustes.get("candidato") or ev.get("organizador") or "—")[:120],
            cargo="outro",
            titulo=(ajustes.get("titulo") or ev.get("titulo") or cartao.get("titulo") or t.titulo or "Evento")[:200],
            tipo=TIPO_EVENTO.get(str(ev.get("tipo") or "").lower(), "outro"),  # type: ignore[arg-type]
            data=date.fromisoformat(str(data_ev)),
            hora_inicio=hora,
            cidade=(ev.get("cidade") or "")[:120],
            uf=uf if uf in UFS else "",
            local=(ev.get("local") or "")[:200],
            rodovias=rodovias,
            impacto_rodovia=bool(ev.get("impacto_rodovia_federal")) or bool(rodovias),
            descricao=descricao[:2000],
            fonte_url=t.url if t.url.startswith(("http://", "https://")) else None,
            status="previsto",
        )
    except (ValidationError, ValueError) as exc:
        raise ErroPipeline(422, f"evento inválido para a Agenda: {str(exc)[:200]}") from exc
    campos = dados.model_dump()
    campos["rodovias"] = ",".join(dados.rodovias)
    evento = AgendaEvento(**campos)
    session.add(evento)
    session.commit()
    session.refresh(evento)
    return evento


def aprovar(session: Session, t: IaTarefa, destino: str = "ambos", por: str = "painel", ajustes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Escreve no Boletim e/ou na Agenda (idempotente) e marca a tarefa como aprovada."""
    ajustes = ajustes or {}
    if t.veredito not in ("RELEVANTE", "OBSERVAR"):
        raise ErroPipeline(409, "só tarefas RELEVANTE ou OBSERVAR vão para boletim/agenda")
    if destino not in ("boletim", "agenda", "ambos"):
        raise ErroPipeline(422, "destino deve ser boletim, agenda ou ambos")
    feitos: dict[str, Any] = {}
    if destino in ("boletim", "ambos") and not t.boletim_item_id:
        item = _criar_boletim(session, t, ajustes)
        t.boletim_item_id = item.id
        feitos["boletim_item_id"] = item.id
        if t.hit_id:
            hit = session.get(MonitorHit, t.hit_id)
            if hit is not None:
                hit.boletim_item_id, hit.lido = item.id, True
                session.add(hit)
    if destino in ("agenda", "ambos") and not t.agenda_evento_id:
        tem_evento = bool(_carregar(t, "evento_json")) or bool(ajustes.get("data"))
        if tem_evento:
            evento = _criar_agenda(session, t, ajustes)
            t.agenda_evento_id = evento.id
            feitos["agenda_evento_id"] = evento.id
        elif destino == "agenda":
            raise ErroPipeline(422, "a tarefa não tem evento extraído; informe 'data' e 'titulo' na aprovação")
    t.aprovacao, t.aprovado_por, t.aprovado_em = "aprovada", por[:120], agora()
    if t.alerta_id:
        alerta = session.get(Alerta, t.alerta_id)
        if alerta is not None:
            alerta.lido = True
            session.add(alerta)
    session.add(t)
    session.commit()
    session.refresh(t)
    return {"tarefa_id": t.id, "aprovacao": t.aprovacao, **feitos, "boletim_item_id": t.boletim_item_id, "agenda_evento_id": t.agenda_evento_id}


def rejeitar(session: Session, t: IaTarefa, por: str = "painel", motivo: str = "") -> IaTarefa:
    t.aprovacao, t.aprovado_por, t.aprovado_em = "rejeitada", por[:120], agora()
    if motivo:
        t.justificativa = f"{t.justificativa} | rejeitado: {motivo}"[:600]
    if t.alerta_id:
        alerta = session.get(Alerta, t.alerta_id)
        if alerta is not None:
            alerta.lido = True
            session.add(alerta)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def reprocessar(session: Session, t: IaTarefa, desde: str = "triagem") -> IaTarefa:
    ordem = ["triagem", "extracao", "pesquisa", "cartao"]
    if desde not in ordem:
        raise ErroPipeline(422, f"desde deve ser um de {', '.join(ordem)}")
    for etapa in ordem[ordem.index(desde) :]:
        setattr(t, CAMPO_JSON[etapa], "{}")
    if desde == "triagem":
        t.veredito = t.severidade = t.secao_sugerida = None
        t.justificativa, t.eh_evento = "", False
    t.status, t.etapa, t.erro, t.tentativas, t.concluido_em = "pendente", "", "", 0, None
    if t.aprovacao != "aprovada":
        t.aprovacao = "nao_se_aplica"
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


async def pesquisar_sob_pedido(session: Session, t: IaTarefa, cliente: ClienteOpenClaw | None = None, prefs: Preferencias | None = None) -> dict[str, Any]:
    """Roda o pesquisador (e refaz o cartão) para uma tarefa já triada, a pedido do analista."""
    prefs = prefs or _prefs()
    cliente = cliente or get_cliente()
    tri = _carregar(t, "triagem_json")
    if not tri:
        raise ErroPipeline(409, "tarefa ainda não foi triada")
    if teto_atingido(session, prefs):
        raise ErroPipeline(429, "teto diário de custo atingido")
    ctx = await _contexto(session, t, None, prefs)
    ev = _carregar(t, "evento_json") or None
    t.pesquisa_json = "{}"
    t.cartao_json = "{}"
    ref_padrao = prefs.iaModeloPadrao or MODELO_PADRAO_REF
    pesquisa = await _etapa(session, t, cliente, "pesquisa", AGENTS["pesquisa"], prompts.prompt_pesquisa(ctx, tri, ev), PesquisaOut, modelo=prefs.iaModeloPadrao or None, max_tokens=3000, timeout=max(cliente.timeout, 420.0), modelo_ref=ref_padrao)
    cartao = await _etapa(session, t, cliente, "cartao", AGENTS["cartao"], prompts.prompt_cartao(ctx, tri, ev, pesquisa.model_dump(mode="json")), CartaoOut, modelo=prefs.iaModeloPadrao or None, max_tokens=1200, modelo_ref=ref_padrao)
    if t.alerta_id:
        alerta = session.get(Alerta, t.alerta_id)
        if alerta is not None and isinstance(cartao, CartaoOut):
            alerta.resumo = "\n".join(p for p in (t.justificativa, cartao.resumo, cartao.impacto_rodovia and f"Impacto: {cartao.impacto_rodovia}", cartao.acao and f"Ação: {cartao.acao}") if p)[:1000]
            session.add(alerta)
    t.status, t.etapa = "concluida", "fim"
    session.add(t)
    session.commit()
    return {"pesquisa": pesquisa.model_dump(mode="json"), "cartao": cartao.model_dump(mode="json")}


# ------------------------------------------------------------------ status
def status(session: Session, prefs: Preferencias | None = None) -> dict[str, Any]:
    prefs = prefs or _prefs()
    por_status = {s: int(n) for s, n in session.exec(select(IaTarefa.status, func.count(IaTarefa.id)).group_by(IaTarefa.status)).all()}
    por_veredito = {str(v): int(n) for v, n in session.exec(select(IaTarefa.veredito, func.count(IaTarefa.id)).where(IaTarefa.veredito != None).group_by(IaTarefa.veredito)).all()}  # noqa: E711
    pendentes = int(session.exec(select(func.count(IaTarefa.id)).where(IaTarefa.aprovacao == "pendente")).one())
    nao_lidos = int(session.exec(select(func.count(Alerta.id)).where(Alerta.tipo == "ia", Alerta.lido == False)).one())  # noqa: E712
    c = custo_do_dia(session)
    cliente = get_cliente()
    return {
        "ativo": prefs.iaAtivo,
        "intervalo_min": prefs.iaIntervaloMin,
        "openclaw_configurado": cliente.configurado,
        "openclaw_url": cliente.base_url,
        "fila": {"pendente": por_status.get("pendente", 0), "em_processo": por_status.get("em_processo", 0), "concluida": por_status.get("concluida", 0), "erro": por_status.get("erro", 0)},
        "vereditos": por_veredito,
        "aprovacoes_pendentes": pendentes,
        "alertas_ia_nao_lidos": nao_lidos,
        "custo_hoje": {"data": c.data.isoformat(), "chamadas": c.chamadas, "tokens_entrada": c.tokens_entrada, "tokens_saida": c.tokens_saida, "custo_usd": round(c.custo_usd, 4), "teto_usd": prefs.iaCustoDiarioUsd, "bloqueado": teto_atingido(session, prefs)},
        "politica": {"boletim": prefs.iaBoletim, "agenda": prefs.iaAgenda, "pesquisar_min": prefs.iaPesquisarSeveridadeMin, "telegram_relevante": prefs.iaTelegramRelevante, "resumo_horas": prefs.iaResumoHoras},
        "ultimo_ciclo": ULTIMO_CICLO,
    }


def custo_por_dia(session: Session, dias: int = 7) -> list[dict[str, Any]]:
    desde = hoje_local() - timedelta(days=max(1, dias) - 1)
    rows = session.exec(select(IaCusto).where(IaCusto.data >= desde).order_by(col(IaCusto.data).desc())).all()
    return [{"data": r.data.isoformat(), "chamadas": r.chamadas, "tokens_entrada": r.tokens_entrada, "tokens_saida": r.tokens_saida, "custo_usd": round(r.custo_usd, 4)} for r in rows]
