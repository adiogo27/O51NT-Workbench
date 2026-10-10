"""Orquestrador de busca reversa: upload (vira evidência com hash) → deeplinks por provedor."""

from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.db import get_session
from app.routers.evidence import EvidenceOut, criar_evidencia

router = APIRouter(prefix="/api/images", tags=["images"])

# Provedores do PDF. Sem API: páginas de upload manual ou busca por URL pública da imagem.
PROVEDORES: dict[str, dict[str, str | None]] = {
    "google": {
        "nome": "Imagens do Google (Lens)",
        "upload": "https://www.google.com/imghp",
        "por_url": "https://lens.google.com/uploadbyurl?url={u}",
    },
    "tineye": {"nome": "TinEye", "upload": "https://tineye.com/", "por_url": "https://tineye.com/search?url={u}"},
    "yandex": {
        "nome": "Yandex.Images",
        "upload": "https://yandex.com/images",
        "por_url": "https://yandex.com/images/search?rpt=imageview&url={u}",
    },
    "bing": {"nome": "Bing Visual Search", "upload": "https://www.bing.com/visualsearch", "por_url": "https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:{u}"},
    "lenso": {"nome": "Lenso.ai", "upload": "https://lenso.ai/pt", "por_url": None},
    "sensity": {"nome": "Sensity (Deep Fake Detection)", "upload": "https://platform.sensity.ai/login", "por_url": None},
}


def gerar_deeplinks(url_publica: str | None) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    for pid, p in PROVEDORES.items():
        por_url = p["por_url"].format(u=quote_plus(url_publica)) if (p["por_url"] and url_publica) else None
        out[pid] = {"nome": p["nome"], "abrir": por_url or p["upload"], "upload_manual": p["upload"], "por_url": por_url}
    return out


@router.get("/providers")
async def provedores() -> dict:
    return {"provedores": gerar_deeplinks(None)}


@router.get("/deeplinks")
async def deeplinks(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Informe uma URL pública http(s) da imagem")
    return {"url": url, "provedores": gerar_deeplinks(url)}


@router.post("/upload")
async def upload(
    arquivo: UploadFile = File(...),
    origem_url: str | None = Form(None),
    notas: str = Form(""),
    session: Session = Depends(get_session),
) -> dict:
    if not (arquivo.content_type or "").startswith("image/"):
        raise HTTPException(415, "Envie um arquivo de imagem")
    ev = criar_evidencia(session, arquivo, "imagem", origem_url, notas)
    publica = origem_url if (origem_url or "").startswith(("http://", "https://")) else None
    return {
        "evidencia": EvidenceOut.model_validate(ev, from_attributes=True).model_dump(mode="json"),
        "provedores": gerar_deeplinks(publica),
        "observacao": (
            "Imagem local não é enviada a terceiros automaticamente. Use 'upload manual' em cada provedor "
            "ou informe a URL pública de origem para busca direta."
        ),
    }
