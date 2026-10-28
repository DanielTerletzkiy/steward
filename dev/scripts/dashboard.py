"""Create the "Household" dashboard for the Steward demo (idempotent).

Entity ids depend on HA's language when the integration was added, so they are looked up
in the entity registry by the integration's unique-id keys.

Usage: python dev/scripts/dashboard.py <ha-access-token> [ws://localhost:8123/api/websocket]
"""

import asyncio
import json
import sys

import websockets

URL_PATH = "steward-household"


def tile(entity: str, name: str, color: str, **extra) -> dict:
    return {"type": "tile", "entity": entity, "name": name, "color": color, **extra}


def press(entity: str, name: str, color: str, icon: str) -> dict:
    """A tile that presses a button entity (buttons have no useful state to show)."""
    return tile(entity, name, color, icon=icon, hide_state=True, grid_options={"columns": 12},
                tap_action={"action": "perform-action", "perform_action": "button.press", "target": {"entity_id": entity}})


def build(e: dict[str, str], person_key: str | None, person: str | None) -> dict:
    full = {"grid_options": {"columns": 12}}
    owner = person or "household"
    outfit_cards = []
    if f"outfit_image_{owner}" in e:
        outfit_cards = [
            {"type": "picture-entity", "entity": e[f"outfit_image_{owner}"], "show_name": False, "show_state": False, **full},
            tile(e[f"outfit_{owner}"], "Today's outfit", "deep-purple", **full),
            press(e[f"suggest_outfit_{owner}"], "Suggest another outfit", "deep-purple", "mdi:hanger"),
        ]
    chores_card = (
        [{"type": "todo-list", "entity": e[person_key], "title": "My chores", **full}] if person_key else []
    )
    return {
        "title": "Household",
        "views": [
            {
                "title": "Today",
                "path": "today",
                "icon": "mdi:home-heart",
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Stock", "icon": "mdi:fridge-outline"},
                            tile(e["expired"], "Expired", "red"),
                            tile(e["expiring_soon"], "Expiring soon", "amber"),
                            tile(e["below_min_stock"], "Below minimum", "orange"),
                            tile(e["stock_value"], "Stock value", "green"),
                            press(e["add_missing"], "Add missing to list", "teal", "mdi:cart-plus"),
                            {"type": "todo-list", "entity": e["shopping_1"], "title": "Shopping list", **full},
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Chores & tasks", "icon": "mdi:broom"},
                            tile(e["chores_due"], "Chores due", "purple"),
                            tile(e["tasks_due"], "Tasks due", "indigo"),
                            *chores_card,
                            {"type": "todo-list", "entity": e["tasks"], "title": "Tasks", **full},
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Wardrobe", "icon": "mdi:tshirt-crew-outline"},
                            *outfit_cards,
                            tile(e["laundry"], "Laundry", "blue"),
                            press(e["laundry_done"], "Laundry done", "blue", "mdi:washing-machine"),
                            {"type": "heading", "heading": "Kitchen", "icon": "mdi:silverware-fork-knife"},
                            tile(e["meals_today"], "Meals today", "orange", **full),
                            tile(e["warranty_ending"], "Warranties ending", "red", **full),
                        ],
                    },
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Money", "icon": "mdi:receipt-text-outline"},
                            tile(e["spending_month"], "This month", "teal"),
                            tile(e["last_trip"], "Last trip", "teal"),
                            tile(e["deposit_balance"], "Deposit balance", "cyan"),
                            tile(e["spending_total"], "Spent in total", "blue-grey"),
                            {
                                "type": "calendar",
                                "initial_view": "listWeek",
                                "entities": [e["calendar_meal_plan"], e["calendar_chores"], e["calendar_due_dates"],
                                             e["calendar_tasks"], e["calendar_warranties"]],
                                **full,
                            },
                        ],
                    },
                ],
            }
        ],
    }


async def call(ws, msg_id: int, **payload) -> dict:
    await ws.send(json.dumps({"id": msg_id, **payload}))
    while True:
        reply = json.loads(await ws.recv())
        if reply.get("id") == msg_id:
            return reply


async def main(token: str, url: str) -> None:
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        assert json.loads(await ws.recv())["type"] == "auth_ok"

        registry = (await call(ws, 1, type="config/entity_registry/list"))["result"]
        entities = {}
        for entry in registry:
            if entry["platform"] == "steward" and "_" in (entry.get("unique_id") or ""):
                key = entry["unique_id"].split("_", 1)[1]
                entities[key] = entry["entity_id"]
        person_keys = sorted(k for k in entities if k.startswith("chores_person.") and k != "chores_everyone")
        person = person_keys[0].removeprefix("chores_") if person_keys else None
        dashboard = build(entities, person_keys[0] if person_keys else None, person)

        existing = {d["url_path"] for d in (await call(ws, 2, type="lovelace/dashboards/list"))["result"]}
        if URL_PATH not in existing:
            print(await call(ws, 3, type="lovelace/dashboards/create", url_path=URL_PATH, title="Household",
                             icon="mdi:home-heart", show_in_sidebar=True, require_admin=False, mode="storage"))
        print(await call(ws, 4, type="lovelace/config/save", url_path=URL_PATH, config=dashboard))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "ws://localhost:8123/api/websocket"))
