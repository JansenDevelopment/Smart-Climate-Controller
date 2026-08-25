"""Tests for the pure control core: decide(), plan_routes(), and the band."""

import itertools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.control import (
    COOL,
    HEAT,
    IDLE,
    OFF,
    Decision,
    clamp_band,
    decide,
    plan_routes,
)


def _dev(entity_id, role, fan=False):
    return {"entity_id": entity_id, "role": role, "supports_fan_only": fan}


# ---------------------------------------------------------------------------
# decide()
# ---------------------------------------------------------------------------

def test_off_mode_is_off():
    d = decide(mode="off", room_temp=30, heat_target=21, cool_target=25)
    assert d == Decision(OFF, None)


def test_explicit_heat_targets_heat():
    d = decide(mode="heat", room_temp=30, heat_target=21, cool_target=25)
    assert d.intent == HEAT and d.target == 21


def test_explicit_cool_targets_cool():
    d = decide(mode="cool", room_temp=10, heat_target=21, cool_target=25)
    assert d.intent == COOL and d.target == 25


def test_auto_below_band_heats():
    d = decide(mode="auto", room_temp=18, heat_target=21, cool_target=25)
    assert d.intent == HEAT and d.target == 21


def test_auto_above_band_cools():
    d = decide(mode="auto", room_temp=27, heat_target=21, cool_target=25)
    assert d.intent == COOL and d.target == 25


def test_auto_inside_band_idles():
    d = decide(mode="auto", room_temp=23, heat_target=21, cool_target=25)
    assert d.intent == IDLE


def test_hysteresis_keeps_heating_until_target_plus_h():
    # Was heating; room just reached heat_target — keep heating until +H.
    d = decide(mode="auto", room_temp=21.1, heat_target=21, cool_target=25,
               prev_intent=HEAT, hysteresis=0.3)
    assert d.intent == HEAT
    # Past heat_target + H → stop (idle).
    d2 = decide(mode="auto", room_temp=21.4, heat_target=21, cool_target=25,
                prev_intent=HEAT, hysteresis=0.3)
    assert d2.intent == IDLE


def test_hysteresis_keeps_cooling_until_target_minus_h():
    d = decide(mode="auto", room_temp=24.9, heat_target=21, cool_target=25,
               prev_intent=COOL, hysteresis=0.3)
    assert d.intent == COOL
    d2 = decide(mode="auto", room_temp=24.6, heat_target=21, cool_target=25,
                prev_intent=COOL, hysteresis=0.3)
    assert d2.intent == IDLE


def test_override_single_target_heats_and_cools():
    assert decide(mode="auto", room_temp=18, heat_target=21, cool_target=25,
                  override_target=22).intent == HEAT
    assert decide(mode="auto", room_temp=26, heat_target=21, cool_target=25,
                  override_target=22).intent == COOL


def test_override_ignored_when_off():
    d = decide(mode="off", room_temp=30, heat_target=21, cool_target=25,
               override_target=22)
    assert d.intent == OFF


def test_no_room_temp_holds_prev_intent_in_auto():
    d = decide(mode="auto", room_temp=None, heat_target=21, cool_target=25,
               prev_intent=HEAT)
    assert d.intent == HEAT


def test_misconfigured_band_is_clamped():
    # cool_target below heat_target would allow simultaneous demand — clamp it.
    h, c = clamp_band(25, 22, min_gap=1.0)
    assert c >= h + 1.0
    # And decide() must never both-heat-and-cool with an overlapping band.
    d = decide(mode="auto", room_temp=24, heat_target=25, cool_target=22)
    assert d.intent in (HEAT, IDLE, COOL)  # a single intent, never a conflict


# ---------------------------------------------------------------------------
# plan_routes()
# ---------------------------------------------------------------------------

def test_heat_intent_routes_to_heat_and_both_only():
    devices = [_dev("climate.rad", "heat"), _dev("climate.ac", "cool", fan=True),
               _dev("climate.combo", "both")]
    cmds = plan_routes(Decision(HEAT, 21), devices)
    by_id = {c.entity_id: c for c in cmds}
    assert by_id["climate.rad"].hvac_mode == "heat"
    assert by_id["climate.combo"].hvac_mode == "heat"
    # cool-only AC parks on fan_only, never heats or turns off
    assert by_id["climate.ac"].hvac_mode == "fan_only"


def test_cool_intent_routes_to_cool_and_both_only():
    devices = [_dev("climate.rad", "heat"), _dev("climate.ac", "cool", fan=True),
               _dev("climate.combo", "both")]
    cmds = plan_routes(Decision(COOL, 25), devices)
    by_id = {c.entity_id: c for c in cmds}
    assert by_id["climate.ac"].hvac_mode == "cool"
    assert by_id["climate.combo"].hvac_mode == "cool"
    # heat-only radiator (no fan) must go OFF while cooling, never stay in heat
    assert by_id["climate.rad"].hvac_mode == "off"


def test_off_decision_powers_all_off():
    devices = [_dev("climate.ac", "both", fan=True), _dev("climate.rad", "heat")]
    cmds = plan_routes(Decision(OFF, None), devices)
    assert all(c.hvac_mode == "off" for c in cmds)


def test_idle_parks_fan_devices_on_fan_and_others_off():
    devices = [_dev("climate.ac", "both", fan=True), _dev("climate.rad", "heat")]
    cmds = plan_routes(Decision(IDLE, None), devices)
    modes = {c.entity_id: c.hvac_mode for c in cmds}
    assert modes["climate.ac"] == "fan_only"      # airflow preserved
    assert modes["climate.rad"] == "off"           # no airflow to keep


# ---------------------------------------------------------------------------
# Conflict-prevention invariant (property style)
# ---------------------------------------------------------------------------

def test_never_heats_and_cools_simultaneously():
    devices = [_dev("a", "heat"), _dev("b", "cool", fan=True), _dev("c", "both", fan=True)]
    rooms = [5, 15, 20, 21, 23, 25, 27, 35]
    bands = [(21, 25), (25, 22), (20, 20), (18, 30)]  # includes overlapping/degenerate
    modes = ["auto", "heat", "cool", "off"]
    prevs = [None, HEAT, COOL, IDLE]
    for room, (h, c), mode, prev in itertools.product(rooms, bands, modes, prevs):
        d = decide(mode=mode, room_temp=room, heat_target=h, cool_target=c,
                   prev_intent=prev)
        cmds = plan_routes(d, devices)
        actions = {cmd.hvac_mode for cmd in cmds}
        assert not ("heat" in actions and "cool" in actions), (
            f"conflict: mode={mode} room={room} band=({h},{c}) prev={prev} -> {actions}"
        )


def test_devices_never_receive_the_coordinators_auto_mode():
    """``auto`` is ours, never a device's.

    The coordinator may sit in ``auto`` — that is what makes *it* decide heat
    versus cool. The devices must always be handed an explicit, unambiguous
    mode, otherwise the third-party thermostat would be making that call on its
    own thermostat logic and we would no longer be the lead.
    """
    devices = [_dev("a", "heat"), _dev("b", "cool", fan=True), _dev("c", "both", fan=True)]
    allowed = {"off", "heat", "cool", "fan_only"}
    rooms = [5, 15, 20, 21, 23, 25, 27, 35]
    bands = [(21, 25), (25, 22), (20, 20), (18, 30)]
    modes = ["auto", "heat", "cool", "off"]
    prevs = [None, HEAT, COOL, IDLE]
    for room, (h, c), mode, prev in itertools.product(rooms, bands, modes, prevs):
        for override in (None, 19.0):
            d = decide(mode=mode, room_temp=room, heat_target=h, cool_target=c,
                       override_target=override, prev_intent=prev)
            for cmd in plan_routes(d, devices):
                assert cmd.hvac_mode in allowed, (
                    f"device got {cmd.hvac_mode!r}: mode={mode} room={room} "
                    f"band=({h},{c}) override={override} prev={prev}"
                )
