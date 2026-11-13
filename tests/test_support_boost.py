"""'CV erbij' (support boost): the support heater joins now, for a while or until the target."""

import copy
from datetime import timedelta

import pytest
import test_device_modes as tdm
from test_device_modes import _hvac, _make


@pytest.fixture(autouse=True)
def _room():
    """Each test may change the room temperature; put the shared states back afterwards."""
    saved = copy.deepcopy((tdm.AIRCO_STATE, tdm.CV_STATE))
    yield
    tdm.AIRCO_STATE.clear(), tdm.AIRCO_STATE.update(saved[0])
    tdm.CV_STATE.clear(), tdm.CV_STATE.update(saved[1])


def _room_at(temp):
    tdm.AIRCO_STATE["attributes"]["current_temperature"] = temp
    tdm.CV_STATE["attributes"]["current_temperature"] = temp


async def test_boost_lets_the_cv_join_even_with_support_switched_off():
    entity, hass, _ = _make({"support_enabled": False})
    await entity._apply_control()
    assert ("climate.cv", "heat") not in _hvac(hass)
    assert ("climate.airco", "heat") in _hvac(hass)
    hass.services.async_call.reset_mock()
    await entity.async_set_support_boost(True)
    assert ("climate.cv", "heat") in _hvac(hass)
    assert ("climate.airco", "off") not in _hvac(hass)  # the Qlima keeps heating too


async def test_boost_lets_the_cv_join_when_the_room_is_only_a_little_too_cold():
    _room_at(20.5)  # 0.5 under the target of 21: normally no support (delta 1.5)
    entity, hass, _ = _make()
    await entity._apply_control()
    assert ("climate.cv", "heat") not in _hvac(hass)
    await entity.async_set_support_boost(True)
    assert entity._support_active
    assert ("climate.cv", "heat") in _hvac(hass)


async def test_boost_ends_by_itself_after_its_time():
    entity, hass, clock = _make({"support_enabled": False})
    await entity.async_set_support_boost(True, minutes=30)
    assert entity.extra_state_attributes["support_boost_until"]
    clock["now"] += timedelta(minutes=31)
    hass.services.async_call.reset_mock()
    await entity._apply_control()
    assert entity.extra_state_attributes["support_boost_until"] is None
    assert ("climate.cv", "heat") not in _hvac(hass)


async def test_boost_ends_when_the_room_reaches_the_target():
    _room_at(20.5)
    entity, _, _ = _make()
    await entity.async_set_support_boost(True)
    assert entity._support_boost_until is not None
    _room_at(21.0)
    await entity._apply_control()
    assert entity._support_boost_until is None


async def test_boost_lifts_a_support_pause_but_not_a_hand_choice():
    entity, hass, _ = _make()
    await entity.async_set_support_pause(True, minutes=60)
    await entity.async_set_support_boost(True)
    assert "climate.cv" not in entity._device_modes  # the pause is gone
    assert ("climate.cv", "heat") in _hvac(hass)

    entity, hass, _ = _make()
    await entity.async_set_device_mode("climate.cv", "off")
    hass.services.async_call.reset_mock()
    await entity.async_set_support_boost(True)
    assert entity._device_modes["climate.cv"]["mode"] == "off"  # "Niet gebruiken" stays
    assert ("climate.cv", "heat") not in _hvac(hass)


async def test_stopping_the_boost_and_restart_persistence():
    entity, _, _ = _make({"support_enabled": False})
    await entity.async_set_support_boost(True)
    persisted = [c.kwargs["data"] for c in entity.hass.config_entries.async_update_entry.call_args_list]
    assert persisted[-1]["support_boost_until"]
    await entity.async_set_support_boost(False)
    persisted = [c.kwargs["data"] for c in entity.hass.config_entries.async_update_entry.call_args_list]
    assert persisted[-1]["support_boost_until"] is None
    assert entity.extra_state_attributes["support_boost_until"] is None

    # a boost that was running survives a restart (read back from the entry data)
    until = (tdm.datetime(2026, 1, 12, 8, 0).astimezone()).isoformat()
    entity, hass, _ = _make({"support_enabled": False, "support_boost_until": until})
    await entity._apply_control()
    assert ("climate.cv", "heat") in _hvac(hass)


async def test_boost_sets_the_cv_above_its_own_reading():
    """A CV thermostat that already reads warm (the Qlima warmed the air around it) would not fire
    at the plain target: during the boost its setpoint sits a degree above its own reading."""
    _room_at(20.0)  # the room is the mean of both devices: (20.0 + 21.6) / 2 = 20.8, still under 21
    tdm.CV_STATE["attributes"]["current_temperature"] = 21.6
    entity, hass, _ = _make()
    await entity.async_set_support_boost(True)
    cv = next(p for p in entity._plan if p["entity_id"] == "climate.cv")
    assert cv["hvac_mode"] == "heat" and cv["temperature"] >= 22.5


def test_boost_lead_bounds():
    from custom_components.smart_climate.control import support_boost_lead

    assert support_boost_lead(None, 21) == 1.0
    assert support_boost_lead(19, 21) == 1.0     # cold sensor: just above the target
    assert support_boost_lead(21.6, 21) == pytest.approx(1.6)   # warm sensor: a degree above its reading
    assert support_boost_lead(25, 21) == 3.0     # capped
    assert support_boost_lead(20, None) == 0.0
