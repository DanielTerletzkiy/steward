"""Shopping lists."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Product, ShoppingItem, ShoppingList
from ..schemas import ShoppingItemIn, ShoppingItemPatch
from . import Invalid, NotFound
from .catalog import find_product_by_name, get_product

DEFAULT_LIST_NAME = "Shopping list"


async def lists(session: AsyncSession) -> list[ShoppingList]:
    result = list((await session.scalars(select(ShoppingList).order_by(ShoppingList.id))).all())
    if not result:
        default = ShoppingList(name=DEFAULT_LIST_NAME)
        session.add(default)
        await session.commit()
        result = [default]
    return result


async def default_list(session: AsyncSession) -> ShoppingList:
    return (await lists(session))[0]


async def items(session: AsyncSession, list_id: int) -> list[ShoppingItem]:
    query = (
        select(ShoppingItem)
        .where(ShoppingItem.list_id == list_id)
        .order_by(ShoppingItem.done, ShoppingItem.created_at)
    )
    return list((await session.scalars(query)).all())


async def add_item(session: AsyncSession, hub: EventHub, list_id: int, data: ShoppingItemIn) -> ShoppingItem:
    if await session.get(ShoppingList, list_id) is None:
        raise NotFound(f"Shopping list {list_id} not found")
    product: Product | None = None
    if data.product_id is not None:
        product = await get_product(session, data.product_id)
    elif data.text:
        # Free text that names a known product gets linked, so buying it can tick it off.
        product = await find_product_by_name(session, data.text)
    text = data.text or (product.name if product else None)
    if not text:
        raise Invalid("Give a text or a product")
    item = ShoppingItem(
        list_id=list_id, product_id=product.id if product else None, text=text, amount=data.amount, note=data.note
    )
    session.add(item)
    await session.commit()
    hub.publish("shopping", list_id=list_id)
    return item


async def update_item(session: AsyncSession, hub: EventHub, item_id: int, patch: ShoppingItemPatch) -> ShoppingItem:
    item = await session.get(ShoppingItem, item_id)
    if item is None:
        raise NotFound(f"Item {item_id} not found")
    values = patch.model_dump(exclude_unset=True)
    if "text" in values and not (values["text"] or "").strip():
        raise Invalid("Text must not be empty")
    if "amount" in values and not (values["amount"] or 0) > 0:
        raise Invalid("Amount must be more than 0")
    if values.get("done") is None:
        values.pop("done", None)
    for key, value in values.items():
        setattr(item, key, value)
    await session.commit()
    hub.publish("shopping", list_id=item.list_id)
    return item


async def delete_item(session: AsyncSession, hub: EventHub, item_id: int) -> None:
    item = await session.get(ShoppingItem, item_id)
    if item is None:
        raise NotFound(f"Item {item_id} not found")
    await session.delete(item)
    await session.commit()
    hub.publish("shopping", list_id=item.list_id)


async def clear_done(session: AsyncSession, hub: EventHub, list_id: int) -> int:
    done = [item for item in await items(session, list_id) if item.done]
    for item in done:
        await session.delete(item)
    await session.commit()
    hub.publish("shopping", list_id=list_id)
    return len(done)


async def is_on_list(session: AsyncSession, product_id: int) -> bool:
    """Whether the product is on any shopping list and not ticked off yet."""
    found = await session.scalar(
        select(ShoppingItem.id).where(ShoppingItem.product_id == product_id, ShoppingItem.done.is_(False)).limit(1)
    )
    return found is not None


async def ensure_on_list(session: AsyncSession, product: Product, amount: float) -> None:
    """Put a product on the default list unless it is already there (not done). Caller commits."""
    target = await default_list(session)
    existing = await session.scalar(
        select(ShoppingItem).where(
            ShoppingItem.list_id == target.id, ShoppingItem.product_id == product.id, ShoppingItem.done.is_(False)
        )
    )
    if existing is None:
        session.add(ShoppingItem(list_id=target.id, product_id=product.id, text=product.name, amount=round(amount, 3)))


async def add_missing(session: AsyncSession, hub: EventHub, list_id: int | None = None) -> int:
    """Add every product below its min stock. Returns how many were added."""
    from .stock import stock_overview  # stock imports shopping lazily too

    target = await session.get(ShoppingList, list_id) if list_id else await default_list(session)
    if target is None:
        raise NotFound(f"Shopping list {list_id} not found")
    open_products = {i.product_id for i in await items(session, target.id) if not i.done and i.product_id}
    added = 0
    for item in await stock_overview(session, include_empty=True):
        if item.below_min and item.product.id not in open_products:
            session.add(
                ShoppingItem(
                    list_id=target.id,
                    product_id=item.product.id,
                    text=item.product.name,
                    amount=round(item.product.min_stock - item.amount, 3),
                )
            )
            added += 1
    await session.commit()
    hub.publish("shopping", list_id=target.id)
    return added


async def tick_off_products(session: AsyncSession, product_ids: set[int]) -> int:
    """Mark open items for these products as done (after a purchase). Caller commits."""
    if not product_ids:
        return 0
    open_items = (
        await session.scalars(
            select(ShoppingItem).where(ShoppingItem.product_id.in_(product_ids), ShoppingItem.done.is_(False))
        )
    ).all()
    for item in open_items:
        item.done = True
    return len(open_items)
