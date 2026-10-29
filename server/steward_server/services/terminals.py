"""Kitchen terminals: a browser (e.g. a Raspberry Pi in kiosk mode) that pairs once with a short code
and then stays signed in with a cookie. A terminal may only use the stock and scanning endpoints."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Terminal
from ..schemas import TerminalOut, TerminalPairOut
from ..timeutil import as_utc, utcnow
from . import Invalid, NotFound

COOKIE = "steward_terminal"
COOKIE_DAYS = 3650
PAIR_MINUTES = 15
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I

# What a terminal may call, as (method, path pattern). Everything else answers 403.
ALLOWED = [
    (method, re.compile(pattern))
    for method, pattern in [
        ("GET", r"/api/(info|me|summary|locations|products|stock|shopping-lists|kiosk/frequent)"),
        ("GET", r"/api/shopping-lists/\d+/items"),
        ("GET", r"/api/scan/lookup"),
        ("GET", r"/api/files/\d+(/thumb)?"),
        ("POST", r"/api/scan"),
        ("POST", r"/api/stock/(purchase|consume|open)"),
        ("POST", r"/api/stock/undo/\d+"),
        ("PATCH", r"/api/stock/entries/\d+"),
        ("POST", r"/api/products"),
        ("POST", r"/api/products/\d+/barcodes"),
        ("POST", r"/api/shopping-lists/\d+/items"),
        ("DELETE", r"/api/shopping-items/\d+"),  # undo of "To list"
    ]
]


def allowed(method: str, path: str) -> bool:
    return any(method == m and pattern.fullmatch(path) for m, pattern in ALLOWED)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


class Registry:
    """The paired terminals' secret hashes, kept in memory so checking a request needs no database.
    Also remembers when each terminal was last seen; listing the terminals writes that back."""

    def __init__(self) -> None:
        self.secrets: dict[int, str] = {}
        self.seen: dict[int, datetime] = {}

    async def load(self, session: AsyncSession) -> None:
        rows = (await session.scalars(select(Terminal).where(Terminal.secret_hash.is_not(None)))).all()
        self.secrets = {t.id: t.secret_hash for t in rows if t.secret_hash}

    def identify(self, cookie_value: str | None) -> int | None:
        if not cookie_value or "." not in cookie_value:
            return None
        raw_id, secret = cookie_value.split(".", 1)
        if not raw_id.isdigit():
            return None
        expected = self.secrets.get(int(raw_id))
        if expected is None or not secrets.compare_digest(expected, _hash(secret)):
            return None
        self.seen[int(raw_id)] = utcnow()
        return int(raw_id)


def _out(terminal: Terminal) -> TerminalOut:
    return TerminalOut(
        id=terminal.id, name=terminal.name, paired=terminal.secret_hash is not None,
        created_at=terminal.created_at, last_seen=terminal.last_seen,
    )  # fmt: skip


def _pair_code(terminal: Terminal) -> str:
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    terminal.pair_code_hash = _hash(code)
    terminal.pair_expires = utcnow() + timedelta(minutes=PAIR_MINUTES)
    return f"{code[:4]}-{code[4:]}"


async def list_terminals(session: AsyncSession, registry: Registry) -> list[TerminalOut]:
    rows = (await session.scalars(select(Terminal).order_by(Terminal.name, Terminal.id))).all()
    for terminal in rows:
        seen = registry.seen.get(terminal.id)
        if seen and (terminal.last_seen is None or as_utc(terminal.last_seen) < seen):
            terminal.last_seen = seen
    await session.commit()
    return [_out(t) for t in rows]


async def create(session: AsyncSession, hub: EventHub, name: str) -> TerminalPairOut:
    name = name.strip()
    if not name:
        raise Invalid("Give the terminal a name")
    terminal = Terminal(name=name)
    code = _pair_code(terminal)
    session.add(terminal)
    await session.commit()
    hub.publish("terminals")
    return TerminalPairOut(terminal=_out(terminal), code=code, expires=terminal.pair_expires)


async def new_code(session: AsyncSession, hub: EventHub, terminal_id: int) -> TerminalPairOut:
    terminal = await session.get(Terminal, terminal_id)
    if terminal is None:
        raise NotFound("Terminal not found")
    code = _pair_code(terminal)
    await session.commit()
    hub.publish("terminals")
    return TerminalPairOut(terminal=_out(terminal), code=code, expires=terminal.pair_expires)


async def delete(session: AsyncSession, hub: EventHub, registry: Registry, terminal_id: int) -> None:
    terminal = await session.get(Terminal, terminal_id)
    if terminal is None:
        raise NotFound("Terminal not found")
    await session.delete(terminal)
    await session.commit()
    registry.secrets.pop(terminal_id, None)
    registry.seen.pop(terminal_id, None)
    hub.publish("terminals")


async def redeem(session: AsyncSession, hub: EventHub, registry: Registry, code: str) -> str:
    """Pair a browser: returns the cookie value. A new pairing signs out the browser paired before."""
    normalized = _normalize_code(code)
    terminal = (
        await session.scalars(select(Terminal).where(Terminal.pair_code_hash == _hash(normalized)))
    ).first() if len(normalized) == 8 else None
    if terminal is None or terminal.pair_expires is None or as_utc(terminal.pair_expires) < utcnow():
        raise Invalid("This pairing code is wrong or has expired. Create a new one in Steward → Settings → Kitchen terminals.")
    secret = secrets.token_urlsafe(32)
    terminal.secret_hash = _hash(secret)
    terminal.pair_code_hash = None
    terminal.pair_expires = None
    terminal.last_seen = utcnow()
    await session.commit()
    registry.secrets[terminal.id] = terminal.secret_hash
    hub.publish("terminals")
    return f"{terminal.id}.{secret}"


async def names(session: AsyncSession) -> dict[int, str]:
    return {t.id: t.name for t in (await session.scalars(select(Terminal))).all()}
