"""Shared base for Smart Climate helper entities (number/switch/select).

These entities are thin controls that mirror a value from the paired Smart
Climate *climate* entity and write changes back through the ``smart_climate.*``
services.  They resolve their climate entity via the entity registry using the
``smart_climate_{entry_id}`` unique-id convention (the same trick the presence
sensor uses) and re-render whenever the climate entity's state changes.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SmartClimateChildEntity:
    """Mixin that binds a helper entity to its paired climate entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str) -> None:
        self.hass = hass
        self._entry = entry
        self._key = key
        self._attr_unique_id = f"smart_climate_{key}_{entry.entry_id}"
        self._climate_entity_id: str | None = None

    @property
    def device_info(self):
        """Group all Smart Climate entities for this entry under one device."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.data.get("name", "Smart Climate"),
            "manufacturer": "Smart Climate",
            "model": "Smart Climate Controller",
        }

    async def async_added_to_hass(self) -> None:
        """Resolve the paired climate entity and subscribe to its changes."""
        registry = er.async_get(self.hass)
        self._climate_entity_id = registry.async_get_entity_id(
            "climate", DOMAIN, f"smart_climate_{self._entry.entry_id}"
        )
        if not self._climate_entity_id:
            _LOGGER.warning(
                "%s: could not find paired climate entity for entry %s",
                type(self).__name__,
                self._entry.entry_id,
            )
            return

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._climate_entity_id], self._on_climate_change
            )
        )
        self.async_write_ha_state()

    async def _on_climate_change(self, event) -> None:
        self.async_write_ha_state()

    def _climate_attr(self, attr: str, default=None):
        """Read an attribute from the paired climate entity's state."""
        if not self._climate_entity_id:
            return default
        state = self.hass.states.get(self._climate_entity_id)
        if not state:
            return default
        return state.attributes.get(attr, default)

    async def _call_service(self, service: str, **data) -> None:
        """Call a smart_climate service targeting the paired climate entity."""
        if not self._climate_entity_id:
            return
        await self.hass.services.async_call(
            DOMAIN,
            service,
            {"entity_id": self._climate_entity_id, **data},
            blocking=True,
        )
