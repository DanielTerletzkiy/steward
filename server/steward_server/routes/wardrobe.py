"""Wardrobe routes: clothes, wearing, laundry, outfits and style profiles."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..api import Bridge, Files, Hub, Session, require_auth
from ..schemas import (
    GarmentIn,
    GarmentOut,
    GarmentPatch,
    LaundryIn,
    OutfitFeedbackIn,
    OutfitIn,
    OutfitOut,
    StyleProfileIn,
    StyleProfileOut,
    WearIn,
)
from ..services import ai, outfits, wardrobe

router = APIRouter(prefix="/api/wardrobe", dependencies=[Depends(require_auth)])


class SuggestIn(BaseModel):
    owner: str | None = None
    day: date | None = None
    occasion: str = "comfort"
    count: int = 3
    use_ai: bool = True
    weather: dict | None = None  # skip the forecast lookup (tests, trips)
    lang: str = "en"


@router.get("/vocabulary")
async def vocabulary() -> dict:
    return wardrobe.vocabulary()


@router.get("/garments", response_model=list[GarmentOut])
async def list_garments(session: Session, owner: str | None = None):
    return await wardrobe.list_garments(session, owner)


@router.post("/garments", response_model=GarmentOut)
async def create_garment(session: Session, hub: Hub, body: GarmentIn):
    return await wardrobe.create_garment(session, hub, body)


@router.get("/garments/{garment_id}", response_model=GarmentOut)
async def get_garment(session: Session, garment_id: int):
    return await wardrobe.get_garment(session, garment_id)


@router.patch("/garments/{garment_id}", response_model=GarmentOut)
async def update_garment(session: Session, hub: Hub, garment_id: int, body: GarmentPatch):
    return await wardrobe.update_garment(session, hub, garment_id, body)


@router.delete("/garments/{garment_id}", status_code=204)
async def delete_garment(session: Session, hub: Hub, files: Files, garment_id: int) -> None:
    await wardrobe.delete_garment(session, hub, files, garment_id)


@router.put("/garments/{garment_id}/photo", response_model=GarmentOut)
async def set_photo(session: Session, hub: Hub, files: Files, garment_id: int, file: UploadFile = File(...)):
    return await wardrobe.set_photo(session, hub, files, garment_id, await file.read(), file.filename)


@router.delete("/garments/{garment_id}/photo", response_model=GarmentOut)
async def remove_photo(session: Session, hub: Hub, files: Files, garment_id: int):
    return await wardrobe.remove_photo(session, hub, files, garment_id)


@router.post("/wear", response_model=list[GarmentOut])
async def wear(session: Session, hub: Hub, body: WearIn):
    return await wardrobe.wear(session, hub, body.garment_ids, body.day)


@router.post("/laundry/done")
async def laundry_done(session: Session, hub: Hub, body: LaundryIn | None = None) -> dict:
    return {"washed": await wardrobe.laundry_done(session, hub, body.garment_ids if body else None)}


@router.post("/laundry/dismiss", status_code=204)
async def dismiss_laundry_prompt(session: Session, hub: Hub) -> None:
    await wardrobe.dismiss_laundry_prompt(session, hub)


@router.get("/outfits", response_model=list[OutfitOut])
async def list_outfits(session: Session, owner: str | None = None, day: date | None = None, limit: int = 50):
    return await wardrobe.list_outfits(session, owner, day, limit)


@router.post("/outfits", response_model=OutfitOut)
async def create_outfit(session: Session, hub: Hub, body: OutfitIn):
    return await wardrobe.create_outfit(session, hub, body)


@router.post("/outfits/{outfit_id}/wear", response_model=OutfitOut)
async def wear_outfit(session: Session, hub: Hub, outfit_id: int):
    return await wardrobe.wear_outfit(session, hub, outfit_id)


@router.post("/outfits/{outfit_id}/feedback", response_model=OutfitOut)
async def outfit_feedback(session: Session, hub: Hub, outfit_id: int, body: OutfitFeedbackIn):
    return await wardrobe.outfit_feedback(session, hub, outfit_id, body)


@router.delete("/outfits/{outfit_id}", status_code=204)
async def delete_outfit(session: Session, hub: Hub, outfit_id: int) -> None:
    await wardrobe.delete_outfit(session, hub, outfit_id)


@router.post("/suggest", response_model=list[OutfitOut])
async def suggest(session: Session, hub: Hub, bridge: Bridge, files: Files, body: SuggestIn):
    return await outfits.suggest(
        session, hub, bridge, files, owner=body.owner, day=body.day, occasion=body.occasion,
        count=max(1, min(body.count, 5)), use_ai=body.use_ai, weather=body.weather, lang=body.lang,
    )  # fmt: skip


@router.get("/outfits/{outfit_id}/image", include_in_schema=False)
async def outfit_image(session: Session, files: Files, outfit_id: int) -> Response:
    return Response(await outfits.outfit_image(session, files, outfit_id), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})  # fmt: skip


@router.post("/analyze")
async def analyze(session: Session, bridge: Bridge, files: list[UploadFile] = File(...)) -> dict:
    images = [ai.Image(await f.read(), f.content_type or "image/jpeg") for f in files]
    return await wardrobe.analyze_photo(session, bridge, images)


@router.get("/profile", response_model=StyleProfileOut)
async def get_profile(session: Session, owner: str | None = None):
    return await wardrobe.get_profile(session, owner)


@router.put("/profile", response_model=StyleProfileOut)
async def set_profile(session: Session, hub: Hub, body: StyleProfileIn, owner: str | None = None):
    return await wardrobe.set_profile(session, hub, owner, body)
