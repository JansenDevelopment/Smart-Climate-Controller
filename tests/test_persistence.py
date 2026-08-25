"""Tests that runtime-configurable settings persist to config-entry storage.

Regression coverage for: settings changed at runtime (via the config/schedule
cards or the smart_climate.* services) must be written back to the config
entry's ``data`` so they survive a Home Assistant restart, and must be restored
on the next startup.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (
    CONF_AUTO_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_AWAY_TEMPERATURE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_HVAC_MODE,
    CONF_INTERRUPTIBLE,
    CONF_SCHEDULE,
)


def _make_entity(entry_data=None):
    """Build a SmartClimateEntity whose config entry persists like real HA.

    The mock ``async_update_entry`` mutates ``entry.data`` in place so a
    rebuilt entity reads back whatever a setter persisted.
    """
    from custom_components.smart_climate.climate import SmartClimateEntity

    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.services.async_call = AsyncMock()

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
        wrapped_climate="climate.wrapped",
        zone_home="zone.home",
        away_temp=14.0,
        away_delay_minutes=0,
        interruptible=True,
        default_override_mode="timer",
        default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    return entity, hass, entry


async def test_set_auto_temperature_persists():
    entity, hass, entry = _make_entity()
    await entity.async_set_auto_temperature(19.5)
    assert entry.data[CONF_AUTO_TEMPERATURE] == 19.5
    hass.config_entries.async_update_entry.assert_called()


async def test_set_away_temperature_persists():
    entity, _, entry = _make_entity()
    await entity.async_set_away_temperature(12.0)
    assert entry.data[CONF_AWAY_TEMPERATURE] == 12.0


async def test_set_away_delay_persists():
    entity, _, entry = _make_entity()
    await entity.async_set_away_delay(15)
    assert entry.data[CONF_AWAY_DELAY_MINUTES] == 15


async def test_set_interruptible_persists():
    entity, _, entry = _make_entity()
    await entity.async_set_interruptible(False)
    assert entry.data[CONF_INTERRUPTIBLE] is False


async def test_set_default_override_mode_persists():
    entity, _, entry = _make_entity()
    await entity.async_set_default_override_mode("infinity", 45)
    assert entry.data[CONF_DEFAULT_OVERRIDE_MODE] == "infinity"
    assert entry.data[CONF_DEFAULT_OVERRIDE_DURATION] == 45


async def test_set_schedule_persists():
    entity, _, entry = _make_entity()
    schedule = {"mode": "daily", "daily": [{"time": "06:00", "temp": 21}]}
    await entity.async_set_schedule(schedule)
    assert entry.data[CONF_SCHEDULE] == schedule


async def test_turn_on_selects_auto_so_the_coordinator_leads():
    """turn_on must not pin heat — the band owns the heat/cool decision."""
    entity, _, entry = _make_entity()
    await entity.async_turn_on()
    assert entity._hvac_mode == "auto"
    assert entry.data[CONF_HVAC_MODE] == "auto"


async def test_turn_off_persists_hvac_mode():
    entity, _, entry = _make_entity()
    await entity.async_turn_off()
    assert entity._hvac_mode == "off"
    assert entry.data[CONF_HVAC_MODE] == "off"


def test_constructor_restores_persisted_auto_temperature_and_schedule():
    schedule = {"mode": "daily", "daily": [{"time": "07:00", "temp": 20}]}
    entity, _, _ = _make_entity(
        entry_data={CONF_AUTO_TEMPERATURE: 23, CONF_SCHEDULE: schedule}
    )
    assert entity._auto_temperature == 23
    assert entity._schedule == schedule


async def test_setting_then_rebuilding_round_trips():
    """A value set at runtime is visible to a freshly constructed entity."""
    entity, hass, entry = _make_entity()
    await entity.async_set_auto_temperature(18.0)

    # Rebuild from the same (now-mutated) entry, mimicking a restart.
    from custom_components.smart_climate.climate import SmartClimateEntity

    rebuilt = SmartClimateEntity(
        hass=hass,
        entry=entry,
        name="Test Climate",
        wrapped_climate="climate.wrapped",
        zone_home="zone.home",
        away_temp=14.0,
        away_delay_minutes=0,
        interruptible=True,
        default_override_mode="timer",
        default_override_duration=30,
    )
    assert rebuilt._auto_temperature == 18.0
