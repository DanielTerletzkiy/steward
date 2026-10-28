"""Stock ledger: purchase, consume, open, undo, and the aggregated stock view."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Product, StockEntry, StockTxn
from ..schemas import ProductOut, StockEntryOut, StockItemOut, StockTxnOut
from ..timeutil import LOCAL_TZ, today, utcnow
from . import Invalid, NotFound
from .catalog import get_product

DUE_SOON_DAYS = 3
_EPSILON = 1e-9


def _status(next_due: date | None, amount: float) -> str:
    if amount <= _EPSILON:
        return "out"
    if next_due is None:
        return "ok"
    if next_due < today():
        return "expired"
    if next_due <= today() + timedelta(days=DUE_SOON_DAYS):
        return "due_soon"
    return "ok"


async def _entries(session: AsyncSession, product_id: int | None = None) -> list[StockEntry]:
    query = select(StockEntry).where(StockEntry.amount > _EPSILON)
    if product_id is not None:
        query = query.where(StockEntry.product_id == product_id)
    return list((await session.scalars(query)).all())


def _consume_order(entry: StockEntry) -> tuple:
    # Opened packs first, then first-expiring-first-out, then oldest purchase.
    return (entry.opened_at is None, entry.due_date or date.max, entry.purchased_at)


async def stock_overview(session: AsyncSession, include_empty: bool = False) -> list[StockItemOut]:
    products = {p.id: p for p in (await session.scalars(select(Product))).all()}
    by_product: dict[int, list[StockEntry]] = {}
    for entry in await _entries(session):
        by_product.setdefault(entry.product_id, []).append(entry)

    items = []
    for product in sorted(products.values(), key=lambda p: p.name.casefold()):
        entries = sorted(by_product.get(product.id, []), key=_consume_order)
        amount = sum(e.amount for e in entries)
        if not entries and not include_empty and product.min_stock <= 0:
            continue
        dues = [e.due_date for e in entries if e.due_date]
        next_due = min(dues) if dues else None
        items.append(
            StockItemOut(
                product=ProductOut.model_validate(product),
                amount=round(amount, 3),
                opened=round(sum(e.amount for e in entries if e.opened_at), 3),
                next_due=next_due,
                status=_status(next_due, amount),
                below_min=product.min_stock > 0 and amount + _EPSILON < product.min_stock,
                value=round(sum(e.amount * (e.unit_price or 0) for e in entries), 2),
                entries=[StockEntryOut.model_validate(e) for e in entries],
            )
        )
    return items


async def purchase(
    session: AsyncSession,
    hub: EventHub,
    product_id: int,
    amount: float,
    *,
    due_date: date | None = None,
    location_id: int | None = None,
    unit_price: float | None = None,
    actor: str | None = None,
    source: str = "ui",
    receipt_line_id: int | None = None,
    at: datetime | None = None,
    commit: bool = True,
) -> StockEntry:
    if amount <= 0:
        raise Invalid("Amount must be positive")
    product = await get_product(session, product_id)
    if due_date is None and product.due_days is not None:
        bought_on = at.astimezone(LOCAL_TZ).date() if at else today()
        due_date = bought_on + timedelta(days=product.due_days)
    entry = StockEntry(
        product_id=product.id,
        amount=amount,
        location_id=location_id or product.location_id,
        due_date=due_date,
        unit_price=unit_price,
        purchased_at=at or utcnow(),
    )
    session.add(entry)
    await session.flush()
    session.add(
        StockTxn(
            type="purchase",
            product_id=product.id,
            entry_id=entry.id,
            amount=amount,
            unit_price=unit_price,
            actor=actor,
            source=source,
            receipt_line_id=receipt_line_id,
            at=at or utcnow(),
        )
    )
    if commit:
        await session.commit()
        hub.publish("stock", product_id=product.id)
    return entry


async def consume(
    session: AsyncSession,
    hub: EventHub,
    product_id: int,
    amount: float,
    *,
    spoiled: bool = False,
    actor: str | None = None,
    source: str = "ui",
    commit: bool = True,
) -> float:
    """Take `amount` out of stock. Returns how much was actually taken."""
    if amount <= 0:
        raise Invalid("Amount must be positive")
    product = await get_product(session, product_id)
    entries = sorted(await _entries(session, product.id), key=_consume_order)
    if not entries:
        raise Invalid(f"{product.name} is not in stock")
    remaining = amount
    for entry in entries:
        if remaining <= _EPSILON:
            break
        taken = min(entry.amount, remaining)
        entry.amount = round(entry.amount - taken, 6)
        remaining -= taken
        session.add(
            StockTxn(
                type="spoil" if spoiled else "consume",
                product_id=product.id,
                entry_id=entry.id,
                amount=taken,
                unit_price=entry.unit_price,
                actor=actor,
                source=source,
            )
        )
    await _auto_add_to_shopping_list(session, product)
    if commit:
        await session.commit()
        hub.publish("stock", product_id=product.id)
        hub.publish("shopping")
    return amount - max(remaining, 0)


async def open_product(
    session: AsyncSession, hub: EventHub, product_id: int, amount: float = 1, *, actor: str | None = None
) -> None:
    product = await get_product(session, product_id)
    closed = sorted((e for e in await _entries(session, product.id) if e.opened_at is None), key=_consume_order)
    if not closed:
        raise Invalid(f"No unopened {product.name} in stock")
    remaining = amount
    for entry in closed:
        if remaining <= _EPSILON:
            break
        if entry.amount > remaining + _EPSILON:
            # Split the lot: the opened part becomes its own entry.
            entry.amount = round(entry.amount - remaining, 6)
            opened = StockEntry(
                product_id=entry.product_id,
                amount=remaining,
                location_id=entry.location_id,
                due_date=entry.due_date,
                unit_price=entry.unit_price,
                purchased_at=entry.purchased_at,
                opened_at=utcnow(),
            )
            session.add(opened)
            await session.flush()
            session.add(StockTxn(type="open", product_id=product.id, entry_id=opened.id, amount=remaining, actor=actor))
            remaining = 0
        else:
            entry.opened_at = utcnow()
            remaining -= entry.amount
            session.add(StockTxn(type="open", product_id=product.id, entry_id=entry.id, amount=entry.amount, actor=actor))
    await session.commit()
    hub.publish("stock", product_id=product.id)


async def undo(session: AsyncSession, hub: EventHub, txn_id: int) -> None:
    txn = await session.get(StockTxn, txn_id)
    if txn is None:
        raise NotFound(f"Transaction {txn_id} not found")
    if txn.undone:
        raise Invalid("Already undone")
    entry = await session.get(StockEntry, txn.entry_id) if txn.entry_id else None
    if txn.type == "purchase":
        if entry is None or entry.amount + _EPSILON < txn.amount:
            raise Invalid("Part of this purchase was already used; consume it instead")
        entry.amount = round(entry.amount - txn.amount, 6)
    elif txn.type in ("consume", "spoil"):
        if entry is None:
            raise Invalid("The stock entry no longer exists")
        entry.amount = round(entry.amount + txn.amount, 6)
    elif txn.type == "open":
        if entry is None or entry.opened_at is None:
            raise Invalid("The opened stock entry no longer exists")
        entry.opened_at = None
        # A lot that was split when opening goes back into its unopened sibling.
        sibling = await session.scalar(
            select(StockEntry).where(
                StockEntry.id != entry.id, StockEntry.product_id == entry.product_id, StockEntry.opened_at.is_(None),
                StockEntry.due_date.is_(entry.due_date) if entry.due_date is None else StockEntry.due_date == entry.due_date,
                StockEntry.purchased_at == entry.purchased_at, StockEntry.amount > 0,
            )
        )  # fmt: skip
        if sibling is not None:
            sibling.amount = round(sibling.amount + entry.amount, 6)
            entry.amount = 0
    else:
        raise Invalid(f"Cannot undo a {txn.type} transaction")
    txn.undone = True
    await session.commit()
    hub.publish("stock", product_id=txn.product_id)


async def journal(session: AsyncSession, limit: int = 100) -> list[StockTxnOut]:
    rows = (
        await session.execute(
            select(StockTxn, Product.name)
            .join(Product, Product.id == StockTxn.product_id)
            .order_by(StockTxn.at.desc(), StockTxn.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        StockTxnOut(
            id=txn.id,
            type=txn.type,
            product_id=txn.product_id,
            product_name=name,
            amount=txn.amount,
            unit_price=txn.unit_price,
            at=txn.at,
            actor=txn.actor,
            source=txn.source,
            undone=txn.undone,
        )
        for txn, name in rows
    ]


async def _auto_add_to_shopping_list(session: AsyncSession, product: Product) -> None:
    """Grocy behaviour: falling below min stock puts the product on the shopping list."""
    if product.min_stock <= 0:
        return
    await session.flush()
    amount = sum(e.amount for e in await _entries(session, product.id))
    if amount + _EPSILON >= product.min_stock:
        return
    from .shopping import ensure_on_list  # local import: shopping imports stock

    await ensure_on_list(session, product, product.min_stock - amount)


async def txn_ids_after(session: AsyncSession, after_id: int) -> list[int]:
    """Ledger ids written since `after_id`, so callers can offer an exact undo."""
    return list((await session.scalars(select(StockTxn.id).where(StockTxn.id > after_id).order_by(StockTxn.id))).all())


async def last_txn_id(session: AsyncSession) -> int:
    return await session.scalar(select(func.max(StockTxn.id))) or 0
