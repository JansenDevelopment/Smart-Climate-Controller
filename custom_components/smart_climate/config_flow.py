from homeassistant import config_entries
import voluptuous as vol

DOMAIN = "smart_climate"


class SmartClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Smart Climate",
                data=user_input,
            )

        schema = vol.Schema({
            vol.Optional("name", default="Smart Climate"): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema)