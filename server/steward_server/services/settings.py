"""Settings edited in the UI, stored as JSON rows."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Setting


async def get(session: AsyncSession, key: str, default: Any = None) -> Any:
    row = await session.get(Setting, key)
    return default if row is None or row.value is None else row.value


async def put(session: AsyncSession, hub: EventHub | None, key: str, value: Any) -> Any:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    await session.commit()
    if hub is not None:
        hub.publish("settings", key=key)
    return value
