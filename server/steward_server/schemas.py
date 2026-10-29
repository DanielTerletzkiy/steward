"""API request and response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .timeutil import as_utc

# SQLite returns naive datetimes; they are UTC, and the API always says so.
UTCDatetime = Annotated[datetime, AfterValidator(as_utc)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- people ---------------------------------------------------------------


class PersonIn(BaseModel):
    id: str
    name: str
    user_id: str | None = None
    picture: str | None = None
    state: str | None = None


class PersonOut(ORM):
    id: str
    name: str
    user_id: str | None
    picture: str | None
    state: str | None
    active: bool


# --- catalog --------------------------------------------------------------


class LocationIn(BaseModel):
    name: str
    is_freezer: bool = False


class LocationPatch(BaseModel):
    name: str | None = None
    is_freezer: bool | None = None


class LocationOut(ORM):
    id: int
    name: str
    is_freezer: bool


class ProductIn(BaseModel):
    name: str
    brand: str | None = None
    category: str | None = None
    location_id: int | None = None
    unit: str = "Stk"
    min_stock: float = 0
    due_days: int | None = None
    due_type: str = "best_before"
    image_url: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    receipt_aliases: list[str] = Field(default_factory=list)


class ProductPatch(BaseModel):
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    location_id: int | None = None
    unit: str | None = None
    min_stock: float | None = None
    due_days: int | None = None
    due_type: str | None = None
    image_url: str | None = None


class BarcodeOut(ORM):
    code: str
    amount: float


class ProductOut(ORM):
    id: int
    name: str
    brand: str | None
    category: str | None
    location_id: int | None
    unit: str
    min_stock: float
    due_days: int | None
    due_type: str
    image_url: str | None
    barcodes: list[BarcodeOut] = Field(default_factory=list)


# --- stock ----------------------------------------------------------------


class StockEntryOut(ORM):
    id: int
    amount: float
    location_id: int | None
    due_date: date | None
    opened_at: UTCDatetime | None
    purchased_at: UTCDatetime
    unit_price: float | None


class StockItemOut(BaseModel):
    product: ProductOut
    amount: float
    opened: float
    next_due: date | None
    status: str  # ok / due_soon / expired / out
    below_min: bool
    value: float
    entries: list[StockEntryOut]


class EntryMoveIn(BaseModel):
    location_id: int | None


class EntryPatch(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    unit_price: float | None = Field(default=None, ge=0)


class PurchaseIn(BaseModel):
    product_id: int
    amount: float = 1
    due_date: date | None = None
    location_id: int | None = None
    unit_price: float | None = None


class ConsumeIn(BaseModel):
    product_id: int
    amount: float = 1
    spoiled: bool = False


class OpenIn(BaseModel):
    product_id: int
    amount: float = 1


class StockTxnOut(BaseModel):
    id: int
    type: str
    product_id: int
    product_name: str
    amount: float
    unit_price: float | None
    at: UTCDatetime
    actor: str | None
    actor_name: str | None = None
    source: str
    undone: bool


# --- shopping -------------------------------------------------------------


class ShoppingListOut(ORM):
    id: int
    name: str


class ShoppingItemIn(BaseModel):
    text: str | None = None
    product_id: int | None = None
    amount: float = 1
    note: str | None = None


class ShoppingItemPatch(BaseModel):
    text: str | None = None
    amount: float | None = None
    note: str | None = None
    done: bool | None = None


class ShoppingItemOut(ORM):
    id: int
    list_id: int
    product_id: int | None
    text: str
    amount: float
    note: str | None
    done: bool
    created_at: UTCDatetime


# --- chores ---------------------------------------------------------------


class ChoreIn(BaseModel):
    name: str
    description: str | None = None
    icon: str | None = None
    schedule: str = "dynamic"
    interval: int = 1
    weekdays: list[int] = Field(default_factory=list)
    assignment: str = "none"
    assignees: list[str] = Field(default_factory=list)
    points: int = 1
    consume_product_id: int | None = None
    consume_amount: float = 1
    first_due: UTCDatetime | None = None


class ChorePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    schedule: str | None = None
    interval: int | None = None
    weekdays: list[int] | None = None
    assignment: str | None = None
    assignees: list[str] | None = None
    points: int | None = None
    next_due: UTCDatetime | None = None


class ChoreOut(BaseModel):
    id: int
    name: str
    description: str | None
    icon: str | None
    schedule: str
    interval: int
    weekdays: list[int]
    assignment: str
    assignees: list[str]
    next_assignee: str | None
    next_due: UTCDatetime | None
    status: str  # overdue / due_today / due_soon / scheduled / manual
    last_done: UTCDatetime | None
    last_done_by: str | None
    points: int


class ChoreExecuteIn(BaseModel):
    person_id: str | None = None
    skipped: bool = False


# --- tasks ----------------------------------------------------------------


class TaskIn(BaseModel):
    name: str
    notes: str | None = None
    category: str = "General"
    due_date: date | None = None
    assignee: str | None = None


class TaskPatch(BaseModel):
    name: str | None = None
    notes: str | None = None
    category: str | None = None
    due_date: date | None = None
    assignee: str | None = None
    done: bool | None = None


class TaskOut(ORM):
    id: int
    name: str
    notes: str | None
    category: str
    due_date: date | None
    assignee: str | None
    done_at: UTCDatetime | None


# --- receipts -------------------------------------------------------------


class ReceiptLineOut(ORM):
    id: int
    idx: int
    raw_text: str
    qty: float
    unit: str | None
    unit_price: float | None
    total: float
    tax: str | None
    kind: str
    product_id: int | None
    confidence: float
    method: str | None
    confirmed: bool
    pieces: float | None
    pieces_source: str | None
    # Deposit and bottle-return lines: how many bottles or cans they stand for (None if unknown).
    bottles: int | None = None


class ReceiptOut(ORM):
    id: int
    chain: str
    store: str | None
    at: UTCDatetime
    total: float
    payment: str | None
    loyalty: str | None
    source: str
    stocked: bool
    lines: list[ReceiptLineOut]


class ReceiptSummaryOut(ORM):
    id: int
    chain: str
    store: str | None
    at: UTCDatetime
    total: float
    stocked: bool
    line_count: int
    matched: int
    unmatched: int


class LinePiecesIn(BaseModel):
    pieces: float = Field(gt=0, le=1000)


class LineMatchIn(BaseModel):
    product_id: int | None = None
    new_product: ProductIn | None = None


class ReceiptAliasOut(ORM):
    id: int
    normalized: str
    product_id: int
    hits: int


class ProductAliasesIn(BaseModel):
    texts: list[str]


class AliasMovedOut(BaseModel):
    text: str
    product_id: int
    product_name: str


class ProductAliasesOut(BaseModel):
    aliases: list[ReceiptAliasOut]
    moved: list[AliasMovedOut]  # texts that belonged to another product until now


# --- files ----------------------------------------------------------------


class FileOut(ORM):
    id: str
    kind: str
    filename: str | None
    content_type: str
    size: int
    pages: int | None
    created_at: UTCDatetime


# --- equipment ------------------------------------------------------------


class EquipmentIn(BaseModel):
    name: str
    brand: str | None = None
    model: str | None = None
    serial: str | None = None
    room: str | None = None
    ha_device_id: str | None = None
    ha_entities: list[str] = Field(default_factory=list)
    kind: str = "other"
    automation: dict = Field(default_factory=dict)
    purchased_on: date | None = None
    price: float | None = None
    shop: str | None = None
    warranty_until: date | None = None
    notes: str | None = None
    consumable_ids: list[int] = Field(default_factory=list)
    chore_ids: list[int] = Field(default_factory=list)


class EquipmentPatch(BaseModel):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    serial: str | None = None
    room: str | None = None
    ha_device_id: str | None = None
    ha_entities: list[str] | None = None
    kind: str | None = None
    automation: dict | None = None
    purchased_on: date | None = None
    price: float | None = None
    shop: str | None = None
    warranty_until: date | None = None
    notes: str | None = None
    consumable_ids: list[int] | None = None
    chore_ids: list[int] | None = None


class EquipmentDocumentOut(ORM):
    id: int
    kind: str
    title: str
    file: FileOut


class EquipmentOut(ORM):
    id: int
    name: str
    brand: str | None
    model: str | None
    serial: str | None
    room: str | None
    ha_device_id: str | None
    ha_entities: list[str]
    kind: str
    automation: dict  # overrides as set by the user
    automation_effective: dict  # with the kind's defaults filled in
    live: dict | None
    live_at: UTCDatetime | None
    run_count: int
    last_run_at: UTCDatetime | None
    purchased_on: date | None
    price: float | None
    shop: str | None
    warranty_until: date | None
    warranty_status: str  # none / active / ending / expired
    notes: str | None
    photo_id: str | None
    consumable_ids: list[int]
    chore_ids: list[int]
    documents: list[EquipmentDocumentOut]


class LiveIn(BaseModel):
    """What the HA integration reports about a linked appliance right now."""

    state: str | None = None
    running: bool = False
    remaining_minutes: float | None = None
    battery: float | None = None
    commands: list[str] = Field(default_factory=list)
    entities: list[dict] = Field(default_factory=list)


class FinishedIn(BaseModel):
    source: str | None = None
    detail: str | None = None


class CommandIn(BaseModel):
    command: str


class ManualHit(BaseModel):
    equipment_id: int
    equipment_name: str
    document_id: int
    document_title: str
    file_id: str
    page: int
    snippet: str


# --- wardrobe -------------------------------------------------------------


class GarmentIn(BaseModel):
    owner: str | None = None
    name: str
    category: str
    layer: str | None = None  # derived from the category when left out
    colors: list[str] = Field(default_factory=list)
    pattern: str | None = None
    material: str | None = None
    warmth: int = Field(3, ge=1, le=5)
    temp_min: float | None = None
    temp_max: float | None = None
    rain: str = "none"
    windproof: bool = False
    formality: int = Field(2, ge=1, le=5)
    uses: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    brand: str | None = None
    size: str | None = None
    price: float | None = None
    favorite: bool = False
    notes: str | None = None
    wears_per_wash: int | None = None  # derived from the category when left out
    laundry_mode: str | None = None  # auto / ask; None = the category's default
    photo_id: str | None = None


class GarmentPatch(BaseModel):
    owner: str | None = None
    name: str | None = None
    category: str | None = None
    layer: str | None = None
    colors: list[str] | None = None
    pattern: str | None = None
    material: str | None = None
    warmth: int | None = Field(None, ge=1, le=5)
    temp_min: float | None = None
    temp_max: float | None = None
    rain: str | None = None
    windproof: bool | None = None
    formality: int | None = Field(None, ge=1, le=5)
    uses: list[str] | None = None
    seasons: list[str] | None = None
    brand: str | None = None
    size: str | None = None
    price: float | None = None
    favorite: bool | None = None
    notes: str | None = None
    state: str | None = None
    wears_per_wash: int | None = None
    wears_since_wash: int | None = Field(None, ge=0)  # lets "undo laundry done" restore the count
    laundry_mode: str | None = None
    extra_wears: int | None = Field(None, ge=0)
    dry_until: UTCDatetime | None = None
    photo_id: str | None = None


class GarmentOut(ORM):
    id: int
    owner: str | None
    name: str
    category: str
    layer: str
    colors: list[str]
    pattern: str | None
    material: str | None
    warmth: int
    temp_min: float | None
    temp_max: float | None
    rain: str
    windproof: bool
    formality: int
    uses: list[str]
    seasons: list[str]
    brand: str | None
    size: str | None
    price: float | None
    favorite: bool
    notes: str | None
    photo_id: str | None
    state: str
    wears_per_wash: int
    wears_since_wash: int
    laundry_mode: str | None
    laundry_mode_effective: str
    extra_wears: int
    needs_wash: bool
    washed_at: UTCDatetime | None
    dry_until: UTCDatetime | None
    wear_count: int
    last_worn: date | None
    cost_per_wear: float | None


class WearIn(BaseModel):
    garment_ids: list[int]
    day: date | None = None


class LaundryIn(BaseModel):
    garment_ids: list[int] | None = None  # None = everything in the laundry


class StillFineIn(BaseModel):
    garment_ids: list[int]
    wears: int | None = Field(None, ge=1, le=20)  # more wears before asking again; default about half the usual


class WardrobeSettings(BaseModel):
    # Hours freshly washed clothes need before they're suggested again; 0 = right away,
    # None = until marked dry.
    drying_hours: int | None = Field(24, ge=0, le=168)


class OutfitIn(BaseModel):
    owner: str | None = None
    day: date | None = None
    garment_ids: list[int]
    occasion: str | None = None
    worn: bool = False


class OutfitFeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    feedback: str | None = None


class OutfitOut(ORM):
    id: int
    owner: str | None
    day: date
    garment_ids: list[int]
    source: str
    occasion: str | None
    weather: dict | None
    reason: str | None
    worn: bool
    rating: int
    feedback: str | None
    created_at: UTCDatetime


class StyleProfileIn(BaseModel):
    description: str | None = None
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    runs_warm: int = Field(0, ge=-2, le=2)


class StyleProfileOut(ORM):
    owner: str
    description: str | None
    likes: list[str]
    dislikes: list[str]
    runs_warm: int


# --- recipes and meal plan ------------------------------------------------


class IngredientIn(BaseModel):
    text: str
    name: str | None = None  # parsed from text when left out
    amount: float | None = None
    unit: str | None = None
    product_id: int | None = None
    stock_amount: float | None = None
    optional: bool = False
    group: str | None = None


class IngredientOut(ORM):
    id: int
    text: str
    name: str
    amount: float | None
    unit: str | None
    product_id: int | None
    stock_amount: float | None
    optional: bool
    group: str | None


class RecipeIn(BaseModel):
    name: str
    description: str | None = None
    servings: int = Field(2, ge=1, le=50)
    minutes: int | None = None
    instructions: str | None = None
    source_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    ingredients: list[IngredientIn] = Field(default_factory=list)


class RecipePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    servings: int | None = Field(None, ge=1, le=50)
    minutes: int | None = None
    instructions: str | None = None
    source_url: str | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    ingredients: list[IngredientIn] | None = None  # replaces the list


class RecipeOut(ORM):
    id: int
    name: str
    description: str | None
    servings: int
    minutes: int | None
    instructions: str | None
    source_url: str | None
    photo_id: str | None
    tags: list[str]
    favorite: bool
    cooked_count: int
    last_cooked: date | None
    ingredients: list[IngredientOut]


class IngredientStatus(BaseModel):
    ingredient_id: int
    name: str
    product_id: int | None
    product_name: str | None
    needed: float | None  # in the product's unit, for the asked servings
    in_stock: float | None
    unit: str | None
    status: str  # have / partial / missing / unlinked / optional
    expiring: bool  # stock of it is due soon or expired: cooking this uses it up


class Fulfillment(BaseModel):
    recipe_id: int
    servings: int
    can_cook: bool
    missing: int
    unlinked: int
    uses_expiring: int
    ingredients: list[IngredientStatus]


class RecipeSuggestion(BaseModel):
    recipe: RecipeOut
    fulfillment: Fulfillment
    score: float


class CookIn(BaseModel):
    servings: int | None = None


class RecipeImportIn(BaseModel):
    url: str


class MealPlanIn(BaseModel):
    day: date
    slot: str = "dinner"
    recipe_id: int | None = None
    note: str | None = None
    servings: int | None = None


class MealPlanPatch(BaseModel):
    day: date | None = None
    slot: str | None = None
    recipe_id: int | None = None
    note: str | None = None
    servings: int | None = None
    done: bool | None = None


class MealPlanOut(ORM):
    id: int
    day: date
    slot: str
    recipe_id: int | None
    note: str | None
    servings: int | None
    done: bool


# --- kitchen terminals ----------------------------------------------------


class TerminalIn(BaseModel):
    name: str


class TerminalOut(BaseModel):
    id: int
    name: str
    paired: bool
    created_at: UTCDatetime
    last_seen: UTCDatetime | None


class TerminalPairOut(BaseModel):
    terminal: TerminalOut
    code: str
    expires: UTCDatetime


class TerminalsOut(BaseModel):
    terminals: list[TerminalOut]
    # Where a terminal reaches Steward directly (the app's host port), when the server knows it.
    direct_url: str | None
