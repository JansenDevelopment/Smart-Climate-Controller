"""Off means hands off: the coordinator powers down once, then drives nothing."""

import pathlib
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.control import OFF, decide, plan_routes

AIRCO_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat", "cool", "fan_only"], "target_temp_step": 1, "current_temperature": 15}}
CV_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "current_temperature": 15}}
DEVICES = [
    {"entity_id": "climate.airco", "role": "both", "tier": "primary", "park": "off"},
    {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"},
]


@pytest.fixture(autouse=True)
def _restore_clock():
    from custom_components.smart_climate import climate as climate_mod

    original = climate_mod.dt_util.now
    yield
    climate_mod.dt_util.now = original


def _make(states):
    from custom_components.smart_climate import climate as climate_mod
    from custom_components.smart_climate.climate import SmartClimateEntity

    def _get(eid):
        if eid not in states:
            return None
        st = MagicMock()
        st.state = states[eid]["state"]
        st.attributes = states[eid]["attributes"]
        return st

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=_get)
    entry = MagicMock()
    entry.entry_id = "e"
    entry.data = {"devices": DEVICES, "auto_temperature": 21, "support_grace": 0}
    entity = SmartClimateEntity(
        hass=hass, entry=entry, name="T", wrapped_climate=None, zone_home="zone.home",
        away_temp=14.0, away_delay_minutes=0, interruptible=True,
        default_override_mode="timer", default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = "auto"
    entity._presence = "home"
    clock = {"now": datetime(2026, 1, 12, 7, 30).astimezone()}
    climate_mod.dt_util.now = lambda: clock["now"]
    return entity, hass, clock


def _on(state, temperature=None):
    attrs = {**AIRCO_STATE["attributes"]}
    if temperature is not None:
        attrs["temperature"] = temperature
    return {"state": state, "attributes": attrs}


def _hvac_calls(hass):
    return [
        (c.args[2]["entity_id"], c.args[2]["hvac_mode"])
        for c in hass.services.async_call.call_args_list
        if c.args[0] == "climate" and c.args[1] == "set_hvac_mode"
    ]


def _event(entity_id, state, temperature=None):
    new = MagicMock()
    new.state = state
    new.attributes = {"temperature": temperature} if temperature is not None else {}
    ev = MagicMock()
    ev.data = {"entity_id": entity_id, "new_state": new}
    return ev


async def test_an_expired_manual_mode_is_not_switched_off_while_off():
    # The 2 October case: the Qlima was set by hand, its manual mode ran out
    # at the next schedule point while the coordinator was off.
    states = {"climate.airco": _on("heat", 24), "climate.cv": CV_STATE}
    entity, hass, clock = _make(states)
    entity._hvac_mode = "off"
    entity._device_modes["climate.airco"] = {
        "mode": "manual", "until": (clock["now"] - timedelta(minutes=1)).isoformat(),
        "source": "external",
    }
    await entity._update_state()
    assert "climate.airco" not in entity._device_modes  # expired as before
    assert _hvac_calls(hass) == []  # but nothing is driven
    assert entity._acting is False


async def test_an_outside_change_is_not_taken_over_while_off():
    states = {"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE}
    entity, hass, clock = _make(states)
    await entity.async_set_hvac_mode("off")
    hass.services.async_call.reset_mock()
    clock["now"] += timedelta(minutes=5)
    states["climate.airco"] = _on("heat", 24)
    await entity._on_watched_change(_event("climate.airco", "heat", temperature=24))
    assert entity._device_modes == {}
    assert _hvac_calls(hass) == []


async def test_switching_to_off_powers_auto_devices_down_exactly_once():
    states = {"climate.airco": _on("heat", 21), "climate.cv": {**CV_STATE, "state": "heat"}}
    entity, hass, clock = _make(states)
    await entity.async_set_device_mode("climate.cv", "manual")
    hass.services.async_call.reset_mock()

    await entity.async_set_hvac_mode("off")
    assert _hvac_calls(hass) == [("climate.airco", "off")]  # manual CV untouched

    # The user turns the airco back on by remote; ticks leave it alone.
    states["climate.airco"] = _on("heat", 24)
    for _ in range(3):
        clock["now"] += timedelta(minutes=1)
        await entity._update_state()
    await entity.async_set_hvac_mode("off")  # off again: not a switch, no command
    assert _hvac_calls(hass) == [("climate.airco", "off")]


async def test_switching_back_on_drives_normally_and_is_no_takeover():
    states = {"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE}
    entity, hass, clock = _make(states)
    await entity.async_set_hvac_mode("off")
    clock["now"] += timedelta(hours=3)
    hass.services.async_call.reset_mock()

    await entity.async_set_hvac_mode("auto")
    assert ("climate.airco", "heat") in _hvac_calls(hass)
    # The device's own echo of that command is not an outside change.
    states["climate.airco"] = _on("heat", 21)
    clock["now"] += timedelta(seconds=5)
    await entity._on_watched_change(_event("climate.airco", "heat", temperature=21))
    assert entity._device_modes == {}


def test_auto_with_a_warm_room_still_switches_devices_off():
    # Hands off belongs to the coordinator being off, not to "no heat needed".
    devices = [{"entity_id": "a", "role": "heat", "tier": "primary", "park": "off"}]
    d = decide(mode="auto", room_temp=23, heat_target=21, cool_target=24, cooling_allowed=False)
    assert d.intent != OFF
    assert {c.entity_id: c.hvac_mode for c in plan_routes(d, devices)} == {"a": "off"}


async def test_a_device_that_ignores_a_setpoint_is_not_spammed():
    # 3 October: the Qlima did not take 14 °C and got it again every few seconds.
    states = {"climate.airco": _on("heat", 22), "climate.cv": CV_STATE}
    entity, hass, clock = _make(states)
    entity._hvac_mode = "heat"
    entity._auto_temperature = 14

    def _temps():
        return [
            c.args[2]["temperature"] for c in hass.services.async_call.call_args_list
            if c.args[1] == "set_temperature" and c.args[2]["entity_id"] == "climate.airco"
        ]

    await entity._apply_control()
    assert _temps() == [14]
    for _ in range(20):  # the device stays on 22; ticks and sensor updates follow
        clock["now"] += timedelta(seconds=5)
        await entity._apply_control()
    assert _temps() == [14]
    clock["now"] += timedelta(minutes=5)  # but it is retried now and then
    await entity._apply_control()
    assert _temps() == [14, 14]
