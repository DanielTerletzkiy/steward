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
from .api import is_authorized, router
from .config import Settings, load_settings
from .db import Database
from .events import EventHub
from .services import ServiceError

LOG = logging.getLogger("steward")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.db_url)
        await db.create_all()
        app.state.settings, app.state.db, app.state.hub = settings, db, EventHub()
        if settings.seed_demo:
            from .seed import seed_demo

            async with db.sessions() as session:
                await seed_demo(session, app.state.hub, settings.demo_receipts_dir)
        LOG.info("Steward %s ready, data in %s", __version__, settings.data_dir)
        yield
        await db.dispose()

    app = FastAPI(title="Steward", version=__version__, lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.websocket("/api/ws")
    async def events(websocket: WebSocket) -> None:
        host = websocket.client.host if websocket.client else None
        if not is_authorized(websocket.headers, host, websocket.query_params.get("token"), settings):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        hub: EventHub = websocket.app.state.hub
        queue = hub.subscribe()
        await websocket.send_json({"type": "hello", "version": __version__, "api_version": API_VERSION})
        # Clients only listen; this task notices when they hang up.
        receiver = asyncio.create_task(_drain(websocket))
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


async def _drain(websocket: WebSocket) -> None:
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host="0.0.0.0", port=8095, proxy_headers=False)


if __name__ == "__main__":
    run()
