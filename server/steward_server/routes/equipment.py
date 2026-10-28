"""Equipment routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..api import Bridge, Files, Hub, Session, require_auth
from ..schemas import (
    CommandIn,
    EquipmentDocumentOut,
    EquipmentIn,
    EquipmentOut,
    EquipmentPatch,
    FinishedIn,
    LiveIn,
    ManualHit,
)
from ..services import equipment

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/equipment", response_model=list[EquipmentOut])
async def list_equipment(session: Session):
    return await equipment.list_equipment(session)


@router.post("/equipment", response_model=EquipmentOut)
async def create_equipment(session: Session, hub: Hub, body: EquipmentIn):
    return await equipment.create_equipment(session, hub, body)


@router.get("/equipment/search", response_model=list[ManualHit])
async def search_manuals(session: Session, q: str, equipment_id: int | None = None, limit: int = 10):
    return await equipment.search_manuals(session, q, equipment_id, limit)


@router.get("/equipment/ha-devices")
async def ha_devices(bridge: Bridge, q: str | None = None) -> list[dict]:
    return await equipment.ha_devices(bridge, q)


@router.get("/equipment/ha-entities")
async def ha_entities(bridge: Bridge, q: str | None = None) -> list[dict]:
    return await bridge.request("entities", timeout=30, query=q)


@router.get("/equipment/{equipment_id}", response_model=EquipmentOut)
async def get_equipment(session: Session, equipment_id: int):
    return await equipment.get_equipment(session, equipment_id)


@router.patch("/equipment/{equipment_id}", response_model=EquipmentOut)
async def update_equipment(session: Session, hub: Hub, equipment_id: int, body: EquipmentPatch):
    return await equipment.update_equipment(session, hub, equipment_id, body)


@router.delete("/equipment/{equipment_id}", status_code=204)
async def delete_equipment(session: Session, hub: Hub, files: Files, equipment_id: int) -> None:
    await equipment.delete_equipment(session, hub, files, equipment_id)


@router.put("/equipment/{equipment_id}/photo", response_model=EquipmentOut)
async def set_photo(session: Session, hub: Hub, files: Files, equipment_id: int, file: UploadFile = File(...)):
    return await equipment.set_photo(session, hub, files, equipment_id, await file.read(), file.filename)


@router.delete("/equipment/{equipment_id}/photo", response_model=EquipmentOut)
async def remove_photo(session: Session, hub: Hub, files: Files, equipment_id: int):
    return await equipment.remove_photo(session, hub, files, equipment_id)


@router.post("/equipment/{equipment_id}/documents", response_model=EquipmentDocumentOut)
async def add_document(
    session: Session,
    hub: Hub,
    files: Files,
    equipment_id: int,
    file: UploadFile = File(...),
    kind: str = Form("manual"),
    title: str | None = Form(None),
):
    return await equipment.add_document(
        session, hub, files, equipment_id, await file.read(),
        filename=file.filename, content_type=file.content_type, kind=kind, title=title,
    )  # fmt: skip


@router.delete("/equipment/{equipment_id}/documents/{document_id}", status_code=204)
async def delete_document(session: Session, hub: Hub, files: Files, equipment_id: int, document_id: int) -> None:
    await equipment.delete_document(session, hub, files, equipment_id, document_id)


@router.put("/equipment/{equipment_id}/live", status_code=204)
async def set_live(session: Session, hub: Hub, equipment_id: int, body: LiveIn) -> None:
    await equipment.set_live(session, hub, equipment_id, body)


@router.post("/equipment/{equipment_id}/finished")
async def finished(session: Session, hub: Hub, equipment_id: int, body: FinishedIn) -> dict:
    return await equipment.finished(session, hub, equipment_id, body)


@router.get("/equipment/{equipment_id}/runs")
async def runs(session: Session, equipment_id: int, limit: int = 20) -> list[dict]:
    return [
        {"id": r.id, "finished_at": r.finished_at, "source": r.source, "detail": r.detail}
        for r in await equipment.runs(session, equipment_id, limit)
    ]


@router.post("/equipment/{equipment_id}/command")
async def command(session: Session, bridge: Bridge, equipment_id: int, body: CommandIn) -> dict:
    return {"result": await equipment.command(session, bridge, equipment_id, body.command)}
