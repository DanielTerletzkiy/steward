"""Settings: AI providers per job, and the weather source."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..api import Bridge, Hub, Session, require_auth
from ..services import ai, weather
from ..services import settings as settings_store

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_auth)])


class WeatherSettings(BaseModel):
    entity_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.get("/ai")
async def get_ai(session: Session, bridge: Bridge) -> dict[str, Any]:
    return ai.public_config(await ai.load_config(session), bridge)


@router.put("/ai")
async def put_ai(session: Session, hub: Hub, bridge: Bridge, body: dict[str, Any]) -> dict[str, Any]:
    return await ai.save_config(session, hub, bridge, body)


@router.post("/ai/test/{provider_id}")
async def test_ai(session: Session, bridge: Bridge, provider_id: str) -> dict[str, Any]:
    return await ai.test_provider(session, bridge, provider_id)


@router.get("/weather")
async def get_weather_settings(session: Session, bridge: Bridge) -> dict[str, Any]:
    return {
        **(await weather.load_config(session)),
        "home_assistant": {
            "connected": bridge.connected,
            "weather": bridge.can("weather"),
            "entities": bridge.info.get("weather_entities", []),
        },
    }


@router.put("/weather")
async def put_weather_settings(session: Session, hub: Hub, body: WeatherSettings) -> dict[str, Any]:
    return await settings_store.put(session, hub, weather.SETTINGS_KEY, body.model_dump(exclude_none=True))


@router.get("/weather/forecast")
async def forecast(session: Session, bridge: Bridge, day: date | None = None) -> dict[str, Any]:
    return await weather.for_day(session, bridge, day)
