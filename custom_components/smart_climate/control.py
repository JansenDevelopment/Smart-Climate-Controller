"""Pure, HA-independent control logic for the Smart Climate coordinator.

This module contains the *decision* and *routing* core:

- :func:`decide` turns the coordinator's mode, the current room temperature, and
  the resolved heat/cool band into a single :class:`Decision` (one intent —
  heat / cool / idle / off — for the whole instance).
- :func:`plan_routes` turns that one decision into the per-device commands,
  honouring each device's role and whether it can keep airflow (``fan_only``).

Both are pure functions with no Home Assistant imports so they can be unit
tested directly.  The single-intent design is what guarantees no device ever
heats while another cools (see ``docs/multi-device-design.md`` §6).
"""

from dataclasses import dataclass

from .const import (
    DEFAULT_HYSTERESIS,
    MIN_BAND_GAP,
    ROLE_BOTH,
    ROLE_COOL,
    ROLE_HEAT,
)

# Intents
HEAT = "heat"
COOL = "cool"
IDLE = "idle"
OFF = "off"


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


def _single_target(room_temp, target, prev_intent, hysteresis):
    """Heat below / cool above one setpoint, with hysteresis to avoid flapping."""
    if room_temp is None:
        return Decision(prev_intent or IDLE, target if prev_intent in (HEAT, COOL) else None)
    # Heating side
    if prev_intent == HEAT:
        if room_temp < target + hysteresis:
            return Decision(HEAT, target)
    elif room_temp < target:
        return Decision(HEAT, target)
    # Cooling side
    if prev_intent == COOL:
        if room_temp > target - hysteresis:
            return Decision(COOL, target)
    elif room_temp > target:
        return Decision(COOL, target)
    return Decision(IDLE, None)


def _band(room_temp, heat_target, cool_target, prev_intent, hysteresis):
    """Deadband decision: heat below heat_target, cool above cool_target."""
    if room_temp is None:
        return Decision(prev_intent or IDLE, None)
    # Heating: start below heat_target, keep going until heat_target + H
    if prev_intent == HEAT:
        if room_temp < heat_target + hysteresis:
            return Decision(HEAT, heat_target)
    elif room_temp < heat_target:
        return Decision(HEAT, heat_target)
    # Cooling: start above cool_target, keep going until cool_target - H
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
) -> Decision:
    """Resolve the single control decision for this evaluation.

    Args:
        mode: coordinator HVAC mode — ``off`` / ``heat`` / ``cool`` / ``auto``.
        room_temp: measured room temperature (``None`` if unavailable).
        heat_target: heat-to setpoint for the current slot/presence.
        cool_target: cool-above setpoint (band upper) for the current slot.
        override_target: when set, a manual single-setpoint override is active
            and takes precedence over auto/heat/cool (but not over ``off``).
        prev_intent: the previous intent, used for hysteresis.
        hysteresis: anti-flap deadband in degrees.
        min_gap: minimum enforced gap between heat_target and cool_target.
    """
    if mode == OFF:
        return Decision(OFF, None)

    if override_target is not None:
        return _single_target(room_temp, override_target, prev_intent, hysteresis)

    if mode == HEAT:
        return Decision(HEAT, heat_target)
    if mode == COOL:
        return Decision(COOL, cool_target)

    # auto (integration-driven band)
    heat_target, cool_target = clamp_band(heat_target, cool_target, min_gap)
    return _band(room_temp, heat_target, cool_target, prev_intent, hysteresis)


@dataclass(frozen=True)
class DeviceCommand:
    """A desired end-state for one actuator device."""

    entity_id: str
    hvac_mode: str
    temperature: float | None = None


def plan_routes(decision: Decision, devices: list[dict]) -> list[DeviceCommand]:
    """Map one :class:`Decision` onto per-device commands.

    ``devices`` is a list of ``{"entity_id", "role", "supports_fan_only"}``
    dicts.  A device that cannot serve the current intent — wrong role, or the
    intent is ``idle`` — is **parked**: ``fan_only`` if it supports it (so an
    airco keeps circulating air), otherwise ``off``.  A device is never left in
    the *opposite* conditioning mode (e.g. a radiator is never in ``heat`` while
    the system is cooling), which is what keeps heat and cool from ever running
    at once.  Only an explicit ``off`` decision powers a fan-capable device down.
    """
    commands: list[DeviceCommand] = []
    for dev in devices:
        entity_id = dev["entity_id"]
        role = dev.get("role", ROLE_BOTH)
        supports_fan_only = dev.get("supports_fan_only", False)

        if decision.intent == OFF:
            commands.append(DeviceCommand(entity_id, OFF))
            continue

        serves_heat = decision.intent == HEAT and role in (ROLE_HEAT, ROLE_BOTH)
        serves_cool = decision.intent == COOL and role in (ROLE_COOL, ROLE_BOTH)

        if serves_heat:
            commands.append(DeviceCommand(entity_id, HEAT, decision.target))
        elif serves_cool:
            commands.append(DeviceCommand(entity_id, COOL, decision.target))
        elif supports_fan_only:
            # Keep airflow without conditioning (aircos).
            commands.append(DeviceCommand(entity_id, "fan_only"))
        else:
            # No airflow to preserve (e.g. a radiator) → off, so it can never
            # counteract the active intent.
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
