"""Keeps a snapshot of the Steward server's data, refreshed whenever the server reports a change."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import StewardClient, StewardError
from .const import DOMAIN, LOGGER

type StewardConfigEntry = ConfigEntry[StewardRuntime]


@dataclass
class StewardData:
    summary: dict[str, Any]
    stock: list[dict[str, Any]]
    shopping_lists: list[dict[str, Any]]
    shopping_items: dict[int, list[dict[str, Any]]]
    chores: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    people: list[dict[str, Any]]
    receipts: list[dict[str, Any]] = field(default_factory=list)
    equipment: list[dict[str, Any]] = field(default_factory=list)
    garments: list[dict[str, Any]] = field(default_factory=list)
    recipes: list[dict[str, Any]] = field(default_factory=list)
    meal_plan: list[dict[str, Any]] = field(default_factory=list)

    def recipe_name(self, recipe_id: int | None) -> str | None:
        return next((r["name"] for r in self.recipes if r["id"] == recipe_id), None)

    def person_name(self, person_id: str | None) -> str | None:
        return next((p["name"] for p in self.people if p["id"] == person_id), None)


@dataclass
class StewardRuntime:
    client: StewardClient
    coordinator: StewardCoordinator
    listener: asyncio.Task | None = None
    info: dict[str, Any] = field(default_factory=dict)


class StewardCoordinator(DataUpdateCoordinator[StewardData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: StewardClient) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            # Changes are pushed over the WebSocket; polling is only a safety net.
            update_interval=timedelta(minutes=10),
            request_refresh_debouncer=Debouncer(hass, LOGGER, cooldown=0.3, immediate=False),
        )
        self.client = client

    async def _async_update_data(self) -> StewardData:
        try:
            lists = await self.client.get("api/shopping-lists")
            start = dt_util.now().date() - timedelta(days=7)
            end = start + timedelta(days=35)
            (summary, stock, chores, tasks, people, receipts, equipment, garments, recipes, meal_plan,
             *items) = await asyncio.gather(  # fmt: skip
                self.client.get("api/summary"),
                self.client.get("api/stock", include_empty="true"),
                self.client.get("api/chores"),
                self.client.get("api/tasks"),
                self.client.get("api/people"),
                self.client.get("api/receipts"),
                self.client.get("api/equipment"),
                self.client.get("api/wardrobe/garments"),
                self.client.get("api/recipes"),
                self.client.get("api/mealplan", start=start.isoformat(), end=end.isoformat()),
                *(self.client.get(f"api/shopping-lists/{lst['id']}/items") for lst in lists),
            )
        except StewardError as err:
            raise UpdateFailed(str(err)) from err
        return StewardData(
            summary=summary,
            stock=stock,
            shopping_lists=lists,
            shopping_items={lst["id"]: lst_items for lst, lst_items in zip(lists, items, strict=True)},
            chores=chores,
            tasks=tasks,
            people=people,
            receipts=receipts,
            equipment=equipment,
            garments=garments,
            recipes=recipes,
            meal_plan=meal_plan,
        )
