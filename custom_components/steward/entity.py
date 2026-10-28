"""Base entity: everything hangs off one Steward service device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StewardConfigEntry, StewardCoordinator, StewardData


class StewardEntity(CoordinatorEntity[StewardCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, entry: StewardConfigEntry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Steward",
            manufacturer="Steward",
            model="Household server",
            sw_version=entry.runtime_data.info.get("version"),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data.get("panel_url") or entry.data.get("url"),
        )

    @property
    def client(self):
        return self._entry.runtime_data.client


def outfit_owners(entry: StewardConfigEntry) -> list[tuple[str, str | None]]:
    """Whose outfit gets entities: each HA person, or the household when there are no people."""
    people = entry.runtime_data.coordinator.data.people
    active = [p for p in people if p.get("active", True)]
    return [(p["id"], p["name"]) for p in active] or [("", None)]


def todays_outfit(data: StewardData, owner: str) -> dict | None:
    outfits = data.summary.get("wardrobe", {}).get("outfits_today", {})
    return outfits.get(owner) or outfits.get("")
