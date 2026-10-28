"""Database tables."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import today, utcnow


class Person(Base):
    """Mirror of a Home Assistant `person`, keyed by its entity id."""

    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. person.daniel
    name: Mapped[str] = mapped_column(String)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    picture: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)  # home / not_home / zone
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    is_freezer: Mapped[bool] = mapped_column(Boolean, default=False)


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"), nullable=True)
    unit: Mapped[str] = mapped_column(String, default="Stk")
    min_stock: Mapped[float] = mapped_column(Float, default=0)
    due_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_type: Mapped[str] = mapped_column(String, default="best_before")  # or use_by
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    location: Mapped[Location | None] = relationship(lazy="selectin")
    barcodes: Mapped[list[Barcode]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class Barcode(Base):
    __tablename__ = "barcode"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float, default=1)


class StockEntry(Base):
    """One lot on the shelf. Amount drops to zero when it is used up."""

    __tablename__ = "stock_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)


class StockTxn(Base):
    """Append-only ledger of every stock change."""

    __tablename__ = "stock_txn"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String)  # purchase / consume / spoil / open / undo
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"), index=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("stock_entry.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="ui")  # ui / ha / receipt / voice / seed
    receipt_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipt_line.id", ondelete="SET NULL"), nullable=True
    )
    undone: Mapped[bool] = mapped_column(Boolean, default=False)


class ShoppingList(Base):
    __tablename__ = "shopping_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class ShoppingItem(Base):
    __tablename__ = "shopping_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("shopping_list.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float, default=1)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chore(Base):
    __tablename__ = "chore"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    # manual / daily / weekly / monthly / dynamic (interval days after the last time it was done)
    schedule: Mapped[str] = mapped_column(String, default="dynamic")
    interval: Mapped[int] = mapped_column(Integer, default=1)
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=list)  # 0 = Monday, for weekly
    # none / fixed / least_done / rotation
    assignment: Mapped[str] = mapped_column(String, default="none")
    assignees: Mapped[list[str]] = mapped_column(JSON, default=list)  # person ids
    next_assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    next_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=1)
    consume_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id", ondelete="SET NULL"), nullable=True
    )
    consume_amount: Mapped[float] = mapped_column(Float, default=1)


class ChoreLog(Base):
    __tablename__ = "chore_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chore_id: Mapped[int] = mapped_column(ForeignKey("chore.id", ondelete="CASCADE"), index=True)
    done_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    done_by: Mapped[str | None] = mapped_column(String, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String, default="ui")


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String, default="General")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Receipt(Base):
    __tablename__ = "receipt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, unique=True)  # content hash, keeps imports idempotent
    chain: Mapped[str] = mapped_column(String, default="REWE")
    store: Mapped[str | None] = mapped_column(String, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total: Mapped[float] = mapped_column(Float)
    payment: Mapped[str | None] = mapped_column(String, nullable=True)
    loyalty: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="upload")
    stocked: Mapped[bool] = mapped_column(Boolean, default=False)

    lines: Mapped[list[ReceiptLine]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="ReceiptLine.idx"
    )


class ReceiptLine(Base):
    __tablename__ = "receipt_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipt.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float] = mapped_column(Float)
    tax: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, default="item")  # item / deposit / deposit_return / bag
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    method: Mapped[str | None] = mapped_column(String, nullable=True)  # alias / fuzzy / manual
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class ReceiptAlias(Base):
    """A receipt text that is known to mean a product, learned from confirmations."""

    __tablename__ = "receipt_alias"
    __table_args__ = (UniqueConstraint("chain", "normalized"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String)
    normalized: Mapped[str] = mapped_column(String)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="CASCADE"))
    hits: Mapped[int] = mapped_column(Integer, default=0)


class StoredFile(Base):
    """An uploaded photo or document. Bytes live under <data>/files; photos also get a WebP thumbnail."""

    __tablename__ = "stored_file"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # random hex, also the file name on disk
    kind: Mapped[str] = mapped_column(String)  # photo / manual / document
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


WARRANTY_WARN_DAYS = 30
APPLIANCE_KINDS = ("washer", "dryer", "dishwasher", "vacuum", "other")
# What a finished run does by default: complete the linked chores (the vacuum did it) or make them due
# ("hang up the laundry"), and whether to offer marking the laundry as clean.
AUTOMATION_DEFAULTS = {
    "washer": {"chores": "make_due", "laundry": "ask"},
    "dryer": {"chores": "make_due", "laundry": "off"},
    "dishwasher": {"chores": "make_due", "laundry": "off"},
    "vacuum": {"chores": "complete", "laundry": "off"},
    "other": {"chores": "off", "laundry": "off"},
}


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    serial: Mapped[str | None] = mapped_column(String, nullable=True)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    ha_device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Linked HA entities on top of the device's own (e.g. template or helper entities).
    ha_entities: Mapped[list[str]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    kind: Mapped[str] = mapped_column(String, default="other", server_default="other")  # washer / dryer / dishwasher / vacuum / other
    # What a finished run does, overriding the kind's defaults: {"chores": complete|make_due|off, "laundry": ask|auto|off}
    automation: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    live: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # status pushed by the HA integration
    live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purchased_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shop: Mapped[str | None] = mapped_column(String, nullable=True)
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("stored_file.id", ondelete="SET NULL"), nullable=True)
    consumable_ids: Mapped[list[int]] = mapped_column(JSON, default=list)  # products it uses up
    chore_ids: Mapped[list[int]] = mapped_column(JSON, default=list)  # upkeep chores
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[EquipmentDocument]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="EquipmentDocument.id"
    )

    @property
    def automation_effective(self) -> dict:
        return {**AUTOMATION_DEFAULTS.get(self.kind or "other", AUTOMATION_DEFAULTS["other"]), **(self.automation or {})}

    @property
    def warranty_status(self) -> str:
        """none / active / ending (within WARRANTY_WARN_DAYS) / expired."""
        if self.warranty_until is None:
            return "none"
        days = (self.warranty_until - today()).days
        if days < 0:
            return "expired"
        return "ending" if days <= WARRANTY_WARN_DAYS else "active"


class EquipmentRun(Base):
    """A finished run of an appliance (wash cycle, vacuum run), reported by Home Assistant."""

    __tablename__ = "equipment_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. event.washer_notification
    detail: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. washing_is_complete


class EquipmentDocument(Base):
    """A manual, invoice or other file attached to a piece of equipment."""

    __tablename__ = "equipment_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("stored_file.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String, default="manual")  # manual / invoice / other
    title: Mapped[str] = mapped_column(String)

    file: Mapped[StoredFile] = relationship(lazy="selectin")


class Garment(Base):
    __tablename__ = "garment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # person id
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)  # t-shirt, sweater, jeans, jacket, sneakers, ...
    layer: Mapped[str] = mapped_column(String)  # base / mid / outer / bottom / full / shoes / accessory
    colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    material: Mapped[str | None] = mapped_column(String, nullable=True)
    warmth: Mapped[int] = mapped_column(Integer, default=3)  # 1 (very light) .. 5 (very warm)
    temp_min: Mapped[float | None] = mapped_column(Float, nullable=True)  # comfortable from (°C, feels-like)
    temp_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain: Mapped[str] = mapped_column(String, default="none")  # none / resistant / waterproof
    windproof: Mapped[bool] = mapped_column(Boolean, default=False)
    formality: Mapped[int] = mapped_column(Integer, default=2)  # 1 (lounge) .. 5 (formal)
    uses: Mapped[list[str]] = mapped_column(JSON, default=list)  # home / comfort / going_out / work / sport / formal
    seasons: Mapped[list[str]] = mapped_column(JSON, default=list)  # summer / transition / winter
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    size: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("stored_file.id", ondelete="SET NULL"), nullable=True)
    # clean / worn / laundry / repair / lent / stored
    state: Mapped[str] = mapped_column(String, default="clean")
    wears_per_wash: Mapped[int] = mapped_column(Integer, default=1)
    wears_since_wash: Mapped[int] = mapped_column(Integer, default=0)
    wear_count: Mapped[int] = mapped_column(Integer, default=0)
    last_worn: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def cost_per_wear(self) -> float | None:
        if self.price is None:
            return None
        return round(self.price / max(self.wear_count, 1), 2)


class Outfit(Base):
    __tablename__ = "outfit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    garment_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual / rules / ai
    occasion: Mapped[str | None] = mapped_column(String, nullable=True)
    weather: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    worn: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1 / 0 / 1
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StyleProfile(Base):
    __tablename__ = "style_profile"

    owner: Mapped[str] = mapped_column(String, primary_key=True)  # person id, or "" for the household
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    likes: Mapped[list[str]] = mapped_column(JSON, default=list)
    dislikes: Mapped[list[str]] = mapped_column(JSON, default=list)
    runs_warm: Mapped[int] = mapped_column(Integer, default=0)  # -2 (always cold) .. 2 (always warm)


class Setting(Base):
    """Key/value settings edited in the UI (AI providers, weather source, ...)."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)


class BarcodeLookup(Base):
    """Cached Open Food Facts / Open Products Facts answers (also "not found", to avoid asking again)."""

    __tablename__ = "barcode_lookup"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recipe(Base):
    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    servings: Mapped[int] = mapped_column(Integer, default=2)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # total time
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)  # one step per line
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("stored_file.id", ondelete="SET NULL"), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    cooked_count: Mapped[int] = mapped_column(Integer, default=0)
    last_cooked: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="RecipeIngredient.idx"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(String)  # the line as written ("200 g spaghetti")
    name: Mapped[str] = mapped_column(String)  # what it is ("spaghetti")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # for the recipe's servings
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id", ondelete="SET NULL"), nullable=True)
    # How much of the product's stock unit one recipe batch uses; None = "some" (only checks it's there).
    stock_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    group: Mapped[str | None] = mapped_column(String, nullable=True)


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String, default="dinner")  # breakfast / lunch / dinner / snack
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"), nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)  # "Leftovers", "Eating out", ...
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = the recipe's own
    done: Mapped[bool] = mapped_column(Boolean, default=False)
