"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

# Requests proxied by the HA Supervisor's ingress come from this address.
SUPERVISOR_INGRESS_IP = "172.30.32.2"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_token: str
    trust_all: bool
    seed_demo: bool
    demo_receipts_dir: Path | None

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


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("STEWARD_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    receipts = os.environ.get("STEWARD_DEMO_RECEIPTS")
    return Settings(
        data_dir=data_dir,
        api_token=_load_token(data_dir),
        trust_all=os.environ.get("STEWARD_TRUST_ALL", "").lower() in ("1", "true", "yes"),
        seed_demo=os.environ.get("STEWARD_SEED_DEMO", "").lower() in ("1", "true", "yes"),
        demo_receipts_dir=Path(receipts) if receipts else None,
    )
