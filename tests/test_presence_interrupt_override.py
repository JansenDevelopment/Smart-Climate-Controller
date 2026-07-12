"""Tests for presence-interrupt-override behavior.

These tests verify that when 'Allow presence to interrupt override' is enabled
(interruptible=True), returning home cancels ALL override modes
(timer, infinity, and next_node), not just timer overrides.

Regression test for the bug: "when i am away, and i turn on override and then come home,
it will not go back to schedule even when 'Allow presence to interrupt override' is on"
"""

import sys
import pathlib
from unittest.mock import AsyncMock, MagicMock
import pytest

# Ensure custom_components is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.const import (
    MODE_AUTO,
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal SmartClimateEntity instance without HA runtime
# ---------------------------------------------------------------------------

def _make_entity(interruptible: bool = True, mode: str = MODE_AUTO) -> "object":
    """Return a SmartClimateEntity wired up with mock HA objects."""
    from custom_components.smart_climate.climate import SmartClimateEntity

    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {}

    entity = SmartClimateEntity(
        hass=hass,
        entry=entry,
        name="Test Climate",
        wrapped_climate="climate.wrapped",
        zone_home="zone.home",
        away_temp=14.0,
        away_delay_minutes=0,
        interruptible=interruptible,
        default_override_mode="timer",
        default_override_duration=30,
    )
    entity._mode = mode
    entity._presence = "away"
    entity._auto_temperature = 21.0
    entity._override_temperature = 22.0

    # Patch write_ha_state to be a no-op
    entity.async_write_ha_state = MagicMock()

    return entity


# ---------------------------------------------------------------------------
# Tests for _on_zone_change  (event-driven path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("override_mode", [
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
])
async def test_coming_home_cancels_all_overrides_when_interruptible(override_mode):
    """Coming home with interruptible=True must cancel any active override mode."""
    entity = _make_entity(interruptible=True, mode=override_mode)

    # Simulate zone.home reporting 1 person
    zone_state = MagicMock()
    zone_state.state = "1"
    entity.hass.states.get = MagicMock(return_value=zone_state)

    event = MagicMock()
    await entity._on_zone_change(event)

    assert entity._mode == MODE_AUTO, (
        f"Expected MODE_AUTO after coming home with interruptible=True, "
        f"but got {entity._mode!r} (override was {override_mode!r})"
    )
    assert entity._presence == "home"


@pytest.mark.asyncio
@pytest.mark.parametrize("override_mode", [
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
])
async def test_coming_home_keeps_overrides_when_not_interruptible(override_mode):
    """Coming home with interruptible=False must NOT cancel any override mode."""
    entity = _make_entity(interruptible=False, mode=override_mode)

    zone_state = MagicMock()
    zone_state.state = "1"
    entity.hass.states.get = MagicMock(return_value=zone_state)

    event = MagicMock()
    await entity._on_zone_change(event)

    assert entity._mode == override_mode, (
        f"Expected override to remain {override_mode!r} when interruptible=False, "
        f"but got {entity._mode!r}"
    )


# ---------------------------------------------------------------------------
# Tests for _update_state  (polling path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("override_mode", [
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
])
async def test_update_state_cancels_all_overrides_on_return_home_when_interruptible(override_mode):
    """_update_state must cancel any override when presence transitions away->home."""
    entity = _make_entity(interruptible=True, mode=override_mode)
    # Ensure _presence starts as "away" so the transition logic fires
    entity._presence = "away"

    zone_state = MagicMock()
    zone_state.state = "1"
    entity.hass.states.get = MagicMock(return_value=zone_state)

    # _update_state calls _update_target_temperature which calls hass.services
    entity.hass.services.async_call = AsyncMock()

    await entity._update_state()

    assert entity._mode == MODE_AUTO, (
        f"_update_state: expected MODE_AUTO after coming home with interruptible=True, "
        f"but got {entity._mode!r} (override was {override_mode!r})"
    )
    assert entity._presence == "home"


# ---------------------------------------------------------------------------
# Tests for _transition_to_away
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("override_mode", [
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
])
def test_transition_to_away_cancels_all_overrides_when_interruptible(override_mode):
    """_transition_to_away must cancel any active override when interruptible=True."""
    entity = _make_entity(interruptible=True, mode=override_mode)
    entity._presence = "home"

    entity._transition_to_away()

    assert entity._mode == MODE_AUTO, (
        f"_transition_to_away: expected MODE_AUTO with interruptible=True, "
        f"but got {entity._mode!r} (override was {override_mode!r})"
    )
    assert entity._presence == "away"


@pytest.mark.parametrize("override_mode", [
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
])
def test_transition_to_away_keeps_overrides_when_not_interruptible(override_mode):
    """_transition_to_away must NOT cancel override when interruptible=False."""
    entity = _make_entity(interruptible=False, mode=override_mode)
    entity._presence = "home"

    entity._transition_to_away()

    assert entity._mode == override_mode, (
        f"_transition_to_away: expected override {override_mode!r} to remain when "
        f"interruptible=False, but got {entity._mode!r}"
    )

