"""Demo data: a household with real REWE eBons. Only runs on an empty database."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .demo_art import garment_picture, manual_pdf
from .events import EventHub
from .models import Chore, ChoreLog, Equipment, Garment, Product, Recipe
from .schemas import (
    ChoreIn,
    EquipmentIn,
    GarmentIn,
    IngredientIn,
    LocationIn,
    MealPlanIn,
    OutfitIn,
    ProductIn,
    RecipeIn,
    ShoppingItemIn,
    TaskIn,
)
from .services import Invalid, catalog, chores, equipment, receipts, recipes, shopping, stock, tasks, wardrobe
from .services.files import FileStore
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


# name, brand, model, room, bought days ago, price, warranty years, linked chore, consumable products
EQUIPMENT = [
    ("Coffee machine", "De'Longhi", "Magnifica S ECAM 22.110", "Kitchen", 700, 349.0, 2, "Descale the coffee machine", ["Descaler", "Coffee beans 1 kg"]),
    ("Dishwasher", "Bosch", "SMV4HVX31E", "Kitchen", 1100, 579.0, 2, "Run the dishwasher", ["Dishwasher tabs"]),
    ("Robot vacuum", "Roborock", "Q7 Max", "Living room", 400, 299.0, 2, "Vacuum", []),
    ("Washing machine", "LG", "F4WV709P1E (ThinQ)", "Bathroom", 2000, 899.0, 2, "Hang up the laundry", []),
    ("Smoke detectors (4)", "Hekatron", "Genius Plus", "Hallway", 900, 120.0, 10, "Test the smoke detectors", []),
]

KINDS = {"Dishwasher": "dishwasher", "Robot vacuum": "vacuum", "Washing machine": "washer"}

COFFEE_MANUAL = [
    "Contents\n1 Safety  2 First use  3 Making coffee  4 Cleaning  5 Descaling  6 Troubleshooting",
    "Making coffee\nFill the water tank and the bean container. Turn the grinder knob to adjust the grind:\n"
    "finer for a stronger espresso, coarser for a milder coffee. Press the cup button once for one cup.",
    "Cleaning\nEmpty the grounds container daily. Rinse the drip tray and the milk frother after each use.\n"
    "Remove the brewing unit once a week and rinse it under lukewarm water. Do not use detergent.",
    "Descaling\nWhen the descale light comes on, descale the machine (about every 3 months).\n"
    "1. Empty the drip tray and remove the water filter.\n"
    "2. Pour 100 ml of descaler into the water tank and fill it with water up to level A.\n"
    "3. Place a 1.5 l container under the coffee spout and press the descale button for 5 seconds.\n"
    "4. When the tank is empty, rinse it and fill it with fresh water up to MAX, then press OK.\n"
    "The descaling cycle takes about 30 minutes.",
    "Troubleshooting\nCoffee is not hot: preheat the cups with hot water.\n"
    "Coffee comes out slowly: the grind is too fine, turn the grinder knob one step coarser.\n"
    "Water filter: replace it every 2 months or after 60 litres.",
]

# name, category, color, warmth, temp range, rain, windproof, formality, uses, seasons, state, wears, price
GARMENTS = [
    ("White tee", "t-shirt", "white", 1, (18, 35), "none", False, 2, ["home", "comfort", "going_out"], ["summer", "transition"], "clean", 14, 15.0),
    ("Black tee", "t-shirt", "black", 1, (18, 35), "none", False, 2, ["home", "comfort", "going_out"], ["summer", "transition"], "laundry", 22, 15.0),
    ("Navy long-sleeve", "long-sleeve", "navy", 2, (10, 22), "none", False, 2, ["comfort", "going_out"], ["transition"], "clean", 9, 25.0),
    ("Light blue oxford shirt", "shirt", "light blue", 2, (12, 26), "none", False, 3, ["work", "going_out"], ["summer", "transition", "winter"], "clean", 11, 49.0),
    ("Grey merino sweater", "sweater", "grey", 3, (2, 15), "none", False, 3, ["work", "going_out", "comfort"], ["transition", "winter"], "worn", 18, 89.0),
    ("Green hoodie", "hoodie", "green", 3, (5, 17), "none", False, 1, ["home", "comfort", "sport"], ["transition", "winter"], "clean", 30, 45.0),
    ("Olive rain jacket", "rain jacket", "olive", 2, (5, 18), "waterproof", True, 2, ["comfort", "going_out", "sport"], ["transition"], "clean", 12, 129.0),
    ("Navy wool coat", "coat", "navy", 5, (-10, 8), "resistant", True, 4, ["work", "going_out", "formal"], ["winter"], "clean", 6, 220.0),
    ("Denim jacket", "jacket", "blue", 2, (12, 22), "none", False, 2, ["going_out", "comfort"], ["transition"], "clean", 7, 79.0),
    ("Dark jeans", "jeans", "navy", 3, (-5, 24), "none", False, 2, ["going_out", "comfort", "work"], ["transition", "winter"], "worn", 40, 89.0),
    ("Beige chinos", "chinos", "beige", 2, (10, 28), "none", False, 3, ["work", "going_out"], ["summer", "transition"], "clean", 8, 59.0),
    ("Grey joggers", "joggers", "grey", 3, (0, 20), "none", False, 1, ["home", "comfort", "sport"], ["transition", "winter"], "clean", 25, 35.0),
    ("Black shorts", "shorts", "black", 1, (20, 35), "none", False, 1, ["home", "comfort", "sport"], ["summer"], "stored", 10, 25.0),
    ("White sneakers", "sneakers", "white", 2, (8, 30), "none", False, 2, ["comfort", "going_out"], ["summer", "transition"], "clean", 60, 99.0),
    ("Brown leather boots", "boots", "brown", 4, (-8, 14), "resistant", True, 3, ["work", "going_out"], ["transition", "winter"], "clean", 35, 169.0),
    ("Running shoes", "sneakers", "orange", 2, (0, 30), "none", False, 1, ["sport"], ["summer", "transition", "winter"], "clean", 50, 120.0),
    ("Grey wool scarf", "scarf", "grey", 4, (-10, 8), "none", True, 2, ["going_out", "work", "comfort"], ["winter"], "clean", 12, 39.0),
    ("Black beanie", "hat", "black", 4, (-10, 6), "none", True, 1, ["comfort", "going_out"], ["winter"], "clean", 9, 19.0),
]


# name, servings, minutes, tags, ingredients as (line, product, stock amount per batch), steps
RECIPES = [
    ("Linguine Bolognese", 2, 30, ["Pasta", "Quick"], [
        ("250 g linguine", "Linguine", 0.5), ("1 sachet Knorr Fix Spaghetti Bolognese", "Knorr Fix Spaghetti Bolognese", 1),
        ("2 tbsp tomato paste", "Tomato paste", 0.1), ("400 g minced beef", None, None), ("1 onion", None, None),
    ], "Brown the minced beef with the chopped onion.\nStir in the tomato paste and the sauce mix with 400 ml water; simmer 10 minutes.\nCook the linguine and toss with the sauce."),
    ("Lasagne al forno", 4, 75, ["Oven", "Pasta"], [
        ("1 sachet Maggi Fix Lasagne", "Maggi Fix Lasagne", 1), ("500 g minced beef", None, None),
        ("250 g lasagne sheets", None, None), ("2 tbsp tomato paste", "Tomato paste", 0.1), ("200 g grated cheese", None, None),
        ("1 tbsp butter", "Butter", 0.1),
    ], "Brown the beef, add tomato paste, the sauce mix and 500 ml water.\nLayer sauce and sheets in a buttered dish, finish with cheese.\nBake 40 minutes at 200 °C."),
    ("Udon stir-fry", 2, 20, ["Quick", "Noodles"], [
        ("1 pack udon noodles", "Udon noodles", 1), ("2 eggs", "Eggs (10)", 0.2), ("1 carrot", None, None),
        ("2 tbsp soy sauce", None, None), ("Spring onions, optional", None, None),
    ], "Cut the carrot into thin sticks and stir-fry for 3 minutes.\nAdd the noodles and the soy sauce, then push aside and scramble the eggs.\nToss everything together; top with spring onions."),
    ("Pretzel breakfast", 1, 5, ["Breakfast"], [
        ("2 pretzels", "Pretzel", 2), ("Butter", "Butter", 0.05), ("A few slices of salami", "Salami, thinly sliced", 0.3),
        ("Mild gherkins, optional", "Mild gherkins", None),
    ], "Halve the pretzels, butter them and add salami and gherkins."),
    ("Scrambled eggs", 2, 10, ["Breakfast", "Quick"], [
        ("4 eggs", "Eggs (10)", 0.4), ("1 tbsp butter", "Butter", 0.05), ("50 ml milk", "Whole milk 1 l", 0.05),
        ("Salt and pepper", None, None),
    ], "Whisk eggs with milk, salt and pepper.\nCook slowly in butter, stirring, until just set."),
]  # fmt: skip

# days from today, slot, recipe or note, done
MEAL_PLAN = [
    (0, "breakfast", "Pretzel breakfast", True),
    (0, "dinner", "Udon stir-fry", False),
    (1, "dinner", "Linguine Bolognese", False),
    (2, "dinner", "Lasagne al forno", False),
    (3, "dinner", "Eating out with friends", False),
    (4, "breakfast", "Scrambled eggs", False),
]


async def seed_demo(session: AsyncSession, hub: EventHub, files: FileStore, receipts_dir: Path | None) -> None:
    """Each module seeds itself when its tables are empty, so older demo databases pick up new modules."""
    if not await session.scalar(select(func.count()).select_from(Product)):
        await seed_core(session, hub, receipts_dir)
    if not await session.scalar(select(func.count()).select_from(Equipment)):
        await seed_equipment(session, hub, files)
    if not await session.scalar(select(func.count()).select_from(Garment)):
        await seed_wardrobe(session, hub, files)
    if not await session.scalar(select(func.count()).select_from(Recipe)):
        await seed_kitchen(session, hub)


async def seed_core(session: AsyncSession, hub: EventHub, receipts_dir: Path | None) -> None:
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


async def seed_equipment(session: AsyncSession, hub: EventHub, files: FileStore) -> None:
    LOG.info("Seeding demo equipment")
    descaler = await catalog.find_product_by_name(session, "Descaler")
    if descaler is None:
        household = next((loc for loc in await catalog.list_locations(session) if loc.name == "Household"), None)
        descaler = await catalog.create_product(
            session,
            hub,
            ProductIn(name="Descaler", category="Household", unit="bottle", min_stock=1,
                      location_id=household.id if household else None),
        )  # fmt: skip
    if not await session.scalar(select(func.count()).select_from(Chore).where(Chore.name == "Descale the coffee machine")):
        chore = await chores.create_chore(
            session, hub,
            ChoreIn(name="Descale the coffee machine", icon="mdi:coffee-maker-outline", schedule="monthly", interval=3,
                    assignment="least_done", consume_product_id=descaler.id, consume_amount=0.25),
        )  # fmt: skip
        session.add(ChoreLog(chore_id=chore.id, done_at=utcnow() - timedelta(days=80), source="seed"))
        model = await session.get(Chore, chore.id)
        model.next_due = chores.next_due_after(model, utcnow() - timedelta(days=80))
        await session.commit()
    if not await session.scalar(select(func.count()).select_from(Chore).where(Chore.name == "Hang up the laundry")):
        # Manual: it becomes due when the washing machine reports a finished cycle.
        await chores.create_chore(
            session, hub, ChoreIn(name="Hang up the laundry", icon="mdi:tshirt-crew-outline", schedule="manual")
        )
    chore_ids = {c.name: c.id for c in await chores.list_chores(session)}
    product_ids = {p.name: p.id for p in await catalog.list_products(session)}
    for name, brand, model_name, room, bought, price, years, chore, consumables in EQUIPMENT:
        purchased = today() - timedelta(days=bought)
        item = await equipment.create_equipment(
            session, hub,
            EquipmentIn(
                name=name, brand=brand, model=model_name, room=room, purchased_on=purchased, price=price,
                kind=KINDS.get(name, "other"),
                warranty_until=purchased.replace(year=purchased.year + years), shop="MediaMarkt" if price > 200 else None,
                chore_ids=[chore_ids[chore]] if chore in chore_ids else [],
                consumable_ids=[product_ids[c] for c in consumables if c in product_ids],
            ),
        )  # fmt: skip
        if name == "Coffee machine":
            await equipment.add_document(
                session, hub, files, item.id, manual_pdf("De'Longhi Magnifica S - User manual", COFFEE_MANUAL),
                filename="Magnifica S manual.pdf", content_type="application/pdf", title="User manual",
            )  # fmt: skip


async def seed_wardrobe(session: AsyncSession, hub: EventHub, files: FileStore) -> None:
    LOG.info("Seeding demo wardrobe")
    ids: dict[str, int] = {}
    for (name, category, color, warmth, (t_min, t_max), rain, windproof, formality, uses, seasons, state, wears,
         price) in GARMENTS:  # fmt: skip
        garment = await wardrobe.create_garment(
            session, hub,
            GarmentIn(name=name, category=category, colors=[color], pattern="denim" if category == "jeans" else "solid",
                      warmth=warmth, temp_min=t_min, temp_max=t_max, rain=rain, windproof=windproof,
                      formality=formality, uses=uses, seasons=seasons, price=price),
        )  # fmt: skip
        await wardrobe.set_photo(session, hub, files, garment.id, garment_picture(category, color), f"{name}.png")
        model = await wardrobe.get_garment(session, garment.id)
        model.state, model.wear_count = state, wears
        model.wears_since_wash = {"worn": 1, "laundry": model.wears_per_wash}.get(state, 0)
        model.last_worn = today() - timedelta(days=1 if state in ("worn", "laundry") else 6)
        ids[name] = garment.id
    await session.commit()
    outfit = await wardrobe.create_outfit(
        session, hub,
        OutfitIn(day=today() - timedelta(days=1), garment_ids=[ids["Black tee"], ids["Grey merino sweater"],
                 ids["Dark jeans"], ids["White sneakers"]], occasion="work"),
    )  # fmt: skip
    outfit.worn = True  # the wear counts above already include it
    await session.commit()


async def seed_kitchen(session: AsyncSession, hub: EventHub) -> None:
    LOG.info("Seeding demo recipes")
    products = {p.name: p.id for p in await catalog.list_products(session)}
    ids = {}
    for name, servings, minutes, tags, ingredients, steps in RECIPES:
        recipe = await recipes.create_recipe(
            session, hub,
            RecipeIn(
                name=name, servings=servings, minutes=minutes, tags=tags, instructions=steps,
                ingredients=[
                    IngredientIn(text=line, product_id=products.get(product), stock_amount=amount)
                    if product in products else IngredientIn(text=line, product_id=None)
                    for line, product, amount in ingredients
                ],
            ),
        )  # fmt: skip
        ids[name] = recipe.id
    for days, slot, what, done in MEAL_PLAN:
        entry = await recipes.add_meal(
            session, hub,
            MealPlanIn(day=today() + timedelta(days=days), slot=slot, recipe_id=ids.get(what),
                       note=None if what in ids else what),
        )  # fmt: skip
        if done:
            entry.done = True
    await session.commit()
