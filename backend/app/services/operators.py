"""Parser/validador dos operadores de busca.

Google (documento mestre O51NT):
- Precisão: "frase exata", -excluir, OR, ( ), *
- Temporal: before:AAAA-MM-DD, after:AAAA-MM-DD
- Escopo: site:, -site:, filetype:, inurl:, intitle:, intext:

X/Twitter e TweetDeck (strings do boletim "Op. Eleições 2026"):
- Temporal: since:AAAA-MM-DD, until:AAAA-MM-DD
- Filtros: is:/-is: (retweet, reply, quote, verified), has: (media, images, videos, links…),
  from:, to:, lang:, filter:/-filter:, min_faves:, min_retweets:, min_replies:, near:, within:
- Sintaxe: AND explícito (implícito nos buscadores) e menções @usuário

O tokenizador percorre a string uma única vez (O(n)).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum

OPERADORES_PRECISAO: tuple[str, ...] = ('" "', "-", "OR", "( )", "*")
OPERADORES_TEMPORAIS: tuple[str, ...] = ("before", "after")
OPERADORES_ESCOPO: tuple[str, ...] = ("site", "filetype", "inurl", "intitle", "intext")
# Chaves do Google (nome mantido por compatibilidade: é o conjunto usado por operadores_google()).
OPERADORES_CHAVE: frozenset[str] = frozenset(OPERADORES_TEMPORAIS + OPERADORES_ESCOPO)

OPERADORES_X_TEMPORAIS: tuple[str, ...] = ("since", "until")
OPERADORES_X_FILTROS: tuple[str, ...] = (
    "is", "has", "from", "to", "lang", "filter", "min_faves", "min_retweets", "min_replies", "near", "within",
)
OPERADORES_X_CHAVE: frozenset[str] = frozenset(OPERADORES_X_TEMPORAIS + OPERADORES_X_FILTROS)
TODAS_CHAVES: frozenset[str] = OPERADORES_CHAVE | OPERADORES_X_CHAVE

X_IS_VALORES: frozenset[str] = frozenset({"retweet", "reply", "quote", "verified", "nativeretweets"})
X_HAS_VALORES: frozenset[str] = frozenset({"media", "images", "videos", "links", "mentions", "hashtags", "geo", "cashtags"})
X_NEGAVEIS: frozenset[str] = frozenset({"is", "filter", "has", "from", "to"})

_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DOMINIO_RE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", re.IGNORECASE)
_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_]{1,15}$")
_LANG_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")


class TipoToken(StrEnum):
    FRASE = "frase"
    TERMO = "termo"
    OPERADOR = "operador"
    OR = "or"
    AND = "and"
    ABRE = "abre_parenteses"
    FECHA = "fecha_parenteses"
    CURINGA = "curinga"
    HASHTAG = "hashtag"
    MENCAO = "mencao"


@dataclass(slots=True)
class Token:
    tipo: TipoToken
    valor: str
    posicao: int
    negado: bool = False
    chave: str | None = None  # para OPERADOR: site, before, since, is, ...


@dataclass(slots=True)
class Problema:
    codigo: str
    mensagem: str
    posicao: int | None = None


@dataclass(slots=True)
class ResultadoValidacao:
    query: str
    valida: bool
    erros: list[Problema] = field(default_factory=list)
    avisos: list[Problema] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)
    operadores: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        for t in d["tokens"]:
            t["tipo"] = str(t["tipo"])
        return d


def _ler_valor_operador(q: str, i: int, n: int) -> tuple[str, int, bool]:
    """Lê o valor após `chave:`; aceita valor entre aspas. Retorna (valor, novo_i, aspas_ok)."""
    if i < n and q[i] == '"':
        fim = q.find('"', i + 1)
        if fim == -1:
            return q[i:], n, False
        return q[i : fim + 1], fim + 1, True
    j = i
    while j < n and not q[j].isspace() and q[j] not in "()":
        j += 1
    return q[i:j], j, True


def tokenizar(q: str) -> tuple[list[Token], list[Problema]]:
    """Tokeniza a query em uma passada. Retorna tokens e erros estruturais (aspas/parênteses)."""
    tokens: list[Token] = []
    erros: list[Problema] = []
    profundidade = 0
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            profundidade += 1
            tokens.append(Token(TipoToken.ABRE, c, i))
            i += 1
            continue
        if c == ")":
            if profundidade == 0:
                erros.append(Problema("parenteses_desbalanceados", "Parêntese ')' sem abertura correspondente.", i))
            else:
                profundidade -= 1
            tokens.append(Token(TipoToken.FECHA, c, i))
            i += 1
            continue

        inicio = i
        negado = False
        if c == "-" and i + 1 < n and not q[i + 1].isspace():
            negado = True
            i += 1
            c = q[i]

        if c == '"':
            fim = q.find('"', i + 1)
            if fim == -1:
                erros.append(Problema("aspas_desbalanceadas", "Aspas abertas sem fechamento.", i))
                tokens.append(Token(TipoToken.FRASE, q[i:], inicio, negado))
                break
            tokens.append(Token(TipoToken.FRASE, q[i : fim + 1], inicio, negado))
            i = fim + 1
            continue

        # palavra simples ou operador chave:valor
        j = i
        while j < n and not q[j].isspace() and q[j] not in '()"':
            if q[j] == ":":
                break
            j += 1
        palavra = q[i:j]
        if j < n and q[j] == ":" and palavra.lower() in TODAS_CHAVES:
            valor, k, ok = _ler_valor_operador(q, j + 1, n)
            if not ok:
                erros.append(Problema("aspas_desbalanceadas", f"Aspas abertas sem fechamento em {palavra}:.", j + 1))
            tokens.append(Token(TipoToken.OPERADOR, valor, inicio, negado, palavra.lower()))
            i = k
            continue
        # palavra comum (pode conter ':' como em URLs)
        while j < n and not q[j].isspace() and q[j] not in '()"':
            j += 1
        palavra = q[i:j]
        if palavra == "OR" and not negado:
            tipo = TipoToken.OR
        elif palavra == "AND" and not negado:
            tipo = TipoToken.AND
        elif palavra == "*" and not negado:
            tipo = TipoToken.CURINGA
        elif palavra.startswith("#") and len(palavra) > 1:
            tipo = TipoToken.HASHTAG
        elif palavra.startswith("@") and len(palavra) > 1:
            tipo = TipoToken.MENCAO
        else:
            tipo = TipoToken.TERMO
        tokens.append(Token(tipo, palavra, inicio, negado))
        i = j

    if profundidade > 0:
        erros.append(Problema("parenteses_desbalanceados", f"{profundidade} parêntese(s) '(' sem fechamento."))
    return tokens, erros


def _parse_data(valor: str) -> date | None:
    if not _DATA_RE.match(valor):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _normalizar_dominio(valor: str) -> str:
    v = valor.strip('"').lower()
    v = re.sub(r"^https?://", "", v)
    return v.split("/", 1)[0].removeprefix("www.")


def _validar_operador_x(t: Token, erros: list[Problema], avisos: list[Problema]) -> None:
    """Regras de valor dos operadores do X (chamado só para chaves de OPERADORES_X_FILTROS)."""
    assert t.chave is not None
    v = t.valor.strip('"')
    if t.negado and t.chave not in X_NEGAVEIS:
        avisos.append(Problema("x_negacao_invalida", f"'-{t.chave}:' não é aceito pelo X; a negação será ignorada.", t.posicao))
    if t.chave == "is" and v.lower() not in X_IS_VALORES:
        avisos.append(Problema("x_valor_desconhecido", f"is:{v} — valores conhecidos: {', '.join(sorted(X_IS_VALORES))}.", t.posicao))
    elif t.chave == "has" and v.lower() not in X_HAS_VALORES:
        avisos.append(Problema("x_valor_desconhecido", f"has:{v} — valores conhecidos: {', '.join(sorted(X_HAS_VALORES))}.", t.posicao))
    elif t.chave in ("from", "to") and not _HANDLE_RE.match(v):
        avisos.append(Problema("x_handle_suspeito", f"{t.chave}:{v} não parece um usuário do X (letras, dígitos e _, até 15).", t.posicao))
    elif t.chave == "lang" and not _LANG_RE.match(v):
        avisos.append(Problema("x_valor_desconhecido", f"lang:{v} — use código de idioma (ex.: pt, en).", t.posicao))
    elif t.chave.startswith("min_") and not v.isdigit():
        erros.append(Problema("valor_invalido", f"{t.chave}: exige número inteiro (recebido '{v}').", t.posicao))
    elif t.chave == "within" and not re.fullmatch(r"\d+(?:km|mi)", v.lower()):
        avisos.append(Problema("x_valor_desconhecido", f"within:{v} — formato esperado: 15km ou 10mi.", t.posicao))


def validar(query: str) -> ResultadoValidacao:
    """Valida uma query crua com os operadores do Google e do X/TweetDeck."""
    tokens, erros = tokenizar(query)
    avisos: list[Problema] = []
    operadores: dict[str, list[str]] = {}

    befores: list[tuple[date, int]] = []
    afters: list[tuple[date, int]] = []
    sinces: list[tuple[date, int]] = []
    untils: list[tuple[date, int]] = []
    sites_incl: dict[str, int] = {}
    sites_excl: dict[str, int] = {}
    chaves_x: list[str] = []
    tem_positivo = False
    tem_and = False
    tem_mencao = False
    anterior: Token | None = None

    for idx, t in enumerate(tokens):
        if t.tipo is TipoToken.OPERADOR:
            assert t.chave is not None
            rotulo = f"-{t.chave}" if t.negado else t.chave
            operadores.setdefault(rotulo, []).append(t.valor)
            if not t.valor:
                erros.append(Problema("operador_vazio", f"Operador '{t.chave}:' sem valor (não use espaço após ':').", t.posicao))
                anterior = t
                continue
            if t.chave in OPERADORES_X_CHAVE and f"{rotulo}:" not in chaves_x:
                chaves_x.append(f"{rotulo}:")
            if t.chave in OPERADORES_TEMPORAIS or t.chave in OPERADORES_X_TEMPORAIS:
                d = _parse_data(t.valor)
                if d is None:
                    erros.append(Problema("data_invalida", f"{t.chave}: exige data AAAA-MM-DD válida (recebido '{t.valor}').", t.posicao))
                elif t.chave == "before":
                    befores.append((d, t.posicao))
                elif t.chave == "after":
                    afters.append((d, t.posicao))
                elif t.chave == "since":
                    sinces.append((d, t.posicao))
                else:
                    untils.append((d, t.posicao))
                if t.negado:
                    avisos.append(Problema("temporal_negado", f"'-{t.chave}:' não é suportado.", t.posicao))
            elif t.chave == "site":
                dom = _normalizar_dominio(t.valor)
                if not _DOMINIO_RE.match(dom):
                    avisos.append(Problema("dominio_suspeito", f"Domínio '{t.valor}' parece inválido.", t.posicao))
                (sites_excl if t.negado else sites_incl).setdefault(dom, t.posicao)
            elif t.chave == "filetype":
                if not re.fullmatch(r"[A-Za-z0-9]{1,8}", t.valor):
                    erros.append(Problema("filetype_invalido", f"filetype: inválido '{t.valor}' (ex.: pdf, docx).", t.posicao))
            elif t.chave in OPERADORES_X_FILTROS:
                _validar_operador_x(t, erros, avisos)
            if not t.negado:
                tem_positivo = True
        elif t.tipo in (TipoToken.TERMO, TipoToken.FRASE, TipoToken.HASHTAG, TipoToken.MENCAO):
            if not t.negado:
                tem_positivo = True
            if t.tipo is TipoToken.MENCAO:
                tem_mencao = True
            elif t.tipo is TipoToken.TERMO:
                if t.valor.lower() == "or" and t.valor != "OR":
                    avisos.append(Problema("or_minusculo", "Use 'OR' em maiúsculas; 'or' minúsculo é tratado como palavra.", t.posicao))
                elif t.valor.lower() in OPERADORES_CHAVE:
                    avisos.append(Problema("operador_sem_dois_pontos", f"'{t.valor}' parece um operador sem ':'.", t.posicao))
                elif (
                    _DOMINIO_RE.match(t.valor)
                    and anterior is not None
                    and anterior.tipo is TipoToken.OR
                    and idx >= 2
                    and tokens[idx - 2].tipo is TipoToken.OPERADOR
                    and tokens[idx - 2].chave == "site"
                ):
                    avisos.append(
                        Problema("site_ausente", f"'{t.valor}' em grupo de site: — faltou 'site:{t.valor}'?", t.posicao)
                    )
        elif t.tipo is TipoToken.OR:
            if anterior is None or anterior.tipo in (TipoToken.OR, TipoToken.AND, TipoToken.ABRE):
                erros.append(Problema("or_mal_posicionado", "OR sem termo à esquerda.", t.posicao))
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            if nxt is None or nxt.tipo in (TipoToken.OR, TipoToken.AND, TipoToken.FECHA):
                erros.append(Problema("or_mal_posicionado", "OR sem termo à direita.", t.posicao))
        elif t.tipo is TipoToken.AND:
            tem_and = True
            if anterior is None or anterior.tipo in (TipoToken.OR, TipoToken.AND, TipoToken.ABRE):
                erros.append(Problema("and_mal_posicionado", "AND sem termo à esquerda.", t.posicao))
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            if nxt is None or nxt.tipo in (TipoToken.OR, TipoToken.AND, TipoToken.FECHA):
                erros.append(Problema("and_mal_posicionado", "AND sem termo à direita.", t.posicao))
        elif t.tipo is TipoToken.FECHA and anterior is not None and anterior.tipo is TipoToken.ABRE:
            avisos.append(Problema("grupo_vazio", "Parênteses vazios.", t.posicao))
        elif t.tipo is TipoToken.CURINGA:
            avisos.append(Problema("curinga_fora_aspas", "Curinga '*' funciona melhor dentro de aspas: \"Termo * Termo2\".", t.posicao))
        anterior = t

    # temporal: janela precisa ser não vazia (after < before; since < until)
    if befores and afters:
        b = min(befores)[0]
        a = max(afters)[0]
        if b <= a:
            erros.append(
                Problema(
                    "janela_temporal_vazia",
                    f"before:{b.isoformat()} deve ser posterior a after:{a.isoformat()} (janela vazia).",
                )
            )
    if untils and sinces:
        u = min(untils)[0]
        s = max(sinces)[0]
        if u <= s:
            erros.append(
                Problema(
                    "janela_temporal_vazia",
                    f"until:{u.isoformat()} deve ser posterior a since:{s.isoformat()} (janela vazia).",
                )
            )
    if len(befores) > 1 or len(afters) > 1:
        avisos.append(Problema("temporal_repetido", "Mais de um before:/after: — será usado o mais restritivo."))
    if len(sinces) > 1 or len(untils) > 1:
        avisos.append(Problema("temporal_repetido", "Mais de um since:/until: — será usado o mais restritivo."))
    if (befores or afters) and (sinces or untils):
        avisos.append(
            Problema("temporal_misto", "before:/after: são do Google e since:/until: do X — cada motor ignora o par do outro.")
        )

    # escopo: site: e -site: do mesmo domínio
    for dom, pos in sites_incl.items():
        if dom in sites_excl:
            erros.append(Problema("site_conflitante", f"site:{dom} e -site:{dom} na mesma query.", pos))
        else:
            for excl in sites_excl:
                if dom.endswith("." + excl):
                    avisos.append(Problema("site_subdominio_excluido", f"site:{dom} é subdomínio de -site:{excl}.", pos))

    # X/TweetDeck: avisos consolidados (um por tipo)
    if chaves_x:
        avisos.append(
            Problema(
                "operador_x",
                f"Operadores do X/TweetDeck ({', '.join(chaves_x)}): funcionam no X; no Google e demais motores viram texto literal.",
            )
        )
    if tem_and:
        avisos.append(Problema("and_explicito", "'AND' é implícito nos buscadores; mantido para TweetDeck/X. No Google pode virar palavra."))
    if tem_mencao:
        avisos.append(Problema("mencao", "'@usuário' é menção do X; no Google é tratado como palavra."))

    if tokens and not tem_positivo:
        avisos.append(Problema("somente_exclusoes", "A query contém apenas exclusões; buscadores podem não retornar nada."))
    if not query.strip():
        erros.append(Problema("query_vazia", "Query vazia."))

    return ResultadoValidacao(
        query=query,
        valida=not erros,
        erros=erros,
        avisos=avisos,
        tokens=tokens,
        operadores=operadores,
    )


def operadores_google(query: str) -> list[str]:
    """Rótulos dos operadores exclusivos do Google presentes na query (ordem de 1ª ocorrência).

    Motores acessados via SearXNG não respeitam esses operadores. Espelha
    `frontend/src/lib/queryOperators.ts::detectGoogleOperators` — ambos são testados contra
    `shared/google_operator_cases.json` ("casos").
    Rótulos: "site:", "-site:", "inurl:", ..., "OR", '""' (aspas balanceadas), "()".
    Operadores do X (since:, is:, @, AND) NÃO entram aqui — ver operadores_x().
    """
    tokens, _ = tokenizar(query)
    achados: list[str] = []

    def add(rotulo: str) -> None:
        if rotulo not in achados:
            achados.append(rotulo)

    for t in tokens:
        if t.tipo is TipoToken.OPERADOR:
            if t.chave in OPERADORES_CHAVE:
                add(f"{'-' if t.negado else ''}{t.chave}:")
        elif t.tipo is TipoToken.OR:
            add("OR")
        elif t.tipo is TipoToken.FRASE and len(t.valor) >= 2 and t.valor.endswith('"'):
            add('""')
        elif t.tipo in (TipoToken.ABRE, TipoToken.FECHA):
            add("()")
    return achados


def operadores_x(query: str) -> list[str]:
    """Rótulos dos operadores do X/TweetDeck na query (ordem de 1ª ocorrência).

    Espelha `frontend/src/lib/queryOperators.ts::detectXOperators` — testados contra
    `shared/google_operator_cases.json` ("casos_x").
    Rótulos: "since:", "until:", "is:", "-is:", "has:", "from:", "to:", "lang:", "filter:",
    "min_faves:", …, "@" (menção) e "AND".
    """
    tokens, _ = tokenizar(query)
    achados: list[str] = []

    def add(rotulo: str) -> None:
        if rotulo not in achados:
            achados.append(rotulo)

    for t in tokens:
        if t.tipo is TipoToken.OPERADOR:
            if t.chave in OPERADORES_X_CHAVE:
                add(f"{'-' if t.negado else ''}{t.chave}:")
        elif t.tipo is TipoToken.MENCAO:
            add("@")
        elif t.tipo is TipoToken.AND:
            add("AND")
    return achados
