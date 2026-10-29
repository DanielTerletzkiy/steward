"""Kitchen terminals: pairing and removing them, and what the kiosk page needs.

Terminals themselves can only reach /api/kiosk/frequent here (see services.terminals.ALLOWED)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import supervisor
from ..api import Hub, Session, require_auth
from ..schemas import ProductOut, TerminalIn, TerminalPairOut, TerminalsOut
from ..services import stock, terminals

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/terminals", response_model=TerminalsOut)
async def list_terminals(request: Request, session: Session):
    return TerminalsOut(
        terminals=await terminals.list_terminals(session, request.app.state.terminals),
        direct_url=await supervisor.direct_url(request.app.state.settings),
    )


@router.post("/terminals", response_model=TerminalPairOut)
async def create_terminal(session: Session, hub: Hub, body: TerminalIn):
    return await terminals.create(session, hub, body.name)


@router.post("/terminals/{terminal_id}/code", response_model=TerminalPairOut)
async def new_pairing_code(session: Session, hub: Hub, terminal_id: int):
    return await terminals.new_code(session, hub, terminal_id)


@router.delete("/terminals/{terminal_id}", status_code=204)
async def delete_terminal(request: Request, session: Session, hub: Hub, terminal_id: int) -> None:
    await terminals.delete(session, hub, request.app.state.terminals, terminal_id)


@router.get("/kiosk/frequent", response_model=list[ProductOut])
async def frequent(session: Session, limit: int = 12):
    return await stock.frequent_without_barcode(session, limit)
