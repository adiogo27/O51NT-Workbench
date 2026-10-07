"""Léxico ponderado de mobilização (puro Python; sempre disponível, sem ML).

Avalia um texto (OCR do cartaz + texto do post) e devolve um score 0-100 explicável:
termos casados por categoria, data/hora/local extraídos e a distinção "convocando × noticiando".
A comparação usa `radar.normalizar` (sem acentos, sem caixa), o que tolera acentos perdidos pelo OCR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from app.services import locations
from app.services.radar import normalizar

CATEGORIAS: tuple[str, ...] = ("convocacao", "nao_pacifico", "temporal", "local", "distribuicao")
PESOS_CATEGORIA: dict[str, int] = {"convocacao": 2, "nao_pacifico": 4, "temporal": 2, "local": 1, "distribuicao": 2}

# Termos já normalizados (sem acento, minúsculos). `*` = sufixo livre (\w*). Frases toleram quebras de linha.
LEXICO: dict[str, tuple[str, ...]] = {
    "convocacao": (
        "ato", "atos", "ato publico", "ato nacional", "ato unificado", "manifesta*", "protest*", "mobiliza*", "convoca*",
        "chamada geral", "chamado geral", "chamamento", "todos as ruas", "todos nas ruas", "todo mundo na rua",
        "vem pra rua", "vem para a rua", "vem pra luta", "vamos pra rua", "vamos para as ruas", "vamos as ruas", "as ruas",
        "nas ruas", "pra rua", "greve geral", "greve", "paralisa*", "marcha", "passeata", "grito dos excluidos",
        "grito dos excluidos e das excluidas", "concentracao", "ocupa*", "tranca*", "6x1", "escala 6x1", "fim da escala 6x1",
        "panelaco", "buzinaco", "carreata", "motociata", "levante", "levante popular", "resistencia", "luta", "lutar",
        "bora pra rua", "bora pra cima", "pra cima deles", "nao vamos recuar", "sem recuo", "revolucao",
    ),
    "nao_pacifico": (
        "nao pacifico", "nao pacifica", "nao pacificos", "ato nao pacifico", "revolta", "revolta nas ruas", "revoltar",
        "vai pegar fogo", "pegar fogo", "botar fogo", "tocar fogo", "por fogo", "incendiar", "queimar", "quebrar tudo",
        "quebra-quebra", "quebra quebra", "quebrar", "depredar", "saquear", "saque", "derrubar", "invadir", "invasao",
        "tomar o poder", "tomar de assalto", "bloqueio", "bloqueios", "bloquear", "bloqueio de rodovia", "fechar a br",
        "fechar rodovia", "fechar a rodovia", "fechar as rodovias", "trancar rodovia", "confronto", "enfrentamento",
        "enfrentar a policia", "resistencia armada", "armados", "armas", "armado", "guerra", "guerra civil", "pau",
        "porrada", "violencia", "violento", "barricada", "barricadas", "intervencao militar", "golpe", "insurreicao",
        "radicaliza*", "sem anistia", "derrubar o governo", "cacar", "linchar", "justica com as proprias maos",
        "coquetel molotov", "molotov", "explodir", "bomba", "sabotagem", "sabotar",
    ),
    "distribuicao": (
        "compartilh*", "repass*", "divulg*", "espalh*", "link do grupo", "link do zap", "entre no grupo", "entra no grupo",
        "entrem no grupo", "grupo do whatsapp", "grupo no whatsapp", "grupo do zap", "grupo do telegram", "canal do telegram",
        "canal no telegram", "nosso grupo", "grupo oficial", "qr code", "qrcode", "qr-code", "link na bio", "chat.whatsapp.com",
        "t.me", "telegram.me", "whatsapp.com/channel", "convide", "chame os amigos", "chama a galera", "marque", "marca os amigos",
    ),
    # local e temporal usam regex próprias (abaixo) além das capitais/UFs de locations.py
    "local": (
        "praca", "em frente", "em frente a", "em frente ao", "concentracao em", "concentracao na", "concentracao no", "assembleia",
        "camara", "congresso", "esplanada", "esplanada dos ministerios", "paulista", "av paulista", "avenida paulista",
        "largo", "avenida", "rodoviaria", "centro da cidade", "prefeitura", "palacio", "cinelandia", "candelaria",
        "praca sete", "praca da liberdade", "praca da se", "masp", "copacabana", "estadio",
    ),
    "temporal": ("hoje", "amanha", "depois de amanha", "neste sabado", "neste domingo", "nesta sexta", "proximo sabado", "proximo domingo",
                 "este sabado", "este domingo", "esta sexta", "fim de semana", "final de semana", "feriado", "a partir das"),
}

MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
MESES_ABREV = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
DIAS_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")

_RE_DATA_EXTENSO = re.compile(
    r"(?<!\d)(?:dia\s+)?(\d{1,2})\s*(?:de\s+)?(" + "|".join(MESES) + r"|" + "|".join(MESES_ABREV) + r")\b\.?(?:\s*(?:de\s+)?(\d{4}))?"
)
_RE_DATA_NUM = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
_RE_DIA_SEMANA = re.compile(r"\b(" + "|".join(DIAS_SEMANA) + r")(?:-feira|\s+feira)?\b")
_RE_HORA = re.compile(
    r"(?<![\w])(\d{1,2})\s*(?:h|hs|hrs|horas?)(?:\s*(\d{2}))?(?![\w])"  # 14h, 14h30, 9 horas
    r"|(?<!\d)(\d{1,2}):(\d{2})(?!\d)"  # 14:30
    r"|\bas\s+(\d{1,2})(?![\w:/])(?!\s*(?:de\b|/|x\d|horas?\b))"  # "às 14" (não "ruas 6x1")
)

# Pistas de cobertura jornalística (pretérito, atribuição, veículos) × pistas de convocação (imperativo/futuro).
PISTAS_NOTICIANDO: tuple[str, ...] = (
    "protestaram", "manifestaram", "se manifestaram", "ocorreu", "ocorreram", "aconteceu", "aconteceram", "reuniu", "reuniram",
    "bloquearam", "fecharam", "foram presos", "foi preso", "presos", "detidos", "terminou", "terminaram", "deixou feridos",
    "feridos", "segundo a pm", "segundo a policia", "segundo a prf", "segundo o governo", "informou", "afirmou", "disse",
    "declarou", "de acordo com", "reportagem", "jornalista", "fotos:", "foto:", "credito", "leia mais", "saiba mais",
    "veja o video", "assista", "g1", "folha", "estadao", "uol", "agencia brasil", "cnn", "metropoles", "poder360", "o globo",
    "band", "sbt", "record", "manifestantes", "organizadores disseram", "a policia estima", "participaram", "compareceram",
)
PISTAS_CONVOCANDO: tuple[str, ...] = (
    "vem", "venha", "venham", "vamos", "bora", "compareca", "comparecam", "participe", "participem", "sera", "vai ter", "vai acontecer",
    "acontece", "acontecera", "concentracao as", "concentracao a partir", "todos", "todas", "todes", "convocamos", "chamamos",
    "nao falte", "nao faltem", "presenca", "esteja", "estejam", "junte-se", "junte se", "leve", "traga", "tragam",
)
_RE_IMPERATIVO = re.compile(r"\b(vem|venha|venham|vamos|bora|compareca|comparecam|participe|participem|traga|tragam|leve|levem)\b")

Tempo = Literal["futuro", "passado", "indefinido"]


@dataclass(slots=True)
class AvaliacaoLexico:
    pontos: int = 0
    cobertura: int = 0
    termos: dict[str, list[str]] = field(default_factory=dict)
    tempo: Tempo = "indefinido"
    data_evento: date | None = None
    hora_evento: str | None = None
    local: str | None = None
    noticiando: bool = False
    pistas_noticiando: list[str] = field(default_factory=list)
    pistas_convocando: list[str] = field(default_factory=list)
    nao_pacifico: bool = False
    score: int = 0

    def resumo(self) -> dict:
        return {
            "pontos": self.pontos,
            "cobertura": self.cobertura,
            "termos": self.termos,
            "tempo": self.tempo,
            "data_evento": self.data_evento.isoformat() if self.data_evento else None,
            "hora_evento": self.hora_evento,
            "local": self.local,
            "noticiando": self.noticiando,
            "pistas_noticiando": self.pistas_noticiando,
            "pistas_convocando": self.pistas_convocando,
            "nao_pacifico": self.nao_pacifico,
            "score": self.score,
        }


def _regex_termo(termo: str) -> re.Pattern[str]:
    partes = [p for p in normalizar(termo).split(" ") if p]
    corpo = r"\s+".join(re.escape(p).replace(r"\*", r"\w*") for p in partes)
    return re.compile(rf"(?<![\w@#]){corpo}(?!\w)")


_COMPILADO: dict[str, list[tuple[str, re.Pattern[str]]]] = {cat: [(t, _regex_termo(t)) for t in termos] for cat, termos in LEXICO.items()}

# Localidades: capitais e UFs (nome completo) + apelidos comuns. Resultado "Cidade/UF".
_ALIASES_CIDADE: dict[str, tuple[str, str]] = {
    "bh": ("Belo Horizonte", "MG"), "belzonte": ("Belo Horizonte", "MG"), "beaga": ("Belo Horizonte", "MG"),
    "sampa": ("São Paulo", "SP"), "poa": ("Porto Alegre", "RS"), "bsb": ("Brasília", "DF"), "brasilia df": ("Brasília", "DF"),
    "floripa": ("Florianópolis", "SC"), "rio de janeiro": ("Rio de Janeiro", "RJ"), "rj": ("Rio de Janeiro", "RJ"),
}


def _localidades() -> list[tuple[re.Pattern[str], str]]:
    itens: list[tuple[re.Pattern[str], str]] = []
    for cod, uf, nome in locations.CAPITAIS:
        itens.append((_regex_termo(nome), f"{nome}/{uf}"))
    for apelido, (nome, uf) in _ALIASES_CIDADE.items():
        itens.append((_regex_termo(apelido), f"{nome}/{uf}"))
    for cod, sigla, nome in locations.UFS:
        itens.append((_regex_termo(nome), f"{nome}/{sigla}"))
    # mais específicos (nomes longos) primeiro, para "rio de janeiro" vencer "rj"
    itens.sort(key=lambda x: -len(x[0].pattern))
    return itens


_LOCALIDADES = _localidades()
_UF_SIGLAS = {sigla for _, sigla, _ in locations.UFS}


def extrair_local(texto_norm: str) -> str | None:
    """Primeira localidade reconhecida ("Belo Horizonte/MG"); cidade tem prioridade sobre UF."""
    nomes_uf = {n for _, _, n in locations.UFS}
    melhor: tuple[int, int, str] | None = None
    for rx, rotulo in _LOCALIDADES:
        m = rx.search(texto_norm)
        if m is None:
            continue
        prioridade = 1 if rotulo.split("/")[0] in nomes_uf else 0
        chave = (prioridade, m.start(), rotulo)
        if melhor is None or chave[:2] < melhor[:2]:
            melhor = chave
    return melhor[2] if melhor else None


def _ano_para(dia: int, mes: int, referencia: date) -> date | None:
    """Data sem ano: assume o ano da referência; se já passou há mais de 60 dias, assume o próximo (cartaz anuncia o futuro)."""
    try:
        d = date(referencia.year, mes, dia)
    except ValueError:
        return None
    if (referencia - d).days > 60:
        try:
            d = date(referencia.year + 1, mes, dia)
        except ValueError:
            return None
    return d


def extrair_data(texto_norm: str, referencia: date) -> tuple[date | None, str | None]:
    """(data_evento, hora_evento) a partir de "dia 11 de outubro", "11/10", "às 14h", "14:30"."""
    data: date | None = None
    for m in _RE_DATA_EXTENSO.finditer(texto_norm):
        dia = int(m.group(1))
        mes_txt = m.group(2)
        mes = (MESES.index(mes_txt) if mes_txt in MESES else MESES_ABREV.index(mes_txt)) + 1
        if m.group(3):
            try:
                data = date(int(m.group(3)), mes, dia)
            except ValueError:
                data = None
        else:
            data = _ano_para(dia, mes, referencia)
        if data:
            break
    if data is None:
        for m in _RE_DATA_NUM.finditer(texto_norm):
            dia, mes = int(m.group(1)), int(m.group(2))
            if not (1 <= mes <= 12 and 1 <= dia <= 31):
                continue
            if m.group(3):
                ano = int(m.group(3))
                ano = ano + 2000 if ano < 100 else ano
                try:
                    data = date(ano, mes, dia)
                except ValueError:
                    data = None
            else:
                data = _ano_para(dia, mes, referencia)
            if data:
                break
    hora: str | None = None
    for m in _RE_HORA.finditer(texto_norm):
        if m.group(1):
            h, mi = int(m.group(1)), int(m.group(2) or 0)
        elif m.group(3):
            h, mi = int(m.group(3)), int(m.group(4))
        else:
            h, mi = int(m.group(5)), 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            hora = f"{h:02d}:{mi:02d}"
            break
    return data, hora


def _casar_categoria(cat: str, texto: str, extras: tuple[tuple[str, re.Pattern[str]], ...] = (), excluir: frozenset[str] = frozenset()) -> list[str]:
    achados: list[str] = []
    for rotulo, rx in (*_COMPILADO[cat], *extras):
        if rotulo in excluir:
            continue
        if rx.search(texto):
            achados.append(rotulo)
    return achados


def avaliar(
    texto: str,
    referencia: datetime | None = None,
    extras: list[str] | tuple[str, ...] = (),
    excluir: list[str] | tuple[str, ...] = (),
    host_imprensa: bool = False,
) -> AvaliacaoLexico:
    """Pontua o texto. `extras` entram na categoria convocacao (peso 2); `excluir` remove termos do léxico."""
    ref_dt = referencia or datetime.now(UTC)
    ref = ref_dt.date()
    t = normalizar(texto)
    av = AvaliacaoLexico()
    if not t:
        return av
    excl = frozenset(normalizar(e) for e in excluir)
    extras_rx = tuple((normalizar(e), _regex_termo(e)) for e in extras if e.strip())

    for cat in CATEGORIAS:
        achados = _casar_categoria(cat, t, extras_rx if cat == "convocacao" else (), excl)
        if achados:
            av.termos[cat] = achados

    av.data_evento, av.hora_evento = extrair_data(t, ref)
    if _RE_DIA_SEMANA.search(t):
        av.termos.setdefault("temporal", []).append(_RE_DIA_SEMANA.search(t).group(0))  # type: ignore[union-attr]
    if av.data_evento:
        av.termos.setdefault("temporal", []).insert(0, av.data_evento.strftime("%d/%m/%Y"))
    if av.hora_evento:
        av.termos.setdefault("temporal", []).append(av.hora_evento)
    av.local = extrair_local(t)
    if av.local:
        av.termos.setdefault("local", []).insert(0, av.local)

    # pistas
    av.pistas_noticiando = [p for p in PISTAS_NOTICIANDO if _regex_termo(p).search(t)]
    av.pistas_convocando = [p for p in PISTAS_CONVOCANDO if _regex_termo(p).search(t)]
    if host_imprensa:
        av.pistas_noticiando.append("fonte: imprensa")
    data_passada = av.data_evento is not None and av.data_evento < ref
    data_futura = av.data_evento is not None and av.data_evento >= ref
    if data_passada:
        av.pistas_noticiando.append("data no passado")
    if data_futura:
        av.pistas_convocando.append("data no futuro")
    if av.hora_evento:
        av.pistas_convocando.append("hora explícita")
    av.noticiando = len(av.pistas_noticiando) >= 2 and len(av.pistas_noticiando) > len(av.pistas_convocando) - 1
    if data_futura or (len(av.pistas_convocando) >= 2 and not av.noticiando):
        av.tempo = "futuro"
    elif data_passada or av.noticiando:
        av.tempo = "passado"

    # pontuação
    av.pontos = sum(PESOS_CATEGORIA[cat] * len(ts) for cat, ts in av.termos.items())
    av.cobertura = len(av.termos)
    av.nao_pacifico = bool(av.termos.get("nao_pacifico"))
    bruto = min(100.0, 10.0 * av.pontos + 10.0 * av.cobertura)
    if not (av.termos.get("convocacao") or av.termos.get("nao_pacifico") or av.termos.get("distribuicao")):
        bruto = min(bruto, 10.0)  # só contexto (data/local) não é convocação
    if av.noticiando:
        bruto *= 0.35
    if av.tempo == "passado":
        bruto *= 0.8
    elif av.tempo == "futuro":
        bruto *= 1.2
    av.score = int(round(min(100.0, bruto)))
    return av


def janela_referencia(publicado_em: datetime | None) -> datetime:
    """Referência temporal: data de publicação (se houver) ou agora. Datetimes do SQLite podem vir sem fuso."""
    if publicado_em is None:
        return datetime.now(UTC)
    return publicado_em if publicado_em.tzinfo else publicado_em.replace(tzinfo=UTC)


__all__ = ["AvaliacaoLexico", "CATEGORIAS", "LEXICO", "PESOS_CATEGORIA", "avaliar", "extrair_data", "extrair_local", "janela_referencia"]
