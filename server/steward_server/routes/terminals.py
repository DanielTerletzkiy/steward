"""Kitchen terminals: pairing and removing them, and what the kiosk page and its helper on the Pi need.

Terminals themselves can only reach the /api/kiosk/... routes here (see services.terminals.ALLOWED)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import supervisor
from ..api import Hub, Session, require_auth, terminal_id
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


# --- the helper on the Pi (Bluetooth pairing) ---------------------------------


class AgentCommandIn(BaseModel):
    type: str
    args: dict[str, Any] = {}


class AgentResultIn(BaseModel):
    ok: bool
    result: Any = None
    error: str | None = None


class AgentHello(BaseModel):
    version: str | None = None
    bluetooth: bool | None = None


def _terminal(request: Request) -> int:
    found = terminal_id(request.headers, request.app.state.terminals)
    if found is None:
        raise HTTPException(403, "Only a kitchen terminal can do this")
    return found


@router.get("/kiosk/agent")
async def agent_status(request: Request) -> dict[str, Any]:
    return request.app.state.agents.status(_terminal(request))


@router.post("/kiosk/agent/commands")
async def agent_command(request: Request, body: AgentCommandIn) -> dict[str, Any]:
    return request.app.state.agents.send(_terminal(request), body.type, body.args).out()


@router.get("/kiosk/agent/commands/{command_id}")
async def agent_command_status(request: Request, command_id: int) -> dict[str, Any]:
    return request.app.state.agents.get(_terminal(request), command_id).out()


@router.post("/kiosk/agent/next")
async def agent_next(request: Request, body: AgentHello, wait: float = 25):
    """The helper's long poll: the next command, or 204 after `wait` seconds."""
    command = await request.app.state.agents.next(_terminal(request), wait, body.model_dump(exclude_none=True))
    if command is None:
        return Response(status_code=204)
    return {"id": command.id, "type": command.type, "args": command.args}


@router.post("/kiosk/agent/commands/{command_id}/result", status_code=204)
async def agent_result(request: Request, command_id: int, body: AgentResultIn) -> None:
    request.app.state.agents.report(_terminal(request), command_id, body.ok, body.result, body.error)
