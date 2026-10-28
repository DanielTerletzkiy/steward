"""Products and locations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Barcode, Location, Product, ReceiptAlias
from ..schemas import LocationIn, ProductIn, ProductPatch
from ..textnorm import normalize_receipt_text
from . import NotFound


async def list_locations(session: AsyncSession) -> list[Location]:
    return list((await session.scalars(select(Location).order_by(Location.name))).all())


async def create_location(session: AsyncSession, hub: EventHub, data: LocationIn) -> Location:
    location = Location(name=data.name, is_freezer=data.is_freezer)
    session.add(location)
    await session.commit()
    hub.publish("catalog")
    return location


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
