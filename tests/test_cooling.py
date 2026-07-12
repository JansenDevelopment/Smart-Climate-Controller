"""Coordinator integration tests: mode-owned control driving a single device.

These exercise SmartClimateEntity._apply_control end-to-end against one actuator
device — the pure decision/routing logic itself lives in test_control.py.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    CONF_DEVICES,
    MODE_AUTO,
)

WRAPPED = "climate.wrapped"


def _make_entity(
    hvac_mode="heat",
    device_state="off",
    device_attrs=None,
    room_temp=None,
    presence="home",
    entry_data=None,
):
    from custom_components.smart_climate.climate import SmartClimateEntity

    device = MagicMock()
    device.state = device_state
    attrs = {}
    if room_temp is not None:
        attrs["current_temperature"] = room_temp
    if device_attrs:
        attrs.update(device_attrs)
    device.attributes = attrs

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=lambda eid: device if eid == WRAPPED else None)
    hass.config_entries.async_update_entry = MagicMock()

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = dict(entry_data or {})

    entity = SmartClimateEntity(
        hass=hass, entry=entry, name="Test", wrapped_climate=WRAPPED,
        zone_home="zone.home", away_temp=14.0, away_delay_minutes=0,
        interruptible=True, default_override_mode="timer", default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = hvac_mode
    entity._presence = presence
    entity._mode = MODE_AUTO
    return entity, hass, device


def _svc(hass, service):
    return [
        c.args[2]
        for c in hass.services.async_call.call_args_list
        if c.args[0] == "climate" and c.args[1] == service
    ]


def _last_temp(hass):
    calls = _svc(hass, "set_temperature")
    return calls[-1]["temperature"] if calls else None


def _last_mode(hass):
    calls = _svc(hass, "set_hvac_mode")
    return calls[-1]["hvac_mode"] if calls else None


# ---------------------------------------------------------------------------
# Setpoint routing per coordinator mode
# ---------------------------------------------------------------------------

async def test_heat_mode_home_sets_heat_and_auto_temp():
    entity, hass, _ = _make_entity(hvac_mode="heat", presence="home")
    entity._auto_temperature = 21
    await entity._apply_control()
    assert _last_mode(hass) == "heat"
    assert _last_temp(hass) == 21


async def test_heat_mode_away_uses_away_temp():
    entity, hass, _ = _make_entity(hvac_mode="heat", presence="away")
    await entity._apply_control()
    assert _last_temp(hass) == 14.0


async def test_cool_mode_home_uses_cool_auto_temp():
    entity, hass, _ = _make_entity(
        hvac_mode="cool", presence="home",
        entry_data={CONF_COOL_AUTO_TEMPERATURE: 24, CONF_COOL_AWAY_TEMPERATURE: 28},
    )
    await entity._apply_control()
    assert _last_mode(hass) == "cool"
    assert _last_temp(hass) == 24


async def test_cool_mode_away_uses_cool_away_temp():
    entity, hass, _ = _make_entity(
        hvac_mode="cool", presence="away",
        entry_data={CONF_COOL_AUTO_TEMPERATURE: 24, CONF_COOL_AWAY_TEMPERATURE: 28},
    )
    await entity._apply_control()
    assert _last_temp(hass) == 28


async def test_auto_below_band_heats_device():
    entity, hass, _ = _make_entity(hvac_mode="auto", presence="home", room_temp=18,
                                   entry_data={CONF_COOL_AUTO_TEMPERATURE: 25})
    entity._auto_temperature = 21
    await entity._apply_control()
    assert _last_mode(hass) == "heat"
    assert _last_temp(hass) == 21


async def test_auto_above_band_cools_device():
    entity, hass, _ = _make_entity(hvac_mode="auto", presence="home", room_temp=27,
                                   entry_data={CONF_COOL_AUTO_TEMPERATURE: 25})
    entity._auto_temperature = 21
    await entity._apply_control()
    assert _last_mode(hass) == "cool"
    assert _last_temp(hass) == 25


async def test_auto_inside_band_idles_device_off_without_fan():
    entity, hass, _ = _make_entity(hvac_mode="auto", device_state="heat", presence="home",
                                   room_temp=23, entry_data={CONF_COOL_AUTO_TEMPERATURE: 25})
    entity._auto_temperature = 21
    await entity._apply_control()
    # No fan_only support → parked off, and no setpoint written
    assert _last_mode(hass) == "off"
    assert _svc(hass, "set_temperature") == []


async def test_auto_inside_band_keeps_airflow_when_fan_capable():
    entity, hass, _ = _make_entity(
        hvac_mode="auto", presence="home", room_temp=23,
        device_attrs={"hvac_modes": ["off", "heat", "cool", "fan_only"]},
        entry_data={CONF_COOL_AUTO_TEMPERATURE: 25},
    )
    entity._auto_temperature = 21
    await entity._apply_control()
    assert _last_mode(hass) == "fan_only"


async def test_off_mode_powers_device_off():
    entity, hass, _ = _make_entity(hvac_mode="off", device_state="heat", presence="home")
    await entity._apply_control()
    assert _last_mode(hass) == "off"
    assert _svc(hass, "set_temperature") == []


async def test_no_devices_does_nothing():
    entity, hass, _ = _make_entity(hvac_mode="heat")
    entity._devices = []
    await entity._apply_control()
    assert hass.services.async_call.call_count == 0


async def test_change_detection_skips_redundant_calls():
    # Device already in heat at the target — no service calls should be issued.
    entity, hass, device = _make_entity(hvac_mode="heat", device_state="heat", presence="home")
    entity._auto_temperature = 21
    device.attributes["temperature"] = 21
    await entity._apply_control()
    assert hass.services.async_call.call_count == 0


# ---------------------------------------------------------------------------
# Capability aggregation & migration
# ---------------------------------------------------------------------------

def test_hvac_modes_are_own_set():
    entity, _, _ = _make_entity()
    assert entity.hvac_modes == ["off", "heat", "cool", "auto"]


def test_hvac_mode_is_owned():
    entity, _, _ = _make_entity(hvac_mode="cool")
    assert entity.hvac_mode == "cool"


def test_min_max_step_aggregate_from_devices():
    entity, _, _ = _make_entity(
        device_attrs={"min_temp": 7, "max_temp": 35, "target_temp_step": 1}
    )
    assert entity.min_temp == 7
    assert entity.max_temp == 35
    assert entity.target_temperature_step == 1


def test_supported_features_include_fan_when_device_supports_it():
    from custom_components.smart_climate.climate import ClimateEntityFeature

    entity, _, _ = _make_entity(device_attrs={"supported_features": 393})
    assert entity.supported_features & ClimateEntityFeature.FAN_MODE


def test_hvac_action_reflects_intent():
    entity, hass, _ = _make_entity(hvac_mode="heat", presence="home")
    entity._auto_temperature = 21
    # before any evaluation
    assert entity.hvac_action == "idle"


def test_migration_from_single_wrapped_climate():
    entity, _, _ = _make_entity()
    assert entity._devices == [{"entity_id": WRAPPED, "role": "both"}]


def test_devices_list_from_entry():
    entity, _, _ = _make_entity(
        entry_data={CONF_DEVICES: [
            {"entity_id": "climate.rad", "role": "heat"},
            {"entity_id": "climate.ac", "role": "cool"},
        ]}
    )
    assert {d["entity_id"] for d in entity._devices} == {"climate.rad", "climate.ac"}
    assert entity._devices[0]["role"] == "heat"


class _Sub:
    def __init__(self, subentry_type, data):
        self.subentry_type = subentry_type
        self.data = data


def test_build_devices_merges_subentries_and_data():
    from custom_components.smart_climate.climate import SmartClimateEntity

    entry = MagicMock()
    entry.subentries = {
        "s1": _Sub("device", {"entity_id": "climate.a", "role": "heat"}),
        "s2": _Sub("other", {"entity_id": "climate.ignored"}),
    }
    entry.data = {CONF_DEVICES: [{"entity_id": "climate.b", "role": "cool"}]}
    devices = SmartClimateEntity._build_devices(entry, None)
    ids = [d["entity_id"] for d in devices]
    assert "climate.a" in ids and "climate.b" in ids
    assert "climate.ignored" not in ids


def test_build_devices_dedupes_by_entity_id():
    from custom_components.smart_climate.climate import SmartClimateEntity

    entry = MagicMock()
    entry.subentries = {"s1": _Sub("device", {"entity_id": "climate.a", "role": "heat"})}
    entry.data = {CONF_DEVICES: [{"entity_id": "climate.a", "role": "cool"}]}
    devices = SmartClimateEntity._build_devices(entry, None)
    assert len(devices) == 1
    assert devices[0]["role"] == "heat"  # subentry wins (added first)


def test_build_devices_migrates_wrapped_when_no_list():
    from custom_components.smart_climate.climate import SmartClimateEntity

    entry = MagicMock()
    entry.subentries = {}
    entry.data = {}
    devices = SmartClimateEntity._build_devices(entry, "climate.legacy")
    assert devices == [{"entity_id": "climate.legacy", "role": "both"}]
