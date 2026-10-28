"""Equipment: appliances with photos, manuals, warranty, consumables and upkeep chores."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..ha_bridge import HABridge
from ..models import APPLIANCE_KINDS, Chore, Equipment, EquipmentDocument, EquipmentRun, Garment
from ..schemas import EquipmentIn, EquipmentPatch, FinishedIn, LiveIn, ManualHit
from ..timeutil import as_utc, utcnow
from . import Invalid, NotFound, chores
from . import settings as settings_store
from .files import FileStore, pdf_pages

# Dropped from manual searches unless nothing else is left ("how do I descale" -> "descale").
STOPWORDS = frozenset(
    "a an and are can do does for how i in is it my of on or the to what when where which why with "
    "der die das ein eine und oder wie was wo wann ich mein meine mit von zu im in ist kann man den dem des".split()
)


async def list_equipment(session: AsyncSession) -> list[Equipment]:
    return list((await session.scalars(select(Equipment).order_by(Equipment.name))).all())


async def get_equipment(session: AsyncSession, equipment_id: int) -> Equipment:
    item = await session.get(Equipment, equipment_id)
    if item is None:
        raise NotFound(f"Equipment {equipment_id} not found")
    return item


def _check(values: dict) -> None:
    if values.get("kind") is not None and values["kind"] not in APPLIANCE_KINDS:
        raise Invalid(f"kind must be one of: {', '.join(APPLIANCE_KINDS)}")
    automation = values.get("automation") or {}
    if automation.get("chores", "off") not in ("complete", "make_due", "off"):
        raise Invalid("automation.chores must be complete, make_due or off")
    if automation.get("laundry", "off") not in ("ask", "auto", "off"):
        raise Invalid("automation.laundry must be ask, auto or off")


async def create_equipment(session: AsyncSession, hub: EventHub, data: EquipmentIn) -> Equipment:
    _check(data.model_dump())
    item = Equipment(**data.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item, ["documents"])  # async sessions can't lazy-load during serialization
    hub.publish("equipment")
    return item


async def update_equipment(session: AsyncSession, hub: EventHub, equipment_id: int, patch: EquipmentPatch) -> Equipment:
    item = await get_equipment(session, equipment_id)
    values = patch.model_dump(exclude_unset=True)
    _check(values)
    if "ha_device_id" in values or "ha_entities" in values:
        item.live = item.live_at = None  # the new link reports its own status
    for key, value in values.items():
        setattr(item, key, value)
    await session.commit()
    hub.publish("equipment")
    return item


async def delete_equipment(session: AsyncSession, hub: EventHub, files: FileStore, equipment_id: int) -> None:
    item = await get_equipment(session, equipment_id)
    await session.execute(text("DELETE FROM manual_page WHERE equipment_id = :id"), {"id": equipment_id})
    file_ids = [doc.file_id for doc in item.documents] + [item.photo_id]
    await session.delete(item)
    for file_id in file_ids:
        await files.delete(session, file_id)
    await session.commit()
    hub.publish("equipment")


async def set_photo(
    session: AsyncSession, hub: EventHub, files: FileStore, equipment_id: int, data: bytes, filename: str | None
) -> Equipment:
    item = await get_equipment(session, equipment_id)
    stored = await files.save(session, data, filename=filename, content_type="image/*", kind="photo")
    old, item.photo_id = item.photo_id, stored.id
    await files.delete(session, old)
    await session.commit()
    hub.publish("equipment")
    return item


async def remove_photo(session: AsyncSession, hub: EventHub, files: FileStore, equipment_id: int) -> Equipment:
    item = await get_equipment(session, equipment_id)
    old, item.photo_id = item.photo_id, None
    await files.delete(session, old)
    await session.commit()
    hub.publish("equipment")
    return item


async def add_document(
    session: AsyncSession,
    hub: EventHub,
    files: FileStore,
    equipment_id: int,
    data: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    kind: str = "manual",
    title: str | None = None,
) -> EquipmentDocument:
    item = await get_equipment(session, equipment_id)
    stored = await files.save(session, data, filename=filename, content_type=content_type, kind=kind)
    document = EquipmentDocument(
        equipment_id=item.id, file_id=stored.id, kind=kind, title=title or _title_from(filename) or kind.title()
    )
    session.add(document)
    if stored.content_type == "application/pdf":
        pages = await asyncio.to_thread(pdf_pages, data)
        stored.pages = len(pages)
        for number, page_text in enumerate(pages, start=1):
            if page_text.strip():
                await session.execute(
                    text(
                        "INSERT INTO manual_page (text, equipment_id, file_id, page) VALUES (:text, :eq, :file, :page)"
                    ),
                    {"text": page_text, "eq": item.id, "file": stored.id, "page": number},
                )
    await session.commit()
    await session.refresh(item)
    await session.refresh(document, ["file"])
    hub.publish("equipment")
    return document


async def delete_document(
    session: AsyncSession, hub: EventHub, files: FileStore, equipment_id: int, document_id: int
) -> None:
    document = await session.get(EquipmentDocument, document_id)
    if document is None or document.equipment_id != equipment_id:
        raise NotFound(f"Document {document_id} not found")
    await session.execute(text("DELETE FROM manual_page WHERE file_id = :id"), {"id": document.file_id})
    file_id = document.file_id
    await session.execute(delete(EquipmentDocument).where(EquipmentDocument.id == document_id))
    await files.delete(session, file_id)
    await session.commit()
    hub.publish("equipment")


async def search_manuals(session: AsyncSession, query: str, equipment_id: int | None = None, limit: int = 10) -> list[ManualHit]:
    """Full-text search over manual pages. All words must appear; if nothing matches, any word may."""
    words = re.findall(r"\w+", query.lower())
    if not words:
        raise Invalid("Search for at least one word")
    words = [w for w in words if w not in STOPWORDS] or words
    hits: list[ManualHit] = []
    for joiner in (" ", " OR "):
        match = joiner.join(f'"{w}"*' if len(w) > 3 else f'"{w}"' for w in words)
        sql = (
            "SELECT equipment_id, file_id, page, snippet(manual_page, 0, '«', '»', '…', 16) AS snip "
            "FROM manual_page WHERE manual_page MATCH :match"
            + (" AND equipment_id = :eq" if equipment_id is not None else "")
            + " ORDER BY rank LIMIT :limit"
        )
        rows = (await session.execute(text(sql), {"match": match, "eq": equipment_id, "limit": limit})).all()
        if rows:
            break
    else:
        return hits
    documents = {
        d.file_id: d
        for d in (
            await session.scalars(select(EquipmentDocument).where(EquipmentDocument.file_id.in_({r.file_id for r in rows})))
        ).all()
    }
    names = {e.id: e.name for e in await list_equipment(session)}
    for row in rows:
        document = documents.get(row.file_id)
        if document is None:
            continue
        hits.append(
            ManualHit(
                equipment_id=int(row.equipment_id),
                equipment_name=names.get(int(row.equipment_id), "?"),
                document_id=document.id,
                document_title=document.title,
                file_id=row.file_id,
                page=int(row.page),
                snippet=" ".join(row.snip.split()),
            )
        )
    return hits


def _title_from(filename: str | None) -> str | None:
    if not filename:
        return None
    stem = filename.rsplit(".", 1)[0]
    return re.sub(r"[_-]+", " ", stem).strip() or None


# --- Home Assistant appliances ------------------------------------------------

FINISH_DEDUPE = timedelta(minutes=10)  # an event and a state change often report the same run
LAUNDRY_PROMPT = "laundry_prompt"
VACUUM_COMMANDS = ("start", "pause", "stop", "return_to_base", "locate", "clean_spot")


async def set_live(session: AsyncSession, hub: EventHub, equipment_id: int, live: LiveIn) -> None:
    item = await get_equipment(session, equipment_id)
    data = live.model_dump()
    if data != item.live:
        item.live, item.live_at = data, utcnow()
        await session.commit()
        hub.publish("equipment", equipment_id=item.id)


async def finished(session: AsyncSession, hub: EventHub, equipment_id: int, data: FinishedIn) -> dict[str, Any]:
    """An appliance finished a run: log it, then complete or schedule its chores and handle the laundry."""
    item = await get_equipment(session, equipment_id)
    now = utcnow()
    if item.last_run_at and now - as_utc(item.last_run_at) < FINISH_DEDUPE:
        return {"counted": False}
    session.add(EquipmentRun(equipment_id=item.id, finished_at=now, source=data.source, detail=data.detail))
    item.run_count += 1
    item.last_run_at = now
    rules = item.automation_effective
    result: dict[str, Any] = {"counted": True, "chores_done": [], "chores_due": [], "laundry": None}
    await session.commit()
    for chore_id in item.chore_ids:
        if rules["chores"] == "complete":
            done = await chores.execute(session, hub, chore_id, source="appliance", at=now)
            result["chores_done"].append(done.name)
        elif rules["chores"] == "make_due":
            await chores.make_due(session, hub, chore_id, now)
            chore = await session.get(Chore, chore_id)
            if chore is not None:
                result["chores_due"].append(chore.name)
    from . import wardrobe

    in_laundry = await session.scalar(
        select(func.count()).select_from(Garment).where(Garment.state.in_(("laundry", "washing")))
    )
    if item.kind == "dryer" and rules["laundry"] == "auto":
        result["laundry"] = "dried" if await wardrobe.dried(session, hub) else None
    elif in_laundry and rules["laundry"] == "auto" and item.kind == "washer":
        await wardrobe.washed(session, hub)
        result["laundry"] = "washed"
    elif in_laundry and rules["laundry"] == "ask" and item.kind == "washer":
        await settings_store.put(session, hub, LAUNDRY_PROMPT,
                                 {"equipment_id": item.id, "name": item.name, "at": now.isoformat(), "pieces": in_laundry})  # fmt: skip
        result["laundry"] = "asked"
    await session.commit()
    hub.publish("equipment", equipment_id=item.id)
    return result


async def started(session: AsyncSession, hub: EventHub, equipment_id: int) -> dict[str, Any]:
    """An appliance started a run. For a washer on "auto", the laundry bin is assumed to be in it."""
    item = await get_equipment(session, equipment_id)
    rules = item.automation_effective
    if item.kind == "washer" and rules["laundry"] == "auto":
        from . import wardrobe

        return {"washing": await wardrobe.start_wash(session, hub)}
    return {}


async def runs(session: AsyncSession, equipment_id: int, limit: int = 20) -> list[EquipmentRun]:
    query = (
        select(EquipmentRun).where(EquipmentRun.equipment_id == equipment_id).order_by(EquipmentRun.id.desc()).limit(limit)
    )
    return list((await session.scalars(query)).all())


async def command(session: AsyncSession, bridge: HABridge, equipment_id: int, name: str) -> dict[str, Any]:
    """Run a vacuum action on the appliance's own vacuum entity in HA (the integration checks the link too)."""
    item = await get_equipment(session, equipment_id)
    if name not in VACUUM_COMMANDS:
        raise Invalid(f"command must be one of: {', '.join(VACUUM_COMMANDS)}")
    if not item.ha_device_id and not item.ha_entities:
        raise Invalid(f"{item.name} is not linked to a Home Assistant device")
    return await bridge.request("appliance_command", timeout=30, equipment_id=item.id, command=name,
                                device_id=item.ha_device_id, entities=item.ha_entities)  # fmt: skip


async def ha_devices(bridge: HABridge, query: str | None = None) -> list[dict[str, Any]]:
    """HA's devices (with their entities) to link equipment to."""
    devices = await bridge.request("devices", timeout=30)
    if query:
        wanted = query.casefold()
        devices = [
            d for d in devices
            if wanted in " ".join(filter(None, (d.get("name"), d.get("manufacturer"), d.get("model"), d.get("area")))).casefold()
        ]  # fmt: skip
    return devices
