"""Import eBons from a mailbox: check it over IMAP for mails from REWE with a PDF and import those.

Steward remembers the last mail it looked at (IMAP UID), so each mail is read once; importing the same eBon
twice is a no-op anyway. The mailbox is opened read-only unless imported mails should be marked as read.
"""

from __future__ import annotations

import asyncio
import email
import hashlib
import imaplib
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.policy import default as default_policy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Receipt
from ..timeutil import utcnow
from . import Invalid
from . import receipts as receipt_service
from . import settings as settings_store

LOG = logging.getLogger("steward.mail")
SETTINGS_KEY = "email_import"
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "host": "imap.gmail.com",
    "port": 993,
    "username": "",
    "password": None,
    "folder": "INBOX",
    "sender": "rewe.de",
    "mark_read": False,
    "interval_minutes": 15,
    # How far back the first check looks.
    "since_days": 30,
}
EDITABLE = ("enabled", "host", "port", "username", "folder", "sender", "mark_read", "interval_minutes", "since_days")
MAX_PER_RUN = 200
TIMEOUT = 30


@dataclass
class Fetched:
    uidvalidity: int
    last_uid: int
    # (uid, PDFs attached to that mail)
    mails: list[tuple[int, list[bytes]]] = field(default_factory=list)


async def load_config(session: AsyncSession) -> dict[str, Any]:
    return {**DEFAULTS, **(await settings_store.get(session, SETTINGS_KEY, {}) or {})}


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """For the UI: the password is never sent back, only whether one is set."""
    shown = {k: v for k, v in config.items() if k != "password"}
    shown["password_set"] = bool(config.get("password"))
    return shown


async def save_config(session: AsyncSession, hub: EventHub, data: dict[str, Any]) -> dict[str, Any]:
    old = await load_config(session)
    config = dict(old)
    for key in EDITABLE:
        if key in data and data[key] is not None:
            config[key] = data[key]
    # A password left out keeps the stored one; an empty string clears it. Google shows app passwords
    # in groups of four, so spaces are dropped.
    if (password := data.get("password")) is not None:
        config["password"] = password.replace(" ", "") or None
    config["host"] = str(config["host"]).strip()
    config["username"] = str(config["username"]).strip()
    config["port"] = int(config["port"])
    config["interval_minutes"] = max(5, int(config["interval_minutes"]))
    config["since_days"] = max(1, min(int(config["since_days"]), 3650))
    if config["enabled"] and not (config["host"] and config["username"] and config.get("password")):
        raise Invalid("Fill in the server, the address and the app password first")
    if any(config[key] != old[key] for key in ("host", "username", "folder")):
        config.pop("state", None)  # a different mailbox starts over
    await settings_store.put(session, hub, SETTINGS_KEY, config)
    return public_config(config)


def _connect(config: dict[str, Any]) -> imaplib.IMAP4_SSL:
    try:
        client = imaplib.IMAP4_SSL(config["host"], int(config["port"]), timeout=TIMEOUT)
    except (OSError, socket.timeout) as exc:
        raise Invalid(f"Can't reach {config['host']}: {exc}") from exc
    try:
        client.login(config["username"], config.get("password") or "")
    except imaplib.IMAP4.error as exc:
        _logout(client)
        raise Invalid(f"Sign-in failed: {_text(exc)}. For Gmail, use an app password.") from exc
    return client


def _logout(client: imaplib.IMAP4) -> None:
    try:
        client.logout()
    except (imaplib.IMAP4.error, OSError):
        pass


def _text(value: Any) -> str:
    if isinstance(value, imaplib.IMAP4.error):
        value = value.args[0] if value.args else ""
    return value.decode(errors="replace") if isinstance(value, bytes) else str(value)


def _mailbox(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _select(client: imaplib.IMAP4, folder: str, readonly: bool) -> int:
    status, data = client.select(_mailbox(folder), readonly=readonly)
    if status != "OK":
        raise Invalid(f"Folder {folder!r} not found: {_text(data[0] if data else '')}")
    _, values = client.response("UIDVALIDITY")
    return int(values[0]) if values and values[0] else 0


def _folders(client: imaplib.IMAP4) -> list[str]:
    status, data = client.list()
    folders = []
    for raw in data if status == "OK" else []:
        line = _text(raw)
        if "\\Noselect" in line:
            continue
        name = line.rsplit(' "/" ', 1)[-1].strip()
        folders.append(name[1:-1] if name.startswith('"') and name.endswith('"') else name)
    return folders


def pdf_attachments(raw: bytes) -> list[bytes]:
    """The PDF files attached to one mail."""
    message = email.message_from_bytes(raw, policy=default_policy)
    if not isinstance(message, EmailMessage):
        return []
    pdfs = []
    for part in message.walk():
        filename = (part.get_filename() or "").lower()
        if part.get_content_type() == "application/pdf" or filename.endswith(".pdf"):
            payload = part.get_payload(decode=True)
            if payload and payload[:5] == b"%PDF-":
                pdfs.append(payload)
    return pdfs


def _search(client: imaplib.IMAP4, config: dict[str, Any], state: dict[str, Any], uidvalidity: int) -> list[int]:
    sender = str(config.get("sender") or "").replace('"', "")
    criteria: list[str] = []
    last_uid = int(state.get("last_uid") or 0) if state.get("uidvalidity") == uidvalidity else 0
    if last_uid:
        criteria += ["UID", f"{last_uid + 1}:*"]
    else:
        since = (datetime.now() - timedelta(days=int(config["since_days"]))).strftime("%d-%b-%Y")
        criteria += ["SINCE", since]
    if sender:
        criteria += ["FROM", f'"{sender}"']
    status, data = client.uid("SEARCH", None, *criteria)
    if status != "OK":
        raise Invalid(f"Search failed: {_text(data[0] if data else '')}")
    # "UID n:*" always matches the newest mail, even when it is older than n.
    return sorted(uid for uid in (int(x) for x in (data[0] or b"").split()) if uid > last_uid)


def fetch(config: dict[str, Any], state: dict[str, Any]) -> Fetched:
    """Blocking: new matching mails and their PDFs since the last check."""
    client = _connect(config)
    try:
        uidvalidity = _select(client, config["folder"], readonly=True)
        uids = _search(client, config, state, uidvalidity)
        last_uid = int(state.get("last_uid") or 0) if state.get("uidvalidity") == uidvalidity else 0
        result = Fetched(uidvalidity=uidvalidity, last_uid=last_uid)
        for uid in uids[:MAX_PER_RUN]:
            status, data = client.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None)
            if status == "OK" and raw:
                result.mails.append((uid, pdf_attachments(raw)))
            result.last_uid = max(result.last_uid, uid)
        return result
    finally:
        _logout(client)


def mark_read(config: dict[str, Any], uids: list[int]) -> None:
    if not uids:
        return
    client = _connect(config)
    try:
        _select(client, config["folder"], readonly=False)
        client.uid("STORE", ",".join(str(uid) for uid in uids), "+FLAGS", "(\\Seen)")
    finally:
        _logout(client)


def check(config: dict[str, Any]) -> dict[str, Any]:
    """Blocking: sign in, list folders, count matching mails in the chosen folder."""
    client = _connect(config)
    try:
        folders = _folders(client)
        uidvalidity = _select(client, config["folder"], readonly=True)
        matches = _search(client, config, {}, uidvalidity)
        return {"ok": True, "folders": folders, "matches": len(matches)}
    finally:
        _logout(client)


async def test(session: AsyncSession, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Try the stored settings, or unsaved ones from the form (a missing password uses the stored one)."""
    config = await load_config(session)
    for key in EDITABLE:
        if data and data.get(key) is not None:
            config[key] = data[key]
    if data and data.get("password"):
        config["password"] = data["password"].replace(" ", "")
    if not (config["host"] and config["username"] and config.get("password")):
        raise Invalid("Fill in the server, the address and the app password first")
    return await asyncio.to_thread(check, config)


async def run(session: AsyncSession, hub: EventHub) -> dict[str, Any]:
    """Check the mailbox now and import new eBons."""
    config = await load_config(session)
    if not (config["host"] and config["username"] and config.get("password")):
        raise Invalid("Email import isn't set up")
    started = utcnow()
    result: dict[str, Any] = {"at": started.isoformat(), "mails": 0, "imported": 0, "known": 0, "skipped": 0}
    try:
        fetched = await asyncio.to_thread(fetch, config, config.get("state") or {})
    except Invalid as exc:
        result["error"] = str(exc)
        await _remember(session, hub, config, result)
        raise
    imported_uids = []
    for uid, pdfs in fetched.mails:
        result["mails"] += 1
        for pdf in pdfs:
            known = await session.scalar(select(Receipt.id).where(Receipt.external_id == hashlib.sha256(pdf).hexdigest()))
            if known is not None:
                result["known"] += 1
                continue
            try:
                await receipt_service.import_ebon(session, hub, pdf, source="email")
            except Invalid as exc:  # a PDF that isn't an eBon (a newsletter, an invoice)
                LOG.info("Skipped a PDF in mail %s: %s", uid, exc)
                result["skipped"] += 1
                continue
            result["imported"] += 1
            imported_uids.append(uid)
    config["state"] = {"uidvalidity": fetched.uidvalidity, "last_uid": fetched.last_uid}
    if config.get("mark_read") and imported_uids:
        try:
            await asyncio.to_thread(mark_read, config, imported_uids)
        except Invalid as exc:
            LOG.warning("Could not mark imported mails as read: %s", exc)
    if result["imported"]:
        LOG.info("Imported %s eBon(s) from email", result["imported"])
    await _remember(session, hub, config, result)
    return result


async def _remember(session: AsyncSession, hub: EventHub, config: dict[str, Any], result: dict[str, Any]) -> None:
    config["last_run"] = result
    await settings_store.put(session, hub, SETTINGS_KEY, config)


async def run_if_due(session: AsyncSession, hub: EventHub) -> dict[str, Any] | None:
    config = await load_config(session)
    if not config["enabled"]:
        return None
    last = (config.get("last_run") or {}).get("at")
    if last and utcnow() - datetime.fromisoformat(last) < timedelta(minutes=int(config["interval_minutes"])) - timedelta(seconds=30):
        return None
    try:
        return await run(session, hub)
    except Invalid as exc:
        LOG.warning("Email import failed: %s", exc)
        return None
