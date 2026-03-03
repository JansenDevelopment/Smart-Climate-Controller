# Smart Climate Controller

A Home Assistant custom integration that wraps an existing climate entity and adds presence-aware automatic temperature control, timed overrides, and configurable away behaviour.

## Installation

1. Open your Home Assistant dashboard.
2. Go to **HACS** → **Integrations**.
3. Search for **Smart Climate Controller** and click **Install**.
4. Restart Home Assistant.

## Configuration

No YAML configuration is required. After installation and restart, add the integration through the Home Assistant UI:

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Smart Climate** and select it.
3. Fill in the required fields:
   - **Name** – a friendly name for this Smart Climate instance.
   - **Wrapped Climate** – the existing climate entity to control (e.g. `climate.living_room`).
   - **Zone (home)** – the `zone.home` entity (or equivalent) used for presence detection.
   - Optional defaults: auto temperature, away temperature, away delay, override mode, etc.
4. Click **Submit**.

All settings can be changed later via **Settings** → **Devices & Services** → Smart Climate → **Configure**.

## Lovelace Card Usage

The integration ships with a built-in config card. Add it to any dashboard:

```yaml
type: custom:smart-climate-config-card
entity: climate.living_room
```

The card lets you adjust the auto temperature, away temperature, away delay, and override behaviour directly from the dashboard without editing YAML.

## HVAC Mode

The Smart Climate entity supports two standard HA HVAC modes, controllable from any native climate card or automation:

| HVAC mode | Behaviour |
|-----------|-----------|
| `heat` | Normal operation — auto/schedule mode or active override controls the wrapped climate. |
| `off` | Turns the wrapped climate off and suspends all temperature writes until `heat` is selected again. |

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

## Persistent Storage

Configuration values that can be changed at runtime (away temperature, away delay, interruptible flag, default override mode, default override duration, auto temperature, and schedule) are now saved persistently.

When you call any of the configuration services (e.g. `set_away_temperature`, `set_schedule`) or use one of the built-in Lovelace cards, the updated values are written immediately to Home Assistant's config entry storage:

```
<config_dir>/.storage/core.config_entries
```

This means all settings survive a Home Assistant restart without any extra steps. The values that were set via services are reloaded automatically when the integration starts.

## Troubleshooting

- **Integration does not appear after install** – Make sure you restarted Home Assistant after installing via HACS.
- **Entity not found / config flow fails** – Verify that the wrapped climate entity and zone entity exist and are spelled correctly.
- **Temperature not changing** – Check that the wrapped climate entity is reachable and that no external automation is overriding it.
