"""Config, subentry (devices) and options flows for Smart Climate."""

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_ZONE_HOME,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_ROLE,
    CONF_TEMPERATURE_SOURCE,
    CONF_TEMPERATURE_SENSOR,
    CONF_PRIMARY_DEVICE,
    CONF_HYSTERESIS,
    CONF_INTEGRATION_DRIVEN_AUTO,
    ROLE_HEAT,
    ROLE_COOL,
    ROLE_BOTH,
    SUBENTRY_TYPE_DEVICE,
    TEMP_SOURCE_SENSOR,
    TEMP_SOURCE_PRIMARY,
    TEMP_SOURCE_MEAN,
    DEFAULT_HYSTERESIS,
)

ROLES = [ROLE_HEAT, ROLE_COOL, ROLE_BOTH]


def _device_schema(defaults=None):
    """Schema for one actuator device (entity + role)."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Required(
                CONF_ROLE, default=defaults.get(CONF_ROLE, ROLE_BOTH)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ROLES, translation_key="device_role"
                )
            ),
        }
    )


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smart Climate."""

    VERSION = 1

    def __init__(self):
        super().__init__()
        self._import_name = None

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry):
        """Actuator devices are managed as config subentries."""
        return {SUBENTRY_TYPE_DEVICE: DeviceSubentryFlowHandler}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartClimateOptionsFlow()

    async def async_step_import(self, import_data):
        """Handle import from YAML (only name is required)."""
        if isinstance(import_data, list):
            if import_data:
                self._import_name = import_data[0].get(CONF_NAME, "Smart Climate")
        else:
            self._import_name = import_data.get(CONF_NAME, "Smart Climate")
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Initial setup: name, home zone, and the first actuator device."""
        if user_input is not None:
            await self.async_set_unique_id(user_input.get(CONF_NAME, "smart_climate"))
            self._abort_if_unique_id_configured()

            # Fold the first device into the devices list.
            data = dict(user_input)
            entity_id = data.pop(CONF_ENTITY_ID, None)
            role = data.pop(CONF_ROLE, ROLE_BOTH)
            if entity_id:
                data[CONF_DEVICES] = [{"entity_id": entity_id, "role": role}]

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, "Smart Climate"),
                data=data,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self._import_name or "Smart Climate"): selector.TextSelector(),
                vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_ROLE, default=ROLE_BOTH): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=ROLES, translation_key="device_role")
                ),
                vol.Required(CONF_ZONE_HOME): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Optional(CONF_AWAY_TEMPERATURE, default=14): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=35, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_COOL_AUTO_TEMPERATURE, default=24): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=15, max=35, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_COOL_AWAY_TEMPERATURE, default=28): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=15, max=35, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_INTERRUPTIBLE, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_DEFAULT_OVERRIDE_MODE, default="timer"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["timer", "infinity", "next_node"])
                ),
                vol.Optional(CONF_DEFAULT_OVERRIDE_DURATION, default=30): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=1440, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure the home zone (devices are managed as subentries)."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, **user_input},
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ZONE_HOME,
                    default=entry.data.get(CONF_ZONE_HOME, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
            }
        )

        return self.async_show_form(step_id="reconfigure", data_schema=schema)


class DeviceSubentryFlowHandler(ConfigSubentryFlow):
    """Add or edit a single actuator device as a config subentry."""

    async def async_step_user(self, user_input=None):
        """Add a new device."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_ENTITY_ID],
                data={
                    CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                    CONF_ROLE: user_input[CONF_ROLE],
                },
            )
        return self.async_show_form(step_id="user", data_schema=_device_schema())

    async def async_step_reconfigure(self, user_input=None):
        """Edit an existing device."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_ENTITY_ID],
                data={
                    CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                    CONF_ROLE: user_input[CONF_ROLE],
                },
            )
        return self.async_show_form(
            step_id="reconfigure", data_schema=_device_schema(subentry.data)
        )


class SmartClimateOptionsFlow(OptionsFlow):
    """Instance tunables: room-temperature source, hysteresis, auto strategy."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TEMPERATURE_SOURCE,
                    default=current.get(CONF_TEMPERATURE_SOURCE, TEMP_SOURCE_MEAN),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[TEMP_SOURCE_MEAN, TEMP_SOURCE_PRIMARY, TEMP_SOURCE_SENSOR],
                        translation_key="temperature_source",
                    )
                ),
                vol.Optional(
                    CONF_TEMPERATURE_SENSOR,
                    description={"suggested_value": current.get(CONF_TEMPERATURE_SENSOR)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Optional(
                    CONF_PRIMARY_DEVICE,
                    description={"suggested_value": current.get(CONF_PRIMARY_DEVICE)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Optional(
                    CONF_HYSTERESIS,
                    default=current.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=3.0, step=0.1, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_INTEGRATION_DRIVEN_AUTO,
                    default=current.get(CONF_INTEGRATION_DRIVEN_AUTO, True),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
