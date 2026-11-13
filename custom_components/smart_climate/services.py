"""Service registration for Smart Climate Controller.

This module owns all HA service registrations for the Smart Climate
integration.  Call :func:`async_register_services` once (or more — it is
idempotent) from ``async_setup_entry`` in ``climate.py`` to wire up every
service handler.  Service calls are routed to the correct entity via the
``entity_id`` field in the call data, looked up from
``hass.data[DOMAIN]["entities"]``.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_SET_AUTO_TEMPERATURE,
    SERVICE_SET_AWAY_DELAY,
    SERVICE_SET_AWAY_TEMPERATURE,
    SERVICE_SET_BEHAVIOUR,
    SERVICE_SET_COOL_AUTO_TEMPERATURE,
    SERVICE_SET_COOL_AWAY_TEMPERATURE,
    SERVICE_SET_COOLING_MODE,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_DEVICE_MODE,
    SERVICE_SET_HEAT_SUPPORT,
    SERVICE_SET_INTERRUPTIBLE,
    SERVICE_SET_OBSERVE,
    SERVICE_SET_OVERRIDE_INFINITY,
    SERVICE_SET_OVERRIDE_NEXT_NODE,
    SERVICE_SET_OVERRIDE_TIMER,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_SUPPORT_BOOST,
    SERVICE_SET_SUPPORT_PAUSE,
)

_LOGGER = logging.getLogger(__name__)


def _get_entity(hass: HomeAssistant, call: ServiceCall) -> Any | None:
    """Return the SmartClimateEntity targeted by *call*, or ``None``."""
    entity_id = call.data.get("entity_id")
    if isinstance(entity_id, (list, tuple)):
        entity_id = entity_id[0] if entity_id else None
    if not entity_id:
        _LOGGER.warning("Smart Climate service called without entity_id")
        return None
    entity = hass.data.get(DOMAIN, {}).get("entities", {}).get(entity_id)
    if entity is None:
        _LOGGER.warning(
            "Smart Climate entity not found: %s — check entity_id and ensure the entity is loaded",
            entity_id,
        )
    return entity


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all Smart Climate HA services (idempotent).

    Safe to call on every ``async_setup_entry`` invocation; services are
    only registered once.  Each handler looks up the target entity by the
    ``entity_id`` field in the service call data so that multiple
    SmartClimate entities are all handled correctly.

    Args:
        hass: The Home Assistant instance.
    """
    if hass.services.has_service(DOMAIN, SERVICE_SET_OVERRIDE_TIMER):
        return  # Already registered — nothing to do

    async def handle_set_override_timer(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_override_timer(
                call.data.get("minutes", 60),
                call.data.get("temperature", 21),
            )

    async def handle_set_override_infinity(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_override_infinity(
                call.data.get("temperature", 21),
            )

    async def handle_set_override_next_node(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_override_next_node(
                call.data.get("temperature", 21),
            )

    async def handle_clear_override(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_clear_override()

    async def handle_set_interruptible(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_interruptible(call.data.get("interruptible", True))

    async def handle_set_auto_temperature(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_auto_temperature(call.data.get("temperature", 21))

    async def handle_set_away_temperature(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_away_temperature(call.data.get("temperature", 14))

    async def handle_set_cool_auto_temperature(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_cool_auto_temperature(call.data.get("temperature", 24))

    async def handle_set_cool_away_temperature(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_cool_away_temperature(call.data.get("temperature", 28))

    async def handle_set_away_delay(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_away_delay(call.data.get("minutes", 5))

    async def handle_set_default_override_mode(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_default_override_mode(
                call.data.get("mode", "timer"),
                call.data.get("duration", 30),
            )

    async def handle_set_schedule(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_schedule(call.data.get("schedule"))

    async def handle_set_cooling_mode(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_cooling_mode(call.data.get("mode", "auto"))

    async def handle_set_heat_support(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_heat_support(call.data.get("enabled", True))

    async def handle_set_observe(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_observe(call.data.get("enabled", True))

    async def handle_set_behaviour(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_behaviour(
                fan_boost=call.data.get("fan_boost"), hold_primary=call.data.get("hold_primary")
            )

    async def handle_set_device_mode(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_device_mode(
                call.data.get("device"),
                call.data.get("mode", "auto"),
                minutes=call.data.get("minutes"),
                until=call.data.get("until"),
            )

    async def handle_set_support_pause(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_support_pause(
                enabled=call.data.get("enabled", True),
                minutes=call.data.get("minutes"),
                until_morning=call.data.get("until_morning", False),
            )

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
        DOMAIN, SERVICE_SET_COOL_AUTO_TEMPERATURE, handle_set_cool_auto_temperature
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_COOL_AWAY_TEMPERATURE, handle_set_cool_away_temperature
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
    hass.services.async_register(
        DOMAIN, SERVICE_SET_COOLING_MODE, handle_set_cooling_mode
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_HEAT_SUPPORT, handle_set_heat_support
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DEVICE_MODE, handle_set_device_mode
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OBSERVE, handle_set_observe
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_BEHAVIOUR, handle_set_behaviour
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SUPPORT_PAUSE, handle_set_support_pause
    )

    async def handle_set_support_boost(call: ServiceCall) -> None:
        entity = _get_entity(hass, call)
        if entity:
            await entity.async_set_support_boost(
                enabled=call.data.get("enabled", True),
                minutes=call.data.get("minutes"),
            )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SUPPORT_BOOST, handle_set_support_boost
    )
