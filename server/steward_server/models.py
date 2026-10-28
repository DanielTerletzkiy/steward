"""Database tables."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow


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
