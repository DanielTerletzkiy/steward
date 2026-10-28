"""Time helpers. All timestamps are stored timezone-aware in UTC."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))


def utcnow() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    """The household's local date."""
    return datetime.now(LOCAL_TZ).date()


def as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; values read back are UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
