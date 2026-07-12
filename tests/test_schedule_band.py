"""Tests for schedule_helper.get_scheduled_band (per-node heat/cool band)."""

import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from custom_components.smart_climate.schedule_helper import get_scheduled_band


def test_no_schedule_uses_fallbacks():
    heat, cool = get_scheduled_band(None, datetime(2026, 7, 12, 8, 0), 21, 25)
    assert (heat, cool) == (21, 25)


def test_node_with_cool_temp():
    schedule = {"mode": "daily", "daily": [
        {"time": "06:00", "temp": 21, "cool_temp": 25},
        {"time": "22:00", "temp": 18, "cool_temp": 23},
    ]}
    heat, cool = get_scheduled_band(schedule, datetime(2026, 7, 12, 8, 0), 20, 26)
    assert (heat, cool) == (21, 25)
    heat2, cool2 = get_scheduled_band(schedule, datetime(2026, 7, 12, 23, 0), 20, 26)
    assert (heat2, cool2) == (18, 23)


def test_node_without_cool_temp_uses_cool_fallback():
    schedule = {"mode": "daily", "daily": [{"time": "06:00", "temp": 21}]}
    heat, cool = get_scheduled_band(schedule, datetime(2026, 7, 12, 8, 0), 20, 27)
    assert heat == 21
    assert cool == 27  # fell back


def test_before_first_node_wraps_to_last():
    schedule = {"mode": "daily", "daily": [
        {"time": "06:00", "temp": 21, "cool_temp": 25},
        {"time": "22:00", "temp": 18, "cool_temp": 23},
    ]}
    # 05:00 is before the first node → wrap to the last node of the day
    heat, cool = get_scheduled_band(schedule, datetime(2026, 7, 12, 5, 0), 20, 26)
    assert (heat, cool) == (18, 23)


def test_invalid_cool_temp_falls_back():
    schedule = {"mode": "daily", "daily": [
        {"time": "06:00", "temp": 21, "cool_temp": "warm"},
    ]}
    heat, cool = get_scheduled_band(schedule, datetime(2026, 7, 12, 8, 0), 20, 26)
    assert heat == 21 and cool == 26
