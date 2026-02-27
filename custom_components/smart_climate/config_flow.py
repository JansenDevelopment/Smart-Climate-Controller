from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
import voluptuous as vol
from .const import (
    DOMAIN,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
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
                vol.Required(CONF_NAME, default=self._import_name or "Smart Climate"): selector.TextSelector(),
                vol.Required(CONF_WRAPPED_CLIMATE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_ZONE_HOME): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Optional(CONF_AWAY_TEMPERATURE, default=14): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=35, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_INTERRUPTIBLE, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_DEFAULT_OVERRIDE_MODE, default="timer"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["timer", "infinity"])
                ),
                vol.Optional(CONF_DEFAULT_OVERRIDE_DURATION, default=30): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=1440, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
                ),
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
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(
                    CONF_ZONE_HOME,
                    default=entry.data.get(CONF_ZONE_HOME, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
        )