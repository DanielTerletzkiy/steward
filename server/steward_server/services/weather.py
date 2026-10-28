"""The day's weather for outfit suggestions: HA's weather entity first, Open-Meteo as a fallback."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..ha_bridge import HABridge
from ..timeutil import LOCAL_TZ, today
from . import ServiceError
from . import settings as settings_store

LOG = logging.getLogger("steward.weather")
SETTINGS_KEY = "weather"
DAY_HOURS = (7, 22)  # the part of the day clothes have to work for


class WeatherUnavailable(ServiceError):
    status = 503


async def load_config(session: AsyncSession) -> dict[str, Any]:
    return await settings_store.get(session, SETTINGS_KEY, {}) or {}


async def for_day(session: AsyncSession, bridge: HABridge, day: date | None = None) -> dict[str, Any]:
    """A compact summary: temperatures (actual and feels-like), rain, wind and conditions for the day."""
    day = day or today()
    config = await load_config(session)
    if bridge.can("weather"):
        try:
            raw = await bridge.request("weather", timeout=30, entity_id=config.get("entity_id"))
            return summarize(raw, day)
        except ServiceError as err:
            LOG.warning("Weather from Home Assistant failed: %s", err)
    latitude = config.get("latitude", bridge.info.get("latitude"))
    longitude = config.get("longitude", bridge.info.get("longitude"))
    if latitude is not None and longitude is not None:
        return summarize(await _open_meteo(latitude, longitude), day)
    raise WeatherUnavailable("No weather source: connect Home Assistant or set a location under Settings")


def summarize(raw: dict[str, Any], day: date) -> dict[str, Any]:
    """Reduce hourly (or daily) forecasts in °C to what clothing decisions need."""
    to_c = _converter(raw.get("temperature_unit"))
    start = datetime.combine(day, time(DAY_HOURS[0]), LOCAL_TZ)
    end = datetime.combine(day, time(DAY_HOURS[1]), LOCAL_TZ)
    hours = [h for h in raw.get("hourly") or [] if start <= _local(h["datetime"]) <= end]
    if hours:
        temps = [to_c(h["temperature"]) for h in hours if h.get("temperature") is not None]
        feels = [to_c(h.get("apparent_temperature", h.get("temperature"))) for h in hours if h.get("temperature") is not None]
        rain = [h.get("precipitation_probability") or 0 for h in hours]
        wind = [h.get("wind_speed") or 0 for h in hours]
        conditions = [h.get("condition") for h in hours if h.get("condition")]
        rain_from = next((_local(h["datetime"]).strftime("%H:%M") for h in hours if (h.get("precipitation_probability") or 0) >= 40), None)
    else:
        daily = next((d for d in raw.get("daily") or [] if _local(d["datetime"]).date() == day), None)
        if daily is None:
            current = raw.get("current") or {}
            if day != today() or current.get("temperature") is None:
                raise WeatherUnavailable(f"No forecast for {day.isoformat()}")
            daily = {**current, "templow": current["temperature"]}
        high, low = to_c(daily["temperature"]), to_c(daily.get("templow", daily["temperature"]))
        temps, feels = [low, high], [low - _wind_chill(daily.get("wind_speed")), high]
        rain, wind = [daily.get("precipitation_probability") or 0], [daily.get("wind_speed") or 0]
        conditions = [daily["condition"]] if daily.get("condition") else []
        rain_from = None
    if not temps:
        raise WeatherUnavailable("The forecast has no temperatures")
    return {
        "day": day.isoformat(),
        "source": raw.get("source", "home_assistant"),
        "temp_min": round(min(temps), 1),
        "temp_max": round(max(temps), 1),
        "feels_min": round(min(feels), 1),
        "feels_max": round(max(feels), 1),
        "rain_probability": round(max(rain)),
        "rain_from": rain_from,
        "wind_max": round(max(wind), 1),
        "conditions": sorted(set(conditions), key=conditions.index),
    }


def _converter(unit: str | None):
    if unit and "F" in unit:
        return lambda v: (float(v) - 32) * 5 / 9
    return float


def _wind_chill(wind_speed: float | None) -> float:
    return min((wind_speed or 0) / 10, 4)


def _local(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


async def _open_meteo(latitude: float, longitude: float) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m,weather_code",
        "forecast_days": 3,
        "timezone": str(LOCAL_TZ),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
    except httpx.HTTPError as err:
        raise WeatherUnavailable(f"Open-Meteo could not be reached: {err}") from err
    data = response.json()["hourly"]
    hourly = [
        {
            "datetime": stamp,
            "temperature": data["temperature_2m"][i],
            "apparent_temperature": data["apparent_temperature"][i],
            "precipitation_probability": data["precipitation_probability"][i],
            "wind_speed": data["wind_speed_10m"][i],
            "condition": _wmo_condition(data["weather_code"][i]),
        }
        for i, stamp in enumerate(data["time"])
    ]
    return {"source": "open_meteo", "temperature_unit": "°C", "hourly": hourly}


def _wmo_condition(code: int | None) -> str | None:
    """Open-Meteo's WMO weather codes, mapped to HA's condition names."""
    if code is None:
        return None
    for limit, name in ((0, "sunny"), (2, "partlycloudy"), (3, "cloudy"), (48, "fog"), (67, "rainy"),
                        (77, "snowy"), (82, "pouring"), (86, "snowy"), (99, "lightning-rainy")):  # fmt: skip
        if code <= limit:
            return name
    return None
