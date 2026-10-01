DOMAIN = "smart_climate"
PLATFORMS = ["climate", "sensor", "number", "switch", "select"]

# Modes
MODE_AUTO = "auto"
MODE_OVERRIDE_TIMER = "override_timer"
MODE_OVERRIDE_INFINITY = "override_infinity"
MODE_OVERRIDE_NEXT_NODE = "override_next_node"

# Config keys
CONF_WRAPPED_CLIMATE = "wrapped_climate"
CONF_ZONE_HOME = "zone_home"
CONF_AWAY_TEMPERATURE = "away_temperature"
CONF_AWAY_DELAY_MINUTES = "away_delay_minutes"
CONF_INTERRUPTIBLE = "interruptible"
CONF_DEFAULT_OVERRIDE_MODE = "default_override_mode"
CONF_DEFAULT_OVERRIDE_DURATION = "default_override_duration"
CONF_AUTO_TEMPERATURE = "auto_temperature"
CONF_SCHEDULE = "schedule"
CONF_COOL_AUTO_TEMPERATURE = "cool_auto_temperature"
CONF_COOL_AWAY_TEMPERATURE = "cool_away_temperature"
# Multi-device coordinator (Phase 1)
CONF_DEVICES = "devices"
CONF_HVAC_MODE = "hvac_mode"
CONF_TEMPERATURE_SOURCE = "temperature_source"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_PRIMARY_DEVICE = "primary_device"
CONF_HYSTERESIS = "hysteresis"
CONF_INTEGRATION_DRIVEN_AUTO = "integration_driven_auto"
# Cooling policy + heat support
CONF_COOLING_MODE = "cooling_mode"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_OUTDOOR_SENSOR = "outdoor_sensor"
CONF_WARM_THRESHOLD = "warm_threshold"
CONF_HARD_CEILING = "hard_ceiling"
CONF_SUPPORT_ENABLED = "support_enabled"
CONF_SUPPORT_DELTA = "support_delta"
CONF_SUPPORT_GRACE = "support_grace"
CONF_SUPPORT_MIN_RISE = "support_min_rise"
CONF_TIER = "tier"
CONF_DEVICE_MODES = "device_modes"
CONF_DEVICE_SEEDED = "device_modes_seeded"
CONF_CONTROL = "control"
CONF_SKIP_UNTIL = "skip_until"
CONF_PARK = "park"

# Device roles
ROLE_HEAT = "heat"
ROLE_COOL = "cool"
ROLE_BOTH = "both"
CONF_ROLE = "role"
CONF_ENTITY_ID = "entity_id"

# Config subentry type for an actuator device
SUBENTRY_TYPE_DEVICE = "device"

# Per-device control: auto = the coordinator drives it, off = kept off and never
# used, manual = hands off (the user operates it; the coordinator ignores it).
DEVICE_MODE_AUTO = "auto"
DEVICE_MODE_OFF = "off"
DEVICE_MODE_MANUAL = "manual"
DEVICE_MODES = [DEVICE_MODE_AUTO, DEVICE_MODE_OFF, DEVICE_MODE_MANUAL]
DEFAULT_SKIP_UNTIL = "10:00"

# Heating tiers: the primary device heats alone; a support device joins only
# when the room is far enough below the heat target.
TIER_PRIMARY = "primary"
TIER_SUPPORT = "support"

# What a device does when it is not the one serving the current intent.
PARK_OFF = "off"
PARK_FAN_ONLY = "fan_only"

# Cooling policy (the coordinator-level "Cooling" select)
COOLING_OFF = "off"
COOLING_AUTO = "auto"
COOLING_ON = "on"
COOLING_MODES = [COOLING_OFF, COOLING_AUTO, COOLING_ON]

# Room-temperature sources
TEMP_SOURCE_SENSOR = "sensor"
TEMP_SOURCE_PRIMARY = "primary"
TEMP_SOURCE_MEAN = "mean"

# Defaults
# Deliberately loose: the airco/CV should not chase the setpoint tightly.
DEFAULT_HYSTERESIS = 0.5
# Cool limit must sit at least this far above the heat target, so a mis-set
# schedule can never cool right after the room overshoots a heat target.
MIN_BAND_GAP = 3.0
# Auto cooling: allowed on a warm day/period (forecast or observed high at or
# above the threshold), or whenever the room passes the hard ceiling.
DEFAULT_WARM_THRESHOLD = 22.0
DEFAULT_HARD_CEILING = 26.0
# Support (CV) joins when the room is this far below the heat target and
# leaves again once the deficit is under half of it.
DEFAULT_SUPPORT_DELTA = 1.5
# ... but only after the primary heater has had this long (minutes) to close the
# gap, and only if the room is warming slower than this (°C per hour). Warming
# up after arriving home is slow but steady — the primary heater is doing its
# job and the support heater is not needed; a flat/falling room means it cannot
# keep up.
DEFAULT_SUPPORT_GRACE_MIN = 15
DEFAULT_SUPPORT_MIN_RISE = 0.3

# Attributes
ATTR_MODE = "mode"
ATTR_PRESENCE = "presence"
ATTR_REMAINING_MINUTES = "remaining_minutes"
ATTR_INTERRUPTIBLE = "interruptible"
ATTR_ZONE_HOME_COUNT = "zone_home_count"
ATTR_AWAY_DELAY_SECONDS_REMAINING = "away_delay_seconds_remaining"
ATTR_OVERRIDE_TEMPERATURE = "override_temperature"
ATTR_WRAPPED_CLIMATE = "wrapped_climate"
ATTR_COOL_AUTO_TEMPERATURE = "cool_auto_temperature"
ATTR_COOL_AWAY_TEMPERATURE = "cool_away_temperature"
ATTR_AUTO_TEMPERATURE = "auto_temperature"
ATTR_AWAY_TEMPERATURE = "away_temperature"
ATTR_AWAY_DELAY_MINUTES = "away_delay_minutes"
ATTR_DEFAULT_OVERRIDE_MODE = "default_override_mode"
ATTR_DEFAULT_OVERRIDE_DURATION = "default_override_duration"
ATTR_HEAT_TARGET = "heat_target"
ATTR_COOL_LIMIT = "cool_limit"
ATTR_INTENT = "intent"
ATTR_DEVICES = "devices"
ATTR_SCHEDULE = "schedule"
ATTR_COOLING_MODE = "cooling_mode"
ATTR_COOLING_ALLOWED = "cooling_allowed"
ATTR_SUPPORT_ENABLED = "support_enabled"
ATTR_SUPPORT_ACTIVE = "support_active"
ATTR_SUPPORT_DELTA = "support_delta"
ATTR_ROOM_TREND = "room_trend"
ATTR_DEVICE_MODES = "device_modes"
ATTR_SUPPORT_PAUSED_UNTIL = "support_paused_until"
ATTR_WARM_THRESHOLD = "warm_threshold"
ATTR_HARD_CEILING = "hard_ceiling"
ATTR_FORECAST_HIGH_TODAY = "forecast_high_today"
ATTR_FORECAST_HIGH_TOMORROW = "forecast_high_tomorrow"
ATTR_OUTDOOR_MAX_24H = "outdoor_max_24h"
ATTR_WEATHER_ENTITY = "weather_entity"
ATTR_OUTDOOR_SENSOR = "outdoor_sensor"

# Services
SERVICE_SET_OVERRIDE_TIMER = "set_override_timer"
SERVICE_SET_OVERRIDE_INFINITY = "set_override_infinity"
SERVICE_SET_OVERRIDE_NEXT_NODE = "set_override_next_node"
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SET_INTERRUPTIBLE = "set_interruptible"
SERVICE_SET_AUTO_TEMPERATURE = "set_auto_temperature"
SERVICE_SET_AWAY_TEMPERATURE = "set_away_temperature"
SERVICE_SET_COOL_AUTO_TEMPERATURE = "set_cool_auto_temperature"
SERVICE_SET_COOL_AWAY_TEMPERATURE = "set_cool_away_temperature"
SERVICE_SET_AWAY_DELAY = "set_away_delay"
SERVICE_SET_DEFAULT_OVERRIDE_MODE = "set_default_override_mode"
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_SET_COOLING_MODE = "set_cooling_mode"
SERVICE_SET_HEAT_SUPPORT = "set_heat_support"
SERVICE_SET_DEVICE_MODE = "set_device_mode"
SERVICE_SET_SUPPORT_PAUSE = "set_support_pause"

# Schedule modes
SCHEDULE_MODE_DAILY = "daily"
SCHEDULE_MODE_52 = "5/2"
SCHEDULE_MODE_INDIVIDUAL = "individual"