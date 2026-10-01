"""Pure, HA-independent control logic for the Smart Climate coordinator.

This module contains the *decision* and *routing* core:

- :func:`decide` turns the coordinator's mode, the current room temperature, and
  the resolved heat/cool band into a single :class:`Decision` (one intent —
  heat / cool / idle / off — for the whole instance).
- :func:`support_needed` decides whether a *support* heater (e.g. the CV next
  to an efficient airco) should join the primary heater.
- :func:`plan_routes` turns that one decision into the per-device commands,
  honouring each device's role, tier, parking preference and capabilities.

All are pure functions with no Home Assistant imports so they can be unit
tested directly.  The single-intent design is what guarantees no device ever
heats while another cools (see ``docs/multi-device-design.md`` §6).

The regulation is deliberately **loose**: wide hysteresis, an override that
never cools, and a policy gate on auto-cooling (``cooling.py``) so overshoot
after heating does not turn into cooling.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
    DEFAULT_HYSTERESIS,
    MIN_BAND_GAP,
    PARK_FAN_ONLY,
    ROLE_BOTH,
    ROLE_COOL,
    ROLE_HEAT,
    TIER_PRIMARY,
    TIER_SUPPORT,
)

# Intents
HEAT = "heat"
COOL = "cool"
IDLE = "idle"
OFF = "off"

# A support heater leaves once the deficit is under this fraction of its delta.
SUPPORT_RELEASE_FRACTION = 0.5


@dataclass(frozen=True)
class Decision:
    """The single instance-wide control decision for one evaluation."""

    intent: str
    target: float | None = None


def clamp_band(heat_target: float, cool_target: float, min_gap: float = MIN_BAND_GAP):
    """Return a (heat, cool) band guaranteed to satisfy cool >= heat + min_gap.

    Protects against a misconfigured band (cool limit at or below the heat
    target), which is the only way the single-intent model could otherwise be
    asked to heat and cool at the same temperature.
    """
    cool_target = max(cool_target, heat_target + min_gap)
    return heat_target, cool_target


def _heat_only(room_temp, target, prev_intent, hysteresis):
    """Heat below one setpoint, with hysteresis. Never cools.

    Used for manual overrides: an override says "keep it at least this warm".
    Overshoot above the override temperature must not turn into cooling (e.g.
    in winter, after the heating has pushed the room a little too high).
    """
    if room_temp is None:
        return Decision(HEAT, target) if prev_intent == HEAT else Decision(IDLE, None)
    if prev_intent == HEAT:
        if room_temp < target + hysteresis:
            return Decision(HEAT, target)
    elif room_temp < target:
        return Decision(HEAT, target)
    return Decision(IDLE, None)


def _band(room_temp, heat_target, cool_target, prev_intent, hysteresis, cooling_allowed=True):
    """Deadband decision: heat below heat_target, cool above cool_target.

    Cooling is only considered when ``cooling_allowed``; otherwise the room
    simply idles above the band (it cools down by itself).
    """
    if room_temp is None:
        return Decision(prev_intent or IDLE, None)
    # Heating: start below heat_target, keep going until heat_target + H
    if prev_intent == HEAT:
        if room_temp < heat_target + hysteresis:
            return Decision(HEAT, heat_target)
    elif room_temp < heat_target:
        return Decision(HEAT, heat_target)
    # Cooling: start above cool_target, keep going until cool_target - H
    if cooling_allowed:
        if prev_intent == COOL:
            if room_temp > cool_target - hysteresis:
                return Decision(COOL, cool_target)
        elif room_temp > cool_target:
            return Decision(COOL, cool_target)
    return Decision(IDLE, None)


def decide(
    *,
    mode: str,
    room_temp: float | None,
    heat_target: float,
    cool_target: float,
    override_target: float | None = None,
    prev_intent: str | None = None,
    hysteresis: float = DEFAULT_HYSTERESIS,
    min_gap: float = MIN_BAND_GAP,
    cooling_allowed: bool = True,
) -> Decision:
    """Resolve the single control decision for this evaluation.

    Args:
        mode: coordinator HVAC mode — ``off`` / ``heat`` / ``cool`` / ``auto``.
        room_temp: measured room temperature (``None`` if unavailable).
        heat_target: heat-to setpoint for the current slot/presence.
        cool_target: cool-above setpoint (band upper) for the current slot.
        override_target: when set, a manual override is active and takes
            precedence over the schedule band (but not over ``off``).  In
            ``auto``/``heat`` it only ever heats; in an explicit ``cool`` mode
            it cools to the override temperature.
        prev_intent: the previous intent, used for hysteresis.
        hysteresis: anti-flap deadband in degrees.
        min_gap: minimum enforced gap between heat_target and cool_target.
        cooling_allowed: policy gate for *auto* cooling (see ``cooling.py``).
            An explicit ``cool`` mode is the user's choice and ignores it.
    """
    if mode == OFF:
        return Decision(OFF, None)

    if override_target is not None:
        if mode == COOL:
            return Decision(COOL, override_target)
        return _heat_only(room_temp, override_target, prev_intent, hysteresis)

    if mode == HEAT:
        return Decision(HEAT, heat_target)
    if mode == COOL:
        return Decision(COOL, cool_target)

    # auto (integration-driven band)
    heat_target, cool_target = clamp_band(heat_target, cool_target, min_gap)
    return _band(
        room_temp, heat_target, cool_target, prev_intent, hysteresis, cooling_allowed
    )


class RoomTrend:
    """Rolling room-temperature history to estimate the warming rate (°C/h)."""

    def __init__(self, window_minutes: int = 30) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._samples: deque[tuple[datetime, float]] = deque()

    def record(self, now: datetime, temp: float | None) -> None:
        """Add a sample (at most one per minute) and drop old ones."""
        if temp is None:
            return
        if self._samples and (now - self._samples[-1][0]).total_seconds() < 60:
            return
        self._samples.append((now, temp))
        while self._samples and now - self._samples[0][0] > self._window:
            self._samples.popleft()

    def rise_per_hour(self) -> float | None:
        """Warming rate over the window, or None if there is too little history."""
        if len(self._samples) < 2:
            return None
        (t0, v0), (t1, v1) = self._samples[0], self._samples[-1]
        hours = (t1 - t0).total_seconds() / 3600
        if hours < self._window.total_seconds() / 3600 * 0.66:
            return None
        return (v1 - v0) / hours


def support_needed(
    room_temp: float | None,
    heat_target: float,
    delta: float,
    prev_active: bool,
    *,
    heating_minutes: float | None = None,
    rise_per_hour: float | None = None,
    grace_minutes: float = 0.0,
    min_rise: float = 0.0,
    release_fraction: float = SUPPORT_RELEASE_FRACTION,
) -> bool:
    """Should the *support* heater (e.g. the CV) join the primary one?

    - Already active: stays until the deficit has shrunk to under
      ``release_fraction`` of ``delta`` (a wide, loose hysteresis).
    - Joins when the room is at least ``delta`` below the heat target — and,
      when a grace period is configured, only after the primary heater has had
      ``grace_minutes`` of heating to close the gap *and* the room is warming
      slower than ``min_rise`` °C/h.  Warming up after arriving home is slow
      but steady, so the support heater is not needed; a flat or falling room
      means the primary heater cannot keep up.
    Without a room temperature the previous state is kept.
    """
    if room_temp is None:
        return prev_active
    deficit = heat_target - room_temp
    if prev_active:
        return deficit > delta * release_fraction
    if deficit < delta:
        return False
    if grace_minutes <= 0:
        return True
    if heating_minutes is None or heating_minutes < grace_minutes:
        return False
    return rise_per_hour is None or rise_per_hour < min_rise


@dataclass(frozen=True)
class DeviceCommand:
    """A desired end-state for one actuator device."""

    entity_id: str
    hvac_mode: str
    temperature: float | None = None


def _round_to_step(value: float | None, step: float | None) -> float | None:
    """Round a setpoint to a device's step (e.g. an airco that only does whole degrees)."""
    if value is None or not step or step <= 0:
        return value
    rounded = int(value / step + 0.5) * step
    return int(rounded) if float(rounded).is_integer() else round(rounded, 2)


def plan_routes(
    decision: Decision,
    devices: list[dict],
    *,
    support_active: bool = False,
) -> list[DeviceCommand]:
    """Map one :class:`Decision` onto per-device commands.

    ``devices`` is a list of dicts with ``entity_id`` and optionally:

    - ``role`` (heat/cool/both, default both)
    - ``tier`` (``primary`` default, or ``support``) — heating only
    - ``park`` (``fan_only`` default, or ``off``) — what to do when not serving
    - ``supports_fan_only`` — whether ``fan_only`` is a valid mode for it
    - ``can_heat`` / ``can_cool`` — whether the device advertises that HVAC mode
    - ``available`` — False if the entity is unavailable right now
    - ``step`` — the device's temperature step (setpoints are rounded to it)

    Heating: primary devices heat alone; *support* devices join only while
    ``support_active``.  If no primary device can serve (none configured,
    unavailable, or unable to heat) the support devices heat regardless, so the
    system never goes cold because the preferred heater is down.

    Cooling: every device that can cool serves.

    A device that is not serving is **parked**: ``fan_only`` only if it asks for
    that *and* supports it, otherwise ``off``.  A device is never left in the
    *opposite* conditioning mode, so heat and cool can never run at once.  Only
    an explicit ``off`` decision powers a fan-capable device down.
    """

    def _serves(dev, intent):
        role = dev.get("role", ROLE_BOTH)
        if intent == HEAT:
            return role in (ROLE_HEAT, ROLE_BOTH) and dev.get("can_heat", True)
        if intent == COOL:
            return role in (ROLE_COOL, ROLE_BOTH) and dev.get("can_cool", True)
        return False

    serving: set[str] = set()
    if decision.intent in (HEAT, COOL):
        candidates = [
            d for d in devices
            if d.get("available", True) and _serves(d, decision.intent)
        ]
        if decision.intent == HEAT:
            primary = [d for d in candidates if d.get("tier", TIER_PRIMARY) == TIER_PRIMARY]
            support = [d for d in candidates if d.get("tier", TIER_PRIMARY) == TIER_SUPPORT]
            chosen = primary + support if (support_active or not primary) else primary
        else:
            chosen = candidates
        serving = {d["entity_id"] for d in chosen}

    commands: list[DeviceCommand] = []
    for dev in devices:
        entity_id = dev["entity_id"]

        if decision.intent == OFF:
            commands.append(DeviceCommand(entity_id, OFF))
        elif entity_id in serving:
            mode = HEAT if decision.intent == HEAT else COOL
            commands.append(
                DeviceCommand(entity_id, mode, _round_to_step(decision.target, dev.get("step")))
            )
        elif dev.get("park", PARK_FAN_ONLY) == PARK_FAN_ONLY and dev.get("supports_fan_only", False):
            # Keep airflow without conditioning (aircos).
            commands.append(DeviceCommand(entity_id, "fan_only"))
        else:
            # Nothing to preserve (or the device was told not to ventilate) →
            # off, so it can never counteract the active intent.
            commands.append(DeviceCommand(entity_id, OFF))
    return commands


def intent_to_hvac_action(intent: str | None) -> str:
    """Map an intent to a HA hvac_action string."""
    return {
        HEAT: "heating",
        COOL: "cooling",
        IDLE: "idle",
        OFF: "off",
    }.get(intent, "idle")
