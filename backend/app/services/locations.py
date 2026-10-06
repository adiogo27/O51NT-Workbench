"""Base local embutida (subset) de localidades IBGE e rodovias federais DNIT.

Usada para sugerir termos de localidade na dica "Acompanhamento de termos focado em
localidades" do documento mestre. Subconjunto pequeno para baixo consumo de memória.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Localidade:
    nome: str
    tipo: str  # uf | capital | rodovia
    uf: str
    codigo: str  # código IBGE (UF/município) ou designação DNIT


UFS: tuple[tuple[str, str, str], ...] = (
    ("12", "AC", "Acre"), ("27", "AL", "Alagoas"), ("16", "AP", "Amapá"), ("13", "AM", "Amazonas"),
    ("29", "BA", "Bahia"), ("23", "CE", "Ceará"), ("53", "DF", "Distrito Federal"), ("32", "ES", "Espírito Santo"),
    ("52", "GO", "Goiás"), ("21", "MA", "Maranhão"), ("51", "MT", "Mato Grosso"), ("50", "MS", "Mato Grosso do Sul"),
    ("31", "MG", "Minas Gerais"), ("15", "PA", "Pará"), ("25", "PB", "Paraíba"), ("41", "PR", "Paraná"),
    ("26", "PE", "Pernambuco"), ("22", "PI", "Piauí"), ("33", "RJ", "Rio de Janeiro"), ("24", "RN", "Rio Grande do Norte"),
    ("43", "RS", "Rio Grande do Sul"), ("11", "RO", "Rondônia"), ("14", "RR", "Roraima"), ("42", "SC", "Santa Catarina"),
    ("35", "SP", "São Paulo"), ("28", "SE", "Sergipe"), ("17", "TO", "Tocantins"),
)

CAPITAIS: tuple[tuple[str, str, str], ...] = (
    ("1200401", "AC", "Rio Branco"), ("2704302", "AL", "Maceió"), ("1600303", "AP", "Macapá"),
    ("1302603", "AM", "Manaus"), ("2927408", "BA", "Salvador"), ("2304400", "CE", "Fortaleza"),
    ("5300108", "DF", "Brasília"), ("3205309", "ES", "Vitória"), ("5208707", "GO", "Goiânia"),
    ("2111300", "MA", "São Luís"), ("5103403", "MT", "Cuiabá"), ("5002704", "MS", "Campo Grande"),
    ("3106200", "MG", "Belo Horizonte"), ("1501402", "PA", "Belém"), ("2507507", "PB", "João Pessoa"),
    ("4106902", "PR", "Curitiba"), ("2611606", "PE", "Recife"), ("2211001", "PI", "Teresina"),
    ("3304557", "RJ", "Rio de Janeiro"), ("2408102", "RN", "Natal"), ("4314902", "RS", "Porto Alegre"),
    ("1100205", "RO", "Porto Velho"), ("1400100", "RR", "Boa Vista"), ("4205407", "SC", "Florianópolis"),
    ("3550308", "SP", "São Paulo"), ("2800308", "SE", "Aracaju"), ("1721000", "TO", "Palmas"),
)

# Rodovias federais (DNIT) com UFs atravessadas (subset das principais).
RODOVIAS: tuple[tuple[str, str], ...] = (
    ("BR-101", "RN,PB,PE,AL,SE,BA,ES,RJ,SP,PR,SC,RS"), ("BR-116", "CE,PE,BA,MG,RJ,SP,PR,SC,RS"),
    ("BR-153", "PA,TO,GO,MG,SP,PR,SC,RS"), ("BR-040", "DF,GO,MG,RJ"), ("BR-050", "DF,GO,MG,SP"),
    ("BR-060", "DF,GO,MS"), ("BR-070", "DF,GO,MT"), ("BR-163", "PA,MT,MS,PR,SC,RS"),
    ("BR-364", "SP,MG,GO,MT,RO,AC"), ("BR-381", "MG,SP"), ("BR-262", "ES,MG,SP,MS"),
    ("BR-230", "PB,PE,PI,MA,TO,PA,AM"), ("BR-232", "PE"), ("BR-316", "PA,MA,PI,PE,AL"),
    ("BR-020", "DF,GO,BA,PI,CE"), ("BR-277", "PR"), ("BR-376", "PR,SC"), ("BR-386", "RS"),
    ("BR-290", "RS"), ("BR-319", "AM,RO"), ("BR-174", "AM,RR,MT"), ("BR-010", "DF,GO,TO,MA,PA"),
    ("BR-135", "MA,PI,BA,MG"), ("BR-242", "BA,TO,MT"), ("BR-304", "CE,RN"), ("BR-343", "PI"),
    ("BR-365", "MG,GO"), ("BR-267", "MG,SP,MS"), ("BR-282", "SC"), ("BR-470", "SC,RS"),
)


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _todas() -> list[Localidade]:
    itens = [Localidade(nome, "uf", sigla, cod) for cod, sigla, nome in UFS]
    itens += [Localidade(nome, "capital", uf, cod) for cod, uf, nome in CAPITAIS]
    itens += [Localidade(br, "rodovia", ufs, br) for br, ufs in RODOVIAS]
    return itens


LOCALIDADES: tuple[Localidade, ...] = tuple(_todas())


def buscar(q: str = "", uf: str | None = None, tipo: str | None = None, limite: int = 50) -> list[dict]:
    nq = _norm(q.strip())
    out: list[dict] = []
    for loc in LOCALIDADES:
        if tipo and loc.tipo != tipo:
            continue
        if uf and uf.upper() not in loc.uf.split(","):
            continue
        if nq and nq not in _norm(loc.nome) and nq not in _norm(loc.codigo):
            continue
        out.append(asdict(loc))
        if len(out) >= limite:
            break
    return out


def termo_busca(loc: dict) -> str:
    """Formata como termo de busca: rodovias geram (BR-101 OR "BR 101" OR BR101)."""
    if loc["tipo"] == "rodovia":
        num = loc["nome"].split("-")[1]
        return f'(BR-{num} OR "BR {num}" OR BR{num})'
    nome = loc["nome"]
    return f'"{nome}"' if " " in nome else nome
