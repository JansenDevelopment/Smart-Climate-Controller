from homeassistant.components.climate import ClimateEntity
from homeassistant.const import UnitOfTemperature


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SmartClimateDummy(entry.data.get("name", "Smart Climate"))])


class SmartClimateDummy(ClimateEntity):
    def __init__(self, name):
        self._attr_name = name
        self._attr_unique_id = f"smart_climate_{name.lower().replace(' ', '_')}"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_mode = "heat"
        self._attr_target_temperature = 21
        self._attr_min_temp = 5
        self._attr_max_temp = 25

    @property
    def hvac_modes(self):
        return ["heat", "off"]