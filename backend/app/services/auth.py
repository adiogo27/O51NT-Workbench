"""Login por e-mail + código de uso único, sessões por cookie e gestão de usuários (só admin).

Fluxo: `solicitar_codigo(email)` → código de 6 dígitos (10 min, 5 tentativas) entregue por e-mail (SMTP); sem SMTP,
Telegram do usuário; sem nenhum dos dois, o código vai para o journal do serviço (operador da VM). `verificar_codigo`
abre uma sessão (token aleatório, guardado como HMAC) com validade absoluta e por inatividade.

Proteções: respostas genéricas (não revelam se o e-mail existe), limite de pedidos por e-mail, bloqueio temporário por
e-mail e por IP após falhas, comparação em tempo constante, códigos anteriores invalidados a cada novo pedido,
trilha de auditoria em `eventoacesso`.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from app.config import get_settings
from app.models.auth import CodigoAcesso, EventoAcesso, Sessao, Usuario

logger = logging.getLogger("o51nt.auth")
PAPEIS = ("admin", "analista")
MENSAGEM_GENERICA = "Se o e-mail estiver autorizado, um código de acesso foi enviado."
_pepper_cache: bytes | None = None


class AuthErro(Exception):
    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.detalhe = detalhe


# ------------------------------------------------------------------ utilidades
def agora() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def normalizar_email(email: str) -> str:
    e = (email or "").strip().lower()
    if len(e) > 254 or "@" not in e or e.startswith("@") or e.endswith("@") or " " in e:
        raise AuthErro(422, "e-mail inválido")
    return e


def _pepper() -> bytes:
    """Chave dos HMACs: O51NT_AUTH_SECRET ou arquivo data/auth_secret (criado uma vez, modo 600)."""
    global _pepper_cache
    if _pepper_cache is not None:
        return _pepper_cache
    s = get_settings()
    if s.auth_secret:
        _pepper_cache = s.auth_secret.encode()
        return _pepper_cache
    p: Path = s.data_dir / "auth_secret"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        p.chmod(0o600)
    _pepper_cache = p.read_text(encoding="utf-8").strip().encode()
    return _pepper_cache


def reset_cache() -> None:
    global _pepper_cache
    _pepper_cache = None


def hash_segredo(valor: str) -> str:
    return hmac.new(_pepper(), valor.encode(), sha256).hexdigest()


def gerar_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def registrar(session: Session, evento: str, *, email: str = "", ip: str = "", ok: bool = True, detalhe: str = "") -> None:
    session.add(EventoAcesso(evento=evento, email=email, ip=ip, ok=ok, detalhe=detalhe[:500]))
    session.commit()


def _falhas_recentes(session: Session, *, email: str | None = None, ip: str | None = None) -> int:
    s = get_settings()
    desde = agora() - timedelta(minutes=s.auth_bloqueio_minutos)
    q = select(func.count()).select_from(EventoAcesso).where(EventoAcesso.evento == "login_falha", EventoAcesso.em >= desde)
    if email is not None:
        q = q.where(EventoAcesso.email == email)
    if ip is not None:
        q = q.where(EventoAcesso.ip == ip)
    return int(session.exec(q).one())


def bloqueado(session: Session, email: str, ip: str) -> bool:
    s = get_settings()
    return _falhas_recentes(session, email=email) >= s.auth_falhas_bloqueio or _falhas_recentes(session, ip=ip) >= s.auth_falhas_bloqueio * 4


# ------------------------------------------------------------------ usuários
def garantir_admin(session: Session) -> Usuario | None:
    """Cria (ou reativa/promove) o administrador inicial definido em O51NT_ADMIN_EMAIL."""
    s = get_settings()
    if not s.admin_email:
        return None
    email = normalizar_email(s.admin_email)
    u = session.exec(select(Usuario).where(Usuario.email == email)).first()
    if u is None:
        u = Usuario(email=email, nome="Administrador", papel="admin", ativo=True, criado_por="sistema", telegram_chat_id=s.telegram_chat_id)
        session.add(u)
        session.commit()
        session.refresh(u)
        registrar(session, "usuario_criado", email=email, detalhe="admin inicial (O51NT_ADMIN_EMAIL)")
    elif u.papel != "admin" or not u.ativo:
        u.papel, u.ativo = "admin", True
        session.add(u)
        session.commit()
    return u


def obter_usuario(session: Session, email: str) -> Usuario | None:
    return session.exec(select(Usuario).where(Usuario.email == email)).first()


def criar_usuario(session: Session, *, email: str, nome: str, papel: str, telegram_chat_id: str | None, por: str) -> Usuario:
    email = normalizar_email(email)
    if papel not in PAPEIS:
        raise AuthErro(422, f"papel deve ser um de {', '.join(PAPEIS)}")
    if obter_usuario(session, email):
        raise AuthErro(409, "e-mail já cadastrado")
    u = Usuario(email=email, nome=nome.strip()[:120], papel=papel, telegram_chat_id=(telegram_chat_id or "").strip() or None, criado_por=por)
    session.add(u)
    session.commit()
    session.refresh(u)
    registrar(session, "usuario_criado", email=email, detalhe=f"por {por}; papel={papel}")
    return u


def _ultimo_admin(session: Session, usuario: Usuario) -> bool:
    ativos = session.exec(select(func.count()).select_from(Usuario).where(Usuario.papel == "admin", Usuario.ativo == True)).one()  # noqa: E712
    return usuario.papel == "admin" and usuario.ativo and int(ativos) <= 1


def alterar_usuario(session: Session, usuario: Usuario, *, por: Usuario, **campos: object) -> Usuario:
    novo_papel = campos.get("papel")
    novo_ativo = campos.get("ativo")
    rebaixa = (novo_papel is not None and novo_papel != "admin") or (novo_ativo is False)
    if rebaixa and _ultimo_admin(session, usuario):
        raise AuthErro(409, "não é possível rebaixar ou desativar o último administrador")
    if usuario.id == por.id and rebaixa:
        raise AuthErro(409, "você não pode rebaixar ou desativar a própria conta")
    if novo_papel is not None and novo_papel not in PAPEIS:
        raise AuthErro(422, f"papel deve ser um de {', '.join(PAPEIS)}")
    for k, v in campos.items():
        if v is None:
            continue
        if k == "nome":
            v = str(v).strip()[:120]
        if k == "telegram_chat_id":
            v = str(v).strip() or None
        setattr(usuario, k, v)
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    if novo_ativo is False:
        revogar_todas(session, usuario.id)  # type: ignore[arg-type]
    registrar(session, "usuario_alterado", email=usuario.email, detalhe=f"por {por.email}; {campos}")
    return usuario


def remover_usuario(session: Session, usuario: Usuario, *, por: Usuario) -> None:
    if usuario.id == por.id:
        raise AuthErro(409, "você não pode remover a própria conta")
    if _ultimo_admin(session, usuario):
        raise AuthErro(409, "não é possível remover o último administrador")
    revogar_todas(session, usuario.id)  # type: ignore[arg-type]
    for c in session.exec(select(CodigoAcesso).where(CodigoAcesso.usuario_id == usuario.id)).all():
        session.delete(c)
    for ss in session.exec(select(Sessao).where(Sessao.usuario_id == usuario.id)).all():
        session.delete(ss)
    email = usuario.email
    session.delete(usuario)
    session.commit()
    registrar(session, "usuario_removido", email=email, detalhe=f"por {por.email}")


# ------------------------------------------------------------------ entrega do código
@dataclass
class Entrega:
    canal: str  # email | telegram | journal | nenhum
    ok: bool
    erro: str = ""


def canal_de_entrega(usuario: Usuario | None = None) -> str:
    s = get_settings()
    if s.smtp_configurado:
        return "email"
    if usuario is not None and usuario.telegram_chat_id and s.telegram_bot_token:
        return "telegram"
    return "journal"


def enviar_email(destino: str, assunto: str, corpo: str) -> None:
    """SMTP (STARTTLS por padrão; SMTPS com SMTP_SSL=true). Lança exceção em falha."""
    s = get_settings()
    if not s.smtp_host:
        raise RuntimeError("SMTP não configurado")
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user or ""
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(corpo)
    ctx = ssl.create_default_context()
    if s.smtp_ssl:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=ctx) as smtp:
            if s.smtp_user and s.smtp_password:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ctx)
        smtp.ehlo()
        if s.smtp_user and s.smtp_password:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def _texto_codigo(codigo: str, ip: str) -> str:
    s = get_settings()
    return (
        f"Seu código de acesso ao O51NT Workbench: {codigo}\n\n"
        f"Válido por {s.auth_codigo_minutos} minutos, uso único. Pedido feito a partir do IP {ip or 'desconhecido'}.\n"
        "Se não foi você, ignore esta mensagem — ninguém entra sem este código.\n"
        f"Painel: {s.app_url}\n"
    )


async def entregar_codigo(usuario: Usuario, codigo: str, ip: str) -> Entrega:
    import asyncio

    canal = canal_de_entrega(usuario)
    texto = _texto_codigo(codigo, ip)
    if canal == "email":
        try:
            await asyncio.to_thread(enviar_email, usuario.email, "O51NT — código de acesso", texto)
            return Entrega("email", True)
        except Exception as exc:  # falha de SMTP não derruba o fluxo; fica registrada
            logger.error("falha ao enviar e-mail de código", extra={"dados": {"email": usuario.email, "erro": str(exc)}})
            return Entrega("email", False, str(exc))
    if canal == "telegram":
        from app.services import alerts

        try:
            r = await alerts.enviar_telegram("🔐 <b>O51NT</b>\n" + alerts._esc(texto), usuario.telegram_chat_id)
            return Entrega("telegram", bool(r.get("ok")), str(r.get("erro") or ""))
        except Exception as exc:
            return Entrega("telegram", False, str(exc))
    # journal: só quem opera a VM lê (journalctl -u o51nt). Nunca vai para a resposta HTTP.
    logger.warning("CODIGO DE ACESSO (SMTP ausente) para %s: %s", usuario.email, codigo)
    return Entrega("journal", True)


# ------------------------------------------------------------------ códigos
def _invalidar_codigos(session: Session, usuario_id: int) -> None:
    for c in session.exec(select(CodigoAcesso).where(CodigoAcesso.usuario_id == usuario_id, CodigoAcesso.usado_em == None, CodigoAcesso.invalidado == False)).all():  # noqa: E711,E712
        c.invalidado = True
        session.add(c)
    session.commit()


async def solicitar_codigo(session: Session, email_bruto: str, ip: str) -> dict:
    """Sempre responde a mesma coisa para e-mails desconhecidos/inativos/limitados (sem enumeração)."""
    s = get_settings()
    email = normalizar_email(email_bruto)
    generico = {"ok": True, "mensagem": MENSAGEM_GENERICA, "canal": canal_de_entrega(None), "validade_min": s.auth_codigo_minutos}
    u = obter_usuario(session, email)
    if u is None or not u.ativo:
        registrar(session, "codigo_recusado", email=email, ip=ip, ok=False, detalhe="e-mail não autorizado" if u is None else "usuário inativo")
        return generico
    if bloqueado(session, email, ip):
        registrar(session, "bloqueado", email=email, ip=ip, ok=False, detalhe="pedido de código durante bloqueio")
        return generico
    desde = agora() - timedelta(minutes=15)
    pedidos = int(session.exec(select(func.count()).select_from(CodigoAcesso).where(CodigoAcesso.usuario_id == u.id, CodigoAcesso.criado_em >= desde)).one())
    if pedidos >= s.auth_pedidos_por_15min:
        registrar(session, "codigo_limite", email=email, ip=ip, ok=False, detalhe=f"{pedidos} pedidos em 15 min")
        return generico
    _invalidar_codigos(session, u.id)  # type: ignore[arg-type]
    codigo = gerar_codigo()
    entrega = await entregar_codigo(u, codigo, ip)
    session.add(CodigoAcesso(usuario_id=u.id, codigo_hash=hash_segredo(codigo), expira_em=agora() + timedelta(minutes=s.auth_codigo_minutos), ip=ip, canal=entrega.canal))  # type: ignore[arg-type]
    session.commit()
    registrar(session, "codigo_solicitado", email=email, ip=ip, ok=entrega.ok, detalhe=f"canal={entrega.canal} {entrega.erro}".strip())
    return {**generico, "canal": entrega.canal}


def verificar_codigo(session: Session, email_bruto: str, codigo: str, ip: str, user_agent: str) -> tuple[Usuario, str]:
    """Valida e abre sessão. Devolve (usuario, token em claro para o cookie)."""
    s = get_settings()
    email = normalizar_email(email_bruto)
    codigo = (codigo or "").strip().replace(" ", "")
    if bloqueado(session, email, ip):
        registrar(session, "bloqueado", email=email, ip=ip, ok=False, detalhe="tentativa durante bloqueio")
        raise AuthErro(429, f"muitas tentativas; aguarde {s.auth_bloqueio_minutos} minutos")
    u = obter_usuario(session, email)
    if u is None or not u.ativo or not codigo.isdigit() or len(codigo) != 6:
        registrar(session, "login_falha", email=email, ip=ip, ok=False, detalhe="usuário/código inválido")
        raise AuthErro(401, "código inválido ou expirado")
    atual = session.exec(
        select(CodigoAcesso).where(CodigoAcesso.usuario_id == u.id, CodigoAcesso.usado_em == None, CodigoAcesso.invalidado == False).order_by(CodigoAcesso.id.desc())  # type: ignore[attr-defined]  # noqa: E711,E712
    ).first()
    if atual is None or _aware(atual.expira_em) < agora():
        registrar(session, "login_falha", email=email, ip=ip, ok=False, detalhe="sem código vigente")
        raise AuthErro(401, "código inválido ou expirado")
    atual.tentativas += 1
    if not hmac.compare_digest(atual.codigo_hash, hash_segredo(codigo)):
        if atual.tentativas >= s.auth_codigo_tentativas:
            atual.invalidado = True
        session.add(atual)
        session.commit()
        registrar(session, "login_falha", email=email, ip=ip, ok=False, detalhe=f"código errado ({atual.tentativas}/{s.auth_codigo_tentativas})")
        raise AuthErro(401, "código inválido ou expirado")
    atual.usado_em = agora()
    u.ultimo_login = agora()
    session.add(atual)
    session.add(u)
    session.commit()
    token = criar_sessao(session, u, ip, user_agent)
    registrar(session, "login_ok", email=email, ip=ip, detalhe=f"canal={atual.canal}")
    return u, token


# ------------------------------------------------------------------ sessões
def criar_sessao(session: Session, usuario: Usuario, ip: str, user_agent: str) -> str:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    session.add(Sessao(token_hash=hash_segredo(token), usuario_id=usuario.id, expira_em=agora() + timedelta(hours=s.auth_sessao_horas), ip=ip, user_agent=user_agent[:200]))  # type: ignore[arg-type]
    session.commit()
    return token


def obter_sessao(session: Session, token: str | None) -> tuple[Sessao, Usuario] | None:
    if not token or len(token) > 128:
        return None
    s = get_settings()
    ss = session.exec(select(Sessao).where(Sessao.token_hash == hash_segredo(token))).first()
    if ss is None or ss.revogada:
        return None
    t = agora()
    if _aware(ss.expira_em) < t or _aware(ss.ultimo_uso) + timedelta(minutes=s.auth_sessao_inatividade_min) < t:
        ss.revogada = True
        session.add(ss)
        session.commit()
        return None
    u = session.get(Usuario, ss.usuario_id)
    if u is None or not u.ativo:
        return None
    if (t - _aware(ss.ultimo_uso)).total_seconds() > 60:  # evita uma escrita por requisição
        ss.ultimo_uso = t
        session.add(ss)
        session.commit()
    return ss, u


def revogar_sessao(session: Session, token: str | None) -> None:
    if not token:
        return
    ss = session.exec(select(Sessao).where(Sessao.token_hash == hash_segredo(token))).first()
    if ss is not None:
        ss.revogada = True
        session.add(ss)
        session.commit()


def revogar_todas(session: Session, usuario_id: int, exceto_token: str | None = None) -> int:
    manter = hash_segredo(exceto_token) if exceto_token else None
    n = 0
    for ss in session.exec(select(Sessao).where(Sessao.usuario_id == usuario_id, Sessao.revogada == False)).all():  # noqa: E712
        if ss.token_hash == manter:
            continue
        ss.revogada = True
        session.add(ss)
        n += 1
    session.commit()
    return n


def limpar_expirados(session: Session) -> None:
    """Higiene: apaga códigos e sessões vencidos há mais de 1 dia e eventos com mais de 180 dias."""
    corte = agora() - timedelta(days=1)
    for c in session.exec(select(CodigoAcesso).where(CodigoAcesso.expira_em < corte)).all():
        session.delete(c)
    for ss in session.exec(select(Sessao).where(Sessao.expira_em < corte)).all():
        session.delete(ss)
    for ev in session.exec(select(EventoAcesso).where(EventoAcesso.em < agora() - timedelta(days=180))).all():
        session.delete(ev)
    session.commit()
