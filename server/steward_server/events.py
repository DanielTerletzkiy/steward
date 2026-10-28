"""In-process event hub that feeds WebSocket subscribers (the HA integration and the web UI)."""

from __future__ import annotations

import asyncio
from typing import Any

# Topics a client can expect. Each change publishes the topic of the data that changed.
TOPICS = ("stock", "shopping", "chores", "tasks", "receipts", "people", "catalog", "equipment", "wardrobe", "settings", "recipes", "mealplan")


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, topic: str, **data: Any) -> None:
        event = {"type": "event", "topic": topic, "data": data}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stuck client loses events; it resyncs on reconnect.
                self._subscribers.discard(queue)
