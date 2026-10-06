"""Armazenamento de evidências com cadeia de custódia (SHA-256 + manifesto JSONL)."""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings
from app.models.evidence import Evidence

CHUNK = 1024 * 1024


def _nome_seguro(nome: str) -> str:
    base = Path(nome or "arquivo").name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "arquivo"
    return base[:120]


def evidence_dir() -> Path:
    d = get_settings().evidence_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifesto_path() -> Path:
    return evidence_dir() / "manifest.jsonl"


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        while bloco := fh.read(CHUNK):
            h.update(bloco)
    return h.hexdigest()


def salvar(stream: BinaryIO, nome_original: str, limite_bytes: int) -> tuple[str, str, int]:
    """Grava em streaming calculando o hash. Retorna (arquivo_relativo, sha256, tamanho)."""
    dia = datetime.now(UTC).strftime("%Y/%m/%d")
    destino_dir = evidence_dir() / dia
    destino_dir.mkdir(parents=True, exist_ok=True)
    rel = f"{dia}/{uuid.uuid4().hex[:12]}_{_nome_seguro(nome_original)}"
    destino = evidence_dir() / rel
    h = hashlib.sha256()
    tamanho = 0
    try:
        with destino.open("wb") as out:
            while bloco := stream.read(CHUNK):
                tamanho += len(bloco)
                if tamanho > limite_bytes:
                    raise ValueError(f"arquivo excede o limite de {limite_bytes // (1024 * 1024)} MB")
                h.update(bloco)
                out.write(bloco)
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return rel, h.hexdigest(), tamanho


def caminho_absoluto(ev: Evidence) -> Path:
    base = evidence_dir().resolve()
    p = (base / ev.arquivo).resolve()
    if base not in p.parents:
        raise ValueError("caminho fora do diretório de evidências")
    return p


def registrar_manifesto(ev: Evidence, acao: str = "criado") -> None:
    linha = {
        "acao": acao,
        "id": ev.id,
        "tipo": ev.tipo,
        "arquivo": ev.arquivo,
        "nome_original": ev.nome_original,
        "sha256": ev.sha256,
        "tamanho": ev.tamanho,
        "origem_url": ev.origem_url,
        "criado_em": ev.criado_em.isoformat() if ev.criado_em else None,
        "registrado_em": datetime.now(UTC).isoformat(),
        "notas": ev.notas,
    }
    with manifesto_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")


def verificar(ev: Evidence) -> dict:
    p = caminho_absoluto(ev)
    if not p.exists():
        return {"id": ev.id, "integro": False, "sha256_esperado": ev.sha256, "sha256_atual": None, "erro": "arquivo ausente"}
    atual = sha256_arquivo(p)
    return {"id": ev.id, "integro": atual == ev.sha256, "sha256_esperado": ev.sha256, "sha256_atual": atual}


def exportar_zip(evidencias: list[Evidence]) -> bytes:
    """ZIP com arquivos + manifest.json + SHA256SUMS (formato sha256sum)."""
    buf = io.BytesIO()
    manifest: list[dict] = []
    sums: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ev in evidencias:
            p = caminho_absoluto(ev)
            if not p.exists():
                continue
            arcname = f"evidencias/{ev.id:05d}_{Path(ev.arquivo).name}"
            zf.write(p, arcname)
            manifest.append(
                {
                    "id": ev.id,
                    "arquivo": arcname,
                    "nome_original": ev.nome_original,
                    "tipo": ev.tipo,
                    "mime": ev.mime,
                    "tamanho": ev.tamanho,
                    "sha256": ev.sha256,
                    "origem_url": ev.origem_url,
                    "criado_em": ev.criado_em.isoformat(),
                    "notas": ev.notas,
                }
            )
            sums.append(f"{ev.sha256}  {arcname}")
        meta = {"gerado_em": datetime.now(UTC).isoformat(), "ferramenta": "O51NT-Workbench/1.0", "itens": manifest}
        manifest_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode()
        zf.writestr("manifest.json", manifest_bytes)
        sums.append(f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json")
        zf.writestr("SHA256SUMS", "\n".join(sums) + "\n")
    return buf.getvalue()
