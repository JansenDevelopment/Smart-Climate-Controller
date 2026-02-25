from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
from .const import (
    DOMAIN,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
)


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smart Climate."""

    VERSION = 1

    async def async_step_import(self, import_data):
        """Handle import from YAML."""
        for config in import_data:
            name = config.get(CONF_NAME, "Smart Climate")
            await self.async_set_unique_id(name)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=name,
                data=config,
            )
        return self.async_abort(reason="invalid_yaml")

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_NAME, "smart_climate"))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, "Smart Climate"),
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Smart Climate"): str,
                vol.Required(CONF_WRAPPED_CLIMATE): cv.entity_id,
                vol.Required(CONF_ZONE_HOME): cv.entity_id,
                vol.Optional(CONF_AWAY_TEMPERATURE, default=14): vol.Coerce(float),
                vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): vol.Coerce(int),
                vol.Optional(CONF_INTERRUPTIBLE, default=True): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )