"""Config flow: point Home Assistant at a Steward server."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .client import StewardAuthError, StewardClient, StewardError
from .const import CONF_APP, CONF_PANEL_URL, DOMAIN, SUPPORTED_API_VERSIONS


async def _validate(hass, url: str, token: str) -> dict[str, Any]:
    info = await StewardClient(async_get_clientsession(hass), url, token).get("api/info")
    if info.get("api_version") not in SUPPORTED_API_VERSIONS:
        raise StewardError("unsupported api version")
    return info


class StewardConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _discovered: dict[str, Any]

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The Steward app announced itself through the Supervisor."""
        config = discovery_info.config
        data = {CONF_URL: f"http://{config['host']}:{config['port']}", CONF_TOKEN: config["token"], CONF_APP: True}
        await self.async_set_unique_id(DOMAIN)
        # A reinstalled or moved app gets a new address or token: update the entry instead of asking again.
        self._abort_if_unique_id_configured(updates=data)
        self._discovered = data
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            try:
                await _validate(self.hass, self._discovered[CONF_URL], self._discovered[CONF_TOKEN])
            except StewardError:
                return self.async_abort(reason="cannot_connect")
            return self.async_create_entry(title="Steward", data=self._discovered)
        self._set_confirm_only()
        return self.async_show_form(step_id="hassio_confirm")

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                await _validate(self.hass, url, user_input.get(CONF_TOKEN, ""))
            except StewardAuthError:
                errors["base"] = "invalid_auth"
            except StewardError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Steward", data={**user_input, CONF_URL: url})
        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default="http://localhost:8095"): str,
                vol.Optional(CONF_TOKEN, default=""): str,
                vol.Optional(CONF_PANEL_URL, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StewardOptionsFlow()


class StewardOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_PANEL_URL) or self.config_entry.data.get(CONF_PANEL_URL, "")
        schema = vol.Schema({vol.Optional(CONF_PANEL_URL, default=current): str})
        return self.async_show_form(step_id="init", data_schema=schema)
