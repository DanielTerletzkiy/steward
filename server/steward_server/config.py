"""Runtime settings, read from environment variables."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Requests proxied by the HA Supervisor's ingress come from this address.
SUPERVISOR_INGRESS_IP = "172.30.32.2"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_token: str
    trust_all: bool
    seed_demo: bool
    demo_receipts_dir: Path | None
    # Where Home Assistant is, for "Sign in with Home Assistant": as the server reaches it, and as
    # the browser reaches it (they differ in Docker setups).
    ha_url: str | None = None
    ha_public_url: str | None = None
    # Running as a Home Assistant app (Supervisor): ingress, discovery, options from /data/options.json.
    supervisor_token: str | None = None
    log_level: str = "info"

    @property
    def is_app(self) -> bool:
        return bool(self.supervisor_token)

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir / 'steward.db'}"


def _load_token(data_dir: Path) -> str:
    """Use STEWARD_API_TOKEN, or create one in the data dir on first start."""
    if token := os.environ.get("STEWARD_API_TOKEN"):
        return token
    token_file = data_dir / "api_token"
    if token_file.exists():
        return token_file.read_text().strip()
    token = secrets.token_urlsafe(32)
    token_file.write_text(token)
    return token


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def _app_options(data_dir: Path) -> dict[str, Any]:
    """The app's options as set in Home Assistant's app configuration tab."""
    path = data_dir / "options.json"
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("STEWARD_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    receipts = os.environ.get("STEWARD_DEMO_RECEIPTS")
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    options = _app_options(data_dir) if supervisor_token else {}
    ha_url = (os.environ.get("STEWARD_HA_URL") or options.get("home_assistant_url") or "").rstrip("/") or None
    return Settings(
        data_dir=data_dir,
        api_token=_load_token(data_dir),
        # Never in the app: ingress already identifies the user.
        trust_all=_flag("STEWARD_TRUST_ALL") and not supervisor_token,
        seed_demo=_flag("STEWARD_SEED_DEMO") or bool(options.get("demo_data")),
        demo_receipts_dir=Path(receipts) if receipts else None,
        ha_url=ha_url,
        ha_public_url=(os.environ.get("STEWARD_HA_PUBLIC_URL") or "").rstrip("/") or ha_url,
        supervisor_token=supervisor_token,
        log_level=str(options.get("log_level") or os.environ.get("STEWARD_LOG_LEVEL") or "info"),
    )
