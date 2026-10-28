"""Requests from the server to Home Assistant, carried by the integration's WebSocket.

The integration says hello with what it can do ("ai_task", "weather"). The server then puts requests
into that connection's outgoing queue and waits for the matching response. This works the same on
HA OS and on HA Container, and the server never needs an HA token.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

from .services import ServiceError


class BridgeUnavailable(ServiceError):
    status = 503


class BridgeError(ServiceError):
    status = 502


class HABridge:
    def __init__(self) -> None:
        self._links: dict[asyncio.Queue, set[str]] = {}
        self._pending: dict[int, tuple[asyncio.Queue, asyncio.Future]] = {}
        self._ids = itertools.count(1)
        self.info: dict[str, Any] = {}  # what the integration told us about HA (location, time zone, ...)

    def register(self, queue: asyncio.Queue, capabilities: list[str], info: dict[str, Any] | None = None) -> None:
        self._links[queue] = set(capabilities)
        self.info = info or {}

    def unregister(self, queue: asyncio.Queue) -> None:
        self._links.pop(queue, None)
        for request_id, (owner, future) in list(self._pending.items()):
            if owner is queue and not future.done():
                future.set_exception(BridgeUnavailable("Home Assistant disconnected"))
                self._pending.pop(request_id, None)

    def can(self, capability: str) -> bool:
        return any(capability in caps for caps in self._links.values())

    @property
    def connected(self) -> bool:
        return bool(self._links)

    def resolve(self, message: dict[str, Any]) -> None:
        entry = self._pending.pop(message.get("id"), None)
        if entry is None or entry[1].done():
            return
        if message.get("error"):
            entry[1].set_exception(BridgeError(str(message["error"])))
        else:
            entry[1].set_result(message.get("result"))

    async def request(self, op: str, timeout: float = 120, **payload: Any) -> Any:
        queue = next((q for q, caps in self._links.items() if op in caps), None)
        if queue is None:
            raise BridgeUnavailable(f"Home Assistant is not connected (needed for {op})")
        request_id = next(self._ids)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (queue, future)
        queue.put_nowait({"type": "ha_request", "id": request_id, "op": op, **payload})
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as err:
            raise BridgeError(f"Home Assistant did not answer the {op} request in time") from err
        finally:
            self._pending.pop(request_id, None)
