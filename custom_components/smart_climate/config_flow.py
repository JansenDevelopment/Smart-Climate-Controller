from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_NAME
import voluptuous as vol
from .const import DOMAIN


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smart Climate."""
    
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_NAME, "smart_climate"))
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, "Smart Climate"),
                data=user_input,
            )

        schema = vol.Schema({
            vol.Required(CONF_NAME, default="Smart Climate"): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )