"""Ferramentas OSINT instaladas no servidor (as do Kali), executadas com lista de permissão e sem shell.

Regras: só OSINT passivo sobre dados públicos (whois, DNS, subdomínios, usernames públicos, metadados de mídia);
ferramentas intrusivas (nmap, masscan, nuclei, gobuster, wpscan, hydra, sqlmap) NÃO entram. As sensíveis por LGPD
(holehe, h8mail, phoneinfoga) só rodam com `ferramentasSensiveisAtivas`, ficam na auditoria sem a saída e nunca têm
o resultado persistido. Alvo validado por regex por tipo; `create_subprocess_exec` (sem shell); timeout; saída ≤ 64 KB.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from app.config import get_settings
from app.models.evidence import Evidence
from app.models.ia import FerramentaExecucao

logger = logging.getLogger("o51nt.ferramentas")
SAIDA_MAX = 64 * 1024
_semaforo = asyncio.Semaphore(2)


class ErroFerramenta(Exception):
    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.detalhe = detalhe


@dataclass(slots=True)
class Ferramenta:
    id: str
    nome: str
    binario: str
    descricao: str
    tipo_alvo: str  # dominio | usuario | url | email | telefone | evidencia
    args: list[str]  # "{alvo}" é substituído pelo alvo validado
    grupo: str  # infra | perfis | midia | sensivel
    timeout_s: int = 60
    sensivel: bool = False
    exemplo: str = ""
    binarios_alternativos: tuple[str, ...] = field(default_factory=tuple)


REGISTRO: dict[str, Ferramenta] = {
    f.id: f
    for f in (
        Ferramenta("whois", "whois", "whois", "Registro do domínio (registrante, datas, servidores de nome).", "dominio", ["{alvo}"], "infra", 30, exemplo="prf.gov.br"),
        Ferramenta("dig", "dig", "dig", "Registros DNS públicos (A, AAAA, MX, NS, TXT, CNAME).", "dominio", ["+noall", "+answer", "{alvo}", "A", "{alvo}", "AAAA", "{alvo}", "MX", "{alvo}", "NS", "{alvo}", "TXT", "{alvo}", "CNAME"], "infra", 30, exemplo="prf.gov.br"),
        Ferramenta("dnsrecon", "dnsrecon", "dnsrecon", "Enumeração DNS padrão (SOA, NS, MX, SRV, zona) — modo passivo.", "dominio", ["-d", "{alvo}", "-t", "std"], "infra", 120, exemplo="prf.gov.br"),
        Ferramenta("subfinder", "subfinder", "subfinder", "Subdomínios por fontes passivas (certificados, buscadores).", "dominio", ["-d", "{alvo}", "-passive", "-silent", "-timeout", "20"], "infra", 180, exemplo="prf.gov.br"),
        Ferramenta("theharvester", "theHarvester", "theHarvester", "E-mails institucionais, hosts e subdomínios em fontes públicas.", "dominio", ["-d", "{alvo}", "-b", "duckduckgo,bing,crtsh", "-l", "100"], "infra", 240, exemplo="prf.gov.br", binarios_alternativos=("theharvester",)),
        Ferramenta("sherlock", "sherlock", "sherlock", "Em quais redes um nome de usuário público existe.", "usuario", ["--print-found", "--no-txt", "--timeout", "10", "--no-color", "{alvo}"], "perfis", 240, exemplo="prfbrasil"),
        Ferramenta("maigret", "maigret", "maigret", "Perfis públicos por nome de usuário (mais sites, com metadados).", "usuario", ["--no-color", "--no-progressbar", "--timeout", "10", "--top-sites", "300", "{alvo}"], "perfis", 300, exemplo="prfbrasil"),
        Ferramenta("exiftool", "exiftool", "exiftool", "Metadados de uma evidência já guardada (câmera, data, GPS, software).", "evidencia", ["-j", "-G", "-n", "{alvo}"], "midia", 30, exemplo="12 (id da evidência)"),
        Ferramenta("ytdlp", "yt-dlp (metadados)", "yt-dlp", "Metadados de um vídeo público (título, canal, data, descrição) sem baixar.", "url", ["--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings", "{alvo}"], "midia", 90, exemplo="https://www.youtube.com/watch?v=…"),
        Ferramenta("holehe", "holehe", "holehe", "Serviços em que um e-mail está cadastrado (dado pessoal — LGPD).", "email", ["--only-used", "--no-color", "{alvo}"], "sensivel", 180, sensivel=True, exemplo="pessoa@exemplo.com"),
        Ferramenta("h8mail", "h8mail", "h8mail", "Vazamentos conhecidos de um e-mail (dado pessoal — LGPD; chaves de API opcionais).", "email", ["-t", "{alvo}", "--skip-defaults"], "sensivel", 180, sensivel=True, exemplo="pessoa@exemplo.com"),
        Ferramenta("phoneinfoga", "phoneinfoga", "phoneinfoga", "Operadora, região e pegadas públicas de um telefone (dado pessoal — LGPD).", "telefone", ["scan", "-n", "{alvo}"], "sensivel", 90, sensivel=True, exemplo="+5561999999999"),
    )
}

_REGEX = {
    "dominio": re.compile(r"^(?=.{1,253}$)(?!-)(?:[a-z0-9-]{1,63}\.)+[a-z]{2,24}$"),
    "usuario": re.compile(r"^[A-Za-z0-9_.-]{2,40}$"),
    "email": re.compile(r"^[A-Za-z0-9._%+-]{1,64}@(?:[a-z0-9-]{1,63}\.)+[a-z]{2,24}$"),
    "telefone": re.compile(r"^\+?[0-9]{8,15}$"),
    "url": re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{1,2000}$"),
}


def validar_alvo(tipo: str, alvo: str, session: Session | None = None) -> str:
    """Normaliza e valida o alvo; levanta ErroFerramenta(422). Nunca aceita espaços, aspas ou início com '-'."""
    a = (alvo or "").strip()
    if not a or a.startswith("-") or any(ch in a for ch in " \t\n\r'\"`$;|&<>\\"):
        raise ErroFerramenta(422, "alvo inválido")
    if tipo == "evidencia":
        if not a.isdigit() or session is None:
            raise ErroFerramenta(422, "informe o id numérico da evidência")
        ev = session.get(Evidence, int(a))
        if ev is None:
            raise ErroFerramenta(404, f"evidência #{a} não encontrada")
        base = get_settings().evidence_dir.resolve()
        caminho = (base / ev.arquivo).resolve()
        if base not in caminho.parents or not caminho.is_file():
            raise ErroFerramenta(422, "arquivo da evidência fora do diretório de evidências")
        return str(caminho)
    if tipo in ("dominio", "email"):
        a = a.lower().removeprefix("https://").removeprefix("http://").split("/", 1)[0].removeprefix("www.")
    if tipo == "usuario":
        a = a.lstrip("@")
    rx = _REGEX.get(tipo)
    if rx is None or not rx.match(a):
        raise ErroFerramenta(422, f"alvo não parece um(a) {tipo} válido(a)")
    return a


def _path() -> str:
    s = get_settings()
    extra = [str(s.ferramentas_dir), str(Path.home() / ".local" / "bin")]
    return os.pathsep.join(extra + [os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")])


def binario_de(f: Ferramenta) -> str | None:
    for nome in (f.binario, *f.binarios_alternativos):
        achado = shutil.which(nome, path=_path())
        if achado:
            return achado
    return None


def catalogo(prefs_sensiveis: bool) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "nome": f.nome,
            "descricao": f.descricao,
            "tipo_alvo": f.tipo_alvo,
            "grupo": f.grupo,
            "sensivel": f.sensivel,
            "timeout_s": f.timeout_s,
            "exemplo": f.exemplo,
            "instalada": binario_de(f) is not None,
            "habilitada": (not f.sensivel) or prefs_sensiveis,
        }
        for f in REGISTRO.values()
    ]


@dataclass(slots=True)
class ResultadoFerramenta:
    id: int | None
    ferramenta: str
    alvo: str
    comando: list[str]
    ok: bool
    codigo: int | None
    saida: str
    truncada: bool
    duracao_ms: int
    erro: str | None = None


async def executar(session: Session, ferramenta: str, alvo: str, solicitante: str = "painel", sensiveis_ativas: bool = False) -> ResultadoFerramenta:
    f = REGISTRO.get(ferramenta)
    if f is None:
        raise ErroFerramenta(404, "ferramenta desconhecida")
    if f.sensivel and not sensiveis_ativas:
        raise ErroFerramenta(403, "ferramenta sensível (dados pessoais) desligada: habilite 'Ferramentas sensíveis' em Tema, com justificativa legal")
    binario = binario_de(f)
    if binario is None:
        raise ErroFerramenta(503, f"'{f.binario}' não está instalado no servidor (rode deploy/vps/08_ferramentas.sh)")
    alvo_ok = validar_alvo(f.tipo_alvo, alvo, session)
    comando = [binario, *(a.replace("{alvo}", alvo_ok) for a in f.args)]
    # HOME gravável dentro de data/ (o serviço roda com ProtectHome=true; theHarvester/maigret gravam cache e relatórios em $HOME)
    home = get_settings().data_dir / "ferramentas_home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"PATH": _path(), "HOME": str(home), "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "TERM": "dumb"}
    t0 = time.monotonic()
    saida = b""
    codigo: int | None = None
    erro: str | None = None
    async with _semaforo:
        try:
            proc = await asyncio.create_subprocess_exec(*comando, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL, env=env, cwd=str(home))
            try:
                saida, _ = await asyncio.wait_for(proc.communicate(), timeout=f.timeout_s)
                codigo = proc.returncode
            except TimeoutError:
                proc.kill()
                await proc.wait()
                erro = f"tempo esgotado ({f.timeout_s}s)"
        except OSError as exc:
            erro = f"falha ao executar: {exc}"
    duracao = int((time.monotonic() - t0) * 1000)
    truncada = len(saida) > SAIDA_MAX
    texto = saida[:SAIDA_MAX].decode("utf-8", "replace")
    texto = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", texto)  # cores ANSI remanescentes
    ok = erro is None and codigo == 0
    linhas = texto.count("\n") + (1 if texto and not texto.endswith("\n") else 0)
    resumo = f"[sensível] {linhas} linha(s) de saída" if f.sensivel else texto[:2000]
    reg = FerramentaExecucao(ferramenta=f.id, alvo=alvo_ok if not f.sensivel else _mascarar(alvo_ok), solicitante=solicitante[:120], ok=ok, duracao_ms=duracao, resumo=(erro or resumo)[:2000])
    session.add(reg)
    session.commit()
    session.refresh(reg)
    logger.info("ferramenta executada", extra={"dados": {"ferramenta": f.id, "ok": ok, "ms": duracao, "solicitante": solicitante}})
    return ResultadoFerramenta(id=reg.id, ferramenta=f.id, alvo=alvo_ok, comando=[Path(binario).name, *comando[1:]] if not f.sensivel else [Path(binario).name, "…"], ok=ok, codigo=codigo, saida=texto, truncada=truncada, duracao_ms=duracao, erro=erro)


def _mascarar(valor: str) -> str:
    if "@" in valor:
        nome, dom = valor.split("@", 1)
        return f"{nome[:2]}***@{dom}"
    return f"{valor[:4]}***{valor[-2:]}" if len(valor) > 6 else "***"


def historico(session: Session, limit: int = 50) -> list[FerramentaExecucao]:
    return list(session.exec(select(FerramentaExecucao).order_by(col(FerramentaExecucao.id).desc()).limit(max(1, min(limit, 500)))).all())
