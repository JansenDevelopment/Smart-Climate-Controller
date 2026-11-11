"""Register Smart Climate Lovelace card."""

import hashlib
import logging
import re
from pathlib import Path

from homeassistant.components.lovelace import MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)
HACS_PATH = "www/community/smart-climate-card"
RESOURCE_DIR = "/hacsfiles/smart-climate-card"
# The cards that are registered as Lovelace resources ...
CARD_FILES = (
    "smart-climate-card",
    "smart-climate-schedule-card",
    "smart-climate-config-card",
)
# ... and every module that has to be copied next to them (the cards import
# the shared helpers and the editor base class relatively).
HELPER_FILES = ("smart-climate-base-editor", "smart-climate-shared")
MODULE_FILES = (*CARD_FILES, *HELPER_FILES)

_HELPERS = "|".join(HELPER_FILES)
_IMPORT_RE = re.compile(rf'(from\s+"\./(?:{_HELPERS})\.js)"')


def _modules_hash(directory: Path) -> str:
    """Hash of all card modules, used for cache busting."""
    digest = hashlib.md5()
    for name in MODULE_FILES:
        module = directory / f"{name}.js"
        if module.exists():
            digest.update(module.read_bytes())
    return digest.hexdigest()[:10]


def _with_versioned_imports(source: str, tag: str) -> str:
    """Give the relative imports of the helper modules a ``?hacstag=`` query.

    The Lovelace resource URL is cache-busted, but the modules a card imports
    are not, so after an update the browser could mix a new card with a stale
    shared module.
    """
    return _IMPORT_RE.sub(lambda m: f'{m.group(1)}?hacstag={tag}"', source)


def _copy_modules(source_dir: Path, dest_dir: Path) -> None:
    """Copy all card modules to ``dest_dir`` (blocking; run in the executor)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    tag = _modules_hash(source_dir)
    for name in MODULE_FILES:
        source = source_dir / f"{name}.js"
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8")
        (dest_dir / f"{name}.js").write_text(
            _with_versioned_imports(text, tag), encoding="utf-8"
        )


class SmartClimateCardRegistration:
    """Register Smart Climate Lovelace card."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    def _get_card_hash(self) -> str:
        """Get hash of the card files for cache busting."""
        return _modules_hash(Path(__file__).parent)

    async def async_register(self) -> None:
        """Register card."""
        # Copy card to HACS community directory
        await self._async_copy_card_to_hacs()

        if self.lovelace and self.lovelace.resource_mode == MODE_STORAGE:
            await self._async_wait_for_lovelace_resources()

    async def _async_copy_card_to_hacs(self) -> None:
        """Copy the card JS files to the HACS community directory."""
        source_dir = Path(__file__).parent
        dest_dir = Path(self.hass.config.path(HACS_PATH))

        try:
            await self.hass.async_add_executor_job(_copy_modules, source_dir, dest_dir)
            _LOGGER.debug("Copied Smart Climate cards to %s", dest_dir)
        except OSError as e:
            _LOGGER.error("Failed to copy cards: %s", e)

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
        """Register the cards in Lovelace resources."""
        _LOGGER.debug("Registering Smart Climate cards")

        # Get card hash for cache busting
        card_hash = await self.hass.async_add_executor_job(self._get_card_hash)

        for name in CARD_FILES:
            base_url = f"{RESOURCE_DIR}/{name}.js"
            url = f"{base_url}?hacstag={card_hash}"

            # An existing resource for this card (also one registered by hand
            # under another path) is matched on the file name.
            resources = [
                r
                for r in self.lovelace.resources.async_items()
                if r["url"].split("?")[0].rsplit("/", 1)[-1] == f"{name}.js"
            ]

            if resources:
                existing = resources[0]
                if existing["url"].split("?")[0] == base_url:
                    # Update if the hash changed
                    if existing["url"] != url:
                        _LOGGER.debug("Updating %s resource", name)
                        await self.lovelace.resources.async_update_item(
                            existing["id"], {"res_type": "module", "url": url}
                        )
                else:
                    _LOGGER.debug("%s already registered", name)
                continue

            # Register new resource
            _LOGGER.debug("Adding %s to Lovelace resources", name)
            await self.lovelace.resources.async_create_item(
                {"res_type": "module", "url": url}
            )
