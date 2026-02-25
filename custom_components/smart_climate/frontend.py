"""Register Smart Climate Lovelace card."""

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_climate"
CARD_NAME = "smart-climate-card"
CARD_PATH = "/smart_climate"


class SmartClimateCardRegistration:
    """Register Smart Climate Lovelace card."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    async def async_register(self) -> None:
        """Register card."""
        await self._async_register_path()

        if self.lovelace and self.lovelace.resource_mode == MODE_STORAGE:
            await self._async_wait_for_lovelace_resources()

    async def _async_register_path(self) -> None:
        """Register resource path."""
        try:
            await self.hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        CARD_PATH,
                        Path(__file__).parent,
                        False,
                    )
                ]
            )
            _LOGGER.debug("Registered Smart Climate card path")
        except RuntimeError:
            _LOGGER.debug("Smart Climate card path already registered")

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Wait for lovelace resources to load."""

        async def _check_lovelace_loaded(now):
            if self.lovelace.resources.loaded:
                await self._async_register_module()
            else:
                _LOGGER.debug("Waiting for Lovelace resources...")
                async_call_later(self.hass, 5, _check_lovelace_loaded)

        await _check_lovelace_loaded(0)

    async def _async_register_module(self) -> None:
        """Register card in Lovelace resources."""
        _LOGGER.debug("Registering Smart Climate card")

        url = f"{CARD_PATH}/{CARD_NAME}.js"

        # Check if already registered
        resources = [
            r
            for r in self.lovelace.resources.async_items()
            if CARD_PATH in r["url"]
        ]

        if resources:
            _LOGGER.debug("Smart Climate card already registered")
            return

        # Register new resource
        _LOGGER.debug("Adding Smart Climate card to Lovelace resources")
        await self.lovelace.resources.async_create_item(
            {"res_type": "module", "url": url}
        )
