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
  frontend.py                        # copies all card modules to www/community + registers the 3 cards as resources
  const.py                           # DOMAIN, modes, config keys, attribute names, service names
  manifest.json                      # integration manifest (domain, version, codeowners)
  strings.json / translations/       # en.json, nl.json — config-flow + entity translations
  smart-climate-card.js              # main control card (LitElement), nl/en via hass.language
  smart-climate-shared.js            # helpers shared by the cards: language, number format, cooling explanation
  smart-climate-config-card.js       # settings card (LitElement) + its editor
  smart-climate-schedule-card.js     # interactive schedule editor card + its editor
  smart-climate-base-editor.js       # shared base class for card GUI editors
  smart-climate-card.new.js          # EMPTY placeholder — future work, ignore
  smart-climate-card-clean.js        # EMPTY placeholder — future work, ignore
tools/card-preview/                  # local card harness (mock hass + Playwright shots), see "Frontend cards"
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

`_mode` (the preset/override axis) is **orthogonal** to the coordinator's own
**HVAC mode** (`off`/`heat`/`cool`/`auto` — see `_OWN_HVAC_MODES`). That mode is
**owned here**, not mirrored from a device: it is persisted as `CONF_HVAC_MODE`
and fed into `control.decide` as an input.

**Off means hands off.** Switching *to* `off` powers the auto devices down
once (`_apply_control(force=True)`); while `off`, `_apply_control` still
resolves state but sends nothing, and `_detect_external_change` records no
takeovers. `control.decide` returning `OFF` is not the same thing: in `auto`
that just means "no heat needed" and the devices are still driven off. Keep
that distinction in `climate.py`, not in `control.py`.

**The coordinator leads.** `decide` resolves a single intent
(`off`/`idle`/`heat`/`cool`) from the room temperature and the band, and
`plan_routes` then writes each device's HVAC mode *and* setpoint — so a
third-party thermostat never gets to pick heating-versus-cooling by itself.
That is why `async_turn_on` selects `auto` instead of pinning `heat`: pinning a
mode would hand that decision back to whoever set it.

### Fan boost, hold, observe and the action log (1.4)

- **Fan boost** (`fan_boost`, switch + `set_behaviour`, default off): `control.fan_for` picks high / medium /
  auto from the deficit (> 1 deg / > 0.3 deg / near), steps up at once, down only after 10 min and a 0.2 deg backoff.
  Only primary devices with `fan_modes`. Measured on a Qlima: high warms 2-3x faster.
- **Hold** (`hold_primary`, default off): while the intent is idle, a primary heater keeps heating at the target
  (`plan_routes(hold_target=...)`) instead of being parked; `control.hold_trim` lowers its setpoint 1 deg after the
  room has been > 0.5 deg over the target for 20 min. A target below the device's `min_temp` (night setback) = off.
- **Observe** (`observe`, switch + `set_observe`): everything is decided and `plan` is published, but nothing is
  sent; changed plans go into the log as `who: observe`. Devices on manual (source user) are planned as auto then.
- **Action log**: `_log_action` keeps the last 40 entries in the `log` attribute (memory only, empty after a
  restart) and fires every entry as event `smart_climate_log` (the recorder keeps events) with room, outdoor,
  target and presence. `who`: user (service/card), hand (device changed outside us), control (we sent), observe.
- **Off by hand** stays off: an auto device switched off outside us becomes manual without end
  (`off_by_hand`), and switching it on by hand hands it back. Other outside changes stay "until next node".
- **One part at a time** (`_execute`): mode, setpoint and fan are sent separately, each after the device reported
  the previous one (`COMMAND_CONFIRM_SECONDS` 6, then `COMMAND_GAP_SECONDS` 1); a part that did not stick is
  resent after `RETRY_SECONDS` 20, `RETRY_TIMES` 3, then every `RESEND_SECONDS`. Reason: the Qlima (Tuya, via
  localtuya which sends one DP per call) puts an earlier DP back when a second one arrives before it reported the
  first. Tests zero the waits in `conftest.py`.
- **Override survives a restart** (1.4.3): `_sync_override` stores the active override (`CONF_OVERRIDE`: mode, temperature,
  start+minutes or until) whenever it changes, `_restore_override` puts it back unless it ran out. The first presence
  reading after a start (`_presence_known`) is not a homecoming, otherwise "interruptible" cancels the restored override.
- After a restart nothing is driven until the configured room sensor has a value (max 120 s): the fallback to
  the devices' own sensors reads an airco's outlet air.

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
duration), `switch` (interruptible), and `select` (default override mode). They
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

`frontend.py` copies **all** card modules (`MODULE_FILES`: the three cards, the
base editor and `smart-climate-shared.js`) into HA's HACS community dir and
registers the three cards as Lovelace resources with one md5-hash cache-buster
over all modules. While copying it appends `?hacstag=<hash>` to the relative
imports of the helper modules, otherwise the browser could pair a new card with
a stale `smart-climate-shared.js`. **A new JS module that a card imports must be
added to `MODULE_FILES`** (`tests/test_frontend.py` checks this). Cards are
LitElement classes that `window.customCards.push({...})` to appear in the picker.
Config/schedule/main card GUI editors extend `SmartClimateBaseEditor`. Cards are
thin clients: they call `smart_climate.*` services and re-render on state change
— all logic stays in the backend.

- Cards are bilingual: `translate(dict, hass, key)` from `smart-climate-shared.js`
  picks `nl` when `hass.language` starts with `nl`, otherwise `en`. The schedule
  card is bilingual too (own `TEXT` dict).
- Cards must **degrade on an older backend**: the new attributes (`cooling_mode`,
  `support_*`, `forecast_*`, `devices`, `intent`, ...) may be missing — leave that
  part out, never crash. The schedule card reads `attributes.schedule`: if the key
  is absent it shows a warning and disables Save (so defaults can never overwrite
  a real schedule); `schedule: null` means "no schedule saved yet" and is fine.
- Main card device control: the header device chips are buttons (>= 44 px) that open an inline menu
  (Auto / Niet gebruiken / Handmatig, plus 30 min / 1 h / until 10:00 / permanent for the latter two;
  permanent is the quiet option) -> `set_device_mode`. A chip shows name + hvac state ("Airco · verwarmt")
  and, when not on Auto, the control label ("Niet gebruiken · nog 25 min", "Handmatig (afstandsbediening)").
  State comes from `device_modes[id] = {mode, until, source}` (already effective, so an expired temporary
  mode reads `auto`; `source` user | pause | external, missing = user). "Until 10:00" is sent as `minutes`,
  computed in the HA time zone (`minutesUntilClock` in `smart-climate-shared.js`), never from the browser's
  zone. A device left on Off/Manual without end (or > 12 h) and not set by the pause buttons gets a quiet
  line under the headline with a "Weer automatisch" button. The header sentence only names devices on `auto`
  and says "X niet beschikbaar" for `unavailable` ones.
- Support pause: `supportPause()` in the shared module reads `support_paused_until` + `support_pause_kind`
  (`until_morning` | `minutes` | `open` | null). `until_morning` -> toggle chip pressed with the real end
  time; `minutes` / `open` -> "CV gepauzeerd ... Hervat" row. `kind` null = the support device is off by
  user choice, which is NOT a pause. Only an old backend without `support_pause_kind` falls back to the
  duration heuristic (<= 125 min = "leaving soon"). English texts use the support device's friendly name
  (`supportName`), never a hardcoded "CV".
- The cooling block is folded to one line ("Koelen: Auto · nu niet nodig") while `coolingRelevant()` is false
  (mode auto, not allowed, no forecast/measured high >= warm_threshold); the forecast tiles live inside the
  unfolded block. `room_temperature_source` ({kind mean|primary|sensor, entity}) is shown small under the target.
- Touch targets: every button/switch is >= 44 px; segmented controls are `aria-pressed` buttons (no radiogroup).
  Small/white-on-colour text uses `--sc-muted` / `--sc-strong` (color-mix) to stay >= 4.5:1 - the harness checks it.
- Override state shown on the main card comes from the `mode` attribute
  (`override_timer` → remaining time, `override_infinity`, `override_next_node`).

**Card preview harness** (`tools/card-preview/`, no HA needed, needs internet for
lit from unpkg): `index.html?card=main|schedule&scenario=<name>&theme=light|dark&lang=nl|en&w=<px>`
renders a card against a mock `hass` (`mock.js`: scenarios, stateful `callService`,
history API). `node tools/card-preview/shoot.mjs [filter]` serves the repo root,
writes screenshots to `tools/card-preview/shots/`, runs interaction smoke tests and
prints console/page errors plus audits (every main-card button >= 44 px, text contrast >= WCAG AA, card heights) (Playwright is taken from `PLAYWRIGHT_PATH`, default
`D:/git/Martijn/HomeAssistant/tools/node_modules/playwright`). `viewer.html` +
`serve.py` (port 8777) run the same cards on the real simulation.
The harness stubs `ha-card`/`ha-icon` as custom elements with a shadow root
(document styles do not reach into the cards' shadow DOM).

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

pip install ruff==0.16.4
ruff check custom_components/
```

**Pin ruff to the version in `ci.yml`** (currently `0.16.4`). Ruff enables new
rules in its default set as it evolves, so an unpinned install lints against a
different rule set than CI and can turn CI red on a commit that changed nothing.
When bumping the pin, fix or suppress whatever the new rules flag in the same
commit.

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
