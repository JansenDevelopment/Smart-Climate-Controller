"""Sensor platform for Smart Climate — exposes presence state for history logging."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import ATTR_PRESENCE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate sensor platform."""
    async_add_entities([SmartClimatePresenceSensor(hass, entry)])


class SmartClimatePresenceSensor(SensorEntity):
    """Sensor that exposes the Smart Climate presence state for history logging.

    The presence attribute on the climate entity is not recorded by HA
    (only state changes are logged).  By surfacing presence as the *state*
    of this dedicated sensor, HA writes a history entry on every change so
    the schedule card can draw the home/leaving/away bar.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"smart_climate_presence_{entry.entry_id}"
        self._attr_name = f"{entry.data.get('name', 'Smart Climate')} Presence"
        self._attr_icon = "mdi:account-home"
        self._native_value: str | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the paired climate entity's state changes."""
        registry = er.async_get(self.hass)
        climate_entity_id = registry.async_get_entity_id(
            "climate", DOMAIN, f"smart_climate_{self._entry.entry_id}"
        )
        if not climate_entity_id:
            _LOGGER.warning(
                "SmartClimatePresenceSensor: could not find climate entity for entry %s",
                self._entry.entry_id,
            )
            return

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [climate_entity_id], self._on_climate_change
            )
        )

        # Set initial value from current climate state
        climate_state = self.hass.states.get(climate_entity_id)
        if climate_state:
            self._native_value = climate_state.attributes.get(ATTR_PRESENCE)
            self.async_write_ha_state()

    async def _on_climate_change(self, event) -> None:
        """Handle climate entity state changes and mirror the presence attribute."""
        new_state = event.data.get("new_state")
        if not new_state:
            return
        presence = new_state.attributes.get(ATTR_PRESENCE)
        if presence is not None and presence != self._native_value:
            self._native_value = presence
            self.async_write_ha_state()

    @property
    def device_info(self):
        """Group all Smart Climate entities for this entry under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.data.get("name", "Smart Climate"),
            "manufacturer": "Smart Climate",
            "model": "Smart Climate Controller",
        }

    @property
    def native_value(self) -> str | None:
        return self._native_value
