"""Constants for the Steward integration."""

from __future__ import annotations

import logging

DOMAIN = "steward"
LOGGER = logging.getLogger(__package__)

CONF_PANEL_URL = "panel_url"
PANEL_PATH = "steward"
PANEL_ICON = "mdi:home-heart"

# Server API versions this integration understands.
SUPPORTED_API_VERSIONS = (1,)
