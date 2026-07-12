"""Register Smart Climate Lovelace card."""

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.components.lovelace import MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)
CARD_NAME = "smart-climate-card"
HACS_PATH = "www/community/smart-climate-card"
RESOURCE_URL = "/hacsfiles/smart-climate-card/smart-climate-card.js"


class SmartClimateCardRegistration:
    """Register Smart Climate Lovelace card."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    def _get_card_hash(self) -> str:
        """Get hash of card file for cache busting."""
        card_file = Path(__file__).parent / f"{CARD_NAME}.js"
        if not card_file.exists():
            return "0"
        
        with open(card_file, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:10]

    async def async_register(self) -> None:
        """Register card."""
        # Copy card to HACS community directory
        await self._async_copy_card_to_hacs()

        if self.lovelace and self.lovelace.resource_mode == MODE_STORAGE:
            await self._async_wait_for_lovelace_resources()

    async def _async_copy_card_to_hacs(self) -> None:
        """Copy card JS file to HACS community directory."""
        source = Path(__file__).parent / f"{CARD_NAME}.js"
        dest = Path(self.hass.config.path(HACS_PATH)) / f"{CARD_NAME}.js"
        
        # Create directory if it doesn't exist
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            await self.hass.async_add_executor_job(
                shutil.copy2, source, dest
            )
            _LOGGER.debug("Copied %s to %s", CARD_NAME, dest)
        except Exception as e:
            _LOGGER.error("Failed to copy card: %s", e)

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

        # Get card hash for cache busting
        card_hash = await self.hass.async_add_executor_job(self._get_card_hash)
        url = f"{RESOURCE_URL}?hacstag={card_hash}"

        # Check if already registered
        resources = [
            r
            for r in self.lovelace.resources.async_items()
            if CARD_NAME in r["url"]
        ]

        if resources:
            # Update if hash changed
            existing = resources[0]
            if existing["url"].split("?")[0] == RESOURCE_URL:
                _LOGGER.debug("Updating %s resource", CARD_NAME)
                await self.lovelace.resources.async_update_item(
                    existing["id"],
                    {"res_type": "module", "url": url}
                )
            else:
                _LOGGER.debug("Smart Climate card already registered")
            return

        # Register new resource
        _LOGGER.debug("Adding Smart Climate card to Lovelace resources")
        await self.lovelace.resources.async_create_item(
            {"res_type": "module", "url": url}
        )



