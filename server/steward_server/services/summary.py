"""One snapshot of everything Home Assistant shows as sensors."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from . import chores as chores_service
from . import equipment as equipment_service
from . import people as people_service
from . import receipts as receipts_service
from . import recipes as recipes_service
from . import stock as stock_service
from . import tasks as tasks_service
from . import settings as settings_store
from . import wardrobe as wardrobe_service
from ..timeutil import today


def _item_brief(item) -> dict:
    return {
        "product_id": item.product.id,
        "name": item.product.name,
        "amount": item.amount,
        "unit": item.product.unit,
        "due": item.next_due.isoformat() if item.next_due else None,
    }


async def summary(session: AsyncSession) -> dict:
    stock = await stock_service.stock_overview(session, include_empty=True)
    chores = await chores_service.list_chores(session)
    tasks = await tasks_service.list_tasks(session, include_done=False)
    people = await people_service.list_people(session)
    equipment = await equipment_service.list_equipment(session)
    garments = await wardrobe_service.list_garments(session)
    needs_wash = [g for g in garments if g.needs_wash]
    outfits_today = await wardrobe_service.list_outfits(session, day=today())
    meals = await recipes_service.meal_plan(session, today(), today())
    recipe_names = {r.id: r.name for r in await recipes_service.list_recipes(session)} if meals else {}

    due_chores = [c for c in chores if c.status in ("overdue", "due_today")]
    per_person = {
        person.id: {
            "name": person.name,
            "chores_due": [c.name for c in due_chores if c.next_assignee == person.id],
        }
        for person in people
    }
    return {
        "stock": {
            "products_in_stock": sum(1 for i in stock if i.amount > 0),
            "value": round(sum(i.value for i in stock), 2),
            "expired": [_item_brief(i) for i in stock if i.status == "expired"],
            "due_soon": [_item_brief(i) for i in stock if i.status == "due_soon"],
            "below_min": [_item_brief(i) for i in stock if i.below_min],
        },
        "chores": {
            "overdue": [c.model_dump(mode="json") for c in chores if c.status == "overdue"],
            "due_today": [c.model_dump(mode="json") for c in chores if c.status == "due_today"],
        },
        "tasks": {
            "open": len(tasks),
            "due": [
                {"id": t.id, "name": t.name, "due": t.due_date.isoformat()}
                for t in tasks
                if t.due_date and t.due_date <= today()
            ],
        },
        "spending": await receipts_service.spending(session),
        "people": per_person,
        "meals_today": [
            {"id": m.id, "slot": m.slot, "recipe_id": m.recipe_id, "name": recipe_names.get(m.recipe_id) or m.note,
             "note": m.note, "servings": m.servings, "done": m.done}
            for m in meals
        ],  # fmt: skip
        "equipment": {
            "count": len(equipment),
            "warranty_ending": [
                {"id": e.id, "name": e.name, "warranty_until": e.warranty_until.isoformat()}
                for e in equipment
                if e.warranty_status == "ending"
            ],
            "running": [
                {"id": e.id, "name": e.name, "kind": e.kind, "state": e.live.get("state"),
                 "remaining_minutes": e.live.get("remaining_minutes"), "battery": e.live.get("battery")}
                for e in equipment
                if e.live and e.live.get("running")
            ],  # fmt: skip
        },
        "wardrobe": {
            "garments": len(garments),
            "clean": sum(1 for g in garments if g.state in ("clean", "worn") and not g.needs_wash),
            "laundry": sum(1 for g in garments if g.state == "laundry"),
            "needs_wash": [{"id": g.id, "name": g.name} for g in needs_wash],
            "washing": sum(1 for g in garments if g.state == "washing"),
            "drying": [
                {"id": g.id, "name": g.name, "dry_until": g.dry_until.isoformat() if g.dry_until else None}
                for g in garments
                if g.state == "drying"
            ],
            # A washing machine finished: "mark the laundry as clean?"
            "laundry_prompt": await settings_store.get(session, "laundry_prompt"),
            # Today's outfit per owner ("" = household): the worn one, else the newest suggestion.
            "outfits_today": {
                owner: {"id": o.id, "garment_ids": o.garment_ids, "worn": o.worn, "source": o.source, "reason": o.reason}
                for owner, o in _today_outfits(outfits_today).items()
            },
        },
    }


def _today_outfits(outfits) -> dict:
    chosen: dict = {}
    for outfit in sorted(outfits, key=lambda o: (o.worn, o.id)):
        chosen[outfit.owner or ""] = outfit
    return chosen
