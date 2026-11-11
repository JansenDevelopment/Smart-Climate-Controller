"""Pure, HA-independent cooling policy.

Cooling in ``auto`` must not be triggered by heating overshoot (e.g. a room
that reaches 23 °C on a cold January evening), yet it *should* run in the
evening after a warm day even when it is only 16 °C outside.  So the decision
looks at the *heat load* — the forecast highs and what was actually measured
outdoors over the last 24 hours — not just at the current outdoor temperature.

``cooling_permitted`` only answers "is auto cooling allowed at all right
now?".  Whether the room is actually above the cool limit is still decided by
``control.decide``.
"""

from collections import deque
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from .const import COOLING_AUTO, COOLING_OFF, COOLING_ON

WINDOW = timedelta(hours=24)


def warm_period(highs: Iterable[float | None], threshold: float) -> bool:
    """True if any known high (forecast or observed) reaches ``threshold``."""
    return any(h is not None and h >= threshold for h in highs)


def cooling_permitted(
    setting: str,
    room_temp: float | None,
    *,
    highs: Iterable[float | None],
    warm_threshold: float,
    hard_ceiling: float,
) -> bool:
    """Decide whether auto-cooling may run right now.

    ``off``  → never; ``on`` → always.
    ``auto`` → when the room is at/above the hard ceiling, or when we are in a
    warm period (any of ``highs`` at/above ``warm_threshold``).  With no data at
    all, ``auto`` only cools above the hard ceiling.
    """
    if setting == COOLING_OFF:
        return False
    if setting == COOLING_ON:
        return True
    if setting != COOLING_AUTO:
        return False
    if room_temp is not None and room_temp >= hard_ceiling:
        return True
    return warm_period(highs, warm_threshold)


def _day_of(raw, to_local=None):
    """The calendar day of a forecast entry, in local time when possible.

    Weather integrations often give the day as a UTC timestamp
    (``2026-10-01T22:00:00+00:00`` is 2 October locally), so aware timestamps are
    converted with ``to_local`` before taking the date.
    """
    text = str(raw)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return date.fromisoformat(text[:10])
    if moment.tzinfo is not None and to_local is not None:
        moment = to_local(moment)
    return moment.date()


def parse_daily_highs(forecast, today: date, to_local=None) -> tuple[float | None, float | None]:
    """Return ``(today_high, tomorrow_high)`` from a ``weather.get_forecasts`` list.

    Items are dicts with an ISO ``datetime`` and a ``temperature`` (the day's
    high for ``daily`` forecasts).  Missing days give ``None``.
    """
    tomorrow = today + timedelta(days=1)
    found: dict[date, float] = {}
    for item in forecast or []:
        try:
            day = _day_of(item.get("datetime", ""), to_local)
            temp = float(item["temperature"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        found.setdefault(day, temp)
    return found.get(today), found.get(tomorrow)


class OutdoorMaxTracker:
    """Rolling maximum of sampled outdoor temperatures over the last 24 hours."""

    def __init__(self) -> None:
        self._samples: deque[tuple[datetime, float]] = deque()

    def record(self, now: datetime, temp: float | None) -> None:
        """Add a sample (ignored when ``temp`` is None) and drop old ones."""
        if temp is None:
            return
        self._samples.append((now, temp))
        self._prune(now)

    def _prune(self, now: datetime) -> None:
        while self._samples and now - self._samples[0][0] > WINDOW:
            self._samples.popleft()

    def max_24h(self, now: datetime) -> float | None:
        """Highest sample in the last 24 hours, or None without samples."""
        self._prune(now)
        if not self._samples:
            return None
        return max(t for _, t in self._samples)
