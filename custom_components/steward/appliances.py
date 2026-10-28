"""Appliances: equipment in Steward linked to HA devices (an LG ThinQ washer, a robot vacuum, ...).

The integration watches the linked entities, reports a compact live status to the server, and
recognizes finished runs from what HA integrations expose:
- vacuum entities going from "cleaning" back to the dock,
- event entities announcing completion (LG ThinQ "washing_is_complete", "drying_is_complete", ...),
- run-state sensors reaching an end state (LG ThinQ current_state "end", Home Connect "finished", ...).
A finished run goes to the server (which completes or schedules chores, asks about the laundry) and
fires `steward_appliance_finished` in HA for your own automations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .client import StewardError
from .const import DOMAIN, LOGGER

EVENT_FINISHED = f"{DOMAIN}_appliance_finished"
FINISH_EVENT_TYPES = {
    "washing_is_complete", "drying_is_complete", "cleaning_is_complete", "cleaning_is_completed",
    "styling_is_complete", "cooking_is_complete", "program_finished", "finished",
}  # fmt: skip
FINISHED_STATES = {"end", "complete", "completed", "done", "finished", "running_end", "cleaning_is_done", "program_finished"}
IDLE_STATES = {"power_off", "off", "initial", "standby", "sleep", "ready", "inactive", STATE_UNKNOWN, STATE_UNAVAILABLE}
VACUUM_DONE = {"docked", "returning", "idle"}
# Sensors that carry an appliance's run state (by translation key, or entity id for helpers and templates).
RUN_STATE_KEYS = ("current_state", "run_state", "operation_state", "program_phase", "machine_state")
VACUUM_COMMANDS = {"start", "pause", "stop", "return_to_base", "locate", "clean_spot"}
KIND_WORDS = {
    "washer": ("washer", "washing", "wasch", "wash_combo", "washcombo"),
    "dryer": ("dryer", "trockner"),
    "dishwasher": ("dishwasher", "dish_washer", "spülmaschine", "geschirrspüler", "spuelmaschine"),
}


def linked_entities(hass: HomeAssistant, equipment: dict[str, Any]) -> list[str]:
    """The device's enabled entities plus any entities linked one by one."""
    entity_ids = list(equipment.get("ha_entities") or [])
    if device_id := equipment.get("ha_device_id"):
        entity_ids += [
            entry.entity_id
            for entry in er.async_entries_for_device(er.async_get(hass), device_id)
            if not entry.disabled_by
        ]
    return list(dict.fromkeys(entity_ids))


def guess_kind(hass: HomeAssistant, device: dr.DeviceEntry, entity_ids: list[str]) -> str:
    if any(e.startswith("vacuum.") for e in entity_ids):
        return "vacuum"
    text = " ".join(filter(None, (device.name, device.model, device.name_by_user, *entity_ids))).lower()
    for kind, words in KIND_WORDS.items():
        if any(word in text for word in words):
            return kind
    return "other"


def devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """HA's devices with their entities, for linking equipment in Steward's UI."""
    devices_reg, entities_reg, areas = dr.async_get(hass), er.async_get(hass), ar.async_get(hass)
    found = []
    for device in devices_reg.devices.values():
        if device.disabled_by or device.entry_type is dr.DeviceEntryType.SERVICE:
            continue
        entries = [e for e in er.async_entries_for_device(entities_reg, device.id) if not e.disabled_by]
        if not entries:
            continue
        entity_ids = [e.entity_id for e in entries]
        area = areas.async_get_area(device.area_id) if device.area_id else None
        found.append(
            {
                "id": device.id,
                "name": device.name_by_user or device.name or device.model or device.id,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "area": area.name if area else None,
                "kind": guess_kind(hass, device, entity_ids),
                "entities": [
                    {
                        "entity_id": e.entity_id,
                        "name": (state.name if (state := hass.states.get(e.entity_id)) else e.original_name) or e.entity_id,
                        "state": state.state if state else None,
                    }
                    for e in entries
                ],
            }
        )
    return sorted(found, key=lambda d: (d["kind"] == "other", d["name"].casefold()))


LINKABLE_DOMAINS = ("vacuum", "sensor", "binary_sensor", "event", "switch", "select", "button", "lawn_mower")


def entities(hass: HomeAssistant, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Entities to link one by one (helpers, templates, or anything without a device)."""
    wanted = (query or "").casefold()
    found = [
        {"entity_id": s.entity_id, "name": s.name, "state": s.state, "domain": s.domain}
        for s in hass.states.async_all(LINKABLE_DOMAINS)
        if not wanted or wanted in f"{s.entity_id} {s.name}".casefold()
    ]
    return sorted(found, key=lambda e: (e["domain"] != "vacuum", e["entity_id"]))[:limit]


def live_status(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, Any]:
    """A compact status: the run state, remaining minutes, battery, and what can be commanded."""
    states = [s for e in entity_ids if (s := hass.states.get(e)) is not None]
    vacuum = next((s for s in states if s.domain == "vacuum"), None)
    run_state = vacuum or _run_state_sensor(hass, states)
    state = run_state.state if run_state else None
    running = bool(state) and state not in IDLE_STATES | FINISHED_STATES | VACUUM_DONE | {"paused", "pause", "error"}
    battery = vacuum.attributes.get("battery_level") if vacuum else None
    if battery is None:
        battery_state = next((s for s in states if s.attributes.get("device_class") == "battery"), None)
        battery = _number(battery_state.state) if battery_state else None
    commands = []
    if vacuum is not None:
        commands = ["start", "pause", "return_to_base", "locate"] if vacuum.state != STATE_UNAVAILABLE else []
    return {
        "state": state,
        "running": running,
        "remaining_minutes": _remaining(hass, states) if running else None,
        "battery": battery,
        "commands": commands,
        "entities": [
            {"entity_id": s.entity_id, "name": s.name, "state": s.state, "unit": s.attributes.get("unit_of_measurement")}
            for s in states
            if s.domain in ("vacuum", "sensor", "binary_sensor", "event")
        ][:12],
    }


def _run_state_sensor(hass: HomeAssistant, states: list[State]) -> State | None:
    registry = er.async_get(hass)
    for state in states:
        entry = registry.async_get(state.entity_id)
        key = (entry.translation_key if entry else None) or state.entity_id.split(".", 1)[1]
        if any(key.endswith(name) for name in RUN_STATE_KEYS):
            return state
    return next((s for s in states if s.domain == "sensor" and s.state in FINISHED_STATES), None)


def _remaining(hass: HomeAssistant, states: list[State]) -> float | None:
    registry = er.async_get(hass)
    for state in states:
        entry = registry.async_get(state.entity_id)
        key = (entry.translation_key or "") if entry else ""
        if "remain" not in key and "remain" not in state.entity_id and "finish" not in key:
            continue
        if state.attributes.get("device_class") == "timestamp":
            if (end := dt_util.parse_datetime(state.state)) is not None:
                return max(round((end - dt_util.utcnow()).total_seconds() / 60), 0)
        value = _number(state.state)
        if value is not None:
            unit = state.attributes.get("unit_of_measurement")
            return round(value * {"h": 60, "s": 1 / 60}.get(unit, 1), 1)
    return None


def _number(value: str | None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def finish_reason(old: State | None, new: State | None) -> str | None:
    """Why this state change means a finished run, or None."""
    if old is None or new is None or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    if new.domain == "vacuum":
        return f"vacuum {old.state} → {new.state}" if old.state == "cleaning" and new.state in VACUUM_DONE else None
    if new.domain == "event":
        event_type = new.attributes.get("event_type")
        return event_type if new.state != old.state and event_type in FINISH_EVENT_TYPES else None
    if new.state in FINISHED_STATES and old.state not in FINISHED_STATES | IDLE_STATES:
        return new.state
    return None


class ApplianceTracker:
    """Follows the linked entities of every piece of equipment; re-links when Steward's data changes."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self._unsub = None
        self._watched: dict[str, int] = {}  # entity id -> equipment id
        self._last_sent: dict[int, dict] = {}
        self._debouncers: dict[int, Debouncer] = {}

    @property
    def coordinator(self):
        return self.entry.runtime_data.coordinator

    @callback
    def async_start(self) -> None:
        self.entry.async_on_unload(self.coordinator.async_add_listener(self._relink))
        self.entry.async_on_unload(self._stop)
        self._relink()

    @callback
    def _stop(self) -> None:
        if self._unsub:
            self._unsub()
        for debouncer in self._debouncers.values():
            debouncer.async_shutdown()

    @callback
    def _relink(self) -> None:
        watched = {}
        for equipment in self.coordinator.data.equipment:
            for entity_id in linked_entities(self.hass, equipment):
                watched[entity_id] = equipment["id"]
        if watched == self._watched:
            return
        self._watched = watched
        if self._unsub:
            self._unsub()
        self._unsub = async_track_state_change_event(self.hass, list(watched), self._changed) if watched else None
        for equipment_id in set(watched.values()):
            self._schedule(equipment_id)

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        equipment_id = self._watched.get(event.data["entity_id"])
        if equipment_id is None:
            return
        if reason := finish_reason(event.data["old_state"], event.data["new_state"]):
            self.hass.async_create_task(self._finished(equipment_id, event.data["entity_id"], reason))
        self._schedule(equipment_id)

    @callback
    def _schedule(self, equipment_id: int) -> None:
        if equipment_id not in self._debouncers:

            async def push(equipment_id: int = equipment_id) -> None:
                await self._push(equipment_id)

            self._debouncers[equipment_id] = Debouncer(self.hass, LOGGER, cooldown=2, immediate=False, function=push)
        self._debouncers[equipment_id].async_schedule_call()

    def _equipment(self, equipment_id: int) -> dict[str, Any] | None:
        return next((e for e in self.coordinator.data.equipment if e["id"] == equipment_id), None)

    async def _push(self, equipment_id: int) -> None:
        equipment = self._equipment(equipment_id)
        if equipment is None:
            return
        status = live_status(self.hass, linked_entities(self.hass, equipment))
        if status == self._last_sent.get(equipment_id):
            return
        try:
            await self.entry.runtime_data.client.put(f"api/equipment/{equipment_id}/live", status)
            self._last_sent[equipment_id] = status
        except StewardError as err:
            LOGGER.debug("Could not report %s status: %s", equipment["name"], err)

    async def _finished(self, equipment_id: int, entity_id: str, reason: str) -> None:
        equipment = self._equipment(equipment_id)
        if equipment is None:
            return
        try:
            result = await self.entry.runtime_data.client.post(
                f"api/equipment/{equipment_id}/finished", {"source": entity_id, "detail": reason}
            )
        except StewardError as err:
            LOGGER.warning("Could not report the finished run of %s: %s", equipment["name"], err)
            return
        if result.get("counted"):
            self.hass.bus.async_fire(
                EVENT_FINISHED,
                {
                    "equipment_id": equipment_id,
                    "name": equipment["name"],
                    "kind": equipment.get("kind"),
                    "reason": reason,
                    "chores_done": result.get("chores_done", []),
                    "chores_due": result.get("chores_due", []),
                    "laundry": result.get("laundry"),
                    "finished_at": datetime.now().astimezone().isoformat(),
                },
            )


async def command(hass: HomeAssistant, request: dict[str, Any]) -> dict[str, Any]:
    """A vacuum action from Steward, only on a vacuum entity that belongs to that equipment's link."""
    name = request.get("command")
    if name not in VACUUM_COMMANDS:
        raise HomeAssistantError(f"Unknown command {name}")
    linked = linked_entities(hass, {"ha_device_id": request.get("device_id"), "ha_entities": request.get("entities")})
    vacuum = next((e for e in linked if e.startswith("vacuum.")), None)
    if vacuum is None:
        raise HomeAssistantError("This equipment has no vacuum entity")
    await hass.services.async_call("vacuum", name, {"entity_id": vacuum}, blocking=True)
    state = hass.states.get(vacuum)
    return {"entity_id": vacuum, "state": state.state if state else None}
