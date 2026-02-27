DOMAIN = "smart_climate"
PLATFORMS = ["climate"]

# Modes
MODE_AUTO = "auto"
MODE_OVERRIDE_TIMER = "override_timer"
MODE_OVERRIDE_INFINITY = "override_infinity"

# Schedule modes
SCHEDULE_MODE_DAILY = "daily"
SCHEDULE_MODE_52 = "5/2"
SCHEDULE_MODE_INDIVIDUAL = "individual"

# Config keys
CONF_WRAPPED_CLIMATE = "wrapped_climate"
CONF_ZONE_HOME = "zone_home"
CONF_AUTO_TEMPERATURE = "auto_temperature"
CONF_AWAY_TEMPERATURE = "away_temperature"
CONF_AWAY_DELAY_MINUTES = "away_delay_minutes"
CONF_INTERRUPTIBLE = "interruptible"
CONF_DEFAULT_OVERRIDE_MODE = "default_override_mode"
CONF_DEFAULT_OVERRIDE_DURATION = "default_override_duration"
CONF_SCHEDULE = "schedule"

# Attributes
ATTR_WRAPPED_CLIMATE = "wrapped_climate"
ATTR_ZONE_HOME = "zone_home"
ATTR_MODE = "mode"
ATTR_PRESENCE = "presence"
ATTR_REMAINING_MINUTES = "remaining_minutes"
ATTR_INTERRUPTIBLE = "interruptible"
ATTR_ZONE_HOME_COUNT = "zone_home_count"
ATTR_AWAY_DELAY_SECONDS_REMAINING = "away_delay_seconds_remaining"
ATTR_OVERRIDE_TEMPERATURE = "override_temperature"
ATTR_AUTO_TEMPERATURE = "auto_temperature"
ATTR_AWAY_TEMPERATURE = "away_temperature"
ATTR_AWAY_DELAY_MINUTES = "away_delay_minutes"
ATTR_DEFAULT_OVERRIDE_MODE = "default_override_mode"
ATTR_DEFAULT_OVERRIDE_DURATION = "default_override_duration"
ATTR_SCHEDULE = "schedule"

# Services
SERVICE_SET_OVERRIDE_TIMER = "set_override_timer"
SERVICE_SET_OVERRIDE_INFINITY = "set_override_infinity"
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_SET_INTERRUPTIBLE = "set_interruptible"
SERVICE_SET_AUTO_TEMPERATURE = "set_auto_temperature"
SERVICE_SET_AWAY_TEMPERATURE = "set_away_temperature"
SERVICE_SET_AWAY_DELAY = "set_away_delay"
SERVICE_SET_DEFAULT_OVERRIDE_MODE = "set_default_override_mode"
SERVICE_SET_SCHEDULE = "set_schedule"