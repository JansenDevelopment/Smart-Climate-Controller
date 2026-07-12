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

# Device roles
ROLE_HEAT = "heat"
ROLE_COOL = "cool"
ROLE_BOTH = "both"
CONF_ROLE = "role"
CONF_ENTITY_ID = "entity_id"

# Config subentry type for an actuator device
SUBENTRY_TYPE_DEVICE = "device"

# Room-temperature sources
TEMP_SOURCE_SENSOR = "sensor"
TEMP_SOURCE_PRIMARY = "primary"
TEMP_SOURCE_MEAN = "mean"

# Defaults
DEFAULT_HYSTERESIS = 0.3
MIN_BAND_GAP = 1.0

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

# Schedule modes
SCHEDULE_MODE_DAILY = "daily"
SCHEDULE_MODE_52 = "5/2"
SCHEDULE_MODE_INDIVIDUAL = "individual"