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


class LineMatchIn(BaseModel):
    product_id: int | None = None
    new_product: ProductIn | None = None
