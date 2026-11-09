"""Fan boost, hold and trim for a primary heater that modulates on its own sensor."""

from custom_components.smart_climate import control
from custom_components.smart_climate.control import Decision

FANS = ["auto", "low", "medium", "high"]


def test_fan_steps_with_the_deficit():
    assert control.fan_for(18.0, 21.0, None, None, FANS) == "high"
    assert control.fan_for(20.5, 21.0, None, None, FANS) == "medium"
    assert control.fan_for(20.8, 21.0, None, None, FANS) == "auto"
    assert control.fan_for(22.0, 21.0, None, None, FANS) == "auto"


def test_fan_steps_up_at_once_but_down_only_after_hold_and_backoff():
    # up: immediately, even right after a change
    assert control.fan_for(18.0, 21.0, "auto", 1, FANS) == "high"
    # down: too soon
    assert control.fan_for(20.5, 21.0, "high", 5, FANS) == "high"
    # down: long enough, but still within the backoff of the high threshold
    assert control.fan_for(20.1, 21.0, "high", 30, FANS) == "high"
    # down: long enough and clearly past it
    assert control.fan_for(20.3, 21.0, "high", 30, FANS) == "medium"
    assert control.fan_for(20.95, 21.0, "medium", 30, FANS) == "auto"


def test_fan_without_room_or_modes_leaves_it_alone():
    assert control.fan_for(None, 21.0, None, None, FANS) is None
    assert control.fan_for(18.0, 21.0, None, None, None) is None
    assert control.fan_for(18.0, 21.0, None, None, ["silent"]) is None


def test_fan_falls_back_to_an_available_step():
    assert control.fan_for(20.5, 21.0, None, None, ["auto", "low", "high"]) == "low"


def test_trim_goes_down_after_a_while_and_back_under_the_target():
    assert control.hold_trim(21.6, 21.0, 0.0, 5) == 0.0
    assert control.hold_trim(21.6, 21.0, 0.0, 25) == -1.0
    assert control.hold_trim(21.2, 21.0, -1.0, None) == -1.0
    assert control.hold_trim(20.9, 21.0, -1.0, None) == 0.0


def test_eta():
    assert control.eta_minutes(19.0, 21.0, 1.0) == 120
    assert control.eta_minutes(21.5, 21.0, 1.0) == 0
    assert control.eta_minutes(19.0, 21.0, 0.05) is None
    assert control.eta_minutes(19.0, 21.0, None) is None


QLIMA = {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "park": "off",
         "hold": True, "min_temp": 16, "step": 1, "fan": "medium"}
CV = {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"}


def test_heating_carries_the_fan_mode():
    cmds = control.plan_routes(Decision(control.HEAT, 21.0), [QLIMA, CV])
    assert cmds[0] == control.DeviceCommand("climate.qlima", "heat", 21, "medium")
    assert cmds[1] == control.DeviceCommand("climate.cv", "off")


def test_idle_holds_the_primary_heater_with_trim():
    q = {**QLIMA, "trim": -1.0, "fan": "auto"}
    cmds = control.plan_routes(Decision(control.IDLE), [q, CV], hold_target=21.0)
    assert cmds[0] == control.DeviceCommand("climate.qlima", "heat", 20, "auto")
    assert cmds[1].hvac_mode == "off"


def test_idle_without_hold_parks_as_before():
    q = {**QLIMA, "hold": False}
    cmds = control.plan_routes(Decision(control.IDLE), [q], hold_target=21.0)
    assert cmds == [control.DeviceCommand("climate.qlima", "off")]


def test_setback_below_the_device_range_turns_it_off():
    cmds = control.plan_routes(Decision(control.IDLE), [QLIMA], hold_target=11.5)
    assert cmds == [control.DeviceCommand("climate.qlima", "off")]


def test_manual_device_is_never_held():
    q = {**QLIMA, "control": "manual"}
    assert control.plan_routes(Decision(control.IDLE), [q], hold_target=21.0) == []


def test_off_decision_beats_hold():
    cmds = control.plan_routes(Decision(control.OFF), [QLIMA], hold_target=21.0)
    assert cmds == [control.DeviceCommand("climate.qlima", "off")]


def test_primary_off_by_hand_means_no_heating_at_all():
    q = {**QLIMA, "control": "manual", "off_by_hand": True}
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [q, CV], support_active=True)
    assert cmds == [control.DeviceCommand("climate.cv", "off")]


def test_unavailable_primary_still_hands_over_to_the_cv():
    q = {**QLIMA, "available": False}
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [q, CV])
    assert control.DeviceCommand("climate.cv", "heat", 21.5) in cmds


def test_primary_not_used_by_choice_still_hands_over_to_the_cv():
    q = {**QLIMA, "control": "off"}
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [q, CV])
    assert control.DeviceCommand("climate.cv", "heat", 21.5) in cmds

