"""Serving stored photos and documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..api import Files, Session, require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
CACHE = {"Cache-Control": "private, max-age=31536000, immutable"}  # file ids never change content


@router.get("/files/{file_id}", include_in_schema=False)
async def get_file(session: Session, files: Files, file_id: str) -> FileResponse:
    file = await files.get(session, file_id)
    return FileResponse(files.path(file), media_type=file.content_type, filename=file.filename, headers=CACHE,
                        content_disposition_type="inline")


@router.get("/files/{file_id}/thumb", include_in_schema=False)
async def get_thumb(session: Session, files: Files, file_id: str) -> FileResponse:
    file = await files.get(session, file_id)
    thumb = files.thumb_path(file)
    return FileResponse(thumb if thumb.exists() else files.path(file), media_type="image/webp", headers=CACHE)
