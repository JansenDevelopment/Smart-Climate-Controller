"""Observe (proefdraaien), the action log, fan boost/hold in the loop, and off-by-hand."""

import pathlib
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

FANS = ["auto", "low", "medium", "high"]
QLIMA = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat", "cool", "fan_only"], "target_temp_step": 1, "min_temp": 16,
    "current_temperature": 18, "fan_modes": FANS, "fan_mode": "auto"}}
CV = {"state": "off", "attributes": {"hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "current_temperature": 18}}
DEVICES = [
    {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "park": "off"},
    {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"},
]


@pytest.fixture(autouse=True)
def _restore_clock():
    from custom_components.smart_climate import climate as climate_mod

    original = climate_mod.dt_util.now
    yield
    climate_mod.dt_util.now = original


def _state(spec):
    st = MagicMock()
    st.state = spec["state"]
    st.attributes = spec["attributes"]
    return st


def _make(states, **data):
    from custom_components.smart_climate import climate as climate_mod
    from custom_components.smart_climate.climate import SmartClimateEntity

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=lambda eid: _state(states[eid]) if eid in states else None)
    entry = MagicMock()
    entry.entry_id = "e"
    entry.data = {"devices": DEVICES, "auto_temperature": 21, "support_grace": 0,
                  "support_enabled": False, "temperature_source": "sensor",
                  "temperature_sensor": "sensor.room", **data}
    entity = SmartClimateEntity(
        hass=hass, entry=entry, name="T", wrapped_climate=None, zone_home="zone.home",
        away_temp=17.0, away_delay_minutes=0, interruptible=True,
        default_override_mode="next_node", default_override_duration=30,
    )
    entity.entity_id = "climate.smart_climate"
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = "auto"
    entity._presence = "home"
    clock = {"now": datetime(2026, 1, 12, 7, 30).astimezone()}
    climate_mod.dt_util.now = lambda: clock["now"]
    return entity, hass, clock


def _calls(hass, service):
    return [c.args[2] for c in hass.services.async_call.call_args_list if c.args[1] == service]


def _event(entity_id, old, new):
    ev = MagicMock()
    ev.data = {"entity_id": entity_id, "old_state": _state(old), "new_state": _state(new)}
    return ev


def _room(states, value):
    states["sensor.room"] = {"state": str(value), "attributes": {}}


async def test_boost_heats_on_high_and_holds_at_the_target():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 18.5)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True)
    await entity._apply_control()
    assert {"entity_id": "climate.qlima", "hvac_mode": "heat"} in _calls(hass, "set_hvac_mode")
    assert {"entity_id": "climate.qlima", "fan_mode": "high"} in _calls(hass, "set_fan_mode")
    assert entity.extra_state_attributes["plan"][0]["fan_mode"] == "high"
    assert [e["who"] for e in entity._log] == ["control"]

    # warm: idle, but the Qlima keeps heating at the target, fan back to auto after the hold time
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "fan_mode": "high"}}
    _room(states, 21.6)  # past target + hysteresis
    clock["now"] += timedelta(minutes=30)
    hass.services.async_call.reset_mock()
    await entity._apply_control()
    assert entity._intent == "idle"
    assert _calls(hass, "set_hvac_mode") == []
    assert _calls(hass, "set_fan_mode") == [{"entity_id": "climate.qlima", "fan_mode": "auto"}]


async def test_without_the_options_nothing_changes():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 18.5)
    entity, hass, clock = _make(states)
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == []
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21}}
    _room(states, 21.6)
    clock["now"] += timedelta(minutes=30)
    await entity._apply_control()
    assert {"entity_id": "climate.qlima", "hvac_mode": "off"} in _calls(hass, "set_hvac_mode")


async def test_observe_logs_what_it_would_do_and_sends_nothing():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 18.5)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True, observe=True)
    # devices the user put on manual are planned as auto while observing
    entity._device_modes["climate.qlima"] = {"mode": "manual", "until": None, "source": "user"}
    await entity._apply_control()
    await entity._apply_control()
    assert hass.services.async_call.call_count == 0
    texts = [(e["who"], e["entity_id"], e["text"]) for e in entity._log]
    assert ("observe", "climate.qlima", "warm · 21° · ventilator hoog") in texts
    assert len(texts) == 2  # qlima + cv once, not again on the second pass
    assert entity.extra_state_attributes["observe"] is True


async def test_hand_changes_are_logged_with_context():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 19.0)
    entity, hass, clock = _make(states, observe=True)
    old = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22, "fan_mode": "medium"}}
    new = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22, "fan_mode": "high"}}
    entity._log.clear()
    await entity._on_watched_change(_event("climate.qlima", old, new))
    hand = [e for e in entity._log if e["who"] == "hand"]
    assert hand[0]["text"] == "ventilator hoog"
    assert hand[0]["room"] == 19.0
    assert hand[0]["presence"] == "home"


async def test_off_by_hand_stays_off_until_on_by_hand():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 19.0)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True)
    await entity._apply_control()  # qlima heats
    clock["now"] += timedelta(minutes=5)
    on = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21}}
    off = {"state": "off", "attributes": {**QLIMA["attributes"], "temperature": 21}}
    states["climate.qlima"] = off
    await entity._on_watched_change(_event("climate.qlima", on, off))
    assert entity._device_modes["climate.qlima"]["off_by_hand"] is True
    assert entity._device_modes["climate.qlima"]["until"] is None

    # hours later, past schedule points: still left alone
    hass.services.async_call.reset_mock()
    clock["now"] += timedelta(hours=6)
    await entity._update_state()
    assert [c for c in _calls(hass, "set_hvac_mode") if c["entity_id"] == "climate.qlima"] == []

    # on again by hand: back to the coordinator
    states["climate.qlima"] = on
    await entity._on_watched_change(_event("climate.qlima", off, on))
    assert "climate.qlima" not in entity._device_modes
    assert "weer aan met de hand" in entity._log[-2]["text"] or "weer aan met de hand" in entity._log[-1]["text"]


async def test_switching_off_by_the_coordinator_is_not_off_by_hand():
    states = {"climate.qlima": {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21}}, "climate.cv": CV}
    _room(states, 23.0)
    entity, hass, clock = _make(states)  # no hold: a warm room parks the qlima off
    await entity._apply_control()
    assert {"entity_id": "climate.qlima", "hvac_mode": "off"} in _calls(hass, "set_hvac_mode")
    clock["now"] += timedelta(seconds=5)
    await entity._on_watched_change(_event("climate.qlima", states["climate.qlima"], {**QLIMA}))
    assert "climate.qlima" not in entity._device_modes


async def test_waits_for_the_room_sensor_after_a_restart():
    warm = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "current_temperature": 24}}
    states = {"climate.qlima": warm, "climate.cv": CV}  # sensor.room not loaded yet
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True)
    await entity._apply_control()
    assert hass.services.async_call.call_count == 0
    _room(states, 19.0)
    clock["now"] += timedelta(seconds=20)
    await entity._apply_control()
    assert {"entity_id": "climate.qlima", "fan_mode": "high"} in _calls(hass, "set_fan_mode")


async def test_parts_are_sent_one_after_another_and_a_lost_part_is_retried():
    # measured 9 November: a fan command before the setpoint was confirmed put the old setpoint back
    states = {"climate.qlima": {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 23, "fan_mode": "high"}},
              "climate.cv": CV}
    _room(states, 20.5)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True)
    await entity._apply_control()
    sent = [(c.args[1], c.args[2].get("temperature") or c.args[2].get("fan_mode")) for c in hass.services.async_call.call_args_list]
    assert sent == [("set_temperature", 21), ("set_fan_mode", "medium")]
    # the device kept 23 (lost) but took the fan: only the setpoint is sent again, after 20 s
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 23, "fan_mode": "medium"}}
    hass.services.async_call.reset_mock()
    clock["now"] += timedelta(seconds=10)
    await entity._apply_control()
    assert hass.services.async_call.call_count == 0
    clock["now"] += timedelta(seconds=15)
    await entity._apply_control()
    assert [c.args[1] for c in hass.services.async_call.call_args_list] == ["set_temperature"]
    assert "poging 2" in entity._log[-1]["text"]

