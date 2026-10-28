"""Through the real app and routes: catches errors that only show up when responses are serialized."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from steward_server.config import Settings
from steward_server.demo_art import garment_picture, manual_pdf
from steward_server.main import create_app
from steward_server.services.recipes import parse_ingredient

AUTH = {"Authorization": "Bearer t"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, api_token="t", trust_all=False, seed_demo=False, demo_receipts_dir=None)
    with TestClient(create_app(settings), headers=AUTH) as c:
        yield c


def ok(response):
    assert response.status_code < 300, response.text
    return response.json() if response.status_code != 204 else None


def test_equipment_with_photo_and_manual(client):
    item = ok(client.post("/api/equipment", json={"name": "Coffee machine", "warranty_until": "2027-01-01"}))
    assert item["documents"] == [] and item["warranty_status"] in ("active", "ending")
    ok(client.put(f"/api/equipment/{item['id']}/photo", files={"file": ("p.png", garment_picture("coat", "red"), "image/png")}))
    pdf = manual_pdf("Manual", ["Descaling\nUse descaler every 3 months."])
    doc = ok(client.post(f"/api/equipment/{item['id']}/documents", files={"file": ("m.pdf", pdf, "application/pdf")}, data={"kind": "manual"}))
    assert doc["file"]["pages"] == 1 and doc["title"] == "m"
    assert ok(client.get("/api/equipment/search", params={"q": "descale"}))[0]["page"] == 1
    assert ok(client.delete(f"/api/equipment/{item['id']}/photo"))["photo_id"] is None
    ok(client.delete(f"/api/equipment/{item['id']}/documents/{doc['id']}"))


def test_garments_wear_and_undo_laundry(client):
    tee = ok(client.post("/api/wardrobe/garments", json={"name": "Tee", "category": "t-shirt"}))
    ok(client.post("/api/wardrobe/wear", json={"garment_ids": [tee["id"]]}))
    assert ok(client.post("/api/wardrobe/laundry/done", json={}))["washed"] == 1
    undone = ok(client.patch(f"/api/wardrobe/garments/{tee['id']}", json={"state": "laundry", "wears_since_wash": 1}))
    assert (undone["state"], undone["wears_since_wash"]) == ("laundry", 1)


def test_recipe_cook_and_meal_plan(client):
    pasta = ok(client.post("/api/products", json={"name": "Spaghetti", "unit": "g"}))
    sauce = ok(client.post("/api/products", json={"name": "Tomato sauce", "unit": "jar"}))
    ok(client.post("/api/stock/purchase", json={"product_id": pasta["id"], "amount": 500}))
    recipe = ok(client.post("/api/recipes", json={
        "name": "Spaghetti al pomodoro", "servings": 2,
        "ingredients": [{"text": "250 g Spaghetti"}, {"text": "1 jar tomato sauce"}, {"text": "Salt, to taste"}],
    }))  # fmt: skip
    by_name = {i["name"]: i for i in recipe["ingredients"]}
    assert by_name["Spaghetti"]["product_id"] == pasta["id"] and by_name["Spaghetti"]["stock_amount"] == 250
    assert by_name["tomato sauce"]["product_id"] == sauce["id"]
    assert by_name["Salt"]["product_id"] is None and by_name["Salt"]["optional"]

    check = ok(client.get(f"/api/recipes/{recipe['id']}/fulfillment", params={"servings": 4}))
    statuses = {i["name"]: i["status"] for i in check["ingredients"]}
    assert statuses == {"Spaghetti": "have", "tomato sauce": "missing", "Salt": "optional"} and not check["can_cook"]

    entry = ok(client.post("/api/mealplan", json={"day": "2030-01-07", "recipe_id": recipe["id"]}))
    assert ok(client.post("/api/mealplan/shopping", params={"start": "2030-01-07", "end": "2030-01-13"}))["added"] == ["Tomato sauce"]
    ok(client.post("/api/stock/purchase", json={"product_id": sauce["id"], "amount": 1}))
    ok(client.post(f"/api/mealplan/{entry['id']}/done"))
    left = {i["product"]["name"]: i["amount"] for i in ok(client.get("/api/stock", params={"include_empty": True}))}
    assert left["Spaghetti"] == 250 and left["Tomato sauce"] == 0
    assert ok(client.get(f"/api/recipes/{recipe['id']}"))["cooked_count"] == 1


@pytest.mark.parametrize(
    ("line", "amount", "unit", "name"),
    [
        ("200 g Spaghetti", 200, "g", "Spaghetti"),
        ("1 1/2 EL Olivenöl", 1.5, "tbsp", "Olivenöl"),
        ("½ TL Salz", 0.5, "tsp", "Salz"),
        ("2-3 Zehen Knoblauch, fein gehackt", 3, "clove", "Knoblauch"),
        ("400g passierte Tomaten (1 Packung)", 400, "g", "passierte Tomaten"),
        ("1 onion", 1, None, "onion"),
        ("Pfeffer", None, None, "Pfeffer"),
    ],
)
def test_ingredient_lines(line, amount, unit, name):
    parsed = parse_ingredient(line)
    assert (parsed["amount"], parsed["unit"], parsed["name"]) == (amount, unit, name)


def test_recipe_import_reads_json_ld(client, monkeypatch):
    import httpx

    page = """<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebPage"},
      {"@type":"Recipe","name":"Pfannkuchen","recipeYield":"4 Portionen","totalTime":"PT25M",
       "recipeIngredient":["250 g Mehl","3 Eier","500 ml Milch"],
       "recipeInstructions":[{"@type":"HowToStep","text":"Alles verrühren."},{"@type":"HowToStep","text":"Ausbacken."}]}]}
    </script></html>"""

    def handler(request):
        return httpx.Response(200, text=page)

    real = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    recipe = ok(client.post("/api/recipes/import", json={"url": "https://example.com/pfannkuchen"}))
    assert (recipe["name"], recipe["servings"], recipe["minutes"]) == ("Pfannkuchen", 4, 25)
    assert [i["name"] for i in recipe["ingredients"]] == ["Mehl", "Eier", "Milch"]
    assert recipe["instructions"] == "Alles verrühren.\nAusbacken."


def test_appliance_runs(client):
    vacuuming = ok(client.post("/api/chores", json={"name": "Vacuum", "schedule": "dynamic", "interval": 7}))
    hang_up = ok(client.post("/api/chores", json={"name": "Hang up the laundry", "schedule": "manual"}))
    robot = ok(client.post("/api/equipment", json={"name": "Robot", "kind": "vacuum", "ha_entities": ["vacuum.robot"],
                                                   "chore_ids": [vacuuming["id"]]}))  # fmt: skip
    washer = ok(client.post("/api/equipment", json={"name": "Washer", "kind": "washer", "ha_device_id": "dev1",
                                                    "chore_ids": [hang_up["id"]]}))  # fmt: skip
    assert washer["automation_effective"] == {"chores": "make_due", "laundry": "ask"}

    ran = ok(client.post(f"/api/equipment/{robot['id']}/finished", json={"source": "vacuum.robot", "detail": "docked"}))
    assert ran["chores_done"] == ["Vacuum"]
    assert ok(client.post(f"/api/equipment/{robot['id']}/finished", json={}))["counted"] is False  # same run twice

    tee = ok(client.post("/api/wardrobe/garments", json={"name": "Tee", "category": "t-shirt"}))
    ok(client.post("/api/wardrobe/wear", json={"garment_ids": [tee["id"]]}))
    washed = ok(client.post(f"/api/equipment/{washer['id']}/finished", json={"detail": "washing_is_complete"}))
    assert (washed["chores_due"], washed["laundry"]) == (["Hang up the laundry"], "asked")
    summary = ok(client.get("/api/summary"))
    assert summary["wardrobe"]["laundry_prompt"]["name"] == "Washer"
    statuses = {c["name"]: c["status"] for c in ok(client.get("/api/chores"))}
    assert statuses["Hang up the laundry"] in ("overdue", "due_today")
    ok(client.post("/api/wardrobe/laundry/done", json={}))
    assert ok(client.get("/api/summary"))["wardrobe"]["laundry_prompt"] is None

    ok(client.put(f"/api/equipment/{washer['id']}/live", json={"state": "rinsing", "running": True, "remaining_minutes": 42}))
    assert ok(client.get("/api/summary"))["equipment"]["running"][0]["remaining_minutes"] == 42
    assert len(ok(client.get(f"/api/equipment/{washer['id']}/runs"))) == 1
    # Commands need HA: without the integration connected, the server says so.
    assert client.post(f"/api/equipment/{robot['id']}/command", json={"command": "start"}).status_code == 503
    assert client.post(f"/api/equipment/{robot['id']}/command", json={"command": "self_destruct"}).status_code == 400


async def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    from steward_server.db import Database

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE equipment (id INTEGER PRIMARY KEY, name VARCHAR, consumable_ids JSON, chore_ids JSON)")
        conn.execute("INSERT INTO equipment (name, consumable_ids, chore_ids) VALUES ('Old washer', '[]', '[]')")
    db = Database(f"sqlite+aiosqlite:///{path}")
    await db.create_all()
    await db.dispose()
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT kind, ha_entities, automation, run_count FROM equipment").fetchone()
    assert row == ("other", "[]", "{}", 0)


def test_websocket_rejects_with_4401(tmp_path):
    from starlette.websockets import WebSocketDisconnect

    settings = Settings(data_dir=tmp_path, api_token="t", trust_all=False, seed_demo=False, demo_receipts_dir=None)
    with TestClient(create_app(settings)) as anonymous:
        with pytest.raises(WebSocketDisconnect) as closed, anonymous.websocket_connect("/api/ws") as ws:
            ws.receive_json()
        assert closed.value.code == 4401


def test_stock_actions_return_undoable_txn_ids(client):
    milk = ok(client.post("/api/products", json={"name": "Milk", "barcodes": ["4006381333931"]}))
    bought = ok(client.post("/api/stock/purchase", json={"product_id": milk["id"], "amount": 2}))
    used = ok(client.post("/api/stock/consume", json={"product_id": milk["id"], "amount": 1}))
    assert len(bought["txn_ids"]) == 1 and len(used["txn_ids"]) == 1
    ok(client.post(f"/api/stock/undo/{used['txn_ids'][0]}"))
    scanned = ok(client.post("/api/scan", json={"code": "4006381333931", "mode": "purchase"}))
    assert scanned["pack_amount"] == 1 and len(scanned["txn_ids"]) == 1
    left = {i["product"]["name"]: i["amount"] for i in ok(client.get("/api/stock"))}
    assert left["Milk"] == 3


def test_open_can_be_undone(client):
    juice = ok(client.post("/api/products", json={"name": "Juice"}))
    ok(client.post("/api/stock/purchase", json={"product_id": juice["id"], "amount": 3}))
    opened = ok(client.post("/api/stock/open", json={"product_id": juice["id"], "amount": 1}))
    item = next(i for i in ok(client.get("/api/stock")) if i["product"]["name"] == "Juice")
    assert item["opened"] == 1
    for txn_id in opened["txn_ids"]:
        ok(client.post(f"/api/stock/undo/{txn_id}"))
    item = next(i for i in ok(client.get("/api/stock")) if i["product"]["name"] == "Juice")
    assert (item["amount"], item["opened"], len([e for e in item["entries"] if e["amount"] > 0])) == (3, 0, 1)
