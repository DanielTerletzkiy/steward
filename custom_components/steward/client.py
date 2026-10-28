"""Minimal async client for the Steward server. Moves to the steward-client PyPI package later."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import LOGGER


class StewardError(Exception):
    """The server answered with an error or could not be reached."""


class StewardAuthError(StewardError):
    """The token was rejected."""


class StewardClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self.url = url.rstrip("/") + "/"
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            async with self._session.request(
                method, self.url + path, headers=headers, timeout=aiohttp.ClientTimeout(total=30), **kwargs
            ) as resp:
                if resp.status == 401:
                    raise StewardAuthError("Invalid token")
                if resp.status >= 400:
                    detail = await resp.text()
                    raise StewardError(f"{method} {path} failed ({resp.status}): {detail}")
                if resp.status == 204:
                    return None
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise StewardError(f"Cannot reach Steward at {self.url}: {err}") from err

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params or None)

    async def post(self, path: str, json: Any = None, actor: str | None = None) -> Any:
        return await self.request("POST", path, json=json, headers=_actor(actor))

    async def put(self, path: str, json: Any = None) -> Any:
        return await self.request("PUT", path, json=json)

    async def patch(self, path: str, json: Any) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def upload_receipt(self, filename: str, data: bytes) -> Any:
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="application/pdf")
        return await self.request("POST", "api/receipts", data=form)

    async def listen(self, on_event: Callable[[dict[str, Any]], Awaitable[None] | None]) -> None:
        """Stream server events forever, reconnecting with backoff. Cancel the task to stop."""
        delay = 1
        ws_url = self.url.replace("http", "ws", 1) + "api/ws"
        while True:
            try:
                async with self._session.ws_connect(ws_url, headers=self._headers, heartbeat=30) as ws:
                    LOGGER.debug("Connected to Steward events")
                    delay = 1
                    # Anything may have changed while we were away.
                    await _call(on_event, {"type": "event", "topic": "*"})
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            payload = msg.json()
                            if payload.get("type") == "event":
                                await _call(on_event, payload)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep reconnecting whatever happened
                LOGGER.debug("Steward event stream dropped: %s", err)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


def _actor(actor: str | None) -> dict[str, str]:
    return {"X-Steward-Actor": actor} if actor else {}


async def _call(callback: Callable[[dict[str, Any]], Awaitable[None] | None], payload: dict[str, Any]) -> None:
    result = callback(payload)
    if asyncio.iscoroutine(result):
        await result
