"""Service registration for Smart Climate Controller.

This module owns all HA service registrations for the Smart Climate
integration.  Call :func:`async_register_services` once from
``async_setup_entry`` in ``climate.py`` to wire up every service handler.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SERVICE_SET_OVERRIDE_TIMER,
    SERVICE_SET_OVERRIDE_INFINITY,
    SERVICE_SET_OVERRIDE_NEXT_NODE,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_SET_INTERRUPTIBLE,
    SERVICE_SET_AUTO_TEMPERATURE,
    SERVICE_SET_AWAY_TEMPERATURE,
    SERVICE_SET_AWAY_DELAY,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_SCHEDULE,
)

_LOGGER = logging.getLogger(__name__)


async def async_register_services(hass: HomeAssistant, entity: Any) -> None:
    """Register all Smart Climate HA services for *entity*.

    Creates one handler closure per service and registers each with
    ``hass.services``.  This function is intentionally *async* so it can be
    awaited from ``async_setup_entry`` and extended with async setup steps in
    the future without a signature change.

    Args:
        hass: The Home Assistant instance.
        entity: The :class:`SmartClimateEntity` instance whose methods the
            service handlers will delegate to.
    """

    async def handle_set_override_timer(call):
        await entity.async_set_override_timer(
            call.data.get("minutes", 60),
            call.data.get("temperature", 21),
        )

    async def handle_set_override_infinity(call):
        await entity.async_set_override_infinity(
            call.data.get("temperature", 21),
        )

    async def handle_set_override_next_node(call):
        await entity.async_set_override_next_node(
            call.data.get("temperature", 21),
        )

    async def handle_clear_override(call):
        await entity.async_clear_override()

    async def handle_set_interruptible(call):
        await entity.async_set_interruptible(call.data.get("interruptible", True))

    async def handle_set_auto_temperature(call):
        await entity.async_set_auto_temperature(call.data.get("temperature", 21))

    async def handle_set_away_temperature(call):
        await entity.async_set_away_temperature(call.data.get("temperature", 14))

    async def handle_set_away_delay(call):
        await entity.async_set_away_delay(call.data.get("minutes", 5))

    async def handle_set_default_override_mode(call):
        await entity.async_set_default_override_mode(
            call.data.get("mode", "timer"),
            call.data.get("duration", 30),
        )

    async def handle_set_schedule(call):
        await entity.async_set_schedule(call.data.get("schedule"))

    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE_TIMER, handle_set_override_timer
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE_INFINITY, handle_set_override_infinity
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE_NEXT_NODE, handle_set_override_next_node
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_OVERRIDE, handle_clear_override)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_INTERRUPTIBLE, handle_set_interruptible
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AUTO_TEMPERATURE, handle_set_auto_temperature
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AWAY_TEMPERATURE, handle_set_away_temperature
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AWAY_DELAY, handle_set_away_delay
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DEFAULT_OVERRIDE_MODE, handle_set_default_override_mode
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule
    )
