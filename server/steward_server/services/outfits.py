"""Outfit suggestions: rules build a shortlist and safe outfits; an AI (if set up) picks with taste.

1. Context: the day's weather (feels-like range, rain, wind), the occasion and the style profile.
2. Rules: only available pieces; warmth, rain protection and formality must fit; recently worn
   pieces, disliked things and badly rated pieces sink.
3. AI: chooses up to three outfits from the shortlist, looking at a contact sheet of the photos.
4. Check: every outfit goes through the rules again and is repaired if a required piece is missing.
"""

from __future__ import annotations

import asyncio
import io
import itertools
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..ha_bridge import HABridge
from ..models import Garment, Outfit, StoredFile, StyleProfile
from ..timeutil import today
from . import Invalid, ServiceError
from . import ai, wardrobe
from . import weather as weather_service
from .files import FileStore

LOG = logging.getLogger("steward.outfits")

OCCASIONS = ("home", "comfort", "going_out", "work", "sport", "formal")
FORMALITY = {"home": 1, "comfort": 2, "sport": 1, "going_out": 3, "work": 3, "formal": 5}
NEUTRALS = {"black", "white", "grey", "navy", "beige", "brown", "olive"}
AVAILABLE = ("clean", "worn")
SHORTLIST = 6  # pieces per slot shown to the AI
SLOTS = ("base", "bottom", "full", "mid", "outer", "shoes", "accessory")


@dataclass
class Context:
    day: date
    occasion: str
    weather: dict[str, Any]
    profile: StyleProfile
    ratings: dict[int, float] = field(default_factory=dict)

    @property
    def shift(self) -> float:
        # Someone who is always cold experiences the day colder than the thermometer says.
        return self.profile.runs_warm * 1.5

    @property
    def cold(self) -> float:
        return self.weather["feels_min"] + self.shift

    @property
    def mean(self) -> float:
        return (self.weather["feels_min"] + self.weather["feels_max"]) / 2 + self.shift

    @property
    def rainy(self) -> bool:
        return self.weather.get("rain_probability", 0) >= 50

    @property
    def windy(self) -> bool:
        return self.weather.get("wind_max", 0) >= 30

    @property
    def season(self) -> str:
        return "summer" if self.mean >= 20 else "winter" if self.mean < 8 else "transition"

    def needs(self) -> dict[str, bool]:
        return {
            "mid": self.mean < 15 and self.occasion != "sport",
            "outer": self.cold < 15 or self.weather.get("rain_probability", 0) >= 40 or self.windy,
            "warm_accessories": self.cold < 6,
        }


# --- scoring --------------------------------------------------------------


def score(garment: Garment, ctx: Context) -> float:
    s = 0.0
    reference = {"outer": ctx.cold, "accessory": ctx.cold}.get(garment.layer, ctx.mean)
    if garment.temp_min is not None and garment.temp_max is not None:
        if reference < garment.temp_min:
            s -= (garment.temp_min - reference) * 0.6
        elif reference > garment.temp_max:
            s -= (reference - garment.temp_max) * 0.6
    else:
        ideal = min(5.0, max(1.0, 1 + (24 - reference) / 7))
        s -= abs(garment.warmth - ideal) * 1.2
    if garment.uses:
        s += 2 if ctx.occasion in garment.uses else -1.5
    s -= abs(garment.formality - FORMALITY[ctx.occasion]) * 0.7
    if ctx.rainy and garment.layer in ("outer", "shoes"):
        s += {"waterproof": 3, "resistant": 1.5}.get(garment.rain, -2)
    if ctx.windy and garment.layer == "outer" and garment.windproof:
        s += 1
    if garment.seasons and ctx.season not in garment.seasons:
        s -= 1
    if garment.last_worn and (ctx.day - garment.last_worn).days <= 1 and garment.layer not in ("outer", "shoes"):
        s -= 1.5
    if garment.favorite:
        s += 0.5
    s += ctx.ratings.get(garment.id, 0) * 0.4
    words = " ".join([garment.name, garment.category, garment.material or "", *garment.colors]).lower()
    s += sum(1 for like in ctx.profile.likes if like.lower() in words)
    s -= sum(2.5 for dislike in ctx.profile.dislikes if dislike.lower() in words)
    return s


def harmony(pieces: list[Garment]) -> float:
    colors = {c for g in pieces for c in g.colors[:1]}
    loud = colors - NEUTRALS
    patterned = sum(1 for g in pieces if g.pattern not in (None, "solid", "denim", "melange"))
    return -max(0, len(loud) - 1) * 1.5 - max(0, patterned - 1) * 1.5


def available(garments: list[Garment]) -> list[Garment]:
    return [g for g in garments if g.state in AVAILABLE]


def by_slot(garments: list[Garment], ctx: Context) -> dict[str, list[Garment]]:
    slots: dict[str, list[Garment]] = {slot: [] for slot in SLOTS}
    for garment in available(garments):
        if garment.layer == "accessory" and garment.warmth < 3 and garment.category not in ("belt",):
            continue
        slots.setdefault(garment.layer, []).append(garment)
    for pieces in slots.values():
        pieces.sort(key=lambda g: score(g, ctx), reverse=True)
    return slots


def rules_outfits(garments: list[Garment], ctx: Context, count: int = 3) -> list[list[Garment]]:
    """The best few complete outfits by score, each different in at least one main piece."""
    slots = by_slot(garments, ctx)
    needs = ctx.needs()
    cores: list[tuple[Garment, ...]] = [(b, p) for b in slots["base"][:3] for p in slots["bottom"][:3]]
    cores += [(f,) for f in slots["full"][:2]]
    if not cores or not slots["shoes"]:
        missing = "shoes" if cores else "a top and a bottom"
        raise Invalid(f"Not enough clean clothes for an outfit: {missing} missing")
    options = [cores, slots["shoes"][:3]]
    if needs["mid"] and slots["mid"]:
        options.append(slots["mid"][:3])
    if needs["outer"] and slots["outer"]:
        options.append(slots["outer"][:3])
    warm = [g for g in slots["accessory"] if g.warmth >= 3] if needs["warm_accessories"] else []

    ranked = []
    for combo in itertools.product(*options):
        pieces = [g for part in combo for g in (part if isinstance(part, tuple) else (part,))]
        pieces += _accessories(warm)
        ranked.append((sum(score(g, ctx) for g in pieces) + harmony(pieces), pieces))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen: list[list[Garment]] = []
    # Prefer outfits that differ in at least two main pieces; settle for one when the closet is small.
    for min_difference in (2, 1):
        for _, pieces in ranked:
            if len(chosen) == count:
                return chosen
            main = _main(pieces)
            if all(len(main ^ _main(other)) >= 2 * min_difference for other in chosen):
                chosen.append(pieces)
    return chosen


def _main(pieces: list[Garment]) -> set[int]:
    return {g.id for g in pieces if g.layer in ("base", "bottom", "full", "mid", "outer")}


def _accessories(warm: list[Garment]) -> list[Garment]:
    """At most one of each kind (scarf, hat, gloves)."""
    picked: dict[str, Garment] = {}
    for garment in warm:
        picked.setdefault(garment.category, garment)
    return list(picked.values())


def repair(ids: list[int], garments: list[Garment], ctx: Context) -> tuple[list[Garment], list[str]]:
    """Check an outfit against the rules; fill what's missing from the best rule choices."""
    usable = {g.id: g for g in available(garments)}
    pieces, notes, seen_layers = [], [], set()
    for garment_id in dict.fromkeys(ids):
        garment = usable.get(garment_id)
        if garment is None:
            notes.append(f"dropped unavailable piece {garment_id}")
            continue
        if garment.layer in seen_layers and garment.layer != "accessory":
            notes.append(f"dropped a second {garment.layer}")
            continue
        seen_layers.add(garment.layer)
        pieces.append(garment)
    slots = by_slot(garments, ctx)
    needs = ctx.needs()
    required = ["shoes"] + (["full"] if "full" in seen_layers else ["base", "bottom"])
    if needs["outer"]:
        required.append("outer")
    for layer in required:
        if layer not in seen_layers and slots.get(layer):
            pieces.append(slots[layer][0])
            seen_layers.add(layer)
            notes.append(f"added {slots[layer][0].name}")
    if ctx.rainy:
        outer = next((g for g in pieces if g.layer == "outer"), None)
        dry = [g for g in slots["outer"] if g.rain != "none"]
        if outer is not None and outer.rain == "none" and dry:
            pieces[pieces.index(outer)] = dry[0]
            notes.append(f"swapped in {dry[0].name} for the rain")
    return pieces, notes


# --- suggestions ----------------------------------------------------------


async def suggest(
    session: AsyncSession,
    hub: EventHub,
    bridge: HABridge,
    files: FileStore,
    *,
    owner: str | None = None,
    day: date | None = None,
    occasion: str = "comfort",
    count: int = 3,
    use_ai: bool = True,
    weather: dict[str, Any] | None = None,
    lang: str = "en",
) -> list[Outfit]:
    if occasion not in OCCASIONS:
        raise Invalid(f"occasion must be one of: {', '.join(OCCASIONS)}")
    day = day or today()
    if weather is None:
        weather = await weather_service.for_day(session, bridge, day)
    profile = await wardrobe.get_profile(session, owner)
    garments = await wardrobe.list_garments(session, owner)
    ctx = Context(day=day, occasion=occasion, weather=weather, profile=profile, ratings=await _ratings(session, owner))

    fallback = rules_outfits(garments, ctx, count)
    picks: list[tuple[list[Garment], str, str]] = []
    if use_ai and await ai.available(session, bridge, "outfits"):
        try:
            picks = await _ai_outfits(session, bridge, files, garments, ctx, count, lang)
        except ServiceError as err:
            LOG.warning("AI outfit suggestion failed, using rules: %s", err)
    if not picks:
        picks = [(pieces, rules_reason(pieces, ctx, lang), "rules") for pieces in fallback]

    # A new round replaces earlier untouched suggestions for that day.
    await session.execute(
        delete(Outfit).where(
            Outfit.day == day, Outfit.owner.is_(owner) if owner is None else Outfit.owner == owner,
            Outfit.source != "manual", Outfit.worn.is_(False), Outfit.rating == 0,
        )
    )  # fmt: skip
    outfits = []
    for pieces, reason, source in picks[:count]:
        outfit = Outfit(
            owner=owner, day=day, garment_ids=[g.id for g in _ordered(pieces)], source=source,
            occasion=occasion, weather=weather, reason=reason,
        )  # fmt: skip
        session.add(outfit)
        outfits.append(outfit)
    await session.commit()
    hub.publish("wardrobe")
    return outfits


async def _ratings(session: AsyncSession, owner: str | None) -> dict[int, float]:
    """Thumbs up or down on past outfits rub off on their pieces."""
    rated = (
        await session.scalars(select(Outfit).where(Outfit.rating != 0).order_by(Outfit.id.desc()).limit(60))
    ).all()
    totals: dict[int, float] = {}
    for outfit in rated:
        if owner is not None and outfit.owner not in (owner, None):
            continue
        for garment_id in outfit.garment_ids:
            totals[garment_id] = totals.get(garment_id, 0) + outfit.rating
    return totals


def _ordered(pieces: list[Garment]) -> list[Garment]:
    order = {layer: i for i, layer in enumerate(("outer", "mid", "base", "full", "bottom", "shoes", "accessory"))}
    return sorted(pieces, key=lambda g: order.get(g.layer, 99))


def rules_reason(pieces: list[Garment], ctx: Context, lang: str = "en") -> str:
    w = ctx.weather
    de = lang.startswith("de")
    parts = [f"{w['temp_min']:.0f}–{w['temp_max']:.0f} °C" + (f", gefühlt {w['feels_min']:.0f} °C" if de else f", feels like {w['feels_min']:.0f} °C")]
    if w.get("rain_probability", 0) >= 40:
        when = f" ab {w['rain_from']}" if de and w.get("rain_from") else f" from {w['rain_from']}" if w.get("rain_from") else ""
        parts.append(f"{w['rain_probability']} % Regen{when}" if de else f"{w['rain_probability']} % rain{when}")
    outer = next((g for g in pieces if g.layer == "outer"), None)
    mid = next((g for g in pieces if g.layer == "mid"), None)
    if ctx.rainy and outer is not None and outer.rain != "none":
        choice = f"daher {outer.name}" if de else f"so the {outer.name}"
    elif outer is not None:
        choice = f"{outer.name} für draußen" if de else f"{outer.name} for outside"
    elif mid is not None:
        choice = f"{mid.name} als warme Schicht" if de else f"{mid.name} as the warm layer"
    else:
        choice = "leicht angezogen" if de else "light and comfortable"
    return ", ".join(parts) + ": " + choice + "."


async def _ai_outfits(
    session: AsyncSession,
    bridge: HABridge,
    files: FileStore,
    garments: list[Garment],
    ctx: Context,
    count: int,
    lang: str,
) -> list[tuple[list[Garment], str, str]]:
    slots = by_slot(garments, ctx)
    shortlist = [g for pieces in slots.values() for g in pieces[:SHORTLIST]]
    needs = ctx.needs()
    recent = (await session.scalars(select(Outfit).where(Outfit.worn.is_(True)).order_by(Outfit.day.desc()).limit(3))).all()
    feedback = (
        await session.scalars(
            select(Outfit).where(Outfit.rating != 0, Outfit.feedback.is_not(None)).order_by(Outfit.id.desc()).limit(8)
        )
    ).all()
    names = {g.id: g.name for g in garments}
    lines = [
        f"{g.id} | {g.name} | {g.category} ({g.layer}) | {', '.join(g.colors) or '?'} | {g.pattern or 'solid'} | "
        f"warmth {g.warmth}/5 | {_range(g)} | rain: {g.rain} | formality {g.formality}/5 | "
        f"{', '.join(g.uses) or 'any use'}{' | favorite' if g.favorite else ''}"
        for g in shortlist
    ]
    w = ctx.weather
    language = "German" if lang.startswith("de") else "English"
    instructions = "\n".join(
        [
            "You are a personal stylist. Put together outfits from the pieces listed below (and shown in the "
            "attached contact sheet, labeled with their ids). Use only these ids.",
            "",
            f"Day: {ctx.day.isoformat()} · occasion: {ctx.occasion.replace('_', ' ')}",
            f"Weather 7–22 h: {w['temp_min']}–{w['temp_max']} °C, feels like {w['feels_min']}–{w['feels_max']} °C, "
            f"rain chance {w.get('rain_probability', 0)} %" + (f" from {w['rain_from']}" if w.get("rain_from") else "")
            + f", wind up to {w.get('wind_max', 0)} km/h, {', '.join(w.get('conditions') or []) or 'no conditions given'}.",
            "Needed: a top (base) and a bottom, or a dress/jumpsuit (full); shoes"
            + ("; a mid layer" if needs["mid"] else "")
            + ("; an outer layer" + (" that keeps rain out" if ctx.rainy else "") if needs["outer"] else "")
            + ("; warm accessories" if needs["warm_accessories"] else "")
            + ".",
            f"This person runs {'warm' if ctx.profile.runs_warm > 0 else 'cold' if ctx.profile.runs_warm < 0 else 'neither warm nor cold'}.",
            f"Their taste: {ctx.profile.description or 'not described'}. Likes: {', '.join(ctx.profile.likes) or '-'}. "
            f"Dislikes: {', '.join(ctx.profile.dislikes) or '-'}.",
            "Recently worn (avoid repeating): "
            + ("; ".join(", ".join(names.get(i, '?') for i in o.garment_ids) for o in recent) or "-"),
            "Earlier feedback: "
            + ("; ".join(f"{'liked' if o.rating > 0 else 'disliked'} '{', '.join(names.get(i, '?') for i in o.garment_ids)}': {o.feedback}" for o in feedback) or "-"),
            "",
            "Pieces (id | name | category (layer) | colors | pattern | warmth | comfortable range | rain | formality | uses):",
            *lines,
            "",
            f"Return up to {count} different outfits, best first, with colors and styles that go together. "
            f"For each, one short sentence in {language} saying why it suits the day (mention the weather when it matters).",
        ]
    )
    schema = ai.obj(
        {
            "outfits": {
                "type": "array",
                "items": ai.obj(
                    {
                        "garment_ids": {"type": "array", "items": {"type": "integer"}},
                        "reason": {"type": "string"},
                    }
                ),
            }
        }
    )
    sheet = await asyncio.to_thread(contact_sheet, files, shortlist, await _files_for(session, shortlist))
    images = [ai.Image(sheet, "image/png")] if sheet else []
    result = await ai.generate(session, bridge, "outfits", ai.AIRequest("Steward outfit suggestion", instructions, schema, images))
    picks = []
    for item in result.get("outfits") or []:
        pieces, notes = repair([int(i) for i in item.get("garment_ids") or [] if str(i).lstrip("-").isdigit()], garments, ctx)
        if notes:
            LOG.info("Repaired AI outfit: %s", "; ".join(notes))
        if any(g.layer == "shoes" for g in pieces) and {g.id for g in pieces} not in [{g.id for g in p} for p, _, _ in picks]:
            picks.append((pieces, str(item.get("reason") or "").strip() or rules_reason(pieces, ctx, lang), "ai"))
    return picks


def _range(garment: Garment) -> str:
    if garment.temp_min is None or garment.temp_max is None:
        return "range unknown"
    return f"{garment.temp_min:.0f}–{garment.temp_max:.0f} °C"


async def _files_for(session: AsyncSession, garments: list[Garment]) -> dict[str, StoredFile]:
    ids = [g.photo_id for g in garments if g.photo_id]
    if not ids:
        return {}
    return {f.id: f for f in (await session.scalars(select(StoredFile).where(StoredFile.id.in_(ids)))).all()}


# --- pictures -------------------------------------------------------------


def contact_sheet(files: FileStore, garments: list[Garment], stored: dict[str, StoredFile]) -> bytes | None:
    """All shortlisted pieces in one image, each labeled with its id, so the AI sees colors and style."""
    from PIL import Image, ImageDraw

    pictured = [(g, stored[g.photo_id]) for g in garments if g.photo_id in stored]
    if not pictured:
        return None
    cell, columns = 200, 6
    rows = (len(pictured) + columns - 1) // columns
    sheet = Image.new("RGB", (cell * columns, cell * rows), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (garment, file) in enumerate(pictured):
        x, y = (index % columns) * cell, (index // columns) * cell
        _paste(sheet, files.thumb_path(file), x + 10, y + 26, cell - 20, cell - 36)
        draw.rectangle([x + 4, y + 4, x + 56, y + 24], fill=(20, 20, 20))
        draw.text((x + 10, y + 7), f"#{garment.id}", fill=(255, 255, 255))
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


async def outfit_image(session: AsyncSession, files: FileStore, outfit_id: int) -> bytes:
    """A collage of the outfit's pieces, for HA's image entity and notifications."""
    outfit = await wardrobe.get_outfit(session, outfit_id)
    garments = [g for g in [await session.get(Garment, i) for i in outfit.garment_ids] if g is not None]
    stored = await _files_for(session, garments)
    return await asyncio.to_thread(_collage, files, _ordered(garments), stored)


def _collage(files: FileStore, garments: list[Garment], stored: dict[str, StoredFile]) -> bytes:
    from PIL import Image, ImageDraw

    main = [g for g in garments if g.layer != "accessory"]
    extras = [g for g in garments if g.layer == "accessory"]
    cell = 360
    columns = 2 if len(main) > 1 else 1
    rows = max(1, (len(main) + columns - 1) // columns)
    width, height = cell * columns, cell * rows + (cell // 2 if extras else 0)
    canvas = Image.new("RGB", (width, height), (244, 244, 241))
    draw = ImageDraw.Draw(canvas)
    for index, garment in enumerate(main):
        x, y = (index % columns) * cell, (index // columns) * cell
        _tile(canvas, draw, files, garment, stored, x, y, cell)
    for index, garment in enumerate(extras):
        _tile(canvas, draw, files, garment, stored, index * cell // 2, rows * cell, cell // 2)
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


def _tile(canvas, draw, files: FileStore, garment: Garment, stored: dict[str, StoredFile], x: int, y: int, size: int) -> None:
    file = stored.get(garment.photo_id or "")
    if file is not None:
        _paste(canvas, files.thumb_path(file), x + 12, y + 12, size - 24, size - 24)
    else:
        draw.rounded_rectangle([x + 12, y + 12, x + size - 12, y + size - 12], radius=16, fill=(220, 220, 215))
        draw.text((x + 24, y + size // 2), garment.name, fill=(60, 60, 60))


def _paste(canvas, path: Path, x: int, y: int, width: int, height: int) -> None:
    from PIL import Image

    try:
        with Image.open(path) as picture:
            picture = picture.convert("RGBA")
            picture.thumbnail((width, height))
            offset = (x + (width - picture.width) // 2, y + (height - picture.height) // 2)
            canvas.paste(picture, offset, picture)
    except OSError:
        LOG.warning("Missing picture %s", path)


def outfit_brief(outfit: Outfit, garments: dict[int, Garment]) -> dict[str, Any]:
    return {
        "id": outfit.id,
        "day": outfit.day.isoformat(),
        "pieces": [garments[i].name for i in outfit.garment_ids if i in garments],
        "reason": outfit.reason,
        "worn": outfit.worn,
        "source": outfit.source,
    }


async def latest_for(session: AsyncSession, owner: str | None, day: date | None = None) -> Outfit | None:
    """Today's outfit for someone: the worn one, else the newest suggestion."""
    day = day or today()
    query = select(Outfit).where(Outfit.day == day).order_by(Outfit.worn.desc(), Outfit.id.desc())
    if owner is not None:
        query = query.where((Outfit.owner == owner) | Outfit.owner.is_(None))
    return (await session.scalars(query.limit(1))).first()

