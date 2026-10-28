"""Recipes and the meal plan: what can be cooked from stock, cooking, missing items, imports."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

import httpx
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import __version__
from ..events import EventHub
from ..models import MealPlanEntry, Product, Recipe, RecipeIngredient
from ..schemas import (
    Fulfillment,
    IngredientIn,
    IngredientStatus,
    MealPlanIn,
    MealPlanPatch,
    RecipeIn,
    RecipeOut,
    RecipePatch,
    RecipeSuggestion,
)
from ..timeutil import today
from . import Invalid, NotFound, catalog, shopping, stock
from .files import FileStore

LOG = logging.getLogger("steward.recipes")

SLOTS = ("breakfast", "lunch", "dinner", "snack")
EPSILON = 1e-6
MATCH_THRESHOLD = 82

# Spellings of units, mapped to one name. German and English, as recipe sites write them.
UNITS = {
    "g": "g", "gr": "g", "gramm": "g", "gram": "g", "grams": "g", "kg": "kg", "mg": "mg",
    "ml": "ml", "l": "l", "liter": "l", "litre": "l", "cl": "cl", "dl": "dl",
    "el": "tbsp", "essl": "tbsp", "esslöffel": "tbsp", "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tl": "tsp", "teel": "tsp", "teelöffel": "tsp", "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "cup": "cup", "cups": "cup", "tasse": "cup", "tassen": "cup",
    "prise": "pinch", "prisen": "pinch", "pinch": "pinch",
    "stk": "pc", "stk.": "pc", "stück": "pc", "piece": "pc", "pieces": "pc", "pc": "pc", "pcs": "pc",
    "dose": "can", "dosen": "can", "can": "can", "cans": "can",
    "pck": "pack", "pck.": "pack", "packung": "pack", "päckchen": "pack", "pack": "pack", "packs": "pack",
    "bund": "bunch", "bunch": "bunch", "zehe": "clove", "zehen": "clove", "clove": "clove", "cloves": "clove",
    "scheibe": "slice", "scheiben": "slice", "slice": "slice", "slices": "slice",
    "glas": "jar", "gläser": "jar", "jar": "jar", "becher": "tub", "tub": "tub", "beutel": "sachet", "tüte": "sachet",
}  # fmt: skip
# Units that mean the same as a product's counting unit.
COUNTING = {"pc", "pack", "can", "jar", "tub", "sachet", "bottle", "bar", "tube", "pcs", "stk"}
UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅛": "1/8"}
AMOUNT = r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"  # "1 1/2", "1/2", "1,5"


# --- ingredient lines -----------------------------------------------------


def parse_ingredient(line: str) -> dict[str, Any]:
    """'200 g Spaghetti' → amount 200, unit g, name Spaghetti. Ranges take the upper end; notes are dropped."""
    text = " ".join(line.split())
    for symbol, fraction in UNICODE_FRACTIONS.items():
        text = text.replace(symbol, f" {fraction}")
    text = text.strip()
    amount = None
    match = re.match(rf"^{AMOUNT}(?:\s*[-–]\s*{AMOUNT})?\s*", text)
    if match:
        amount = _number(match.group(2) or match.group(1))
        text = text[match.end() :]
    unit = None
    if text:
        first, _, rest = text.partition(" ")
        key = first.lower().rstrip(".")
        if key in UNITS or first.lower() in UNITS:
            unit = UNITS.get(key) or UNITS[first.lower()]
            text = rest
        else:
            glued = re.match(r"^(\d+(?:[.,]\d+)?)([a-zA-Z]+)\s+(.*)$", first + " " + rest)
            if amount is None and glued and glued.group(2).lower() in UNITS:
                amount, unit, text = _number(glued.group(1)), UNITS[glued.group(2).lower()], glued.group(3)
    name = re.sub(r"\(.*?\)", "", text)
    name = name.split(",")[0].strip(" -–:;") or line.strip()
    optional = bool(re.search(r"\b(optional|nach belieben|to taste|n\. ?b\.)\b", line, re.IGNORECASE))
    return {"text": line.strip(), "name": name, "amount": amount, "unit": unit, "optional": optional}


def _number(value: str) -> float:
    total = 0.0
    for part in value.replace(",", ".").split():
        total += float(Fraction(part)) if "/" in part else float(part)
    return round(total, 3)


def _same_unit(unit: str | None, product_unit: str) -> bool:
    if unit is None:
        return True
    product = UNITS.get(product_unit.lower(), product_unit.lower())
    return unit == product or (unit in COUNTING and product in COUNTING)


async def _match_product(session: AsyncSession, name: str, products: list[Product] | None = None) -> Product | None:
    products = products if products is not None else await catalog.list_products(session)
    if not products or not name:
        return None
    match = process.extractOne(name, {p.id: p.name for p in products}, scorer=fuzz.WRatio)
    if match is None or match[1] < MATCH_THRESHOLD:
        return None
    return next(p for p in products if p.id == match[2])


async def _build_ingredients(session: AsyncSession, items: list[IngredientIn]) -> list[RecipeIngredient]:
    products = await catalog.list_products(session)
    by_id = {p.id: p for p in products}
    built = []
    for idx, item in enumerate(items):
        parsed = parse_ingredient(item.text)
        values = {**parsed, **item.model_dump(exclude_unset=True, exclude_none=True)}
        values.setdefault("name", parsed["name"])
        product = by_id.get(values.get("product_id")) if values.get("product_id") else None
        if product is None and "product_id" not in item.model_fields_set:
            product = await _match_product(session, values["name"], products)
        values["product_id"] = product.id if product else None
        if product is not None and values.get("stock_amount") is None and values.get("amount") is not None:
            # Same unit as the product's stock: the recipe amount is the stock amount.
            if _same_unit(values.get("unit"), product.unit):
                values["stock_amount"] = values["amount"]
        built.append(RecipeIngredient(idx=idx, **{k: values.get(k) for k in IngredientIn.model_fields}))
    return built


# --- recipes --------------------------------------------------------------


async def list_recipes(session: AsyncSession) -> list[Recipe]:
    return list((await session.scalars(select(Recipe).order_by(Recipe.name))).all())


async def get_recipe(session: AsyncSession, recipe_id: int) -> Recipe:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None:
        raise NotFound(f"Recipe {recipe_id} not found")
    return recipe


async def create_recipe(session: AsyncSession, hub: EventHub, data: RecipeIn) -> Recipe:
    values = data.model_dump(exclude={"ingredients"})
    recipe = Recipe(**values, ingredients=await _build_ingredients(session, data.ingredients))
    session.add(recipe)
    await session.commit()
    hub.publish("recipes")
    return await get_recipe(session, recipe.id)


async def update_recipe(session: AsyncSession, hub: EventHub, recipe_id: int, patch: RecipePatch) -> Recipe:
    recipe = await get_recipe(session, recipe_id)
    values = patch.model_dump(exclude_unset=True, exclude={"ingredients"})
    for key, value in values.items():
        setattr(recipe, key, value)
    if patch.ingredients is not None:
        recipe.ingredients = await _build_ingredients(session, patch.ingredients)
    await session.commit()
    hub.publish("recipes")
    await session.refresh(recipe)
    return recipe


async def delete_recipe(session: AsyncSession, hub: EventHub, files: FileStore, recipe_id: int) -> None:
    recipe = await get_recipe(session, recipe_id)
    photo = recipe.photo_id
    await session.delete(recipe)
    await files.delete(session, photo)
    await session.commit()
    hub.publish("recipes")
    hub.publish("mealplan")


async def set_photo(
    session: AsyncSession, hub: EventHub, files: FileStore, recipe_id: int, data: bytes, filename: str | None
) -> Recipe:
    recipe = await get_recipe(session, recipe_id)
    stored = await files.save(session, data, filename=filename, content_type="image/*", kind="photo")
    old, recipe.photo_id = recipe.photo_id, stored.id
    await files.delete(session, old)
    await session.commit()
    hub.publish("recipes")
    return recipe


async def remove_photo(session: AsyncSession, hub: EventHub, files: FileStore, recipe_id: int) -> Recipe:
    recipe = await get_recipe(session, recipe_id)
    old, recipe.photo_id = recipe.photo_id, None
    await files.delete(session, old)
    await session.commit()
    hub.publish("recipes")
    return recipe


# --- what can be cooked ---------------------------------------------------


async def _stock_by_product(session: AsyncSession) -> dict[int, Any]:
    return {item.product.id: item for item in await stock.stock_overview(session, include_empty=True)}


def fulfillment(recipe: Recipe, servings: int | None, stock_items: dict[int, Any]) -> Fulfillment:
    servings = servings or recipe.servings
    factor = servings / recipe.servings
    statuses = []
    for ingredient in recipe.ingredients:
        item = stock_items.get(ingredient.product_id) if ingredient.product_id else None
        needed = round(ingredient.stock_amount * factor, 3) if ingredient.stock_amount is not None else None
        in_stock = item.amount if item else None
        if ingredient.product_id is None:
            status = "optional" if ingredient.optional else "unlinked"
        elif not in_stock:
            status = "optional" if ingredient.optional else "missing"
        elif needed is not None and in_stock + EPSILON < needed:
            status = "optional" if ingredient.optional else "partial"
        else:
            status = "have"
        statuses.append(
            IngredientStatus(
                ingredient_id=ingredient.id,
                name=ingredient.name,
                product_id=ingredient.product_id,
                product_name=item.product.name if item else None,
                needed=needed,
                in_stock=in_stock,
                unit=item.product.unit if item else ingredient.unit,
                status=status,
                expiring=bool(item and in_stock and item.status in ("due_soon", "expired")),
            )
        )
    missing = sum(1 for s in statuses if s.status in ("missing", "partial"))
    return Fulfillment(
        recipe_id=recipe.id,
        servings=servings,
        can_cook=missing == 0,
        missing=missing,
        unlinked=sum(1 for s in statuses if s.status == "unlinked"),
        uses_expiring=sum(1 for s in statuses if s.expiring),
        ingredients=statuses,
    )


async def get_fulfillment(session: AsyncSession, recipe_id: int, servings: int | None = None) -> Fulfillment:
    return fulfillment(await get_recipe(session, recipe_id), servings, await _stock_by_product(session))


async def suggestions(session: AsyncSession, limit: int = 10) -> list[RecipeSuggestion]:
    """Recipes ranked for tonight: cookable from stock first, especially those that use up what expires."""
    stock_items = await _stock_by_product(session)
    ranked = []
    for recipe in await list_recipes(session):
        result = fulfillment(recipe, None, stock_items)
        score = (10 if result.can_cook else 0) + result.uses_expiring * 4 - result.missing * 2 - result.unlinked * 0.5
        score += 1 if recipe.favorite else 0
        if recipe.last_cooked and (today() - recipe.last_cooked).days < 4:
            score -= 3
        ranked.append(RecipeSuggestion(recipe=RecipeOut.model_validate(recipe), fulfillment=result, score=round(score, 1)))
    ranked.sort(key=lambda s: s.score, reverse=True)
    return ranked[:limit]


async def cook(
    session: AsyncSession, hub: EventHub, recipe_id: int, servings: int | None = None, actor: str | None = None
) -> list[dict[str, Any]]:
    """Take the ingredients out of stock. Amounts given only as "some" are not taken out."""
    recipe = await get_recipe(session, recipe_id)
    result = fulfillment(recipe, servings, await _stock_by_product(session))
    used = []
    for status in result.ingredients:
        if status.product_id is None or not status.in_stock or status.needed is None:
            continue
        amount = min(status.needed, status.in_stock)
        taken = await stock.consume(session, hub, status.product_id, amount, actor=actor, source="recipe", commit=False)
        used.append({"product_id": status.product_id, "name": status.product_name, "amount": taken, "unit": status.unit})
    recipe.cooked_count += 1
    recipe.last_cooked = today()
    await session.commit()
    hub.publish("stock")
    hub.publish("shopping")
    hub.publish("recipes")
    return used


async def add_missing_to_list(
    session: AsyncSession, hub: EventHub, needs: dict[int, float | None], stock_items: dict[int, Any] | None = None
) -> list[str]:
    """Put what is missing for the given product needs (None = "some") on the shopping list."""
    stock_items = stock_items if stock_items is not None else await _stock_by_product(session)
    added = []
    for product_id, needed in needs.items():
        have = stock_items[product_id].amount if product_id in stock_items else 0
        short = (needed - have) if needed is not None else (0 if have > 0 else 1)
        if short > EPSILON:
            product = await catalog.get_product(session, product_id)
            await shopping.ensure_on_list(session, product, max(round(short, 2), 0.01))
            added.append(product.name)
    await session.commit()
    hub.publish("shopping")
    return added


async def recipe_to_list(session: AsyncSession, hub: EventHub, recipe_id: int, servings: int | None = None) -> list[str]:
    recipe = await get_recipe(session, recipe_id)
    result = fulfillment(recipe, servings, await _stock_by_product(session))
    needs = {s.product_id: s.needed for s in result.ingredients if s.product_id and s.status in ("missing", "partial")}
    return await add_missing_to_list(session, hub, needs)


# --- import from a website ------------------------------------------------


async def import_url(session: AsyncSession, hub: EventHub, files: FileStore, url: str) -> Recipe:
    """Read a recipe page's schema.org data (most recipe sites have it) and save it with its photo."""
    if not re.match(r"^https?://", url):
        raise Invalid("Give a web address starting with http:// or https://")
    headers = {"User-Agent": f"Mozilla/5.0 (compatible; Steward/{__version__}; recipe import)"}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
            page = await client.get(url)
            page.raise_for_status()
            data = _find_recipe(page.text)
            if data is None:
                raise Invalid("No recipe found on that page")
            image_url = _image_url(data.get("image"))
            image = None
            if image_url:
                try:
                    picture = await client.get(image_url)
                    picture.raise_for_status()
                    image = picture.content
                except httpx.HTTPError:
                    LOG.info("Recipe photo %s could not be loaded", image_url)
    except httpx.HTTPError as err:
        raise Invalid(f"The page could not be loaded: {err}") from err

    recipe = await create_recipe(
        session,
        hub,
        RecipeIn(
            name=_text(data.get("name")) or "Imported recipe",
            description=_text(data.get("description")) or None,
            servings=_servings(data.get("recipeYield")),
            minutes=_minutes(data.get("totalTime")) or _sum_minutes(data.get("prepTime"), data.get("cookTime")),
            instructions=_instructions(data.get("recipeInstructions")),
            source_url=url,
            tags=_tags(data),
            ingredients=[IngredientIn(text=_text(line)) for line in data.get("recipeIngredient") or [] if _text(line)],
        ),
    )
    if image:
        try:
            recipe = await set_photo(session, hub, files, recipe.id, image, "recipe.jpg")
        except Invalid:
            pass
    return recipe


def _find_recipe(html: str) -> dict[str, Any] | None:
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        found = _recipe_in(data)
        if found:
            return found
    return None


def _recipe_in(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        return next((r for r in (_recipe_in(d) for d in data) if r), None)
    if isinstance(data, dict):
        kind = data.get("@type")
        if kind == "Recipe" or (isinstance(kind, list) and "Recipe" in kind):
            return data
        return _recipe_in(data.get("@graph")) if "@graph" in data else None
    return None


def _text(value: Any) -> str:
    import html

    if isinstance(value, list):
        value = value[0] if value else ""
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def _image_url(value: Any) -> str | None:
    if isinstance(value, list):
        return _image_url(value[0]) if value else None
    if isinstance(value, dict):
        return value.get("url")
    return value if isinstance(value, str) else None


def _servings(value: Any) -> int:
    match = re.search(r"\d+", _text(value))
    return max(1, min(int(match.group()), 50)) if match else 2


def _minutes(value: Any) -> int | None:
    match = re.match(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", _text(value))
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g or 0) for g in match.groups())
    return days * 1440 + hours * 60 + minutes or None


def _sum_minutes(*values: Any) -> int | None:
    total = sum(_minutes(v) or 0 for v in values)
    return total or None


def _instructions(value: Any) -> str | None:
    steps: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            steps.extend(line.strip() for line in re.split(r"\n+", _text(node)) if line.strip())
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            if node.get("@type") == "HowToSection":
                walk(node.get("itemListElement"))
            else:
                walk(node.get("text") or node.get("name"))

    walk(value)
    return "\n".join(steps) or None


def _tags(data: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("recipeCategory", "recipeCuisine", "keywords"):
        value = data.get(key)
        parts = value if isinstance(value, list) else str(value or "").split(",")
        tags.extend(_text(p) for p in parts if _text(p))
    return list(dict.fromkeys(tags))[:8]


# --- meal plan ------------------------------------------------------------


async def meal_plan(session: AsyncSession, start: date, end: date) -> list[MealPlanEntry]:
    query = select(MealPlanEntry).where(MealPlanEntry.day >= start, MealPlanEntry.day <= end)
    entries = (await session.scalars(query)).all()
    return sorted(entries, key=lambda e: (e.day, SLOTS.index(e.slot) if e.slot in SLOTS else 9, e.id))


async def _entry(session: AsyncSession, entry_id: int) -> MealPlanEntry:
    entry = await session.get(MealPlanEntry, entry_id)
    if entry is None:
        raise NotFound(f"Meal plan entry {entry_id} not found")
    return entry


async def add_meal(session: AsyncSession, hub: EventHub, data: MealPlanIn) -> MealPlanEntry:
    if data.slot not in SLOTS:
        raise Invalid(f"slot must be one of: {', '.join(SLOTS)}")
    if data.recipe_id is None and not data.note:
        raise Invalid("Plan a recipe or write a note")
    if data.recipe_id is not None:
        await get_recipe(session, data.recipe_id)
    entry = MealPlanEntry(**data.model_dump())
    session.add(entry)
    await session.commit()
    hub.publish("mealplan")
    return entry


async def update_meal(session: AsyncSession, hub: EventHub, entry_id: int, patch: MealPlanPatch) -> MealPlanEntry:
    entry = await _entry(session, entry_id)
    values = patch.model_dump(exclude_unset=True)
    if values.get("slot") is not None and values["slot"] not in SLOTS:
        raise Invalid(f"slot must be one of: {', '.join(SLOTS)}")
    for key, value in values.items():
        setattr(entry, key, value)
    await session.commit()
    hub.publish("mealplan")
    return entry


async def delete_meal(session: AsyncSession, hub: EventHub, entry_id: int) -> None:
    await session.delete(await _entry(session, entry_id))
    await session.commit()
    hub.publish("mealplan")


async def complete_meal(
    session: AsyncSession, hub: EventHub, entry_id: int, cook_it: bool = True, actor: str | None = None
) -> MealPlanEntry:
    """Mark a planned meal as eaten; by default its recipe's ingredients leave stock."""
    entry = await _entry(session, entry_id)
    if not entry.done and cook_it and entry.recipe_id is not None:
        await cook(session, hub, entry.recipe_id, entry.servings, actor=actor)
    entry.done = True
    await session.commit()
    hub.publish("mealplan")
    return entry


async def plan_to_list(session: AsyncSession, hub: EventHub, start: date, end: date) -> list[str]:
    """Everything the planned (not yet eaten) meals in a date range still need, on the shopping list."""
    stock_items = await _stock_by_product(session)
    needs: dict[int, float | None] = {}
    for entry in await meal_plan(session, start, end):
        if entry.done or entry.recipe_id is None:
            continue
        result = fulfillment(await get_recipe(session, entry.recipe_id), entry.servings, stock_items)
        for status in result.ingredients:
            if status.product_id is None or status.status == "optional":
                continue
            # Amounts add up across meals; "some" (None) only counts if no meal gives an amount.
            current = needs.get(status.product_id)
            if status.needed is not None:
                needs[status.product_id] = (current or 0) + status.needed
            else:
                needs.setdefault(status.product_id, None)
    return await add_missing_to_list(session, hub, needs, stock_items)


def week_of(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)
