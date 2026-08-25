import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AWAY_DELAY_MINUTES,
    CONF_AWAY_TEMPERATURE,
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_INTERRUPTIBLE,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    DOMAIN,
    PLATFORMS,
)
from .frontend import SmartClimateCardRegistration

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): cv.string,
                        vol.Required(CONF_WRAPPED_CLIMATE): cv.entity_id,
                        vol.Required(CONF_ZONE_HOME): cv.entity_id,
                        vol.Optional(CONF_AWAY_TEMPERATURE, default=14): vol.Coerce(float),
                        vol.Optional(CONF_COOL_AUTO_TEMPERATURE, default=24): vol.Coerce(float),
                        vol.Optional(CONF_COOL_AWAY_TEMPERATURE, default=28): vol.Coerce(float),
                        vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): vol.Coerce(int),
                        vol.Optional(CONF_INTERRUPTIBLE, default=True): cv.boolean,
                        vol.Optional(CONF_DEFAULT_OVERRIDE_MODE, default="timer"): vol.In(["timer", "infinity", "next_node"]),
                        vol.Optional(CONF_DEFAULT_OVERRIDE_DURATION, default=30): vol.Coerce(int),
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Smart Climate integration from YAML."""
    hass.data.setdefault(DOMAIN, {})

    # Register Lovelace card
    card_registration = SmartClimateCardRegistration(hass)
    await card_registration.async_register()

    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=config.get(DOMAIN, []),
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Climate from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entities", {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Reload when the actuator device list changes (a device subentry added,
    # edited, or removed). Routine setpoint persistence writes entry.data but
    # never changes the device list, so it does not trigger a reload.
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry only when its resolved device list changed."""
    from .climate import SmartClimateEntity

    wrapped = entry.data.get(CONF_WRAPPED_CLIMATE)
    new_devices = SmartClimateEntity._build_devices(entry, wrapped)
    for ent in list(hass.data.get(DOMAIN, {}).get("entities", {}).values()):
        if getattr(ent, "entry", None) is entry:
            if ent._devices != new_devices:
                await hass.config_entries.async_reload(entry.entry_id)
            return
    # Coordinator entity not found yet — reload to pick up the change.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok