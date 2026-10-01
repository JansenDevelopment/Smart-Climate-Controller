import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import ClassVar

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from . import control, cooling, schedule_helper
from .const import (
    ATTR_AUTO_TEMPERATURE,
    ATTR_AWAY_DELAY_MINUTES,
    ATTR_AWAY_DELAY_SECONDS_REMAINING,
    ATTR_AWAY_TEMPERATURE,
    ATTR_COOL_AUTO_TEMPERATURE,
    ATTR_COOL_AWAY_TEMPERATURE,
    ATTR_COOL_LIMIT,
    ATTR_COOLING_ALLOWED,
    ATTR_COOLING_MODE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    ATTR_DEVICES,
    ATTR_FORECAST_HIGH_TODAY,
    ATTR_FORECAST_HIGH_TOMORROW,
    ATTR_HARD_CEILING,
    ATTR_HEAT_TARGET,
    ATTR_INTENT,
    ATTR_INTERRUPTIBLE,
    ATTR_MODE,
    ATTR_OUTDOOR_MAX_24H,
    ATTR_OUTDOOR_SENSOR,
    ATTR_OVERRIDE_TEMPERATURE,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_ROOM_TREND,
    ATTR_SCHEDULE,
    ATTR_SUPPORT_ACTIVE,
    ATTR_SUPPORT_DELTA,
    ATTR_SUPPORT_ENABLED,
    ATTR_WARM_THRESHOLD,
    ATTR_WEATHER_ENTITY,
    ATTR_WRAPPED_CLIMATE,
    CONF_AUTO_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_AWAY_TEMPERATURE,
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    CONF_COOLING_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEVICES,
    CONF_HARD_CEILING,
    CONF_HVAC_MODE,
    CONF_HYSTERESIS,
    CONF_INTERRUPTIBLE,
    CONF_OUTDOOR_SENSOR,
    CONF_PARK,
    CONF_PRIMARY_DEVICE,
    CONF_SCHEDULE,
    CONF_SUPPORT_DELTA,
    CONF_SUPPORT_ENABLED,
    CONF_SUPPORT_GRACE,
    CONF_SUPPORT_MIN_RISE,
    CONF_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_SOURCE,
    CONF_TIER,
    CONF_WARM_THRESHOLD,
    CONF_WEATHER_ENTITY,
    CONF_WRAPPED_CLIMATE,
    CONF_ZONE_HOME,
    COOLING_AUTO,
    COOLING_MODES,
    DEFAULT_HARD_CEILING,
    DEFAULT_HYSTERESIS,
    DEFAULT_SUPPORT_DELTA,
    DEFAULT_SUPPORT_GRACE_MIN,
    DEFAULT_SUPPORT_MIN_RISE,
    DEFAULT_WARM_THRESHOLD,
    DOMAIN,
    MODE_AUTO,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
    MODE_OVERRIDE_TIMER,
    PARK_FAN_ONLY,
    ROLE_BOTH,
    SUBENTRY_TYPE_DEVICE,
    TEMP_SOURCE_MEAN,
    TEMP_SOURCE_PRIMARY,
    TEMP_SOURCE_SENSOR,
    TIER_PRIMARY,
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
    _OWN_HVAC_MODES: ClassVar[list[HVACMode]] = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.AUTO,
    ]

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

        # Coordinator-owned HVAC mode (persisted to entry.data). The instance
        # tunables (temp source, hysteresis, auto toggle) are read *live* via
        # _conf() so Options-flow changes take effect without a reload.
        self._hvac_mode = entry.data.get(CONF_HVAC_MODE, HVACMode.HEAT)
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

        # Cooling policy (off / auto / on) and heat support (the CV next to a
        # more efficient primary heater such as an airco).
        self._cooling_mode = entry.data.get(CONF_COOLING_MODE, COOLING_AUTO)
        self._cooling_allowed = False
        self._support_enabled = entry.data.get(CONF_SUPPORT_ENABLED, True)
        self._support_active = False
        self._room_trend = control.RoomTrend()
        self._heat_since = None

        # Outdoor context for the auto-cooling policy.
        self._outdoor_tracker = cooling.OutdoorMaxTracker()
        self._forecast_highs = (None, None)
        self._forecast_fetched = None

    @staticmethod
    def _build_devices(entry, wrapped_climate):
        """Return the actuator device list from all sources.

        Devices come from (in order) config subentries of type ``device`` and an
        ``entry.data['devices']`` list; a legacy single ``wrapped_climate`` is
        migrated to one ``both``-role device when no list is present.
        """
        devices = []
        seen = set()

        def _add(entity_id, role, tier=None, park=None):
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                devices.append({
                    "entity_id": entity_id,
                    "role": role or ROLE_BOTH,
                    "tier": tier or TIER_PRIMARY,
                    "park": park or PARK_FAN_ONLY,
                })

        subentries = getattr(entry, "subentries", None)
        if isinstance(subentries, Mapping):
            for sub in subentries.values():
                if getattr(sub, "subentry_type", None) == SUBENTRY_TYPE_DEVICE:
                    data = getattr(sub, "data", {}) or {}
                    _add(
                        data.get("entity_id"), data.get("role"),
                        data.get(CONF_TIER), data.get(CONF_PARK),
                    )

        for d in entry.data.get(CONF_DEVICES, []) or []:
            _add(d.get("entity_id"), d.get("role"), d.get(CONF_TIER), d.get(CONF_PARK))

        if not devices and wrapped_climate:
            _add(wrapped_climate, ROLE_BOTH)
        return devices

    def _conf(self, key, default):
        """Read a tunable live — entry.options overrides entry.data."""
        options = getattr(self.entry, "options", None)
        if isinstance(options, Mapping) and key in options:
            return options[key]
        data = self.entry.data
        if isinstance(data, Mapping) and key in data:
            return data[key]
        return default

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
        sensor = self._conf(CONF_TEMPERATURE_SENSOR, None)
        if sensor:
            watched.append(sensor)
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
        if (
            self._mode == MODE_OVERRIDE_NEXT_NODE
            and self._next_node_datetime
            and current_time >= self._next_node_datetime
        ):
            self._mode = MODE_AUTO
            self._next_node_datetime = None

        # Outdoor context for the cooling policy, then evaluate + drive devices
        await self._refresh_outdoor(current_time)
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
        source = self._conf(CONF_TEMPERATURE_SOURCE, TEMP_SOURCE_MEAN)
        sensor = self._conf(CONF_TEMPERATURE_SENSOR, None)
        if source == TEMP_SOURCE_SENSOR:
            v = self._numeric_state(sensor)
            if v is not None:
                return v
        if source == TEMP_SOURCE_PRIMARY:
            v = self._device_current_temp(self._conf(CONF_PRIMARY_DEVICE, None))
            if v is not None:
                return v
        # mean (default), or fallthrough when the selected source has no value
        temps = [self._device_current_temp(d["entity_id"]) for d in self._devices]
        temps = [t for t in temps if t is not None]
        if temps:
            return sum(temps) / len(temps)
        return self._numeric_state(sensor)

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
        """Return per-device dicts for routing (role, tier, park, capabilities)."""
        caps = []
        for dev in self._devices:
            state = self.hass.states.get(dev["entity_id"])
            available = state is not None and state.state not in ("unavailable", "unknown")
            attrs = state.attributes if state else {}
            modes = attrs.get("hvac_modes")
            step = attrs.get("target_temp_step")
            caps.append({
                "entity_id": dev["entity_id"],
                "role": dev.get("role", ROLE_BOTH),
                "tier": dev.get("tier", TIER_PRIMARY),
                "park": dev.get("park", PARK_FAN_ONLY),
                "available": available,
                "supports_fan_only": HVACMode.FAN_ONLY in (modes or []),
                # Unknown capabilities (no hvac_modes list) are assumed capable.
                "can_heat": modes is None or HVACMode.HEAT in modes,
                "can_cool": modes is None or HVACMode.COOL in modes,
                "step": step if isinstance(step, (int, float)) else None,
            })
        return caps

    # ---- Outdoor context (cooling policy) ---------------------------------

    def _outdoor_temperature(self):
        """Current outdoor temperature: the dedicated sensor, else the weather entity."""
        v = self._numeric_state(self._conf(CONF_OUTDOOR_SENSOR, None))
        if v is not None:
            return v
        weather = self.hass.states.get(self._conf(CONF_WEATHER_ENTITY, None) or "")
        if weather:
            val = weather.attributes.get("temperature")
            if isinstance(val, (int, float)):
                return val
        return None

    async def _refresh_outdoor(self, now):
        """Sample the outdoor temperature and refresh the forecast (every 30 min)."""
        self._outdoor_tracker.record(now, self._outdoor_temperature())

        weather_id = self._conf(CONF_WEATHER_ENTITY, None)
        if not weather_id:
            return
        if self._forecast_fetched and now - self._forecast_fetched < timedelta(minutes=30):
            return
        self._forecast_fetched = now  # also throttles retries after a failure
        try:
            response = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": weather_id, "type": "daily"},
                blocking=True, return_response=True,
            )
        except Exception as err:  # noqa: BLE001 - a flaky weather source must never break control
            _LOGGER.warning(
                "%s: could not fetch forecast from %s: %s", self._attr_name, weather_id, err
            )
            return
        forecast = ((response or {}).get(weather_id) or {}).get("forecast")
        self._forecast_highs = cooling.parse_daily_highs(forecast, now.date())

    def _cooling_highs(self, now):
        """Known highs for the warm-period test: forecast today/tomorrow + observed 24 h."""
        today, tomorrow = self._forecast_highs
        highs = [today, tomorrow, self._outdoor_tracker.max_24h(now)]
        if all(h is None for h in highs):
            highs.append(self._outdoor_temperature())
        return highs

    async def _apply_control(self):
        """Resolve the control decision and drive the actuator devices."""
        if not self._devices:
            return

        heat_target, cool_target, override_target = self._resolve_band()
        self._heat_target = heat_target
        self._cool_target = cool_target
        room_temp = self._room_temperature()

        self._cooling_allowed = cooling.cooling_permitted(
            self._cooling_mode,
            room_temp,
            highs=self._cooling_highs(dt_util.now()),
            warm_threshold=self._conf(CONF_WARM_THRESHOLD, DEFAULT_WARM_THRESHOLD),
            hard_ceiling=self._conf(CONF_HARD_CEILING, DEFAULT_HARD_CEILING),
        )

        decision = control.decide(
            mode=self._hvac_mode,
            room_temp=room_temp,
            heat_target=heat_target,
            cool_target=cool_target,
            override_target=override_target,
            prev_intent=self._intent,
            hysteresis=self._conf(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
            cooling_allowed=self._cooling_allowed,
        )
        now = dt_util.now()
        if decision.intent == control.HEAT:
            if self._intent != control.HEAT or self._heat_since is None:
                self._heat_since = now
        else:
            self._heat_since = None
        self._room_trend.record(now, room_temp)
        self._intent = decision.intent
        self._active_target = decision.target

        # The support heater only ever joins while we are heating, and only
        # when the user has not switched it off.
        if self._support_enabled and decision.intent == control.HEAT:
            self._support_active = control.support_needed(
                room_temp,
                decision.target if decision.target is not None else heat_target,
                self._conf(CONF_SUPPORT_DELTA, DEFAULT_SUPPORT_DELTA),
                self._support_active,
                heating_minutes=(
                    (now - self._heat_since).total_seconds() / 60
                    if self._heat_since else None
                ),
                rise_per_hour=self._room_trend.rise_per_hour(),
                grace_minutes=self._conf(CONF_SUPPORT_GRACE, DEFAULT_SUPPORT_GRACE_MIN),
                min_rise=self._conf(CONF_SUPPORT_MIN_RISE, DEFAULT_SUPPORT_MIN_RISE),
            )
        else:
            self._support_active = False

        commands = control.plan_routes(
            decision, self._device_caps(), support_active=self._support_active
        )
        for cmd in commands:
            await self._execute(cmd)

    async def _execute(self, cmd):
        """Apply one DeviceCommand, only calling services when state differs.

        A device that is missing/unavailable is skipped, and a failing service
        call is logged instead of raised — one misbehaving device must never
        abort the control loop (and with it the other devices and the state
        write).
        """
        state = self.hass.states.get(cmd.entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        try:
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
        except Exception as err:  # noqa: BLE001 - see docstring
            _LOGGER.warning(
                "%s: could not drive %s (%s): %s",
                self._attr_name, cmd.entity_id, cmd.hvac_mode, err,
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

    async def async_set_cooling_mode(self, mode: str):
        """Set the auto-cooling policy: off / auto / on."""
        if mode not in COOLING_MODES:
            return
        self._cooling_mode = mode
        self._persist(**{CONF_COOLING_MODE: mode})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_heat_support(self, enabled: bool):
        """Enable or disable the support heater (e.g. the CV next to an airco)."""
        self._support_enabled = bool(enabled)
        self._persist(**{CONF_SUPPORT_ENABLED: self._support_enabled})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the coordinator off (powers all actuators down)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the coordinator on in auto — it owns the heat/cool decision.

        Not ``heat``: pinning a mode here would hand the heat-versus-cool call
        back to whatever set it, while the whole point of the coordinator is
        that ``control.decide`` picks the intent from the room temperature and
        the band, and ``plan_routes`` drives the devices accordingly.
        """
        await self.async_set_hvac_mode(HVACMode.AUTO)

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

    def _rounded_trend(self):
        """Warming rate (°C/h) over the last 30 minutes, or None."""
        rate = self._room_trend.rise_per_hour()
        return None if rate is None else round(rate, 2)

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
            ATTR_SCHEDULE: self._schedule,
            ATTR_COOLING_MODE: self._cooling_mode,
            ATTR_COOLING_ALLOWED: self._cooling_allowed,
            ATTR_SUPPORT_ENABLED: self._support_enabled,
            ATTR_SUPPORT_ACTIVE: self._support_active,
            ATTR_ROOM_TREND: self._rounded_trend(),
            ATTR_SUPPORT_DELTA: self._conf(CONF_SUPPORT_DELTA, DEFAULT_SUPPORT_DELTA),
            ATTR_WARM_THRESHOLD: self._conf(CONF_WARM_THRESHOLD, DEFAULT_WARM_THRESHOLD),
            ATTR_HARD_CEILING: self._conf(CONF_HARD_CEILING, DEFAULT_HARD_CEILING),
            ATTR_FORECAST_HIGH_TODAY: self._forecast_highs[0],
            ATTR_FORECAST_HIGH_TOMORROW: self._forecast_highs[1],
            ATTR_OUTDOOR_MAX_24H: self._outdoor_tracker.max_24h(dt_util.now()),
            ATTR_WEATHER_ENTITY: self._conf(CONF_WEATHER_ENTITY, None),
            ATTR_OUTDOOR_SENSOR: self._conf(CONF_OUTDOOR_SENSOR, None),
        }