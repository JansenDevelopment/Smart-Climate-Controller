"""Tests for cooling support and HVAC-mode-aware setpoint resolution.

The wrapper reads the wrapped device's current HVAC mode and:
  - heat / auto  → heating setpoints (away/auto/schedule),
  - cool         → cooling setpoints (cool_away / cool_auto),
  - off / fan_only / dry → writes no setpoint at all.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    MODE_AUTO,
)

WRAPPED = "climate.wrapped"


def _make_entity(wrapped_mode="heat", wrapped_attrs=None, entry_data=None):
    """Build an entity whose wrapped device reports *wrapped_mode*.

    ``hass.states.get`` returns a wrapped-climate state for the wrapped id and
    ``None`` for anything else (e.g. the zone), so presence stays put.
    """
    from custom_components.smart_climate.climate import SmartClimateEntity

    wrapped_state = MagicMock()
    wrapped_state.state = wrapped_mode
    wrapped_state.attributes = wrapped_attrs or {}

    hass = MagicMock()
    hass.services.async_call = AsyncMock()

    def _states_get(entity_id):
        return wrapped_state if entity_id == WRAPPED else None

    hass.states.get = MagicMock(side_effect=_states_get)

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = dict(entry_data or {})

    def _update_entry(target, data=None, **kwargs):
        if data is not None:
            target.data = dict(data)
        return True

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update_entry)

    entity = SmartClimateEntity(
        hass=hass,
        entry=entry,
        name="Test Climate",
        wrapped_climate=WRAPPED,
        zone_home="zone.home",
        away_temp=14.0,
        away_delay_minutes=0,
        interruptible=True,
        default_override_mode="timer",
        default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    entity._mode = MODE_AUTO
    return entity, hass


def _last_set_temperature(hass):
    """Return the temperature from the last climate.set_temperature call, or None."""
    for call in reversed(hass.services.async_call.call_args_list):
        args = call.args
        if len(args) >= 2 and args[0] == "climate" and args[1] == "set_temperature":
            return args[2]["temperature"]
    return None


# ---------------------------------------------------------------------------
# Heating vs cooling setpoint family
# ---------------------------------------------------------------------------

async def test_heat_home_uses_auto_temperature():
    entity, hass = _make_entity(wrapped_mode="heat")
    entity._presence = "home"
    entity._auto_temperature = 21
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 21


async def test_heat_away_uses_away_temperature():
    entity, hass = _make_entity(wrapped_mode="heat")
    entity._presence = "away"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 14.0


async def test_cool_home_uses_cool_auto_temperature():
    entity, hass = _make_entity(
        wrapped_mode="cool",
        entry_data={CONF_COOL_AUTO_TEMPERATURE: 24, CONF_COOL_AWAY_TEMPERATURE: 28},
    )
    entity._presence = "home"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 24


async def test_cool_away_uses_cool_away_temperature():
    entity, hass = _make_entity(
        wrapped_mode="cool",
        entry_data={CONF_COOL_AUTO_TEMPERATURE: 24, CONF_COOL_AWAY_TEMPERATURE: 28},
    )
    entity._presence = "away"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 28


async def test_cool_ignores_heating_schedule():
    """A configured heating schedule must not affect cooling setpoints."""
    entity, hass = _make_entity(
        wrapped_mode="cool", entry_data={CONF_COOL_AUTO_TEMPERATURE: 25}
    )
    entity._presence = "home"
    entity._schedule = {"mode": "daily", "daily": [{"time": "00:00", "temp": 18}]}
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 25


async def test_auto_mode_uses_heating_comfort_target():
    entity, hass = _make_entity(wrapped_mode="auto")
    entity._presence = "home"
    entity._auto_temperature = 20
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) == 20


# ---------------------------------------------------------------------------
# Non-managed modes write no setpoint
# ---------------------------------------------------------------------------

async def test_off_writes_no_setpoint():
    entity, hass = _make_entity(wrapped_mode="off")
    entity._presence = "home"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) is None


async def test_fan_only_writes_no_setpoint():
    entity, hass = _make_entity(wrapped_mode="fan_only")
    entity._presence = "home"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) is None


async def test_dry_writes_no_setpoint():
    entity, hass = _make_entity(wrapped_mode="dry")
    entity._presence = "home"
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) is None


async def test_unavailable_wrapped_writes_no_setpoint():
    entity, hass = _make_entity()
    hass.states.get = MagicMock(return_value=None)
    await entity._update_target_temperature()
    assert _last_set_temperature(hass) is None


# ---------------------------------------------------------------------------
# Mirroring the wrapped device's capabilities
# ---------------------------------------------------------------------------

def test_hvac_modes_mirror_wrapped():
    modes = ["heat", "fan_only", "dry", "cool", "auto", "off"]
    entity, _ = _make_entity(wrapped_mode="heat", wrapped_attrs={"hvac_modes": modes})
    assert entity.hvac_modes == modes


def test_min_max_step_mirror_wrapped():
    entity, _ = _make_entity(
        wrapped_mode="heat",
        wrapped_attrs={"min_temp": 7, "max_temp": 35, "target_temp_step": 1},
    )
    assert entity.min_temp == 7
    assert entity.max_temp == 35
    assert entity.target_temperature_step == 1


def test_supported_features_advertise_fan_when_wrapped_supports_it():
    from custom_components.smart_climate.climate import ClimateEntityFeature

    # 393 = TARGET_TEMPERATURE | FAN_MODE | TURN_OFF | TURN_ON (the Qlima airco)
    entity, _ = _make_entity(
        wrapped_mode="cool", wrapped_attrs={"supported_features": 393}
    )
    assert entity.supported_features & ClimateEntityFeature.FAN_MODE


def test_supported_features_no_fan_when_wrapped_lacks_it():
    from custom_components.smart_climate.climate import ClimateEntityFeature

    entity, _ = _make_entity(
        wrapped_mode="heat", wrapped_attrs={"supported_features": 1}
    )
    assert not (entity.supported_features & ClimateEntityFeature.FAN_MODE)


async def test_set_cool_auto_temperature_persists():
    entity, _ = _make_entity(wrapped_mode="cool")
    await entity.async_set_cool_auto_temperature(23)
    assert entity.entry.data[CONF_COOL_AUTO_TEMPERATURE] == 23


async def test_set_cool_away_temperature_persists():
    entity, _ = _make_entity(wrapped_mode="cool")
    await entity.async_set_cool_away_temperature(30)
    assert entity.entry.data[CONF_COOL_AWAY_TEMPERATURE] == 30
