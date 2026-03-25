# Project Guidelines

## Code Style
- **Python**: Follows Home Assistant integration conventions. See `custom_components/smart_climate/climate.py` for entity/state logic and `custom_components/smart_climate/__init__.py` for setup/config.
- **JavaScript (Lovelace card)**: Uses LitElement for custom cards. See `custom_components/smart_climate/smart-climate-card.js` for UI logic and style. Use template literals, reactive properties, and Home Assistant theme variables.
- **Formatting**: 2 spaces for YAML, 4 spaces for Python, 2 spaces for JS (match existing files).

## Architecture
- **Backend**: Python custom integration wraps an existing climate entity, adds presence-aware logic, override modes, and persistent config.
- **Frontend**: Custom Lovelace card (LitElement) for user interaction, override control, and live feedback.
- **Service boundaries**: All logic (timers, presence, override) is backend-driven; UI is a thin client.
- **Data flow**: Card calls backend services, backend updates state, card re-renders on state change.

## Build and Test
- **Install**: Place in `custom_components/smart_climate/` and install via HACS or manually.
- **Test**: Restart Home Assistant, add integration via UI, use Lovelace card for interaction.
- **No standalone test runner**; test via Home Assistant instance.

## Project Conventions
- **Config**: All runtime config is stored in HA's config entry storage (`.storage/core.config_entries`).
- **Services**: All actions (set override, set temp, set away, etc.) are exposed as HA services under `smart_climate` domain.
- **Preset modes**: Internal state is mapped to HA preset modes for compatibility with native cards/automations.
- **No YAML required**: All config is UI-driven after install.

## Integration Points
- **Depends on**: Existing climate entity (e.g. `climate.living_room`), zone entity for presence (e.g. `zone.home`).
- **Frontend**: Card is loaded as a Lovelace resource, auto-updated by HACS.

## Security
- **No external network calls**.
- **No credentials stored**.
- **All state changes go through Home Assistant's service layer and permission model.**
