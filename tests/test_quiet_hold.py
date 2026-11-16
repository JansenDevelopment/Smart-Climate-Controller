"""Quiet hold (1.7): while holding, a sagging room gets the setpoint +1 instead of a fan step (every command beeps)."""

from datetime import timedelta

from custom_components.smart_climate import control
from tests.test_observe_log import (  # noqa: F401
    CV,
    QLIMA,
    _calls,
    _make,
    _restore_clock,
    _room,
)

FANS = ["auto", "low", "medium", "high"]


def test_trim_goes_up_only_in_quiet_hold_and_back_at_the_target():
    assert control.hold_trim(21.1, 21.5, 0.0, None) == 0.0                # not quiet: nothing
    assert control.hold_trim(21.3, 21.5, 0.0, None, quiet=True) == 0.0    # within 0.3: nothing
    assert control.hold_trim(21.1, 21.5, 0.0, None, quiet=True) == 1.0
    assert control.hold_trim(20.9, 21.5, 0.0, None, quiet=True) == 0.0    # > 0.5 under: the lead's job
    assert control.hold_trim(21.4, 21.5, 1.0, None, quiet=True) == 1.0    # stays until the target
    assert control.hold_trim(21.5, 21.5, 1.0, None, quiet=True) == 0.0
    assert control.hold_trim(20.9, 21.5, 1.0, None, quiet=True) == 0.0    # sagged on: hand over to the lead
    assert control.hold_trim(21.1, 21.5, 1.0, None) == 0.0                # switched off: back at once
    # the downward trim is unchanged
    assert control.hold_trim(22.1, 21.5, 0.0, 25, quiet=True) == -1.0
    assert control.hold_trim(21.6, 21.5, -1.0, None, quiet=True) == -1.0
    assert control.hold_trim(21.4, 21.5, -1.0, None, quiet=True) == 0.0


def test_fan_never_steps_up_without_step_up_but_still_steps_down():
    assert control.fan_for(20.5, 21.0, "auto", 30, FANS, step_up=False) == "auto"
    assert control.fan_for(20.5, 21.0, None, None, FANS, step_up=False) == "auto"
    assert control.fan_for(20.5, 21.0, "high", 30, FANS, step_up=False) == "medium"
    assert control.fan_for(20.95, 21.0, "medium", 30, FANS, step_up=False) == "auto"
    assert control.fan_for(20.5, 21.0, "auto", 30, FANS) == "medium"       # default unchanged


async def _holding(**data):
    """An entity at its target of 21 with the fan on auto (warmed up first)."""
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 18.5)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True, **data)
    await entity._apply_control()
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "fan_mode": "high"}}
    _room(states, 21.6)
    clock["now"] += timedelta(minutes=30)
    await entity._apply_control()
    assert entity._intent == "idle"
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "fan_mode": "auto"}}
    hass.services.async_call.reset_mock()
    return entity, hass, clock, states


async def test_quiet_hold_raises_the_setpoint_and_leaves_the_fan():
    entity, hass, clock, states = await _holding(quiet_hold=True)
    _room(states, 20.6)
    clock["now"] += timedelta(minutes=20)
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == []
    assert _calls(hass, "set_temperature") == [{"entity_id": "climate.qlima", "temperature": 22}]

    # back at the target: the plain setpoint again, still no fan command
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22, "fan_mode": "auto"}}
    _room(states, 21.0)
    clock["now"] += timedelta(minutes=20)
    hass.services.async_call.reset_mock()
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == []
    assert _calls(hass, "set_temperature") == [{"entity_id": "climate.qlima", "temperature": 21}]


async def test_without_quiet_hold_the_fan_steps_up_as_before():
    entity, hass, clock, states = await _holding()
    _room(states, 20.6)
    clock["now"] += timedelta(minutes=20)
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == [{"entity_id": "climate.qlima", "fan_mode": "medium"}]
    assert _calls(hass, "set_temperature") == []


async def test_far_under_the_target_the_warm_up_takes_over():
    entity, hass, clock, states = await _holding(quiet_hold=True)
    _room(states, 20.2)
    clock["now"] += timedelta(minutes=20)
    await entity._apply_control()
    assert entity._trim == 0.0
    assert _calls(hass, "set_fan_mode") == [{"entity_id": "climate.qlima", "fan_mode": "medium"}]


async def test_set_behaviour_stores_quiet_hold():
    entity, hass, _clock, _states = await _holding()
    assert entity.extra_state_attributes["quiet_hold"] is False
    await entity.async_set_behaviour(quiet_hold=True)
    persisted = [c.kwargs["data"] for c in hass.config_entries.async_update_entry.call_args_list]
    assert any(d.get("quiet_hold") is True for d in persisted)
    assert any(e["text"] == "stil aanhouden aan" for e in entity._log)
