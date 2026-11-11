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
    DEVICE_MODE_MANUAL,
    DEVICE_MODE_OFF,
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

    def rise_per_hour(self, since: datetime | None = None, min_span_minutes: float | None = None) -> float | None:
        """Warming rate (°C/h), or None if there is too little history.

        ``since`` restricts the estimate to samples taken at/after that moment
        (e.g. when heating started, so the flat period before it does not dilute
        the rate).  ``min_span_minutes`` is the minimum time the samples must
        cover (default: two thirds of the window).
        """
        samples = [x for x in self._samples if since is None or x[0] >= since]
        if len(samples) < 2:
            return None
        (t0, v0), (t1, v1) = samples[0], samples[-1]
        hours = (t1 - t0).total_seconds() / 3600
        need_min = (
            min_span_minutes
            if min_span_minutes is not None
            else self._window.total_seconds() / 60 * 0.66
        )
        if hours < need_min / 60:
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
    if rise_per_hour is None:
        # No trend yet (e.g. just after a restart): do not guess; only join
        # once the primary heater has had twice the grace period.
        return heating_minutes >= grace_minutes * 2
    return rise_per_hour < min_rise


# Fan boost while heating (measured on a Qlima split unit, 6-11-2026, room =
# separate sensor): high warms 2-3x faster than medium, auto/low barely move the
# room. High while the room is more than BOOST_HIGH below the target, medium
# within that, the device's own auto once it is within BOOST_AUTO.
BOOST_HIGH = 1.0
BOOST_AUTO = 0.3
BOOST_BACKOFF = 0.2      # step down only once the deficit is this far past the threshold
BOOST_HOLD_MINUTES = 10  # a fan step stays at least this long (every command beeps)
FAN_ORDER = ("auto", "low", "medium", "high")

# Hold trim: a holding device runs on its own sensor, which can sit far from the
# room sensor. Room more than TRIM_ABOVE over the target for TRIM_MINUTES ->
# its setpoint goes TRIM_STEP lower; back once the room is under the target.
TRIM_ABOVE = 0.5
TRIM_MINUTES = 20
TRIM_STEP = 1.0

# Below this a hold is a night setback, not a hold: the device goes off. Some
# devices report a min_temp they do not honour (the Qlima via localtuya says 7
# but ignores anything under ~16, so a 12 deg hold kept it heating at 22).
HOLD_FLOOR = 16.0

# Setpoint lead while warming up: an airco regulates on its own sensor, which reads
# the warm air near the unit (Qlima, 10-11-2026: 23-25 deg while the room sensor
# read 20-21). With the plain target as setpoint it thinks it is there already and
# throttles down far below the target. While the room is more than LEAD_ON under
# the target, the setpoint goes up by the measured offset (whole degrees, at most
# LEAD_MAX); back to the plain target once the deficit is under LEAD_OFF.
# While the room stays short the lead follows a growing offset upwards once the offset
# is LEAD_STEP above it (Qlima 10/11-11-2026: lead 3, offset 5-6 after fan up and swing
# off, room stuck 0.5-1 deg under the target for hours). It never goes down on the way.
LEAD_ON = 0.5
LEAD_OFF = 0.2
LEAD_MAX = 6
LEAD_STEP = 1.0
OFFSET_ALPHA = 0.02   # per 10 s tick: about 8 min to follow a new offset
# A heating air-to-air unit whose own sensor reads this far under the room is defrosting
# (it blows cold for a few minutes; Qlima 10-11-2026: 24 -> 10 deg every ~35 min at 0-2 outside).
DEFROST_BELOW_ROOM = 1.0


def update_offset(prev: float | None, device_temp: float | None, room_temp: float | None) -> float | None:
    """Running estimate of how much warmer a heating device's own sensor reads than the room.

    Only fed while the device heats. A sample under the room temperature is a defrost
    cycle (an air-to-air heat pump blows cold for a few minutes) and is skipped.
    """
    if device_temp is None or room_temp is None:
        return prev
    sample = device_temp - room_temp
    if sample < 0:
        return prev
    if prev is None:
        return sample
    return prev + OFFSET_ALPHA * (sample - prev)


def setpoint_lead(
    room_temp: float | None,
    target: float | None,
    prev_lead: int,
    offset: float | None,
) -> int:
    """Whole degrees to add to a heating primary's setpoint (0 = the plain target).

    Every setpoint change beeps on some devices, so the lead only changes when it has
    to: it starts at the measured offset, goes up while the room stays short and the
    offset has grown ``LEAD_STEP`` past it, and drops to 0 once the room is within
    ``LEAD_OFF`` of the target.
    """
    if room_temp is None or target is None:
        return prev_lead
    deficit = target - room_temp
    wanted = int(min(max(offset, 0), LEAD_MAX) + 0.5) if offset is not None else 0
    if prev_lead:
        if deficit <= LEAD_OFF:
            return 0
        if offset is not None and offset >= prev_lead + LEAD_STEP:
            return max(prev_lead, wanted)
        return prev_lead
    if deficit > LEAD_ON and offset is not None:
        return wanted
    return 0


def fan_for(
    room_temp: float | None,
    target: float | None,
    prev_fan: str | None,
    held_minutes: float | None,
    fan_modes: list[str] | None,
) -> str | None:
    """The fan mode a heating device should run at, or None to leave it alone.

    ``prev_fan`` is the fan mode the boost chose last (None = never), and
    ``held_minutes`` how long ago that was.  Stepping *up* is immediate (a cold
    room should start warming at once); stepping *down* waits for
    ``BOOST_HOLD_MINUTES`` and an extra ``BOOST_BACKOFF`` so the fan does not
    flap around a threshold.  Only modes the device advertises are returned.
    """
    if room_temp is None or target is None or not fan_modes:
        return None
    available = [f for f in FAN_ORDER if f in fan_modes]
    if not available:
        return None
    deficit = target - room_temp
    want = "high" if deficit > BOOST_HIGH else "medium" if deficit > BOOST_AUTO else "auto"
    if prev_fan in FAN_ORDER and FAN_ORDER.index(want) < FAN_ORDER.index(prev_fan):
        held = held_minutes if held_minutes is not None else 0
        threshold = BOOST_HIGH if prev_fan == "high" else BOOST_AUTO
        if held < BOOST_HOLD_MINUTES or deficit > threshold - BOOST_BACKOFF:
            want = prev_fan
    if want not in available:
        # e.g. a device without "medium": nearest available step downwards, else upwards
        lower = [f for f in available if FAN_ORDER.index(f) <= FAN_ORDER.index(want)]
        want = lower[-1] if lower else available[0]
    return want


def hold_trim(
    room_temp: float | None,
    target: float | None,
    prev_trim: float,
    above_minutes: float | None,
) -> float:
    """Setpoint offset for a holding device (0 or -TRIM_STEP).

    ``above_minutes`` is how long the room has been more than ``TRIM_ABOVE``
    over the target (None = it is not).
    """
    if room_temp is None or target is None:
        return prev_trim
    if prev_trim:
        return 0.0 if room_temp < target else prev_trim
    if above_minutes is not None and above_minutes >= TRIM_MINUTES:
        return -TRIM_STEP
    return 0.0


def eta_minutes(room_temp: float | None, target: float | None, rise_per_hour: float | None) -> float | None:
    """Minutes until the room reaches the target at the current warming rate (None if unknown)."""
    if room_temp is None or target is None or rise_per_hour is None:
        return None
    deficit = target - room_temp
    if deficit <= 0:
        return 0.0
    if rise_per_hour < 0.2:
        return None  # flat or falling: no honest estimate
    return deficit / rise_per_hour * 60


@dataclass(frozen=True)
class DeviceCommand:
    """A desired end-state for one actuator device."""

    entity_id: str
    hvac_mode: str
    temperature: float | None = None
    fan_mode: str | None = None


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
    hold_target: float | None = None,
) -> list[DeviceCommand]:
    """Map one :class:`Decision` onto per-device commands.

    ``devices`` is a list of dicts with ``entity_id`` and optionally:

    - ``role`` (heat/cool/both, default both)
    - ``tier`` (``primary`` default, or ``support``) — heating only
    - ``park`` (``fan_only`` default, or ``off``) — what to do when not serving
    - ``supports_fan_only`` — whether ``fan_only`` is a valid mode for it
    - ``can_heat`` / ``can_cool`` — whether the device advertises that HVAC mode
    - ``available`` — False if the entity is unavailable right now
    - ``heating`` — the device currently reports ``heat`` (used for devices on
      ``manual`` that the user runs by hand)
    - ``control`` (``auto`` default, ``off`` or ``manual``) — the user's per-device
      choice.  ``manual``: hands off — the device is never commanded and never
      counted as serving.  ``off``: kept off and never used (not even as
      support), whatever its ``park`` preference.
    - ``step`` — the device's temperature step (setpoints are rounded to it)
    - ``hold`` — a primary heater that keeps heating at ``hold_target`` while
      the coordinator idles (it then modulates on its own sensor) instead of
      being parked; ``min_temp`` — a heat or hold setpoint below that is off
      instead (a hold also below ``HOLD_FLOOR``)
    - ``lead`` — whole degrees added to its heat setpoint while warming up (see
      ``setpoint_lead``), capped at ``max_temp``
    - ``fan`` — the fan mode to run at while heating or holding (None = leave it)
    - ``trim`` — setpoint offset applied to its hold setpoint (see ``hold_trim``)
    - ``off_by_hand`` — the user switched this device off outside the coordinator

    Heating: primary devices heat alone; *support* devices join only while
    ``support_active``.  If no primary device can serve (none configured,
    unavailable, or unable to heat) the support devices heat regardless, so the
    system never goes cold because the preferred heater is down.  But a primary
    heater the user switched **off by hand** means "no heating now": then no
    support device heats either, not as a stand-in and not as support (9-11-2026:
    the Qlima was switched off when leaving and the CV took over).

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
            if d.get("available", True)
            and d.get("control", "auto") == "auto"
            and _serves(d, decision.intent)
        ]
        if decision.intent == HEAT:
            primary = [d for d in candidates if d.get("tier", TIER_PRIMARY) == TIER_PRIMARY]
            support = [d for d in candidates if d.get("tier", TIER_PRIMARY) == TIER_SUPPORT]
            # A hand-operated primary that is heating right now counts as "the
            # primary is doing its job": the support heater then only joins on
            # real need, not as the sole heater.
            primary_working = bool(primary) or any(
                d.get("control") == "manual"
                and d.get("tier", TIER_PRIMARY) == TIER_PRIMARY
                and d.get("heating")
                for d in devices
            )
            chosen = primary + support if (support_active or not primary_working) else primary
            hand_off = any(
                d.get("off_by_hand") and d.get("tier", TIER_PRIMARY) == TIER_PRIMARY for d in devices
            )
            if hand_off and not primary:
                chosen = []
        else:
            chosen = candidates
        serving = {d["entity_id"] for d in chosen}

    commands: list[DeviceCommand] = []
    for dev in devices:
        entity_id = dev["entity_id"]
        control_mode = dev.get("control", "auto")

        if control_mode == DEVICE_MODE_MANUAL:
            continue  # hands off: the user operates this device
        if decision.intent == OFF or control_mode == DEVICE_MODE_OFF:
            commands.append(DeviceCommand(entity_id, OFF))
        elif entity_id in serving:
            mode = HEAT if decision.intent == HEAT else COOL
            temp = decision.target
            min_temp = dev.get("min_temp")
            if mode == HEAT and isinstance(min_temp, (int, float)) and temp is not None and temp < min_temp:
                # A setpoint below its range (e.g. a 15 deg setback on an airco that
                # does 16 at least) would be clamped up by the device: off instead.
                commands.append(DeviceCommand(entity_id, OFF))
                continue
            if mode == HEAT and temp is not None and dev.get("lead"):
                temp = temp + dev["lead"]
                max_temp = dev.get("max_temp")
                if isinstance(max_temp, (int, float)):
                    temp = min(temp, max_temp)
            commands.append(
                DeviceCommand(
                    entity_id, mode, _round_to_step(temp, dev.get("step")),
                    dev.get("fan") if mode == HEAT else None,
                )
            )
        elif (
            decision.intent == IDLE
            and hold_target is not None
            and dev.get("hold")
            and dev.get("available", True)
            and dev.get("tier", TIER_PRIMARY) == TIER_PRIMARY
            and _serves(dev, HEAT)
        ):
            # Keep a primary heater running at the target instead of cycling it
            # off and on: it modulates on its own sensor (the user runs it like
            # that by hand), the coordinator only trims the setpoint.
            temp = _round_to_step(hold_target + dev.get("trim", 0.0), dev.get("step"))
            min_temp = dev.get("min_temp")
            floor = max(min_temp, HOLD_FLOOR) if isinstance(min_temp, (int, float)) else HOLD_FLOOR
            if temp < floor:
                commands.append(DeviceCommand(entity_id, OFF))  # a setback, not a hold: off
            else:
                commands.append(DeviceCommand(entity_id, HEAT, temp, dev.get("fan")))
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
