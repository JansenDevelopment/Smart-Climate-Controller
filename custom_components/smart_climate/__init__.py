from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
from homeassistant.helpers import config_validation as cv
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
)
import voluptuous as vol
import os

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
                        vol.Optional(CONF_AWAY_DELAY_MINUTES, default=5): vol.Coerce(int),
                        vol.Optional(CONF_INTERRUPTIBLE, default=True): cv.boolean,
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

    # Register frontend resources
    frontend_path = os.path.join(
        os.path.dirname(__file__), "smart-climate-card.js"
    )
    hass.http.register_static_path(
        "/local/smart-climate-card.js",
        frontend_path,
        cache_headers=False,
    )

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
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok