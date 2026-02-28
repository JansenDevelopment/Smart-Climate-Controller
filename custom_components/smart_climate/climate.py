from datetime import datetime, timedelta
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
import logging

from .const import (
    DOMAIN,
    MODE_AUTO,
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_52,
    SCHEDULE_MODE_INDIVIDUAL,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AUTO_TEMPERATURE,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_SCHEDULE,
    ATTR_WRAPPED_CLIMATE,
    ATTR_ZONE_HOME,
    ATTR_MODE,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_INTERRUPTIBLE,
    ATTR_AWAY_DELAY_SECONDS_REMAINING,
    ATTR_OVERRIDE_TEMPERATURE,
    ATTR_AUTO_TEMPERATURE,
    ATTR_AWAY_TEMPERATURE,
    ATTR_AWAY_DELAY_MINUTES,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_SCHEDULE,
    SERVICE_SET_OVERRIDE_TIMER,
    SERVICE_SET_OVERRIDE_INFINITY,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_SET_INTERRUPTIBLE,
    SERVICE_SET_AUTO_TEMPERATURE,
    SERVICE_SET_AWAY_TEMPERATURE,
    SERVICE_SET_AWAY_DELAY,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_SCHEDULE,
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
    auto_temp = entry.data.get(CONF_AUTO_TEMPERATURE, 21)
    away_delay = entry.data.get(CONF_AWAY_DELAY_MINUTES, 5)
    interruptible = entry.data.get(CONF_INTERRUPTIBLE, True)
    default_override_mode = entry.data.get(CONF_DEFAULT_OVERRIDE_MODE, "timer")
    default_override_duration = entry.data.get(CONF_DEFAULT_OVERRIDE_DURATION, 30)
    schedule = entry.data.get(CONF_SCHEDULE, None)

    entity = SmartClimateEntity(
        hass,
        entry,
        name,
        wrapped_climate,
        zone_home,
        auto_temp,
        away_temp,
        away_delay,
        interruptible,
        default_override_mode,
        default_override_duration,
        schedule,
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

    async def handle_set_auto_temperature(call):
        await entity.async_set_auto_temperature(call.data.get("temperature", 21))

    async def handle_set_away_temperature(call):
        await entity.async_set_away_temperature(call.data.get("temperature", 14))

    async def handle_set_away_delay(call):
        await entity.async_set_away_delay(call.data.get("minutes", 5))

    async def handle_set_default_override_mode(call):
        await entity.async_set_default_override_mode(
            call.data.get("mode", "timer"),
            call.data.get("duration", 30),
        )

    async def handle_set_schedule(call):
        await entity.async_set_schedule(call.data.get("schedule"))

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
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AUTO_TEMPERATURE, handle_set_auto_temperature
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AWAY_TEMPERATURE, handle_set_away_temperature
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AWAY_DELAY, handle_set_away_delay
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_DEFAULT_OVERRIDE_MODE, handle_set_default_override_mode
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule
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
        auto_temp: float,
        away_temp: float,
        away_delay_minutes: int,
        interruptible: bool,
        default_override_mode: str,
        default_override_duration: int,
        schedule: dict | None = None,
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
        self._auto_temperature = auto_temp
        self._away_temperature = away_temp
        self._away_delay_minutes = away_delay_minutes
        self._default_override_mode = default_override_mode
        self._default_override_duration = default_override_duration
        self._schedule = schedule

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

        # Track the last temperature written to the wrapped climate to avoid
        # unnecessary writes and to detect external changes
        self._last_written_temperature = None

    async def async_added_to_hass(self):
        """Initialize after added to hass."""
        await super().async_added_to_hass()

        # Start listening to zone changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._zone_home], self._on_zone_change
            )
        )

        # Listen to wrapped climate changes to detect external temperature adjustments
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._wrapped_climate], self._on_wrapped_climate_change
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
                self._away_delay_task = None
                self._transition_to_away()

        # Update override timer
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed = (datetime.now() - self._override_start_time).total_seconds() / 60
            remaining = self._override_duration_minutes - elapsed
            if remaining <= 0:
                self._mode = MODE_AUTO
                self._override_start_time = None
                self._last_written_temperature = 0
            else:
                self._override_start_time = datetime.now() - timedelta(
                    minutes=elapsed
                )

        # Calculate target temperature
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def _on_wrapped_climate_change(self, event):
        """Handle wrapped climate state changes.

        If the target temperature was changed externally (not by us), start an
        override so the change is respected instead of being overwritten.
        """
        new_state = event.data.get("new_state")
        if not new_state:
            return

        new_temp = new_state.attributes.get("target_temperature")
        if new_temp is None:
            return

        # Detect an external change: the temperature differs from what we last wrote
        if (
            self._last_written_temperature is not None
            and new_temp != self._last_written_temperature
        ):
            # Acknowledge the external change immediately so subsequent state-change
            # events with the same temperature don't re-trigger the override
            self._last_written_temperature = new_temp
            if self._default_override_mode == "infinity":
                await self.async_set_override_infinity(new_temp)
            else:
                await self.async_set_override_timer(self._default_override_duration, new_temp)

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

    def _transition_to_away(self):
        """Transition presence to away and interrupt override if needed."""
        self._presence = "away"
        if self._mode == MODE_OVERRIDE_TIMER and self._interruptible:
            self._mode = MODE_AUTO

    async def _start_away_delay(self):
        """Start away delay timer."""
        if self._away_delay_minutes == 0:
            self._transition_to_away()
            return
        if not self._away_delay_task:
            self._away_delay_remaining = self._away_delay_minutes * 60
            self._away_delay_task = True

    async def _cancel_away_delay(self):
        """Cancel away delay."""
        self._away_delay_task = None
        self._away_delay_remaining = 0

    def _get_scheduled_temperature(self) -> float:
        """Return the scheduled temperature for the current time, or fall back to auto_temperature."""
        if not self._schedule:
            return self._auto_temperature

        schedule_mode = self._schedule.get("mode", SCHEDULE_MODE_DAILY)
        now = datetime.now()
        weekday = now.weekday()  # Monday=0 … Sunday=6

        if schedule_mode == SCHEDULE_MODE_DAILY:
            nodes = self._schedule.get("daily", [])
        elif schedule_mode == SCHEDULE_MODE_52:
            if weekday < 5:
                nodes = self._schedule.get("weekday", [])
            else:
                nodes = self._schedule.get("weekend", [])
        elif schedule_mode == SCHEDULE_MODE_INDIVIDUAL:
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            nodes = self._schedule.get(day_names[weekday], [])
        else:
            nodes = []

        if not nodes:
            return self._auto_temperature

        def _parse_time(t: str):
            """Parse HH:MM time string; return a comparable time object."""
            try:
                return datetime.strptime(t, "%H:%M").time()
            except (ValueError, TypeError):
                _LOGGER.warning("Smart Climate: invalid time format '%s' in schedule node (expected HH:MM)", t)
                return None

        current_time = now.time().replace(second=0, microsecond=0)

        # Sort nodes by parsed time, skipping any with invalid times
        valid_nodes = []
        for node in nodes:
            t = _parse_time(node.get("time", ""))
            if t is not None and "temp" in node:
                valid_nodes.append((t, node["temp"]))
            else:
                _LOGGER.warning("Smart Climate: skipping schedule node with missing/invalid time or temp: %s", node)

        if not valid_nodes:
            return self._auto_temperature

        valid_nodes.sort(key=lambda x: x[0])

        # Find the last node whose time <= current time
        target_temp = None
        for node_time, node_temp in valid_nodes:
            if node_time <= current_time:
                target_temp = node_temp

        # If no node matched (current time is before the first node), wrap around to the last node
        if target_temp is None:
            target_temp = valid_nodes[-1][1]

        return target_temp

    async def _update_target_temperature(self):
        """Calculate and update target temperature to wrapped climate."""
        if self._mode == MODE_OVERRIDE_TIMER or self._mode == MODE_OVERRIDE_INFINITY:
            target = self._override_temperature
        elif self._mode == MODE_AUTO:
            if self._presence == "home":
                target = self._get_scheduled_temperature()
            else:
                target = self._away_temperature
        else:
            target = 21

        # Only write to the wrapped climate when the target temperature has changed;
        # callers are responsible for calling async_write_ha_state() to update the UI
        if target == self._last_written_temperature:
            return

        self._last_written_temperature = target
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
        self._last_written_temperature = 0
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_override_infinity(self, temperature: float):
        """Set override infinity mode."""
        self._mode = MODE_OVERRIDE_INFINITY
        self._override_temperature = temperature
        self._override_start_time = None
        self._last_written_temperature = 0
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        self._last_written_temperature = 0
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_interruptible(self, interruptible: bool):
        """Set interruptible mode."""
        self._interruptible = interruptible
        self.async_write_ha_state()

    async def async_set_auto_temperature(self, temperature: float):
        """Set the auto (home) temperature."""
        self._auto_temperature = temperature
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_temperature(self, temperature: float):
        """Set the away temperature."""
        self._away_temperature = temperature
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_delay(self, minutes: int):
        """Set the away delay in minutes."""
        self._away_delay_minutes = minutes
        self.async_write_ha_state()

    async def async_set_default_override_mode(self, mode: str, duration: int = None):
        """Set the default override mode and optionally the duration."""
        self._default_override_mode = mode
        if duration is not None:
            self._default_override_duration = duration
        self.async_write_ha_state()

    async def async_set_schedule(self, schedule: dict | None):
        """Set the temperature schedule used in auto mode when presence is home."""
        self._schedule = schedule
        await self._update_target_temperature()
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
            return self._get_scheduled_temperature()
        return self._away_temperature

    @property
    def extra_state_attributes(self):
        remaining_minutes = 0
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed = (datetime.now() - self._override_start_time).total_seconds() / 60
            remaining_minutes = max(0, self._override_duration_minutes - elapsed)

        return {
            ATTR_WRAPPED_CLIMATE: self._wrapped_climate,
            ATTR_ZONE_HOME: self._zone_home,
            ATTR_MODE: self._mode,
            ATTR_PRESENCE: "leaving" if self._away_delay_task else self._presence,
            ATTR_REMAINING_MINUTES: int(remaining_minutes),
            ATTR_INTERRUPTIBLE: self._interruptible,
            ATTR_OVERRIDE_TEMPERATURE: self._override_temperature,
            ATTR_AWAY_DELAY_SECONDS_REMAINING: self._away_delay_remaining,
            ATTR_AUTO_TEMPERATURE: self._auto_temperature,
            ATTR_AWAY_TEMPERATURE: self._away_temperature,
            ATTR_AWAY_DELAY_MINUTES: self._away_delay_minutes,
            ATTR_DEFAULT_OVERRIDE_MODE: self._default_override_mode,
            ATTR_DEFAULT_OVERRIDE_DURATION: self._default_override_duration,
            ATTR_SCHEDULE: self._schedule,
        }