# Design: multi-device coordination, per-node band, and integration-driven auto

Status: **proposed** — for review before implementation.

This document designs three interlocking features and, importantly, the
foundational change they share. Decisions marked **[OPEN]** need sign-off; the
rest are recommendations with rationale.

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
  "temperature_sensor": "sensor.living_room_temp",   // optional override
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

## 4. Config UX  **[OPEN]**

HA **config subentries** would be the natural fit but require a newer HA than
our current floor (`hacs.json` → `2023.1.0`). Recommendation:

- **Initial config flow** (unchanged shape): name, home zone, **one** device
  (defaults to role `both`), and the existing optional defaults.
- **Options flow** manages everything after: a menu to **add device / edit
  device / remove device** (entity picker + role select), set the optional
  temperature sensor, and toggle integration-driven auto.

Alternative if we raise the HA floor: model each actuator as a **config
subentry**. Cleaner device/entity association, but drops <2024.x support.

→ **Decision needed:** keep the 2023.1 floor + Options-flow list, or raise the
floor and use subentries.

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
- A small **hysteresis** `H` (e.g. 0.3°C) around switch points prevents rapid
  heat/cool flapping. **[OPEN]** default value / make it configurable?
- Only issue a device call when the desired (mode, target) differs from the
  device's current state, to avoid command spam every 10 s.

## 7. Reported state (the coordinator entity)

- `hvac_modes` = `[off, heat, cool, auto]` (own set; not mirrored).
- `hvac_mode` = owned `_hvac_mode`.
- `hvac_action` = last intent → `off` / `idle` / `heating` / `cooling` (exposed
  so cards show what it's actually doing).
- `current_temperature` = room temp (see §8).
- `target_temperature` = the acting target (heat_target while heating/idle,
  cool_limit while cooling); both `heat_target` and `cool_limit` also published
  as attributes. **[OPEN]** alternatively advertise `TARGET_TEMPERATURE_RANGE`
  and expose `target_temp_low/high` in auto so the native card renders the band.
- `min_temp`/`max_temp`/`step` = tightest common range across actuators
  (fallback 5 / 35 / 0.5).

## 8. Room temperature source

Per the chosen option: **configured sensor if set, else the devices'
`current_temperature`.** With multiple devices, "the devices" resolves as:

1. `temperature_sensor` entity if configured, else
2. the mean of the actuators' `current_temperature` (ignoring `None`), else
3. `None` → integration-driven auto can't decide → hold last intent and warn.

**[OPEN]** mean vs a designated "primary device" for step 2 (mean chosen for
zero extra config).

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
- Migration — old `wrapped_climate` entry yields one `both` device.

## 14. Phasing (after this design is signed off)

1. **Foundation + decision core** — coordinator owns mode; `devices` model +
   migration; `get_scheduled_band`; pure `decide`/`route`; wire the control loop;
   integration-driven auto toggle. (Single or multiple devices already work.)
2. **Config/Options UX** — the add/edit/remove-device Options flow + sensor +
   toggle.
3. **Schedule card** — dual-line (heat/cool) band editing on the timeline.
4. **Polish** — hvac_action in cards, per-device role selects, docs.

## 15. Open decisions (need sign-off)

1. **Config UX / HA floor** (§4): keep 2023.1 + Options-flow list, or raise the
   floor and use config subentries.
2. **Band target reporting** (§7): single `target_temperature` + attributes, or
   advertise a temperature *range* (`target_temp_low/high`) in auto.
3. **Hysteresis** (§6): default value, and configurable or fixed.
4. **Room temp aggregation** (§8): mean of devices vs a designated primary.
5. **Idle actuation** (§6): idle = turn actuators fully **off**, or set them to a
   neutral/eco setpoint (e.g. heat_target for heaters) so recovery is faster.
