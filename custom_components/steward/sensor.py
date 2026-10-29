"""Sensors: stock warnings, money, chores, tasks, warranties and laundry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import StewardConfigEntry, StewardData
from .entity import StewardEntity, outfit_owners, todays_outfit


@dataclass(frozen=True, kw_only=True)
class StewardSensorDescription(SensorEntityDescription):
    value: Callable[[StewardData], Any]
    attributes: Callable[[StewardData], dict[str, Any]] | None = None


def _spending(data: StewardData) -> dict[str, Any]:
    return data.summary["spending"]


def _names(items: list[dict]) -> dict[str, Any]:
    return {"items": [{"name": i["name"], "due": i.get("due"), "amount": i.get("amount")} for i in items]}


SENSORS: tuple[StewardSensorDescription, ...] = (
    StewardSensorDescription(
        key="expiring_soon",
        translation_key="expiring_soon",
        icon="mdi:clock-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["stock"]["due_soon"]),
        attributes=lambda d: _names(d.summary["stock"]["due_soon"]),
    ),
    StewardSensorDescription(
        key="expired",
        translation_key="expired",
        icon="mdi:food-off-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["stock"]["expired"]),
        attributes=lambda d: _names(d.summary["stock"]["expired"]),
    ),
    StewardSensorDescription(
        key="below_min_stock",
        translation_key="below_min_stock",
        icon="mdi:package-down",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["stock"]["below_min"]),
        attributes=lambda d: _names(d.summary["stock"]["below_min"]),
    ),
    StewardSensorDescription(
        key="stock_value",
        translation_key="stock_value",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value=lambda d: d.summary["stock"]["value"],
    ),
    StewardSensorDescription(
        key="spending_month",
        translation_key="spending_month",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value=lambda d: _spending(d)["month_total"],
        attributes=lambda d: {"trips": _spending(d)["month_trips"]},
    ),
    StewardSensorDescription(
        key="spending_total",
        translation_key="spending_total",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value=lambda d: _spending(d)["total_spent"],
    ),
    StewardSensorDescription(
        key="last_trip",
        translation_key="last_trip",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value=lambda d: (_spending(d)["last_trip"] or {}).get("total"),
        attributes=lambda d: _spending(d)["last_trip"] or {},
    ),
    StewardSensorDescription(
        key="deposit_balance",
        translation_key="deposit_balance",
        icon="mdi:bottle-soda-classic-outline",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value=lambda d: _spending(d)["deposit_balance"],
        # Bottles and cans: bought with deposit, returned, and still to take back (bought - returned).
        attributes=lambda d: {f"bottles_{k}": v for k, v in (_spending(d).get("deposit_bottles") or {}).items()},
    ),
    StewardSensorDescription(
        key="chores_due",
        translation_key="chores_due",
        icon="mdi:broom",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["chores"]["overdue"]) + len(d.summary["chores"]["due_today"]),
        attributes=lambda d: {
            "overdue": [c["name"] for c in d.summary["chores"]["overdue"]],
            "due_today": [c["name"] for c in d.summary["chores"]["due_today"]],
        },
    ),
    StewardSensorDescription(
        key="tasks_due",
        translation_key="tasks_due",
        icon="mdi:clipboard-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["tasks"]["due"]),
        attributes=lambda d: {"tasks": [t["name"] for t in d.summary["tasks"]["due"]], "open": d.summary["tasks"]["open"]},
    ),
    StewardSensorDescription(
        key="warranty_ending",
        translation_key="warranty_ending",
        icon="mdi:shield-alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.summary["equipment"]["warranty_ending"]),
        attributes=lambda d: {"equipment": d.summary["equipment"]["warranty_ending"]},
    ),
    StewardSensorDescription(
        key="laundry",
        translation_key="laundry",
        icon="mdi:basket-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.summary["wardrobe"]["laundry"],
        attributes=lambda d: {
            "pieces": [g["name"] for g in d.garments if g["state"] == "laundry"],
            "needs_wash": [g["name"] for g in d.garments if g.get("needs_wash")],
            "washing": [g["name"] for g in d.garments if g["state"] == "washing"],
            "drying": [g["name"] for g in d.garments if g["state"] == "drying"],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data.coordinator.data
    entities: list[SensorEntity] = [StewardSensor(entry, description) for description in SENSORS]
    entities.extend(PersonChoresSensor(entry, person["id"], person["name"]) for person in data.people)
    entities.extend(OutfitSensor(entry, owner, name) for owner, name in outfit_owners(entry))
    entities.append(MealsTodaySensor(entry))
    async_add_entities(entities)


class StewardSensor(StewardEntity, SensorEntity):
    entity_description: StewardSensorDescription

    def __init__(self, entry: StewardConfigEntry, description: StewardSensorDescription) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator.data)


class PersonChoresSensor(StewardEntity, SensorEntity):
    """How many chores are waiting for one person."""

    _attr_translation_key = "person_chores"
    _attr_icon = "mdi:account-clock"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: StewardConfigEntry, person_id: str, name: str) -> None:
        super().__init__(entry, f"chores_due_{person_id}")
        self._person_id = person_id
        self._attr_translation_placeholders = {"person": name}

    @property
    def native_value(self) -> int:
        return len(self._chores())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"chores": self._chores()}

    def _chores(self) -> list[str]:
        person = self.coordinator.data.summary["people"].get(self._person_id) or {}
        return person.get("chores_due", [])


class OutfitSensor(StewardEntity, SensorEntity):
    """Today's outfit: the pieces as the state, the reason and weather as attributes."""

    _attr_icon = "mdi:tshirt-crew-outline"

    def __init__(self, entry: StewardConfigEntry, owner: str, name: str | None) -> None:
        super().__init__(entry, f"outfit_{owner or 'household'}")
        self._owner = owner
        if name is None:
            self._attr_translation_key = "outfit_household"
        else:
            self._attr_translation_key = "outfit_person"
            self._attr_translation_placeholders = {"person": name}

    def _outfit(self) -> dict | None:
        return todays_outfit(self.coordinator.data, self._owner)

    def _pieces(self, outfit: dict) -> list[str]:
        names = {g["id"]: g["name"] for g in self.coordinator.data.garments}
        return [names[i] for i in outfit["garment_ids"] if i in names]

    @property
    def native_value(self) -> str | None:
        outfit = self._outfit()
        return ", ".join(self._pieces(outfit))[:255] if outfit else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        outfit = self._outfit()
        if outfit is None:
            return None
        return {
            "outfit_id": outfit["id"],
            "pieces": self._pieces(outfit),
            "reason": outfit.get("reason"),
            "worn": outfit.get("worn"),
            "source": outfit.get("source"),
        }


class MealsTodaySensor(StewardEntity, SensorEntity):
    """What's planned to eat today: dinner (or the next meal) as the state, every slot as attributes."""

    _attr_translation_key = "meals_today"
    _attr_icon = "mdi:silverware-fork-knife"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "meals_today")

    def _today(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        return [m for m in self.coordinator.data.meal_plan if m["day"] == today]

    def _title(self, meal: dict) -> str:
        return self.coordinator.data.recipe_name(meal.get("recipe_id")) or meal.get("note") or meal["slot"]

    @property
    def native_value(self) -> str | None:
        meals = self._today()
        main = next((m for m in meals if m["slot"] == "dinner"), None) or next((m for m in meals if not m["done"]), None)
        return self._title(main)[:255] if main else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {m["slot"]: self._title(m) for m in self._today()} | {
            "done": [m["slot"] for m in self._today() if m["done"]]
        }
