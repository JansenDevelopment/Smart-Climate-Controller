"""Per-device control (auto / off / manual), temporary modes and the support pause."""

import pathlib
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.control import (
    COOL,
    HEAT,
    IDLE,
    OFF,
    Decision,
    plan_routes,
)


@pytest.fixture(autouse=True)
def _restore_clock():
    """_make() pins dt_util.now; put the real one back after every test."""
    from custom_components.smart_climate import climate as climate_mod

    original = climate_mod.dt_util.now
    yield
    climate_mod.dt_util.now = original


def _dev(entity_id, role="both", tier="primary", park="off", **extra):
    return {"entity_id": entity_id, "role": role, "tier": tier, "park": park, **extra}


def _modes(cmds):
    return {c.entity_id: c.hvac_mode for c in cmds}


# ---------------------------------------------------------------------------
# plan_routes()
# ---------------------------------------------------------------------------

def test_manual_device_is_never_commanded():
    devices = [_dev("a", control="manual"), _dev("b", "heat", "support")]
    for decision in (Decision(HEAT, 21), Decision(IDLE, None), Decision(OFF, None)):
        cmds = plan_routes(decision, devices, support_active=True)
        assert "a" not in _modes(cmds)


def test_manual_primary_lets_the_support_heater_take_over():
    devices = [_dev("airco", control="manual"), _dev("cv", "heat", "support")]
    assert _modes(plan_routes(Decision(HEAT, 21), devices))["cv"] == "heat"


def test_off_device_is_kept_off_and_never_serves():
    devices = [_dev("airco", control="off"), _dev("cv", "heat", "support")]
    modes = _modes(plan_routes(Decision(HEAT, 21), devices, support_active=False))
    assert modes["airco"] == "off"
    assert modes["cv"] == "heat"  # nothing else can serve, so the support heater does


def test_off_device_ignores_fan_only_parking():
    airco = _dev("airco", park="fan_only", supports_fan_only=True, control="off")
    assert _modes(plan_routes(Decision(IDLE, None), [airco])) == {"airco": "off"}


def test_off_support_device_does_not_join_even_when_support_is_active():
    devices = [_dev("airco"), _dev("cv", "heat", "support", control="off")]
    modes = _modes(plan_routes(Decision(HEAT, 21), devices, support_active=True))
    assert modes == {"airco": "heat", "cv": "off"}


def test_cooling_skips_off_and_manual_devices():
    devices = [_dev("a", control="off"), _dev("b", control="manual"), _dev("c")]
    modes = _modes(plan_routes(Decision(COOL, 24), devices))
    assert modes == {"a": "off", "c": "cool"}


# ---------------------------------------------------------------------------
# Entity level
# ---------------------------------------------------------------------------

AIRCO_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat", "cool", "fan_only"], "target_temp_step": 1, "current_temperature": 15}}
CV_STATE = {"state": "off", "attributes": {
    "hvac_modes": ["off", "heat"], "target_temp_step": 0.5, "current_temperature": 15}}
DEVICES = [
    {"entity_id": "climate.airco", "role": "both", "tier": "primary", "park": "off"},
    {"entity_id": "climate.cv", "role": "heat", "tier": "support", "park": "off"},
]


def _make(entry_data=None, now=None):
    from custom_components.smart_climate import climate as climate_mod
    from custom_components.smart_climate.climate import SmartClimateEntity

    states = {"climate.airco": AIRCO_STATE, "climate.cv": CV_STATE}

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
    return entity, hass, clock


def _hvac(hass):
    return {
        (c.args[2]["entity_id"], c.args[2]["hvac_mode"])
        for c in hass.services.async_call.call_args_list
        if c.args[0] == "climate" and c.args[1] == "set_hvac_mode"
    }


async def test_cv_off_keeps_the_cv_out_even_with_a_big_deficit():
    entity, hass, _ = _make()
    await entity.async_set_device_mode("climate.cv", "off")
    await entity._apply_control()
    assert ("climate.cv", "heat") not in _hvac(hass)
    assert ("climate.airco", "heat") in _hvac(hass)


async def test_manual_device_gets_no_commands_at_all():
    entity, hass, _ = _make()
    await entity.async_set_device_mode("climate.airco", "manual")
    await entity._apply_control()
    assert all(eid != "climate.airco" for eid, _mode in _hvac(hass))


async def test_temporary_device_mode_expires_and_is_persisted():
    entity, hass, clock = _make()
    start = clock["now"]
    await entity.async_set_device_mode("climate.cv", "off", minutes=60)
    assert entity._effective_device_mode("climate.cv", start) == "off"
    assert entity._effective_device_mode("climate.cv", start + timedelta(minutes=61)) == "auto"
    clock["now"] = start + timedelta(minutes=61)
    entity._expire_device_modes(clock["now"])
    assert "climate.cv" not in entity._device_modes
    persisted = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert persisted["device_modes"] == {}


async def test_invalid_device_or_mode_is_ignored():
    entity, _, _ = _make()
    await entity.async_set_device_mode("climate.nope", "off")
    await entity.async_set_device_mode("climate.cv", "banana")
    assert entity._device_modes == {}


async def test_support_pause_until_morning_ends_at_the_next_ten_oclock():
    entity, _, _ = _make(now=datetime(2026, 1, 11, 22, 0).astimezone())
    await entity.async_set_support_pause(True, until_morning=True)
    until = datetime.fromisoformat(entity._support_paused_until())
    assert (until.day, until.hour, until.minute) == (12, 10, 0)
    # only the support device is paused, never the primary
    assert "climate.airco" not in entity._device_modes
    assert entity._device_modes["climate.cv"]["mode"] == "off"


async def test_support_pause_in_the_morning_ends_the_same_morning():
    entity, _, _ = _make(now=datetime(2026, 1, 12, 7, 30).astimezone())
    await entity.async_set_support_pause(True, until_morning=True)
    until = datetime.fromisoformat(entity._support_paused_until())
    assert (until.day, until.hour) == (12, 10)


async def test_support_pause_for_minutes_and_resume():
    entity, _, _ = _make()
    await entity.async_set_support_pause(True, minutes=45)
    assert entity._support_paused_until() not in (None, "")
    await entity.async_set_support_pause(False)
    assert entity._support_paused_until() is None
    assert entity._device_modes == {}


async def test_open_ended_pause_reports_an_empty_end():
    entity, _, _ = _make()
    await entity.async_set_support_pause(True)
    assert entity._support_paused_until() == ""


async def test_pause_makes_the_airco_do_all_the_heating():
    entity, hass, _ = _make()
    await entity.async_set_support_pause(True, minutes=60)
    await entity._apply_control()
    assert ("climate.cv", "heat") not in _hvac(hass)  # the paused CV is not used
    assert ("climate.airco", "heat") in _hvac(hass)


async def test_attributes_expose_modes_and_pause():
    entity, _, _ = _make()
    await entity.async_set_support_pause(True, minutes=30)
    attrs = entity.extra_state_attributes
    assert attrs["device_modes"]["climate.cv"]["mode"] == "off"
    assert attrs["device_modes"]["climate.airco"]["mode"] == "auto"
    assert attrs["support_paused_until"]


# ---------------------------------------------------------------------------
# Helper entities
# ---------------------------------------------------------------------------

CLIMATE_ID = "climate.smart"


def _helper(cls, attrs, *args):
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    st = MagicMock()
    st.attributes = attrs
    hass.states.get = MagicMock(side_effect=lambda eid: st if eid == CLIMATE_ID else None)
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"name": "Living"}
    ent = cls(hass, entry, *args)
    ent.hass = hass
    ent._climate_entity_id = CLIMATE_ID
    ent.async_write_ha_state = MagicMock()
    return ent, hass


async def test_device_mode_select_reads_and_writes():
    from custom_components.smart_climate.select import SmartClimateDeviceModeSelect

    ent, hass = _helper(
        SmartClimateDeviceModeSelect,
        {"device_modes": {"climate.cv": {"mode": "off", "until": "2026-01-12T10:00:00+01:00"}}},
        "climate.cv",
    )
    assert ent.current_option == "off"
    assert ent.extra_state_attributes["until"].startswith("2026-01-12T10")
    await ent.async_select_option("manual")
    args = hass.services.async_call.call_args.args
    assert args[1] == "set_device_mode"
    assert args[2] == {"entity_id": CLIMATE_ID, "device": "climate.cv", "mode": "manual"}


async def test_device_added_in_manual_starts_hands_off_and_is_seeded_once():
    qlima = {"entity_id": "climate.airco", "role": "both", "tier": "primary", "park": "off",
             "control": "manual"}
    entity, hass, _ = _make(entry_data={"devices": [qlima, DEVICES[1]]})
    # applied in memory straight away, so the very first evaluation leaves it alone
    assert entity._device_modes["climate.airco"]["mode"] == "manual"
    await entity._apply_control()
    assert all(eid != "climate.airco" for eid, _mode in _hvac(hass))

    # persisted (with the seeded marker) once the entity registers ...
    entity._persist_seeded_modes()
    persisted = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert persisted["device_modes"]["climate.airco"]["mode"] == "manual"
    assert "climate.airco" in persisted["device_modes_seeded"]

    # ... and never seeded again: once the user sets auto it stays auto after a reload
    entity2, _, _ = _make(entry_data={"devices": [qlima, DEVICES[1]],
                                      "device_modes_seeded": ["climate.airco", "climate.cv"]})
    assert "climate.airco" not in entity2._device_modes


async def test_support_pause_switch_reads_and_writes():
    from custom_components.smart_climate.switch import SmartClimateSupportPauseSwitch

    ent, hass = _helper(SmartClimateSupportPauseSwitch, {"support_paused_until": "2026-01-12T10:00:00+01:00"})
    assert ent.is_on is True
    await ent.async_turn_off()
    assert hass.services.async_call.call_args.args[2] == {"entity_id": CLIMATE_ID, "enabled": False}
    ent2, hass2 = _helper(SmartClimateSupportPauseSwitch, {"support_paused_until": None})
    assert ent2.is_on is False
    await ent2.async_turn_on()
    assert hass2.services.async_call.call_args.args[2] == {
        "entity_id": CLIMATE_ID, "enabled": True, "until_morning": True}
