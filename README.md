# HA Smart Climate

A Home Assistant custom integration that wraps an existing climate entity and adds presence-aware automatic temperature control, timed overrides, and configurable away behaviour.

## Installation

1. Open your Home Assistant dashboard.
2. Go to **HACS** → **Integrations**.
3. Search for **HA Smart Climate** and click **Install**.
4. Restart Home Assistant.

## Configuration

### Recommended: UI / Config Flow (primary method)

After installation and restart, add the integration through the Home Assistant UI:

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Smart Climate** and select it.
3. Fill in the required fields:
   - **Name** – a friendly name for this Smart Climate instance.
   - **Wrapped Climate** – the existing climate entity to control (e.g. `climate.living_room`).
   - **Zone (home)** – the `zone.home` entity (or equivalent) used for presence detection.
   - Optional defaults: auto temperature, away temperature, away delay, override mode, etc.
4. Click **Submit**.

All settings can be changed later via **Settings** → **Devices & Services** → Smart Climate → **Configure**.

### Optional: Minimal YAML Bootstrap

YAML configuration is optional. Use it only if you want the integration entry to be created automatically on startup (e.g. for automated deployments). Only the `name` field is required; all other settings are managed through the UI after import.

```yaml
smart_climate:
  - name: Living Room
```

> **Note:** Do **not** configure this integration under `climate: - platform: smart_climate`. The correct top-level key is `smart_climate:`.

## Lovelace Card Usage

The integration ships with a built-in config card. Add it to any dashboard:

```yaml
type: custom:smart-climate-config-card
entity: climate.living_room
```

The card lets you adjust the auto temperature, away temperature, away delay, and override behaviour directly from the dashboard without editing YAML.

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

Set the default override mode (`timer` or `infinity`) used when a temperature is changed manually.

```yaml
service: smart_climate.set_default_override_mode
data:
  entity_id: climate.living_room
  mode: timer
  duration: 30
```

## Troubleshooting

- **Integration does not appear after install** – Make sure you restarted Home Assistant after installing via HACS.
- **Entity not found / config flow fails** – Verify that the wrapped climate entity and zone entity exist and are spelled correctly.
- **Temperature not changing** – Check that the wrapped climate entity is reachable and that no external automation is overriding it.
- **YAML import not working** – Ensure the top-level key is `smart_climate:`, not `climate:`. Restart Home Assistant after any YAML change.