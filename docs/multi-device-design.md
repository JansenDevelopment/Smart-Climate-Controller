# Design: multi-device coordination, per-node band, and integration-driven auto

Status: **decisions locked** — ready to implement (see §14 phasing).

This document designs three interlocking features and, importantly, the
foundational change they share. All five open questions are resolved (§15).

## 1. Goals

1. **Per-node comfort band** — each schedule node carries a *heat-to* temperature
   and a *cool-above* limit, so heating and cooling targets vary by time of day.
2. **Integration-driven auto** — Smart Climate compares the room temperature to
   that band and decides the intent (**heat / cool / idle**) itself, instead of
   handing one setpoint to a device's native auto. Configurable per instance.
3. **Multiple devices with roles** — one Smart Climate instance can command
   several climate devices, each tagged **heat**, **cool**, or **both**; the
   intent is routed to the devices that can act on it.

## 2. The shared foundation: coordinator, not mirror

Today the Smart Climate entity **mirrors a single wrapped device** (its
`hvac_mode`, `hvac_modes`, min/max, fan, etc. are read straight from that
device). Both integration-driven auto and multi-device make that impossible —
there is no longer a single device whose mode *is* Smart Climate's mode.

So Smart Climate becomes a **coordinator/brain**:

- It **owns** its own `hvac_mode` (`off` / `heat` / `cool` / `auto`), persisted.
- Wrapped devices become **actuators** it commands via `climate.set_hvac_mode`
  / `climate.set_temperature` / `climate.turn_off`.
- Its reported state (current temp, action, capabilities) is **derived/aggregated**
  from the actuators, not mirrored from one.

This reverses the mirror behavior shipped in the cooling commit. It is the
correct base for everything below and the band/decision logic is identical for
one device or five.

## 3. Data model

### Config-entry `data`

```jsonc
{
  "name": "Living Room",
  "zone_home": "zone.home",
  "devices": [
    { "entity_id": "climate.radiator", "role": "heat" },
    { "entity_id": "climate.qlima",    "role": "both" }
  ],
  "temperature_source": "mean",                       // sensor | primary | mean
  "temperature_sensor": "sensor.living_room_temp",    // used when source = sensor
  "primary_device": "climate.qlima",                  // used when source = primary
  "hysteresis": 0.3,                                   // °C, anti-flap deadband
  "integration_driven_auto": true,                    // per-instance toggle

  // heating setpoints (existing)
  "away_temperature": 14,
  "auto_temperature": 21,          // runtime, persisted
  "schedule": { ... },             // runtime, persisted (now band-capable)

  // cooling setpoints (existing)
  "cool_auto_temperature": 24,
  "cool_away_temperature": 28,

  // override defaults (existing)
  "away_delay_minutes": 5,
  "interruptible": true,
  "default_override_mode": "timer",
  "default_override_duration": 30
}
```

`role` ∈ `heat` | `cool` | `both`.

### Migration / backward compatibility

- Old entries have `wrapped_climate: "climate.x"` and no `devices`. On load,
  synthesize `devices = [{entity_id: wrapped_climate, role: "both"}]`.
- Keep reading `wrapped_climate` as the fallback; `devices` wins when present.
- `ATTR_WRAPPED_CLIMATE` stays for one-device instances; add a `devices`
  attribute (list) for the general case.

## 4. Config UX  — **decided: raise HA floor, use config subentries**

The HA floor moves to a current release (`hacs.json` / `manifest.json`
`min_version`) so we can use **config subentries**, the idiomatic way to attach a
variable-length set of things to an entry.

- **Initial config flow**: name, home zone, room-temperature source (see §8),
  and the existing optional defaults.
- **Actuator devices are subentries** — each subentry is one device: an entity
  picker (`domain: climate`) + a role select (`heat` / `cool` / `both`). Add /
  edit / remove devices from the entry's **Subentries** UI.
- Instance-level tunables (temperature-source choice, hysteresis,
  integration-driven-auto toggle) live in an **Options flow**.

The `devices` list in §3 is the runtime projection of the device subentries.
Migration (§3) still applies for pre-subentry single-device entries.

## 5. Schedule: per-node band

Node format gains an optional cooling limit:

```jsonc
{ "time": "07:00", "temp": 21, "cool_temp": 25 }
```

- `temp` — heat-to target (existing; unchanged meaning).
- `cool_temp` — cool-above limit (new, optional).
- Fallbacks when `cool_temp` is absent: `cool_auto_temperature` (home) — so old
  schedules keep working and simply use the flat cooling setpoint.

`schedule_helper` gains a pure function:

```python
get_scheduled_band(schedule, now, heat_fallback, cool_fallback) -> (heat, cool)
```

`get_scheduled_temperature` stays for the heat-only path / back-compat.

## 6. Control pipeline

Every tick / event resolves an **intent** then **routes** it. Pure decision
logic (unit-testable, no HA):

```
decide(mode, preset, presence, room_temp, band, setpoints, override) -> Decision
  # Decision = { intent: heat|cool|idle|off, target: float|None }

if mode == off:                      -> {off}
if preset is an override:
    t = override_temp
    # single target: heat or cool toward it, deadband via a small hysteresis H
    if room_temp < t - H: -> {heat, t}
    if room_temp > t + H: -> {cool, t}
    else:                 -> {idle}
if mode == heat:                     -> {heat, heat_setpoint(presence,schedule)}
if mode == cool:                     -> {cool, cool_setpoint(presence,schedule)}
if mode == auto:
    heat_target, cool_limit = band(presence, schedule)
    if room_temp < heat_target: -> {heat, heat_target}
    if room_temp > cool_limit:  -> {cool, cool_limit}
    else:                       -> {idle}
```

### Conflict prevention (no device heats while another cools)

This is guaranteed structurally, not by coordination between devices:

1. **Single global intent.** `decide()` returns exactly one intent per
   evaluation for the whole instance; `route()` applies that one intent to all
   actuators. There is no path that demands heat and cool in the same tick.
2. **Deadband.** Since `heat_target < cool_limit`, temperatures below the band
   heat, above the band cool, and inside the band are idle — no single room
   temperature satisfies both, so the system never *wants* both.
3. **Idle is not conditioning.** A `both` device at idle goes to `fan_only` /
   neutral (§6 idle rule), so it is not cooling in the background while a heater
   runs.

**Guard against misconfiguration:** validate — in the config/Options flow *and*
defensively in `decide()` — that `cool_limit >= heat_target + max(min_gap,
hysteresis)` for every schedule node and for the flat home/away setpoints
(suggested `min_gap` = 1°C). If a node violates it, reject on input; if it ever
slips through, `decide()` clamps `cool_limit = heat_target + min_gap` and logs a
warning so cooling can never be asked for below the heating target.

Routing the intent to actuators (has HA side effects):

```
route(decision, devices):
  for d in devices:
    if decision.intent == heat and d.role in (heat, both):
        set d -> hvac_mode=heat, temperature=decision.target
    elif decision.intent == cool and d.role in (cool, both):
        set d -> hvac_mode=cool, temperature=decision.target
    else:
        turn d off        # device can't serve this intent, or intent is idle/off
```

Notes:
- **Hysteresis** `H` around switch points prevents rapid heat/cool flapping.
  **Decided:** configurable per instance (Options flow), **default 0.3°C**.
- **Idle never powers a device off** (that kills the airflow on an airco).
  **Decided** idle actuation, per device:
  - device supports `fan_only` → set `hvac_mode = fan_only` (airflow, no
    heat/cool);
  - else (e.g. a radiator) → set a **neutral setpoint**: for a heat-capable
    device, the heat_target (so it coasts without overshooting); it is not
    turned off.
  Explicit coordinator `off` is the only path that actually powers devices off.
- Only issue a device call when the desired (mode, target) differs from the
  device's current state, to avoid command spam every 10 s.

## 7. Reported state (the coordinator entity)

- `hvac_modes` = `[off, heat, cool, auto]` (own set; not mirrored).
- `hvac_mode` = owned `_hvac_mode`.
- `hvac_action` = last intent → `off` / `idle` / `heating` / `cooling` (exposed
  so cards show what it's actually doing).
- `current_temperature` = room temp (see §8).
- `target_temperature` = **single** acting target (heat_target while
  heating/idle, cool_limit while cooling). **Decided:** one target, not a range;
  `heat_target` and `cool_limit` are also published as attributes so the schedule
  card can render the band itself.
- `min_temp`/`max_temp`/`step` = tightest common range across actuators
  (fallback 5 / 35 / 0.5).

## 8. Room temperature source — **decided: selectable**

A per-instance **temperature-source** setting (config/Options flow) chooses how
the room temperature is measured:

- **`sensor`** — a dedicated `sensor` entity (most accurate).
- **`primary`** — the `current_temperature` of a chosen primary actuator.
- **`mean`** — the mean of all actuators' `current_temperature` (default;
  zero extra config).

Resolution falls through to the next available option if the selected source
yields no value; if nothing is available, integration-driven auto holds the last
intent and logs a warning.

## 9. Overrides

Overrides already carry a single target temperature. In the new model an
override becomes a single-setpoint auto: heat or cool toward the override temp
(with the same hysteresis). Timer / infinity / next-node expiry and the
interruptible-on-presence logic are unchanged.

## 10. Integration-driven vs device-native auto

`integration_driven_auto` (default **true**):
- **true** → the pipeline above (works for any number of devices/roles).
- **false** → legacy single-setpoint passthrough. Only well-defined with a
  single `both` device; with multiple devices we log a warning and fall back to
  integration-driven. (Multi-device inherently needs the coordinator to decide.)

## 11. Fan mode & exotic modes

Fan mode is per-device and has no single meaning across actuators. v1:
- Expose fan passthrough **only** when there is exactly one actuator that
  supports `FAN_MODE`; otherwise omit it from the coordinator.
- `fan_only` / `dry` are not part of the coordinator's own mode set; they remain
  reachable by controlling the underlying device directly. (Revisit if needed.)

## 12. Helper entities

Unaffected in shape — they still read coordinator attributes and call services.
New candidates (later): a `select` for the coordinator HVAC mode, a `switch` for
integration-driven auto, and per-device role `select`s (Phase 3 polish).

## 13. Testing

- `schedule_helper.get_scheduled_band` — pure, table-driven tests.
- `decide(...)` — pure; exhaustive tests over mode × presence × room-vs-band ×
  override, including hysteresis edges.
- `route(...)` — with mock devices of each role, assert which get heat/cool/off
  and that no redundant calls are issued.
- **Conflict-prevention invariant** — property-style test: for any devices +
  room temp + band, the routed commands never contain both a `heat` and a `cool`
  action; and an overlapping band (`cool_limit <= heat_target`) is clamped, never
  routed as simultaneous heat+cool.
- Migration — old `wrapped_climate` entry yields one `both` device.

## 14. Phasing (after this design is signed off)

1. **Foundation + decision core** — coordinator owns mode; `devices` model +
   migration; `get_scheduled_band`; pure `decide`/`route`; wire the control loop;
   integration-driven auto toggle. (Single or multiple devices already work.)
2. **Config/Options UX** — the add/edit/remove-device Options flow + sensor +
   toggle.
3. **Schedule card** — dual-line (heat/cool) band editing on the timeline.
4. **Polish** — hvac_action in cards, per-device role selects, docs.

## 15. Resolved decisions

1. **Config UX / HA floor** (§4): **raise the floor to a current HA release** and
   model actuator devices as **config subentries**.
2. **Band target reporting** (§7): **single `target_temperature`** + band
   attributes (no range).
3. **Hysteresis** (§6): **configurable, default 0.3°C**.
4. **Room temp source** (§8): **selectable** — `sensor` / `primary` / `mean`.
5. **Idle actuation** (§6): **never power off** — `fan_only` where supported,
   else a neutral setpoint. Only explicit coordinator `off` powers devices down.
