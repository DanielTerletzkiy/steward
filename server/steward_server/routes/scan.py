"""Scanning routes: barcodes, scan modes and photo recognition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from ..api import Actor, Bridge, Hub, Session, require_auth
from ..schemas import ProductOut
from ..services import ai, scan

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


class ScanIn(BaseModel):
    code: str
    mode: str = "lookup"
    amount: float | None = None


class BarcodeIn(BaseModel):
    code: str
    amount: float = 1


@router.get("/scan/lookup")
async def lookup(session: Session, code: str) -> dict[str, Any]:
    return await scan.lookup(session, code)


@router.post("/scan")
async def apply_scan(session: Session, hub: Hub, actor: Actor, body: ScanIn) -> dict[str, Any]:
    return await scan.apply(session, hub, body.code, body.mode, body.amount, actor=actor)


@router.post("/scan/photo")
async def recognize(
    session: Session, bridge: Bridge, files: list[UploadFile] = File(...), hint: str | None = Form(None)
) -> dict[str, Any]:
    images = [ai.Image(await f.read(), f.content_type or "image/jpeg") for f in files]
    return await scan.recognize(session, bridge, images, hint)


@router.post("/products/{product_id}/barcodes", response_model=ProductOut)
async def add_barcode(session: Session, hub: Hub, product_id: int, body: BarcodeIn):
    return await scan.add_barcode(session, hub, product_id, body.code, body.amount)
