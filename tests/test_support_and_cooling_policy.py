"""Heat support (primary + support tiers), the auto-cooling policy and the
fixes around them: heat-only devices never get a cool command, service
failures never abort the control loop, and the schedule is exposed."""

import itertools
import pathlib
import sys
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate import cooling
from custom_components.smart_climate.control import (
    COOL,
    HEAT,
    IDLE,
    OFF,
    Decision,
    decide,
    plan_routes,
    RoomTrend,
    support_needed,
)


def _dev(entity_id, role="both", tier="primary", park="off", **extra):
    return {"entity_id": entity_id, "role": role, "tier": tier, "park": park, **extra}


def _modes(cmds):
    return {c.entity_id: c.hvac_mode for c in cmds}


# ---------------------------------------------------------------------------
# decide(): the loose regulation
# ---------------------------------------------------------------------------

def test_cooling_not_allowed_means_overshoot_idles():
    # Heating overshoot in winter: 26 °C with a 24 cool limit must NOT cool.
    d = decide(mode="auto", room_temp=26, heat_target=21, cool_target=24,
               cooling_allowed=False)
    assert d.intent == IDLE


def test_cooling_allowed_cools_above_the_limit():
    d = decide(mode="auto", room_temp=26, heat_target=21, cool_target=24,
               cooling_allowed=True)
    assert d.intent == COOL


def test_explicit_cool_mode_ignores_the_policy_gate():
    d = decide(mode="cool", room_temp=20, heat_target=21, cool_target=24,
               cooling_allowed=False)
    assert d.intent == COOL


def test_gate_closing_stops_a_running_cool_cycle():
    d = decide(mode="auto", room_temp=25, heat_target=21, cool_target=24,
               prev_intent=COOL, cooling_allowed=False)
    assert d.intent == IDLE


def test_heating_is_not_affected_by_the_cooling_gate():
    d = decide(mode="auto", room_temp=18, heat_target=21, cool_target=24,
               cooling_allowed=False)
    assert d.intent == HEAT


def test_default_hysteresis_is_loose():
    # Heating keeps going until target + 0.5 (not +0.3).
    d = decide(mode="auto", room_temp=21.4, heat_target=21, cool_target=25,
               prev_intent=HEAT)
    assert d.intent == HEAT
    d2 = decide(mode="auto", room_temp=21.6, heat_target=21, cool_target=25,
                prev_intent=HEAT)
    assert d2.intent == IDLE


def test_band_gap_is_at_least_three_degrees():
    # heat 21 / cool 22 would cool right after a small overshoot — clamped to 24.
    d = decide(mode="auto", room_temp=23, heat_target=21, cool_target=22,
               cooling_allowed=True)
    assert d.intent == IDLE


# ---------------------------------------------------------------------------
# support_needed()
# ---------------------------------------------------------------------------

def test_support_joins_when_deficit_reaches_delta():
    assert support_needed(19.4, 21, 1.5, False) is True
    assert support_needed(19.6, 21, 1.5, False) is False


def test_support_stays_until_deficit_is_under_half_delta():
    assert support_needed(20.0, 21, 1.5, True) is True    # deficit 1.0 > 0.75
    assert support_needed(20.3, 21, 1.5, True) is False   # deficit 0.7


def test_support_keeps_state_without_a_room_temperature():
    assert support_needed(None, 21, 1.5, True) is True
    assert support_needed(None, 21, 1.5, False) is False


# ---------------------------------------------------------------------------
# plan_routes(): tiers, parking, capabilities
# ---------------------------------------------------------------------------

AIRCO = _dev("climate.airco", "both", "primary", "off", supports_fan_only=True, step=1)
CV = _dev("climate.cv", "heat", "support", "off", can_cool=False)


def test_primary_heats_alone_without_support():
    cmds = plan_routes(Decision(HEAT, 21), [AIRCO, CV], support_active=False)
    assert _modes(cmds) == {"climate.airco": "heat", "climate.cv": "off"}


def test_support_joins_when_active():
    cmds = plan_routes(Decision(HEAT, 21), [AIRCO, CV], support_active=True)
    assert _modes(cmds) == {"climate.airco": "heat", "climate.cv": "heat"}


def test_support_heats_when_the_primary_is_unavailable():
    airco = {**AIRCO, "available": False}
    cmds = plan_routes(Decision(HEAT, 21), [airco, CV], support_active=False)
    assert _modes(cmds)["climate.cv"] == "heat"


def test_support_heats_when_the_primary_cannot_heat():
    airco = {**AIRCO, "can_heat": False}
    cmds = plan_routes(Decision(HEAT, 21), [airco, CV], support_active=False)
    assert _modes(cmds)["climate.cv"] == "heat"


def test_cooling_goes_to_the_airco_only():
    cmds = plan_routes(Decision(COOL, 24), [AIRCO, CV])
    assert _modes(cmds) == {"climate.airco": "cool", "climate.cv": "off"}


def test_heat_only_device_never_gets_a_cool_command_even_with_role_both():
    # Regression: a heat-only wrapped climate (HomeKit off/heat) migrated as
    # role "both" used to be sent `cool`, which the device rejects.
    heat_only = _dev("climate.hk", "both", can_cool=False)
    cmds = plan_routes(Decision(COOL, 24), [heat_only])
    assert _modes(cmds) == {"climate.hk": "off"}


def test_airco_parks_off_when_idle():
    cmds = plan_routes(Decision(IDLE, None), [AIRCO, CV])
    assert set(_modes(cmds).values()) == {"off"}


def test_airco_parks_on_fan_only_when_asked_and_supported():
    airco = {**AIRCO, "park": "fan_only"}
    cmds = plan_routes(Decision(IDLE, None), [airco])
    assert _modes(cmds) == {"climate.airco": "fan_only"}
    # ... but never fan_only for a device that does not support it
    no_fan = {**AIRCO, "park": "fan_only", "supports_fan_only": False}
    assert _modes(plan_routes(Decision(IDLE, None), [no_fan])) == {"climate.airco": "off"}


def test_setpoint_is_rounded_to_the_device_step():
    # The airco only does whole degrees.
    cmds = plan_routes(Decision(HEAT, 20.5), [AIRCO])
    assert cmds[0].temperature == 21
    cmds = plan_routes(Decision(HEAT, 20.4), [AIRCO])
    assert cmds[0].temperature == 20
    # A 0.5 step keeps half degrees.
    cv = {**CV, "step": 0.5}
    assert plan_routes(Decision(HEAT, 20.5), [cv], support_active=True)[0].temperature == 20.5


def test_off_decision_powers_everything_off():
    assert set(_modes(plan_routes(Decision(OFF, None), [AIRCO, CV])).values()) == {"off"}


def test_never_heats_and_cools_simultaneously_with_tiers():
    devices = [AIRCO, CV, _dev("climate.x", "cool", can_heat=False)]
    rooms = [5, 15, 20, 21, 23, 25, 27, 35]
    bands = [(21, 24), (25, 22), (20, 20), (18, 30)]
    for room, (h, c), mode, prev, gate, sup in itertools.product(
        rooms, bands, ["auto", "heat", "cool", "off"], [None, HEAT, COOL, IDLE],
        [True, False], [True, False],
    ):
        d = decide(mode=mode, room_temp=room, heat_target=h, cool_target=c,
                   prev_intent=prev, cooling_allowed=gate)
        actions = set(_modes(plan_routes(d, devices, support_active=sup)).values())
        assert not ("heat" in actions and "cool" in actions)
        assert actions <= {"off", "heat", "cool", "fan_only"}


# ---------------------------------------------------------------------------
# cooling.py
# ---------------------------------------------------------------------------

def test_off_and_on_settings_are_absolute():
    kw = {"highs": [30], "warm_threshold": 22, "hard_ceiling": 26}
    assert cooling.cooling_permitted("off", 30, **kw) is False
    assert cooling.cooling_permitted("on", 10, highs=[], warm_threshold=22, hard_ceiling=26) is True


def test_auto_allows_cooling_after_a_warm_day_even_when_it_is_cool_outside_now():
    # Evening: 25 °C inside, 16 °C outside, but 27 °C was measured today.
    assert cooling.cooling_permitted(
        "auto", 25, highs=[None, None, 27.0], warm_threshold=22, hard_ceiling=26
    ) is True


def test_auto_uses_the_forecast_too():
    assert cooling.cooling_permitted(
        "auto", 24.5, highs=[23.0, None, None], warm_threshold=22, hard_ceiling=26
    ) is True


def test_auto_never_cools_from_heating_overshoot_in_winter():
    assert cooling.cooling_permitted(
        "auto", 24.5, highs=[6.0, 5.0, 4.0], warm_threshold=22, hard_ceiling=26
    ) is False


def test_auto_cools_above_the_hard_ceiling_regardless():
    assert cooling.cooling_permitted(
        "auto", 26.5, highs=[5.0], warm_threshold=22, hard_ceiling=26
    ) is True


def test_auto_with_no_data_does_nothing_below_the_ceiling():
    assert cooling.cooling_permitted(
        "auto", 25, highs=[None, None], warm_threshold=22, hard_ceiling=26
    ) is False


def test_unknown_setting_is_treated_as_off():
    assert cooling.cooling_permitted(
        "banana", 30, highs=[30], warm_threshold=22, hard_ceiling=26
    ) is False


def test_parse_daily_highs():
    forecast = [
        {"datetime": "2026-10-01T00:00:00+00:00", "temperature": 19.6},
        {"datetime": "2026-10-02T00:00:00+00:00", "temperature": 20.0},
        {"datetime": "garbage", "temperature": 99},
        {"datetime": "2026-10-03T00:00:00+00:00"},
    ]
    assert cooling.parse_daily_highs(forecast, date(2026, 10, 1)) == (19.6, 20.0)
    assert cooling.parse_daily_highs(forecast, date(2026, 10, 2)) == (20.0, None)
    assert cooling.parse_daily_highs(None, date(2026, 10, 1)) == (None, None)


def test_outdoor_tracker_keeps_a_24h_window():
    t0 = datetime(2026, 7, 1, 12, 0)
    tr = cooling.OutdoorMaxTracker()
    assert tr.max_24h(t0) is None
    tr.record(t0, 28.0)
    tr.record(t0 + timedelta(hours=6), 22.0)
    tr.record(t0 + timedelta(hours=7), None)  # ignored
    assert tr.max_24h(t0 + timedelta(hours=8)) == 28.0
    # After 24 h the 28 °C sample has dropped out of the window.
    assert tr.max_24h(t0 + timedelta(hours=25)) == 22.0


# ---------------------------------------------------------------------------
# Entity level
# ---------------------------------------------------------------------------

def _make(hvac_mode="auto", devices=None, states=None, entry_data=None, presence="home"):
    from custom_components.smart_climate.climate import SmartClimateEntity

    states = states or {}

    def _get(eid):
        if eid not in states:
            return None
        st = MagicMock()
        st.state = states[eid].get("state", "off")
        st.attributes = states[eid].get("attributes", {})
        return st

    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states.get = MagicMock(side_effect=_get)
    hass.config_entries.async_update_entry = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e"
    entry.data = dict(entry_data or {})
    if devices:
        entry.data["devices"] = devices
    entity = SmartClimateEntity(
        hass=hass, entry=entry, name="T", wrapped_climate=None, zone_home="zone.home",
        away_temp=14.0, away_delay_minutes=0, interruptible=True,
        default_override_mode="timer", default_override_duration=30,
    )
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = hvac_mode
    entity._presence = presence
    return entity, hass


def _calls(hass, service):
    return [c.args[2] for c in hass.services.async_call.call_args_list
            if c.args[0] == "climate" and c.args[1] == service]


HEAT_ONLY_STATES = {"climate.hk": {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat"], "current_temperature": 22.8}}}


async def test_override_below_room_temperature_does_not_send_cool_to_a_heat_only_device():
    # Regression for the live bug: override 21 with the room at 22.8 used to
    # produce `set_hvac_mode cool` on a device that only does off/heat.
    entity, hass = _make(hvac_mode="heat", devices=[{"entity_id": "climate.hk", "role": "both"}],
                         states=HEAT_ONLY_STATES)
    await entity.async_set_override_infinity(21)
    assert "cool" not in [c["hvac_mode"] for c in _calls(hass, "set_hvac_mode")]


async def test_auto_above_the_cool_limit_never_sends_cool_to_a_heat_only_device():
    states = {"climate.hk": {"state": "off", "attributes": {
        "hvac_modes": ["off", "heat"], "current_temperature": 27.0}}}
    entity, hass = _make(devices=[{"entity_id": "climate.hk", "role": "both"}], states=states,
                         entry_data={"cooling_mode": "on"})
    await entity._apply_control()
    assert "cool" not in [c["hvac_mode"] for c in _calls(hass, "set_hvac_mode")]


async def test_a_failing_service_call_does_not_abort_the_loop():
    states = {
        "climate.a": {"state": "off", "attributes": {"hvac_modes": ["off", "heat"], "current_temperature": 15}},
        "climate.b": {"state": "off", "attributes": {"hvac_modes": ["off", "heat"], "current_temperature": 15}},
    }
    entity, hass = _make(devices=[{"entity_id": "climate.a", "role": "heat"},
                                  {"entity_id": "climate.b", "role": "heat"}], states=states)
    hass.services.async_call = AsyncMock(side_effect=[RuntimeError("boom"), None, None, None])
    await entity._apply_control()  # must not raise
    assert hass.services.async_call.await_count >= 2  # b was still driven


async def test_unavailable_device_is_skipped():
    states = {"climate.a": {"state": "unavailable", "attributes": {}}}
    entity, hass = _make(devices=[{"entity_id": "climate.a", "role": "both"}], states=states)
    await entity._apply_control()
    assert hass.services.async_call.await_count == 0


AIRCO_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat", "cool", "fan_only"], "target_temp_step": 1, "current_temperature": 18}}
CV_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "current_temperature": 18}}
TWO_DEVICES = [
    {"entity_id": "climate.airco", "role": "both", "tier": "primary", "park": "off"},
    {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"},
]


async def test_airco_heats_alone_for_a_small_deficit():
    states = {"climate.airco": {**AIRCO_STATE, "attributes": {**AIRCO_STATE["attributes"], "current_temperature": 20.5}},
              "climate.cv": {**CV_STATE, "attributes": {**CV_STATE["attributes"], "current_temperature": 20.5}}}
    entity, hass = _make(devices=TWO_DEVICES, states=states, entry_data={"auto_temperature": 21})
    await entity._apply_control()
    assert entity._support_active is False
    assert {(c["entity_id"], c["hvac_mode"]) for c in _calls(hass, "set_hvac_mode")} == {("climate.airco", "heat")}


async def test_cv_joins_for_a_big_deficit_and_can_be_switched_off():
    entity, hass = _make(devices=TWO_DEVICES,
                         states={"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE},
                         entry_data={"auto_temperature": 21, "support_grace": 0})
    await entity._apply_control()
    assert entity._support_active is True
    assert {c["entity_id"] for c in _calls(hass, "set_hvac_mode")} == {"climate.airco", "climate.cv"}

    entity2, hass2 = _make(devices=TWO_DEVICES,
                           states={"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE},
                           entry_data={"auto_temperature": 21, "support_grace": 0, "support_enabled": False})
    await entity2._apply_control()
    assert entity2._support_active is False
    assert {c["entity_id"] for c in _calls(hass2, "set_hvac_mode")} == {"climate.airco"}


async def test_setters_validate_and_persist():
    entity, hass = _make(devices=[{"entity_id": "climate.hk", "role": "both"}], states=HEAT_ONLY_STATES)
    await entity.async_set_cooling_mode("banana")
    assert entity._cooling_mode == "auto"  # unchanged
    await entity.async_set_cooling_mode("off")
    assert entity._cooling_mode == "off"
    await entity.async_set_heat_support(False)
    assert entity._support_enabled is False
    persisted = {}
    for call in hass.config_entries.async_update_entry.call_args_list:
        persisted.update(call.kwargs["data"])
    assert persisted["cooling_mode"] == "off" and persisted["support_enabled"] is False


def test_schedule_and_policy_are_exposed_as_attributes():
    entity, _ = _make(entry_data={"schedule": {"mode": "5/2", "weekday": [{"time": "07:00", "temp": 20}]}})
    attrs = entity.extra_state_attributes
    assert attrs["schedule"]["mode"] == "5/2"
    for key in ("cooling_mode", "cooling_allowed", "support_enabled", "support_active",
                "warm_threshold", "hard_ceiling", "forecast_high_today", "outdoor_max_24h"):
        assert key in attrs


async def test_forecast_is_fetched_and_throttled():
    entity, hass = _make(entry_data={"weather_entity": "weather.home"},
                         states={"weather.home": {"state": "cloudy", "attributes": {"temperature": 17.8}}})
    now = datetime.now().astimezone()
    forecast = {"weather.home": {"forecast": [
        {"datetime": now.date().isoformat() + "T00:00:00", "temperature": 24.0},
        {"datetime": (now.date() + timedelta(days=1)).isoformat() + "T00:00:00", "temperature": 19.0},
    ]}}
    hass.services.async_call = AsyncMock(return_value=forecast)
    await entity._refresh_outdoor(now)
    await entity._refresh_outdoor(now + timedelta(minutes=5))  # throttled
    assert hass.services.async_call.await_count == 1
    assert entity._forecast_highs == (24.0, 19.0)
    assert entity._outdoor_tracker.max_24h(now) == 17.8


async def test_forecast_failure_never_breaks_control():
    entity, hass = _make(entry_data={"weather_entity": "weather.home"})
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("weather down"))
    await entity._refresh_outdoor(datetime.now().astimezone())  # must not raise
    assert entity._forecast_highs == (None, None)


# ---------------------------------------------------------------------------
# Support: grace period + trend (a steady warm-up does not need the CV)
# ---------------------------------------------------------------------------

def _joins(heating_min, rise, room=18.0, **kw):
    return support_needed(room, 20, 1.5, False, heating_minutes=heating_min,
                          rise_per_hour=rise, grace_minutes=30, min_rise=0.3, **kw)


def test_support_waits_for_the_grace_period():
    assert _joins(10, 0.0) is False
    assert _joins(None, 0.0) is False
    assert _joins(31, 0.0) is True


def test_support_does_not_join_while_the_room_is_warming_steadily():
    # e.g. warming up after arriving home with the airco alone: 0.8 °C/h
    assert _joins(45, 0.8) is False
    # ... but joins when the room is flat or falling, i.e. the airco cannot keep up
    assert _joins(45, 0.1) is True
    assert _joins(45, -0.4) is True


def test_support_waits_longer_without_trend_data():
    # No trend yet (e.g. right after a restart): do not guess, wait twice the grace
    assert _joins(45, None) is False
    assert _joins(61, None) is True


def test_support_still_needs_the_deficit():
    assert _joins(60, 0.0, room=19.0) is False  # deficit 1.0 < 1.5


def test_room_trend_needs_enough_history_and_reports_the_rate():
    t0 = datetime(2026, 1, 1, 8, 0)
    tr = RoomTrend(window_minutes=30)
    assert tr.rise_per_hour() is None
    for i in range(31):
        tr.record(t0 + timedelta(minutes=i), 18.0 + i * 0.01)  # +0.6 °C over 30 min
    assert abs(tr.rise_per_hour() - 0.6) < 0.05
    # samples closer than a minute apart are ignored; old ones drop out
    tr.record(t0 + timedelta(minutes=30, seconds=10), 99)
    assert tr.rise_per_hour() < 1
    tr.record(t0 + timedelta(minutes=95), 18.0)
    assert tr.rise_per_hour() is None


async def test_entity_cv_waits_then_joins_when_the_room_does_not_warm():
    from custom_components.smart_climate import climate as climate_mod

    entity, hass = _make(devices=TWO_DEVICES,
                         states={"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE},
                         entry_data={"auto_temperature": 21})
    base = datetime(2026, 1, 12, 7, 0).astimezone()
    real_now = climate_mod.dt_util.now
    try:
        climate_mod.dt_util.now = lambda: base
        await entity._apply_control()
        assert entity._support_active is False  # grace period just started

        for i in range(0, 41):  # 40 min of a flat room at 18 °C
            climate_mod.dt_util.now = lambda i=i: base + timedelta(minutes=i)
            await entity._apply_control()
        assert entity._support_active is True
    finally:
        climate_mod.dt_util.now = real_now
