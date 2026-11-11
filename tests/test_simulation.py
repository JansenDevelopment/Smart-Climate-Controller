"""Scenario regression tests: the real control core against the room/weather model
in tools/simulate.py.  Each scenario carries its own expectations (see check())."""

import dataclasses
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tools"))

import simulate  # noqa: E402


@pytest.mark.parametrize("name", list(simulate.scenarios()))
def test_scenario_expectations_hold(name):
    [result] = simulate.run_all([name])
    failed = [label for label, ok in simulate.check(result).values() if not ok]
    assert not failed, failed


def _run(name, **changes):
    return simulate.simulate(dataclasses.replace(simulate.scenarios()[name], **changes))


def test_support_off_never_uses_the_cv():
    r = _run("cold_snap", support_enabled=False)
    assert r["hours"]["cv"][0] == 0


def test_airco_only_is_cheaper_than_cv_only_in_autumn():
    airco = _run("autumn_week", devices="airco")
    cv = _run("autumn_week", devices="cv")
    assert airco["cost"] < cv["cost"]


def test_cooling_off_never_cools_even_on_hot_days():
    r = _run("hot_day", cooling_mode="off")
    assert r["hours"]["airco"][1] == 0


def test_coordinator_off_does_nothing():
    r = _run("cold_snap", hvac_mode="off")
    assert r["hours"]["airco"] == (0, 0) and r["hours"]["cv"] == (0, 0)


def test_manual_airco_is_left_alone():
    # hands off: the coordinator never commands it, so it never runs
    r = _run("autumn_week", device_control={"airco": ("manual", None, None)})
    assert r["hours"]["airco"] == (0, 0)


def test_export_contains_what_the_viewer_needs(tmp_path):
    import json

    out = tmp_path / "sim.json"
    simulate.export_json(simulate.run_all(["frost_morning_no_cv"]), str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    sc = data["scenarios"][0]
    assert sc["device_control"]["cv"][0] == "off"
    sample = sc["series"][0]
    for key in ("room", "out", "heat_t", "cool_t", "airco", "cv", "support_active", "allowed", "fc_today"):
        assert key in sample
