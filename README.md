# Smart Climate Controller

Custom Home Assistant climate wrapper with:

- Presence aware control
- Manual override timers
- Infinity override
- Custom Lovelace card with slider control

## Configuration

```yaml
climate:
  - platform: smart_climate
    name: "Smart Climate Woonkamer"
    wrapped_climate: climate.woonkamer
    zone_home: zone.home
    away_temperature: 14
    away_delay_minutes: 5
    default_override_mode: "timer"  # or "infinity"
    default_override_duration: 30  # minutes (if mode is "timer")
```

## Options

- `wrapped_climate` - entity_id of the climate entity to wrap
- `zone_home` - zone entity for presence detection
- `away_temperature` - target temp when away (default: 14)
- `away_delay_minutes` - delay before applying away temp (default: 5)
- `default_override_mode` - "timer" or "infinity" (default: "timer")
- `default_override_duration` - minutes for timer mode (default: 30)