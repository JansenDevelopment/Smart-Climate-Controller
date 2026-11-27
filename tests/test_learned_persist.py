"""The hold trim and the learned sensor offsets survive a restart (1.8.2)."""

from datetime import timedelta
from itertools import pairwise

from custom_components.smart_climate import control
from tests.test_observe_log import (  # noqa: F401
    CV,
    QLIMA,
    _make,
    _restore_clock,
    _room,
)


def _stored(hass):
    """The ``learned`` record of every config-entry save, oldest first."""
    return [
        c.kwargs["data"]["learned"]
        for c in hass.config_entries.async_update_entry.call_args_list
        if "learned" in c.kwargs.get("data", {})
    ]


def _heating(states, temperature=21, own=23):
    states["climate.qlima"] = {"state": "heat", "attributes": {
        **QLIMA["attributes"], "temperature": temperature, "current_temperature": own, "fan_mode": "medium"}}


def test_restart_restores_trim_and_offset():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 20.5)
    entity, _hass, _clock = _make(states, learned={"trim": 3.0, "offset": {"climate.qlima": 5.7}})
    assert entity._trim == 3.0
    assert entity._offset == {"climate.qlima": 5.7}


def test_restore_ignores_rubbish_and_clamps_the_trim():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _room(states, 20.5)
    entity, _hass, _clock = _make(states, learned={"trim": 9, "offset": {"climate.qlima": "x", "climate.cv": -1}})
    assert entity._trim == control.TRIM_MAX
    assert entity._offset == {}
    entity, _hass, _clock = _make(states, learned={"trim": "?"})
    assert entity._trim == 0.0


async def test_trim_change_is_stored_at_once():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states)
    _room(states, 20.6)
    entity, hass, clock = _make(states, hold_primary=True)
    await entity._apply_control()
    clock["now"] += timedelta(minutes=31)
    await entity._apply_control()
    assert entity._trim == 1.0
    assert _stored(hass)[-1]["trim"] == 1.0


async def test_offset_is_stored_only_when_it_moved_enough():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, own=23)
    _room(states, 20.0)
    entity, hass, clock = _make(states, fan_boost=True, lead_max=0,   # no lead: only the offset saves
                                learned={"trim": 0.0, "offset": {"climate.qlima": 3.0}})
    await entity._apply_control()  # sample 3.0: nothing new
    assert _stored(hass) == []
    _heating(states, own=26)        # sample 6.0: the average creeps up 2% per tick
    for _ in range(5):
        clock["now"] += timedelta(seconds=10)
        await entity._apply_control()
    assert _stored(hass) == []      # still under LEARNED_OFFSET_STEP
    for _ in range(40):
        clock["now"] += timedelta(seconds=10)
        await entity._apply_control()
    offsets = [3.0] + [s["offset"]["climate.qlima"] for s in _stored(hass)]
    assert 2 <= len(offsets) <= 4   # a handful of saves in 45 ticks, not one per tick
    assert all(b - a >= 0.5 for a, b in pairwise(offsets))


# ---- warm-up lead (1.9.1) -----------------------------------------------------------

SCHEDULE = {"mode": "daily", "daily": [{"time": "00:00", "temp": 21.5}]}


async def test_lead_is_stored_when_it_changes_and_dropped_at_the_target():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, own=27)
    _room(states, 19.0)
    entity, hass, clock = _make(states, fan_boost=True, schedule=SCHEDULE,
                                learned={"trim": 0.0, "offset": {"climate.qlima": 7.5}})
    await entity._apply_control()
    assert entity._lead == {"climate.qlima": 6}
    assert _stored(hass)[-1]["lead"] == {"climate.qlima": 6}
    saves = len(_stored(hass))
    clock["now"] += timedelta(seconds=10)
    await entity._apply_control()
    assert len(_stored(hass)) == saves          # unchanged: no new save
    _room(states, 21.4)                          # within LEAD_OFF: lead back to 0
    clock["now"] += timedelta(seconds=10)
    await entity._apply_control()
    assert _stored(hass)[-1]["lead"] == {}


async def test_restart_keeps_the_lead_while_still_warming_up():
    # 26-11-2026: after the restart the Qlima got 22 instead of 28 with the room 0.6 under
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, own=29)
    _room(states, 20.9)
    entity, _hass, _clock = _make(states, fan_boost=True, quiet_hold=True, schedule=SCHEDULE,
                                  learned={"trim": 0.0, "offset": {"climate.qlima": 7.6},
                                           "lead": {"climate.qlima": 6}})
    assert entity._lead == {"climate.qlima": 6}
    await entity._apply_control()
    assert entity.extra_state_attributes["plan"][0]["temperature"] == 28


async def test_restored_lead_goes_when_no_longer_heating_and_ignores_rubbish():
    states = {"climate.qlima": QLIMA, "climate.cv": CV}
    _heating(states, own=29)
    _room(states, 22.5)                          # warm: not heating
    entity, hass, _clock = _make(states, fan_boost=True, schedule=SCHEDULE,
                                 learned={"lead": {"climate.qlima": 6, "climate.cv": "x", "climate.x": 99}})
    assert entity._lead == {"climate.qlima": 6}
    await entity._apply_control()
    assert entity._lead == {}
    assert _stored(hass)[-1]["lead"] == {}
