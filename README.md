# Smart Climate Controller

Custom Home Assistant climate wrapper with:

- Presence aware control
- Manual override timers
- Infinity override
- Custom Lovelace card with slider control
- Config card to manage all settings from the UI

## Installation

Install via [HACS](https://hacs.xyz/) or copy the `custom_components/smart_climate` folder into your Home Assistant `custom_components` directory.

## Configuration

Add Smart Climate through the Home Assistant **Integrations** page (Settings → Devices & Services → Add Integration), or add a minimal YAML entry to bootstrap the setup:

```yaml
smart_climate:
  - name: "Smart Climate Woonkamer"
```

After adding via YAML, complete the configuration through the Home Assistant UI where you will be prompted to fill in the remaining required settings.

## Config Card

Use the Smart Climate Config Card in your Lovelace dashboard to manage settings at any time:

```yaml
type: custom:smart-climate-config-card
entity: climate.smart_climate_woonkamer
```

### Settings

| Setting | Description | Default |
|---|---|---|
| **Home Temperature** | Target temperature when presence is detected | 21 °C |
| **Away Temperature** | Target temperature when nobody is home | 14 °C |
| **Away Delay** | Minutes to wait before applying away temperature | 5 min |
| **Default Override Mode** | `timer` or `infinity` when adjusting temperature | timer |
| **Default Override Duration** | Duration for timer override mode | 30 min |
| **Interruptible** | Whether presence changes can interrupt an active override | Yes |

## Services

| Service | Description |
|---|---|
| `smart_climate.set_override_timer` | Set manual override for a fixed duration |
| `smart_climate.set_override_infinity` | Set manual override with no time limit |
| `smart_climate.clear_override` | Return to auto mode |
| `smart_climate.set_auto_temperature` | Set home temperature |
| `smart_climate.set_away_temperature` | Set away temperature |
| `smart_climate.set_away_delay` | Set delay before away mode |
| `smart_climate.set_default_override_mode` | Set default override mode and duration |
| `smart_climate.set_interruptible` | Enable/disable presence interrupting override |
