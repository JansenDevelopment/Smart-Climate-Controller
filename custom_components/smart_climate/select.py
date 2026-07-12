"""Select platform — native picker for the default override mode."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
)
from .entity_base import SmartClimateChildEntity

OVERRIDE_MODES = ["timer", "infinity", "next_node"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Climate select helpers."""
    async_add_entities([SmartClimateOverrideModeSelect(hass, entry)])


class SmartClimateOverrideModeSelect(SmartClimateChildEntity, SelectEntity):
    """Pick the default override mode used when a temperature is changed."""

    _attr_options = OVERRIDE_MODES

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "default_override_mode")
        self._attr_name = "Default Override Mode"
        self._attr_icon = "mdi:gesture-tap-button"

    @property
    def current_option(self):
        mode = self._climate_attr(ATTR_DEFAULT_OVERRIDE_MODE)
        return mode if mode in OVERRIDE_MODES else None

    async def async_select_option(self, option: str) -> None:
        # The backend sets mode and duration together; preserve the current
        # duration when only the mode changes.
        duration = self._climate_attr(ATTR_DEFAULT_OVERRIDE_DURATION, 30)
        await self._call_service(
            SERVICE_SET_DEFAULT_OVERRIDE_MODE, mode=option, duration=int(duration)
        )
