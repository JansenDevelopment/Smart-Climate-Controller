# Smart Climate Controller

A Home Assistant custom integration that wraps an existing climate entity and adds presence-aware automatic temperature control, timed overrides, and configurable away behaviour.

## How it works

Smart Climate never talks to your heating hardware directly. It creates a new
`climate.*` entity that *wraps* an existing one and issues standard
`climate.set_temperature` / `climate.set_hvac_mode` calls to it. On top of the
wrapped device it adds:

- **Presence-aware control** – reads the occupancy count from a `zone` entity and
  picks between a **home** and an **away** target temperature. When everyone
  leaves, an *away delay* runs before the away temperature is applied; coming
  home cancels it immediately.
- **Override modes** – a manual temperature change activates an override:
  **timer** (reverts after a set duration), **infinity** (until cleared), or
  **next node** (until the next schedule slot). Overrides can optionally be
  *interruptible* by presence changes.
- **A time-of-day schedule** – `daily`, `5/2` (weekday/weekend), or `individual`
  (per-day), edited visually from the schedule card.

There are **no external network calls and no stored credentials** — everything
runs locally through Home Assistant's service layer.

<!-- Screenshot suggestion: a dashboard showing the three cards side by side.
     Drop the image in an images/ folder and reference it here, e.g.:
     ![Smart Climate dashboard](images/dashboard.png) -->

## Installation

### HACS (recommended)

This integration is distributed as a **custom repository** (it is not in the
HACS default store).

1. In Home Assistant, open **HACS**.
2. Click the **⋮** menu (top-right) → **Custom repositories**.
3. Add the repository URL `https://github.com/JansenDevelopment/Smart-Climate-Controller`
   and select **Integration** as the category, then click **Add**.
4. Search HACS for **Smart Climate Controller** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/smart_climate/` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

No YAML configuration is required. After installing and restarting, add the
integration through the Home Assistant UI:

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Smart Climate** and select it.
3. Fill in the setup form:
   - **Name** – a friendly name for this Smart Climate instance.
   - **Wrapped Climate Entity** – the existing climate entity to control (e.g. `climate.living_room`).
   - **Home Zone** – a `zone` entity whose state is the occupancy count, used for presence detection (e.g. `zone.home`).
   - **Away Temperature** – target when nobody is home (default `14`).
   - **Away Delay (minutes)** – how long to wait after everyone leaves before applying the away temperature (default `5`).
   - **Override is interruptible** – whether a presence change cancels an active override (default on).
   - **Default Override Mode** – `timer`, `infinity`, or `next_node` (default `timer`).
   - **Default Override Duration (minutes)** – timer length for timer overrides (default `30`).
4. Click **Submit**.

The **auto (home) temperature** and the **schedule** are *not* part of the setup
form — they start at their defaults (`21` °C, no schedule) and are set at runtime
from the config/schedule cards or the `smart_climate.set_auto_temperature` /
`smart_climate.set_schedule` services. All runtime settings are saved and
restored across restarts (see [Persistent Storage](#persistent-storage)).

To change the **wrapped climate** or **home zone** later, use **Settings** →
**Devices & Services** → Smart Climate → **Configure**. All other settings are
adjusted from the Lovelace cards or the `smart_climate.*` services.

## Lovelace Cards

The integration ships with three built-in custom cards. Add them to any dashboard via the Lovelace card picker or manually in YAML.

### Smart Climate Card

The main control card — displays current and target temperatures, operating mode, override status, and provides controls for temperature and timer overrides.

```yaml
type: custom:smart-climate-card
entity: climate.living_room
```

<!-- ![Control card](images/control-card.png) -->

| Variable | Required | Description |
|----------|----------|-------------|
| `entity` | Yes | The Smart Climate entity ID (e.g. `climate.living_room`). |

### Smart Climate Config Card

A settings card — lets you adjust the auto temperature, away temperature, away delay, default override mode, and interruptible flag directly from the dashboard without editing YAML.

```yaml
type: custom:smart-climate-config-card
entity: climate.living_room
```

<!-- ![Config card](images/config-card.png) -->

| Variable | Required | Description |
|----------|----------|-------------|
| `entity` | Yes | The Smart Climate entity ID (e.g. `climate.living_room`). |

### Smart Climate Schedule Card

An interactive schedule editor — shows a temperature schedule graph with drag-and-drop nodes, optional temperature history, and presence detection overlay.

Toggle **❄ Cooling** in the card header to edit a **comfort band**: each schedule node then has a 🔥 *heat-to* handle and a ❄ *cool-above* handle, with the idle band shaded between them. Drag either handle (or edit both in the node panel); the card keeps the cool limit at least 1 °C above the heat target. Heat-only users can leave the toggle off and the card behaves exactly as before. The band is what `auto` mode follows (heat below the lower line, cool above the upper line, idle in between).

```yaml
type: custom:smart-climate-schedule-card
entity: climate.living_room
show_history: true
show_yesterday: true
show_presence: true
temp_sensor: sensor.living_room_temperature
```

<!-- ![Schedule card](images/schedule-card.png) -->


| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `entity` | Yes | — | The Smart Climate entity ID (e.g. `climate.living_room`). |
| `show_history` | No | `true` | Show today's temperature history on the graph. |
| `show_yesterday` | No | `true` | Show yesterday's temperature history on the graph. |
| `show_presence` | No | `true` | Show presence detection overlay bar on the graph. |
| `temp_sensor` | No | — | Entity ID of an external temperature sensor to display on the graph (e.g. `sensor.living_room_temperature`). |

## HVAC Modes

The Smart Climate entity **mirrors the HVAC modes of the wrapped device**, so
whatever your device supports (`heat`, `cool`, `auto`, `fan_only`, `dry`, `off`,
…) is available from any native climate card or automation. The wrapper's
min/max temperature, step, and fan modes are also taken from the wrapped device.

How each mode is handled:

| HVAC mode | Behaviour |
|-----------|-----------|
| `heat` | Heating setpoints — auto/schedule/away logic (or an active override) drives the wrapped climate. |
| `auto` | The wrapped device heats or cools toward the smart comfort target (same setpoints/schedule as `heat`). |
| `cool` | Cooling setpoints — uses the **Cooling Home** / **Cooling Away** temperatures (see below), with presence and overrides applied. |
| `off` | Turns the wrapped climate off and writes **no** temperature until a heating/cooling mode is selected again. |
| `fan_only` / `dry` / other | Passed through untouched — the wrapper writes no setpoint. |

### Cooling setpoints

When the wrapped device is in `cool` mode, Smart Climate uses a dedicated pair
of setpoints instead of the heating temperatures:

| Setting | Default | Applies when |
|---------|---------|--------------|
| Cooling Home Temperature | `24` °C | cooling and someone is home |
| Cooling Away Temperature | `28` °C | cooling and nobody is home |

Set them during initial setup, from the **Cooling Home/Away Temperature** number
entities, or via the `smart_climate.set_cool_auto_temperature` /
`smart_climate.set_cool_away_temperature` services. (The time-of-day schedule
applies to heating only in this version; cooling uses the flat Cooling Home
temperature when home.)

## Preset Modes

The operating mode of the Smart Climate is exposed as a standard HA **preset mode**, visible and settable from the native climate card:

| Preset | Internal mode | Description |
|--------|---------------|-------------|
| `auto` | `auto` | Presence-aware automatic/schedule mode (default). |
| `timer` | `override_timer` | Timed manual override — reverts to auto after the configured duration. |
| `infinity` | `override_infinity` | Permanent manual override — remains active until cleared. |
| `next_node` | `override_next_node` | Override until the next schedule node is reached. |

Preset mode labels are translated in the Home Assistant UI:

| Preset value | English label | Dutch label |
|-------------|---------------|-------------|
| `auto` | Schedule | Schema |
| `timer` | Timer | Timer |
| `infinity` | Always | Altijd |
| `next_node` | Until next slot | Tot volgend moment |

> **Backward compatibility** — The custom `mode` extra state attribute (`state_attr('climate.xxx', 'mode')`) is **not deprecated**. It continues to be published alongside the standard `preset_mode` so that existing automations and templates that read it are unaffected.

## Services

All services are under the `smart_climate` domain and target a Smart Climate `climate.*` entity.

### `smart_climate.set_override_timer`

Set a timed manual temperature override.

| Field | Required | Description |
|-------|----------|-------------|
| `entity_id` | Yes | Smart Climate entity |
| `temperature` | Yes | Target temperature (unit follows your HA system setting) |
| `minutes` | Yes | Duration (1–120 min) |

```yaml
service: smart_climate.set_override_timer
data:
  entity_id: climate.living_room
  temperature: 22
  minutes: 60
```

### `smart_climate.set_override_infinity`

Set a permanent manual temperature override (no time limit).

```yaml
service: smart_climate.set_override_infinity
data:
  entity_id: climate.living_room
  temperature: 22
```

### `smart_climate.set_override_next_node`

Set a manual temperature override that lasts until the next schedule node is reached. When the schedule's next node time arrives the override is automatically cleared and auto mode resumes.

```yaml
service: smart_climate.set_override_next_node
data:
  entity_id: climate.living_room
  temperature: 22
```

### `smart_climate.clear_override`

Return to automatic (presence-based) mode.

```yaml
service: smart_climate.clear_override
data:
  entity_id: climate.living_room
```

### `smart_climate.set_auto_temperature`

Set the target temperature used when someone is home in auto mode.

```yaml
service: smart_climate.set_auto_temperature
data:
  entity_id: climate.living_room
  temperature: 21
```

### `smart_climate.set_away_temperature`

Set the target temperature used when nobody is home.

```yaml
service: smart_climate.set_away_temperature
data:
  entity_id: climate.living_room
  temperature: 14
```

### `smart_climate.set_cool_auto_temperature`

Set the target temperature used when someone is home and the wrapped device is cooling.

```yaml
service: smart_climate.set_cool_auto_temperature
data:
  entity_id: climate.living_room
  temperature: 24
```

### `smart_climate.set_cool_away_temperature`

Set the target temperature used when nobody is home and the wrapped device is cooling.

```yaml
service: smart_climate.set_cool_away_temperature
data:
  entity_id: climate.living_room
  temperature: 28
```

### `smart_climate.set_away_delay`

Set how long (in minutes) to wait after everyone leaves before switching to the away temperature.

```yaml
service: smart_climate.set_away_delay
data:
  entity_id: climate.living_room
  minutes: 5
```

### `smart_climate.set_interruptible`

Control whether a presence change can interrupt an active override.

```yaml
service: smart_climate.set_interruptible
data:
  entity_id: climate.living_room
  interruptible: true
```

### `smart_climate.set_default_override_mode`

Set the default override mode (`timer`, `infinity`, or `next_node`) used when a temperature is changed manually.

```yaml
service: smart_climate.set_default_override_mode
data:
  entity_id: climate.living_room
  mode: timer
  duration: 30
```

When `mode` is `next_node` the `duration` field is ignored; the override automatically ends at the next schedule node.

## Helper Entities

In addition to the Lovelace cards, every runtime setting is exposed as a
standard Home Assistant entity, grouped under a single **Smart Climate** device.
These give you history, dashboards, and automations without the custom cards —
and can be dropped onto any dashboard with an Entities card.

| Entity | Type | Setting |
|--------|------|---------|
| Home Temperature | `number` | Auto/home heating target |
| Away Temperature | `number` | Away heating target |
| Cooling Home Temperature | `number` | Home target when cooling |
| Cooling Away Temperature | `number` | Away target when cooling |
| Away Delay | `number` | Minutes before applying the away temperature |
| Default Override Duration | `number` | Timer length for timer overrides |
| Override Interruptible | `switch` | Whether presence changes cancel an override |
| Default Override Mode | `select` | `timer` / `infinity` / `next_node` |

Changing any of these calls the matching `smart_climate.*` service, so the value
is applied immediately and persisted across restarts.

## Persistent Storage

Configuration values that can be changed at runtime (away temperature, cooling home/away temperatures, away delay, interruptible flag, default override mode, default override duration, auto temperature, and schedule) are saved persistently.

When you call any of the configuration services (e.g. `set_away_temperature`, `set_schedule`) or use one of the built-in Lovelace cards, the updated values are written immediately to Home Assistant's config entry storage:

```
<config_dir>/.storage/core.config_entries
```

This means all settings survive a Home Assistant restart without any extra steps. The values that were set via services are reloaded automatically when the integration starts.

## Troubleshooting

- **Integration does not appear after install** – Make sure you restarted Home Assistant after installing via HACS.
- **Entity not found / config flow fails** – Verify that the wrapped climate entity and zone entity exist and are spelled correctly.
- **Temperature not changing** – Check that the wrapped climate entity is reachable and that no external automation is overriding it.
