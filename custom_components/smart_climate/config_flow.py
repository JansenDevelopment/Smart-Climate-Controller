from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
from .const import (
    DOMAIN,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AUTO_TEMPERATURE,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
)


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smart Climate."""

    VERSION = 1

    def __init__(self):
        super().__init__()
        self._import_name = None

    async def async_step_import(self, import_data):
        """Handle import from YAML (only name is required)."""
        if isinstance(import_data, list):
            if import_data:
                self._import_name = import_data[0].get(CONF_NAME, "Smart Climate")
        else:
            self._import_name = import_data.get(CONF_NAME, "Smart Climate")
        return await self.async_step_user()

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
                vol.Required(CONF_NAME, default=self._import_name or "Smart Climate"): str,
                vol.Required(CONF_WRAPPED_CLIMATE): cv.entity_id,
                vol.Required(CONF_ZONE_HOME): cv.entity_id,
                vol.Optional(CONF_AUTO_TEMPERATURE, default=21): vol.Coerce(float),
                vol.Optional(CONF_AWAY_TEMPERATURE, default=14): vol.Coerce(float),
                vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): vol.Coerce(int),
                vol.Optional(CONF_INTERRUPTIBLE, default=True): cv.boolean,
                vol.Optional(CONF_DEFAULT_OVERRIDE_MODE, default="timer"): vol.In(["timer", "infinity"]),
                vol.Optional(CONF_DEFAULT_OVERRIDE_DURATION, default=30): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration — allow changing wrapped_climate and zone_home."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, **user_input},
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WRAPPED_CLIMATE,
                    default=entry.data.get(CONF_WRAPPED_CLIMATE, ""),
                ): cv.entity_id,
                vol.Required(
                    CONF_ZONE_HOME,
                    default=entry.data.get(CONF_ZONE_HOME, ""),
                ): cv.entity_id,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
        )