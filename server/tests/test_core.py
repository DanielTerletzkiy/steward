"""Core behaviour: stock ledger, chore schedules, receipt import and matching."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from steward_server.db import Database
from steward_server.events import EventHub
from steward_server.models import Chore
from steward_server.schemas import ChoreIn, PersonIn, ProductIn
from steward_server.services import Invalid, catalog, chores, people, receipts, shopping, stock
from steward_server.textnorm import as_receipt_name, normalize_receipt_text

SAMPLES = Path(__file__).parents[2] / "samples" / "ebons"


@pytest.fixture
async def session(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_all()
    async with db.sessions() as s:
        yield s
    await db.dispose()


@pytest.fixture
def hub():
    return EventHub()


def test_receipt_names():
    assert normalize_receipt_text("Erdnüsse  geröstet") == "ERDNUESSE GEROESTET"
    assert as_receipt_name("Kräuterbutter-Baguette") == "KRAEUTERBUTTER-B"


async def test_consume_uses_opened_then_first_expiring(session, hub):
    milk = await catalog.create_product(session, hub, ProductIn(name="Milch", min_stock=1))
    late = await stock.purchase(session, hub, milk.id, 1, due_date=datetime(2030, 1, 10).date())
    early = await stock.purchase(session, hub, milk.id, 1, due_date=datetime(2030, 1, 5).date())
    await stock.consume(session, hub, milk.id, 1)
    await session.refresh(early)
    await session.refresh(late)
    assert (early.amount, late.amount) == (0, 1)


async def test_falling_below_min_stock_adds_to_shopping_list(session, hub):
    milk = await catalog.create_product(session, hub, ProductIn(name="Milch", min_stock=2))
    await stock.purchase(session, hub, milk.id, 2)
    await stock.consume(session, hub, milk.id, 1)
    items = await shopping.items(session, (await shopping.default_list(session)).id)
    assert [(i.text, i.amount) for i in items] == [("Milch", 1)]


async def test_undo_consume(session, hub):
    milk = await catalog.create_product(session, hub, ProductIn(name="Milch"))
    await stock.purchase(session, hub, milk.id, 1)
    await stock.consume(session, hub, milk.id, 1)
    last = (await stock.journal(session, 1))[0]
    await stock.undo(session, hub, last.id)
    assert (await stock.stock_overview(session))[0].amount == 1
    with pytest.raises(Invalid):
        await stock.undo(session, hub, last.id)


@pytest.mark.parametrize(
    ("schedule", "interval", "weekdays", "done", "expected"),
    [
        ("dynamic", 3, [], datetime(2026, 10, 1, 18, 0, tzinfo=UTC), datetime(2026, 10, 4, 18, 0, tzinfo=UTC)),
        # Weekly on Wednesday (2): done on Monday 2026-10-26 -> due Wednesday, local midnight (UTC+1).
        ("weekly", 1, [2], datetime(2026, 10, 26, 12, 0, tzinfo=UTC), datetime(2026, 10, 27, 23, 0, tzinfo=UTC)),
        ("weekly", 2, [2], datetime(2026, 10, 26, 12, 0, tzinfo=UTC), datetime(2026, 11, 3, 23, 0, tzinfo=UTC)),
        ("monthly", 1, [], datetime(2026, 1, 31, 12, 0, tzinfo=UTC), datetime(2026, 2, 27, 23, 0, tzinfo=UTC)),
        ("manual", 1, [], datetime(2026, 1, 31, 12, 0, tzinfo=UTC), None),
    ],
)
def test_next_due(schedule, interval, weekdays, done, expected):
    chore = Chore(name="x", schedule=schedule, interval=interval, weekdays=weekdays)
    assert chores.next_due_after(chore, done) == expected


async def test_rotation_and_least_done(session, hub):
    await people.sync(session, hub, [PersonIn(id="person.a", name="A"), PersonIn(id="person.b", name="B")])
    rotating = await chores.create_chore(session, hub, ChoreIn(name="Müll", assignment="rotation"))
    assert rotating.next_assignee == "person.a"
    rotating = await chores.execute(session, hub, rotating.id)
    assert rotating.next_assignee == "person.b"
    least = await chores.create_chore(session, hub, ChoreIn(name="Saugen", assignment="least_done"))
    least = await chores.execute(session, hub, least.id, person_id="person.a")
    assert least.next_assignee == "person.b"


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="sample eBons are not in the repository")
async def test_ebon_import_matches_and_learns(session, hub):
    await catalog.create_product(session, hub, ProductIn(name="Laugenbrezel"))
    await catalog.create_product(session, hub, ProductIn(name="Salami hauchfein"))
    pdf = sorted(SAMPLES.glob("*.pdf"))[0].read_bytes()
    receipt = await receipts.import_ebon(session, hub, pdf)
    assert round(sum(line.total for line in receipt.lines), 2) == receipt.total
    assert (await receipts.import_ebon(session, hub, pdf)).id == receipt.id  # idempotent

    by_text = {line.raw_text: line for line in receipt.lines}
    if "LAUGENBREZEL" in by_text:
        assert by_text["LAUGENBREZEL"].method == "fuzzy"
        line = by_text["LAUGENBREZEL"]
        product_id = line.product_id
        from steward_server.schemas import LineMatchIn

        await receipts.set_line_product(session, hub, receipt.id, line.id, LineMatchIn(product_id=product_id))
        await session.refresh(line)
        assert (line.method, line.confirmed) == ("manual", True)
