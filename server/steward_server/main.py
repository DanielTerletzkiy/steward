"""Application factory: REST API, WebSocket event stream and the web UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import API_VERSION, __version__
from . import supervisor
from .api import is_authorized, router
from .auth import router as auth_router
from .config import Settings, load_settings
from .db import Database
from .events import EventHub
from .ha_bridge import HABridge
from .routes import equipment as equipment_routes
from .routes import files as file_routes
from .routes import recipes as recipe_routes
from .routes import scan as scan_routes
from .routes import settings as settings_routes
from .routes import terminals as terminal_routes
from .routes import wardrobe as wardrobe_routes
from .services import ServiceError, receipts
from .services.files import FileStore
from .services.terminals import Registry

LOG = logging.getLogger("steward")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.db_url)
        await db.create_all()
        app.state.settings, app.state.db, app.state.hub = settings, db, EventHub()
        app.state.files = FileStore(settings.data_dir)
        app.state.bridge = HABridge()
        app.state.terminals = Registry()
        async with db.sessions() as session:
            await receipts.backfill_pieces(session)
            await app.state.terminals.load(session)
        if settings.seed_demo:
            from .seed import seed_demo

            async with db.sessions() as session:
                await seed_demo(session, app.state.hub, app.state.files, settings.demo_receipts_dir)
        LOG.info("Steward %s ready, data in %s", __version__, settings.data_dir)
        await supervisor.announce(settings)
        stop = asyncio.Event()
        housekeeping = asyncio.create_task(_housekeeping(db, app.state.hub, stop))
        yield
        # Let a running job finish: cancelling it in the middle of a database call can hang the shutdown.
        stop.set()
        await housekeeping
        await db.dispose()

    app = FastAPI(title="Steward", version=__version__, lifespan=lifespan)
    app.include_router(router)
    app.include_router(auth_router)
    for module in (file_routes, equipment_routes, wardrobe_routes, scan_routes, settings_routes, recipe_routes, terminal_routes):
        app.include_router(module.router)

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.websocket("/api/ws")
    async def events(websocket: WebSocket) -> None:
        host = websocket.client.host if websocket.client else None
        await websocket.accept()
        token = websocket.query_params.get("token")
        if not is_authorized(websocket.headers, host, token, settings, websocket.app.state.terminals):
            # Accept first: a close before the handshake reaches the browser as 1006, not 4401.
            await websocket.close(code=4401)
            return
        hub: EventHub = websocket.app.state.hub
        queue = hub.subscribe()
        await websocket.send_json({"type": "hello", "version": __version__, "api_version": API_VERSION})
        # Clients mostly listen. The HA integration also answers requests from the server (HABridge).
        bridge: HABridge = websocket.app.state.bridge
        receiver = asyncio.create_task(_receive(websocket, bridge, queue))
        try:
            while not receiver.done():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    await websocket.send_json(getter.result())
                else:
                    getter.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unsubscribe(queue)
            bridge.unregister(queue)
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receiver

    if STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            # Single-page app: unknown paths get index.html; the router in the browser takes over.
            candidate = STATIC_DIR / path
            if path and candidate.is_file() and STATIC_DIR in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


async def _housekeeping(db: Database, hub: EventHub, stop: asyncio.Event) -> None:
    """Small periodic jobs: drying clothes become available again, new eBons are fetched from email."""
    from .services import mail, wardrobe

    while True:
        for job in (wardrobe.release_dried, mail.run_if_due):
            try:
                async with db.sessions() as session:
                    await job(session, hub)
            except Exception:  # noqa: BLE001 - keep the loop alive; the next round retries
                LOG.exception("Housekeeping failed")
            if stop.is_set():
                return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), 300)
        if stop.is_set():
            return


async def _receive(websocket: WebSocket, bridge: HABridge, queue: asyncio.Queue) -> None:
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "ping":
                queue.put_nowait({"type": "pong"})
            elif kind == "ha_hello":
                bridge.register(queue, message.get("capabilities") or [], message.get("info") or {})
                LOG.info("Home Assistant connected (%s)", ", ".join(message.get("capabilities") or []) or "no extras")
                websocket.app.state.hub.publish("settings", key="home_assistant")
            elif kind == "ha_response":
                bridge.resolve(message)


def run() -> None:
    import uvicorn

    settings = load_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8095, proxy_headers=False, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
