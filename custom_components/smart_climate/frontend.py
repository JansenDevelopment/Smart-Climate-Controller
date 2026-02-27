"""Register Smart Climate Lovelace cards."""

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.components.lovelace import MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_climate"
CARD_NAME = "smart-climate-card"
CONFIG_CARD_NAME = "smart-climate-config-card"
SCHEDULE_CARD_NAME = "smart-climate-schedule-card"
HACS_PATH = "www/community/smart-climate-card"
RESOURCE_URL = "/hacsfiles/smart-climate-card/smart-climate-card.js"
CONFIG_RESOURCE_URL = "/hacsfiles/smart-climate-card/smart-climate-config-card.js"
SCHEDULE_RESOURCE_URL = "/hacsfiles/smart-climate-card/smart-climate-schedule-card.js"


class SmartClimateCardRegistration:
    """Register Smart Climate Lovelace cards."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    def _get_card_hash(self, card_name: str) -> str:
        """Get hash of card file for cache busting."""
        card_file = Path(__file__).parent / f"{card_name}.js"
        if not card_file.exists():
            return "0"

        with open(card_file, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:10]

    async def async_register(self) -> None:
        """Register cards."""
        # Copy cards to HACS community directory
        await self._async_copy_card_to_hacs(CARD_NAME)
        await self._async_copy_card_to_hacs(CONFIG_CARD_NAME)
        await self._async_copy_card_to_hacs(SCHEDULE_CARD_NAME)

        if self.lovelace and self.lovelace.resource_mode == MODE_STORAGE:
            await self._async_wait_for_lovelace_resources()

    async def _async_copy_card_to_hacs(self, card_name: str) -> None:
        """Copy card JS file to HACS community directory."""
        source = Path(__file__).parent / f"{card_name}.js"
        dest = Path(self.hass.config.path(HACS_PATH)) / f"{card_name}.js"

        # Create directory if it doesn't exist
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            await self.hass.async_add_executor_job(
                shutil.copy2, source, dest
            )
            _LOGGER.debug(f"Copied {card_name}.js to {dest}")
        except Exception as e:
            _LOGGER.error(f"Failed to copy card {card_name}: {e}")

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Wait for lovelace resources to load."""

        async def _check_lovelace_loaded(now):
            if self.lovelace.resources.loaded:
                await self._async_register_module(CARD_NAME, RESOURCE_URL)
                await self._async_register_module(CONFIG_CARD_NAME, CONFIG_RESOURCE_URL)
                await self._async_register_module(SCHEDULE_CARD_NAME, SCHEDULE_RESOURCE_URL)
            else:
                _LOGGER.debug("Waiting for Lovelace resources...")
                async_call_later(self.hass, 5, _check_lovelace_loaded)

        await _check_lovelace_loaded(0)

    async def _async_register_module(self, card_name: str, resource_url: str) -> None:
        """Register a card in Lovelace resources."""
        _LOGGER.debug(f"Registering {card_name} card")

        # Get card hash for cache busting
        card_hash = await self.hass.async_add_executor_job(
            self._get_card_hash, card_name
        )
        url = f"{resource_url}?hacstag={card_hash}"

        # Check if already registered
        resources = [
            r
            for r in self.lovelace.resources.async_items()
            if card_name in r["url"]
        ]

        if resources:
            # Update if hash changed
            existing = resources[0]
            if existing["url"].split("?")[0] == resource_url:
                _LOGGER.debug(f"Updating {card_name} resource")
                await self.lovelace.resources.async_update_item(
                    existing["id"],
                    {"res_type": "module", "url": url}
                )
            else:
                _LOGGER.debug(f"{card_name} already registered")
            return

        # Register new resource
        _LOGGER.debug(f"Adding {card_name} to Lovelace resources")
        await self.lovelace.resources.async_create_item(
            {"res_type": "module", "url": url}
        )