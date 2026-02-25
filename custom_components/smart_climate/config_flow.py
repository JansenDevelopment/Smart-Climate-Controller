from homeassistant.config_entries import ConfigFlow
import voluptuous as vol
from .const import DOMAIN


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smart Climate."""
    
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle user step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", "Smart Climate"),
                data=user_input,
            )

        schema = vol.Schema({
            vol.Required("name", default="Smart Climate"): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )