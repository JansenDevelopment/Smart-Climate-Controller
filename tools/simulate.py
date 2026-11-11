#!/usr/bin/env python
"""Offline simulation of the Smart Climate control core.

Runs the *real* ``control.py`` / ``cooling.py`` / ``schedule_helper.py`` (loaded
straight from the integration folder, no Home Assistant needed) against a simple
room + weather model, so tunables (support delta, warm threshold, hysteresis,
tiers) can be judged before they go near a real house.

    python tools/simulate.py                      # all scenarios, text summary
    python tools/simulate.py -s hot_day           # one scenario
    python tools/simulate.py --report sim.html    # + self-contained HTML report
    python tools/simulate.py --sweep              # support-delta / tier comparison

The model is deliberately simple (one thermal mass, an inverter airco with a
COP that falls with the outdoor temperature, an on/off CV) — it is for
comparing settings and catching logic mistakes, not for predicting kWh.
"""

from __future__ import annotations

import argparse
import importlib
import math
import pathlib
import sys
import types
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components" / "smart_climate"


def load_core():
    """Import the pure modules without importing the HA-dependent package."""
    name = "smart_climate_core"
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules[name] = pkg
    return {m: importlib.import_module(f"{name}.{m}")
            for m in ("const", "schedule_helper", "control", "cooling")}


CORE = load_core()
control, cooling, schedule_helper, const = (
    CORE["control"], CORE["cooling"], CORE["schedule_helper"], CORE["const"]
)

# ---------------------------------------------------------------------------
# Model parameters
# ---------------------------------------------------------------------------
C_KWH_PER_K = 3.0          # thermal mass of the heated space
UA_KW_PER_K = 0.15         # heat loss to outdoors
STEP_MIN = 1               # simulation step (the real loop runs every 10 s)
EL_PRICE = 0.30            # €/kWh electricity
GAS_PRICE_PER_KWH = 0.123  # €/kWh of gas (≈ €1.20/m³)
CV_EFFICIENCY = 0.9


def airco_cop(t_out: float) -> float:
    """Heating COP falls with the outdoor temperature; cooling COP is flat-ish."""
    return max(1.8, min(4.5, 2.0 + 0.1 * (t_out + 7.0)))


@dataclass
class DeviceSim:
    """A climate device with its own (simple) thermostat."""

    name: str
    thermal_kw: float
    kind: str                       # "airco" | "cv"
    modes: tuple = ("off", "heat")
    step: float = 0.5
    mode: str = "off"
    setpoint: float | None = None
    on: bool = False                # cv relay state
    commanded_changes: int = 0
    run_min_heat: float = 0.0
    run_min_cool: float = 0.0
    last_fraction: float = 0.0
    energy_el: float = 0.0
    energy_gas: float = 0.0

    def fraction(self, room: float) -> tuple[str, float]:
        """('heat'|'cool'|'idle', 0..1 output fraction) given the room temp."""
        if self.setpoint is None or self.mode in ("off", "fan_only"):
            self.on = False
            return "idle", 0.0
        if self.kind == "airco":  # inverter: modulates smoothly around the setpoint
            if self.mode == "heat":
                return "heat", max(0.0, min(1.0, (self.setpoint + 0.2 - room) / 0.5))
            if self.mode == "cool":
                return "cool", max(0.0, min(1.0, (room - (self.setpoint - 0.2)) / 0.5))
            return "idle", 0.0
        # CV: on/off with 0.5 °C hysteresis
        if self.mode == "heat":
            if room < self.setpoint - 0.0:
                self.on = True
            elif room >= self.setpoint + 0.5:
                self.on = False
            return ("heat", 1.0) if self.on else ("idle", 0.0)
        return "idle", 0.0


@dataclass
class Scenario:
    name: str
    title: str
    start: date
    days: int
    t_mean: float                   # mean outdoor temperature
    t_amp: float                    # daily amplitude (peak ~15:00)
    sun_kw: float                   # solar gain at noon, kW into the room
    t0: float = 19.0
    start_hour: float = 0.0         # begin the run at this hour of the first day
    # per device kind ("airco"/"cv"): (mode, from_iso|None, until_iso|None); mode auto|off|manual
    device_control: dict = field(default_factory=dict)
    day_offsets: tuple = ()         # per-day outdoor offsets (weather changes)
    cooling_mode: str = "auto"
    hvac_mode: str = "auto"         # coordinator mode: "auto" | "off"
    support_enabled: bool = True
    support_delta: float = const.DEFAULT_SUPPORT_DELTA
    support_grace: float = const.DEFAULT_SUPPORT_GRACE_MIN
    support_min_rise: float = const.DEFAULT_SUPPORT_MIN_RISE
    support_release: float = control.SUPPORT_RELEASE_FRACTION
    hysteresis: float = const.DEFAULT_HYSTERESIS
    warm_threshold: float = const.DEFAULT_WARM_THRESHOLD
    hard_ceiling: float = const.DEFAULT_HARD_CEILING
    devices: str = "airco+cv"       # "airco+cv" | "cv" | "airco"
    forecast: bool = True
    notes: str = ""
    expect: dict = field(default_factory=dict)


SCHEDULE = {  # the user's real 5/2 schedule
    "mode": "5/2",
    "weekday": [{"time": "07:03", "temp": 20}, {"time": "22:00", "temp": 14}],
    "weekend": [{"time": "08:00", "temp": 20}, {"time": "22:29", "temp": 14}],
}
AUTO_TEMP, AWAY_TEMP = 21.0, 12.0
COOL_HOME, COOL_AWAY = 24.0, 28.0
AWAY_DELAY_MIN = 10


def occupied(now: datetime) -> bool:
    """Weekdays: away 08:00–17:30; weekends: home all day."""
    if now.weekday() >= 5:
        return True
    h = now.hour + now.minute / 60
    return not (8.0 <= h < 17.5)


def outdoor(sc: Scenario, now: datetime) -> float:
    h = now.hour + now.minute / 60
    day = (now.date() - sc.start).days
    off = sc.day_offsets[day] if day < len(sc.day_offsets) else 0.0
    return sc.t_mean + off + sc.t_amp * math.cos(2 * math.pi * (h - 15) / 24)


def sun_gain(sc: Scenario, now: datetime) -> float:
    h = now.hour + now.minute / 60
    if not 6 <= h <= 20:
        return 0.0
    return sc.sun_kw * math.sin(math.pi * (h - 6) / 14)


def daily_high(sc: Scenario, d: date) -> float:
    day = (d - sc.start).days
    off = sc.day_offsets[day] if 0 <= day < len(sc.day_offsets) else 0.0
    return sc.t_mean + off + sc.t_amp


def control_for(sc: Scenario, kind: str, t: datetime) -> str:
    """The per-device control mode (auto/off/manual) in effect at time t."""
    entry = sc.device_control.get(kind)
    if not entry:
        return "auto"
    mode, frm, until = entry
    if frm and t < datetime.fromisoformat(frm):
        return "auto"
    if until and t >= datetime.fromisoformat(until):
        return "auto"
    return mode


def build_devices(kind: str):
    airco = DeviceSim("Airco", 2.5, "airco", modes=("off", "heat", "cool", "fan_only"), step=1)
    cv = DeviceSim("CV", 6.0, "cv", modes=("off", "heat"), step=0.5)
    cfg = {
        "airco+cv": ([airco, cv], [
            {"entity_id": "airco", "role": "both", "tier": "primary", "park": "off"},
            {"entity_id": "cv", "role": "heat", "tier": "support", "park": "off"}]),
        "cv": ([cv], [{"entity_id": "cv", "role": "heat", "tier": "primary", "park": "off"}]),
        "airco": ([airco], [{"entity_id": "airco", "role": "both", "tier": "primary", "park": "off"}]),
    }[kind]
    return cfg


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate(sc: Scenario) -> dict:
    devs, dev_cfg = build_devices(sc.devices)
    by_id = {("airco" if d.kind == "airco" else "cv"): d for d in devs}
    tracker = cooling.OutdoorMaxTracker()
    t = datetime.combine(sc.start, datetime.min.time()) + timedelta(hours=sc.start_hour)
    end = t + timedelta(days=sc.days)
    room = sc.t0

    presence = "home"
    away_since = None
    trend = control.RoomTrend()
    heat_since = None
    stable_since = t
    last_key = None
    intent = None
    support_active = False
    series = []          # one point per 5 min
    stats = {
        "switches": {d.kind: 0 for d in devs},
        "cool_min": 0, "cool_while_gate_closed": 0, "simultaneous": 0,
        "home_cold_min": 0, "steady_cold_min": 0, "home_min": 0, "t_max": -99.0, "t_min": 99.0,
        "heat_ctrl_min": 0, "cool_ctrl_min": 0, "support_min": 0,
        "t_sum": 0.0, "steps": 0, "overshoot_min": 0,
    }

    while t < end:
        occ = occupied(t)
        if occ:
            presence, away_since = "home", None
        elif presence == "home":
            away_since = away_since or t
            if (t - away_since).total_seconds() >= AWAY_DELAY_MIN * 60:
                presence = "away"

        # --- coordinator -----------------------------------------------
        if presence == "home":
            heat_t, cool_t = schedule_helper.get_scheduled_band(
                SCHEDULE, t, AUTO_TEMP, COOL_HOME)
        else:
            heat_t, cool_t = AWAY_TEMP, COOL_AWAY

        key = (presence, heat_t)
        if key != last_key:
            last_key, stable_since = key, t

        t_out = outdoor(sc, t)
        if t.minute % 10 == 0:
            tracker.record(t, t_out)
        highs = [
            daily_high(sc, t.date()) if sc.forecast else None,
            daily_high(sc, t.date() + timedelta(days=1)) if sc.forecast else None,
            tracker.max_24h(t),
        ]
        allowed = cooling.cooling_permitted(
            sc.cooling_mode, room, highs=highs,
            warm_threshold=sc.warm_threshold, hard_ceiling=sc.hard_ceiling)
        decision = control.decide(
            mode=sc.hvac_mode, room_temp=room, heat_target=heat_t, cool_target=cool_t,
            prev_intent=intent, hysteresis=sc.hysteresis, cooling_allowed=allowed)
        if decision.intent == control.HEAT:
            if intent != control.HEAT or heat_since is None:
                heat_since = t
        else:
            heat_since = None
        trend.record(t, room)
        intent = decision.intent
        if sc.support_enabled and intent == control.HEAT:
            support_active = control.support_needed(
                room, decision.target if decision.target is not None else heat_t,
                sc.support_delta, support_active,
                heating_minutes=(t - heat_since).total_seconds() / 60 if heat_since else None,
                rise_per_hour=trend.rise_per_hour(since=heat_since, min_span_minutes=10),
                grace_minutes=sc.support_grace,
                min_rise=sc.support_min_rise, release_fraction=sc.support_release)
        else:
            support_active = False

        caps = []
        for cfg in dev_cfg:
            d = by_id[cfg["entity_id"]]
            caps.append({**cfg, "control": control_for(sc, cfg["entity_id"], t),
                         "supports_fan_only": "fan_only" in d.modes,
                         "can_heat": "heat" in d.modes, "can_cool": "cool" in d.modes,
                         "step": d.step, "available": True})
        for cmd in control.plan_routes(decision, caps, support_active=support_active):
            d = by_id[cmd.entity_id]
            if d.mode != cmd.hvac_mode:
                d.mode = cmd.hvac_mode
                stats["switches"][d.kind] += 1
                d.commanded_changes += 1
            if cmd.temperature is not None:
                d.setpoint = cmd.temperature

        # --- physics ---------------------------------------------------
        dt_h = STEP_MIN / 60
        heat_kw = cool_kw = 0.0
        kinds_active = set()
        for d in devs:
            what, frac = d.fraction(room)
            if what == "heat" and frac > 0:
                kw = d.thermal_kw * frac
                heat_kw += kw
                d.run_min_heat += STEP_MIN * frac
                kinds_active.add("heat")
                if d.kind == "airco":
                    d.energy_el += kw / airco_cop(t_out) * dt_h
                else:
                    d.energy_gas += kw / CV_EFFICIENCY * dt_h
            elif what == "cool" and frac > 0:
                kw = d.thermal_kw * frac
                cool_kw += kw
                d.run_min_cool += STEP_MIN * frac
                kinds_active.add("cool")
                d.energy_el += kw / 3.5 * dt_h
            d.last_fraction = frac if what != "idle" else 0.0
        if "heat" in kinds_active and "cool" in kinds_active:
            stats["simultaneous"] += 1

        gain = sun_gain(sc, t) + (0.15 if occ else 0.05)  # sun + people/appliances
        q = UA_KW_PER_K * (t_out - room) + gain + heat_kw - cool_kw
        room += q / C_KWH_PER_K * dt_h

        # --- stats -----------------------------------------------------
        stats["steps"] += 1
        stats["t_sum"] += room
        stats["t_max"], stats["t_min"] = max(stats["t_max"], room), min(stats["t_min"], room)
        if cool_kw > 0:
            stats["cool_min"] += STEP_MIN
            if not allowed:
                stats["cool_while_gate_closed"] += STEP_MIN
        if intent == control.HEAT:
            stats["heat_ctrl_min"] += STEP_MIN
        if support_active:
            stats["support_min"] += STEP_MIN
        if presence == "home":
            stats["home_min"] += STEP_MIN
            if room < heat_t - 1.0:
                stats["home_cold_min"] += STEP_MIN
                if (t - stable_since).total_seconds() >= 2 * 3600:
                    stats["steady_cold_min"] += STEP_MIN
        if room > cool_t:
            stats["overshoot_min"] += STEP_MIN

        if t.minute % 5 == 0:
            series.append({
                "t": t, "room": room, "out": t_out, "heat_t": heat_t, "cool_t": cool_t,
                "airco": by_id["airco"].mode if "airco" in by_id else "-",
                "cv": by_id["cv"].mode if "cv" in by_id else "-",
                "airco_f": by_id["airco"].last_fraction if "airco" in by_id else 0.0,
                "cv_f": by_id["cv"].last_fraction if "cv" in by_id else 0.0,
                "allowed": allowed, "presence": presence, "intent": intent,
                "support_active": support_active,
                "fc_today": highs[0], "fc_tomorrow": highs[1], "out_max_24h": highs[2],
                "rise": trend.rise_per_hour(),
                "airco_sp": by_id["airco"].setpoint if "airco" in by_id else None,
                "cv_sp": by_id["cv"].setpoint if "cv" in by_id else None,
            })
        t += timedelta(minutes=STEP_MIN)

    el = sum(d.energy_el for d in devs)
    gas = sum(d.energy_gas for d in devs)
    days = max(1, sc.days)
    result = {
        "scenario": sc, "series": series, "stats": stats,
        "kwh_el": el, "kwh_gas": gas,
        "cost": el * EL_PRICE + gas * GAS_PRICE_PER_KWH,
        "cost_per_day": (el * EL_PRICE + gas * GAS_PRICE_PER_KWH) / days,
        "t_mean": stats["t_sum"] / max(1, stats["steps"]),
        "hours": {d.kind: (d.run_min_heat / 60, d.run_min_cool / 60) for d in devs},
        "switches_per_day": {k: v / days for k, v in stats["switches"].items()},
    }
    return result


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
Y, M = 2027, 1


def scenarios() -> dict[str, Scenario]:
    s = {}
    s["winter_week"] = Scenario(
        "winter_week", "Winterweek (0–6 °C)", date(Y, 1, 11), 7, 3.0, 3.0, 0.3, t0=17.0,
        notes="Normale winter: de airco moet het meeste doen, de CV alleen bij echte vraag.")
    s["autumn_week"] = Scenario(
        "autumn_week", "Herfstweek (9–17 °C)", date(Y, 10, 11), 7, 13.0, 4.0, 0.5, t0=20.0,
        day_offsets=(0, 1, -2, -1, 2, 0, -1),
        notes="De situatie van nu: airco verwarmt, CV hoeft niet mee.")
    s["cold_snap"] = Scenario(
        "cold_snap", "Vorstperiode (−8…−2 °C)", date(Y, 2, 8), 4, -5.0, 3.0, 0.2, t0=17.0,
        notes="Airco (2,5 kW) haalt het verlies niet meer: de CV moet bijspringen.")
    s["winter_overshoot"] = Scenario(
        "winter_overshoot", "Winterzon: overshoot door zon", date(Y, 1, 18), 3, 5.0, 2.0, 5.3, t0=21.0,
        notes="Zon door de ramen drijft de kamer boven 24 °C. Dat mag NIET tot koelen leiden.")
    s["hot_day"] = Scenario(
        "hot_day", "Warme dagen (16–30 °C), koelen auto", date(Y, 7, 12), 3, 23.0, 7.0, 1.8, t0=23.0,
        notes="Avondkoeling na een warme dag moet werken, ook al is het buiten 16–20 °C.")
    s["hot_day_off"] = Scenario(
        "hot_day_off", "Warme dagen, koelen uit", date(Y, 7, 12), 3, 23.0, 7.0, 1.8, t0=23.0,
        cooling_mode="off", notes="Met koelen op Uit mag er nooit gekoeld worden.")
    s["cool_spring_overshoot"] = Scenario(
        "cool_spring_overshoot", "Koude dag, kamer warm (geen warme periode)", date(Y, 3, 15), 3, 7.0, 3.0, 4.6, t0=22.0,
        notes="Lentezon: kamer 25 °C maar buiten 4–10 °C: geen warme periode, dus niet koelen.")
    s["frost_morning"] = Scenario(
        "frost_morning", "Vorstochtend, over een uur weg (07:00, 16 °C)", date(Y, 2, 8), 1, -4.0, 2.0, 0.0,
        t0=16.0, start_hour=7.0,
        notes="Normaal: Qlima en CV mogen allebei. Je ziet wat de CV in dat uur toevoegt.")
    s["frost_morning_no_cv"] = Scenario(
        "frost_morning_no_cv", "Vorstochtend, geen CV tot 10:00", date(Y, 2, 8), 1, -4.0, 2.0, 0.0,
        t0=16.0, start_hour=7.0,
        device_control={"cv": ("off", "2027-02-08T07:00:00", "2027-02-08T10:00:00")},
        notes="'Geen CV tot morgenochtend' / 'Ik ga zo weg': alleen de Qlima werkt, daarna is de CV weer auto.")
    return s


def summarize(r: dict) -> str:
    sc, st = r["scenario"], r["stats"]
    h = r["hours"]
    a = h.get("airco", (0, 0))
    c = h.get("cv", (0, 0))
    return (
        f"{sc.title}\n"
        f"  kamer {st['t_min']:.1f}…{st['t_max']:.1f} °C (gem {r['t_mean']:.1f}) | "
        f"te koud thuis (>1°): {st['home_cold_min']/60:.1f} u waarvan {st['steady_cold_min']/60:.1f} u na ≥2 u stabiel doel | boven koelplafond: {st['overshoot_min']/60:.1f} u\n"
        f"  airco: {a[0]:.0f} u verwarmen, {a[1]:.0f} u koelen | CV: {c[0]:.0f} u | CV-ondersteuning actief {st['support_min']/60:.0f} u\n"
        f"  schakelingen/dag: {', '.join(f'{k} {v:.1f}' for k, v in r['switches_per_day'].items())} | "
        f"koelen bij gesloten poort: {st['cool_while_gate_closed']} min | tegelijk stoken+koelen: {st['simultaneous']}\n"
        f"  energie: {r['kwh_el']:.0f} kWh elektra + {r['kwh_gas']:.0f} kWh gas = € {r['cost']:.2f} (€ {r['cost_per_day']:.2f}/dag)"
    )


# ---------------------------------------------------------------------------
# HTML report (self-contained, inline SVG)
# ---------------------------------------------------------------------------

def _svg(r: dict, w=980, h=300) -> str:
    sc, series = r["scenario"], r["series"]
    gl, gr, gt, gb = 44, w - 12, 12, h - 54
    tmin, tmax = -10, 32
    t0 = series[0]["t"]
    total_h = sc.days * 24

    def x(t):
        return gl + ((t - t0).total_seconds() / 3600) / total_h * (gr - gl)

    def y(v):
        return gb - (v - tmin) / (tmax - tmin) * (gb - gt)

    def path(key, step=False):
        pts = []
        for p in series:
            pts.append(f"{x(p['t']):.1f},{y(p[key]):.1f}")
        return "M" + " L".join(pts)

    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for v in range(-10, 33, 5):
        out.append(f'<line x1="{gl}" x2="{gr}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#d3d1c7" stroke-width="0.5"/>')
        out.append(f'<text x="{gl-6}" y="{y(v)+4:.1f}" text-anchor="end" font-size="11" fill="#5f5e5a">{v}°</text>')
    for d in range(sc.days + 1):
        xx = gl + d * 24 / total_h * (gr - gl)
        out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{gt}" y2="{gb}" stroke="#b4b2a9" stroke-width="0.7"/>')
        if d < sc.days:
            lab = (sc.start + timedelta(days=d)).strftime("%a %d-%m")
            out.append(f'<text x="{xx+4:.1f}" y="{gb+14}" font-size="11" fill="#5f5e5a">{lab}</text>')
    out.append(f'<line x1="{gl}" x2="{gr}" y1="{y(sc.hard_ceiling):.1f}" y2="{y(sc.hard_ceiling):.1f}" stroke="#e24b4a" stroke-width="1.2" stroke-dasharray="2,4"/>')
    out.append(f'<path d="{path("cool_t")}" fill="none" stroke="#378add" stroke-width="1" stroke-dasharray="6,4" opacity="0.7"/>')
    out.append(f'<path d="{path("out")}" fill="none" stroke="#888780" stroke-width="1.2"/>')
    out.append(f'<path d="{path("heat_t")}" fill="none" stroke="#ba7517" stroke-width="1.6"/>')
    out.append(f'<path d="{path("room")}" fill="none" stroke="#1d9e75" stroke-width="2"/>')
    # activity strips
    def strip(row, getter, color, label):
        yy = gb + 22 + row * 9
        run = None
        for p in series + [None]:
            on = bool(p) and getter(p)
            if on and run is None:
                run = p["t"]
            if (not on) and run is not None:
                t_end = p["t"] if p else series[-1]["t"]
                out.append(f'<rect x="{x(run):.1f}" y="{yy}" width="{max(0.8, x(t_end)-x(run)):.1f}" height="7" fill="{color}"/>')
                run = None
        out.append(f'<text x="{gl-6}" y="{yy+7}" text-anchor="end" font-size="10" fill="#5f5e5a">{label}</text>')
    strip(0, lambda p: p["airco"] == "heat" and p["airco_f"] > 0, "#ba7517", "airco")
    strip(1, lambda p: p["airco"] == "cool" and p["airco_f"] > 0, "#378add", "koel")
    strip(2, lambda p: p["cv"] == "heat" and p["cv_f"] > 0, "#a32d2d", "CV")
    out.append("</svg>")
    return "".join(out)


def html_report(results: list[dict]) -> str:
    rows = []
    for r in results:
        sc, st = r["scenario"], r["stats"]
        verdict = []
        for key, (label, ok) in check(r).items():
            verdict.append(f'<li style="color:{"#3b6d11" if ok else "#a32d2d"}">{"✓" if ok else "✗"} {label}</li>')
        rows.append(f"""
<section style="margin:0 0 36px">
<h2 style="font-size:18px;font-weight:500;margin:0 0 4px">{sc.title}</h2>
<p style="margin:0 0 8px;color:#5f5e5a">{sc.notes}</p>
{_svg(r)}
<div style="font-size:12px;color:#5f5e5a;margin:2px 0 8px">
<span style="color:#1d9e75">━</span> kamer &nbsp; <span style="color:#ba7517">━</span> stookdoel &nbsp;
<span style="color:#378add">┅</span> koelplafond &nbsp; <span style="color:#e24b4a">┈</span> hard plafond &nbsp; <span style="color:#888780">━</span> buiten</div>
<pre style="font-size:12px;background:#f1efe8;padding:10px;border-radius:8px;white-space:pre-wrap">{summarize(r).split(chr(10),1)[1]}</pre>
<ul style="list-style:none;padding:0;margin:0;font-size:13px">{''.join(verdict)}</ul>
</section>""")
    return f"""<!doctype html><meta charset="utf-8"><title>Smart Climate simulatie</title>
<body style="font-family:system-ui,sans-serif;max-width:1020px;margin:24px auto;padding:0 16px;color:#2c2c2a;background:#fff">
<h1 style="font-size:22px;font-weight:500">Smart Climate simulatie</h1>
<p style="color:#5f5e5a">De echte <code>control.py</code>, <code>cooling.py</code> en <code>schedule_helper.py</code> tegen een eenvoudig kamer- en weermodel. Je 5/2-schema, afwezig 08:00–17:30 op werkdagen.</p>
{''.join(rows)}</body>"""


# ---------------------------------------------------------------------------
# Expectations (also used by tests/test_simulation.py)
# ---------------------------------------------------------------------------

def check(r: dict) -> dict:
    sc, st = r["scenario"], r["stats"]
    a_heat, a_cool = r["hours"].get("airco", (0, 0))
    cv_heat = r["hours"].get("cv", (0, 0))[0]
    days = sc.days
    res = {
        "invariant": ("nooit tegelijk stoken en koelen", st["simultaneous"] == 0),
        "gate": ("nooit koelen terwijl het beleid dat niet toestaat", st["cool_while_gate_closed"] == 0),
        "flap": ("airco schakelt niet vaker dan 12×/dag", r["switches_per_day"].get("airco", 0) <= 12),
    }
    if sc.name == "winter_week":
        res["no_cool"] = ("geen koelen in de winter", a_cool == 0)
        res["airco_main"] = ("airco doet het meeste stookwerk (CV < de helft van de airco-uren)", cv_heat < a_heat / 2)
        res["floor"] = ("kamer zakt nooit onder 10 °C", st["t_min"] > 10)
    if sc.name == "autumn_week":
        res["no_cool"] = ("geen koelen in de herfst", a_cool == 0)
        res["cv_rare"] = ("CV is zelden nodig (<10 u in de week)", cv_heat < 10)
    if sc.name == "cold_snap":
        res["cv_joins"] = ("CV springt bij als de airco het niet haalt", cv_heat > 1)
        res["floor"] = ("kamer zakt nooit onder 10 °C", st["t_min"] > 10)
        res["no_cool"] = ("geen koelen bij vorst", a_cool == 0)
    if sc.name == "winter_overshoot":
        res["overshoot_happened"] = ("kamer kwam boven het koelplafond (test is zinvol)", st["overshoot_min"] > 30)
        res["no_cool"] = ("overshoot leidt niet tot koelen", a_cool == 0)
    if sc.name == "cool_spring_overshoot":
        res["no_cool"] = ("geen koelen bij overshoot op een koude dag", a_cool == 0)
    if sc.name == "hot_day":
        res["cools"] = ("er wordt gekoeld op warme dagen", a_cool > 1)
        res["evening"] = ("er wordt 's avonds gekoeld terwijl het buiten koeler is dan binnen",
                          any(p["airco"] == "cool" and p["airco_f"] > 0 and p["t"].hour >= 19
                              and p["out"] < p["room"] - 3 for p in r["series"]))
        res["no_heat"] = ("geen verwarmen in de zomer", r["hours"].get("airco", (0, 0))[0] == 0 and cv_heat == 0)
    if sc.name == "frost_morning_no_cv":
        cut = datetime(2027, 2, 8, 10, 0)
        res["cv_paused"] = ("CV stookt niet zolang de pauze loopt (tot 10:00)",
                            not any(p["cv"] == "heat" and p["cv_f"] > 0 for p in r["series"] if p["t"] < cut))
        res["airco_works"] = ("de Qlima doet het stookwerk tijdens de pauze",
                              any(p["airco"] == "heat" and p["airco_f"] > 0 for p in r["series"] if p["t"] < cut))
    if sc.name == "frost_morning":
        res["cv_helps"] = ("zonder pauze springt de CV bij in de vorst",
                           any(p["cv"] == "heat" and p["cv_f"] > 0 for p in r["series"][:36]))
    if sc.name == "hot_day_off":
        res["no_cool"] = ("met koelen uit wordt nooit gekoeld", a_cool == 0)
    return res


def export_json(results: list[dict], path: str) -> None:
    """Write the scenarios + time series for the card preview viewer."""
    import json
    out = {"schedule": SCHEDULE, "scenarios": []}
    for r in results:
        sc = r["scenario"]
        out["scenarios"].append({
            "name": sc.name, "title": sc.title, "notes": sc.notes, "devices": sc.devices,
            "cooling_mode": sc.cooling_mode, "hvac_mode": sc.hvac_mode, "support_enabled": sc.support_enabled,
            "support_grace": sc.support_grace, "support_min_rise": sc.support_min_rise, "hysteresis": sc.hysteresis,
            "support_delta": sc.support_delta, "warm_threshold": sc.warm_threshold,
            "hard_ceiling": sc.hard_ceiling, "auto_temp": AUTO_TEMP, "away_temp": AWAY_TEMP,
            "cool_home": COOL_HOME, "cool_away": COOL_AWAY,
            "start": sc.start.isoformat(), "days": sc.days,
            "device_control": {k: list(v) for k, v in sc.device_control.items()},
            "summary": summarize(r).split(chr(10), 1)[1],
            "checks": [[label, ok] for label, ok in check(r).values()],
            "series": [{
                "t": p["t"].isoformat(timespec="minutes"),
                "room": round(p["room"], 2), "out": round(p["out"], 1),
                "heat_t": p["heat_t"], "cool_t": p["cool_t"],
                "airco": p["airco"], "cv": p["cv"],
                "airco_f": round(p["airco_f"], 2), "cv_f": round(p["cv_f"], 2),
                "allowed": p["allowed"], "presence": p["presence"], "intent": p["intent"],
                "support_active": p["support_active"],
                "fc_today": p["fc_today"], "fc_tomorrow": p["fc_tomorrow"],
                "out_max_24h": None if p["out_max_24h"] is None else round(p["out_max_24h"], 1),
                "rise": None if p["rise"] is None else round(p["rise"], 2),
                "airco_sp": p["airco_sp"], "cv_sp": p["cv_sp"],
            } for p in r["series"]],
        })
    pathlib.Path(path).write_text(json.dumps(out), encoding="utf-8")


def run_all(names=None):
    sc = scenarios()
    names = names or list(sc)
    return [simulate(sc[n]) for n in names]


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------

def sweep():
    from dataclasses import replace
    base = scenarios()
    print("\n== Ondersteuning (CV) springt bij onder doel met X °C ==")
    print(f"{'scenario':<14}{'delta':>6}{'CV-uren':>9}{'te koud thuis (u)':>19}{'€/dag':>8}")
    for key in ("winter_week", "cold_snap"):
        for delta in (0.5, 1.0, 1.5, 2.5, 4.0):
            r = simulate(replace(base[key], support_delta=delta))
            print(f"{key:<14}{delta:>6}{r['hours']['cv'][0]:>9.1f}{r['stats']['home_cold_min']/60:>19.1f}{r['cost_per_day']:>8.2f}")
        r = simulate(replace(base[key], support_enabled=False))
        print(f"{key:<14}{'uit':>6}{r['hours']['cv'][0]:>9.1f}{r['stats']['home_cold_min']/60:>19.1f}{r['cost_per_day']:>8.2f}")
    print("\n== Alleen CV  vs  alleen airco  vs  airco + CV ==")
    print(f"{'scenario':<14}{'opstelling':<12}{'te koud (u)':>12}{'kWh el':>8}{'kWh gas':>9}{'€/dag':>8}")
    for key in ("autumn_week", "winter_week", "cold_snap"):
        for dev in ("cv", "airco", "airco+cv"):
            r = simulate(replace(base[key], devices=dev))
            print(f"{key:<14}{dev:<12}{r['stats']['home_cold_min']/60:>12.1f}{r['kwh_el']:>8.0f}{r['kwh_gas']:>9.0f}{r['cost_per_day']:>8.2f}")
    print("\n== Warmtedrempel voor automatisch koelen ==")
    print(f"{'drempel':>8}{'koeluren hot_day':>18}{'koeluren lente-overshoot':>26}")
    for thr in (18, 20, 22, 24, 26):
        a = simulate(replace(base["hot_day"], warm_threshold=thr))
        b = simulate(replace(base["cool_spring_overshoot"], warm_threshold=thr))
        print(f"{thr:>8}{a['hours']['airco'][1]:>18.1f}{b['hours']['airco'][1]:>26.1f}")
    print("\n== Hysterese ==")
    print(f"{'hysterese':>10}{'airco-schakelingen/dag':>24}{'kamer min/max (winter)':>26}")
    for hy in (0.2, 0.3, 0.5, 0.8, 1.2):
        r = simulate(replace(base["winter_week"], hysteresis=hy))
        print(f"{hy:>10}{r['switches_per_day']['airco']:>24.1f}{r['stats']['t_min']:>14.1f}/{r['stats']['t_max']:.1f}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--scenario", action="append", help="scenario name (repeatable); default all")
    ap.add_argument("--report", help="write a self-contained HTML report to this path")
    ap.add_argument("--sweep", action="store_true", help="compare settings (support delta, devices, thresholds, hysteresis)")
    ap.add_argument("--export", help="write scenarios + time series as JSON (for tools/card-preview/viewer.html)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    if args.list:
        for k, v in scenarios().items():
            print(f"{k:<24}{v.title}")
        return 0
    results = run_all(args.scenario)
    failed = 0
    for r in results:
        print(summarize(r))
        for _k, (label, ok) in check(r).items():
            print(f"    [{'ok' if ok else 'FAIL'}] {label}")
            failed += 0 if ok else 1
        print()
    if args.sweep:
        sweep()
    if args.export:
        export_json(results, args.export)
        print(f"export: {args.export}")
    if args.report:
        pathlib.Path(args.report).write_text(html_report(results), encoding="utf-8")
        print(f"report: {args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
