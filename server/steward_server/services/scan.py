"""Scanning: barcodes (local, then Open Food Facts), GS1 codes with dates, and AI photo recognition."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

import httpx
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import __version__
from ..events import EventHub
from ..ha_bridge import HABridge
from ..models import Barcode, BarcodeLookup, Product
from ..schemas import ShoppingItemIn
from ..timeutil import as_utc, today, utcnow
from . import Invalid, NotFound, ai, catalog, shopping, stock

LOG = logging.getLogger("steward.scan")

MODES = ("purchase", "consume", "open", "spoil", "shopping", "lookup")
LOOKUP_TTL = timedelta(days=30)
OFF_FIELDS = "product_name,product_name_en,product_name_de,brands,quantity,categories_tags,image_front_small_url,image_front_url"
OFF_SITES = ("https://world.openfoodfacts.org", "https://world.openproductsfacts.org")
MATCH_THRESHOLD = 75

# Open Food Facts category tags → our categories and the storage place they usually go to.
CATEGORY_HINTS: list[tuple[str, str, str]] = [
    ("frozen", "Frozen", "freezer"), ("ice-cream", "Frozen", "freezer"),
    ("dairies", "Dairy", "fridge"), ("milks", "Dairy", "fridge"), ("cheeses", "Dairy", "fridge"),
    ("yogurts", "Dairy", "fridge"), ("eggs", "Dairy", "fridge"), ("meats", "Meat & fish", "fridge"),
    ("fishes", "Meat & fish", "fridge"), ("sausages", "Deli", "fridge"), ("fresh-vegetables", "Fruit & vegetables", "fridge"),
    ("fruits", "Fruit & vegetables", "pantry"), ("vegetables", "Fruit & vegetables", "pantry"),
    ("breads", "Bakery", "pantry"), ("pastas", "Pasta & rice", "pantry"), ("rices", "Pasta & rice", "pantry"),
    ("beverages", "Drinks", "drinks"), ("waters", "Drinks", "drinks"), ("sodas", "Drinks", "drinks"),
    ("coffees", "Coffee & tea", "pantry"), ("teas", "Coffee & tea", "pantry"), ("snacks", "Sweets & snacks", "pantry"),
    ("chocolates", "Sweets & snacks", "pantry"), ("biscuits", "Sweets & snacks", "pantry"),
    ("sauces", "Sauces & seasoning", "pantry"), ("condiments", "Sauces & seasoning", "pantry"),
]  # fmt: skip
STORAGE_WORDS = {
    "fridge": ("fridge", "kühlschrank", "kuehlschrank"),
    "freezer": ("freezer", "tiefkühl", "gefrier"),
    "pantry": ("pantry", "vorrat", "speisekammer", "cupboard", "schrank"),
    "drinks": ("drinks", "getränke", "getraenke"),
    "bathroom": ("bathroom", "bad"),
    "household": ("household", "haushalt"),
}


# --- barcodes -------------------------------------------------------------


def parse_code(raw: str) -> dict[str, Any]:
    """Split GS1 element strings ("(01)0400…(17)270331" or with FNC1/GS separators) into GTIN, expiry and lot."""
    text = raw.strip()
    result: dict[str, Any] = {"code": text, "gtin": None, "due_date": None, "lot": None}
    if text.startswith("(") or "\x1d" in text or (text.startswith("01") and len(text) > 16 and text[2:16].isdigit()):
        fields = _gs1_fields(text)
        if "01" in fields:
            gtin = fields["01"].lstrip("0") or "0"
            result["gtin"] = gtin.zfill(13) if len(gtin) <= 13 else gtin
            result["code"] = result["gtin"]
        for ai_code in ("17", "15", "16"):  # use by / best before / sell by
            if ai_code in fields and re.fullmatch(r"\d{6}", fields[ai_code]):
                result["due_date"] = _gs1_date(fields[ai_code])
                result["due_type"] = "use_by" if ai_code == "17" else "best_before"
                break
        result["lot"] = fields.get("10")
    return result


def _gs1_fields(text: str) -> dict[str, str]:
    if text.startswith("("):
        return dict(re.findall(r"\((\d{2,4})\)([^(]+)", text))
    fixed = {"01": 14, "11": 6, "15": 6, "16": 6, "17": 6}
    fields, rest = {}, text.replace("]d2", "").replace("]C1", "")
    while len(rest) >= 2:
        key = rest[:2]
        rest = rest[2:]
        if key in fixed:
            fields[key], rest = rest[: fixed[key]], rest[fixed[key] :]
        else:
            value, _, rest = rest.partition("\x1d")
            fields[key] = value
    return fields


def _gs1_date(value: str) -> str | None:
    year, month, day = 2000 + int(value[:2]), int(value[2:4]), int(value[4:])
    try:
        if day == 0:  # "00" means the end of the month
            return (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).isoformat()
        return date(year, month, day).isoformat()
    except ValueError:
        return None


async def lookup(session: AsyncSession, raw: str) -> dict[str, Any]:
    """What a scanned code is: one of our products, a suggestion from Open Food Facts, or unknown."""
    parsed = parse_code(raw)
    code = parsed["code"]
    if not code:
        raise Invalid("Empty code")
    product = await _product_for_code(session, code)
    barcode = await session.get(Barcode, code) if product else None
    result: dict[str, Any] = {
        **parsed,
        "product_id": product.id if product else None,
        "pack_amount": barcode.amount if barcode else None,  # how much one scan of this code is
        "suggestion": None,
    }
    if product is not None:
        result["source"] = "local"
        return result
    if code.isdigit() and len(code) in (8, 12, 13, 14):
        suggestion = await _open_food_facts(session, code)
        if suggestion is not None:
            suggestion["location_id"] = await _location_for(session, suggestion.pop("storage", None))
            existing = await _fuzzy_product(session, suggestion["name"])
            result.update(suggestion=suggestion, source="openfoodfacts")
            if existing is not None:
                result["similar_product_id"] = existing[0].id
            return result
    result["source"] = "none"
    return result


async def _product_for_code(session: AsyncSession, code: str) -> Product | None:
    candidates = {code, code.lstrip("0"), code.zfill(13), code.zfill(14)}
    barcode = (await session.scalars(select(Barcode).where(Barcode.code.in_(candidates)))).first()
    return await session.get(Product, barcode.product_id) if barcode else None


async def _open_food_facts(session: AsyncSession, code: str) -> dict[str, Any] | None:
    cached = await session.get(BarcodeLookup, code)
    if cached is not None and utcnow() - as_utc(cached.fetched_at) < LOOKUP_TTL:
        return dict(cached.data) if cached.found and cached.data else None
    found = None
    headers = {"User-Agent": f"Steward/{__version__} (Home Assistant household app)"}
    try:
        async with httpx.AsyncClient(timeout=8, headers=headers) as client:
            for site in OFF_SITES:
                response = await client.get(f"{site}/api/v2/product/{code}.json", params={"fields": OFF_FIELDS})
                if response.status_code == 200 and response.json().get("status") == 1:
                    found = _from_off(response.json()["product"], site)
                    break
    except httpx.HTTPError as err:
        LOG.info("Open Food Facts lookup for %s failed: %s", code, err)
        return None  # not cached: try again next time
    if cached is None:
        cached = BarcodeLookup(code=code)
        session.add(cached)
    cached.found, cached.data, cached.fetched_at = found is not None, found, utcnow()
    await session.commit()
    return dict(found) if found else None


def _from_off(product: dict[str, Any], site: str) -> dict[str, Any] | None:
    name = product.get("product_name_en") or product.get("product_name") or product.get("product_name_de")
    if not name:
        return None
    brand = (product.get("brands") or "").split(",")[0].strip() or None
    tags = product.get("categories_tags") or []
    category, storage = None, None
    for needle, our_category, place in CATEGORY_HINTS:
        if any(needle in tag for tag in tags):
            category, storage = our_category, place
            break
    quantity = (product.get("quantity") or "").strip()
    return {
        "name": f"{name} {quantity}".strip() if quantity and quantity not in name else name,
        "brand": brand,
        "category": category,
        "storage": storage,
        "image_url": product.get("image_front_url") or product.get("image_front_small_url"),
        "source_site": site,
    }


async def _location_for(session: AsyncSession, storage: str | None) -> int | None:
    if not storage:
        return None
    words = STORAGE_WORDS.get(storage.lower(), (storage.lower(),))
    for location in await catalog.list_locations(session):
        if any(word in location.name.lower() for word in words):
            return location.id
    return None


async def _fuzzy_product(session: AsyncSession, name: str) -> tuple[Product, float] | None:
    products = await catalog.list_products(session)
    if not products or not name:
        return None
    match = process.extractOne(name, {p.id: p.name for p in products}, scorer=fuzz.WRatio)
    if match is None or match[1] < MATCH_THRESHOLD:
        return None
    return next(p for p in products if p.id == match[2]), match[1]


async def add_barcode(session: AsyncSession, hub: EventHub, product_id: int, code: str, amount: float = 1) -> Product:
    """Teach a code: from now on it means this product (several codes per product are fine)."""
    product = await catalog.get_product(session, product_id)
    code = parse_code(code)["code"]
    existing = await session.get(Barcode, code)
    if existing is None:
        session.add(Barcode(code=code, product_id=product.id, amount=amount))
    else:
        existing.product_id, existing.amount = product.id, amount
    await session.commit()
    await session.refresh(product, ["barcodes"])
    hub.publish("catalog")
    return product


async def remove_barcode(session: AsyncSession, hub: EventHub, product_id: int, code: str) -> Product:
    """Forget a code, e.g. one that was linked to the wrong product."""
    product = await catalog.get_product(session, product_id)
    barcode = await session.get(Barcode, code)
    if barcode is None or barcode.product_id != product.id:
        raise NotFound(f"Barcode {code} is not linked to {product.name}")
    await session.delete(barcode)
    await session.commit()
    await session.refresh(product, ["barcodes"])
    hub.publish("catalog")
    return product


async def apply(
    session: AsyncSession,
    hub: EventHub,
    raw: str,
    mode: str,
    amount: float | None = None,
    actor: str | None = None,
    source: str = "scan",
) -> dict[str, Any]:
    """A scan with a mode, as a barcode scanner station does it: act on a known product right away."""
    if mode not in MODES:
        raise Invalid(f"mode must be one of: {', '.join(MODES)}")
    found = await lookup(session, raw)
    if found["product_id"] is None or mode == "lookup":
        return {**found, "mode": mode, "done": False}
    product = await catalog.get_product(session, found["product_id"])
    barcode = await session.get(Barcode, found["code"])
    amount = amount or (barcode.amount if barcode else 1)
    due = date.fromisoformat(found["due_date"]) if found.get("due_date") else None
    before = await stock.last_txn_id(session)
    if mode == "purchase":
        await stock.purchase(session, hub, product.id, amount, due_date=due, actor=actor, source=source)
    elif mode in ("consume", "spoil"):
        await stock.consume(session, hub, product.id, amount, spoiled=mode == "spoil", actor=actor, source=source)
    elif mode == "open":
        await stock.open_product(session, hub, product.id, amount, actor=actor)
    elif mode == "shopping":
        target = await shopping.default_list(session)
        await shopping.add_item(session, hub, target.id, ShoppingItemIn(product_id=product.id, amount=amount))
    txn_ids = await stock.txn_ids_after(session, before)
    return {**found, "mode": mode, "done": True, "amount": amount, "product_name": product.name, "txn_ids": txn_ids}


# --- photos ---------------------------------------------------------------


RECOGNIZE_SCHEMA = ai.obj(
    {
        "items": {
            "type": "array",
            "items": ai.obj(
                {
                    "name": {"type": "string", "description": "Product name as you'd write it on a shopping list, in English"},
                    "brand": {"type": "string", "description": "Brand, or empty"},
                    "quantity": {"type": "number", "description": "How many of this item are visible"},
                    "unit": {"type": "string", "description": "pc, pack, bottle, can, jar, kg, g, l, ..."},
                    "barcode": {"type": "string", "description": "Barcode digits if readable, else empty"},
                    "due_date": {"type": "string", "description": "Date printed on the pack as YYYY-MM-DD, else empty"},
                    "due_type": {"type": "string", "enum": ["best_before", "use_by", "none"]},
                    "date_text_seen": {"type": "string", "description": "The date text exactly as printed, else empty"},
                    "category": {"type": "string"},
                    "storage": {"type": "string", "enum": ["fridge", "freezer", "pantry", "drinks", "bathroom", "household"]},
                    "shelf_life_days": {"type": "integer", "description": "Typical days until it goes off when unopened"},
                    "catalog_match": {"type": "string", "description": "Exact name from the household catalog if it is one of those, else empty"},
                    "confidence": {"type": "number", "description": "0 to 1"},
                }
            ),
        }
    }
)


async def recognize(
    session: AsyncSession, bridge: HABridge, images: list[ai.Image], hint: str | None = None
) -> dict[str, Any]:
    """Identify groceries and read their dates from photos; match them to the household's own products."""
    if not images:
        raise Invalid("Add at least one photo")
    products = await catalog.list_products(session)
    categories = sorted({p.category for p in products if p.category})
    instructions = "\n".join(
        [
            "Identify every grocery or household item in the photo(s), including loose fruit, vegetables and bakery goods.",
            "Read printed dates: 'mindestens haltbar bis' / 'best before' = best_before, 'zu verbrauchen bis' / 'use by' = use_by. "
            "Dates may be short ('EXP 03/27', '12.11.', dot-matrix). Today is "
            f"{today().isoformat()}; pick the year that makes the date plausible. Leave due_date empty when unsure.",
            "If an item is one of the household's catalog products below, put that exact name in catalog_match.",
            f"Categories used here: {', '.join(categories) or 'none yet'}.",
            "Household catalog: " + "; ".join(p.name for p in products[:400]),
        ]
        + ([f"Hint from the user: {hint}"] if hint else [])
    )
    result = await ai.generate(session, bridge, "scan", ai.AIRequest("Steward grocery scan", instructions, RECOGNIZE_SCHEMA, images))
    by_name = {p.name.casefold(): p for p in products}
    items = []
    for item in result.get("items") or []:
        match = by_name.get(str(item.get("catalog_match") or "").casefold())
        score = 100.0 if match else 0.0
        if match is None:
            fuzzy = await _fuzzy_product(session, item.get("name") or "")
            if fuzzy:
                match, score = fuzzy
        due = item.get("due_date") or None
        if due:
            try:
                date.fromisoformat(due)
            except ValueError:
                due = None
        items.append(
            {
                "name": item.get("name") or "?",
                "brand": item.get("brand") or None,
                "quantity": item.get("quantity") or 1,
                "unit": item.get("unit") or "pc",
                "barcode": item.get("barcode") or None,
                "due_date": due,
                "due_type": item.get("due_type") if item.get("due_type") in ("best_before", "use_by") else None,
                "date_text_seen": item.get("date_text_seen") or None,
                "category": item.get("category") or None,
                "location_id": await _location_for(session, item.get("storage")),
                "shelf_life_days": item.get("shelf_life_days") or None,
                "confidence": item.get("confidence"),
                "product_id": match.id if match else None,
                "match_score": round(score),
            }
        )
    return {"items": items}

