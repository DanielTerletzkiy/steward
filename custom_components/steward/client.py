"""Minimal async client for the Steward server. Moves to the steward-client PyPI package later."""

from __future__ import annotations

import asyncio
import json
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
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def request(self, method: str, path: str, timeout_total: float = 30, **kwargs: Any) -> Any:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            async with self._session.request(
                method, self.url + path, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_total), **kwargs
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

    async def post(self, path: str, json: Any = None, actor: str | None = None, timeout_total: float = 30) -> Any:
        return await self.request("POST", path, timeout_total=timeout_total, json=json, headers=_actor(actor))

    async def put(self, path: str, json: Any = None) -> Any:
        return await self.request("PUT", path, json=json)

    async def patch(self, path: str, json: Any) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def get_bytes(self, path: str) -> bytes:
        try:
            async with self._session.get(
                self.url + path, headers=self._headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    raise StewardError(f"GET {path} failed ({resp.status})")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise StewardError(f"Cannot reach Steward at {self.url}: {err}") from err

    async def upload(self, path: str, files: list[tuple[str, bytes, str]], **fields: str) -> Any:
        """Multipart POST: files as (name, bytes, content type) under the field "files"."""
        form = aiohttp.FormData()
        for name, data, content_type in files:
            form.add_field("files", data, filename=name, content_type=content_type)
        for key, value in fields.items():
            form.add_field(key, value)
        return await self.request("POST", path, data=form, timeout_total=180)

    async def upload_receipt(self, filename: str, data: bytes) -> Any:
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="application/pdf")
        return await self.request("POST", "api/receipts", data=form)

    async def listen(
        self,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None],
        hello: Callable[[], dict[str, Any]] | None = None,
        on_request: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> None:
        """Stream server events forever, reconnecting with backoff. Cancel the task to stop.

        With `hello` and `on_request`, the connection also carries requests from the server to HA
        (AI Task, weather); each is answered on its own task so slow AI calls don't block events.
        """
        delay = 1
        ws_url = self.url.replace("http", "ws", 1) + "api/ws"
        while True:
            tasks: set[asyncio.Task] = set()
            try:
                async with self._session.ws_connect(ws_url, headers=self._headers, heartbeat=30) as ws:
                    LOGGER.debug("Connected to Steward events")
                    self._ws = ws
                    delay = 1
                    if hello is not None:
                        await ws.send_str(json.dumps(hello()))
                    # Anything may have changed while we were away.
                    await _call(on_event, {"type": "event", "topic": "*"})
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            payload = msg.json()
                            if payload.get("type") == "event":
                                await _call(on_event, payload)
                            elif payload.get("type") == "ha_request" and on_request is not None:
                                task = asyncio.create_task(_answer(ws, payload, on_request))
                                tasks.add(task)
                                task.add_done_callback(tasks.discard)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                self._ws = None
                for task in tasks:
                    task.cancel()
                raise
            except Exception as err:  # noqa: BLE001 - keep reconnecting whatever happened
                LOGGER.debug("Steward event stream dropped: %s", err)
            self._ws = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


    async def send(self, payload: dict[str, Any]) -> None:
        """Send a message on the event stream, if it is connected (e.g. an updated hello)."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps(payload, default=str))


async def _answer(ws: aiohttp.ClientWebSocketResponse, request: dict[str, Any], handler) -> None:
    reply: dict[str, Any] = {"type": "ha_response", "id": request.get("id")}
    try:
        reply["result"] = await handler(request)
    except Exception as err:  # noqa: BLE001 - every failure goes back to the server as an error
        LOGGER.warning("Steward request %s failed: %s", request.get("op"), err)
        reply["error"] = str(err) or type(err).__name__
    if not ws.closed:
        await ws.send_str(json.dumps(reply, default=str))


def _actor(actor: str | None) -> dict[str, str]:
    return {"X-Steward-Actor": actor} if actor else {}


async def _call(callback: Callable[[dict[str, Any]], Awaitable[None] | None], payload: dict[str, Any]) -> None:
    result = callback(payload)
    if asyncio.iscoroutine(result):
        await result
