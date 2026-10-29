"""REST routes. Each one is a thin wrapper around a service function."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from . import API_VERSION, __version__
from .auth import read_cookie, session_user
from .config import SUPERVISOR_INGRESS_IP, Settings
from .events import EventHub
from .ha_bridge import HABridge
from .schemas import (
    ChoreExecuteIn,
    ChoreIn,
    ChoreOut,
    ChorePatch,
    ConsumeIn,
    EntryMoveIn,
    EntryPatch,
    LineMatchIn,
    LinePiecesIn,
    LocationIn,
    LocationOut,
    LocationPatch,
    OpenIn,
    PersonIn,
    PersonOut,
    ProductAliasesIn,
    ProductAliasesOut,
    ProductIn,
    ProductOut,
    ProductPatch,
    PurchaseIn,
    ReceiptAliasOut,
    ReceiptLineOut,
    ReceiptOut,
    ReceiptSummaryOut,
    ShoppingItemIn,
    ShoppingItemOut,
    ShoppingItemPatch,
    ShoppingListOut,
    StockEntryOut,
    StockItemOut,
    StockTxnOut,
    TaskIn,
    TaskOut,
    TaskPatch,
)
from .services import catalog, chores, people, receipts, shopping, stock, summary, tasks, terminals
from .services.files import FileStore
from .services.terminals import COOKIE as TERMINAL_COOKIE
from .services.terminals import Registry


def is_authorized(
    request_headers, client_host: str | None, query_token: str | None, settings: Settings, registry: Registry | None = None
) -> bool:
    """Bearer token, HA ingress (only from the Supervisor's proxy), a "Sign in with Home Assistant"
    session cookie, a paired kitchen terminal, or trust-all for local development."""
    if settings.trust_all:
        return True
    auth = request_headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else query_token
    if token and secrets.compare_digest(token, settings.api_token):
        return True
    if _ingress_user(request_headers, client_host):
        return True
    if session_user(request_headers, settings) is not None:
        return True
    return terminal_id(request_headers, registry) is not None


def terminal_id(headers, registry: Registry | None) -> int | None:
    """The paired kitchen terminal making this request, if it is one."""
    if registry is None:
        return None
    return registry.identify(read_cookie(headers, TERMINAL_COOKIE))


def _ingress_user(headers, client_host: str | None) -> dict[str, str] | None:
    if client_host != SUPERVISOR_INGRESS_IP or not headers.get("x-remote-user-id"):
        return None
    return {
        "uid": headers["x-remote-user-id"],
        "name": headers.get("x-remote-user-display-name") or headers.get("x-remote-user-name") or "",
    }


def current_user(request: Request) -> dict[str, str] | None:
    host = request.client.host if request.client else None
    return _ingress_user(request.headers, host) or session_user(request.headers, request.app.state.settings)


async def require_auth(request: Request) -> None:
    host = request.client.host if request.client else None
    settings: Settings = request.app.state.settings
    token = request.query_params.get("token")
    if is_authorized(request.headers, host, token, settings):
        return
    # A kitchen terminal: only the stock and scanning endpoints.
    if terminal_id(request.headers, request.app.state.terminals) is None:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    if not terminals.allowed(request.method, request.url.path):
        raise HTTPException(status_code=403, detail="A kitchen terminal can't do this")


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessions() as session:
        yield session


def get_hub(request: Request) -> EventHub:
    return request.app.state.hub


def get_bridge(request: Request) -> HABridge:
    return request.app.state.bridge


def get_files(request: Request) -> FileStore:
    return request.app.state.files


def get_actor(request: Request) -> str | None:
    """Who is acting: what the integration passes along, else the signed-in HA user or the terminal."""
    if actor := request.headers.get("x-steward-actor"):
        return actor
    user = current_user(request)
    if user:
        return user["uid"]
    terminal = terminal_id(request.headers, request.app.state.terminals)
    return f"terminal:{terminal}" if terminal is not None else None


Session = Annotated[AsyncSession, Depends(get_session)]
Hub = Annotated[EventHub, Depends(get_hub)]
Actor = Annotated[str | None, Depends(get_actor)]
Files = Annotated[FileStore, Depends(get_files)]
Bridge = Annotated[HABridge, Depends(get_bridge)]

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/info")
async def info() -> dict:
    return {"name": "Steward", "version": __version__, "api_version": API_VERSION}


@router.get("/me")
async def me(request: Request) -> dict:
    """Who the UI is talking as (null for API tokens and the local trust-all mode)."""
    user = current_user(request)
    settings = request.app.state.settings
    return {
        "user": {"id": user["uid"], "name": user["name"]} if user else None,
        "can_sign_out": user is not None and session_user(request.headers, settings) is not None,
        "app": settings.is_app,
    }


@router.get("/summary")
async def get_summary(session: Session) -> dict:
    return await summary.summary(session)


# --- people ---------------------------------------------------------------


@router.get("/people", response_model=list[PersonOut])
async def list_people(session: Session):
    return await people.list_people(session)


@router.put("/people", response_model=list[PersonOut])
async def sync_people(session: Session, hub: Hub, body: list[PersonIn]):
    return await people.sync(session, hub, body)


# --- catalog --------------------------------------------------------------


@router.get("/locations", response_model=list[LocationOut])
async def list_locations(session: Session):
    return await catalog.list_locations(session)


@router.post("/locations", response_model=LocationOut)
async def create_location(session: Session, hub: Hub, body: LocationIn):
    return await catalog.create_location(session, hub, body)


@router.patch("/locations/{location_id}", response_model=LocationOut)
async def update_location(session: Session, hub: Hub, location_id: int, body: LocationPatch):
    return await catalog.update_location(session, hub, location_id, body)


@router.delete("/locations/{location_id}", status_code=204)
async def delete_location(session: Session, hub: Hub, location_id: int) -> None:
    await catalog.delete_location(session, hub, location_id)


@router.get("/products", response_model=list[ProductOut])
async def list_products(session: Session):
    return await catalog.list_products(session)


@router.post("/products", response_model=ProductOut)
async def create_product(session: Session, hub: Hub, body: ProductIn):
    product = await catalog.create_product(session, hub, body.model_copy(update={"receipt_aliases": []}))
    if body.receipt_aliases:
        await receipts.set_product_aliases(session, hub, product.id, body.receipt_aliases)
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(session: Session, hub: Hub, product_id: int, body: ProductPatch):
    return await catalog.update_product(session, hub, product_id, body)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(session: Session, hub: Hub, product_id: int) -> None:
    await catalog.delete_product(session, hub, product_id)


@router.put("/products/{product_id}/aliases", response_model=ProductAliasesOut)
async def set_product_aliases(session: Session, hub: Hub, product_id: int, body: ProductAliasesIn):
    return await receipts.set_product_aliases(session, hub, product_id, body.texts)


@router.get("/receipt-aliases", response_model=list[ReceiptAliasOut])
async def list_receipt_aliases(session: Session):
    return await receipts.list_aliases(session)


# --- stock ----------------------------------------------------------------


@router.get("/stock", response_model=list[StockItemOut])
async def get_stock(session: Session, include_empty: bool = False):
    return await stock.stock_overview(session, include_empty=include_empty)


@router.get("/stock/journal", response_model=list[StockTxnOut])
async def get_journal(session: Session, limit: int = 100):
    return await stock.journal(session, limit)


@router.post("/stock/purchase")
async def post_purchase(session: Session, hub: Hub, actor: Actor, body: PurchaseIn) -> dict:
    before = await stock.last_txn_id(session)
    entry = await stock.purchase(
        session,
        hub,
        body.product_id,
        body.amount,
        due_date=body.due_date,
        location_id=body.location_id,
        unit_price=body.unit_price,
        actor=actor,
    )
    return {"entry_id": entry.id, "txn_ids": await stock.txn_ids_after(session, before)}


@router.post("/stock/consume")
async def post_consume(session: Session, hub: Hub, actor: Actor, body: ConsumeIn) -> dict:
    before = await stock.last_txn_id(session)
    taken = await stock.consume(session, hub, body.product_id, body.amount, spoiled=body.spoiled, actor=actor)
    return {"consumed": taken, "txn_ids": await stock.txn_ids_after(session, before)}


@router.post("/stock/open")
async def post_open(session: Session, hub: Hub, actor: Actor, body: OpenIn) -> dict:
    before = await stock.last_txn_id(session)
    await stock.open_product(session, hub, body.product_id, body.amount, actor=actor)
    return {"txn_ids": await stock.txn_ids_after(session, before)}


@router.patch("/stock/entries/{entry_id}", response_model=StockEntryOut)
async def edit_entry(session: Session, hub: Hub, actor: Actor, entry_id: int, body: EntryPatch):
    return await stock.edit_entry(session, hub, entry_id, body, actor)


@router.put("/stock/entries/{entry_id}/location", response_model=StockEntryOut)
async def move_entry(session: Session, hub: Hub, entry_id: int, body: EntryMoveIn):
    return await stock.move_entry(session, hub, entry_id, body.location_id)


@router.post("/stock/undo/{txn_id}", status_code=204)
async def post_undo(session: Session, hub: Hub, txn_id: int) -> None:
    await stock.undo(session, hub, txn_id)


# --- shopping -------------------------------------------------------------


@router.get("/shopping-lists", response_model=list[ShoppingListOut])
async def get_lists(session: Session):
    return await shopping.lists(session)


@router.get("/shopping-lists/{list_id}/items", response_model=list[ShoppingItemOut])
async def get_items(session: Session, list_id: int):
    return await shopping.items(session, list_id)


@router.post("/shopping-lists/{list_id}/items", response_model=ShoppingItemOut)
async def add_item(session: Session, hub: Hub, list_id: int, body: ShoppingItemIn):
    return await shopping.add_item(session, hub, list_id, body)


@router.post("/shopping-lists/{list_id}/add-missing")
async def add_missing(session: Session, hub: Hub, list_id: int) -> dict:
    return {"added": await shopping.add_missing(session, hub, list_id)}


@router.post("/shopping-lists/{list_id}/clear-done")
async def clear_done(session: Session, hub: Hub, list_id: int) -> dict:
    return {"removed": await shopping.clear_done(session, hub, list_id)}


@router.patch("/shopping-items/{item_id}", response_model=ShoppingItemOut)
async def update_item(session: Session, hub: Hub, item_id: int, body: ShoppingItemPatch):
    return await shopping.update_item(session, hub, item_id, body)


@router.delete("/shopping-items/{item_id}", status_code=204)
async def delete_item(session: Session, hub: Hub, item_id: int) -> None:
    await shopping.delete_item(session, hub, item_id)


# --- chores ---------------------------------------------------------------


@router.get("/chores", response_model=list[ChoreOut])
async def list_chores(session: Session):
    return await chores.list_chores(session)


@router.post("/chores", response_model=ChoreOut)
async def create_chore(session: Session, hub: Hub, body: ChoreIn):
    return await chores.create_chore(session, hub, body)


@router.patch("/chores/{chore_id}", response_model=ChoreOut)
async def update_chore(session: Session, hub: Hub, chore_id: int, body: ChorePatch):
    return await chores.update_chore(session, hub, chore_id, body)


@router.delete("/chores/{chore_id}", status_code=204)
async def delete_chore(session: Session, hub: Hub, chore_id: int) -> None:
    await chores.delete_chore(session, hub, chore_id)


@router.post("/chores/{chore_id}/execute", response_model=ChoreOut)
async def execute_chore(session: Session, hub: Hub, chore_id: int, body: ChoreExecuteIn | None = None):
    body = body or ChoreExecuteIn()
    return await chores.execute(session, hub, chore_id, person_id=body.person_id, skipped=body.skipped)


@router.get("/chores/history")
async def chore_history(session: Session, chore_id: int | None = None, limit: int = 100) -> list[dict]:
    return [
        {"id": log.id, "chore_id": log.chore_id, "done_at": log.done_at, "done_by": log.done_by, "skipped": log.skipped}
        for log in await chores.history(session, chore_id, limit)
    ]


# --- tasks ----------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(session: Session, include_done: bool = True):
    return await tasks.list_tasks(session, include_done)


@router.post("/tasks", response_model=TaskOut)
async def create_task(session: Session, hub: Hub, body: TaskIn):
    return await tasks.create_task(session, hub, body)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(session: Session, hub: Hub, task_id: int, body: TaskPatch):
    return await tasks.update_task(session, hub, task_id, body)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(session: Session, hub: Hub, task_id: int) -> None:
    await tasks.delete_task(session, hub, task_id)


# --- receipts -------------------------------------------------------------


@router.get("/receipts", response_model=list[ReceiptSummaryOut])
async def list_receipts(session: Session):
    return await receipts.list_receipts(session)


@router.post("/receipts", response_model=ReceiptOut)
async def upload_receipt(session: Session, hub: Hub, file: UploadFile = File(...)):
    return await receipts.import_ebon(session, hub, await file.read())


@router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
async def get_receipt(session: Session, receipt_id: int):
    return await receipts.get_receipt(session, receipt_id)


@router.put("/receipts/{receipt_id}/lines/{line_id}", response_model=ReceiptLineOut)
async def match_line(session: Session, hub: Hub, receipt_id: int, line_id: int, body: LineMatchIn):
    return await receipts.set_line_product(session, hub, receipt_id, line_id, body)


@router.put("/receipts/{receipt_id}/lines/{line_id}/pieces", response_model=ReceiptLineOut)
async def set_line_pieces(session: Session, hub: Hub, receipt_id: int, line_id: int, body: LinePiecesIn):
    return await receipts.set_line_pieces(session, hub, receipt_id, line_id, body.pieces)


@router.delete("/receipts/{receipt_id}", status_code=204)
async def delete_receipt(session: Session, hub: Hub, receipt_id: int) -> None:
    await receipts.delete_receipt(session, hub, receipt_id)


@router.post("/receipts/{receipt_id}/stock")
async def stock_receipt(session: Session, hub: Hub, actor: Actor, receipt_id: int) -> dict:
    return {"stocked": await receipts.stock_receipt(session, hub, receipt_id, actor)}
