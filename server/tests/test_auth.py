"""Who may call the API: tokens, HA ingress, the sign-in cookie; and the app's options."""

from __future__ import annotations

import json
import time

from steward_server.api import is_authorized
from steward_server.auth import COOKIE, sign
from steward_server.config import SUPERVISOR_INGRESS_IP, Settings, load_settings


def settings(**overrides) -> Settings:
    base = dict(data_dir=None, api_token="secret", trust_all=False, seed_demo=False, demo_receipts_dir=None)
    return Settings(**{**base, **overrides})


def test_token_and_ingress():
    s = settings()
    assert is_authorized({"authorization": "Bearer secret"}, "10.0.0.5", None, s)
    assert not is_authorized({"authorization": "Bearer wrong"}, "10.0.0.5", None, s)
    # Ingress headers only count when they come from the Supervisor's proxy.
    assert is_authorized({"x-remote-user-id": "abc"}, SUPERVISOR_INGRESS_IP, None, s)
    assert not is_authorized({"x-remote-user-id": "abc"}, "10.0.0.5", None, s)


def test_session_cookie():
    s = settings()
    good = sign(s, {"kind": "session", "uid": "u1", "name": "Daniel", "exp": time.time() + 60})
    expired = sign(s, {"kind": "session", "uid": "u1", "name": "Daniel", "exp": time.time() - 1})
    state = sign(s, {"kind": "state", "next": "#/", "exp": time.time() + 60})
    assert is_authorized({"cookie": f"{COOKIE}={good}"}, "10.0.0.5", None, s)
    assert not is_authorized({"cookie": f"{COOKIE}={expired}"}, "10.0.0.5", None, s)
    assert not is_authorized({"cookie": f"{COOKIE}={state}"}, "10.0.0.5", None, s)  # a login state is no session
    assert not is_authorized({"cookie": f"{COOKIE}={good[:-2]}xx"}, "10.0.0.5", None, s)
    assert not is_authorized({"cookie": f"{COOKIE}={good}"}, "10.0.0.5", None, settings(api_token="other"))


def test_app_mode_reads_options_and_never_trusts_all(tmp_path, monkeypatch):
    (tmp_path / "options.json").write_text(json.dumps({"log_level": "debug", "demo_data": True}))
    monkeypatch.setenv("STEWARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup")
    monkeypatch.setenv("STEWARD_TRUST_ALL", "true")
    loaded = load_settings()
    assert loaded.is_app and loaded.seed_demo and loaded.log_level == "debug" and not loaded.trust_all
