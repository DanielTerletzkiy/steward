"""Answers requests from the Steward server: run an AI Task, read a weather forecast, list devices,
command a linked appliance.

The server sends JSON schemas; AI Task wants a probatio (voluptuous-style) schema and images as
local media, so images are written to HA's media folder for the duration of the task.
"""

from __future__ import annotations

import base64
import mimetypes
import secrets
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import appliances
from .const import LOGGER

try:  # HA 2026.x validates with probatio; older versions with voluptuous (same API).
    import probatio as schemas
except ImportError:  # pragma: no cover
    import voluptuous as schemas

MEDIA_FOLDER = "steward_ai"


def hello(hass: HomeAssistant) -> dict[str, Any]:
    """What this HA can do for the server, plus facts it needs (home location for weather fallback)."""
    ai_entities = [state.entity_id for state in hass.states.async_all("ai_task")]
    weather_entities = [state.entity_id for state in hass.states.async_all("weather")]
    capabilities = ["devices", "entities", "appliance_command"]
    capabilities += (["ai_task"] if ai_entities else []) + (["weather"] if weather_entities else [])
    return {
        "type": "ha_hello",
        "capabilities": capabilities,
        "info": {
            "ai_task_entities": ai_entities,
            "weather_entities": weather_entities,
            "latitude": hass.config.latitude,
            "longitude": hass.config.longitude,
            "time_zone": hass.config.time_zone,
            "language": hass.config.language,
        },
    }


async def handle(hass: HomeAssistant, request: dict[str, Any]) -> Any:
    op = request.get("op")
    if op == "ai_task":
        return await _ai_task(hass, request)
    if op == "weather":
        return await _weather(hass, request.get("entity_id"))
    if op == "devices":
        return appliances.devices(hass)
    if op == "entities":
        return appliances.entities(hass, request.get("query"))
    if op == "appliance_command":
        return await appliances.command(hass, request)
    raise HomeAssistantError(f"Unknown request {op}")


def json_schema_to_probatio(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if "enum" in schema:
        return schemas.In(schema["enum"])
    if kind == "object":
        return schemas.Schema(
            {
                schemas.Required(key, description=value.get("description")): json_schema_to_probatio(value)
                for key, value in schema.get("properties", {}).items()
            },
            extra=schemas.PREVENT_EXTRA,
        )
    if kind == "array":
        return [json_schema_to_probatio(schema.get("items", {"type": "string"}))]
    return {"integer": int, "number": float, "boolean": bool}.get(kind, str)


async def _ai_task(hass: HomeAssistant, request: dict[str, Any]) -> Any:
    from homeassistant.components import ai_task

    folder, key = _media_folder(hass)
    written: list[Path] = []
    attachments = []
    try:
        for image in request.get("images") or []:
            suffix = mimetypes.guess_extension(image.get("mime") or "image/jpeg") or ".jpg"
            path = folder / f"{secrets.token_hex(8)}{suffix}"
            await hass.async_add_executor_job(_write, path, base64.b64decode(image["data"]))
            written.append(path)
            attachments.append(
                {
                    "media_content_id": f"media-source://media_source/{key}/{MEDIA_FOLDER}/{path.name}",
                    "media_content_type": image.get("mime") or "image/jpeg",
                }
            )
        result = await ai_task.async_generate_data(
            hass,
            task_name=request.get("task_name") or "Steward",
            entity_id=request.get("entity_id"),
            instructions=request["instructions"],
            structure=json_schema_to_probatio(request["schema"]) if request.get("schema") else None,
            attachments=attachments or None,
        )
    finally:
        for path in written:
            await hass.async_add_executor_job(path.unlink, True)
    return result.data


def _media_folder(hass: HomeAssistant) -> tuple[Path, str]:
    key, root = next(iter(hass.config.media_dirs.items()), ("local", hass.config.path("media")))
    if "local" in hass.config.media_dirs:
        key, root = "local", hass.config.media_dirs["local"]
    return Path(root) / MEDIA_FOLDER, key


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def _weather(hass: HomeAssistant, entity_id: str | None) -> dict[str, Any]:
    if entity_id is None:
        states = hass.states.async_all("weather")
        if not states:
            raise HomeAssistantError("No weather entity")
        entity_id = states[0].entity_id
    state = hass.states.get(entity_id)
    if state is None:
        raise HomeAssistantError(f"{entity_id} not found")
    forecasts: dict[str, list] = {}
    for kind in ("hourly", "daily"):
        try:
            response = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": kind},
                blocking=True,
                return_response=True,
            )
            forecasts[kind] = (response or {}).get(entity_id, {}).get("forecast", [])
        except HomeAssistantError as err:
            LOGGER.debug("%s has no %s forecast: %s", entity_id, kind, err)
            forecasts[kind] = []
    attributes = state.attributes
    return {
        "source": entity_id,
        "temperature_unit": attributes.get("temperature_unit"),
        "current": {
            "condition": state.state,
            "temperature": attributes.get("temperature"),
            "apparent_temperature": attributes.get("apparent_temperature"),
            "wind_speed": attributes.get("wind_speed"),
            "humidity": attributes.get("humidity"),
        },
        **forecasts,
    }
