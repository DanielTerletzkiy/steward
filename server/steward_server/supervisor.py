"""Home Assistant app mode: announce the server to HA through the Supervisor's discovery API."""

from __future__ import annotations

import logging
import socket

import httpx

from .config import Settings

LOG = logging.getLogger("steward.supervisor")
SUPERVISOR = "http://supervisor"
PORT = 8095


async def announce(settings: Settings) -> None:
    """HA then shows "Discovered: Steward"; one click sets up the integration with this token."""
    if not settings.is_app:
        return
    payload = {"service": "steward", "config": {"host": socket.gethostname(), "port": PORT, "token": settings.api_token}}
    headers = {"Authorization": f"Bearer {settings.supervisor_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{SUPERVISOR}/discovery", json=payload, headers=headers)
            response.raise_for_status()
        LOG.info("Announced to Home Assistant as %s:%s", payload["config"]["host"], PORT)
    except httpx.HTTPError as err:
        LOG.warning("Could not announce to Home Assistant: %s", err)
