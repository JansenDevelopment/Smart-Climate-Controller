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
    CONF_DEVICES,
    CONF_HVAC_MODE,
    CONF_TEMPERATURE_SOURCE,
    CONF_TEMPERATURE_SENSOR,
    CONF_PRIMARY_DEVICE,
    CONF_HYSTERESIS,
    CONF_INTEGRATION_DRIVEN_AUTO,
    ROLE_BOTH,
    TEMP_SOURCE_SENSOR,
    TEMP_SOURCE_PRIMARY,
    TEMP_SOURCE_MEAN,
    DEFAULT_HYSTERESIS,
    ATTR_MODE,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_INTERRUPTIBLE,
    ATTR_AWAY_DELAY_SECONDS_REMAINING,
    ATTR_OVERRIDE_TEMPERATURE,
    ATTR_WRAPPED_CLIMATE,
    ATTR_COOL_AUTO_TEMPERATURE,
    ATTR_COOL_AWAY_TEMPERATURE,
    ATTR_AUTO_TEMPERATURE,
    ATTR_AWAY_TEMPERATURE,
    ATTR_AWAY_DELAY_MINUTES,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_HEAT_TARGET,
    ATTR_COOL_LIMIT,
    ATTR_INTENT,
    ATTR_DEVICES,
)
from . import control, schedule_helper
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
    """Smart Climate coordinator entity.

    Owns its own HVAC mode (off/heat/cool/auto) and commands one or more
    actuator devices (each tagged heat/cool/both). Every evaluation runs through
    the pure ``control`` core: resolve the heat/cool band → decide a single
    intent → route it to the devices by role. See docs/multi-device-design.md.
    """

    # The coordinator's own HVAC modes (not mirrored from a device).
    _OWN_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]

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
        self._zone_home = zone_home
        self._away_temperature = away_temp
        self._away_delay_minutes = away_delay_minutes
        self._default_override_mode = default_override_mode
        self._default_override_duration = default_override_duration

        # Actuator devices — new `devices` list, or migrate a single
        # `wrapped_climate` to one `both`-role device.
        self._devices = self._build_devices(entry, wrapped_climate)
        # Back-compat single-device attribute (first device, or None).
        self._wrapped_climate = self._devices[0]["entity_id"] if self._devices else None

        # Coordinator-owned HVAC mode + tunables (restored from entry.data).
        self._hvac_mode = entry.data.get(CONF_HVAC_MODE, HVACMode.HEAT)
        self._temperature_source = entry.data.get(CONF_TEMPERATURE_SOURCE, TEMP_SOURCE_MEAN)
        self._temperature_sensor = entry.data.get(CONF_TEMPERATURE_SENSOR)
        self._primary_device = entry.data.get(CONF_PRIMARY_DEVICE)
        self._hysteresis = entry.data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        self._integration_driven_auto = entry.data.get(CONF_INTEGRATION_DRIVEN_AUTO, True)
        self._intent = None
        self._heat_target = None
        self._cool_target = None
        self._active_target = None

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

    @staticmethod
    def _build_devices(entry, wrapped_climate):
        """Return the actuator device list, migrating a single wrapped entity."""
        devices = entry.data.get(CONF_DEVICES)
        if devices:
            return [
                {"entity_id": d["entity_id"], "role": d.get("role", ROLE_BOTH)}
                for d in devices
                if d.get("entity_id")
            ]
        if wrapped_climate:
            return [{"entity_id": wrapped_climate, "role": ROLE_BOTH}]
        return []

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

        # React to actuator / temperature-sensor changes so control re-evaluates
        # promptly (e.g. a device coming back online, or the room warming up).
        watched = [d["entity_id"] for d in self._devices]
        if self._temperature_sensor:
            watched.append(self._temperature_sensor)
        if watched:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, watched, self._on_watched_change
                )
            )

        # Start update timer (every 10 seconds) — register cancel for cleanup
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._update_state, timedelta(seconds=10)
            )
        )

        # Migration: if the coordinator mode was never persisted, adopt the
        # first device's current mode so upgrading a single-device setup does
        # not change its behavior on the first run.
        if CONF_HVAC_MODE not in self.entry.data and self._devices:
            state = self.hass.states.get(self._devices[0]["entity_id"])
            if state and state.state in self._OWN_HVAC_MODES:
                self._hvac_mode = state.state

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

        # Evaluate the control decision and drive the devices
        await self._apply_control()
        self.async_write_ha_state()

    async def _on_watched_change(self, event):
        """Re-evaluate control when a device or the temp sensor changes."""
        await self._apply_control()
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

    # ---- Control pipeline -------------------------------------------------

    def _resolve_band(self):
        """Return (heat_target, cool_target, override_target) for right now."""
        override_target = None
        if self._mode in (MODE_OVERRIDE_TIMER, MODE_OVERRIDE_INFINITY, MODE_OVERRIDE_NEXT_NODE):
            override_target = self._override_temperature

        if self._presence == "home":
            heat_target, cool_target = schedule_helper.get_scheduled_band(
                self._schedule, dt_util.now(),
                self._auto_temperature, self._cool_auto_temperature,
            )
            if not isinstance(heat_target, (int, float)):
                heat_target = self._auto_temperature
            if not isinstance(cool_target, (int, float)):
                cool_target = self._cool_auto_temperature
        else:
            heat_target = self._away_temperature
            cool_target = self._cool_away_temperature
        return heat_target, cool_target, override_target

    def _room_temperature(self):
        """Return the room temperature per the selected source, with fallthrough."""
        if self._temperature_source == TEMP_SOURCE_SENSOR:
            v = self._numeric_state(self._temperature_sensor)
            if v is not None:
                return v
        if self._temperature_source == TEMP_SOURCE_PRIMARY:
            v = self._device_current_temp(self._primary_device)
            if v is not None:
                return v
        # mean (default), or fallthrough when the selected source has no value
        temps = [self._device_current_temp(d["entity_id"]) for d in self._devices]
        temps = [t for t in temps if t is not None]
        if temps:
            return sum(temps) / len(temps)
        return self._numeric_state(self._temperature_sensor)

    def _numeric_state(self, entity_id):
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if not state:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _device_current_temp(self, entity_id):
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if not state:
            return None
        val = state.attributes.get("current_temperature")
        return val if isinstance(val, (int, float)) else None

    def _device_caps(self):
        """Return per-device dicts (entity_id, role, supports_fan_only) for routing."""
        caps = []
        for dev in self._devices:
            state = self.hass.states.get(dev["entity_id"])
            modes = state.attributes.get("hvac_modes") if state else None
            caps.append({
                "entity_id": dev["entity_id"],
                "role": dev.get("role", ROLE_BOTH),
                "supports_fan_only": HVACMode.FAN_ONLY in (modes or []),
            })
        return caps

    async def _apply_control(self):
        """Resolve the control decision and drive the actuator devices."""
        if not self._devices:
            return

        heat_target, cool_target, override_target = self._resolve_band()
        self._heat_target = heat_target
        self._cool_target = cool_target
        room_temp = self._room_temperature()

        decision = control.decide(
            mode=self._hvac_mode,
            room_temp=room_temp,
            heat_target=heat_target,
            cool_target=cool_target,
            override_target=override_target,
            prev_intent=self._intent,
            hysteresis=self._hysteresis,
        )
        self._intent = decision.intent
        self._active_target = decision.target

        commands = control.plan_routes(decision, self._device_caps())
        for cmd in commands:
            await self._execute(cmd)

    async def _execute(self, cmd):
        """Apply one DeviceCommand, only calling services when state differs."""
        state = self.hass.states.get(cmd.entity_id)
        if state is None:
            return  # device unavailable — skip
        if state.state != cmd.hvac_mode:
            await self.hass.services.async_call(
                "climate", "set_hvac_mode",
                {"entity_id": cmd.entity_id, "hvac_mode": cmd.hvac_mode},
            )
        if cmd.temperature is not None and state.attributes.get("temperature") != cmd.temperature:
            await self.hass.services.async_call(
                "climate", "set_temperature",
                {"entity_id": cmd.entity_id, "temperature": cmd.temperature},
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
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_override_infinity(self, temperature: float):
        """Set override infinity mode."""
        self._mode = MODE_OVERRIDE_INFINITY
        self._override_temperature = temperature
        self._override_start_time = None
        await self._apply_control()
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
        await self._apply_control()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        self._next_node_datetime = None
        await self._apply_control()
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
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_away_temperature(self, temperature: float):
        """Set the target temperature used in away mode."""
        self._away_temperature = temperature
        self._persist(**{CONF_AWAY_TEMPERATURE: temperature})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_cool_auto_temperature(self, temperature: float):
        """Set the target temperature used when home and the device is cooling."""
        self._cool_auto_temperature = temperature
        self._persist(**{CONF_COOL_AUTO_TEMPERATURE: temperature})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_cool_away_temperature(self, temperature: float):
        """Set the target temperature used when away and the device is cooling."""
        self._cool_away_temperature = temperature
        self._persist(**{CONF_COOL_AWAY_TEMPERATURE: temperature})
        await self._apply_control()
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
        await self._apply_control()
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
        """Set the coordinator's own HVAC mode and re-drive the devices."""
        self._hvac_mode = hvac_mode
        self._persist(**{CONF_HVAC_MODE: hvac_mode})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Delegate fan mode to the single fan-capable device, if any."""
        device_id = self._single_fan_device()
        if device_id:
            await self.hass.services.async_call(
                "climate", "set_fan_mode",
                {"entity_id": device_id, "fan_mode": fan_mode},
            )
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the coordinator off (powers all actuators down)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the coordinator on (defaults to heat)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    # ---- Capability aggregation ------------------------------------------

    def _single_fan_device(self):
        """Return the entity_id iff exactly one device supports fan mode."""
        fan_devices = [
            d["entity_id"]
            for d in self._devices
            if (state := self.hass.states.get(d["entity_id"]))
            and (state.attributes.get("supported_features", 0) & ClimateEntityFeature.FAN_MODE)
        ]
        return fan_devices[0] if len(fan_devices) == 1 else None

    def _device_states(self):
        return [
            s
            for s in (self.hass.states.get(d["entity_id"]) for d in self._devices)
            if s
        ]

    @property
    def supported_features(self):
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self._single_fan_device():
            features |= ClimateEntityFeature.FAN_MODE
        return features

    @property
    def hvac_modes(self):
        return list(self._OWN_HVAC_MODES)

    @property
    def hvac_mode(self):
        return self._hvac_mode

    @property
    def hvac_action(self):
        return control.intent_to_hvac_action(self._intent)

    @property
    def fan_modes(self):
        device_id = self._single_fan_device()
        state = self.hass.states.get(device_id) if device_id else None
        return state.attributes.get("fan_modes") if state else None

    @property
    def fan_mode(self):
        device_id = self._single_fan_device()
        state = self.hass.states.get(device_id) if device_id else None
        return state.attributes.get("fan_mode") if state else None

    @property
    def min_temp(self):
        mins = [s.attributes.get("min_temp") for s in self._device_states()]
        mins = [m for m in mins if isinstance(m, (int, float))]
        return max(mins) if mins else 5

    @property
    def max_temp(self):
        maxs = [s.attributes.get("max_temp") for s in self._device_states()]
        maxs = [m for m in maxs if isinstance(m, (int, float))]
        return min(maxs) if maxs else 35

    @property
    def target_temperature_step(self):
        steps = [s.attributes.get("target_temp_step") for s in self._device_states()]
        steps = [x for x in steps if isinstance(x, (int, float))]
        return max(steps) if steps else 0.5

    @property
    def current_temperature(self):
        return self._room_temperature()

    @property
    def target_temperature(self):
        if self._active_target is not None:
            return self._active_target
        return self._heat_target

    @property
    def device_info(self):
        """Group all Smart Climate entities for this entry under one device."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self._attr_name,
            "manufacturer": "Smart Climate",
            "model": "Smart Climate Controller",
        }

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
            ATTR_AUTO_TEMPERATURE: self._auto_temperature,
            ATTR_AWAY_TEMPERATURE: self._away_temperature,
            ATTR_AWAY_DELAY_MINUTES: self._away_delay_minutes,
            ATTR_DEFAULT_OVERRIDE_MODE: self._default_override_mode,
            ATTR_DEFAULT_OVERRIDE_DURATION: self._default_override_duration,
            ATTR_HEAT_TARGET: self._heat_target,
            ATTR_COOL_LIMIT: self._cool_target,
            ATTR_INTENT: self._intent,
            ATTR_DEVICES: self._devices,
        }