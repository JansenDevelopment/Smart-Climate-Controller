"""26-11-2026: a defrost dip is not a stall, high fan in the cold, max lead as an option.

Qlima at 0 deg outside: a defrost took the room 20.5 -> 19.7 and latched the CV on; the
fan boost stepped to medium at 0.7 under and the room fell 20.8 -> 20.3; the sensor
offset was 7-8 with the lead capped at 6.
"""

from datetime import datetime, timedelta

from custom_components.smart_climate import control
from tests.test_observe_log import (  # noqa: F401
    CV,
    QLIMA,
    _calls,
    _make,
    _restore_clock,
    _room,
)

SCHEDULE = {"mode": "daily", "daily": [
    {"time": "07:00", "temp": 21.5}, {"time": "23:30", "temp": 11.5}]}
FANS = QLIMA["attributes"]["fan_modes"]


# ---- control ------------------------------------------------------------------------

def test_cold_keeps_the_fan_high_until_close_to_the_target():
    cold = control.BOOST_AUTO
    assert control.fan_for(20.8, 21.5, None, None, FANS) == "medium"                    # mild: medium at 0.7
    assert control.fan_for(20.8, 21.5, None, None, FANS, high_above=cold) == "high"     # cold: high
    # down from high only past the backoff and after the hold time
    assert control.fan_for(21.35, 21.5, "high", 15, FANS, high_above=cold) == "high"    # 0.15 under
    assert control.fan_for(21.45, 21.5, "high", 5, FANS, high_above=cold) == "high"     # too soon
    assert control.fan_for(21.45, 21.5, "high", 15, FANS, high_above=cold) == "auto"
    assert control.fan_for(21.45, 21.5, "high", 15, FANS, quiet=True, high_above=cold) == "medium"


def test_lead_max_caps_the_lead():
    assert control.setpoint_lead(18.0, 21.5, 0, 9.4) == control.LEAD_MAX == 6
    assert control.setpoint_lead(18.0, 21.5, 0, 9.4, lead_max=4) == 4
    assert control.setpoint_lead(18.0, 21.5, 0, 9.4, lead_max=8) == 8
    assert control.setpoint_lead(18.0, 21.5, 0, 9.4, lead_max=0) == 0
    assert control.setpoint_lead(18.0, 21.5, 6, 9.4, lead_max=4) == 4    # cap lowered while warming
    assert control.setpoint_lead(18.0, 21.5, 4, 9.4, lead_max=4) == 4


# ---- entity -------------------------------------------------------------------------

def _qlima(own):
    return {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 28, "current_temperature": own}}


# 26-11-2026 as measured (local time): room sensor (tado) and the Qlima's own sensor.
ROOM_26_11 = [
    ("09:00", 18.3), ("09:02", 18.6), ("09:04", 18.7), ("09:06", 18.8), ("09:10", 19.0), ("09:14", 19.1),
    ("09:17", 19.2), ("09:21", 19.3), ("09:29", 19.5), ("09:33", 19.6), ("09:38", 19.7), ("09:43", 19.8),
    ("09:52", 19.9), ("09:57", 20.1), ("10:06", 20.2), ("10:09", 20.3), ("10:20", 20.4), ("10:24", 20.5),
    ("10:32", 20.6), ("10:37", 20.8), ("10:40", 20.6), ("10:41", 20.5), ("10:43", 20.3), ("10:50", 20.5),
    ("10:55", 20.3), ("10:56", 20.1), ("10:57", 19.9), ("10:58", 19.8), ("10:59", 19.7), ("11:03", 19.9),
    ("11:04", 20.0), ("11:05", 20.1), ("11:07", 20.3), ("11:09", 20.4), ("11:11", 20.6), ("11:15", 20.7),
]
OWN_26_11 = [
    ("09:00", 25), ("09:10", 27), ("09:39", 28), ("10:38", 29), ("10:40", 30), ("10:43", 29), ("10:45", 28),
    ("10:52", 26), ("10:53", 23), ("10:54", 19), ("10:55", 16), ("10:56", 15), ("10:57", 14), ("10:58", 17),
    ("10:59", 19), ("11:00", 21), ("11:01", 23), ("11:02", 25), ("11:03", 26), ("11:05", 27), ("11:07", 28),
]


def _at(series, hhmm):
    value = series[0][1]
    for t, v in series:
        if t <= hhmm:
            value = v
    return value


async def _morning(real_own_sensor):
    """Replay 09:00-11:40 on 26-11; the time the CV joined (None = never) and the entity.

    ``real_own_sensor`` False: the Qlima's own sensor never shows the defrost (as if the
    coordinator could not tell), so the dip reads as a stall.
    """
    states = {"climate.qlima": _qlima(25), "climate.cv": CV}
    _room(states, 18.3)
    entity, _hass, clock = _make(states, schedule=SCHEDULE, fan_boost=True,
                                support_enabled=True, support_grace=15)
    t0 = datetime(2026, 11, 26, 9, 0).astimezone()
    for minute in range(161):
        clock["now"] = t0 + timedelta(minutes=minute)
        hhmm = clock["now"].strftime("%H:%M")
        _room(states, _at(ROOM_26_11, hhmm))
        states["climate.qlima"] = _qlima(_at(OWN_26_11, hhmm) if real_own_sensor else 28)
        await entity._apply_control()
        if entity._support_active:
            return hhmm, entity
    return None, entity


async def test_the_dip_of_26_11_read_as_a_stall_joins_the_cv():
    joined, _ = await _morning(real_own_sensor=False)
    assert joined is not None and "10:58" <= joined <= "11:05"     # live: 11:03


async def test_the_defrost_of_26_11_keeps_the_cv_out():
    joined, entity = await _morning(real_own_sensor=True)
    assert joined is None
    assert entity._defrosts["climate.qlima"] == 1


async def test_a_real_stall_after_a_defrost_still_gets_support():
    states = {"climate.qlima": _qlima(27), "climate.cv": CV}
    _room(states, 19.5)
    entity, _hass, clock = _make(states, schedule=SCHEDULE, fan_boost=True,
                                support_enabled=True, support_grace=15)
    t0 = datetime(2026, 11, 26, 9, 0).astimezone()
    joined = None
    for minute in range(121):          # heating for an hour already, room flat at 19.5
        clock["now"] = t0 + timedelta(minutes=minute)
        states["climate.qlima"] = _qlima(14 if 60 <= minute < 65 else 27)
        if minute < 60:
            entity._support_active = False   # only judge from the defrost on
            entity._slow_since = None
        await entity._apply_control()
        if minute >= 60 and entity._support_active:
            joined = minute
            break
    # defrost ends at 65, settles 10 min, then the 20-minute stall counts afresh
    assert joined is not None
    assert joined >= 65 + control.DEFROST_SETTLE_MINUTES + control.SUPPORT_SLOW_MINUTES


async def test_support_already_on_stays_on_during_a_defrost():
    states = {"climate.qlima": _qlima(27), "climate.cv": CV}
    _room(states, 19.0)
    entity, _hass, clock = _make(states, schedule=SCHEDULE, fan_boost=True,
                                support_enabled=True, support_grace=15)
    clock["now"] = datetime(2026, 11, 26, 9, 0).astimezone()
    entity._support_active = True
    states["climate.qlima"] = _qlima(14)
    await entity._apply_control()
    assert entity._defrosting["climate.qlima"] is True
    assert entity._support_active is True


async def test_outdoor_cold_runs_the_fan_high_at_0_7_under():
    for outdoor, fan in ((0.0, "high"), (8.0, "medium"), (None, "medium")):
        states = {"climate.qlima": _qlima(27), "climate.cv": CV}
        _room(states, 20.8)
        extra = {}
        if outdoor is not None:
            states["sensor.out"] = {"state": str(outdoor), "attributes": {}}
            extra["outdoor_sensor"] = "sensor.out"
        entity, _hass, clock = _make(states, schedule=SCHEDULE, fan_boost=True, **extra)
        clock["now"] = datetime(2026, 11, 26, 10, 37).astimezone()
        await entity._apply_control()
        assert entity.extra_state_attributes["plan"][0]["fan_mode"] == fan, outdoor


async def test_lead_max_option_reaches_the_setpoint():
    for lead_max, setpoint in ((None, 28), (4, 26), (0, 22)):
        states = {"climate.qlima": _qlima(27), "climate.cv": CV}
        _room(states, 18.5)
        extra = {} if lead_max is None else {"lead_max": lead_max}
        entity, _hass, clock = _make(states, schedule=SCHEDULE, fan_boost=True, learned={
            "offset": {"climate.qlima": 7.5}}, **extra)
        clock["now"] = datetime(2026, 11, 26, 9, 0).astimezone()
        await entity._apply_control()
        assert entity.extra_state_attributes["plan"][0]["temperature"] == setpoint, lead_max
