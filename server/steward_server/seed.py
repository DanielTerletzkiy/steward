"""Demo data: a household with real REWE eBons. Only runs on an empty database."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import EventHub
from .models import ChoreLog, Location, Product
from .schemas import ChoreIn, LocationIn, ProductIn, ShoppingItemIn, TaskIn
from .services import Invalid, catalog, chores, receipts, shopping, stock, tasks
from .timeutil import today, utcnow

LOG = logging.getLogger("steward.seed")

LOCATIONS = [
    ("Fridge", False),
    ("Freezer", True),
    ("Pantry", False),
    ("Drinks", False),
    ("Bathroom", False),
    ("Household", False),
]

# name, brand, category, location, due_days, min_stock, unit, receipt aliases.
# A few eBon lines are deliberately left without an alias so the demo shows suggestions and review.
PRODUCTS = [
    ("Salami, thinly sliced", None, "Deli", "Fridge", 10, 0, "pack", ["SALAMI HAUCHFEIN"]),
    ("Pretzel", None, "Bakery", "Pantry", 2, 0, "pc", ["LAUGENBREZEL"]),
    ("1688 Classic bread", "Harry", "Bakery", "Pantry", 7, 0, "pc", ["ANNO 1688 KLASS."]),
    ("CurryKing", "Meica", "Ready meals", "Pantry", 180, 0, "pc", ["CURRYKING"]),
    ("Herb butter baguette", None, "Frozen", "Freezer", 90, 0, "pc", ["KR.BUTTERBAGUETT"]),
    ("Mini pretzel snacks", None, "Sweets & snacks", "Pantry", 60, 0, "pack", ["MINI-KRINGELGEB."]),
    ("Coca-Cola Zero Lemon 1.5 l (6-pack)", "Coca-Cola", "Drinks", "Drinks", 180, 0, "pack", ["ZERO LEMON"]),
    ("Monster Ultra White", "Monster", "Drinks", "Drinks", 365, 0, "can", ["MONSTER ULTR.WHI"]),
    ("Shower gel Hydra Energy", None, "Toiletries", "Bathroom", None, 1, "pc", ["DUSCHE HYDRA EN."]),
    ("Fusilli", None, "Pasta & rice", "Pantry", 365, 1, "pack", ["SPIRALEN"]),
    ("Prinzenrolle chocolate cookies", "De Beukelaer", "Sweets & snacks", "Pantry", 120, 0, "pack", ["PRINZENR.SCHOKO"]),
    ("Cream soap", None, "Toiletries", "Bathroom", None, 1, "pc", ["CREMESEIFE"]),
    ("Coleslaw", None, "Deli", "Fridge", 7, 0, "tub", ["KRAUTSALAT"]),
    ("ja! Snack box", "ja!", "Sweets & snacks", "Pantry", 90, 0, "pack", ["JA! KNABBERBOX"]),
    ("Milk chocolate 90 g", None, "Sweets & snacks", "Pantry", 180, 0, "bar", ["ALPENMILCH 90G"]),
    ("Still water Naturelle 1.5 l (6-pack)", None, "Drinks", "Drinks", 365, 1, "pack", ["NATURELLE"]),
    ("Coca-Cola Zero Cherry", "Coca-Cola", "Drinks", "Drinks", 180, 0, "pc", ["ZERO CHERRY"]),
    ("Multivitamin A-Z tablets", None, "Toiletries", "Bathroom", 365, 0, "pack", ["A-Z TABLETTEN"]),
    ("REWE Soft Cookies", "REWE", "Sweets & snacks", "Pantry", 60, 0, "pack", ["REWE SOFTCOOKIES"]),
    ("Earl Grey tea", None, "Coffee & tea", "Pantry", 365, 0, "pack", ["EARL GREY TEE"]),
    ("Thumbtacks", None, "Household", "Household", None, 0, "pack", ["REISSNAEGEL"]),
    ("Urväter sliced bread", None, "Bakery", "Pantry", 7, 0, "pc", []),
    ("Pizza Salami", None, "Frozen", "Freezer", 180, 1, "pc", ["PIZZA SALAMI"]),
    ("Lasagne", None, "Frozen", "Freezer", 180, 0, "pc", ["LASAGNE"]),
    ("Linguine", None, "Pasta & rice", "Pantry", 365, 0, "pack", ["LINGUINE HW NL"]),
    ("Udon noodles", None, "Pasta & rice", "Pantry", 365, 0, "pack", ["UDON NUDELN"]),
    ("Knorr Fix Spaghetti Bolognese", "Knorr", "Sauces & seasoning", "Pantry", 365, 0, "sachet", ["KNORR FIX BOL BE"]),
    ("Maggi Fix Lasagne", "Maggi", "Sauces & seasoning", "Pantry", 365, 0, "sachet", ["MAGGI FIX LASAG"]),
    ("Tomato paste", None, "Sauces & seasoning", "Pantry", 365, 1, "tube", ["TOMATENMARK"]),
    ("Mild gherkins", None, "Deli", "Pantry", 365, 0, "jar", ["MILDE GUERKCHEN"]),
    ("Peanuts", None, "Sweets & snacks", "Pantry", 180, 0, "pack", ["ERDNUESSE"]),
    # Not from the eBons: everyday products with min stock, so shopping-list automation has something to do.
    ("Whole milk 1 l", None, "Dairy", "Fridge", 8, 2, "pack", []),
    ("Eggs (10)", None, "Dairy", "Fridge", 21, 1, "pack", []),
    ("Butter", None, "Dairy", "Fridge", 30, 1, "pc", []),
    ("Coffee beans 1 kg", None, "Coffee & tea", "Pantry", 300, 1, "pack", []),
    ("Dishwasher tabs", None, "Household", "Household", None, 10, "pc", []),
    ("AA batteries", None, "Household", "Household", None, 4, "pc", []),
]

# product, amount, due in days (None = product default), days since purchase
EXTRA_STOCK = [
    ("Whole milk 1 l", 1, 2, 4),
    ("Eggs (10)", 1, 3, 15),
    ("Butter", 1, -1, 30),
    ("Coffee beans 1 kg", 1, None, 10),
    ("Dishwasher tabs", 14, None, 20),
    ("AA batteries", 2, None, 60),
]

# name, icon, schedule, interval, weekdays, assignment, last done days ago
CHORES = [
    ("Put out the recycling bin", "mdi:recycle", "weekly", 2, [today().weekday()], "rotation", 14),
    ("Vacuum", "mdi:robot-vacuum", "dynamic", 7, [], "least_done", 8),
    ("Run the dishwasher", "mdi:dishwasher", "dynamic", 2, [], "least_done", 1),
    ("Water the plants", "mdi:flower", "dynamic", 4, [], "least_done", 2),
    ("Clean the bathroom", "mdi:shower", "weekly", 1, [5], "rotation", 6),
    ("Wipe out the fridge", "mdi:fridge-outline", "monthly", 1, [], "least_done", 20),
    ("Test the smoke detectors", "mdi:smoke-detector-variant", "monthly", 6, [], "none", 100),
]

TASKS = [
    ("File the 2025 tax return", "Paperwork", 12),
    ("Bleed the radiators", "Home", -1),
    ("Buy a bike lock", "Errands", None),
    ("Book a dentist appointment", "Health", 3),
]


async def seed_demo(session: AsyncSession, hub: EventHub, receipts_dir: Path | None) -> None:
    if await session.scalar(select(func.count()).select_from(Product)):
        return
    LOG.info("Seeding demo data")
    locations: dict[str, int] = {}
    for name, freezer in LOCATIONS:
        locations[name] = (await catalog.create_location(session, hub, LocationIn(name=name, is_freezer=freezer))).id
    products: dict[str, int] = {}
    for name, brand, category, location, due_days, min_stock, unit, aliases in PRODUCTS:
        product = await catalog.create_product(
            session,
            hub,
            ProductIn(
                name=name,
                brand=brand,
                category=category,
                location_id=locations[location],
                due_days=due_days,
                min_stock=min_stock,
                unit=unit,
                receipt_aliases=aliases,
            ),
        )
        products[name] = product.id

    # Real eBons: the older ones go into stock, the newest stays open for review in the demo.
    if receipts_dir and receipts_dir.is_dir():
        imported = []
        for pdf in sorted(receipts_dir.glob("*.pdf")):
            try:
                imported.append(await receipts.import_ebon(session, hub, pdf.read_bytes(), source="demo"))
            except Invalid as exc:
                LOG.warning("Skipping %s: %s", pdf.name, exc)
        imported.sort(key=lambda r: r.at)
        for receipt in imported[:-1]:
            await receipts.stock_receipt(session, hub, receipt.id, actor="demo")

    for name, amount, due_in, bought_days_ago in EXTRA_STOCK:
        await stock.purchase(
            session,
            hub,
            products[name],
            amount,
            due_date=today() + timedelta(days=due_in) if due_in is not None else None,
            at=utcnow() - timedelta(days=bought_days_ago),
            source="seed",
        )
    # Using a bit of everything makes the journal and min-stock automation visible.
    for name, amount in (("Whole milk 1 l", 0.5), ("Pretzel", 1), ("AA batteries", 1)):
        try:
            await stock.consume(session, hub, products[name], amount, source="seed")
        except Invalid:
            pass

    for name, icon, schedule, interval, weekdays, assignment, last_done in CHORES:
        chore = await chores.create_chore(
            session,
            hub,
            ChoreIn(name=name, icon=icon, schedule=schedule, interval=interval, weekdays=weekdays, assignment=assignment),
        )
        done_at = utcnow() - timedelta(days=last_done)
        session.add(ChoreLog(chore_id=chore.id, done_at=done_at, source="seed"))
        model = await session.get(chores.Chore, chore.id)
        model.next_due = chores.next_due_after(model, done_at)
        await session.commit()

    for name, category, due_in in TASKS:
        await tasks.create_task(
            session,
            hub,
            TaskIn(name=name, category=category, due_date=today() + timedelta(days=due_in) if due_in is not None else None),
        )

    target = await shopping.default_list(session)
    for text in ("Toilet paper", "Onions", "Coffee beans 1 kg"):
        await shopping.add_item(session, hub, target.id, ShoppingItemIn(text=text))
    await shopping.add_missing(session, hub, target.id)
    LOG.info("Demo data ready")
