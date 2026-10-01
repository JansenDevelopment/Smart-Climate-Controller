"""Regression tests for the problems found in the independent review."""

import pathlib
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate import cooling
from custom_components.smart_climate.control import (
    HEAT,
    Decision,
    RoomTrend,
    plan_routes,
    support_needed,
)

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


def _make(entry_data=None, now=None, states=None, options=None):
    from custom_components.smart_climate import climate as climate_mod
    from custom_components.smart_climate.climate import SmartClimateEntity

    states = states if states is not None else {"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE}

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
    entry.data = {"devices": DEVICES, "auto_temperature": 21, "support_grace": 0, **(entry_data or {})}
    entity = SmartClimateEntity(
        hass=hass, entry=entry, name="T", wrapped_climate=None, zone_home="zone.home",
        away_temp=14.0, away_delay_minutes=0, interruptible=True,
        default_override_mode="timer", default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = "auto"
    entity._presence = "home"
    clock = {"now": now or datetime(2026, 1, 12, 7, 30).astimezone()}
    climate_mod.dt_util.now = lambda: clock["now"]
    return entity, hass, clock, states


def _hvac(hass):
    return {
        (c.args[2]["entity_id"], c.args[2]["hvac_mode"])
        for c in hass.services.async_call.call_args_list
        if c.args[0] == "climate" and c.args[1] == "set_hvac_mode"
    }


# ---------------------------------------------------------------- B1: time zones

async def test_naive_until_is_read_as_local_time_and_never_crashes_the_loop():
    entity, _, clock, _ = _make()
    await entity.async_set_device_mode("climate.cv", "off", until="2026-01-12 10:00:00")  # no offset
    stored = entity._device_modes["climate.cv"]["until"]
    assert datetime.fromisoformat(stored).tzinfo is not None
    # evaluating with the aware "now" must work, before and after the end time
    assert entity._effective_device_mode("climate.cv", clock["now"]) == "off"
    later = clock["now"] + timedelta(hours=3)
    assert entity._effective_device_mode("climate.cv", later) == "auto"
    await entity._apply_control()
    assert "device_modes" in entity.extra_state_attributes


async def test_an_unreadable_stored_end_time_counts_as_expired():
    entity, _, clock, _ = _make(entry_data={"device_modes": {"climate.cv": {"mode": "off", "until": "garbage"}}})
    assert entity._effective_device_mode("climate.cv", clock["now"]) == "auto"
    entity._expire_device_modes(clock["now"])  # must not raise
    assert "climate.cv" not in entity._device_modes


# ---------------------------------------------------------------- B2/R3: trend

def test_trend_is_measured_from_when_heating_started():
    t0 = datetime(2026, 1, 12, 17, 0)
    tr = RoomTrend(window_minutes=30)
    for i in range(0, 15):  # flat for 15 min before heating starts
        tr.record(t0 + timedelta(minutes=i), 17.0)
    for i in range(15, 31):  # then a steady +0.6 K/h
        tr.record(t0 + timedelta(minutes=i), 17.0 + (i - 15) * 0.01)
    window_rate = tr.rise_per_hour()
    since_rate = tr.rise_per_hour(since=t0 + timedelta(minutes=15), min_span_minutes=10)
    assert window_rate < 0.3  # the old behaviour: diluted by the flat period -> "not warming"
    assert since_rate > 0.5   # measured from the start of heating: clearly warming
    assert support_needed(18.0, 20, 1.5, False, heating_minutes=16, rise_per_hour=since_rate,
                          grace_minutes=15, min_rise=0.3) is False


def test_trend_needs_enough_samples_since_the_start():
    t0 = datetime(2026, 1, 12, 17, 0)
    tr = RoomTrend()
    tr.record(t0, 17.0)
    tr.record(t0 + timedelta(minutes=5), 17.1)
    assert tr.rise_per_hour(since=t0, min_span_minutes=10) is None


# ---------------------------------------------------------------- B3: external change

async def _settled_entity(**kw):
    entity, hass, clock, states = _make(**kw)
    await entity._apply_control()  # the coordinator asks the airco to heat
    assert ("climate.airco", "heat") in _hvac(hass)
    states["climate.airco"] = {"state": "heat", "attributes": {
        **AIRCO_STATE["attributes"], "temperature": 21}}
    return entity, hass, clock, states


def _event(entity_id, state, temperature=None):
    new = MagicMock()
    new.state = state
    new.attributes = {"temperature": temperature} if temperature is not None else {}
    ev = MagicMock()
    ev.data = {"entity_id": entity_id, "new_state": new}
    return ev


async def test_a_change_made_outside_the_coordinator_turns_the_device_manual():
    entity, hass, clock, _ = await _settled_entity()
    clock["now"] += timedelta(minutes=2)
    await entity._on_watched_change(_event("climate.airco", "off"))  # user switched it off by remote
    entry = entity._device_modes["climate.airco"]
    assert entry["mode"] == "manual" and entry["source"] == "external"
    assert entry["until"] is not None  # default override mode is "timer": 30 min
    hass.services.async_call.reset_mock()
    await entity._apply_control()
    assert all(eid != "climate.airco" for eid, _mode in _hvac(hass))  # and it is left alone


async def test_a_clearly_different_target_also_counts():
    entity, _, clock, _ = await _settled_entity()
    clock["now"] += timedelta(minutes=2)
    await entity._on_watched_change(_event("climate.airco", "heat", temperature=24))
    assert entity._device_modes["climate.airco"]["source"] == "external"


async def test_the_devices_own_reply_to_our_command_is_not_an_external_change():
    entity, _, clock, _ = await _settled_entity()
    clock["now"] += timedelta(seconds=5)  # inside the settle window
    await entity._on_watched_change(_event("climate.airco", "off"))
    assert "climate.airco" not in entity._device_modes
    await entity._on_watched_change(_event("climate.airco", "heat", temperature=21))
    assert "climate.airco" not in entity._device_modes


async def test_external_takeover_can_be_switched_off():
    entity, _, clock, _ = await _settled_entity(entry_data={"external_takeover": False})
    clock["now"] += timedelta(minutes=2)
    await entity._on_watched_change(_event("climate.airco", "off"))
    assert "climate.airco" not in entity._device_modes


async def test_a_device_the_user_already_set_is_not_touched_again():
    entity, _, clock, _ = await _settled_entity()
    await entity.async_set_device_mode("climate.airco", "off")
    clock["now"] += timedelta(minutes=2)
    await entity._on_watched_change(_event("climate.airco", "heat"))
    assert entity._device_modes["climate.airco"]["source"] == "user"


# ---------------------------------------------------------------- B4 / R5: pause

async def test_pause_reports_its_kind():
    entity, _, _, _ = _make(now=datetime(2026, 1, 12, 7, 30).astimezone())
    await entity.async_set_support_pause(True, until_morning=True)
    assert entity.extra_state_attributes["support_pause_kind"] == "until_morning"
    await entity.async_set_support_pause(True, minutes=30)
    assert entity.extra_state_attributes["support_pause_kind"] == "minutes"
    await entity.async_set_support_pause(True)
    assert entity.extra_state_attributes["support_pause_kind"] == "open"
    await entity.async_set_support_pause(False)
    assert entity.extra_state_attributes["support_pause_kind"] is None


async def test_resuming_never_removes_a_choice_the_user_made_by_hand():
    entity, _, _, _ = _make()
    await entity.async_set_device_mode("climate.cv", "off")  # user: permanently off
    await entity.async_set_support_pause(True, minutes=30)
    assert entity._device_modes["climate.cv"]["source"] == "user"  # the pause did not overwrite it
    assert entity._support_paused_until() is None  # and it does not count as a pause
    await entity.async_set_support_pause(False)
    assert entity._device_modes["climate.cv"]["mode"] == "off"


async def test_pause_does_not_override_a_manual_device():
    entity, _, _, _ = _make()
    await entity.async_set_device_mode("climate.cv", "manual")
    await entity.async_set_support_pause(True, until_morning=True)
    assert entity._device_modes["climate.cv"]["mode"] == "manual"


# ---------------------------------------------------------------- B5: forecast days

def test_forecast_days_are_read_in_local_time():
    local = timezone(timedelta(hours=2))
    forecast = [
        {"datetime": "2026-10-01T22:00:00+00:00", "temperature": 17.0},   # = 2 Oct, 00:00 local
        {"datetime": "2026-10-02T22:00:00+00:00", "temperature": 19.0},   # = 3 Oct local
    ]
    to_local = lambda d: d.astimezone(local)  # noqa: E731
    from datetime import date

    # without conversion the UTC date is used (the old, wrong reading) ...
    assert cooling.parse_daily_highs(forecast, date(2026, 10, 2)) == (19.0, None)
    # ... with conversion "today" (2 Oct) is the first entry and tomorrow the second
    assert cooling.parse_daily_highs(forecast, date(2026, 10, 2), to_local=to_local) == (17.0, 19.0)


# ---------------------------------------------------------------- R1 .. R13

async def test_a_short_unavailable_blip_does_not_make_the_cv_the_main_heater():
    entity, hass, clock, states = _make(entry_data={"support_grace": 15})
    states["climate.airco"] = {"state": "unavailable", "attributes": {}}
    await entity._apply_control()
    assert ("climate.cv", "heat") not in _hvac(hass)  # still within the debounce window
    clock["now"] += timedelta(minutes=6)
    await entity._apply_control()
    assert ("climate.cv", "heat") in _hvac(hass)  # really gone: the CV takes over


def test_a_hand_operated_airco_that_is_heating_keeps_the_cv_as_support_only():
    airco = {"entity_id": "airco", "role": "both", "tier": "primary", "park": "off",
             "control": "manual", "heating": True}
    cv = {"entity_id": "cv", "role": "heat", "tier": "support", "park": "off"}
    modes = {c.entity_id: c.hvac_mode for c in plan_routes(Decision(HEAT, 21), [airco, cv])}
    assert modes == {"cv": "off"}  # airco untouched (no command), CV not brought in on its own
    modes = {c.entity_id: c.hvac_mode for c in plan_routes(Decision(HEAT, 21), [airco, cv], support_active=True)}
    assert modes == {"cv": "heat"}
    idle = {**airco, "heating": False}
    modes = {c.entity_id: c.hvac_mode for c in plan_routes(Decision(HEAT, 21), [idle, cv])}
    assert modes == {"cv": "heat"}  # airco is off by hand: the CV heats


async def test_tomorrows_forecast_only_counts_in_the_evening():
    entity, _, clock, _ = _make()
    entity._forecast_highs = (15.0, 28.0)
    clock["now"] = datetime(2026, 6, 1, 14, 0).astimezone()
    assert 28.0 not in entity._cooling_highs(clock["now"])
    clock["now"] = datetime(2026, 6, 1, 19, 0).astimezone()
    assert 28.0 in entity._cooling_highs(clock["now"])


async def test_a_failed_forecast_fetch_is_retried_after_two_minutes():
    entity, hass, clock, _ = _make(entry_data={"weather_entity": "weather.home"})
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("not ready"))
    await entity._refresh_outdoor(clock["now"])
    assert hass.services.async_call.await_count == 1
    await entity._refresh_outdoor(clock["now"] + timedelta(minutes=1))
    assert hass.services.async_call.await_count == 1  # throttled
    await entity._refresh_outdoor(clock["now"] + timedelta(minutes=3))
    assert hass.services.async_call.await_count == 2  # retried well before 30 minutes


async def test_the_24h_outdoor_maximum_survives_a_restart():
    now = datetime(2026, 7, 1, 20, 0).astimezone()
    cached = {"value": 29.0, "at": (now - timedelta(hours=3)).isoformat()}
    entity, _, clock, _ = _make(entry_data={"outdoor_max_cache": cached}, now=now)
    assert entity._outdoor_tracker.max_24h(now) == 29.0


async def test_hvac_action_is_idle_when_no_device_is_allowed_to_act():
    entity, _, _, _ = _make()
    await entity.async_set_device_mode("climate.airco", "manual")
    await entity.async_set_device_mode("climate.cv", "manual")
    await entity._apply_control()
    assert entity._intent == HEAT
    assert entity.hvac_action == "idle"


async def test_attributes_describe_the_room_temperature_source_and_takeover():
    entity, _, _, _ = _make(entry_data={"temperature_source": "sensor", "temperature_sensor": "sensor.room"},
                            states={"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE,
                                    "sensor.room": {"state": "21.5", "attributes": {}}})
    attrs = entity.extra_state_attributes
    assert attrs["room_temperature_source"] == {"kind": "sensor", "entity": "sensor.room"}
    assert attrs["external_takeover"] is True
    assert entity.extra_state_attributes["device_modes"]["climate.airco"]["source"] == "user"
