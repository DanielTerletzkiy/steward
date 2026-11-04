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
    assert "/#/kiosk?key=" in response.headers["location"]  # the page keeps the key
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

    for path in ("/api/settings/ai", "/api/settings/email", "/api/receipts", "/api/terminals", "/api/tasks", "/api/stock/journal", "/api/equipment"):
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


def test_key_signs_in_again_until_the_terminal_is_removed(app, admin):
    created = ok(admin.post("/api/terminals", json={"name": "Kitchen"}))
    # The setup script trades the code for the key itself.
    key = ok(TestClient(app).post("/auth/terminal/redeem", json={"code": created["code"]}))["key"]
    assert TestClient(app).post("/auth/terminal/redeem", json={"code": created["code"]}).status_code == 400

    # A terminal paired with a cookie only (before 0.4.0) can read its key; others can't.
    assert TestClient(app, cookies={COOKIE: key}).get("/auth/terminal/key").json() == {"key": key}
    assert TestClient(app).get("/auth/terminal/key").status_code == 401

    # A browser that lost its cookie (or never had one) signs in with the key.
    browser = TestClient(app)
    assert browser.get("/api/info").status_code == 401
    assert browser.post("/auth/terminal/session", json={"key": key}).status_code == 204
    ok(browser.get("/api/info"))
    assert TestClient(app).post("/auth/terminal/session", json={"key": key[:-3] + "xxx"}).status_code == 401

    ok(admin.delete(f"/api/terminals/{created['terminal']['id']}"))
    assert browser.get("/api/info").status_code == 401
    assert TestClient(app).post("/auth/terminal/session", json={"key": key}).status_code == 401


def test_terminal_marks_chores_done_and_reads_recipes(app, admin):
    ok(admin.put("/api/people", json=[{"id": "person.anna", "name": "Anna", "user_id": "u1"}]))
    chore = ok(admin.post("/api/chores", json={"name": "Empty the bin", "schedule": "manual"}))
    recipe = ok(admin.post("/api/recipes", json={"name": "Toast", "instructions": "Toast the bread.\nButter it."}))
    kiosk = pair(app, ok(admin.post("/api/terminals", json={"name": "Kitchen"}))["code"])

    assert [p["name"] for p in ok(kiosk.get("/api/people"))] == ["Anna"]
    done = ok(kiosk.post(f"/api/chores/{chore['id']}/execute", json={"person_id": "person.anna"}))
    assert done["last_done_by"] == "person.anna"
    assert ok(kiosk.get(f"/api/recipes/{recipe['id']}"))["instructions"].startswith("Toast")
    ok(kiosk.get(f"/api/recipes/{recipe['id']}/fulfillment"))
    ok(kiosk.get("/api/mealplan"))
    assert kiosk.patch(f"/api/recipes/{recipe['id']}", json={"name": "x"}).status_code == 403
    assert kiosk.delete(f"/api/chores/{chore['id']}").status_code == 403


def test_a_chosen_batch_is_used_and_opened(admin):
    milk = ok(admin.post("/api/products", json={"name": "Milk"}))
    old = ok(admin.post("/api/stock/purchase", json={"product_id": milk["id"], "amount": 1, "due_date": "2026-11-05"}))
    new = ok(admin.post("/api/stock/purchase", json={"product_id": milk["id"], "amount": 2, "due_date": "2026-11-20"}))

    # Without a choice the one that expires first goes; with a choice, the chosen one.
    used = ok(admin.post("/api/stock/consume", json={"product_id": milk["id"], "amount": 1, "entry_id": new["entry_id"]}))
    assert used["entry_ids"] == [new["entry_id"]]
    amounts = {e["id"]: e["amount"] for e in ok(admin.get("/api/stock"))[0]["entries"]}
    assert amounts == {old["entry_id"]: 1, new["entry_id"]: 1}

    # More than the chosen batch holds: the rest comes from the others.
    used = ok(admin.post("/api/stock/consume", json={"product_id": milk["id"], "amount": 1.5, "entry_id": new["entry_id"]}))
    assert used["consumed"] == 1.5 and used["entry_ids"] == [new["entry_id"], old["entry_id"]]
    for txn in used["txn_ids"]:
        ok(admin.post(f"/api/stock/undo/{txn}"))

    opened = ok(admin.post("/api/stock/open", json={"product_id": milk["id"], "amount": 1, "entry_id": new["entry_id"]}))
    entries = ok(admin.get("/api/stock"))[0]["entries"]
    assert [e["due_date"] for e in entries if e["opened_at"]] == ["2026-11-20"] and opened["entry_ids"]
    gone = admin.post("/api/stock/consume", json={"product_id": milk["id"], "amount": 1, "entry_id": 999})
    assert gone.status_code == 400


def test_commands_reach_the_helper_on_the_pi(app, admin):
    kiosk = pair(app, ok(admin.post("/api/terminals", json={"name": "Kitchen"}))["code"])
    helper = TestClient(app, cookies={COOKIE: kiosk.cookies[COOKIE]})
    assert not ok(kiosk.get("/api/kiosk/agent"))["connected"]
    assert helper.post("/api/kiosk/agent/next?wait=0", json={"version": "1"}).status_code == 204
    assert ok(kiosk.get("/api/kiosk/agent"))["connected"]

    sent = ok(kiosk.post("/api/kiosk/agent/commands", json={"type": "bt_scan", "args": {"seconds": 5}}))
    assert sent["status"] == "pending"
    command = ok(helper.post("/api/kiosk/agent/next?wait=0", json={}))
    assert (command["type"], command["args"]) == ("bt_scan", {"seconds": 5})
    assert ok(kiosk.get(f"/api/kiosk/agent/commands/{sent['id']}"))["status"] == "running"
    ok(helper.post(f"/api/kiosk/agent/commands/{sent['id']}/result", json={"ok": True, "result": {"devices": []}}))
    assert ok(kiosk.get(f"/api/kiosk/agent/commands/{sent['id']}")) == {
        "id": sent["id"], "type": "bt_scan", "status": "done", "result": {"devices": []}, "error": None,
    }  # fmt: skip

    assert kiosk.post("/api/kiosk/agent/commands", json={"type": "rm -rf"}).status_code == 400
    # People and other terminals can't drive this terminal's helper.
    assert admin.post("/api/kiosk/agent/commands", json={"type": "bt_status"}).status_code == 403
    other = pair(app, ok(admin.post("/api/terminals", json={"name": "Hall"}))["code"])
    assert other.get(f"/api/kiosk/agent/commands/{sent['id']}").status_code == 404
