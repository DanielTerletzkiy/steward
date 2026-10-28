"""Actions (services) for automations, scripts and voice."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .client import StewardClient, StewardError
from .const import DOMAIN

ATTR_PRODUCT = "product"
ATTR_AMOUNT = "amount"


def _runtime(hass: HomeAssistant):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    raise ServiceValidationError("Steward is not set up")


async def _product_id(hass: HomeAssistant, value: str | int) -> int:
    """Accept a product id or (case-insensitive) name."""
    data = _runtime(hass).coordinator.data
    if isinstance(value, int) or str(value).isdigit():
        return int(value)
    wanted = str(value).strip().casefold()
    products = [item["product"] for item in data.stock]
    match = next((p for p in products if p["name"].casefold() == wanted), None)
    match = match or next((p for p in products if wanted in p["name"].casefold()), None)
    if match is None:
        raise ServiceValidationError(f"No product called '{value}'")
    return match["id"]


def _chore_id(hass: HomeAssistant, value: str | int) -> int:
    chores = _runtime(hass).coordinator.data.chores
    if isinstance(value, int) or str(value).isdigit():
        return int(value)
    wanted = str(value).strip().casefold()
    match = next((c for c in chores if c["name"].casefold() == wanted), None)
    match = match or next((c for c in chores if wanted in c["name"].casefold()), None)
    if match is None:
        raise ServiceValidationError(f"No chore called '{value}'")
    return match["id"]


def _actor(call: ServiceCall) -> str | None:
    return call.context.user_id


async def _run(hass: HomeAssistant, coro) -> Any:
    try:
        result = await coro
    except StewardError as err:
        raise HomeAssistantError(str(err)) from err
    await _runtime(hass).coordinator.async_request_refresh()
    return result


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    def client() -> StewardClient:
        return _runtime(hass).client

    async def purchase(call: ServiceCall) -> None:
        payload = {"product_id": await _product_id(hass, call.data[ATTR_PRODUCT]), "amount": call.data[ATTR_AMOUNT]}
        if due := call.data.get("due_date"):
            payload["due_date"] = due.isoformat()
        if (price := call.data.get("price")) is not None:
            payload["unit_price"] = price
        await _run(hass, client().post("api/stock/purchase", payload, actor=_actor(call)))

    async def consume(call: ServiceCall) -> None:
        payload = {
            "product_id": await _product_id(hass, call.data[ATTR_PRODUCT]),
            "amount": call.data[ATTR_AMOUNT],
            "spoiled": call.data.get("spoiled", False),
        }
        await _run(hass, client().post("api/stock/consume", payload, actor=_actor(call)))

    async def execute_chore(call: ServiceCall) -> None:
        chore_id = _chore_id(hass, call.data["chore"])
        payload = {"person_id": call.data.get("person"), "skipped": call.data.get("skipped", False)}
        await _run(hass, client().post(f"api/chores/{chore_id}/execute", payload))

    async def add_to_shopping_list(call: ServiceCall) -> None:
        list_id = _runtime(hass).coordinator.data.shopping_lists[0]["id"]
        payload = {"text": call.data["item"], "amount": call.data.get(ATTR_AMOUNT, 1)}
        await _run(hass, client().post(f"api/shopping-lists/{list_id}/items", payload))

    async def import_receipt(call: ServiceCall) -> ServiceResponse:
        path = Path(call.data["path"])
        if not hass.config.is_allowed_path(str(path)):
            raise ServiceValidationError(f"{path} is not in allowlist_external_dirs")
        data = await hass.async_add_executor_job(path.read_bytes)
        receipt = await _run(hass, client().upload_receipt(path.name, data))
        items = [line for line in receipt["lines"] if line["kind"] == "item"]
        return {
            "receipt_id": receipt["id"],
            "total": receipt["total"],
            "lines": len(items),
            "matched": sum(1 for line in items if line["product_id"]),
        }

    async def get_stock(call: ServiceCall) -> ServiceResponse:
        stock = _runtime(hass).coordinator.data.stock
        wanted = (call.data.get(ATTR_PRODUCT) or "").casefold()
        return {
            "products": [
                {
                    "name": item["product"]["name"],
                    "amount": item["amount"],
                    "unit": item["product"]["unit"],
                    "next_due": item["next_due"],
                    "status": item["status"],
                }
                for item in stock
                if item["amount"] > 0 and wanted in item["product"]["name"].casefold()
            ]
        }

    product = vol.Any(cv.positive_int, cv.string)
    hass.services.async_register(
        DOMAIN,
        "purchase",
        purchase,
        vol.Schema(
            {
                vol.Required(ATTR_PRODUCT): product,
                vol.Optional(ATTR_AMOUNT, default=1): vol.Coerce(float),
                vol.Optional("due_date"): cv.date,
                vol.Optional("price"): vol.Coerce(float),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "consume",
        consume,
        vol.Schema(
            {
                vol.Required(ATTR_PRODUCT): product,
                vol.Optional(ATTR_AMOUNT, default=1): vol.Coerce(float),
                vol.Optional("spoiled", default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "execute_chore",
        execute_chore,
        vol.Schema(
            {
                vol.Required("chore"): vol.Any(cv.positive_int, cv.string),
                vol.Optional("person"): cv.entity_id,
                vol.Optional("skipped", default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "add_to_shopping_list",
        add_to_shopping_list,
        vol.Schema({vol.Required("item"): cv.string, vol.Optional(ATTR_AMOUNT, default=1): vol.Coerce(float)}),
    )
    hass.services.async_register(
        DOMAIN,
        "import_receipt",
        import_receipt,
        vol.Schema({vol.Required("path"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "get_stock",
        get_stock,
        vol.Schema({vol.Optional(ATTR_PRODUCT): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
