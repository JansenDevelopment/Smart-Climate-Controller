from datetime import datetime, timedelta
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
import logging

from .const import (
    MODE_AUTO,
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
    PRESET_AUTO,
    PRESET_OVERRIDE_TIMER,
    PRESET_OVERRIDE_INFINITY,
    PRESET_OVERRIDE_NEXT_NODE,
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
    ATTR_NEXT_NODE_MINUTES,
)
from .schedule_helper import (
    get_scheduled_temperature,
    compute_next_node_datetime,
    get_next_node_minutes,
)
from .services import async_register_services

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

    await async_register_services(hass, entity)


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
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
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
        self._is_off = False
        self._presence = "away"  # Start as away
        self._interruptible = interruptible
        self._override_temperature = 21
        self._override_start_time = None
        self._override_duration_minutes = 0
        self._override_next_node_time = None
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

        # Initialize _last_written_temperature from the wrapped climate's current state
        # This ensures we can detect external temperature changes even before we write
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped and wrapped.state != HVACMode.OFF:
            current_temp = wrapped.attributes.get("target_temperature")
            if current_temp is not None:
                self._last_written_temperature = current_temp

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
                    if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE) and self._interruptible:
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

        # Update override next node
        if self._mode == MODE_OVERRIDE_NEXT_NODE:
            if (
                self._override_next_node_time is not None
                and datetime.now() >= self._override_next_node_time
            ):
                self._mode = MODE_AUTO
                self._override_next_node_time = None
                self._last_written_temperature = 0

        # Calculate target temperature
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def _on_wrapped_climate_change(self, event):
        """Handle wrapped climate state changes.

        Syncs HVAC mode (off/on) and detects external target-temperature
        changes so they are reflected as an override on the smart climate.
        """
        new_state = event.data.get("new_state")
        if not new_state:
            return

        old_state = event.data.get("old_state")

        # --- HVAC mode sync ---
        new_hvac = new_state.state
        old_hvac = getattr(old_state, "state", None)
        if new_hvac != old_hvac:
            if new_hvac == HVACMode.OFF:
                self._is_off = True
                self.async_write_ha_state()
                return
            elif old_hvac == HVACMode.OFF:
                self._is_off = False
                # When turning on, check if the temperature was set by the user
                # by comparing it to what we would calculate
                new_temp = new_state.attributes.get("target_temperature")
                if new_temp is not None:
                    # Calculate what temperature the smart climate would set
                    if self._presence == "home":
                        expected_temp = self._get_scheduled_temperature()
                    else:
                        expected_temp = self._away_temperature

                    # If the temperature differs from what we would calculate,
                    # treat it as an external change and create an override
                    if new_temp != expected_temp:
                        self._last_written_temperature = new_temp
                        if self._default_override_mode == "infinity":
                            await self.async_set_override_infinity(new_temp)
                        elif self._default_override_mode == "next_node":
                            await self.async_set_override_next_node(new_temp)
                        else:
                            await self.async_set_override_timer(self._default_override_duration, new_temp)
                        return

                # Normal case: set our calculated temperature
                self._last_written_temperature = 0
                await self._update_target_temperature()
                self.async_write_ha_state()
                return

        # --- External temperature change detection ---
        new_temp = new_state.attributes.get("target_temperature")
        if new_temp is None:
            return

        # Detect an external change: the temperature differs from what we last wrote
        # or we haven't written anything yet (initial state)
        if (
            self._last_written_temperature is None
            or new_temp != self._last_written_temperature
        ):
            # Acknowledge the external change immediately so subsequent state-change
            # events with the same temperature don't re-trigger the override
            self._last_written_temperature = new_temp
            if self._default_override_mode == "infinity":
                await self.async_set_override_infinity(new_temp)
            elif self._default_override_mode == "next_node":
                await self.async_set_override_next_node(new_temp)
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
                if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE) and self._interruptible:
                    self._mode = MODE_AUTO
            else:
                # Everyone left
                await self._start_away_delay()
        except ValueError:
            pass

    def _transition_to_away(self):
        """Transition presence to away and interrupt override if needed."""
        self._presence = "away"
        if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE) and self._interruptible:
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
        return get_scheduled_temperature(self._schedule, datetime.now(), self._auto_temperature)

    def _compute_next_node_datetime(self) -> datetime | None:
        """Return the datetime of the next upcoming schedule node, or None if unavailable."""
        return compute_next_node_datetime(self._schedule, datetime.now())

    def _get_next_node_minutes(self) -> int | None:
        """Return minutes until the next schedule node, or None if no schedule."""
        return get_next_node_minutes(self._schedule, datetime.now())

    async def _update_target_temperature(self):
        """Calculate and update target temperature to wrapped climate."""
        if self._is_off:
            return

        if self._mode == MODE_OVERRIDE_TIMER or self._mode == MODE_OVERRIDE_INFINITY or self._mode == MODE_OVERRIDE_NEXT_NODE:
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

    async def async_set_override_next_node(self, temperature: float):
        """Set override until the next schedule node."""
        now = datetime.now()
        # Preserve the existing override end-time when already active and not yet
        # expired; only (re-)calculate when entering the mode fresh or when the
        # previously stored time has already passed.
        if (
            self._mode != MODE_OVERRIDE_NEXT_NODE
            or self._override_next_node_time is None
            or self._override_next_node_time <= now
        ):
            self._override_next_node_time = self._compute_next_node_datetime()
        self._mode = MODE_OVERRIDE_NEXT_NODE
        self._override_temperature = temperature
        self._override_start_time = None
        self._last_written_temperature = 0
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        self._override_next_node_time = None
        self._last_written_temperature = 0
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def _async_save_config(self):
        """Persist current configuration values to the config entry storage."""
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_AWAY_TEMPERATURE: self._away_temperature,
                CONF_AWAY_DELAY_MINUTES: self._away_delay_minutes,
                CONF_INTERRUPTIBLE: self._interruptible,
                CONF_DEFAULT_OVERRIDE_MODE: self._default_override_mode,
                CONF_DEFAULT_OVERRIDE_DURATION: self._default_override_duration,
                CONF_AUTO_TEMPERATURE: self._auto_temperature,
                CONF_SCHEDULE: self._schedule,
            },
        )

    async def async_set_interruptible(self, interruptible: bool):
        """Set interruptible mode."""
        self._interruptible = interruptible
        await self._async_save_config()
        self.async_write_ha_state()

    async def async_set_auto_temperature(self, temperature: float):
        """Set the auto (home) temperature."""
        self._auto_temperature = temperature
        await self._async_save_config()
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_temperature(self, temperature: float):
        """Set the away temperature."""
        self._away_temperature = temperature
        await self._async_save_config()
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_delay(self, minutes: int):
        """Set the away delay in minutes."""
        self._away_delay_minutes = minutes
        await self._async_save_config()
        self.async_write_ha_state()

    async def async_set_default_override_mode(self, mode: str, duration: int = None):
        """Set the default override mode and optionally the duration."""
        self._default_override_mode = mode
        if duration is not None:
            self._default_override_duration = duration
        await self._async_save_config()
        self.async_write_ha_state()

    async def async_set_schedule(self, schedule: dict | None):
        """Set the temperature schedule used in auto mode when presence is home."""
        self._schedule = schedule
        await self._async_save_config()
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set temperature - preserve the active override mode, or fall back to the default."""
        temperature = kwargs.get("temperature", 22)
        now = datetime.now()

        if self._mode == MODE_OVERRIDE_NEXT_NODE:
            await self.async_set_override_next_node(temperature)
        elif self._mode == MODE_OVERRIDE_INFINITY:
            await self.async_set_override_infinity(temperature)
        elif self._mode == MODE_OVERRIDE_TIMER:
            remaining = self._override_duration_minutes
            if self._override_start_time:
                elapsed = (now - self._override_start_time).total_seconds() / 60
                remaining = max(1, int(self._override_duration_minutes - elapsed))
            await self.async_set_override_timer(remaining, temperature)
        elif self._default_override_mode == "infinity":
            await self.async_set_override_infinity(temperature)
        elif self._default_override_mode == "next_node":
            await self.async_set_override_next_node(temperature)
        else:
            # timer mode (default)
            await self.async_set_override_timer(self._default_override_duration, temperature)

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_mode(self):
        if self._is_off:
            return HVACMode.OFF
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped and wrapped.state == HVACMode.OFF:
            return HVACMode.OFF
        return HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Set HVAC mode. OFF turns off the wrapped climate; HEAT resumes normal operation."""
        if hvac_mode == HVACMode.OFF:
            self._is_off = True
            await self.hass.services.async_call(
                "climate",
                "turn_off",
                {"entity_id": self._wrapped_climate},
            )
            self.async_write_ha_state()
        elif hvac_mode == HVACMode.HEAT:
            self._is_off = False
            await self.hass.services.async_call(
                "climate",
                "turn_on",
                {"entity_id": self._wrapped_climate},
            )
            self._last_written_temperature = 0
            await self._update_target_temperature()
            self.async_write_ha_state()

    @property
    def preset_modes(self):
        return [PRESET_AUTO, PRESET_OVERRIDE_TIMER, PRESET_OVERRIDE_INFINITY, PRESET_OVERRIDE_NEXT_NODE]

    @property
    def preset_mode(self):
        if self._mode == MODE_AUTO:
            return PRESET_AUTO
        if self._mode == MODE_OVERRIDE_TIMER:
            return PRESET_OVERRIDE_TIMER
        if self._mode == MODE_OVERRIDE_INFINITY:
            return PRESET_OVERRIDE_INFINITY
        if self._mode == MODE_OVERRIDE_NEXT_NODE:
            return PRESET_OVERRIDE_NEXT_NODE
        return PRESET_AUTO

    async def async_set_preset_mode(self, preset_mode: str):
        """Set preset mode, mapping to a smart climate override mode."""
        if preset_mode == PRESET_AUTO:
            await self.async_clear_override()
        elif preset_mode == PRESET_OVERRIDE_TIMER:
            await self.async_set_override_timer(
                self._default_override_duration, self._override_temperature
            )
        elif preset_mode == PRESET_OVERRIDE_INFINITY:
            await self.async_set_override_infinity(self._override_temperature)
        elif preset_mode == PRESET_OVERRIDE_NEXT_NODE:
            await self.async_set_override_next_node(self._override_temperature)

    @property
    def hvac_action(self):
        """Return the current HVAC action, forwarded from the wrapped climate entity."""
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped:
            return wrapped.attributes.get("hvac_action")
        return None

    @property
    def current_temperature(self):
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped:
            return wrapped.attributes.get("current_temperature")
        return None

    @property
    def target_temperature(self):
        if self.hvac_mode == HVACMode.OFF:
            return None
        if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE):
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
        elif self._mode == MODE_OVERRIDE_NEXT_NODE and self._override_next_node_time:
            remaining_minutes = max(
                0,
                (self._override_next_node_time - datetime.now()).total_seconds() / 60,
            )

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
            ATTR_NEXT_NODE_MINUTES: self._get_next_node_minutes(),
        }