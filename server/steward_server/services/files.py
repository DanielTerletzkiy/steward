"""Uploaded photos and documents. Photos are stored as WebP (max 2048 px) with a 480 px thumbnail."""

from __future__ import annotations

import asyncio
import io
import logging
import secrets
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import StoredFile
from . import Invalid, NotFound

LOG = logging.getLogger("steward.files")

MAX_UPLOAD = 40 * 1024 * 1024
PHOTO_EDGE = 2048
THUMB_EDGE = 480


class FileStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "files"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, file: StoredFile) -> Path:
        return self.root / (file.id + _extension(file.content_type))

    def thumb_path(self, file: StoredFile) -> Path:
        return self.root / f"{file.id}.thumb.webp"

    async def save(
        self,
        session: AsyncSession,
        data: bytes,
        *,
        filename: str | None,
        content_type: str | None,
        kind: str,
        cutout: bool = False,
    ) -> StoredFile:
        """Store an upload. Photos are normalized; with `cutout`, the background is removed when rembg is installed."""
        if not data:
            raise Invalid("The file is empty")
        if len(data) > MAX_UPLOAD:
            raise Invalid("The file is larger than 40 MB")
        file_id = secrets.token_hex(12)
        is_pdf = data[:5] == b"%PDF-"
        if kind == "photo" or (not is_pdf and (content_type or "").startswith("image/")):
            photo, thumb = await asyncio.to_thread(_prepare_photo, data, cutout)
            file = StoredFile(id=file_id, kind=kind, filename=filename, content_type="image/webp", size=len(photo))
            self.path(file).write_bytes(photo)
            self.thumb_path(file).write_bytes(thumb)
        elif is_pdf:
            file = StoredFile(id=file_id, kind=kind, filename=filename, content_type="application/pdf", size=len(data))
            self.path(file).write_bytes(data)
        else:
            raise Invalid("Only images and PDF files can be uploaded")
        session.add(file)
        await session.flush()
        return file

    async def get(self, session: AsyncSession, file_id: str) -> StoredFile:
        file = await session.get(StoredFile, file_id)
        if file is None:
            raise NotFound(f"File {file_id} not found")
        return file

    async def delete(self, session: AsyncSession, file_id: str | None) -> None:
        if not file_id:
            return
        file = await session.get(StoredFile, file_id)
        if file is None:
            return
        for path in (self.path(file), self.thumb_path(file)):
            path.unlink(missing_ok=True)
        await session.delete(file)


def _extension(content_type: str) -> str:
    return {"image/webp": ".webp", "application/pdf": ".pdf"}.get(content_type, ".bin")


def _prepare_photo(data: bytes, cutout: bool) -> tuple[bytes, bytes]:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise Invalid("This image format can't be read") from exc
    image.thumbnail((PHOTO_EDGE, PHOTO_EDGE))
    if cutout:
        image = _remove_background(image)
    image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
    full = io.BytesIO()
    image.save(full, "WEBP", quality=85)
    small = image.copy()
    small.thumbnail((THUMB_EDGE, THUMB_EDGE))
    thumb = io.BytesIO()
    small.save(thumb, "WEBP", quality=80)
    return full.getvalue(), thumb.getvalue()


def _remove_background(image):
    """Optional: rembg is large (onnxruntime plus a model download), so it is only used when installed."""
    try:
        from rembg import remove
    except ImportError:
        return image
    try:
        return remove(image)
    except Exception:  # noqa: BLE001 - a failed cutout keeps the original photo
        LOG.exception("Background removal failed")
        return image


def pdf_pages(data: bytes) -> list[str]:
    """Text of each page of a PDF, for the manual search index."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]
