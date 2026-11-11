"""Switch platform — native toggle for the interruptible setting."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FAN_BOOST,
    ATTR_HOLD_PRIMARY,
    ATTR_INTERRUPTIBLE,
    ATTR_OBSERVE,
    ATTR_SUPPORT_ENABLED,
    ATTR_SUPPORT_PAUSED_UNTIL,
    SERVICE_SET_BEHAVIOUR,
    SERVICE_SET_HEAT_SUPPORT,
    SERVICE_SET_INTERRUPTIBLE,
    SERVICE_SET_OBSERVE,
    SERVICE_SET_SUPPORT_PAUSE,
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
        SmartClimateSupportPauseSwitch(hass, entry),
        SmartClimateObserveSwitch(hass, entry),
        SmartClimateFanBoostSwitch(hass, entry),
        SmartClimateHoldSwitch(hass, entry),
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


class SmartClimateSupportPauseSwitch(SmartClimateChildEntity, SwitchEntity):
    """Pause the support heater until the next morning (default 10:00)."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "support_pause")
        self._attr_name = "Skip Support Until Morning"
        self._attr_icon = "mdi:radiator-off"

    @property
    def is_on(self):
        return self._climate_attr(ATTR_SUPPORT_PAUSED_UNTIL) is not None

    @property
    def extra_state_attributes(self):
        return {"until": self._climate_attr(ATTR_SUPPORT_PAUSED_UNTIL) or None}

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_SUPPORT_PAUSE, enabled=True, until_morning=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_SUPPORT_PAUSE, enabled=False)


class SmartClimateObserveSwitch(SmartClimateChildEntity, SwitchEntity):
    """Observe ("proefdraaien"): decide and log, but drive nothing."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "observe")
        self._attr_name = "Observe Only"
        self._attr_icon = "mdi:eye-outline"

    @property
    def is_on(self):
        return bool(self._climate_attr(ATTR_OBSERVE, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_OBSERVE, enabled=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_OBSERVE, enabled=False)


class SmartClimateFanBoostSwitch(SmartClimateChildEntity, SwitchEntity):
    """Fan on high while the room is far below the target, then medium, then auto."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "fan_boost")
        self._attr_name = "Fan Boost"
        self._attr_icon = "mdi:fan-chevron-up"

    @property
    def is_on(self):
        return bool(self._climate_attr(ATTR_FAN_BOOST, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_BEHAVIOUR, fan_boost=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_BEHAVIOUR, fan_boost=False)


class SmartClimateHoldSwitch(SmartClimateChildEntity, SwitchEntity):
    """Keep the primary heater heating at the target instead of switching it off."""

    def __init__(self, hass, entry) -> None:
        super().__init__(hass, entry, "hold_primary")
        self._attr_name = "Hold Primary Heater"
        self._attr_icon = "mdi:thermostat-auto"

    @property
    def is_on(self):
        return bool(self._climate_attr(ATTR_HOLD_PRIMARY, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_BEHAVIOUR, hold_primary=True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_service(SERVICE_SET_BEHAVIOUR, hold_primary=False)
