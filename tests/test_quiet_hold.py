"""Quiet hold (1.7.2): the fan stays on medium around the target instead of flapping medium <-> auto."""

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


def test_quiet_fan_holds_medium_until_over_the_target():
    # plain mode unchanged: medium back to auto close to the target
    assert control.fan_for(21.45, 21.5, "medium", 30, FANS) == "auto"
    # quiet: medium stays at and just over the target
    assert control.fan_for(21.45, 21.5, "medium", 60, FANS, quiet=True) == "medium"
    assert control.fan_for(21.6, 21.5, "medium", 60, FANS, quiet=True) == "medium"
    # back to auto only 0.2 over the target and after 30 minutes
    assert control.fan_for(21.7, 21.5, "medium", 20, FANS, quiet=True) == "medium"
    assert control.fan_for(21.7, 21.5, "medium", 30, FANS, quiet=True) == "auto"
    # from auto: up to medium only 0.3 under the target
    assert control.fan_for(21.3, 21.5, "auto", 60, FANS, quiet=True) == "auto"
    assert control.fan_for(21.1, 21.5, "auto", 60, FANS, quiet=True) == "medium"
    # first decision: medium unless already over the target
    assert control.fan_for(21.4, 21.5, None, None, FANS, quiet=True) == "medium"
    assert control.fan_for(21.8, 21.5, None, None, FANS, quiet=True) == "auto"
    # far under: high as before, and high steps down to medium (not auto)
    assert control.fan_for(20.3, 21.5, "medium", 60, FANS, quiet=True) == "high"
    assert control.fan_for(21.6, 21.5, "high", 60, FANS, quiet=True) == "medium"


def test_quiet_lead_starts_later():
    assert control.setpoint_lead(20.9, 21.5, 0, 6.0) == 6
    assert control.setpoint_lead(20.9, 21.5, 0, 6.0, lead_on=control.QUIET_LEAD_ON) == 0
    assert control.setpoint_lead(20.4, 21.5, 0, 6.0, lead_on=control.QUIET_LEAD_ON) == 6


def test_no_upward_trim_any_more():
    assert control.hold_trim(21.1, 21.5, 0.0, None) == 0.0
    assert control.hold_trim(22.1, 21.5, 0.0, 25) == -1.0
    assert control.hold_trim(21.6, 21.5, -1.0, None) == -1.0
    assert control.hold_trim(21.4, 21.5, -1.0, None) == 0.0


async def _holding(**data):
    """An entity at its target of 21 with the fan on medium (warmed up first)."""
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 18.5)
    entity, hass, clock = _make(states, fan_boost=True, hold_primary=True, **data)
    await entity._apply_control()
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "fan_mode": "high"}}
    _room(states, 20.9)
    clock["now"] += timedelta(minutes=30)
    await entity._apply_control()
    states["climate.qlima"] = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 21, "fan_mode": "medium"}}
    hass.services.async_call.reset_mock()
    return entity, hass, clock, states


async def test_quiet_hold_keeps_medium_at_the_target():
    entity, hass, clock, states = await _holding(quiet_hold=True)
    _room(states, 21.05)
    clock["now"] += timedelta(minutes=40)
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == []


async def test_without_quiet_hold_the_fan_steps_down_as_before():
    entity, hass, clock, states = await _holding()
    _room(states, 21.05)
    clock["now"] += timedelta(minutes=40)
    await entity._apply_control()
    assert _calls(hass, "set_fan_mode") == [{"entity_id": "climate.qlima", "fan_mode": "auto"}]


async def test_set_behaviour_stores_quiet_hold():
    entity, hass, _clock, _states = await _holding()
    assert entity.extra_state_attributes["quiet_hold"] is False
    await entity.async_set_behaviour(quiet_hold=True)
    persisted = [c.kwargs["data"] for c in hass.config_entries.async_update_entry.call_args_list]
    assert any(d.get("quiet_hold") is True for d in persisted)
    assert any(e["text"] == "stil aanhouden aan" for e in entity._log)
