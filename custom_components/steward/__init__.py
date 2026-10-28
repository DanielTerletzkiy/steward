"""The Steward integration: Home Assistant side of the Steward household server."""

from __future__ import annotations

from typing import Any

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_filtered, TrackStates
from homeassistant.helpers.typing import ConfigType

from . import bridge
from .appliances import ApplianceTracker
from .client import StewardAuthError, StewardClient, StewardError
from .const import CONF_APP, CONF_PANEL_URL, DOMAIN, LOGGER, PANEL_ICON, PANEL_PATH, SUPPORTED_API_VERSIONS
from .coordinator import StewardConfigEntry, StewardCoordinator, StewardRuntime
from .services import async_setup_services

PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.IMAGE, Platform.SENSOR, Platform.TODO]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: StewardConfigEntry) -> bool:
    client = StewardClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data.get(CONF_TOKEN, ""))
    try:
        info = await client.get("api/info")
    except StewardAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except StewardError as err:
        raise ConfigEntryNotReady(str(err)) from err
    if info.get("api_version") not in SUPPORTED_API_VERSIONS:
        raise ConfigEntryNotReady(
            f"Steward server speaks API version {info.get('api_version')}; update the integration or the server"
        )

    coordinator = StewardCoordinator(hass, entry, client)
    entry.runtime_data = StewardRuntime(client=client, coordinator=coordinator, info=info)
    await _sync_people(hass, client)
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def on_event(_event: dict[str, Any]) -> None:
        await coordinator.async_request_refresh()

    async def on_request(request: dict[str, Any]) -> Any:
        return await bridge.handle(hass, request)

    entry.runtime_data.listener = entry.async_create_background_task(
        hass, client.listen(on_event, lambda: bridge.hello(hass), on_request), f"{DOMAIN} event stream"
    )
    _track_people(hass, entry, client)
    _register_panel(hass, entry)

    _track_capabilities(hass, entry, client)
    ApplianceTracker(hass, entry).async_start()
    entry.async_on_unload(entry.add_update_listener(_reload_on_options_change))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StewardConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload_on_options_change(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _people_payload(hass: HomeAssistant) -> list[dict[str, Any]]:
    return [
        {
            "id": state.entity_id,
            "name": state.attributes.get("friendly_name") or state.entity_id,
            "user_id": state.attributes.get("user_id"),
            "picture": state.attributes.get("entity_picture"),
            "state": state.state,
        }
        for state in hass.states.async_all("person")
    ]


async def _sync_people(hass: HomeAssistant, client: StewardClient) -> None:
    """Mirror HA's `person` entities into Steward, so chores and wardrobes follow the household."""
    try:
        await client.put("api/people", _people_payload(hass))
    except StewardError as err:
        LOGGER.warning("Could not sync people to Steward: %s", err)


@callback
def _track_people(hass: HomeAssistant, entry: StewardConfigEntry, client: StewardClient) -> None:
    known = {p["id"] for p in _people_payload(hass)}

    async def sync() -> None:
        nonlocal known
        await _sync_people(hass, client)
        current = {p["id"] for p in _people_payload(hass)}
        if current != known:
            # Per-person entities follow the household: someone joined or left.
            known = current
            hass.config_entries.async_schedule_reload(entry.entry_id)

    debouncer = Debouncer(hass, LOGGER, cooldown=2, immediate=False, function=sync)
    entry.async_on_unload(debouncer.async_shutdown)

    @callback
    def on_change(_event: Event) -> None:
        debouncer.async_schedule_call()

    tracker = async_track_state_change_filtered(hass, TrackStates(False, set(), {"person"}), on_change)
    entry.async_on_unload(tracker.async_remove)

    if hass.state is not CoreState.running:
        # person entities may appear only once HA has started.
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _e: debouncer.async_schedule_call())


@callback
def _track_capabilities(hass: HomeAssistant, entry: StewardConfigEntry, client: StewardClient) -> None:
    """Tell the server again when AI Task or weather entities come or go (e.g. after HA has started)."""
    known = bridge.hello(hass)["info"]

    async def resend() -> None:
        nonlocal known
        hello = bridge.hello(hass)
        if hello["info"] != known:
            known = hello["info"]
            await client.send(hello)

    debouncer = Debouncer(hass, LOGGER, cooldown=5, immediate=False, function=resend)
    entry.async_on_unload(debouncer.async_shutdown)

    @callback
    def on_change(event: Event) -> None:
        # Only entities appearing or disappearing matter, not every forecast update.
        if event.data.get("old_state") is None or event.data.get("new_state") is None:
            debouncer.async_schedule_call()

    tracker = async_track_state_change_filtered(hass, TrackStates(False, set(), {"ai_task", "weather"}), on_change)
    entry.async_on_unload(tracker.async_remove)


@callback
def _register_panel(hass: HomeAssistant, entry: StewardConfigEntry) -> None:
    """Sidebar entry for Docker setups (an iframe). With the HA app, its ingress panel is the entry instead."""
    if entry.data.get(CONF_APP):
        return
    url = entry.options.get(CONF_PANEL_URL) or entry.data.get(CONF_PANEL_URL) or entry.data[CONF_URL]
    frontend.async_register_built_in_panel(
        hass,
        "iframe",
        sidebar_title="Steward",
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_PATH,
        config={"url": url},
        require_admin=False,
        update=True,
    )
