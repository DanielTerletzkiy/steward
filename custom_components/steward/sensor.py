"""Sensors: stock warnings, money, chores and tasks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StewardConfigEntry, StewardData
from .entity import StewardEntity


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
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data.coordinator.data
    entities: list[SensorEntity] = [StewardSensor(entry, description) for description in SENSORS]
    entities.extend(PersonChoresSensor(entry, person["id"], person["name"]) for person in data.people)
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
