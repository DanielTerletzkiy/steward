"""Sign in with Home Assistant, for the web UI outside HA ingress (HA Container installs, kiosks).

HA's own OAuth flow (IndieAuth style, the server's address is the client id):
1. /auth/login sends the browser to HA's /auth/authorize page.
2. HA sends it back to /auth/callback with a code; the server exchanges it for a token, asks HA
   who the user is, revokes the token again and sets a signed session cookie.
Nothing from HA is stored except the user's id and name.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .config import Settings

COOKIE = "steward_session"
SESSION_DAYS = 30
STATE_SECONDS = 600

router = APIRouter(prefix="/auth", include_in_schema=False)


def _key(settings: Settings) -> bytes:
    return hashlib.sha256(b"steward-session:" + settings.api_token.encode()).digest()


def sign(settings: Settings, payload: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(_key(settings), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def verify(settings: Settings, value: str | None) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    if not hmac.compare_digest(mac, hmac.new(_key(settings), body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    return payload if payload.get("exp", 0) > time.time() else None


def read_cookie(headers, name: str) -> str | None:
    raw = headers.get("cookie")
    if not raw:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:  # noqa: BLE001 - a malformed cookie header is simply no cookie
        return None
    morsel = cookie.get(name)
    return morsel.value if morsel else None


def session_user(headers, settings: Settings) -> dict[str, Any] | None:
    user = verify(settings, read_cookie(headers, COOKIE))
    return user if user and user.get("kind") == "session" else None


def _origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _safe_next(value: str | None) -> str:
    # Only in-app destinations (hash routes) - never another site.
    return value if value and value.startswith("#/") else "#/"


@router.get("/login")
async def login(request: Request, next: str | None = None):
    settings: Settings = request.app.state.settings
    if not settings.ha_url:
        return HTMLResponse(_page("Sign-in is not set up", "Set STEWARD_HA_URL so Steward knows where Home Assistant is."), 503)
    origin = _origin(request)
    state = sign(settings, {"kind": "state", "next": _safe_next(next), "nonce": secrets.token_hex(8), "exp": time.time() + STATE_SECONDS})
    query = urlencode(
        {"response_type": "code", "client_id": f"{origin}/", "redirect_uri": f"{origin}/auth/callback", "state": state}
    )
    return RedirectResponse(f"{settings.ha_public_url}/auth/authorize?{query}", status_code=302)


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None):
    settings: Settings = request.app.state.settings
    checked = verify(settings, state)
    if not code or not checked or checked.get("kind") != "state":
        raise HTTPException(400, "Sign-in expired, please try again")
    origin = _origin(request)
    try:
        user = await _who_is(settings.ha_url, code, f"{origin}/")
    except (httpx.HTTPError, OSError, ValueError, KeyError) as err:
        return HTMLResponse(_page("Sign-in failed", f"Home Assistant could not confirm the sign-in ({err})."), 502)
    session = sign(settings, {"kind": "session", "uid": user["id"], "name": user["name"], "exp": time.time() + SESSION_DAYS * 86400})
    response = RedirectResponse(f"{origin}/{checked['next']}", status_code=302)
    response.set_cookie(
        COOKIE, session, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=request.url.scheme == "https", path="/",
    )  # fmt: skip
    return response


@router.get("/terminal")
async def pair_terminal(request: Request, code: str | None = None):
    """Pair this browser as a kitchen terminal with the code from Settings → Kitchen terminals."""
    from .services import ServiceError, terminals

    origin = _origin(request)
    try:
        async with request.app.state.db.sessions() as session:
            value = await terminals.redeem(session, request.app.state.hub, request.app.state.terminals, code or "")
    except ServiceError as err:
        return HTMLResponse(_page("Pairing failed", str(err), retry=f"{origin}/#/kiosk"), 400)
    response = RedirectResponse(f"{origin}/#/kiosk", status_code=302)
    response.set_cookie(
        terminals.COOKIE, value, max_age=terminals.COOKIE_DAYS * 86400, httponly=True, samesite="lax",
        secure=request.url.scheme == "https", path="/",
    )  # fmt: skip
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(f"{_origin(request)}/", status_code=302)
    response.delete_cookie(COOKIE, path="/")
    return response


async def _who_is(ha_url: str, code: str, client_id: str) -> dict[str, Any]:
    """Exchange the code, read the user from HA's WebSocket API, then revoke the token again."""
    import websockets

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{ha_url}/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id}
        )
        response.raise_for_status()
        tokens = response.json()
        try:
            ws_url = urlsplit(ha_url)._replace(scheme="wss" if ha_url.startswith("https") else "ws").geturl()
            async with websockets.connect(f"{ws_url}/api/websocket", open_timeout=10) as ws:
                await ws.recv()  # auth_required
                await ws.send(json.dumps({"type": "auth", "access_token": tokens["access_token"]}))
                if json.loads(await ws.recv()).get("type") != "auth_ok":
                    raise ValueError("token rejected")
                await ws.send(json.dumps({"id": 1, "type": "auth/current_user"}))
                result = json.loads(await ws.recv())["result"]
        finally:
            if tokens.get("refresh_token"):
                await client.post(f"{ha_url}/auth/revoke", data={"token": tokens["refresh_token"]})
    return {"id": result["id"], "name": result.get("name") or "Home Assistant user", "is_admin": result.get("is_admin")}


def _page(title: str, text: str, retry: str = "/auth/login") -> str:
    title, text = html.escape(title), html.escape(text)
    return (
        "<!doctype html><meta name=viewport content='width=device-width'>"
        f"<title>{title}</title><body style='font:16px system-ui;margin:3rem;max-width:36rem'>"
        f"<h1 style='font-size:1.4rem'>{title}</h1><p>{text}</p><p><a href='{html.escape(retry)}'>Try again</a></p>"
    )
