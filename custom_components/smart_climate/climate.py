import logging
from collections import deque
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
from homeassistant.exceptions import ServiceValidationError
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
    ATTR_DEVICE_MODES,
    ATTR_DEVICES,
    ATTR_ETA_MINUTES,
    ATTR_EXTERNAL_TAKEOVER,
    ATTR_FAN_BOOST,
    ATTR_FORECAST_HIGH_TODAY,
    ATTR_FORECAST_HIGH_TOMORROW,
    ATTR_HARD_CEILING,
    ATTR_HEAT_TARGET,
    ATTR_HOLD_PRIMARY,
    ATTR_HOLD_TARGET,
    ATTR_INTENT,
    ATTR_INTERRUPTIBLE,
    ATTR_LOG,
    ATTR_MODE,
    ATTR_OBSERVE,
    ATTR_OUTDOOR_MAX_24H,
    ATTR_OUTDOOR_SENSOR,
    ATTR_OUTDOOR_TEMPERATURE,
    ATTR_OVERRIDE_TEMPERATURE,
    ATTR_PLAN,
    ATTR_PRESENCE,
    ATTR_REMAINING_MINUTES,
    ATTR_ROOM_TEMPERATURE_SOURCE,
    ATTR_ROOM_TREND,
    ATTR_SCHEDULE,
    ATTR_SUPPORT_ACTIVE,
    ATTR_SUPPORT_DELTA,
    ATTR_SUPPORT_ENABLED,
    ATTR_SUPPORT_PAUSE_KIND,
    ATTR_SUPPORT_PAUSED_UNTIL,
    ATTR_WARM_THRESHOLD,
    ATTR_WEATHER_ENTITY,
    ATTR_WRAPPED_CLIMATE,
    CONF_AUTO_TEMPERATURE,
    CONF_AWAY_DELAY_MINUTES,
    CONF_AWAY_TEMPERATURE,
    CONF_CONTROL,
    CONF_COOL_AUTO_TEMPERATURE,
    CONF_COOL_AWAY_TEMPERATURE,
    CONF_COOLING_MODE,
    CONF_DEFAULT_OVERRIDE_DURATION,
    CONF_DEFAULT_OVERRIDE_MODE,
    CONF_DEVICE_MODES,
    CONF_DEVICE_SEEDED,
    CONF_DEVICES,
    CONF_EXTERNAL_TAKEOVER,
    CONF_FAN_BOOST,
    CONF_HARD_CEILING,
    CONF_HOLD_PRIMARY,
    CONF_HVAC_MODE,
    CONF_HYSTERESIS,
    CONF_INTERRUPTIBLE,
    CONF_OBSERVE,
    CONF_OUTDOOR_CACHE,
    CONF_OUTDOOR_SENSOR,
    CONF_PARK,
    CONF_PRIMARY_DEVICE,
    CONF_SCHEDULE,
    CONF_SKIP_UNTIL,
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
    DEFAULT_SKIP_UNTIL,
    DEFAULT_SUPPORT_DELTA,
    DEFAULT_SUPPORT_GRACE_MIN,
    DEFAULT_SUPPORT_MIN_RISE,
    DEFAULT_WARM_THRESHOLD,
    DEVICE_MODE_AUTO,
    DEVICE_MODE_MANUAL,
    DEVICE_MODE_OFF,
    DEVICE_MODES,
    DOMAIN,
    EVENT_LOG,
    EXTERNAL_SETTLE_SECONDS,
    LOG_SIZE,
    MODE_AUTO,
    MODE_OVERRIDE_INFINITY,
    MODE_OVERRIDE_NEXT_NODE,
    MODE_OVERRIDE_TIMER,
    PARK_OFF,
    RESEND_SECONDS,
    ROLE_BOTH,
    SOURCE_EXTERNAL,
    SOURCE_PAUSE,
    SOURCE_USER,
    SUBENTRY_TYPE_DEVICE,
    TEMP_SOURCE_MEAN,
    TEMP_SOURCE_PRIMARY,
    TEMP_SOURCE_SENSOR,
    TIER_PRIMARY,
    TIER_SUPPORT,
    TOMORROW_FROM_HOUR,
    UNAVAILABLE_DEBOUNCE_SECONDS,
    WHO_CONTROL,
    WHO_HAND,
    WHO_OBSERVE,
    WHO_USER,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)


def _parse_dt(value):
    """Parse a stored/entered datetime into an aware local one (None if unusable).

    Strings without an offset are read as local time, so a naive value can never
    be compared against the aware ``now``.
    """
    try:
        when = dt_util.parse_datetime(str(value))
    except (TypeError, ValueError):
        return None
    return dt_util.as_local(when) if when is not None else None


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
        # Per-device control choice: {entity_id: {"mode": auto|off|manual, "until": iso|None}}
        self._device_modes = {
            k: dict(v) for k, v in (entry.data.get(CONF_DEVICE_MODES) or {}).items()
        }
        # A device added with a start mode (e.g. "manual") begins in that mode, once:
        # it is applied in memory now (so the very first evaluation already
        # respects it) and persisted when the entity is registered.
        already_seeded = set(entry.data.get(CONF_DEVICE_SEEDED) or [])
        self._seed_pending = [
            d["entity_id"] for d in self._devices if d["entity_id"] not in already_seeded
        ]
        self._already_seeded = already_seeded
        for dev in self._devices:
            if (
                dev["entity_id"] in self._seed_pending
                and dev.get("control", DEVICE_MODE_AUTO) != DEVICE_MODE_AUTO
                and dev["entity_id"] not in self._device_modes
            ):
                self._device_modes[dev["entity_id"]] = {"mode": dev["control"], "until": None}
        self._heat_since = None
        self._acting = False
        self._last_sent = {}
        self._unavailable_since = {}

        # Observe ("proefdraaien"), fan boost, hold trim and the action log.
        self._observe = bool(entry.data.get(CONF_OBSERVE, False))
        self._fan_state = {}       # entity_id -> (fan mode the boost chose, since)
        self._trim = 0.0
        self._above_since = None   # room more than TRIM_ABOVE over the hold target since
        self._hold_target = None
        self._eta = None
        self._plan = []
        self._plan_key = None
        self._log = deque(maxlen=LOG_SIZE)

        # Outdoor context for the auto-cooling policy.
        self._outdoor_tracker = cooling.OutdoorMaxTracker()
        cache = entry.data.get(CONF_OUTDOOR_CACHE) or {}
        at = _parse_dt(cache.get('at')) if cache.get('at') else None
        if at is not None and isinstance(cache.get('value'), (int, float)):
            self._outdoor_tracker.record(at, cache['value'])
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

        def _add(entity_id, role, tier=None, park=None, control=None):
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                devices.append({
                    "entity_id": entity_id,
                    "role": role or ROLE_BOTH,
                    "tier": tier or TIER_PRIMARY,
                    "park": park or PARK_OFF,
                    "control": control or DEVICE_MODE_AUTO,
                })

        subentries = getattr(entry, "subentries", None)
        if isinstance(subentries, Mapping):
            for sub in subentries.values():
                if getattr(sub, "subentry_type", None) == SUBENTRY_TYPE_DEVICE:
                    data = getattr(sub, "data", {}) or {}
                    _add(
                        data.get("entity_id"), data.get("role"),
                        data.get(CONF_TIER), data.get(CONF_PARK), data.get(CONF_CONTROL),
                    )

        for d in entry.data.get(CONF_DEVICES, []) or []:
            _add(
                d.get("entity_id"), d.get("role"), d.get(CONF_TIER), d.get(CONF_PARK),
                d.get(CONF_CONTROL),
            )

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

        self._persist_seeded_modes()

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

        self._expire_device_modes(current_time)

        # Outdoor context for the cooling policy, then evaluate + drive devices
        await self._refresh_outdoor(current_time)
        await self._apply_control()
        self.async_write_ha_state()

    async def _on_watched_change(self, event):
        """Re-evaluate control when a device or the temp sensor changes."""
        data = getattr(event, "data", None) or {}
        eid = data.get("entity_id")
        if eid in {d["entity_id"] for d in self._devices}:
            now = dt_util.now()
            old, new = data.get("old_state"), data.get("new_state")
            mark = self._last_sent.get(eid)
            ours = bool(mark) and (now - mark["t"]).total_seconds() < EXTERNAL_SETTLE_SECONDS
            change = self._describe_state(old, new) if old is not None else None
            if change and not ours:
                self._log_action(WHO_HAND, eid, change, self._room_temperature())
            self._detect_external_change(eid, new, now, old)
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

    def _room_temperature_source(self):
        """Where the room temperature comes from (for the cards)."""
        source = self._conf(CONF_TEMPERATURE_SOURCE, TEMP_SOURCE_MEAN)
        sensor = self._conf(CONF_TEMPERATURE_SENSOR, None)
        if source == TEMP_SOURCE_SENSOR and self._numeric_state(sensor) is not None:
            return {"kind": TEMP_SOURCE_SENSOR, "entity": sensor}
        primary = self._conf(CONF_PRIMARY_DEVICE, None)
        if source == TEMP_SOURCE_PRIMARY and self._device_current_temp(primary) is not None:
            return {"kind": TEMP_SOURCE_PRIMARY, "entity": primary}
        return {"kind": TEMP_SOURCE_MEAN, "entity": None}

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
        now = dt_util.now()
        caps = []
        for dev in self._devices:
            eid = dev["entity_id"]
            state = self.hass.states.get(eid)
            reachable = state is not None and state.state not in ("unavailable", "unknown")
            if reachable:
                self._unavailable_since.pop(eid, None)
                available = True
            else:
                since = self._unavailable_since.setdefault(eid, now)
                # A short dropout must not hand the whole job to the other heater.
                available = (now - since).total_seconds() < UNAVAILABLE_DEBOUNCE_SECONDS
            attrs = state.attributes if state else {}
            modes = attrs.get("hvac_modes")
            step = attrs.get("target_temp_step")
            control_mode = self._effective_device_mode(eid, now)
            entry = self._device_modes.get(eid) or {}
            if self._observe and control_mode != DEVICE_MODE_AUTO and entry.get("source") != SOURCE_EXTERNAL:
                # Observing: show what it would do if this device were on auto. A device
                # switched by hand (remote, app) keeps that, just like for real.
                control_mode = DEVICE_MODE_AUTO
            min_temp = attrs.get("min_temp")
            caps.append({
                "entity_id": eid,
                "role": dev.get("role", ROLE_BOTH),
                "tier": dev.get("tier", TIER_PRIMARY),
                "park": dev.get("park", PARK_OFF),
                "control": control_mode,
                "available": available,
                "heating": bool(state) and state.state == "heat",
                "supports_fan_only": HVACMode.FAN_ONLY in (modes or []),
                # Unknown capabilities (no hvac_modes list) are assumed capable.
                "can_heat": modes is None or HVACMode.HEAT in modes,
                "can_cool": modes is None or HVACMode.COOL in modes,
                "step": step if isinstance(step, (int, float)) else None,
                "min_temp": min_temp if isinstance(min_temp, (int, float)) else None,
                "fan_modes": attrs.get("fan_modes") or None,
                "hold": bool(self._conf(CONF_HOLD_PRIMARY, False)),
                "trim": self._trim,
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
        self._forecast_fetched = now
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
            # Right after a restart the weather service may not be ready yet:
            # try again in 2 minutes instead of waiting a full 30.
            self._forecast_fetched = now - timedelta(minutes=28)
            return
        forecast = ((response or {}).get(weather_id) or {}).get("forecast")
        local_now = dt_util.as_local(now)
        self._forecast_highs = cooling.parse_daily_highs(
            forecast, local_now.date(), to_local=dt_util.as_local
        )
        observed = self._outdoor_tracker.max_24h(now)
        if observed is not None:
            self._persist(**{CONF_OUTDOOR_CACHE: {"value": observed, "at": now.isoformat()}})

    def _cooling_highs(self, now):
        """Known highs for the warm-period test: forecast today/tomorrow + observed 24 h."""
        today, tomorrow = self._forecast_highs
        # Tomorrow's high only matters for the evening; a warm tomorrow must not
        # open cooling on a mild afternoon today.
        if dt_util.as_local(now).hour < TOMORROW_FROM_HOUR:
            tomorrow = None
        highs = [today, tomorrow, self._outdoor_tracker.max_24h(now)]
        if all(h is None for h in highs):
            highs.append(self._outdoor_temperature())
        return highs

    async def _apply_control(self, force: bool = False):
        """Resolve the control decision and drive the actuator devices.

        While the coordinator is off it still resolves its state, but drives
        nothing: off means hands off.  ``force`` sends the commands anyway —
        used once, when switching to off, to power the auto devices down.
        """
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
                rise_per_hour=self._room_trend.rise_per_hour(
                    since=self._heat_since, min_span_minutes=10
                ),
                grace_minutes=self._conf(CONF_SUPPORT_GRACE, DEFAULT_SUPPORT_GRACE_MIN),
                min_rise=self._conf(CONF_SUPPORT_MIN_RISE, DEFAULT_SUPPORT_MIN_RISE),
            )
        else:
            self._support_active = False

        # Hold target: what a holding primary heater runs at while the coordinator
        # idles (the override, else the band's heat target). Trimmed down when the
        # room stays clearly too warm, because the device regulates on its own sensor.
        hold_target = None
        if decision.intent in (control.HEAT, control.IDLE):
            hold_target = override_target if override_target is not None else heat_target
        if hold_target is not None and room_temp is not None and room_temp > hold_target + control.TRIM_ABOVE:
            self._above_since = self._above_since or now
        else:
            self._above_since = None
        self._trim = control.hold_trim(
            room_temp, hold_target, self._trim,
            (now - self._above_since).total_seconds() / 60 if self._above_since else None,
        )
        self._hold_target = hold_target
        fan_target = decision.target if decision.intent == control.HEAT else hold_target
        self._eta = control.eta_minutes(
            room_temp, fan_target,
            self._room_trend.rise_per_hour(since=self._heat_since, min_span_minutes=10),
        )

        if self._hvac_mode == HVACMode.OFF and not force:
            # Off = hands off: the coordinator drives nothing until switched back on.
            self._acting = False
            self._plan = []
            return

        caps = self._device_caps()
        boost = bool(self._conf(CONF_FAN_BOOST, False))
        for cap in caps:
            cap["fan"] = None
            if boost and cap["fan_modes"] and cap.get("tier") == TIER_PRIMARY:
                prev, since = self._fan_state.get(cap["entity_id"], (None, None))
                cap["fan"] = control.fan_for(
                    room_temp, fan_target, prev,
                    (now - since).total_seconds() / 60 if since else None,
                    cap["fan_modes"],
                )
        commands = control.plan_routes(
            decision, caps, support_active=self._support_active,
            hold_target=hold_target if bool(self._conf(CONF_HOLD_PRIMARY, False)) else None,
        )
        for cmd in commands:
            if cmd.fan_mode and (self._fan_state.get(cmd.entity_id) or (None,))[0] != cmd.fan_mode:
                self._fan_state[cmd.entity_id] = (cmd.fan_mode, now)
        self._plan = [
            {"entity_id": c.entity_id, "hvac_mode": c.hvac_mode, "temperature": c.temperature, "fan_mode": c.fan_mode}
            for c in commands
        ]
        self._acting = any(c.hvac_mode in ("heat", "cool") for c in commands)
        if self._observe and not force:
            # Proefdraaien: log what it would send (only when that changes), send nothing.
            last = self._plan_key or {}
            for cmd in commands:
                key = (cmd.hvac_mode, cmd.temperature, cmd.fan_mode)
                if last.get(cmd.entity_id) != key:
                    self._log_action(WHO_OBSERVE, cmd.entity_id, self._describe(cmd), room_temp)
            self._plan_key = {c.entity_id: (c.hvac_mode, c.temperature, c.fan_mode) for c in commands}
            return
        for cmd in commands:
            await self._execute(cmd)

    async def _execute(self, cmd):
        """Apply one DeviceCommand, only calling services when state differs.

        A device that is missing/unavailable is skipped, the same command is
        repeated at most every ``RESEND_SECONDS`` (a device that ignores it must
        not be spammed every tick), and a failing service call is logged
        instead of raised — one misbehaving device must never
        abort the control loop (and with it the other devices and the state
        write).
        """
        state = self.hass.states.get(cmd.entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        last = self._last_sent.get(cmd.entity_id)
        if (
            last
            and last.get("mode") == cmd.hvac_mode
            and last.get("temp") == cmd.temperature
            and last.get("fan") == cmd.fan_mode
            and (dt_util.now() - last["t"]).total_seconds() < RESEND_SECONDS
        ):
            return
        sent = False
        what = []
        # Mark before calling: the device reports its new state while we are still
        # awaiting, and that change must be recognised as ours, not as hand operation.
        mark = self._last_sent.setdefault(
            cmd.entity_id, {"t": dt_util.now() - timedelta(hours=1)}
        )
        prev_mark = dict(mark)
        mark["mode"], mark["temp"], mark["fan"] = cmd.hvac_mode, cmd.temperature, cmd.fan_mode
        mark["t"] = dt_util.now()
        try:
            if state.state != cmd.hvac_mode:
                sent = True
                what.append("mode")
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": cmd.entity_id, "hvac_mode": cmd.hvac_mode},
                )
            if cmd.temperature is not None and state.attributes.get("temperature") != cmd.temperature:
                sent = True
                what.append("temp")
                await self.hass.services.async_call(
                    "climate", "set_temperature",
                    {"entity_id": cmd.entity_id, "temperature": cmd.temperature},
                )
            if (
                cmd.fan_mode
                and cmd.hvac_mode != "off"
                and cmd.fan_mode in (state.attributes.get("fan_modes") or [])
                and state.attributes.get("fan_mode") != cmd.fan_mode
            ):
                sent = True
                what.append("fan")
                await self.hass.services.async_call(
                    "climate", "set_fan_mode",
                    {"entity_id": cmd.entity_id, "fan_mode": cmd.fan_mode},
                )
        except Exception as err:  # noqa: BLE001 - see docstring
            _LOGGER.warning(
                "%s: could not drive %s (%s): %s",
                self._attr_name, cmd.entity_id, cmd.hvac_mode, err,
            )
        # Remember what we asked for, to tell our own changes from outside ones.
        # The timestamp only moves when we actually sent something.
        if sent:
            mark["t"] = dt_util.now()
            self._log_action(WHO_CONTROL, cmd.entity_id, self._describe(cmd, what), self._room_temperature())
        else:
            mark["t"] = prev_mark["t"]

    def _detect_external_change(self, entity_id, new_state, now, old_state=None):
        """A device changed without us asking: take it as hand operation.

        If, a while after our last command, an auto device reports a different
        HVAC mode, a clearly different target or another fan mode than we set,
        somebody used the remote, the device's own app or a dashboard.  The
        device then goes to ``manual`` for the default override duration so the
        coordinator does not undo it.

        Switched **off** by hand is stronger: it stays off (manual, no end) until
        somebody switches it on again by hand, which hands it back to the
        coordinator.  That also works while observing, when we send nothing.
        """
        if not self._conf(CONF_EXTERNAL_TAKEOVER, True):
            return
        if self._hvac_mode == HVACMode.OFF:
            return  # nothing to take over while we drive nothing
        if new_state is None or new_state.state in ("unavailable", "unknown"):
            return
        mark = self._last_sent.get(entity_id)
        ours = bool(mark) and (now - mark["t"]).total_seconds() < EXTERNAL_SETTLE_SECONDS
        entry = self._device_modes.get(entity_id) or {}
        was_on = old_state is not None and old_state.state not in ("off", "unavailable", "unknown")

        if entry.get("off_by_hand"):
            if new_state.state != "off" and not ours:
                self._device_modes.pop(entity_id, None)
                self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})
                self._log_action(
                    WHO_HAND, entity_id, "weer aan met de hand: de regeling neemt het weer over",
                    self._room_temperature(),
                )
            return
        if self._effective_device_mode(entity_id, now) != DEVICE_MODE_AUTO:
            return
        if new_state.state == "off" and was_on and not (ours and mark.get("mode") == "off"):
            self._device_modes[entity_id] = {
                "mode": DEVICE_MODE_MANUAL, "until": None, "source": SOURCE_EXTERNAL, "off_by_hand": True,
            }
            self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})
            self._log_action(
                WHO_HAND, entity_id, "met de hand uit: blijft uit tot hij weer met de hand aan gaat",
                self._room_temperature(),
            )
            return
        if not mark or ours:
            return
        changed = new_state.state != mark.get("mode")
        target = new_state.attributes.get("temperature")
        if (
            not changed
            and new_state.state in ("heat", "cool")
            and isinstance(target, (int, float))
            and isinstance(mark.get("temp"), (int, float))
            and abs(target - mark["temp"]) >= 0.5
        ):
            changed = True
        fan = new_state.attributes.get("fan_mode")
        if not changed and mark.get("fan") and fan and fan != mark["fan"]:
            changed = True
        if not changed:
            return
        if self._default_override_mode == "infinity":
            end = None
        elif self._default_override_mode == "next_node":
            end = schedule_helper.compute_next_node_datetime(self._schedule, dt_util.as_local(now))
        else:
            end = now + timedelta(minutes=float(self._default_override_duration))
        _LOGGER.info(
            "%s: %s was changed outside the coordinator (now %s); leaving it alone%s",
            self._attr_name, entity_id, new_state.state,
            f" until {end:%H:%M}" if end else "",
        )
        self._device_modes[entity_id] = {
            "mode": DEVICE_MODE_MANUAL, "until": end.isoformat() if end else None,
            "source": SOURCE_EXTERNAL,
        }
        self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})
        until = f" tot {dt_util.as_local(end):%H:%M}" if end else ""
        self._log_action(
            WHO_HAND, entity_id, "met de hand bediend: regeling blijft eraf" + until,
            self._room_temperature(),
        )

    # ---- Action log -------------------------------------------------------

    _MODE_NL: ClassVar[dict] = {
        "off": "uit", "heat": "warm", "cool": "koel", "auto": "auto", "fan_only": "ventilator", "dry": "droog",
    }
    _FAN_NL: ClassVar[dict] = {"auto": "auto", "low": "laag", "medium": "midden", "high": "hoog"}

    def _describe(self, cmd, what=None):
        """Short Dutch text for a command (what = the parts that were actually sent)."""
        parts = [self._MODE_NL.get(cmd.hvac_mode, cmd.hvac_mode)]
        if cmd.hvac_mode != "off":
            if cmd.temperature is not None and (what is None or "temp" in what or "mode" in what):
                parts.append(f"{cmd.temperature:g}°")
            if cmd.fan_mode and (what is None or "fan" in what or "mode" in what):
                parts.append(f"ventilator {self._FAN_NL.get(cmd.fan_mode, cmd.fan_mode)}")
        return " · ".join(parts)

    @classmethod
    def _describe_state(cls, old, new):
        """What changed on a device (mode, setpoint, fan), or None if nothing of that."""
        if new is None or new.state in ("unavailable", "unknown"):
            return None
        o = old.attributes if old is not None else {}
        n = new.attributes
        parts = []
        if old is None or old.state != new.state:
            parts.append(cls._MODE_NL.get(new.state, new.state))
        if new.state != "off":
            t = n.get("temperature")
            if o.get("temperature") != t and isinstance(t, (int, float)):
                parts.append(f"{t:g}°")
            if o.get("fan_mode") != n.get("fan_mode") and n.get("fan_mode"):
                parts.append(f"ventilator {cls._FAN_NL.get(n.get('fan_mode'), n.get('fan_mode'))}")
        return " · ".join(parts) or None

    def _log_action(self, who, entity_id, text, room_temp=None):
        """Add one entry to the action log and fire it as an event (kept by the recorder)."""
        now = dt_util.now()
        coordinator = getattr(self, "entity_id", None)
        entry = {
            "t": now.isoformat(timespec="seconds"),
            "who": who,
            "entity_id": entity_id or coordinator,
            "text": text,
            "room": room_temp,
            "outdoor": self._outdoor_temperature(),
            "target": self._active_target if self._active_target is not None else self._heat_target,
            "presence": self._presence,
            "mode": self._mode,
            "hvac_mode": self._hvac_mode,
            "observe": self._observe,
        }
        self._log.append(entry)
        try:
            self.hass.bus.async_fire(EVENT_LOG, {**entry, "coordinator": coordinator})
        except Exception as err:  # noqa: BLE001 - logging must never break control
            _LOGGER.debug("%s: could not fire %s: %s", self._attr_name, EVENT_LOG, err)

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
        self._log_action(WHO_USER, None, f"tijdelijk {temperature:g}° voor {minutes:g} min", self._room_temperature())
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_override_infinity(self, temperature: float):
        """Set override infinity mode."""
        self._mode = MODE_OVERRIDE_INFINITY
        self._override_temperature = temperature
        self._override_start_time = None
        self._log_action(WHO_USER, None, f"tijdelijk {temperature:g}° zonder einde", self._room_temperature())
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
        self._log_action(WHO_USER, None, f"tijdelijk {temperature:g}° tot het volgende blok", self._room_temperature())
        await self._apply_control()
        self.async_write_ha_state()

    async def async_clear_override(self):
        """Clear override and return to AUTO."""
        self._mode = MODE_AUTO
        self._override_start_time = None
        self._next_node_datetime = None
        self._log_action(WHO_USER, None, "terug naar het schema", self._room_temperature())
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
        """Set the coordinator's own HVAC mode and re-drive the devices.

        Switching to off powers the auto devices down once; after that the
        coordinator leaves every device alone until it is switched back on.
        """
        turning_off = hvac_mode == HVACMode.OFF and self._hvac_mode != HVACMode.OFF
        if hvac_mode != self._hvac_mode:
            self._log_action(
                WHO_USER, None, f"regeling {self._MODE_NL.get(hvac_mode, hvac_mode)}", self._room_temperature()
            )
        self._hvac_mode = hvac_mode
        self._persist(**{CONF_HVAC_MODE: hvac_mode})
        await self._apply_control(force=turning_off)
        self.async_write_ha_state()

    async def async_set_observe(self, enabled: bool) -> None:
        """Proefdraaien: decide and log what it would do, but drive nothing."""
        enabled = bool(enabled)
        if enabled != self._observe:
            self._log_action(
                WHO_USER, None, "proefdraaien aan" if enabled else "proefdraaien uit: de regeling stuurt",
                self._room_temperature(),
            )
        self._observe = enabled
        self._plan_key = None
        self._persist(**{CONF_OBSERVE: enabled})
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_behaviour(self, fan_boost=None, hold_primary=None) -> None:
        """Switch the fan boost and/or holding the primary heater at the target."""
        changes = {}
        if fan_boost is not None:
            changes[CONF_FAN_BOOST] = bool(fan_boost)
        if hold_primary is not None:
            changes[CONF_HOLD_PRIMARY] = bool(hold_primary)
        if not changes:
            return
        self._persist(**changes)
        self._plan_key = None
        text = ", ".join(
            f"{'ventilator-boost' if k == CONF_FAN_BOOST else 'aanhouden'} {'aan' if v else 'uit'}"
            for k, v in changes.items()
        )
        self._log_action(WHO_USER, None, text, self._room_temperature())
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

    # ---- Per-device control ----------------------------------------------

    def _persist_seeded_modes(self):
        """Persist the start modes of newly added devices (once)."""
        if not self._seed_pending:
            return
        self._persist(**{
            CONF_DEVICE_MODES: dict(self._device_modes),
            CONF_DEVICE_SEEDED: sorted(self._already_seeded | set(self._seed_pending)),
        })
        self._already_seeded |= set(self._seed_pending)
        self._seed_pending = []

    def _effective_device_mode(self, entity_id, now):
        """The device's control mode right now; an expired temporary mode is auto."""
        entry = self._device_modes.get(entity_id)
        if not entry:
            return DEVICE_MODE_AUTO
        until = entry.get("until")
        if until:
            when = _parse_dt(until)
            # An unreadable end time counts as expired rather than crashing.
            if when is None or now >= when:
                return DEVICE_MODE_AUTO
        return entry.get("mode", DEVICE_MODE_AUTO)

    def _expire_device_modes(self, now):
        """Drop temporary device modes whose end time has passed (and persist)."""
        expired = [
            eid for eid, entry in self._device_modes.items()
            if entry.get("until")
            and ((_parse_dt(entry["until"]) or now) <= now)
        ]
        if expired:
            for eid in expired:
                self._device_modes.pop(eid, None)
            self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})

    def _next_skip_end(self, now):
        """The next occurrence of the configured 'skip until' time (default 10:00)."""
        raw = str(self._conf(CONF_SKIP_UNTIL, DEFAULT_SKIP_UNTIL))
        try:
            hh, mm = (int(x) for x in raw.split(":")[:2])
        except ValueError:
            hh, mm = 10, 0
        end = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if end <= now:
            end += timedelta(days=1)
        return end

    async def async_set_device_mode(self, device, mode, minutes=None, until=None):
        """Set a device to auto / off / manual, optionally only for a while."""
        if mode not in DEVICE_MODES:
            raise ServiceValidationError(f"Unknown device mode: {mode}")
        if device not in {d["entity_id"] for d in self._devices}:
            raise ServiceValidationError(f"{device} is not a device of this coordinator")
        now = dt_util.now()
        end = None
        if mode != DEVICE_MODE_AUTO:
            if minutes:
                end = now + timedelta(minutes=float(minutes))
            elif until:
                end = _parse_dt(until)
                if end is None:
                    raise ServiceValidationError(f"Cannot read the end time: {until}")
        if mode == DEVICE_MODE_AUTO:
            self._device_modes.pop(device, None)
        else:
            self._device_modes[device] = {
                "mode": mode, "until": end.isoformat() if end else None,
                "source": SOURCE_USER,
            }
        self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})
        label = {DEVICE_MODE_AUTO: "auto", DEVICE_MODE_OFF: "niet gebruiken", DEVICE_MODE_MANUAL: "handmatig"}[mode]
        until_txt = f" tot {dt_util.as_local(end):%H:%M}" if end else ""
        self._log_action(WHO_USER, device, f"stand {label}{until_txt}", self._room_temperature())
        await self._apply_control()
        self.async_write_ha_state()

    async def async_set_support_pause(self, enabled=True, minutes=None, until_morning=False):
        """Pause (or resume) every support device — e.g. 'no CV tomorrow morning'.

        ``until_morning`` pauses until the next 'skip until' time (default
        10:00); ``minutes`` pauses for a fixed time ("I'm leaving soon");
        without either the pause has no end until it is switched off.
        """
        now = dt_util.now()
        end = None
        kind = "open"
        if enabled:
            if minutes:
                end, kind = now + timedelta(minutes=float(minutes)), "minutes"
            elif until_morning:
                end, kind = self._next_skip_end(now), "until_morning"
        for dev in self._devices:
            if dev.get("tier") != TIER_SUPPORT:
                continue
            eid = dev["entity_id"]
            entry = self._device_modes.get(eid)
            if enabled:
                # A device the user set by hand (off/manual) keeps that choice.
                if entry and entry.get("source") != SOURCE_PAUSE and self._effective_device_mode(eid, now) != DEVICE_MODE_AUTO:
                    continue
                self._device_modes[eid] = {
                    "mode": DEVICE_MODE_OFF, "until": end.isoformat() if end else None,
                    "source": SOURCE_PAUSE, "kind": kind,
                }
            elif entry and entry.get("source") == SOURCE_PAUSE:
                self._device_modes.pop(eid, None)
        self._persist(**{CONF_DEVICE_MODES: dict(self._device_modes)})
        await self._apply_control()
        self.async_write_ha_state()

    def _pause_entries(self):
        """Active pause entries of the support devices."""
        out = []
        for dev in self._devices:
            if dev.get("tier") != TIER_SUPPORT:
                continue
            entry = self._device_modes.get(dev["entity_id"])
            if (
                entry
                and entry.get("source") == SOURCE_PAUSE
                and self._effective_device_mode(dev["entity_id"], dt_util.now()) == DEVICE_MODE_OFF
            ):
                out.append(entry)
        return out

    def _support_paused_until(self):
        """ISO end time of the active support pause ('' if open-ended, None if none)."""
        ends = [e.get("until") or "" for e in self._pause_entries()]
        if not ends:
            return None
        timed = [e for e in ends if e]
        return min(timed) if timed and len(timed) == len(ends) else ""

    def _support_pause_kind(self):
        """until_morning / minutes / open for the active pause, else None."""
        entries = self._pause_entries()
        return entries[0].get("kind", "open") if entries else None

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
        """Turn the coordinator off: auto devices go off once, then hands off."""
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
        if self._intent in (control.HEAT, control.COOL) and not self._acting:
            return "idle"  # the coordinator wants it, but no device is allowed to act
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
            ATTR_DEVICE_MODES: {
                d["entity_id"]: {
                    "mode": self._effective_device_mode(d["entity_id"], dt_util.now()),
                    "until": (self._device_modes.get(d["entity_id"]) or {}).get("until"),
                    "source": (self._device_modes.get(d["entity_id"]) or {}).get("source", SOURCE_USER),
                    "off_by_hand": bool((self._device_modes.get(d["entity_id"]) or {}).get("off_by_hand")),
                }
                for d in self._devices
            },
            ATTR_SUPPORT_PAUSED_UNTIL: self._support_paused_until(),
            ATTR_SUPPORT_PAUSE_KIND: self._support_pause_kind(),
            ATTR_ROOM_TEMPERATURE_SOURCE: self._room_temperature_source(),
            ATTR_EXTERNAL_TAKEOVER: bool(self._conf(CONF_EXTERNAL_TAKEOVER, True)),
            ATTR_SUPPORT_DELTA: self._conf(CONF_SUPPORT_DELTA, DEFAULT_SUPPORT_DELTA),
            ATTR_WARM_THRESHOLD: self._conf(CONF_WARM_THRESHOLD, DEFAULT_WARM_THRESHOLD),
            ATTR_HARD_CEILING: self._conf(CONF_HARD_CEILING, DEFAULT_HARD_CEILING),
            ATTR_FORECAST_HIGH_TODAY: self._forecast_highs[0],
            ATTR_FORECAST_HIGH_TOMORROW: self._forecast_highs[1],
            ATTR_OUTDOOR_MAX_24H: self._outdoor_tracker.max_24h(dt_util.now()),
            ATTR_WEATHER_ENTITY: self._conf(CONF_WEATHER_ENTITY, None),
            ATTR_OUTDOOR_SENSOR: self._conf(CONF_OUTDOOR_SENSOR, None),
            ATTR_OUTDOOR_TEMPERATURE: self._outdoor_temperature(),
            ATTR_OBSERVE: self._observe,
            ATTR_FAN_BOOST: bool(self._conf(CONF_FAN_BOOST, False)),
            ATTR_HOLD_PRIMARY: bool(self._conf(CONF_HOLD_PRIMARY, False)),
            ATTR_PLAN: self._plan,
            ATTR_HOLD_TARGET: self._hold_target,
            ATTR_ETA_MINUTES: None if self._eta is None else round(self._eta),
            ATTR_LOG: list(self._log),
        }