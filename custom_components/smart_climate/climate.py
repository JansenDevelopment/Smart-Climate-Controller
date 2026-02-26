from datetime import datetime, timedelta
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, CONF_NAME, STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
import logging

from .const import (
    DOMAIN,
    MODE_AUTO,
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    ATTR_MODE,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_INTERRUPTIBLE,
    ATTR_ZONE_HOME_COUNT,
    ATTR_AWAY_DELAY_SECONDS_REMAINING,
    ATTR_OVERRIDE_TEMPERATURE,
    SERVICE_SET_OVERRIDE_TIMER,
    SERVICE_SET_OVERRIDE_INFINITY,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_SET_INTERRUPTIBLE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate platform."""
    name = entry.data.get(CONF_NAME, "Smart Climate")
    wrapped_climate = entry.data.get(CONF_WRAPPED_CLIMATE)
    zone_home = entry.data.get(CONF_ZONE_HOME)
    away_temp = entry.data.get(CONF_AWAY_TEMPERATURE, 14)
    away_delay = entry.data.get(CONF_AWAY_DELAY_MINUTES, 5)
    interruptible = entry.data.get(CONF_INTERRUPTIBLE, True)
    default_override_mode = entry.data.get(CONF_DEFAULT_OVERRIDE_MODE, "timer")
    default_override_duration = entry.data.get(CONF_DEFAULT_OVERRIDE_DURATION, 30)

    entity = SmartClimateEntity(
        hass,
        entry,
        name,
        wrapped_climate,
        zone_home,
        away_temp,
        away_delay,
        interruptible,
        default_override_mode,
        default_override_duration,
    )
    async_add_entities([entity], True)

    # Register services
    async def handle_set_override_timer(call):
        await entity.async_set_override_timer(
            call.data.get("minutes", 60),
            call.data.get("temperature", 21),
        )

    async def handle_set_override_infinity(call):
        await entity.async_set_override_infinity(
            call.data.get("temperature", 21),
        )

    async def handle_clear_override(call):
        await entity.async_clear_override()

    async def handle_set_interruptible(call):
        await entity.async_set_interruptible(call.data.get("interruptible", True))

    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE_TIMER, handle_set_override_timer
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_OVERRIDE_INFINITY, handle_set_override_infinity
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_OVERRIDE, handle_clear_override)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_INTERRUPTIBLE, handle_set_interruptible
    )


class SmartClimateEntity(ClimateEntity):
    """Smart Climate controller entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        wrapped_climate: str,
        zone_home: str,
        away_temp: float,
        away_delay_minutes: int,
        interruptible: bool,
        default_override_mode: str,
        default_override_duration: int,
    ):
        self.hass = hass
        self.entry = entry
        self._attr_name = name
        self._attr_unique_id = f"smart_climate_{entry.entry_id}"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 5
        self._attr_max_temp = 25
        self._attr_target_temperature_step = 0.5
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_should_poll = False

        # Config
        self._wrapped_climate = wrapped_climate
        self._zone_home = zone_home
        self._away_temperature = away_temp
        self._away_delay_minutes = away_delay_minutes
        self._default_override_mode = default_override_mode
        self._default_override_duration = default_override_duration

        # State
        self._mode = MODE_AUTO
        self._presence = "away"  # Start as away
        self._interruptible = interruptible
        self._override_temperature = 21
        self._override_start_time = None
        self._override_duration_minutes = 0
        self._away_delay_task = None
        self._away_delay_remaining = 0

        # Timers
        self._update_timer = None

    async def async_added_to_hass(self):
        """Initialize after added to hass."""
        await super().async_added_to_hass()

        # Start listening to zone changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._zone_home], self._on_zone_change
            )
        )

        # Start update timer (every 10 seconds)
        self._update_timer = async_track_time_interval(
            self.hass, self._update_state, timedelta(seconds=10)
        )

        # Initial state update
        await self._update_state()

    async def _update_state(self, now=None):
        """Update internal state every interval."""
        # Update zone presence
        zone_state = self.hass.states.get(self._zone_home)
        if zone_state:
            try:
                zone_count = int(zone_state.state)
                if zone_count > 0 and self._presence != "home":
                    # Someone came home
                    await self._cancel_away_delay()
                    self._presence = "home"
                    if self._mode == MODE_OVERRIDE_TIMER and self._interruptible:
                        self._mode = MODE_AUTO
            except ValueError:
                pass

        # Update away delay
        if self._away_delay_task and self._away_delay_remaining > 0:
            self._away_delay_remaining -= 10
            if self._away_delay_remaining <= 0:
                self._presence = "away"
                self._away_delay_task = None
                if self._mode == MODE_OVERRIDE_TIMER and self._interruptible:
                    self._mode = MODE_AUTO

        # Update override timer
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed = (datetime.now() - self._override_start_time).total_seconds() / 60
            remaining = self._override_duration_minutes - elapsed
            if remaining <= 0:
                self._mode = MODE_AUTO
                self._override_start_time = None
            else:
                self._override_start_time = datetime.now() - timedelta(
                    minutes=elapsed
                )

        # Calculate target temperature
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def _on_zone_change(self, event):
        """Handle zone state changes."""
        zone_state = self.hass.states.get(self._zone_home)
        if not zone_state:
            return

        try:
            zone_count = int(zone_state.state)
            if zone_count > 0:
                # Someone came home
                await self._cancel_away_delay()
                self._presence = "home"
                if self._mode == MODE_OVERRIDE_TIMER and self._interruptible:
                    self._mode = MODE_AUTO
            else:
                # Everyone left
                await self._start_away_delay()
        except ValueError:
            pass

    async def _start_away_delay(self):
        """Start away delay timer."""
        if not self._away_delay_task:
            self._away_delay_remaining = self._away_delay_minutes * 60
            self._away_delay_task = True

    async def _cancel_away_delay(self):
        """Cancel away delay."""
        self._away_delay_task = None
        self._away_delay_remaining = 0

    async def _update_target_temperature(self):
        """Calculate and update target temperature to wrapped climate."""
        if self._mode == MODE_OVERRIDE_TIMER or self._mode == MODE_OVERRIDE_INFINITY:
            target = self._override_temperature
        elif self._mode == MODE_AUTO:
            if self._presence == "home":
                # TODO: Later integrate with schedule
                target = 21
            else:
                target = self._away_temperature
        else:
            target = 21

        # Set on wrapped climate
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": self._wrapped_climate,
                "temperature": target,
            },
        )

    async def async_set_override_timer(self, minutes: int, temperature: float):
        """Set override timer mode."""
        self._mode = MODE_OVERRIDE_TIMER
        self._override_temperature = temperature
        self._override_start_time = datetime.now()
        self._override_duration_minutes = minutes
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_override_infinity(self, temperature: float):
        """Set override infinity mode."""
        self._mode = MODE_OVERRIDE_INFINITY
        self._override_temperature = temperature
        self._override_start_time = None
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_interruptible(self, interruptible: bool):
        """Set interruptible mode."""
        self._interruptible = interruptible
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set temperature - activate override based on DEFAULT_OVERRIDE setting."""
        temperature = kwargs.get("temperature", 22)
        
        if self._default_override_mode == "infinity":
            await self.async_set_override_infinity(temperature)
        else:
            # timer mode (default)
            await self.async_set_override_timer(self._default_override_duration, temperature)

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_mode(self):
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped:
            return wrapped.state
        return HVACMode.HEAT

    @property
    def current_temperature(self):
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped:
            return wrapped.attributes.get("current_temperature")
        return None

    @property
    def target_temperature(self):
        if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY):
            return self._override_temperature
        if self._presence == "home":
            return 21
        return self._away_temperature

    @property
    def extra_state_attributes(self):
        remaining_minutes = 0
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed = (datetime.now() - self._override_start_time).total_seconds() / 60
            remaining_minutes = max(0, self._override_duration_minutes - elapsed)

        return {
            ATTR_MODE: self._mode,
            ATTR_PRESENCE: self._presence,
            ATTR_REMAINING_MINUTES: int(remaining_minutes),
            ATTR_INTERRUPTIBLE: self._interruptible,
            ATTR_OVERRIDE_TEMPERATURE: self._override_temperature,
            ATTR_AWAY_DELAY_SECONDS_REMAINING: self._away_delay_remaining,
        }