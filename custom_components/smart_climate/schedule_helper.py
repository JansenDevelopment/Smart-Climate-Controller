"""Schedule helper functions for Smart Climate Controller.

This module provides pure, HA-independent functions for resolving schedule
nodes and computing target temperatures based on the current time.  All
functions accept the schedule dict and a ``datetime`` object as arguments
so they can be unit-tested without a Home Assistant instance.

Node times are parsed as naive wall-clock times (``%H:%M``) and only their
time-of-day component is ever used, so the ``DTZ007`` suppressions below are
deliberate -- there is no date or timezone in play.
"""

import logging
from datetime import datetime, timedelta

from .const import SCHEDULE_MODE_52, SCHEDULE_MODE_DAILY, SCHEDULE_MODE_INDIVIDUAL

_LOGGER = logging.getLogger(__name__)


def get_schedule_nodes(schedule: dict | None, now: datetime) -> list:
    """Return the list of schedule nodes applicable to the current day/mode.

    Args:
        schedule: The schedule dict (may be ``None`` or empty).
        now: The current datetime used to determine the active weekday.

    Returns:
        A list of schedule node dicts for the active period, or an empty list
        when no schedule is configured or the mode is unrecognised.
    """
    if not schedule:
        return []
    schedule_mode = schedule.get("mode", SCHEDULE_MODE_DAILY)
    weekday = now.weekday()  # Monday=0 … Sunday=6
    if schedule_mode == SCHEDULE_MODE_DAILY:
        return schedule.get("daily", [])
    if schedule_mode == SCHEDULE_MODE_52:
        return schedule.get("weekday", []) if weekday < 5 else schedule.get("weekend", [])
    if schedule_mode == SCHEDULE_MODE_INDIVIDUAL:
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return schedule.get(day_names[weekday], [])
    return []


def get_scheduled_temperature(
    schedule: dict | None,
    now: datetime,
    fallback_temp: float,
) -> float:
    """Return the scheduled temperature for the current time.

    Finds the last schedule node whose time is at or before *now*.  If the
    current time is before the first node of the day the last node of the
    previous day (wrap-around) is used instead.  Falls back to
    *fallback_temp* when the schedule is absent, empty, or contains no
    valid nodes.

    Args:
        schedule: The schedule dict (may be ``None`` or empty).
        now: The current datetime used for time comparisons.
        fallback_temp: Temperature to return when no node matches.

    Returns:
        The target temperature in degrees Celsius.
    """
    if not schedule:
        return fallback_temp

    nodes = get_schedule_nodes(schedule, now)
    if not nodes:
        return fallback_temp

    def _parse_time(t: str):
        """Parse HH:MM time string; return a comparable time object."""
        try:
            return datetime.strptime(t, "%H:%M").time()  # noqa: DTZ007
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Smart Climate: invalid time format '%s' in schedule node (expected HH:MM)", t
            )
            return None

    current_time = now.time().replace(second=0, microsecond=0)

    # Sort nodes by parsed time, skipping any with invalid times
    valid_nodes = []
    for node in nodes:
        t = _parse_time(node.get("time", ""))
        if t is not None and "temp" in node:
            valid_nodes.append((t, node["temp"]))
        else:
            _LOGGER.warning(
                "Smart Climate: skipping schedule node with missing/invalid time or temp: %s",
                node,
            )

    if not valid_nodes:
        return fallback_temp

    valid_nodes.sort(key=lambda x: x[0])

    # Find the last node whose time <= current time
    target_temp = None
    for node_time, node_temp in valid_nodes:
        if node_time <= current_time:
            target_temp = node_temp

    # If no node matched (current time is before the first node), wrap around
    # to the last node of the previous day
    if target_temp is None:
        target_temp = valid_nodes[-1][1]

    return target_temp


def get_scheduled_band(
    schedule: dict | None,
    now: datetime,
    heat_fallback: float,
    cool_fallback: float,
) -> tuple[float, float]:
    """Return the ``(heat_target, cool_target)`` band for the current time.

    Uses the same "last node at or before now" resolution as
    :func:`get_scheduled_temperature` for the heat target (the node's ``temp``).
    The cool target is the node's optional ``cool_temp``; when a node omits it
    (or no schedule is configured), *cool_fallback* is used.  The heat target
    falls back to *heat_fallback*.

    Args:
        schedule: The schedule dict (may be ``None`` or empty).
        now: The current datetime used for time comparisons.
        heat_fallback: Heat target when no node supplies one.
        cool_fallback: Cool target when a node omits ``cool_temp``.

    Returns:
        A ``(heat_target, cool_target)`` tuple.
    """
    heat_target = get_scheduled_temperature(schedule, now, heat_fallback)

    if not schedule:
        return heat_target, cool_fallback

    nodes = get_schedule_nodes(schedule, now)
    if not nodes:
        return heat_target, cool_fallback

    current_time = now.time().replace(second=0, microsecond=0)

    valid = []
    for node in nodes:
        try:
            t = datetime.strptime(node.get("time", ""), "%H:%M").time()  # noqa: DTZ007
        except (ValueError, TypeError):
            continue
        valid.append((t, node))
    if not valid:
        return heat_target, cool_fallback
    valid.sort(key=lambda x: x[0])

    active_node = None
    for t, node in valid:
        if t <= current_time:
            active_node = node
    if active_node is None:
        active_node = valid[-1][1]  # wrap to previous day's last node

    cool_target = active_node.get("cool_temp", cool_fallback)
    if not isinstance(cool_target, (int, float)):
        cool_target = cool_fallback
    return heat_target, cool_target


def compute_next_node_datetime(schedule: dict | None, now: datetime) -> datetime | None:
    """Return the datetime of the next upcoming schedule node.

    Scans the active nodes for the current day and returns the next node
    whose time is strictly after *now*.  If all nodes have already passed,
    the first node of the following day is returned instead.

    Args:
        schedule: The schedule dict (may be ``None`` or empty).
        now: The current datetime used as the reference point.

    Returns:
        A :class:`datetime` for the next node, or ``None`` when no schedule
        is configured or no valid node times could be parsed.
    """
    nodes = get_schedule_nodes(schedule, now)
    if not nodes:
        return None

    def _parse_time(t: str):
        try:
            return datetime.strptime(t, "%H:%M").time()  # noqa: DTZ007
        except (ValueError, TypeError):
            return None

    current_time = now.time().replace(second=0, microsecond=0)
    valid_times = sorted(
        t for node in nodes if (t := _parse_time(node.get("time", ""))) is not None
    )
    if not valid_times:
        return None

    for node_time in valid_times:
        if node_time > current_time:
            return datetime.combine(now.date(), node_time)

    # All nodes are before current time → next node is the first one tomorrow
    return datetime.combine(now.date() + timedelta(days=1), valid_times[0])


def get_next_node_minutes(schedule: dict | None, now: datetime) -> int | None:
    """Return minutes until the next schedule node.

    Args:
        schedule: The schedule dict (may be ``None`` or empty).
        now: The current datetime used as the reference point.

    Returns:
        An integer number of minutes (≥ 0) until the next node, or ``None``
        when no schedule is configured.
    """
    next_dt = compute_next_node_datetime(schedule, now)
    if next_dt is None:
        return None
    return int(max(0, (next_dt - now).total_seconds() / 60))
