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
    entity, hass, clock = _make(states, fan_boost=True, learned={"trim": 0.0, "offset": {"climate.qlima": 3.0}})
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
