"""Home Assistant app mode: announce the server to HA through the Supervisor's discovery API."""

from __future__ import annotations

import logging
import socket
from urllib.parse import urlsplit

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


async def direct_url(settings: Settings) -> str | None:
    """Where the web UI is reachable without ingress: the host port set in the app's Network section,
    on the host that HA itself is reached at. None when no port is set (or outside the app)."""
    if not settings.is_app:
        return None
    headers = {"Authorization": f"Bearer {settings.supervisor_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{SUPERVISOR}/addons/self/info", headers=headers)
            response.raise_for_status()
            network = response.json().get("data", {}).get("network") or {}
    except (httpx.HTTPError, ValueError) as err:
        LOG.warning("Could not read the app's network settings: %s", err)
        return None
    port = network.get(f"{PORT}/tcp")
    if not port:
        return None
    host = urlsplit(settings.ha_public_url).hostname if settings.ha_public_url else None
    return f"http://{host or 'homeassistant.local'}:{port}"
