"""Kitchen terminals: pairing, what they may do, and the scan answers the kiosk page relies on."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from steward_server.config import Settings
from steward_server.main import create_app
from steward_server.models import Terminal
from steward_server.services.terminals import COOKIE
from steward_server.timeutil import utcnow

AUTH = {"Authorization": "Bearer t"}


@pytest.fixture
def app(tmp_path):
    settings = Settings(data_dir=tmp_path, api_token="t", trust_all=False, seed_demo=False, demo_receipts_dir=None)
    return create_app(settings)


@pytest.fixture
def admin(app):
    with TestClient(app, headers=AUTH) as c:
        yield c


def ok(response):
    assert response.status_code < 300, response.text
    return response.json() if response.status_code != 204 else None


def pair(app, code: str) -> TestClient:
    kiosk = TestClient(app)
    response = kiosk.get("/auth/terminal", params={"code": code}, follow_redirects=False)
    assert response.status_code == 302, response.text
    assert response.headers["location"].endswith("/#/kiosk")
    assert COOKIE in kiosk.cookies
    return kiosk


def test_pairing_works_once_and_removal_signs_out(app, admin):
    created = ok(admin.post("/api/terminals", json={"name": "Kitchen"}))
    assert not created["terminal"]["paired"] and len(created["code"]) == 9
    kiosk = pair(app, created["code"].lower().replace("-", " "))  # typed loosely still works
    assert ok(kiosk.get("/api/info"))["name"] == "Steward"
    assert TestClient(app).get("/auth/terminal", params={"code": created["code"]}).status_code == 400  # used up

    listed = ok(admin.get("/api/terminals"))
    assert listed["direct_url"] is None
    assert listed["terminals"][0]["paired"] and listed["terminals"][0]["last_seen"]

    # A new code pairs another browser and signs out the first one.
    again = ok(admin.post(f"/api/terminals/{created['terminal']['id']}/code"))
    second = pair(app, again["code"])
    assert kiosk.get("/api/info").status_code == 401
    ok(second.get("/api/info"))

    ok(admin.delete(f"/api/terminals/{created['terminal']['id']}"))
    assert second.get("/api/info").status_code == 401


def test_expired_code_is_refused(app, admin):
    created = ok(admin.post("/api/terminals", json={"name": "Kitchen"}))

    async def expire():
        async with app.state.db.sessions() as session:
            await session.execute(update(Terminal).values(pair_expires=utcnow() - timedelta(minutes=1)))
            await session.commit()

    admin.portal.call(expire)
    assert TestClient(app).get("/auth/terminal", params={"code": created["code"]}).status_code == 400


def test_terminal_only_reaches_stock_and_scanning(app, admin):
    milk = ok(admin.post("/api/products", json={"name": "Milk", "unit": "l"}))
    ok(admin.post(f"/api/products/{milk['id']}/barcodes", json={"code": "4000000000001"}))
    kiosk = pair(app, ok(admin.post("/api/terminals", json={"name": "Kitchen"}))["code"])

    for path in ("/api/settings/ai", "/api/settings/email", "/api/receipts", "/api/terminals", "/api/chores", "/api/stock/journal"):
        assert kiosk.get(path).status_code == 403, path
    assert kiosk.post("/api/terminals", json={"name": "Mine"}).status_code == 403
    assert kiosk.delete(f"/api/products/{milk['id']}").status_code == 403
    assert kiosk.put("/api/settings/email", json={}).status_code == 403

    ok(kiosk.get("/api/stock"))
    ok(kiosk.get("/api/products"))
    bought = ok(kiosk.post("/api/scan", json={"code": "4000000000001", "mode": "purchase", "amount": 2}))
    assert bought["done"] and bought["in_stock"] == 2
    used = ok(kiosk.post("/api/scan", json={"code": "4000000000001", "mode": "consume"}))
    assert used["in_stock"] == 1
    for txn in used["txn_ids"]:
        ok(kiosk.post(f"/api/stock/undo/{txn}"))
    assert ok(kiosk.get("/api/stock"))[0]["amount"] == 2

    # The journal names the terminal.
    journal = ok(admin.get("/api/stock/journal"))
    assert journal[0]["actor"].startswith("terminal:") and journal[0]["actor_name"] == "Kitchen"


def test_scan_answers_for_the_kiosk(admin):
    bread = ok(admin.post("/api/products", json={"name": "Bread", "min_stock": 1}))
    milk = ok(admin.post("/api/products", json={"name": "Milk"}))
    ok(admin.post(f"/api/products/{milk['id']}/barcodes", json={"code": "4000000000002"}))

    card = ok(admin.post("/api/scan", json={"code": "steward-mode-spoil", "mode": "consume"}))
    assert card["mode_switch"] == "spoil" and not card["done"]

    empty = ok(admin.post("/api/scan", json={"code": "4000000000002", "mode": "consume"}))
    assert empty["not_in_stock"] and not empty["done"]

    listed = ok(admin.post("/api/scan", json={"code": "4000000000002", "mode": "shopping"}))
    assert listed["shopping_item_id"] and listed["on_shopping_list"]

    # Bread has no barcode and is used often: it becomes a tile. Milk has a barcode: no tile.
    ok(admin.post("/api/stock/purchase", json={"product_id": bread["id"], "amount": 3}))
    ok(admin.post("/api/stock/purchase", json={"product_id": milk["id"], "amount": 3}))
    for product in (bread, milk):
        ok(admin.post("/api/stock/consume", json={"product_id": product["id"], "amount": 1}))
    assert [p["name"] for p in ok(admin.get("/api/kiosk/frequent"))] == ["Bread"]
