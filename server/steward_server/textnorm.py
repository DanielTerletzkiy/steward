"""Normalization of receipt article texts.

REWE prints article names in upper case, transliterates umlauts (Ä -> AE, ß -> SS) and cuts
them to 16 characters, so product names are normalized the same way before comparing.
"""

from __future__ import annotations

import re

RECEIPT_NAME_LENGTH = 16

_TRANSLITERATION = str.maketrans({"Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "SS", "ẞ": "SS"})
_SPACES = re.compile(r"\s+")


def normalize_receipt_text(text: str) -> str:
    return _SPACES.sub(" ", text.upper().translate(_TRANSLITERATION)).strip()


def as_receipt_name(product_name: str) -> str:
    """How a product name would likely look on a receipt."""
    return normalize_receipt_text(product_name)[:RECEIPT_NAME_LENGTH].rstrip()
