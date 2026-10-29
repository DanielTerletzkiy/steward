"""German bottle deposit (Pfand) on receipts: how many bottles or cans a deposit line stands for.

REWE prints the deposit right after its item, as "PFAND 0,25 EURO" per bottle or one line for a pack
("PFAND 1,50 EURO" = 6 x 0,25 EUR one-way bottles). Returns are "LEERGUT EINWEG" with one unit per bottle.
"""

from __future__ import annotations

import re

ONE_WAY = 0.25  # Einweg bottles and cans
REUSABLE = (0.08, 0.15)  # Mehrweg bottles; their crate adds 1,50 EUR
CRATE = 1.50
MONEY = re.compile(r"(\d+)[,.](\d{2})")
# "6X1,5L", "4 X 150G", "10X0,33": a pack size printed in the item text.
PACK_IN_NAME = re.compile(r"(?<![\d,.])(\d{1,2})\s*[Xx]\s*\d")


def _cents(value: float) -> int:
    return round(value * 100)


def bottles_per_deposit(amount: float) -> int | None:
    """Bottles in one deposit of this amount: 0,25 -> 1, 1,50 -> 6, 3,10 -> 20 (crate). None if it doesn't add up."""
    cents = _cents(amount)
    if cents <= 0:
        return None
    if cents % _cents(ONE_WAY) == 0:
        return cents // _cents(ONE_WAY)
    for bottle in REUSABLE:
        rest = cents - _cents(CRATE)
        if rest > 0 and rest % _cents(bottle) == 0:
            return rest // _cents(bottle)
        if cents % _cents(bottle) == 0:
            return cents // _cents(bottle)
    return None


def line_bottles(kind: str, raw_text: str, qty: float, unit_price: float | None, total: float) -> int | None:
    """Bottles behind a deposit or bottle-return line."""
    if kind not in ("deposit", "deposit_return"):
        return None
    count = qty if qty > 0 else 1
    if kind == "deposit_return":
        # "LEERGUT EINWEG 26 Stk x 0,25": one unit per bottle. A single line without a count is its money.
        if count > 1 or unit_price:
            return round(count)
        per = bottles_per_deposit(abs(total))
        return per
    match = MONEY.search(raw_text)
    amount = int(match[1]) + int(match[2]) / 100 if match else (unit_price or abs(total) / count)
    per = bottles_per_deposit(amount)
    return round(per * count) if per else None


def pieces_from_name(raw_text: str) -> int | None:
    match = PACK_IN_NAME.search(raw_text)
    if match and 2 <= (pieces := int(match[1])) <= 48:
        return pieces
    return None
