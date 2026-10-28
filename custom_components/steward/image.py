"""Today's outfit as a picture: a collage of the pieces, per person."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .client import StewardError
from .coordinator import StewardConfigEntry
from .entity import StewardEntity, outfit_owners, todays_outfit


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(OutfitImage(hass, entry, owner, name) for owner, name in outfit_owners(entry))


class OutfitImage(StewardEntity, ImageEntity):
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, entry: StewardConfigEntry, owner: str, name: str | None) -> None:
        StewardEntity.__init__(self, entry, f"outfit_image_{owner or 'household'}")
        ImageEntity.__init__(self, hass)
        self._owner = owner
        self._outfit_id: int | None = None
        if name is None:
            self._attr_translation_key = "outfit_household"
        else:
            self._attr_translation_key = "outfit_person"
            self._attr_translation_placeholders = {"person": name}
        self._sync()

    @callback
    def _sync(self) -> None:
        outfit = todays_outfit(self.coordinator.data, self._owner)
        outfit_id = outfit["id"] if outfit else None
        if outfit_id != self._outfit_id:
            self._outfit_id = outfit_id
            self._attr_image_last_updated = dt_util.utcnow()
            self._cached_image = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return super().available and self._outfit_id is not None

    async def async_image(self) -> bytes | None:
        if self._outfit_id is None:
            return None
        try:
            return await self.client.get_bytes(f"api/wardrobe/outfits/{self._outfit_id}/image")
        except StewardError:
            return None

    @property
    def image_last_updated(self) -> datetime | None:
        return self._attr_image_last_updated
