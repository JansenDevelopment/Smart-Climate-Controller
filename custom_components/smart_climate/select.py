"""Select platform — native picker for the default override mode."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COOLING_MODE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_DEVICE_MODES,
    CONF_WRAPPED_CLIMATE,
    COOLING_MODES,
    DEVICE_MODE_AUTO,
    DEVICE_MODES,
    SERVICE_SET_COOLING_MODE,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_DEVICE_MODE,
)
from .entity_base import SmartClimateChildEntity

OVERRIDE_MODES = ["timer", "infinity", "next_node"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Climate select helpers."""
    from .climate import SmartClimateEntity

    devices = SmartClimateEntity._build_devices(entry, entry.data.get(CONF_WRAPPED_CLIMATE))
    async_add_entities([
        SmartClimateOverrideModeSelect(hass, entry),
        SmartClimateCoolingModeSelect(hass, entry),
        *(SmartClimateDeviceModeSelect(hass, entry, d["entity_id"]) for d in devices),
    ])


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


class SmartClimateCoolingModeSelect(SmartClimateChildEntity, SelectEntity):
    """Policy for automatic cooling: off, auto (warm periods only) or on."""

    _attr_options = COOLING_MODES

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "cooling_mode")
        self._attr_name = "Cooling"
        self._attr_icon = "mdi:snowflake-thermometer"

    @property
    def current_option(self):
        mode = self._climate_attr(ATTR_COOLING_MODE)
        return mode if mode in COOLING_MODES else None

    async def async_select_option(self, option: str) -> None:
        await self._call_service(SERVICE_SET_COOLING_MODE, mode=option)


class SmartClimateDeviceModeSelect(SmartClimateChildEntity, SelectEntity):
    """Per device: auto (coordinator drives it), off, or manual (hands off)."""

    _attr_options = DEVICE_MODES

    def __init__(self, hass, entry, device_entity_id: str) -> None:
        slug = device_entity_id.split(".", 1)[-1]
        super().__init__(hass, entry, f"device_mode_{slug}")
        self._device = device_entity_id
        self._attr_name = f"{slug.replace('_', ' ').title()} mode"
        self._attr_icon = "mdi:hvac"

    @property
    def current_option(self):
        modes = self._climate_attr(ATTR_DEVICE_MODES) or {}
        mode = (modes.get(self._device) or {}).get("mode", DEVICE_MODE_AUTO)
        return mode if mode in DEVICE_MODES else DEVICE_MODE_AUTO

    @property
    def extra_state_attributes(self):
        modes = self._climate_attr(ATTR_DEVICE_MODES) or {}
        return {"device": self._device, "until": (modes.get(self._device) or {}).get("until")}

    async def async_select_option(self, option: str) -> None:
        await self._call_service(SERVICE_SET_DEVICE_MODE, device=self._device, mode=option)
