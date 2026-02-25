from homeassistant.components.climate import ClimateEntity, HVACMode
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate platform."""
    name = entry.data.get(CONF_NAME, "Smart Climate")
    async_add_entities([SmartClimateEntity(entry, name)], True)


class SmartClimateEntity(ClimateEntity):
    """Smart Climate controller entity."""

    def __init__(self, entry: ConfigEntry, name: str):
        self.entry = entry
        self._attr_name = name
        self._attr_unique_id = f"smart_climate_{entry.entry_id}"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 21
        self._attr_min_temp = 5
        self._attr_max_temp = 25
        self._attr_should_poll = False

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT, HVACMode.OFF]