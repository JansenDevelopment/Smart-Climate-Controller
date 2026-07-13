# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this is

**Smart Climate Controller** is a [Home Assistant](https://www.home-assistant.io/)
custom integration, distributed via [HACS](https://hacs.xyz/). It wraps an
*existing* climate entity (e.g. `climate.living_room`) and layers on:

- **Presence-aware control** — reads a zone entity's occupancy count and picks
  between "home" and "away" target temperatures.
- **Override modes** — timer, infinity (permanent), and next-node (until the
  next schedule slot).
- **A time-of-day schedule** — daily, 5/2 (weekday/weekend), or per-day.
- **Built-in Lovelace cards** — control, config, and an interactive schedule
  editor, all shipped in-repo and auto-registered.

The integration never talks to the wrapped device directly; it issues
`climate.set_temperature` / `climate.set_hvac_mode` service calls and reads the
wrapped entity's state back. `iot_class` is `local_push`, and there are **no
external network calls and no stored credentials**.

## Repository layout

```
custom_components/smart_climate/     # the integration (all backend + frontend assets)
  __init__.py                        # config-entry + YAML setup, platform forwarding, card registration
  climate.py                         # SmartClimateEntity — core state machine & control loop
  sensor.py                          # SmartClimatePresenceSensor — mirrors presence to a sensor for history
  number.py / switch.py / select.py  # native helper entities for the runtime settings
  entity_base.py                     # SmartClimateChildEntity — shared base for the helper entities
  services.py                        # registers all smart_climate.* HA services (idempotent)
  services.yaml                      # service metadata/selectors shown in the HA UI
  config_flow.py                     # UI config + reconfigure flow
  schedule_helper.py                 # PURE, HA-independent schedule math (unit-testable)
  frontend.py                        # copies + registers the main Lovelace card as a resource
  const.py                           # DOMAIN, modes, config keys, attribute names, service names
  manifest.json                      # integration manifest (domain, version, codeowners)
  strings.json / translations/       # en.json, nl.json — config-flow + entity translations
  smart-climate-card.js              # main control card (LitElement)
  smart-climate-config-card.js       # settings card (LitElement) + its editor
  smart-climate-schedule-card.js     # interactive schedule editor card + its editor
  smart-climate-base-editor.js       # shared base class for card GUI editors
  smart-climate-card.new.js          # EMPTY placeholder — future work, ignore
  smart-climate-card-clean.js        # EMPTY placeholder — future work, ignore
tests/
  conftest.py                        # stubs out homeassistant + voluptuous so tests run without HA
  test_presence_interrupt_override.py
.github/
  workflows/ci.yml                   # ruff lint + pytest
  copilot-instructions.md            # short project-guidelines note (kept in sync with this file)
hacs.json                            # HACS metadata
README.md                            # user-facing install/usage docs
```

## Core concepts

### The control loop (`climate.py`)

`SmartClimateEntity` is the heart of the integration. It does **not** poll
(`_attr_should_poll = False`). Instead it drives itself from two sources:

1. **A 10-second timer** (`async_track_time_interval` → `_update_state`) —
   re-evaluates presence, expires override timers/next-node overrides, ticks the
   away-delay countdown, and re-writes the target temperature.
2. **Zone state-change events** (`async_track_state_change_event` →
   `_on_zone_change`) — reacts immediately when occupancy changes.

Every path ends in `_update_target_temperature()`, which computes the target and
issues a `climate.set_temperature` call to the wrapped entity.

**Target-temperature resolution** (in `_update_target_temperature`) is
**HVAC-mode-aware** — it reads the *wrapped* device's current HVAC mode first:
- Wrapped is `off` / `fan_only` / `dry`, or unavailable → **write nothing**
  (pass-through). This is why selecting `off` genuinely stops setpoint writes.
- Wrapped is `cool` → cooling setpoints: override temp, else `_cool_away_temperature`
  (away) or `_cool_auto_temperature` (home; no schedule in cool for v1).
- Wrapped is `heat` / `auto` → heating setpoints (the original logic):
  - Any override mode → `_override_temperature`.
  - Auto + present + schedule set → `schedule_helper.get_scheduled_temperature(...)`.
  - Auto + present + no schedule → `_auto_temperature`.
  - Auto + away → `_away_temperature`.

The wrapper mirrors the wrapped device's capabilities rather than hardcoding
them: `hvac_modes`, `min_temp`/`max_temp`/`target_temperature_step`, `fan_mode`
(only when the device advertises `FAN_MODE`), and `supported_features` are all
derived from the wrapped entity's state, with sensible fallbacks.

### Modes (`const.py`)

Internal `_mode` is one of `MODE_AUTO`, `MODE_OVERRIDE_TIMER`,
`MODE_OVERRIDE_INFINITY`, `MODE_OVERRIDE_NEXT_NODE`. These map to HA **preset
modes** (`auto` / `timer` / `infinity` / `next_node`) so the native climate card
can display and set them, and are *also* published as a custom `mode` extra state
attribute for backward compatibility — **do not remove the `mode` attribute.**

`_mode` (the preset/override axis) is **orthogonal** to the **HVAC mode**
(`heat`/`cool`/`auto`/`off`/`fan_only`/`dry`), which comes from the *wrapped*
device and drives the heating-vs-cooling setpoint family (see the control loop
above). Setting the HVAC mode delegates to the wrapped entity; the wrapper reads
it back rather than owning it.

### Presence & away delay

- Presence is `"home"` or `"away"`, derived from the zone entity's integer state
  (occupancy count). It starts `"away"`.
- When everyone leaves, an **away delay** timer starts (`_start_away_delay`);
  presence only flips to `"away"` after `away_delay_minutes` elapse. The delay is
  timestamp-based (`_away_delay_start`) to avoid tick drift over the 10s loop.
- Coming home cancels the away delay immediately.
- **Interruptible**: when `_interruptible` is `True`, a presence change back home
  cancels *any* active override (timer, infinity, next-node) and returns to auto.
  When `False`, overrides survive presence changes. This behavior is enforced in
  three code paths — `_on_zone_change`, `_update_state`, and
  `_transition_to_away` — and is the subject of the regression test.

### Schedule (`schedule_helper.py`)

Pure functions, no HA imports — that's deliberate so they can be unit-tested
directly. A schedule is a dict with a `mode` key:
- `"daily"` → `schedule["daily"]` (a list of `{time, temp}` nodes).
- `"5/2"` → `schedule["weekday"]` / `schedule["weekend"]`.
- `"individual"` → per-day keys `monday`…`sunday`.

`get_scheduled_temperature` picks the last node whose `HH:MM` time is ≤ now,
wrapping to the previous day's last node before the first slot.
`compute_next_node_datetime` / `get_next_node_minutes` find the next upcoming
node (wrapping to tomorrow). All parse `time` as `%H:%M` and fall back / warn on
malformed nodes.

### The presence sensor (`sensor.py`)

HA does not record entity *attributes* to history, only state. To let the
schedule card draw the home/away bar, `SmartClimatePresenceSensor` mirrors the
climate entity's `presence` attribute into a dedicated sensor's *state*, which HA
does record. It finds its paired climate entity via the entity registry using the
`smart_climate_{entry_id}` unique-id convention.

### Helper entities (`number.py`, `switch.py`, `select.py`, `entity_base.py`)

Every runtime setting is also exposed as a native HA entity so users get
history, automations, and standard UI control without the custom cards:
`number` (home/away temp, cooling home/away temp, away delay, default override
duration), `switch` (interruptible), and `select` (default override mode, plus
one per-actuator-device role select — heat/cool/both — created per device). They
all extend `SmartClimateChildEntity` (`entity_base.py`), which — like the
presence sensor — resolves the paired climate entity via the registry, subscribes
to its state changes, **reads** the current value from the climate entity's state
*attributes*, and **writes** changes back through the `smart_climate.*` services.
This is why the climate entity publishes `auto_temperature`, `away_temperature`,
`away_delay_minutes`, `default_override_mode/duration`, and the `cool_*` temps as
extra state attributes — they're the helpers' source of truth. All entities share
`device_info` (`identifiers = {(DOMAIN, entry_id)}`) so they group under one
device. The duration `number` and the mode `select` both route through
`set_default_override_mode` (the backend sets mode+duration together), preserving
the other value.

### Services (`services.py` + `services.yaml`)

All services live under the `smart_climate` domain and are registered **once**
(guarded by `hass.services.has_service`). Each handler resolves the target
entity from `hass.data[DOMAIN]["entities"][entity_id]`, which entities register
in `async_added_to_hass`. When adding a service:
1. Add the `SERVICE_*` constant to `const.py`.
2. Add the handler + `async_register` call in `services.py`.
3. Add the entity method it calls in `climate.py`.
4. Add UI metadata to `services.yaml`.

### Frontend cards

`frontend.py` copies `smart-climate-card.js` into HA's HACS community dir and
registers it as a Lovelace resource with an md5-hash cache-buster. Cards are
LitElement classes that `window.customCards.push({...})` to appear in the picker.
Config/schedule card GUI editors extend `SmartClimateBaseEditor`. Cards are thin
clients: they call `smart_climate.*` services and re-render on state change — all
logic stays in the backend.

## Development workflow

### Branch & git conventions

- Default branch is **`develop`** (not `main`).
- Do all work on the assigned feature branch; commit with clear messages; push
  with `git push -u origin <branch>`.
- Do **not** open a PR unless explicitly asked.

### Running tests & lint

Tests run **without a Home Assistant install** — `tests/conftest.py` registers
stub modules for `homeassistant.*` and `voluptuous` in `sys.modules` before
collection. This is why `schedule_helper.py` and the entity's mode logic can be
imported and tested in isolation.

```bash
pip install pytest
pytest tests/ --tb=short

pip install ruff
ruff check custom_components/
```

The async tests rely on `pytest-asyncio` (installed in CI; `asyncio_mode = auto`
is set in `pytest.ini`, so `async def` tests run without needing a per-test
mark). CI (`.github/workflows/ci.yml`) runs both jobs on pushes/PRs to `main`
and `develop`.

### Manual / integration testing

There is no way to exercise the full integration outside a running HA instance.
To test end-to-end: copy `custom_components/smart_climate/` into an HA config,
restart HA, add the integration via **Settings → Devices & Services**, and drive
it from the Lovelace cards or Developer Tools → Services.

## Conventions & gotchas

- **Formatting**: 4-space indent for Python, 2-space for YAML/JS. Match the
  surrounding file.
- **HA conventions**: entity methods are `async_*`; state is pushed with
  `self.async_write_ha_state()`; time uses `homeassistant.util.dt` (`dt_util`),
  not stdlib `datetime.now()`.
- **Constants over strings**: mode names, config keys, attribute names, and
  service names all live in `const.py`. Reference the constants, don't hardcode.
- **Persistence**: runtime-changeable settings are saved to HA's config-entry
  storage (`.storage/core.config_entries`) and survive restarts. Config keys are
  the `CONF_*` values in `const.py`.
- **Default-override modes** are `timer`, `infinity`, and `next_node`. Both the
  UI (`config_flow.py`) and the YAML `CONFIG_SCHEMA` in `__init__.py` accept all
  three — keep them in sync if you add another mode.
- **Empty placeholder JS files** (`smart-climate-card.new.js`,
  `smart-climate-card-clean.js`) are intentionally empty scaffolds — don't treat
  them as broken or wire them up unless that's the task.

### Entity constructor signature

`SmartClimateEntity.__init__` takes `(hass, entry, name, wrapped_climate,
zone_home, away_temp, away_delay_minutes, interruptible, default_override_mode,
default_override_duration)`. `auto_temperature` (default 21), `schedule`
(default `None`), and the cooling setpoints `cool_auto_temperature` (24) /
`cool_away_temperature` (28) are **not** constructor args — they are restored
from `entry.data` on construction and changed at runtime via the
`set_auto_temperature` / `set_schedule` / `set_cool_*_temperature` services.
Tests that build an entity directly (see `_make_entity` in
`tests/test_presence_interrupt_override.py`) set `_auto_temperature` /
`_schedule` as attributes after construction rather than passing them in.

### Adding a runtime setting

The pattern for a persisted, card- and helper-controllable setting: add the
`CONF_*` key + `ATTR_*` name + `SERVICE_*` to `const.py`; read it from
`entry.data` in the constructor; add an `async_set_*` method that calls
`_persist(...)`; register the service (`services.py` + `services.yaml`); publish
it in `extra_state_attributes`; and, if it should have a native control, add a
`number`/`switch`/`select` entry backed by `SmartClimateChildEntity`.

## Where to look first

| I want to change… | Start in |
|---|---|
| Target-temperature / presence / override logic | `climate.py` |
| Schedule math | `schedule_helper.py` |
| Add/modify a service | `services.py`, `services.yaml`, `const.py` |
| Heating/cooling setpoint selection | `_update_target_temperature` in `climate.py` |
| Native number/switch/select controls | `number.py`, `switch.py`, `select.py`, `entity_base.py` |
| Setup flow / config fields | `config_flow.py`, `strings.json`, `translations/` |
| Card UI | `smart-climate-*.js`, `frontend.py` |
| Names/keys/modes | `const.py` |
