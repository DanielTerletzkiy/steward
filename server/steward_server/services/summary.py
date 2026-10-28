"""One snapshot of everything Home Assistant shows as sensors."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from . import chores as chores_service
from . import people as people_service
from . import receipts as receipts_service
from . import stock as stock_service
from . import tasks as tasks_service
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
    }
