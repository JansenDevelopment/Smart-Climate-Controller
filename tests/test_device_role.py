"""Tests for the per-device role setter (`async_set_device_role`).

These verify the runtime role change that backs the per-device role select
helper entities: a valid role updates the resolved device list and persists to
the right source (config subentry when present, else the entry.data devices
list), while invalid roles / unknown devices are ignored.
"""

import sys
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure custom_components is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (  # noqa: E402
    CONF_DEVICES,
    CONF_ENTITY_ID,
    CONF_ROLE,
    ROLE_BOTH,
    ROLE_COOL,
    ROLE_HEAT,
    SUBENTRY_TYPE_DEVICE,
)


def _make_entity(devices=None, subentries=None):
    """Build a SmartClimateEntity with a given device source, sans HA runtime."""
    from custom_components.smart_climate.climate import SmartClimateEntity

    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_DEVICES: devices} if devices is not None else {}
    # _build_devices only treats subentries as a source when it's a Mapping.
    entry.subentries = subentries if subentries is not None else MagicMock()

    entity = SmartClimateEntity(
        hass=hass,
        entry=entry,
        name="Test Climate",
        wrapped_climate=None,
        zone_home="zone.home",
        away_temp=14.0,
        away_delay_minutes=0,
        interruptible=True,
        default_override_mode="timer",
        default_override_duration=30,
    )
    # Isolate the role logic from the control/routing pipeline (tested elsewhere).
    entity._apply_control = AsyncMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def _role_of(entity, entity_id):
    return next(d[CONF_ROLE] for d in entity._devices if d["entity_id"] == entity_id)


@pytest.mark.asyncio
async def test_set_role_updates_devices_and_persists_via_entry_data():
    entity = _make_entity(
        devices=[
            {"entity_id": "climate.a", "role": ROLE_BOTH},
            {"entity_id": "climate.b", "role": ROLE_HEAT},
        ]
    )

    await entity.async_set_device_role("climate.b", ROLE_COOL)

    assert _role_of(entity, "climate.b") == ROLE_COOL
    assert _role_of(entity, "climate.a") == ROLE_BOTH  # untouched
    # Persisted to entry.data devices (no subentry source present).
    entity.hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = entity.hass.config_entries.async_update_entry.call_args
    persisted = {d["entity_id"]: d["role"] for d in kwargs["data"][CONF_DEVICES]}
    assert persisted == {"climate.a": ROLE_BOTH, "climate.b": ROLE_COOL}
    entity._apply_control.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_role_uses_subentry_when_present():
    subentries = {
        "sub1": SimpleNamespace(
            subentry_type=SUBENTRY_TYPE_DEVICE,
            data={CONF_ENTITY_ID: "climate.a", CONF_ROLE: ROLE_BOTH},
        )
    }
    entity = _make_entity(subentries=subentries)
    assert _role_of(entity, "climate.a") == ROLE_BOTH  # sourced from subentry

    await entity.async_set_device_role("climate.a", ROLE_HEAT)

    assert _role_of(entity, "climate.a") == ROLE_HEAT
    # Subentry path persists via async_update_subentry, not entry.data.
    entity.hass.config_entries.async_update_subentry.assert_called_once()
    entity.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_role_is_ignored():
    entity = _make_entity(devices=[{"entity_id": "climate.a", "role": ROLE_HEAT}])

    await entity.async_set_device_role("climate.a", "bogus")

    assert _role_of(entity, "climate.a") == ROLE_HEAT
    entity.hass.config_entries.async_update_entry.assert_not_called()
    entity._apply_control.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_device_is_ignored():
    entity = _make_entity(devices=[{"entity_id": "climate.a", "role": ROLE_HEAT}])

    await entity.async_set_device_role("climate.zzz", ROLE_COOL)

    assert _role_of(entity, "climate.a") == ROLE_HEAT
    assert all(d["entity_id"] != "climate.zzz" for d in entity._devices)
    entity.hass.config_entries.async_update_entry.assert_not_called()
    entity._apply_control.assert_not_awaited()
