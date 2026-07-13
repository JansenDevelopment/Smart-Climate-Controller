"""Select platform — native picker for the default override mode."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_DEVICES,
    CONF_ENTITY_ID,
    CONF_ROLE,
    CONF_WRAPPED_CLIMATE,
    ROLE_BOTH,
    ROLE_COOL,
    ROLE_HEAT,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_DEVICE_ROLE,
)
from .entity_base import SmartClimateChildEntity

OVERRIDE_MODES = ["timer", "infinity", "next_node"]
ROLES = [ROLE_HEAT, ROLE_COOL, ROLE_BOTH]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Climate select helpers.

    One role select is created per actuator device. The entry reloads whenever
    the resolved device list changes, so add/remove of a device re-runs this
    setup with the current list.
    """
    from .climate import SmartClimateEntity

    devices = SmartClimateEntity._build_devices(
        entry, entry.data.get(CONF_WRAPPED_CLIMATE)
    )
    entities = [SmartClimateOverrideModeSelect(hass, entry)]
    entities += [
        SmartClimateDeviceRoleSelect(hass, entry, d["entity_id"]) for d in devices
    ]
    async_add_entities(entities)


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


class SmartClimateDeviceRoleSelect(SmartClimateChildEntity, SelectEntity):
    """Pick one actuator device's role (heat / cool / both)."""

    _attr_options = ROLES
    _attr_icon = "mdi:sun-snowflake"

    def __init__(self, hass, entry, device_entity_id: str) -> None:
        super().__init__(hass, entry, f"device_role_{device_entity_id}")
        self._device_entity_id = device_entity_id
        self._attr_name = f"{device_entity_id} role"

    @property
    def current_option(self):
        for device in self._climate_attr(ATTR_DEVICES) or []:
            if device.get(CONF_ENTITY_ID) == self._device_entity_id:
                role = device.get(CONF_ROLE)
                return role if role in ROLES else None
        return None

    async def async_select_option(self, option: str) -> None:
        await self._call_service(
            SERVICE_SET_DEVICE_ROLE, device=self._device_entity_id, role=option
        )
