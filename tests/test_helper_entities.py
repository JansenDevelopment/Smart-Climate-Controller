"""Tests for the number/switch/select helper entities.

They mirror values from the paired climate entity's attributes and write
changes back through the smart_climate.* services.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (
    ATTR_AUTO_TEMPERATURE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_INTERRUPTIBLE,
    DOMAIN,
    SERVICE_SET_AUTO_TEMPERATURE,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_INTERRUPTIBLE,
)

CLIMATE_ID = "climate.smart"


def _hass_with_climate(attrs):
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    climate_state = MagicMock()
    climate_state.attributes = attrs
    hass.states.get = MagicMock(
        side_effect=lambda eid: climate_state if eid == CLIMATE_ID else None
    )
    return hass


def _entry():
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"name": "Living Room"}
    return entry


def _bind(entity, hass):
    """Attach runtime hooks a real Entity would provide, and bind the climate."""
    entity.hass = hass
    entity._climate_entity_id = CLIMATE_ID
    entity.async_write_ha_state = MagicMock()
    entity.async_on_remove = MagicMock()
    return entity


def _last_service_call(hass):
    call = hass.services.async_call.call_args
    return call.args, call.kwargs


# ---------------------------------------------------------------------------
# Number
# ---------------------------------------------------------------------------

async def test_number_reads_value_from_climate_attribute():
    from custom_components.smart_climate.number import NUMBERS, SmartClimateNumber

    desc = next(d for d in NUMBERS if d.key == "auto_temperature")
    hass = _hass_with_climate({ATTR_AUTO_TEMPERATURE: 21.5})
    number = _bind(SmartClimateNumber(hass, _entry(), desc), hass)
    assert number.native_value == 21.5


async def test_number_set_calls_service():
    from custom_components.smart_climate.number import NUMBERS, SmartClimateNumber

    desc = next(d for d in NUMBERS if d.key == "auto_temperature")
    hass = _hass_with_climate({ATTR_AUTO_TEMPERATURE: 21.5})
    number = _bind(SmartClimateNumber(hass, _entry(), desc), hass)

    await number.async_set_native_value(19.0)

    args, _ = _last_service_call(hass)
    assert args[0] == DOMAIN
    assert args[1] == SERVICE_SET_AUTO_TEMPERATURE
    assert args[2] == {"entity_id": CLIMATE_ID, "temperature": 19.0}


async def test_duration_number_couples_current_mode():
    from custom_components.smart_climate.number import NUMBERS, SmartClimateNumber

    desc = next(d for d in NUMBERS if d.key == "default_override_duration")
    hass = _hass_with_climate(
        {ATTR_DEFAULT_OVERRIDE_MODE: "infinity", ATTR_DEFAULT_OVERRIDE_DURATION: 30}
    )
    number = _bind(SmartClimateNumber(hass, _entry(), desc), hass)

    await number.async_set_native_value(45)

    args, _ = _last_service_call(hass)
    assert args[1] == SERVICE_SET_DEFAULT_OVERRIDE_MODE
    assert args[2] == {"entity_id": CLIMATE_ID, "mode": "infinity", "duration": 45}


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

async def test_switch_reflects_interruptible():
    from custom_components.smart_climate.switch import SmartClimateInterruptibleSwitch

    hass = _hass_with_climate({ATTR_INTERRUPTIBLE: True})
    switch = _bind(SmartClimateInterruptibleSwitch(hass, _entry()), hass)
    assert switch.is_on is True


async def test_switch_turn_off_calls_service():
    from custom_components.smart_climate.switch import SmartClimateInterruptibleSwitch

    hass = _hass_with_climate({ATTR_INTERRUPTIBLE: True})
    switch = _bind(SmartClimateInterruptibleSwitch(hass, _entry()), hass)

    await switch.async_turn_off()

    args, _ = _last_service_call(hass)
    assert args[1] == SERVICE_SET_INTERRUPTIBLE
    assert args[2] == {"entity_id": CLIMATE_ID, "interruptible": False}


# ---------------------------------------------------------------------------
# Select
# ---------------------------------------------------------------------------

async def test_select_reflects_current_mode():
    from custom_components.smart_climate.select import SmartClimateOverrideModeSelect

    hass = _hass_with_climate({ATTR_DEFAULT_OVERRIDE_MODE: "next_node"})
    select = _bind(SmartClimateOverrideModeSelect(hass, _entry()), hass)
    assert select.current_option == "next_node"


async def test_select_unknown_mode_is_none():
    from custom_components.smart_climate.select import SmartClimateOverrideModeSelect

    hass = _hass_with_climate({ATTR_DEFAULT_OVERRIDE_MODE: "bogus"})
    select = _bind(SmartClimateOverrideModeSelect(hass, _entry()), hass)
    assert select.current_option is None


async def test_select_option_preserves_duration():
    from custom_components.smart_climate.select import SmartClimateOverrideModeSelect

    hass = _hass_with_climate(
        {ATTR_DEFAULT_OVERRIDE_MODE: "timer", ATTR_DEFAULT_OVERRIDE_DURATION: 60}
    )
    select = _bind(SmartClimateOverrideModeSelect(hass, _entry()), hass)

    await select.async_select_option("infinity")

    args, _ = _last_service_call(hass)
    assert args[1] == SERVICE_SET_DEFAULT_OVERRIDE_MODE
    assert args[2] == {"entity_id": CLIMATE_ID, "mode": "infinity", "duration": 60}


def test_device_info_groups_by_entry():
    from custom_components.smart_climate.switch import SmartClimateInterruptibleSwitch

    hass = _hass_with_climate({})
    switch = SmartClimateInterruptibleSwitch(hass, _entry())
    info = switch.device_info
    assert (DOMAIN, "e1") in info["identifiers"]
