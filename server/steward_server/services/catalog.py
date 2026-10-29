"""Products and locations."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Barcode, Location, Product, ReceiptAlias, StockEntry
from ..schemas import LocationIn, LocationPatch, ProductIn, ProductPatch
from ..textnorm import normalize_receipt_text
from . import Invalid, NotFound


async def list_locations(session: AsyncSession) -> list[Location]:
    return list((await session.scalars(select(Location).order_by(Location.name))).all())


async def _unique_name(session: AsyncSession, name: str, location_id: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise Invalid("A location needs a name")
    for other in await list_locations(session):
        if other.id != location_id and other.name.casefold() == name.casefold():
            raise Invalid(f"There is already a location called {other.name}")
    return name


async def get_location(session: AsyncSession, location_id: int) -> Location:
    location = await session.get(Location, location_id)
    if location is None:
        raise NotFound(f"Location {location_id} not found")
    return location


async def create_location(session: AsyncSession, hub: EventHub, data: LocationIn) -> Location:
    location = Location(name=await _unique_name(session, data.name), is_freezer=data.is_freezer)
    session.add(location)
    await session.commit()
    hub.publish("catalog")
    return location


async def update_location(session: AsyncSession, hub: EventHub, location_id: int, patch: LocationPatch) -> Location:
    location = await get_location(session, location_id)
    if patch.name is not None:
        location.name = await _unique_name(session, patch.name, location_id)
    if patch.is_freezer is not None:
        location.is_freezer = patch.is_freezer
    await session.commit()
    hub.publish("catalog")
    return location


async def delete_location(session: AsyncSession, hub: EventHub, location_id: int) -> None:
    """Products and lots that were there keep existing, without a location."""
    location = await get_location(session, location_id)
    await session.execute(update(Product).where(Product.location_id == location_id).values(location_id=None))
    await session.execute(update(StockEntry).where(StockEntry.location_id == location_id).values(location_id=None))
    await session.delete(location)
    await session.commit()
    hub.publish("catalog")
    hub.publish("stock")


async def list_products(session: AsyncSession) -> list[Product]:
    return list((await session.scalars(select(Product).order_by(Product.name))).all())


async def get_product(session: AsyncSession, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFound(f"Product {product_id} not found")
    return product


async def find_product_by_name(session: AsyncSession, name: str) -> Product | None:
    wanted = name.strip().casefold()
    for product in await list_products(session):
        if product.name.casefold() == wanted:
            return product
    return None


async def create_product(session: AsyncSession, hub: EventHub, data: ProductIn, chain: str = "REWE") -> Product:
    product = Product(**data.model_dump(exclude={"barcodes", "receipt_aliases"}))
    product.barcodes = [Barcode(code=code) for code in data.barcodes]
    session.add(product)
    await session.flush()
    for alias in data.receipt_aliases:
        session.add(ReceiptAlias(chain=chain, normalized=normalize_receipt_text(alias), product_id=product.id))
    await session.commit()
    hub.publish("catalog")
    return product


async def update_product(session: AsyncSession, hub: EventHub, product_id: int, patch: ProductPatch) -> Product:
    product = await get_product(session, product_id)
    for key, value in patch.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    await session.commit()
    hub.publish("catalog")
    hub.publish("stock")
    return product


async def delete_product(session: AsyncSession, hub: EventHub, product_id: int) -> None:
    await session.delete(await get_product(session, product_id))
    await session.commit()
    hub.publish("catalog")
    hub.publish("stock")
