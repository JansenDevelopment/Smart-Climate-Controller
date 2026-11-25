"""Hold trim upwards (1.8.0): a primary heater at the plain target that leaves the room short gets +1 at a time."""

from datetime import timedelta

from custom_components.smart_climate import control
from custom_components.smart_climate.control import Decision
from tests.test_observe_log import (  # noqa: F401
    CV,
    QLIMA,
    _calls,
    _make,
    _restore_clock,
    _room,
)


def test_trim_steps_up_after_a_while_under_the_target():
    assert control.hold_trim(20.8, 21.5, 0.0, None, 10) == 0.0
    assert control.hold_trim(20.8, 21.5, 0.0, None, 30) == 1.0
    assert control.hold_trim(20.8, 21.5, 1.0, None, 30) == 2.0
    assert control.hold_trim(20.8, 21.5, control.TRIM_MAX, None, 30) == control.TRIM_MAX
    # close to the target (within TRIM_BELOW) nothing counts
    assert control.hold_trim(21.3, 21.5, 1.0, None, None) == 1.0


def test_positive_trim_stays_and_comes_down_a_step_when_too_warm():
    assert control.hold_trim(21.6, 21.5, 2.0, None, None) == 2.0
    assert control.hold_trim(22.1, 21.5, 2.0, 25, None) == 1.0
    assert control.hold_trim(22.1, 21.5, 0.0, 25, None) == -1.0
    # the old downward trim is unchanged: back to 0 once under the target
    assert control.hold_trim(21.4, 21.5, -1.0, None, 40) == 0.0


QLIMA_CAP = {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "park": "off",
             "hold": True, "min_temp": 16, "max_temp": 30, "step": 1, "fan": "medium"}
CV_CAP = {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"}


def test_heating_at_the_plain_target_carries_the_trim():
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [{**QLIMA_CAP, "trim": 1.0}])
    assert cmds[0] == control.DeviceCommand("climate.qlima", "heat", 23, "medium")
    # the warm-up lead wins over the trim
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [{**QLIMA_CAP, "trim": 1.0, "lead": 3}])
    assert cmds[0].temperature == 25
    # a negative trim is for holding only, not for heating
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [{**QLIMA_CAP, "trim": -1.0}])
    assert cmds[0].temperature == 22


def test_support_heater_never_gets_the_trim():
    cmds = control.plan_routes(
        Decision(control.HEAT, 21.5), [{**QLIMA_CAP, "trim": 2.0}, {**CV_CAP, "trim": 2.0}], support_active=True,
    )
    cv = next(c for c in cmds if c.entity_id == "climate.cv")
    assert cv.temperature == 21.5


def _heating(states, temperature=21, own=23):
    states["climate.qlima"] = {"state": "heat", "attributes": {
        **QLIMA["attributes"], "temperature": temperature, "current_temperature": own, "fan_mode": "medium"}}


async def test_room_short_at_the_plain_target_raises_the_setpoint_once_per_half_hour():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states)
    _room(states, 20.6)
    entity, hass, clock = _make(states, hold_primary=True)
    await entity._apply_control()
    clock["now"] += timedelta(minutes=20)
    await entity._apply_control()
    assert entity._trim == 0.0
    clock["now"] += timedelta(minutes=11)
    await entity._apply_control()
    assert entity._trim == 1.0
    assert {"entity_id": "climate.qlima", "temperature": 22} in _calls(hass, "set_temperature")
    assert entity.extra_state_attributes["learning"]["climate.qlima"]["trim"] == 1.0
    # the next step waits its full time again
    _heating(states, temperature=22)
    clock["now"] += timedelta(minutes=10)
    await entity._apply_control()
    assert entity._trim == 1.0


async def test_trim_comes_down_when_the_room_gets_too_warm():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, temperature=23)
    _room(states, 21.7)
    entity, hass, clock = _make(states, hold_primary=True)
    entity._trim = 2.0
    await entity._apply_control()
    clock["now"] += timedelta(minutes=21)
    await entity._apply_control()
    assert entity._trim == 1.0
    assert {"entity_id": "climate.qlima", "temperature": 22} in _calls(hass, "set_temperature")


async def test_no_learning_during_the_warm_up_lead():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, own=23)
    _room(states, 19.5)
    entity, _hass, clock = _make(states, fan_boost=True, hold_primary=True)
    entity._offset["climate.qlima"] = 3.5
    for _ in range(5):
        await entity._apply_control()
        clock["now"] += timedelta(minutes=10)
    assert entity._lead["climate.qlima"] >= 3
    assert entity._trim == 0.0


async def test_night_setback_keeps_the_learned_trim():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states)
    _room(states, 19.0)
    entity, _hass, clock = _make(states, hold_primary=True, auto_temperature=12)
    entity._trim = 2.0
    for _ in range(4):
        await entity._apply_control()
        clock["now"] += timedelta(minutes=15)
    assert entity._trim == 2.0


async def test_no_learning_while_the_heater_is_on_manual():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states)
    _room(states, 20.6)
    entity, _hass, clock = _make(states, hold_primary=True)
    entity._device_modes["climate.qlima"] = {"mode": "manual", "until": None}
    for _ in range(5):
        await entity._apply_control()
        clock["now"] += timedelta(minutes=10)
    assert entity._trim == 0.0
