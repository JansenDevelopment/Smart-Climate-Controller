from homeassistant.components.climate import ClimateEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

async def async_setup_entry(hass, config_entry, async_add_entities):
    async_add_entities([SmartClimateDummy()])


class SmartClimateDummy(ClimateEntity):
    _attr_name = "Smart Climate Dummy"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = "heat"
    _attr_target_temperature = 21

    @property
    def hvac_modes(self):
        return ["heat", "off"]