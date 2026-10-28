"""Wardrobe: clothes with photos and qualities, wear and laundry tracking, outfits, style profiles."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Garment, Outfit, StyleProfile
from ..schemas import GarmentIn, GarmentPatch, OutfitFeedbackIn, OutfitIn, StyleProfileIn
from ..timeutil import today
from ..ha_bridge import HABridge
from . import Invalid, NotFound, ai
from . import settings as settings_store
from .files import FileStore

LAYERS = ("base", "mid", "outer", "bottom", "full", "shoes", "accessory")
LAYER_ORDER = {layer: i for i, layer in enumerate(("outer", "mid", "base", "full", "bottom", "shoes", "accessory"))}
STATES = ("clean", "worn", "laundry", "repair", "lent", "stored")
RAIN = ("none", "resistant", "waterproof")
USES = ("home", "comfort", "going_out", "work", "sport", "formal")
SEASONS = ("summer", "transition", "winter")
PATTERNS = ("solid", "striped", "checked", "printed", "floral", "denim", "melange")
COLORS = (
    "black", "white", "grey", "navy", "blue", "light blue", "beige", "brown", "olive", "green",
    "red", "burgundy", "pink", "purple", "yellow", "orange",
)  # fmt: skip

# category: (layer, wears before washing; 0 = never goes to the laundry automatically)
CATEGORIES: dict[str, tuple[str, int]] = {
    "t-shirt": ("base", 1),
    "long-sleeve": ("base", 1),
    "shirt": ("base", 2),
    "blouse": ("base", 2),
    "polo": ("base", 2),
    "top": ("base", 1),
    "sweater": ("mid", 4),
    "hoodie": ("mid", 4),
    "cardigan": ("mid", 4),
    "fleece": ("mid", 5),
    "vest": ("mid", 5),
    "jacket": ("outer", 20),
    "rain jacket": ("outer", 20),
    "coat": ("outer", 30),
    "blazer": ("outer", 10),
    "jeans": ("bottom", 6),
    "trousers": ("bottom", 4),
    "chinos": ("bottom", 4),
    "shorts": ("bottom", 3),
    "skirt": ("bottom", 3),
    "joggers": ("bottom", 3),
    "leggings": ("bottom", 2),
    "dress": ("full", 2),
    "jumpsuit": ("full", 2),
    "sneakers": ("shoes", 0),
    "boots": ("shoes", 0),
    "shoes": ("shoes", 0),
    "sandals": ("shoes", 0),
    "scarf": ("accessory", 10),
    "hat": ("accessory", 10),
    "cap": ("accessory", 10),
    "gloves": ("accessory", 10),
    "belt": ("accessory", 0),
}


def vocabulary() -> dict:
    """The fixed values the UI, the AI tagger and the outfit engine share."""
    return {
        "categories": [{"name": name, "layer": layer, "wears_per_wash": wears} for name, (layer, wears) in CATEGORIES.items()],
        "layers": list(LAYERS),
        "states": list(STATES),
        "rain": list(RAIN),
        "uses": list(USES),
        "seasons": list(SEASONS),
        "patterns": list(PATTERNS),
        "colors": list(COLORS),
    }


def _check(values: dict) -> None:
    for key, allowed in (("layer", LAYERS), ("state", STATES), ("rain", RAIN)):
        if values.get(key) is not None and values[key] not in allowed:
            raise Invalid(f"{key} must be one of: {', '.join(allowed)}")
    for key, allowed in (("uses", USES), ("seasons", SEASONS)):
        unknown = set(values.get(key) or []) - set(allowed)
        if unknown:
            raise Invalid(f"Unknown {key}: {', '.join(sorted(unknown))}")


# --- garments -------------------------------------------------------------


async def list_garments(session: AsyncSession, owner: str | None = None) -> list[Garment]:
    query = select(Garment)
    if owner is not None:
        # Unowned pieces belong to the whole household.
        query = query.where((Garment.owner == owner) | Garment.owner.is_(None))
    garments = (await session.scalars(query)).all()
    return sorted(garments, key=lambda g: (LAYER_ORDER.get(g.layer, 99), g.category, g.name.casefold()))


async def get_garment(session: AsyncSession, garment_id: int) -> Garment:
    garment = await session.get(Garment, garment_id)
    if garment is None:
        raise NotFound(f"Garment {garment_id} not found")
    return garment


async def create_garment(session: AsyncSession, hub: EventHub, data: GarmentIn) -> Garment:
    values = data.model_dump()
    category = values["category"] = values["category"].strip().lower()
    layer, wears = CATEGORIES.get(category, ("base", 1))
    values["layer"] = values["layer"] or layer
    values["wears_per_wash"] = wears if values["wears_per_wash"] is None else values["wears_per_wash"]
    _check(values)
    garment = Garment(**values)
    session.add(garment)
    await session.commit()
    hub.publish("wardrobe")
    return garment


async def update_garment(session: AsyncSession, hub: EventHub, garment_id: int, patch: GarmentPatch) -> Garment:
    garment = await get_garment(session, garment_id)
    values = patch.model_dump(exclude_unset=True)
    if "category" in values and values["category"]:
        values["category"] = values["category"].strip().lower()
        if "layer" not in values and values["category"] in CATEGORIES:
            values["layer"] = CATEGORIES[values["category"]][0]
    _check(values)
    if values.get("state") == "clean" and "wears_since_wash" not in values:
        values["wears_since_wash"] = 0
    for key, value in values.items():
        setattr(garment, key, value)
    await session.commit()
    hub.publish("wardrobe")
    return garment


async def delete_garment(session: AsyncSession, hub: EventHub, files: FileStore, garment_id: int) -> None:
    garment = await get_garment(session, garment_id)
    photo = garment.photo_id
    await session.delete(garment)
    await files.delete(session, photo)
    await session.commit()
    hub.publish("wardrobe")


async def set_photo(
    session: AsyncSession, hub: EventHub, files: FileStore, garment_id: int, data: bytes, filename: str | None
) -> Garment:
    garment = await get_garment(session, garment_id)
    stored = await files.save(session, data, filename=filename, content_type="image/*", kind="photo", cutout=True)
    old, garment.photo_id = garment.photo_id, stored.id
    await files.delete(session, old)
    await session.commit()
    hub.publish("wardrobe")
    return garment


async def remove_photo(session: AsyncSession, hub: EventHub, files: FileStore, garment_id: int) -> Garment:
    garment = await get_garment(session, garment_id)
    old, garment.photo_id = garment.photo_id, None
    await files.delete(session, old)
    await session.commit()
    hub.publish("wardrobe")
    return garment


# --- wearing and laundry --------------------------------------------------


async def wear(session: AsyncSession, hub: EventHub, garment_ids: list[int], day: date | None = None) -> list[Garment]:
    """Log one wear per piece. Pieces that reach their wears-per-wash go to the laundry."""
    day = day or today()
    garments = []
    for garment_id in dict.fromkeys(garment_ids):
        garment = await get_garment(session, garment_id)
        garment.wear_count += 1
        garment.wears_since_wash += 1
        garment.last_worn = max(garment.last_worn or day, day)
        if garment.state in ("clean", "worn"):
            due = garment.wears_per_wash and garment.wears_since_wash >= garment.wears_per_wash
            garment.state = "laundry" if due else "worn"
        garments.append(garment)
    await session.commit()
    hub.publish("wardrobe")
    return garments


async def laundry_done(session: AsyncSession, hub: EventHub, garment_ids: list[int] | None = None) -> int:
    """Mark pieces as washed: everything in the laundry, or the given pieces."""
    query = select(Garment)
    query = query.where(Garment.id.in_(garment_ids)) if garment_ids else query.where(Garment.state == "laundry")
    garments = (await session.scalars(query)).all()
    for garment in garments:
        garment.state = "clean"
        garment.wears_since_wash = 0
    await settings_store.put(session, None, "laundry_prompt", None)
    await session.commit()
    hub.publish("wardrobe")
    return len(garments)


async def dismiss_laundry_prompt(session: AsyncSession, hub: EventHub) -> None:
    await settings_store.put(session, hub, "laundry_prompt", None)
    hub.publish("wardrobe")


# --- outfits --------------------------------------------------------------


async def list_outfits(
    session: AsyncSession, owner: str | None = None, day: date | None = None, limit: int = 50
) -> list[Outfit]:
    query = select(Outfit).order_by(Outfit.day.desc(), Outfit.id.desc()).limit(limit)
    if owner is not None:
        query = query.where(Outfit.owner == owner)
    if day is not None:
        query = query.where(Outfit.day == day)
    return list((await session.scalars(query)).all())


async def get_outfit(session: AsyncSession, outfit_id: int) -> Outfit:
    outfit = await session.get(Outfit, outfit_id)
    if outfit is None:
        raise NotFound(f"Outfit {outfit_id} not found")
    return outfit


async def create_outfit(session: AsyncSession, hub: EventHub, data: OutfitIn) -> Outfit:
    if not data.garment_ids:
        raise Invalid("An outfit needs at least one piece")
    for garment_id in data.garment_ids:
        await get_garment(session, garment_id)
    outfit = Outfit(
        owner=data.owner, day=data.day or today(), garment_ids=data.garment_ids, source="manual", occasion=data.occasion
    )
    session.add(outfit)
    await session.commit()
    if data.worn:
        return await wear_outfit(session, hub, outfit.id)
    hub.publish("wardrobe")
    return outfit


async def wear_outfit(session: AsyncSession, hub: EventHub, outfit_id: int) -> Outfit:
    outfit = await get_outfit(session, outfit_id)
    if not outfit.worn:
        outfit.worn = True
        await wear(session, hub, outfit.garment_ids, outfit.day)
    return outfit


async def outfit_feedback(session: AsyncSession, hub: EventHub, outfit_id: int, data: OutfitFeedbackIn) -> Outfit:
    outfit = await get_outfit(session, outfit_id)
    outfit.rating = data.rating
    outfit.feedback = data.feedback
    await session.commit()
    hub.publish("wardrobe")
    return outfit


async def delete_outfit(session: AsyncSession, hub: EventHub, outfit_id: int) -> None:
    await session.delete(await get_outfit(session, outfit_id))
    await session.commit()
    hub.publish("wardrobe")


# --- style profile --------------------------------------------------------


async def get_profile(session: AsyncSession, owner: str | None) -> StyleProfile:
    return await session.get(StyleProfile, owner or "") or StyleProfile(
        owner=owner or "", description=None, likes=[], dislikes=[], runs_warm=0
    )


async def set_profile(session: AsyncSession, hub: EventHub, owner: str | None, data: StyleProfileIn) -> StyleProfile:
    profile = await session.get(StyleProfile, owner or "")
    if profile is None:
        profile = StyleProfile(owner=owner or "")
        session.add(profile)
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    await session.commit()
    hub.publish("wardrobe")
    return profile


# --- AI tagging -----------------------------------------------------------


def _tag_schema() -> dict:
    return ai.obj(
        {
            "name": {"type": "string", "description": "Short name, e.g. 'Grey merino sweater'"},
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "colors": {"type": "array", "items": {"type": "string", "enum": list(COLORS)}, "description": "Main color first"},
            "pattern": {"type": "string", "enum": list(PATTERNS)},
            "material": {"type": "string", "description": "Main material if recognizable, else empty"},
            "warmth": {"type": "integer", "description": "1 (very light) to 5 (very warm)"},
            "temp_min": {"type": "number", "description": "Lowest comfortable feels-like temperature in °C"},
            "temp_max": {"type": "number", "description": "Highest comfortable feels-like temperature in °C"},
            "rain": {"type": "string", "enum": list(RAIN)},
            "windproof": {"type": "boolean"},
            "formality": {"type": "integer", "description": "1 (lounge) to 5 (formal)"},
            "uses": {"type": "array", "items": {"type": "string", "enum": list(USES)}},
            "seasons": {"type": "array", "items": {"type": "string", "enum": list(SEASONS)}},
            "brand": {"type": "string", "description": "Brand if a label is readable, else empty"},
        }
    )


async def analyze_photo(session: AsyncSession, bridge: HABridge, images: list[ai.Image]) -> dict:
    """Suggest a garment's details from a photo (and optionally its care label); the user confirms."""
    if not images:
        raise Invalid("Add a photo")
    instructions = (
        "Describe this piece of clothing for a wardrobe app. The first photo shows the piece; a second photo, "
        "if any, shows its care label. Judge warmth and the comfortable temperature range from the material "
        "and thickness, rain protection from the fabric (only 'waterproof' for real rain gear), formality from "
        "the style, and the uses it suits: home (around the house), comfort (relaxed everyday), going_out, "
        "work, sport, formal."
    )
    result = await ai.generate(session, bridge, "wardrobe", ai.AIRequest("Steward clothing tags", instructions, _tag_schema(), images))
    category = result.get("category") if result.get("category") in CATEGORIES else None
    layer, wears = CATEGORIES.get(category or "", (None, None))
    clamp = lambda v, lo, hi, default: min(hi, max(lo, int(v))) if isinstance(v, (int, float)) else default  # noqa: E731
    return {
        "name": result.get("name") or None,
        "category": category,
        "layer": layer,
        "wears_per_wash": wears,
        "colors": [c for c in result.get("colors") or [] if c in COLORS],
        "pattern": result.get("pattern") if result.get("pattern") in PATTERNS else None,
        "material": result.get("material") or None,
        "warmth": clamp(result.get("warmth"), 1, 5, 3),
        "temp_min": result.get("temp_min"),
        "temp_max": result.get("temp_max"),
        "rain": result.get("rain") if result.get("rain") in RAIN else "none",
        "windproof": bool(result.get("windproof")),
        "formality": clamp(result.get("formality"), 1, 5, 2),
        "uses": [u for u in result.get("uses") or [] if u in USES],
        "seasons": [s for s in result.get("seasons") or [] if s in SEASONS],
        "brand": result.get("brand") or None,
    }
