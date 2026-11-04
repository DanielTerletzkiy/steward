"""The kitchen terminal's helper on the Raspberry Pi, and the relay to it.

A web page can't pair a Bluetooth barcode scanner: Web Bluetooth and WebHID refuse keyboard-like devices,
and pairing is a system matter anyway. So the setup script installs a small helper next to Chromium
(kiosk/steward-kiosk-agent). It signs in as the terminal and long-polls Steward for commands; the kiosk
page sends commands through Steward and polls for the result. The browser never talks to the Pi
directly, and nothing here is stored: a restart forgets pending commands, which the page then reports
as timed out.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field
from typing import Any

from . import Invalid, NotFound

COMMANDS = {"bt_status", "bt_scan", "bt_pair", "bt_remove"}
ONLINE_SECONDS = 60  # a helper that polled within this is "connected"
KEEP_SECONDS = 300  # finished commands are forgotten after this


@dataclass
class Command:
    id: int
    terminal_id: int
    type: str
    args: dict[str, Any]
    created: float = field(default_factory=time.monotonic)
    status: str = "pending"  # pending → running → done / failed
    result: Any = None
    error: str | None = None

    def out(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "status": self.status, "result": self.result, "error": self.error}


class AgentHub:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._commands: dict[int, Command] = {}
        self._queues: dict[int, asyncio.Queue[Command]] = {}
        self._last_poll: dict[int, float] = {}
        self._info: dict[int, dict[str, Any]] = {}

    def _queue(self, terminal_id: int) -> asyncio.Queue[Command]:
        return self._queues.setdefault(terminal_id, asyncio.Queue())

    def _prune(self) -> None:
        cutoff = time.monotonic() - KEEP_SECONDS
        for cid in [c.id for c in self._commands.values() if c.created < cutoff]:
            del self._commands[cid]

    def status(self, terminal_id: int) -> dict[str, Any]:
        last = self._last_poll.get(terminal_id)
        return {
            "connected": last is not None and time.monotonic() - last < ONLINE_SECONDS,
            "info": self._info.get(terminal_id, {}),
        }

    def send(self, terminal_id: int, kind: str, args: dict[str, Any]) -> Command:
        if kind not in COMMANDS:
            raise Invalid(f"Unknown command {kind}")
        self._prune()
        command = Command(next(self._ids), terminal_id, kind, args)
        self._commands[command.id] = command
        self._queue(terminal_id).put_nowait(command)
        return command

    def get(self, terminal_id: int, command_id: int) -> Command:
        command = self._commands.get(command_id)
        if command is None or command.terminal_id != terminal_id:
            raise NotFound("Command not found (Steward may have restarted)")
        return command

    async def next(self, terminal_id: int, wait: float, info: dict[str, Any] | None = None) -> Command | None:
        """The helper asks for work; waits up to `wait` seconds for a command."""
        self._last_poll[terminal_id] = time.monotonic()
        if info:
            self._info[terminal_id] = info
        queue = self._queue(terminal_id)
        try:
            command = queue.get_nowait() if not queue.empty() else await asyncio.wait_for(queue.get(), timeout=max(0.0, min(wait, 30.0)))
        except TimeoutError:
            return None
        finally:
            self._last_poll[terminal_id] = time.monotonic()
        command.status = "running"
        return command

    def report(self, terminal_id: int, command_id: int, ok: bool, result: Any = None, error: str | None = None) -> None:
        command = self.get(terminal_id, command_id)
        command.status = "done" if ok else "failed"
        command.result = result
        command.error = None if ok else (error or "Failed")
