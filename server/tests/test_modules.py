"""Equipment, wardrobe, outfit engine, scanning and the HA bridge."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from steward_server.db import Database
from steward_server.demo_art import garment_picture, manual_pdf
from steward_server.events import EventHub
from steward_server.ha_bridge import BridgeError, HABridge
from steward_server.schemas import EquipmentIn, GarmentIn, ProductIn
from steward_server.services import ai, catalog, equipment, outfits, scan, wardrobe
from steward_server.services.files import FileStore
from steward_server.services.weather import summarize


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


@pytest.fixture
def files(tmp_path):
    return FileStore(tmp_path)


def weather(feels_min: float, feels_max: float, rain: int = 0, wind: float = 5) -> dict:
    return {"temp_min": feels_min + 2, "temp_max": feels_max + 2, "feels_min": feels_min, "feels_max": feels_max,
            "rain_probability": rain, "rain_from": "16:00" if rain else None, "wind_max": wind, "conditions": []}  # fmt: skip


async def closet(session, hub) -> dict[str, int]:
    pieces = [
        ("Tee", "t-shirt", 1, (18, 35), "none", 2, ["comfort", "going_out"]),
        ("Oxford", "shirt", 2, (12, 26), "none", 3, ["work"]),
        ("Merino", "sweater", 3, (2, 15), "none", 3, ["work", "comfort"]),
        ("Jeans", "jeans", 3, (-5, 24), "none", 2, ["comfort", "work"]),
        ("Shorts", "shorts", 1, (20, 35), "none", 1, ["comfort"]),
        ("Rain jacket", "rain jacket", 2, (5, 18), "waterproof", 2, ["comfort"]),
        ("Denim jacket", "jacket", 2, (12, 22), "none", 2, ["comfort"]),
        ("Coat", "coat", 5, (-10, 8), "resistant", 4, ["work"]),
        ("Sneakers", "sneakers", 2, (8, 30), "none", 2, ["comfort"]),
        ("Boots", "boots", 4, (-8, 14), "resistant", 3, ["work"]),
        ("Scarf", "scarf", 4, (-10, 8), "none", 2, ["comfort", "work"]),
    ]
    ids = {}
    for name, category, warmth, (lo, hi), rain, formality, uses in pieces:
        g = await wardrobe.create_garment(
            session, hub,
            GarmentIn(name=name, category=category, warmth=warmth, temp_min=lo, temp_max=hi, rain=rain,
                      formality=formality, uses=uses, colors=["navy"]),
        )  # fmt: skip
        ids[name] = g.id
    return ids


def names(pieces) -> set[str]:
    return {g.name for g in pieces}


async def context(session, temp_min, temp_max, rain=0, occasion="comfort"):
    return outfits.Context(
        day=date(2026, 10, 28), occasion=occasion, weather=weather(temp_min, temp_max, rain),
        profile=await wardrobe.get_profile(session, None),
    )  # fmt: skip


async def test_categories_set_layer_and_wears_per_wash(session, hub):
    jeans = await wardrobe.create_garment(session, hub, GarmentIn(name="Jeans", category="Jeans"))
    assert (jeans.category, jeans.layer, jeans.wears_per_wash) == ("jeans", "bottom", 6)


async def test_wearing_moves_pieces_to_laundry_and_washing_resets(session, hub):
    ids = await closet(session, hub)
    tee, jeans, shoes = ids["Tee"], ids["Jeans"], ids["Sneakers"]
    worn = {g.name: g.state for g in await wardrobe.wear(session, hub, [tee, jeans, shoes])}
    assert worn == {"Tee": "laundry", "Jeans": "worn", "Sneakers": "worn"}
    assert await wardrobe.laundry_done(session, hub) == 1
    washed = await wardrobe.get_garment(session, tee)
    assert (washed.state, washed.wears_since_wash) == ("drying", 0)  # dries for a day before it's suggested
    assert await wardrobe.dried(session, hub, [tee]) == 1
    assert (await wardrobe.get_garment(session, tee)).state == "clean"


async def test_cold_rainy_day_gets_warm_layers_and_rain_gear(session, hub):
    await closet(session, hub)
    garments = await wardrobe.list_garments(session)
    best = outfits.rules_outfits(garments, await context(session, 4, 9, rain=70))[0]
    layers = {g.layer for g in best}
    assert {"base", "bottom", "mid", "outer", "shoes"} <= layers
    outer = next(g for g in best if g.layer == "outer")
    shoes = next(g for g in best if g.layer == "shoes")
    assert outer.rain != "none" and shoes.name == "Boots"
    assert "Shorts" not in names(best)


async def test_warm_day_is_light(session, hub):
    await closet(session, hub)
    best = outfits.rules_outfits(await wardrobe.list_garments(session), await context(session, 22, 30))[0]
    assert names(best) & {"Tee", "Shorts"} and not {g.layer for g in best} & {"mid", "outer"}


async def test_dirty_pieces_are_never_suggested(session, hub):
    ids = await closet(session, hub)
    await wardrobe.update_garment(session, hub, ids["Jeans"], wardrobe.GarmentPatch(state="laundry"))
    for pieces in outfits.rules_outfits(await wardrobe.list_garments(session), await context(session, 4, 9)):
        assert "Jeans" not in names(pieces)


async def test_repair_fixes_incomplete_ai_outfits(session, hub):
    ids = await closet(session, hub)
    garments = await wardrobe.list_garments(session)
    ctx = await context(session, 5, 10, rain=80)
    # Shorts + tee + denim jacket in the rain, no shoes, plus an unknown id.
    pieces, notes = outfits.repair([ids["Tee"], ids["Denim jacket"], 999], garments, ctx)
    layers = {g.layer for g in pieces}
    assert {"base", "bottom", "outer", "shoes"} <= layers
    assert next(g for g in pieces if g.layer == "outer").rain != "none"
    assert notes


async def test_suggest_falls_back_to_rules_without_ai(session, hub, files):
    await closet(session, hub)
    suggestions = await outfits.suggest(
        session, hub, HABridge(), files, weather=weather(6, 12, rain=60), occasion="work", count=2
    )
    assert len(suggestions) == 2 and all(o.source == "rules" for o in suggestions)
    assert "60 % rain from 16:00" in suggestions[0].reason
    # A second round replaces the untouched first round.
    again = await outfits.suggest(session, hub, HABridge(), files, weather=weather(6, 12), count=1)
    assert len(await wardrobe.list_outfits(session)) == len(again) == 1


async def test_ai_outfits_are_validated(session, hub, files, monkeypatch):
    ids = await closet(session, hub)

    async def fake_generate(_session, _bridge, job, request):
        assert job == "outfits" and "Rain jacket" in request.instructions
        return {"outfits": [{"garment_ids": [ids["Tee"], ids["Jeans"]], "reason": "Easy day."}]}

    monkeypatch.setattr(ai, "available", lambda *_a: asyncio.sleep(0, True))
    monkeypatch.setattr(ai, "generate", fake_generate)
    [suggestion] = await outfits.suggest(session, hub, HABridge(), files, weather=weather(8, 14, rain=70), count=1)
    assert suggestion.source == "ai" and suggestion.reason == "Easy day."
    layers = {(await wardrobe.get_garment(session, i)).layer for i in suggestion.garment_ids}
    assert {"outer", "shoes"} <= layers  # added by the rule check


async def test_outfit_collage(session, hub, files):
    ids = await closet(session, hub)
    await wardrobe.set_photo(session, hub, files, ids["Tee"], garment_picture("t-shirt", "white"), "tee.png")
    outfit = await wardrobe.create_outfit(session, hub, wardrobe.OutfitIn(garment_ids=[ids["Tee"], ids["Jeans"]]))
    image = await outfits.outfit_image(session, files, outfit.id)
    assert image[:8] == b"\x89PNG\r\n\x1a\n"


async def test_manual_search_finds_page(session, hub, files):
    item = await equipment.create_equipment(session, hub, EquipmentIn(name="Coffee machine"))
    pdf = manual_pdf("Manual", ["Making coffee\nGrind finer for espresso.", "Descaling\nPour 100 ml of descaler into the tank."])
    await equipment.add_document(session, hub, files, item.id, pdf, filename="manual.pdf", content_type="application/pdf")
    [hit] = await equipment.search_manuals(session, "How do I descale it?")
    assert (hit.equipment_name, hit.page) == ("Coffee machine", 2)
    assert "«descaler»" in hit.snippet


def test_gs1_codes():
    parsed = scan.parse_code("(01)04012345678901(17)270331(10)LOT7")
    assert (parsed["code"], parsed["due_date"], parsed["lot"]) == ("4012345678901", "2027-03-31", "LOT7")
    raw = scan.parse_code("01040123456789011727040010ABC")
    assert (raw["code"], raw["due_date"], raw["lot"]) == ("4012345678901", "2027-04-30", "ABC")
    assert scan.parse_code("4006381333931")["code"] == "4006381333931"


async def test_scan_purchase_with_known_barcode(session, hub):
    milk = await catalog.create_product(session, hub, ProductIn(name="Milk", barcodes=["4006381333931"]))
    result = await scan.apply(session, hub, "4006381333931", "purchase")
    assert result["done"] and result["product_id"] == milk.id


def test_weather_summary_uses_daytime_hours():
    hourly = [
        {"datetime": f"2026-10-28T{h:02d}:00:00+01:00", "temperature": t, "apparent_temperature": t - 2,
         "precipitation_probability": p, "wind_speed": 10, "condition": "rainy" if p > 50 else "cloudy"}
        for h, t, p in [(3, 1, 0), (8, 6, 10), (12, 11, 20), (16, 10, 70), (20, 7, 60), (23, 4, 0)]
    ]  # fmt: skip
    summary = summarize({"hourly": hourly, "temperature_unit": "°C"}, date(2026, 10, 28))
    assert (summary["temp_min"], summary["temp_max"], summary["feels_min"]) == (6, 11, 4)
    assert (summary["rain_probability"], summary["rain_from"]) == (70, "16:00")


async def test_bridge_round_trip():
    bridge = HABridge()
    queue: asyncio.Queue = asyncio.Queue()
    bridge.register(queue, ["ai_task"])

    async def answer():
        request = await queue.get()
        bridge.resolve({"type": "ha_response", "id": request["id"], "result": {"ok": True}})

    task = asyncio.create_task(answer())
    assert await bridge.request("ai_task", instructions="hi") == {"ok": True}
    await task

    async def fail():
        request = await queue.get()
        bridge.resolve({"type": "ha_response", "id": request["id"], "error": "no AI entity"})

    task = asyncio.create_task(fail())
    with pytest.raises(BridgeError):
        await bridge.request("ai_task")
    await task


async def test_ai_config_keeps_keys_private(session, hub):
    bridge = HABridge()
    saved = await ai.save_config(
        session, hub, bridge,
        {"providers": [{"type": "anthropic", "api_key": "sk-test"}], "jobs": {"outfits": None}},
    )  # fmt: skip
    [provider] = saved["providers"]
    assert provider["api_key_set"] and "api_key" not in provider and provider["model"] == "claude-opus-5-5"
    # Saving again without a key keeps the stored key.
    again = await ai.save_config(session, hub, bridge, {"providers": [{**provider}], "jobs": {"scan": provider["id"]}})
    assert again["providers"][0]["api_key_set"]
    assert again["effective"]["scan"]["type"] == "anthropic"


async def test_suggestions_vary(session, hub):
    await closet(session, hub)
    first, second, *_ = outfits.rules_outfits(await wardrobe.list_garments(session), await context(session, 8, 14), 3)
    assert len(outfits._main(first) ^ outfits._main(second)) >= 4  # two pieces swapped


async def test_ask_pieces_stop_being_suggested_until_washed_or_still_fine(session, hub):
    ids = await closet(session, hub)  # jeans: 6 wears, category default "ask"
    jeans = await wardrobe.get_garment(session, ids["Jeans"])
    assert jeans.laundry_mode_effective == "ask"
    for _ in range(6):
        await wardrobe.wear(session, hub, [jeans.id])
    jeans = await wardrobe.get_garment(session, jeans.id)
    assert (jeans.state, jeans.needs_wash) == ("worn", True)
    assert jeans.id not in {g.id for g in outfits.available(await wardrobe.list_garments(session))}
    await wardrobe.still_fine(session, hub, [jeans.id], wears=2)
    assert not (await wardrobe.get_garment(session, jeans.id)).needs_wash
    await wardrobe.wear(session, hub, [jeans.id])
    await wardrobe.wear(session, hub, [jeans.id])
    assert (await wardrobe.get_garment(session, jeans.id)).needs_wash


async def test_socks_go_to_the_laundry_and_are_never_in_outfits(session, hub):
    socks = await wardrobe.create_garment(session, hub, GarmentIn(name="Socks", category="socks"))
    assert (socks.layer, socks.laundry_mode_effective) == ("underwear", "auto")
    assert socks.id not in {g.id for g in outfits.available([socks])}
    [worn] = await wardrobe.wear(session, hub, [socks.id])
    assert worn.state == "laundry"


async def test_washing_cycle_and_drying_time(session, hub):
    from datetime import timedelta

    from steward_server.services import settings as settings_store
    from steward_server.timeutil import utcnow

    tee = await wardrobe.create_garment(session, hub, GarmentIn(name="Tee", category="t-shirt"))
    await wardrobe.wear(session, hub, [tee.id])
    assert await wardrobe.start_wash(session, hub) == 1
    assert (await wardrobe.get_garment(session, tee.id)).state == "washing"
    await wardrobe.washed(session, hub)
    tee = await wardrobe.get_garment(session, tee.id)
    assert tee.state == "drying" and tee.dry_until is not None
    assert await wardrobe.release_dried(session, hub) == 0  # still wet
    tee.dry_until = utcnow() - timedelta(minutes=1)
    await session.commit()
    assert await wardrobe.release_dried(session, hub) == 1
    # "Until I mark them dry": no automatic release.
    await settings_store.put(session, hub, wardrobe.SETTINGS_KEY, {"drying_hours": None})
    await wardrobe.wear(session, hub, [tee.id])
    await wardrobe.washed(session, hub)
    tee = await wardrobe.get_garment(session, tee.id)
    assert (tee.state, tee.dry_until) == ("drying", None)
