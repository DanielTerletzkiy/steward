"""Buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StewardConfigEntry
from .entity import StewardEntity, outfit_owners


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[ButtonEntity] = [AddMissingButton(entry), LaundryDoneButton(entry)]
    entities.extend(SuggestOutfitButton(entry, owner, name) for owner, name in outfit_owners(entry))
    async_add_entities(entities)


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


class LaundryDoneButton(StewardEntity, ButtonEntity):
    """Everything in the laundry is clean again."""

    _attr_translation_key = "laundry_done"
    _attr_icon = "mdi:washing-machine"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "laundry_done")

    async def async_press(self) -> None:
        await self.client.post("api/wardrobe/laundry/done", {})
        await self.coordinator.async_request_refresh()


class SuggestOutfitButton(StewardEntity, ButtonEntity):
    """A fresh outfit suggestion for today (replaces untouched earlier suggestions)."""

    _attr_icon = "mdi:hanger"

    def __init__(self, entry: StewardConfigEntry, owner: str, name: str | None) -> None:
        super().__init__(entry, f"suggest_outfit_{owner or 'household'}")
        self._owner = owner
        if name is None:
            self._attr_translation_key = "suggest_outfit_household"
        else:
            self._attr_translation_key = "suggest_outfit_person"
            self._attr_translation_placeholders = {"person": name}

    async def async_press(self) -> None:
        payload = {"owner": self._owner or None, "count": 1, "lang": self.hass.config.language}
        await self.client.post("api/wardrobe/suggest", payload, timeout_total=180)
        await self.coordinator.async_request_refresh()
