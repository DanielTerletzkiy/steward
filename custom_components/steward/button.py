"""Buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StewardConfigEntry
from .entity import StewardEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([AddMissingButton(entry)])


class AddMissingButton(StewardEntity, ButtonEntity):
    """Put every product below its minimum stock on the shopping list."""

    _attr_translation_key = "add_missing"
    _attr_icon = "mdi:cart-plus"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "add_missing")

    async def async_press(self) -> None:
        list_id = self.coordinator.data.shopping_lists[0]["id"]
        await self.client.post(f"api/shopping-lists/{list_id}/add-missing")
        await self.coordinator.async_request_refresh()
