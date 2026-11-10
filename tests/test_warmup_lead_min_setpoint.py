"""Fixes after 10-11-2026: off by hand ends at the next block, own minimum setpoint, warm-up lead."""

from datetime import datetime, timedelta

from custom_components.smart_climate import control
from custom_components.smart_climate.climate import SmartClimateEntity
from custom_components.smart_climate.control import Decision
from tests.test_observe_log import QLIMA, _calls, _event, _make, _restore_clock, _room  # noqa: F401

SCHEDULE = {"mode": "daily", "daily": [
    {"time": "07:00", "temp": 21.5}, {"time": "23:30", "temp": 11.5}]}


# ---- control: offset, lead and minimum -----------------------------------------------

def test_offset_follows_slowly_and_skips_defrost():
    assert control.update_offset(None, 24.0, 20.0) == 4.0
    assert control.update_offset(4.0, 10.0, 20.0) == 4.0          # defrost: cold air, skipped
    assert control.update_offset(4.0, None, 20.0) == 4.0
    assert 3.9 < control.update_offset(4.0, 23.0, 20.0) < 4.0     # slow


def test_lead_starts_well_under_the_target_and_holds_until_close():
    assert control.setpoint_lead(18.0, 21.5, 0, 3.4) == 3
    assert control.setpoint_lead(18.0, 21.5, 0, 5.0) == control.LEAD_MAX
    assert control.setpoint_lead(18.0, 21.5, 0, None) == 0          # nothing learned yet
    assert control.setpoint_lead(21.2, 21.5, 0, 3.4) == 0           # close: no lead
    assert control.setpoint_lead(21.2, 21.5, 3, 1.0) == 3           # keeps its value (beeps)
    assert control.setpoint_lead(21.4, 21.5, 3, 3.4) == 0           # within LEAD_OFF: back


DEV = {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "park": "off",
       "step": 1, "min_temp": 16, "max_temp": 30}


def test_heat_setpoint_gets_the_lead_capped_at_max_temp():
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [{**DEV, "lead": 3}])
    assert cmds == [control.DeviceCommand("climate.qlima", "heat", 25)]
    cmds = control.plan_routes(Decision(control.HEAT, 21.5), [{**DEV, "lead": 3, "max_temp": 23}])
    assert cmds == [control.DeviceCommand("climate.qlima", "heat", 23)]


def test_heat_target_under_the_minimum_is_off():
    cmds = control.plan_routes(Decision(control.HEAT, 15), [DEV])
    assert cmds == [control.DeviceCommand("climate.qlima", "off")]


# ---- entity -----------------------------------------------------------------------

def test_configured_minimum_wins_over_the_reported_range():
    entry = type("E", (), {"data": {"devices": [{"entity_id": "climate.q", "role": "both", "min_setpoint": 16}]}})()
    devices = SmartClimateEntity._build_devices(entry, None)
    assert devices[0]["min_setpoint"] == 16

    states = {"climate.qlima": {"state": "off", "attributes": {**QLIMA["attributes"], "min_temp": 7}}}
    _room(states, 21.0)
    entity, hass, clock = _make(states, devices=[
        {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "min_setpoint": 16}])
    assert entity._device_caps()[0]["min_temp"] == 16


async def test_hold_setback_under_the_configured_minimum_switches_off():
    # 23:30: night block 11.5 deg. The Qlima reports min 7 (localtuya), so before this
    # fix it was sent "heat 12".
    on = {"state": "heat", "attributes": {**QLIMA["attributes"], "min_temp": 7, "temperature": 22}}
    states = {"climate.qlima": on}
    _room(states, 21.9)
    entity, hass, clock = _make(states, hold_primary=True, schedule=SCHEDULE, devices=[
        {"entity_id": "climate.qlima", "role": "both", "tier": "primary", "min_setpoint": 16}])
    clock["now"] = datetime(2026, 11, 9, 23, 31).astimezone()
    await entity._apply_control()
    assert {"entity_id": "climate.qlima", "hvac_mode": "off"} in _calls(hass, "set_hvac_mode")
    assert _calls(hass, "set_temperature") == []


async def test_off_by_hand_ends_when_the_next_block_starts():
    on = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22}}
    off = {"state": "off", "attributes": {**QLIMA["attributes"], "temperature": 22}}
    states = {"climate.qlima": on}
    _room(states, 21.9)
    entity, hass, clock = _make(states, schedule=SCHEDULE, devices=[
        {"entity_id": "climate.qlima", "role": "both", "tier": "primary"}])
    clock["now"] = datetime(2026, 11, 9, 23, 31).astimezone()
    states["climate.qlima"] = off
    await entity._on_watched_change(_event("climate.qlima", on, off))
    mode = entity._device_modes["climate.qlima"]
    assert mode["off_by_hand"] is True
    assert mode["until"].startswith("2026-11-10T07:00")
    assert "of tot 07:00" in entity._log[-1]["text"]

    # 06:59: still left alone, the cold room notwithstanding
    _room(states, 16.2)
    clock["now"] = datetime(2026, 11, 10, 6, 59).astimezone()
    hass.services.async_call.reset_mock()
    await entity._update_state()
    assert _calls(hass, "set_hvac_mode") == []

    # 07:00: the morning block takes it back
    clock["now"] = datetime(2026, 11, 10, 7, 0, 10).astimezone()
    await entity._update_state()
    assert "climate.qlima" not in entity._device_modes
    assert {"entity_id": "climate.qlima", "hvac_mode": "heat"} in _calls(hass, "set_hvac_mode")
    assert any("nieuw blok" in e["text"] for e in entity._log)


async def test_boost_warms_up_with_a_lead_and_drops_it_near_the_target():
    heat = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22, "current_temperature": 23.5}}
    states = {"climate.qlima": heat}
    _room(states, 20.4)
    entity, hass, clock = _make(states, fan_boost=True, schedule=SCHEDULE, devices=[
        {"entity_id": "climate.qlima", "role": "both", "tier": "primary"}])
    clock["now"] = datetime(2026, 11, 10, 14, 0).astimezone()
    await entity._apply_control()   # offset 3.1 learned, deficit 1.1 -> lead 3
    assert entity._lead["climate.qlima"] == 3
    assert {"entity_id": "climate.qlima", "temperature": 25} in _calls(hass, "set_temperature")

    # nearly there: back to the plain target
    states["climate.qlima"] = {"state": "heat", "attributes": {**heat["attributes"], "temperature": 25}}
    _room(states, 21.4)
    clock["now"] += timedelta(minutes=40)
    hass.services.async_call.reset_mock()
    await entity._apply_control()
    assert entity._lead.get("climate.qlima", 0) == 0
    assert {"entity_id": "climate.qlima", "temperature": 22} in _calls(hass, "set_temperature")


async def test_no_lead_without_boost():
    heat = {"state": "heat", "attributes": {**QLIMA["attributes"], "temperature": 22, "current_temperature": 24}}
    states = {"climate.qlima": heat}
    _room(states, 19.0)
    entity, hass, _clock = _make(states, devices=[{"entity_id": "climate.qlima", "role": "both", "tier": "primary"}])
    await entity._apply_control()
    assert entity._lead == {}


async def test_next_node_override_does_not_crash_the_loop_and_ends_on_time():
    # 9/10-11-2026: knop 4 set "15 deg until the next block" at 23:50; the naive end time
    # crashed _update_state every 10 s all night.
    from zoneinfo import ZoneInfo

    from custom_components.smart_climate import schedule_helper

    ams = ZoneInfo("Europe/Amsterdam")
    nxt = schedule_helper.compute_next_node_datetime(SCHEDULE, datetime(2026, 11, 9, 23, 50, tzinfo=ams))
    assert nxt == datetime(2026, 11, 10, 7, 0, tzinfo=ams)

    states = {"climate.qlima": {"state": "off", "attributes": QLIMA["attributes"]}}
    _room(states, 20.3)
    entity, hass, clock = _make(states, schedule=SCHEDULE, devices=[
        {"entity_id": "climate.qlima", "role": "both", "tier": "primary"}])
    clock["now"] = datetime(2026, 11, 9, 23, 50, tzinfo=ams)
    await entity.async_set_override_next_node(15)
    clock["now"] = datetime(2026, 11, 10, 3, 0, tzinfo=ams)
    await entity._update_state()                  # used to raise TypeError
    assert entity._mode == "override_next_node"
    clock["now"] = datetime(2026, 11, 10, 7, 0, 5, tzinfo=ams)
    await entity._update_state()
    assert entity._mode == "auto"


def test_a_naive_stored_time_is_local_not_utc():
    from custom_components.smart_climate import climate as climate_mod
    from custom_components.smart_climate.climate import _parse_dt

    climate_mod.dt_util.now = lambda: datetime(2026, 11, 10, 6, 0).astimezone()   # HA: aware
    when = _parse_dt("2026-11-10T07:00:00")
    assert (when.hour, when.utcoffset()) == (7, datetime.now().astimezone().utcoffset())
