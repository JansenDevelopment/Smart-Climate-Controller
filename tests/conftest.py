"""Pytest configuration: register HA stub modules before any collection occurs."""

import sys
import types
from unittest.mock import MagicMock


def _register_stub(name: str, **attrs):
    """Create and register a stub module with the given attributes."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _ensure_parent(dotted_name: str):
    """Ensure every parent package in the dotted name exists in sys.modules."""
    parts = dotted_name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            _register_stub(parent)


# ---- homeassistant ---------------------------------------------------------
_register_stub("homeassistant")

# homeassistant.core
_register_stub(
    "homeassistant.core",
    HomeAssistant=type("HomeAssistant", (), {}),
    callback=lambda f: f,
)

# homeassistant.const
_register_stub(
    "homeassistant.const",
    UnitOfTemperature=MagicMock(CELSIUS="°C"),
    CONF_NAME="name",
)

# homeassistant.config_entries
_register_stub(
    "homeassistant.config_entries",
    ConfigEntry=type("ConfigEntry", (), {}),
)

# homeassistant.components
_register_stub("homeassistant.components")

# homeassistant.components.climate
_ClimateEntity = type("ClimateEntity", (), {"async_write_ha_state": MagicMock()})
_register_stub(
    "homeassistant.components.climate",
    ClimateEntity=_ClimateEntity,
    ClimateEntityFeature=MagicMock(TARGET_TEMPERATURE=1, PRESET_MODE=2),
    HVACMode=MagicMock(OFF="off", HEAT="heat"),
)

# homeassistant.components.lovelace
_register_stub("homeassistant.components.lovelace", MODE_STORAGE="storage")

# homeassistant.helpers
_register_stub("homeassistant.helpers")

# homeassistant.helpers.entity_platform
_register_stub(
    "homeassistant.helpers.entity_platform",
    AddEntitiesCallback=None,
)

# homeassistant.helpers.event
_register_stub(
    "homeassistant.helpers.event",
    async_track_time_interval=MagicMock(return_value=lambda: None),
    async_track_state_change_event=MagicMock(return_value=lambda: None),
    async_call_later=MagicMock(return_value=lambda: None),
)

# homeassistant.helpers.config_validation
_cv = MagicMock()
_cv.string = str
_cv.ensure_list = lambda v: v if isinstance(v, list) else [v]
_register_stub("homeassistant.helpers.config_validation", **{k: getattr(_cv, k) for k in dir(_cv)})
sys.modules["homeassistant.helpers.config_validation"] = _cv

# homeassistant.helpers.selector
_register_stub("homeassistant.helpers.selector", BooleanSelector=MagicMock)

# ---- voluptuous ------------------------------------------------------------
_vol = MagicMock()
_vol.Schema = lambda schema, **kw: schema
_vol.Required = lambda key, **kw: key
_vol.Optional = lambda key, **kw: key
_vol.All = lambda *args: args[-1]
_vol.ALLOW_EXTRA = 1
sys.modules["voluptuous"] = _vol
