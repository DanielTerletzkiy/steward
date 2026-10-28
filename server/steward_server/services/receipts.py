"""Receipts: import REWE eBons, match lines to products, put purchases into stock."""

from __future__ import annotations

import hashlib
from datetime import datetime

from rapidfuzz import fuzz, process
from rewe_ebon_parser.parse import parse_ebon
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Product, Receipt, ReceiptAlias, ReceiptLine
from ..schemas import LineMatchIn, ReceiptSummaryOut
from ..textnorm import as_receipt_name, normalize_receipt_text
from ..timeutil import LOCAL_TZ, as_utc, today
from . import Invalid, NotFound
from .catalog import create_product, get_product
from .shopping import tick_off_products
from .stock import purchase

CHAIN = "REWE"
# Fuzzy matches at or above this score are pre-filled as suggestions; below, the line stays unknown.
SUGGEST_SCORE = 80


def classify(text: str) -> str:
    upper = text.upper()
    if upper.startswith("PFAND"):
        return "deposit"
    if upper.startswith("LEERGUT"):
        return "deposit_return"
    if "TASCHE" in upper or "TUETE" in upper:
        return "bag"
    return "item"


async def _match_candidates(session: AsyncSession) -> dict[str, int]:
    """Receipt-style names -> product id, from learned aliases and product names."""
    candidates = {as_receipt_name(p.name): p.id for p in (await session.scalars(select(Product))).all()}
    for alias in (await session.scalars(select(ReceiptAlias).where(ReceiptAlias.chain == CHAIN))).all():
        candidates[alias.normalized] = alias.product_id
    return candidates


async def match_line(session: AsyncSession, line: ReceiptLine, candidates: dict[str, int] | None = None) -> None:
    """Fill in product, confidence and method for one line (confirmed lines are left alone)."""
    if line.kind != "item" or line.confirmed:
        return
    normalized = normalize_receipt_text(line.raw_text)
    alias = await session.scalar(
        select(ReceiptAlias).where(ReceiptAlias.chain == CHAIN, ReceiptAlias.normalized == normalized)
    )
    if alias is not None:
        line.product_id, line.confidence, line.method, line.confirmed = alias.product_id, 1.0, "alias", True
        alias.hits += 1
        return
    candidates = candidates if candidates is not None else await _match_candidates(session)
    best = process.extractOne(normalized, list(candidates), scorer=fuzz.WRatio) if candidates else None
    if best and best[1] >= SUGGEST_SCORE:
        line.product_id, line.confidence, line.method = candidates[best[0]], round(best[1] / 100, 2), "fuzzy"
    else:
        line.product_id, line.confidence, line.method = None, 0.0, None


async def import_ebon(session: AsyncSession, hub: EventHub, pdf: bytes, *, source: str = "upload") -> Receipt:
    """Parse a REWE eBon PDF and store it with matched lines. Importing the same PDF twice is a no-op."""
    external_id = hashlib.sha256(pdf).hexdigest()
    existing = await session.scalar(select(Receipt).where(Receipt.external_id == external_id))
    if existing is not None:
        return existing
    try:
        data = parse_ebon(pdf)
    except Exception as exc:  # the parser raises plain exceptions on unknown layouts
        raise Invalid(f"Could not read this eBon: {exc}") from exc
    address = data.get("marketAddress") or {}
    store = " ".join(part for part in (address.get("street"), address.get("city")) if part) or None
    receipt = Receipt(
        external_id=external_id,
        chain=CHAIN,
        store=f"REWE {store}" if store else "REWE",
        at=datetime.fromisoformat(data["datetime_utc"]),
        total=float(data["total"]),
        payment=", ".join(g["type"] for g in data.get("given") or []) or None,
        loyalty=(data.get("loyalty") or {}).get("program"),
        source=source,
    )
    for idx, item in enumerate(data.get("items") or []):
        receipt.lines.append(
            ReceiptLine(
                idx=idx,
                raw_text=item["name"],
                qty=float(item.get("amount") or 1),
                unit=item.get("unit"),
                unit_price=item.get("pricePerUnit"),
                total=float(item["subTotal"]),
                tax=item.get("taxCategory"),
                kind=classify(item["name"]),
            )
        )
    session.add(receipt)
    await session.flush()
    candidates = await _match_candidates(session)
    for line in receipt.lines:
        await match_line(session, line, candidates)
    await session.commit()
    hub.publish("receipts", receipt_id=receipt.id)
    return receipt


async def get_receipt(session: AsyncSession, receipt_id: int) -> Receipt:
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFound(f"Receipt {receipt_id} not found")
    return receipt


async def list_receipts(session: AsyncSession) -> list[ReceiptSummaryOut]:
    receipts = (await session.scalars(select(Receipt).order_by(Receipt.at.desc()))).all()
    result = []
    for r in receipts:
        items = [line for line in r.lines if line.kind == "item"]
        matched = sum(1 for line in items if line.product_id)
        result.append(
            ReceiptSummaryOut(
                id=r.id,
                chain=r.chain,
                store=r.store,
                at=as_utc(r.at),
                total=r.total,
                stocked=r.stocked,
                line_count=len(items),
                matched=matched,
                unmatched=len(items) - matched,
            )
        )
    return result


async def set_line_product(
    session: AsyncSession, hub: EventHub, receipt_id: int, line_id: int, data: LineMatchIn
) -> ReceiptLine:
    """Confirm or correct a line. The receipt text is learned as an alias for the product."""
    line = await session.get(ReceiptLine, line_id)
    if line is None or line.receipt_id != receipt_id:
        raise NotFound(f"Line {line_id} not found on receipt {receipt_id}")
    if data.new_product is not None:
        product = await create_product(session, hub, data.new_product)
    elif data.product_id is not None:
        product = await get_product(session, data.product_id)
    else:
        raise Invalid("Give product_id or new_product")
    line.product_id, line.confidence, line.method, line.confirmed = product.id, 1.0, "manual", True
    normalized = normalize_receipt_text(line.raw_text)
    alias = await session.scalar(
        select(ReceiptAlias).where(ReceiptAlias.chain == CHAIN, ReceiptAlias.normalized == normalized)
    )
    if alias is None:
        session.add(ReceiptAlias(chain=CHAIN, normalized=normalized, product_id=product.id, hits=1))
    else:
        alias.product_id = product.id
    await session.flush()
    # The new alias may resolve the same text on other receipts that are still open.
    open_lines = (
        await session.scalars(
            select(ReceiptLine).where(ReceiptLine.confirmed.is_(False), ReceiptLine.kind == "item")
        )
    ).all()
    for other in open_lines:
        await match_line(session, other)
    await session.commit()
    hub.publish("receipts", receipt_id=receipt_id)
    return line


async def stock_receipt(session: AsyncSession, hub: EventHub, receipt_id: int, actor: str | None = None) -> int:
    """Put every matched item line into stock at its receipt price. Returns the number of lines stocked."""
    receipt = await get_receipt(session, receipt_id)
    if receipt.stocked:
        raise Invalid("This receipt is already in stock")
    stocked, products = 0, set()
    for line in receipt.lines:
        if line.kind != "item" or line.product_id is None:
            continue
        qty = line.qty if line.qty > 0 else 1
        await purchase(
            session,
            hub,
            line.product_id,
            qty,
            unit_price=round(line.total / qty, 4),
            actor=actor,
            source="receipt",
            receipt_line_id=line.id,
            at=as_utc(receipt.at),
            commit=False,
        )
        stocked += 1
        products.add(line.product_id)
    await tick_off_products(session, products)
    receipt.stocked = True
    await session.commit()
    hub.publish("receipts", receipt_id=receipt.id)
    hub.publish("stock")
    hub.publish("shopping")
    return stocked


async def spending(session: AsyncSession) -> dict:
    """Spending this month and the last trip, in the household's time zone."""
    receipts = (await session.scalars(select(Receipt).order_by(Receipt.at.desc()))).all()
    now = today()
    month = [r for r in receipts if as_utc(r.at).astimezone(LOCAL_TZ).date().replace(day=1) == now.replace(day=1)]
    last = receipts[0] if receipts else None
    deposit = sum(
        line.total for r in receipts for line in r.lines if line.kind in ("deposit", "deposit_return")
    )
    return {
        "month_total": round(sum(r.total for r in month), 2),
        "month_trips": len(month),
        "total_spent": round(sum(r.total for r in receipts), 2),
        "deposit_balance": round(deposit, 2),
        "last_trip": {
            "receipt_id": last.id,
            "store": last.store,
            "at": as_utc(last.at).isoformat(),
            "total": last.total,
            "items": sum(1 for line in last.lines if line.kind == "item"),
        }
        if last
        else None,
    }
