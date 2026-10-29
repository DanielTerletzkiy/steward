"""Receipts: import REWE eBons, match lines to products, put purchases into stock."""

from __future__ import annotations

import hashlib
from datetime import datetime

from rapidfuzz import fuzz, process
from rewe_ebon_parser.parse import parse_ebon
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..deposit import pieces_from_name
from ..models import Product, Receipt, ReceiptAlias, ReceiptLine, ReceiptPack
from ..schemas import AliasMovedOut, LineMatchIn, ProductAliasesOut, ReceiptAliasOut, ReceiptSummaryOut
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
    await fill_pieces(session, receipt.lines)
    candidates = await _match_candidates(session)
    for line in receipt.lines:
        await match_line(session, line, candidates)
    await session.commit()
    hub.publish("receipts", receipt_id=receipt.id)
    return receipt


def _price_cents(line: ReceiptLine) -> int:
    """Price of one unit of the line, which tells a pack from a single item with the same text."""
    qty = line.qty if line.qty > 0 else 1
    return round(line.total / qty * 100)


async def fill_pieces(session: AsyncSession, lines: list[ReceiptLine], *, force: bool = False) -> None:
    """Work out pieces per unit for item lines: learned for this text and price, else from the deposit
    line that follows (PFAND 1,50 EURO = 6 bottles), else from the text ("6X1,5L"), else 1."""
    ordered = sorted(lines, key=lambda line: line.idx)
    learned = {
        (pack.normalized, pack.price_cents): pack.pieces
        for pack in (await session.scalars(select(ReceiptPack).where(ReceiptPack.chain == CHAIN))).all()
    }
    for i, line in enumerate(ordered):
        if line.kind != "item" or (line.pieces is not None and not force) or line.pieces_source == "manual":
            continue
        qty = line.qty if line.qty > 0 else 1
        after = ordered[i + 1] if i + 1 < len(ordered) else None
        bottles = after.bottles if after is not None and after.kind == "deposit" else None
        if (pieces := learned.get((normalize_receipt_text(line.raw_text), _price_cents(line)))) is not None:
            line.pieces, line.pieces_source = pieces, "learned"
        elif bottles and bottles / qty >= 1 and bottles % qty == 0:
            line.pieces, line.pieces_source = bottles / qty, "deposit"
        elif (pieces := pieces_from_name(line.raw_text)) is not None:
            line.pieces, line.pieces_source = float(pieces), "name"
        else:
            line.pieces, line.pieces_source = 1.0, None


async def backfill_pieces(session: AsyncSession) -> None:
    """Receipts imported before pieces per pack existed."""
    receipt_ids = (
        await session.scalars(
            select(ReceiptLine.receipt_id).where(ReceiptLine.kind == "item", ReceiptLine.pieces.is_(None)).distinct()
        )
    ).all()
    for receipt_id in receipt_ids:
        receipt = await session.get(Receipt, receipt_id)
        if receipt is not None:
            await fill_pieces(session, receipt.lines)
    if receipt_ids:
        await session.commit()


async def set_line_pieces(
    session: AsyncSession, hub: EventHub, receipt_id: int, line_id: int, pieces: float
) -> ReceiptLine:
    """Correct pieces per pack. Remembered for this receipt text at this price, and applied to open receipts."""
    line = await session.get(ReceiptLine, line_id)
    if line is None or line.receipt_id != receipt_id or line.kind != "item":
        raise NotFound(f"Item line {line_id} not found on receipt {receipt_id}")
    line.pieces, line.pieces_source = pieces, "manual"
    normalized, price = normalize_receipt_text(line.raw_text), _price_cents(line)
    pack = await session.scalar(
        select(ReceiptPack).where(
            ReceiptPack.chain == CHAIN, ReceiptPack.normalized == normalized, ReceiptPack.price_cents == price
        )
    )
    if pack is None:
        session.add(ReceiptPack(chain=CHAIN, normalized=normalized, price_cents=price, pieces=pieces))
    else:
        pack.pieces = pieces
    await session.flush()
    open_receipts = (await session.scalars(select(Receipt).where(Receipt.stocked.is_(False)))).all()
    for receipt in open_receipts:
        same = [
            other
            for other in receipt.lines
            if other.id != line.id
            and other.pieces_source != "manual"
            and normalize_receipt_text(other.raw_text) == normalized
            and _price_cents(other) == price
        ]
        for other in same:
            other.pieces, other.pieces_source = pieces, "learned"
    await session.commit()
    hub.publish("receipts", receipt_id=receipt_id)
    return line


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
    await _rematch_open_lines(session)
    await session.commit()
    hub.publish("receipts", receipt_id=receipt_id)
    return line


async def _rematch_open_lines(session: AsyncSession) -> None:
    open_lines = (
        await session.scalars(
            select(ReceiptLine).where(ReceiptLine.confirmed.is_(False), ReceiptLine.kind == "item")
        )
    ).all()
    for line in open_lines:
        await match_line(session, line)


async def list_aliases(session: AsyncSession) -> list[ReceiptAlias]:
    return list(
        (await session.scalars(select(ReceiptAlias).where(ReceiptAlias.chain == CHAIN).order_by(ReceiptAlias.normalized))).all()
    )


async def set_product_aliases(
    session: AsyncSession, hub: EventHub, product_id: int, texts: list[str]
) -> ProductAliasesOut:
    """Replace the receipt texts of a product. A text another product had moves to this one;
    lines on receipts not yet stocked that were matched by a changed text are matched again."""
    product = await get_product(session, product_id)
    wanted = list(dict.fromkeys(n for n in (normalize_receipt_text(t) for t in texts) if n))
    aliases = (
        await session.scalars(
            select(ReceiptAlias).where(
                ReceiptAlias.chain == CHAIN,
                (ReceiptAlias.product_id == product.id) | ReceiptAlias.normalized.in_(wanted),
            )
        )
    ).all()
    by_text = {a.normalized: a for a in aliases}
    changed: set[str] = set()
    moved: list[AliasMovedOut] = []
    for alias in aliases:
        if alias.product_id == product.id and alias.normalized not in wanted:
            changed.add(alias.normalized)
            await session.delete(alias)
    for text in wanted:
        alias = by_text.get(text)
        if alias is None:
            session.add(ReceiptAlias(chain=CHAIN, normalized=text, product_id=product.id, hits=0))
        elif alias.product_id != product.id:
            previous = await session.get(Product, alias.product_id)
            moved.append(AliasMovedOut(text=text, product_id=alias.product_id, product_name=previous.name if previous else ""))
            alias.product_id = product.id
            changed.add(text)
    await session.flush()
    if changed:
        # Lines matched by a removed or moved text, on receipts not yet stocked, are matched afresh.
        matched = (
            await session.scalars(
                select(ReceiptLine)
                .join(Receipt, Receipt.id == ReceiptLine.receipt_id)
                .where(Receipt.stocked.is_(False), ReceiptLine.method == "alias", ReceiptLine.confirmed.is_(True))
            )
        ).all()
        for line in matched:
            if normalize_receipt_text(line.raw_text) in changed:
                line.confirmed = False
    await _rematch_open_lines(session)
    await session.commit()
    hub.publish("receipts")
    hub.publish("catalog")
    current = (
        await session.scalars(
            select(ReceiptAlias)
            .where(ReceiptAlias.chain == CHAIN, ReceiptAlias.product_id == product.id)
            .order_by(ReceiptAlias.normalized)
        )
    ).all()
    return ProductAliasesOut(aliases=[ReceiptAliasOut.model_validate(a) for a in current], moved=moved)


async def delete_receipt(session: AsyncSession, hub: EventHub, receipt_id: int) -> None:
    """Remove a receipt and its lines. What was already put into stock stays there."""
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFound(f"Receipt {receipt_id} not found")
    await session.delete(receipt)
    await session.commit()
    hub.publish("receipts")


async def stock_receipt(session: AsyncSession, hub: EventHub, receipt_id: int, actor: str | None = None) -> int:
    """Put every matched item line into stock at its receipt price. Returns the number of lines stocked."""
    receipt = await get_receipt(session, receipt_id)
    if receipt.stocked:
        raise Invalid("This receipt is already in stock")
    stocked, products = 0, set()
    for line in receipt.lines:
        if line.kind != "item" or line.product_id is None:
            continue
        # A 6-pack bought once goes into stock as 6 bottles.
        amount = (line.qty if line.qty > 0 else 1) * (line.pieces or 1)
        await purchase(
            session,
            hub,
            line.product_id,
            amount,
            unit_price=round(line.total / amount, 4),
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
    deposit_lines = [line for r in receipts for line in r.lines if line.kind in ("deposit", "deposit_return")]
    bought = sum(line.bottles or 0 for line in deposit_lines if line.kind == "deposit")
    returned = sum(line.bottles or 0 for line in deposit_lines if line.kind == "deposit_return")
    return {
        "month_total": round(sum(r.total for r in month), 2),
        "month_trips": len(month),
        "total_spent": round(sum(r.total for r in receipts), 2),
        # Money paid as deposit minus money back for returns, and the same in bottles and cans.
        "deposit_balance": round(sum(line.total for line in deposit_lines), 2),
        "deposit_bottles": {"bought": bought, "returned": returned, "open": bought - returned},
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
