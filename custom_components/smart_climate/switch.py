"""Switch platform — native toggle for the interruptible setting."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_INTERRUPTIBLE,
    ATTR_SUPPORT_ENABLED,
    SERVICE_SET_HEAT_SUPPORT,
    SERVICE_SET_INTERRUPTIBLE,
)
from .entity_base import SmartClimateChildEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Climate switch helpers."""
    async_add_entities([
        SmartClimateInterruptibleSwitch(hass, entry),
        SmartClimateHeatSupportSwitch(hass, entry),
    ])


class SmartClimateInterruptibleSwitch(SmartClimateChildEntity, SwitchEntity):
    """Toggle whether a presence change interrupts an active override."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "interruptible")
        self._attr_name = "Override Interruptible"
        self._attr_icon = "mdi:motion-sensor"

    @property
    def is_on(self):
        return bool(self._climate_attr(ATTR_INTERRUPTIBLE, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_INTERRUPTIBLE, interruptible=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_INTERRUPTIBLE, interruptible=False)


class SmartClimateHeatSupportSwitch(SmartClimateChildEntity, SwitchEntity):
    """Allow the support heater (e.g. the CV) to join the primary heater."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "heat_support")
        self._attr_name = "Heat Support"
        self._attr_icon = "mdi:radiator"

    @property
    def is_on(self):
        return bool(self._climate_attr(ATTR_SUPPORT_ENABLED, True))

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_HEAT_SUPPORT, enabled=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_HEAT_SUPPORT, enabled=False)
