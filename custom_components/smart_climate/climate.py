from datetime import timedelta
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.util import dt as dt_util
import logging

from .const import (
    DOMAIN,
    MODE_AUTO,
    MODE_OVERRIDE_TIMER,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    CONF_AWAY_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_INTERRUPTIBLE,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_AUTO_TEMPERATURE,
    CONF_SCHEDULE,
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    ATTR_MODE,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_INTERRUPTIBLE,
    ATTR_AWAY_DELAY_SECONDS_REMAINING,
    ATTR_OVERRIDE_TEMPERATURE,
    ATTR_WRAPPED_CLIMATE,
    ATTR_COOL_AUTO_TEMPERATURE,
    ATTR_COOL_AWAY_TEMPERATURE,
)
from . import schedule_helper
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

    # Register services (deduped — safe to call on every entry setup)
    await async_register_services(hass)


class SmartClimateEntity(ClimateEntity):
    """Smart Climate controller entity."""

    # HVAC modes for which the wrapper actively manages the target temperature.
    # Everything else the wrapped device reports (off, fan_only, dry, …) is
    # passed through untouched — the wrapper writes no setpoint for those.
    _HEATING_MODES = (HVACMode.HEAT, HVACMode.AUTO)
    _COOLING_MODES = (HVACMode.COOL,)

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
        self._attr_should_poll = False

        # Config
        self._wrapped_climate = wrapped_climate
        self._zone_home = zone_home
        self._away_temperature = away_temp
        self._away_delay_minutes = away_delay_minutes
        self._default_override_mode = default_override_mode
        self._default_override_duration = default_override_duration

        # State — auto_temperature and schedule are not constructor args; they are
        # restored from persisted config-entry storage (see async_set_* setters).
        self._mode = MODE_AUTO
        self._presence = "away"  # Start as away
        self._interruptible = interruptible
        self._auto_temperature = entry.data.get(CONF_AUTO_TEMPERATURE, 21)
        self._cool_auto_temperature = entry.data.get(CONF_COOL_AUTO_TEMPERATURE, 24)
        self._cool_away_temperature = entry.data.get(CONF_COOL_AWAY_TEMPERATURE, 28)
        self._override_temperature = 21
        self._override_start_time = None
        self._override_duration_minutes = 0
        self._next_node_datetime = None
        self._away_delay_task = None
        self._away_delay_start = None
        self._away_delay_remaining = 0
        self._schedule = entry.data.get(CONF_SCHEDULE, None)

    async def async_added_to_hass(self):
        """Initialize after added to hass."""
        await super().async_added_to_hass()

        # Store reference so services can route calls to this entity
        self.hass.data.setdefault(DOMAIN, {}).setdefault("entities", {})[self.entity_id] = self
        self.async_on_remove(
            lambda: self.hass.data.get(DOMAIN, {}).get("entities", {}).pop(self.entity_id, None)
        )

        # Start listening to zone changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._zone_home], self._on_zone_change
            )
        )

        # Start update timer (every 10 seconds) — register cancel for cleanup
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._update_state, timedelta(seconds=10)
            )
        )

        # Initial state update
        await self._update_state()

    async def _update_state(self, now=None):
        """Update internal state every interval."""
        current_time = dt_util.now()

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

        # Update away delay (timestamp-based to avoid tick-drift)
        if self._away_delay_task and self._away_delay_start is not None:
            elapsed = (current_time - self._away_delay_start).total_seconds()
            remaining = self._away_delay_minutes * 60 - elapsed
            self._away_delay_remaining = max(0, remaining)
            if remaining <= 0:
                self._presence = "away"
                self._away_delay_task = None
                self._away_delay_start = None
                if self._mode == MODE_OVERRIDE_TIMER and self._interruptible:
                    self._mode = MODE_AUTO

        # Update override timer
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed_minutes = (current_time - self._override_start_time).total_seconds() / 60
            if elapsed_minutes >= self._override_duration_minutes:
                self._mode = MODE_AUTO
                self._override_start_time = None

        # Update next-node override
        if self._mode == MODE_OVERRIDE_NEXT_NODE and self._next_node_datetime:
            if current_time >= self._next_node_datetime:
                self._mode = MODE_AUTO
                self._next_node_datetime = None

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
        if not self._away_delay_task:
            self._away_delay_start = dt_util.now()
            self._away_delay_remaining = self._away_delay_minutes * 60
            self._away_delay_task = True

    async def _cancel_away_delay(self):
        """Cancel away delay."""
        self._away_delay_task = None
        self._away_delay_start = None
        self._away_delay_remaining = 0

    async def _update_target_temperature(self):
        """Calculate and push the target temperature to the wrapped climate.

        The wrapper only manages a setpoint while the wrapped device is in a
        temperature-controlled mode (heat/cool/auto).  When the device is off —
        or in a mode that has no meaningful setpoint such as ``fan_only`` or
        ``dry`` — no temperature is written and the device is left untouched.
        Cooling modes use the dedicated ``cool_*`` setpoints; heat/auto use the
        heating setpoints and schedule.
        """
        wrapped = self.hass.states.get(self._wrapped_climate)
        if wrapped is None:
            # Wrapped entity unavailable — nothing we can safely control.
            return
        hvac_mode = wrapped.state
        if hvac_mode not in self._HEATING_MODES and hvac_mode not in self._COOLING_MODES:
            # off / fan_only / dry / unavailable — pass through, write no setpoint.
            return
        cooling = hvac_mode in self._COOLING_MODES

        if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE):
            target = self._override_temperature
        elif self._mode == MODE_AUTO:
            if self._presence == "home":
                if cooling:
                    # Cooling has no schedule in v1 — use the flat cool setpoint.
                    target = self._cool_auto_temperature
                elif self._schedule:
                    target = schedule_helper.get_scheduled_temperature(
                        self._schedule, dt_util.now(), self._auto_temperature
                    )
                    if not isinstance(target, (int, float)):
                        _LOGGER.warning(
                            "%s: schedule returned invalid temperature %r, using fallback",
                            self._attr_name,
                            target,
                        )
                        target = self._auto_temperature
                else:
                    target = self._auto_temperature
            else:
                target = self._cool_away_temperature if cooling else self._away_temperature
        else:
            target = self._cool_auto_temperature if cooling else self._auto_temperature

        # Set on wrapped climate
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": self._wrapped_climate,
                "temperature": target,
            },
        )

    def _persist(self, **changes) -> None:
        """Persist runtime-changeable settings to config-entry storage.

        Writes the given config keys into the entry's ``data`` so the values
        survive a Home Assistant restart (the constructor and
        ``async_setup_entry`` read them back on startup).  ``async_update_entry``
        is a synchronous callback despite the ``async_`` prefix.
        """
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, **changes}
        )

    async def async_set_override_timer(self, minutes: int, temperature: float):
        """Set override timer mode."""
        self._mode = MODE_OVERRIDE_TIMER
        self._override_temperature = temperature
        self._override_start_time = dt_util.now()
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

    async def async_set_override_next_node(self, temperature: float):
        """Set override until the next schedule node."""
        next_dt = schedule_helper.compute_next_node_datetime(self._schedule, dt_util.now())
        if next_dt is None:
            # No schedule configured — fall back to infinity mode
            _LOGGER.info(
                "%s: no schedule configured; next_node override falls back to infinity",
                self._attr_name,
            )
            await self.async_set_override_infinity(temperature)
            return
        self._mode = MODE_OVERRIDE_NEXT_NODE
        self._override_temperature = temperature
        self._next_node_datetime = next_dt
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        self._next_node_datetime = None
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_interruptible(self, interruptible: bool):
        """Set interruptible mode."""
        self._interruptible = interruptible
        self._persist(**{CONF_INTERRUPTIBLE: interruptible})
        self.async_write_ha_state()

    async def async_set_auto_temperature(self, temperature: float):
        """Set the target temperature used in auto/home mode."""
        self._auto_temperature = temperature
        self._persist(**{CONF_AUTO_TEMPERATURE: temperature})
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_temperature(self, temperature: float):
        """Set the target temperature used in away mode."""
        self._away_temperature = temperature
        self._persist(**{CONF_AWAY_TEMPERATURE: temperature})
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_cool_auto_temperature(self, temperature: float):
        """Set the target temperature used when home and the device is cooling."""
        self._cool_auto_temperature = temperature
        self._persist(**{CONF_COOL_AUTO_TEMPERATURE: temperature})
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_cool_away_temperature(self, temperature: float):
        """Set the target temperature used when away and the device is cooling."""
        self._cool_away_temperature = temperature
        self._persist(**{CONF_COOL_AWAY_TEMPERATURE: temperature})
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_away_delay(self, minutes: int):
        """Set the delay before switching to away mode."""
        self._away_delay_minutes = minutes
        self._persist(**{CONF_AWAY_DELAY_MINUTES: minutes})
        self.async_write_ha_state()

    async def async_set_default_override_mode(self, mode: str, duration: int):
        """Set the default mode used when a temperature override is triggered."""
        self._default_override_mode = mode
        self._default_override_duration = duration
        self._persist(**{
            CONF_DEFAULT_OVERRIDE_MODE: mode,
            CONF_DEFAULT_OVERRIDE_DURATION: duration,
        })
        self.async_write_ha_state()

    async def async_set_schedule(self, schedule):
        """Set the temperature schedule used in auto/home mode."""
        self._schedule = schedule
        self._persist(**{CONF_SCHEDULE: schedule})
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set temperature — activate override based on default override setting."""
        temperature = kwargs.get("temperature", 22)

        if self._default_override_mode == "infinity":
            await self.async_set_override_infinity(temperature)
        elif self._default_override_mode == "next_node":
            await self.async_set_override_next_node(temperature)
        else:
            # timer mode (default)
            await self.async_set_override_timer(self._default_override_duration, temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Delegate HVAC mode change to the wrapped climate entity."""
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {
                "entity_id": self._wrapped_climate,
                "hvac_mode": hvac_mode,
            },
        )
        # Re-evaluate the setpoint for the newly selected mode (heat/cool/auto
        # pick different setpoints; off/fan_only/dry write nothing).
        await self._update_target_temperature()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Delegate fan-mode change to the wrapped climate entity."""
        await self.hass.services.async_call(
            "climate",
            "set_fan_mode",
            {"entity_id": self._wrapped_climate, "fan_mode": fan_mode},
        )
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the wrapped climate off."""
        await self.hass.services.async_call(
            "climate", "turn_off", {"entity_id": self._wrapped_climate}
        )
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the wrapped climate on."""
        await self.hass.services.async_call(
            "climate", "turn_on", {"entity_id": self._wrapped_climate}
        )
        await self._update_target_temperature()
        self.async_write_ha_state()

    def _wrapped_state(self):
        """Return the wrapped entity's state object, or ``None``."""
        return self.hass.states.get(self._wrapped_climate)

    @property
    def supported_features(self):
        """Mirror the wrapped device's fan/turn-on/off support."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        wrapped = self._wrapped_state()
        if wrapped and (wrapped.attributes.get("supported_features", 0) & ClimateEntityFeature.FAN_MODE):
            features |= ClimateEntityFeature.FAN_MODE
        # We can always turn the wrapped device on/off via its hvac mode.
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features

    @property
    def hvac_modes(self):
        """Mirror the wrapped device's supported HVAC modes."""
        wrapped = self._wrapped_state()
        if wrapped:
            modes = wrapped.attributes.get("hvac_modes")
            if modes:
                return list(modes)
        return [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]

    @property
    def hvac_mode(self):
        wrapped = self._wrapped_state()
        if wrapped:
            return wrapped.state
        return HVACMode.HEAT

    @property
    def fan_modes(self):
        wrapped = self._wrapped_state()
        if wrapped:
            return wrapped.attributes.get("fan_modes")
        return None

    @property
    def fan_mode(self):
        wrapped = self._wrapped_state()
        if wrapped:
            return wrapped.attributes.get("fan_mode")
        return None

    @property
    def min_temp(self):
        wrapped = self._wrapped_state()
        if wrapped and wrapped.attributes.get("min_temp") is not None:
            return wrapped.attributes["min_temp"]
        return 5

    @property
    def max_temp(self):
        wrapped = self._wrapped_state()
        if wrapped and wrapped.attributes.get("max_temp") is not None:
            return wrapped.attributes["max_temp"]
        return 35

    @property
    def target_temperature_step(self):
        wrapped = self._wrapped_state()
        if wrapped and wrapped.attributes.get("target_temp_step") is not None:
            return wrapped.attributes["target_temp_step"]
        return 0.5

    @property
    def current_temperature(self):
        wrapped = self._wrapped_state()
        if wrapped:
            return wrapped.attributes.get("current_temperature")
        return None

    @property
    def target_temperature(self):
        wrapped = self._wrapped_state()
        if wrapped:
            return wrapped.attributes.get("temperature")
        return 21

    @property
    def extra_state_attributes(self):
        remaining_minutes = 0
        if self._mode == MODE_OVERRIDE_TIMER and self._override_start_time:
            elapsed = (dt_util.now() - self._override_start_time).total_seconds() / 60
            remaining_minutes = max(0, self._override_duration_minutes - elapsed)

        return {
            ATTR_MODE: self._mode,
            ATTR_PRESENCE: self._presence,
            ATTR_REMAINING_MINUTES: int(remaining_minutes),
            ATTR_INTERRUPTIBLE: self._interruptible,
            ATTR_OVERRIDE_TEMPERATURE: self._override_temperature,
            ATTR_AWAY_DELAY_SECONDS_REMAINING: int(self._away_delay_remaining),
            ATTR_WRAPPED_CLIMATE: self._wrapped_climate,
            ATTR_COOL_AUTO_TEMPERATURE: self._cool_auto_temperature,
            ATTR_COOL_AWAY_TEMPERATURE: self._cool_away_temperature,
        }