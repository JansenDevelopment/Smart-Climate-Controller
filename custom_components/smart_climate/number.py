"""Number platform — native controls for Smart Climate's numeric settings."""

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_AUTO_TEMPERATURE,
    ATTR_AWAY_DELAY_MINUTES,
    ATTR_AWAY_TEMPERATURE,
    ATTR_COOL_AUTO_TEMPERATURE,
    ATTR_COOL_AWAY_TEMPERATURE,
    ATTR_DEFAULT_OVERRIDE_DURATION,
    ATTR_DEFAULT_OVERRIDE_MODE,
    SERVICE_SET_AUTO_TEMPERATURE,
    SERVICE_SET_AWAY_DELAY,
    SERVICE_SET_AWAY_TEMPERATURE,
    SERVICE_SET_COOL_AUTO_TEMPERATURE,
    SERVICE_SET_COOL_AWAY_TEMPERATURE,
    SERVICE_SET_DEFAULT_OVERRIDE_MODE,
)
from .entity_base import SmartClimateChildEntity


@dataclass(frozen=True)
class SmartClimateNumberDescription:
    """Describes one number helper entity."""

    key: str
    name: str
    attr: str
    service: str
    data_key: str
    min_value: float
    max_value: float
    step: float
    unit: str | None = None
    icon: str | None = None
    # When True, the value is the timer duration, which the backend sets
    # together with the (current) default override mode.
    mode_coupled: bool = False


NUMBERS: tuple[SmartClimateNumberDescription, ...] = (
    SmartClimateNumberDescription(
        key="auto_temperature",
        name="Home Temperature",
        attr=ATTR_AUTO_TEMPERATURE,
        service=SERVICE_SET_AUTO_TEMPERATURE,
        data_key="temperature",
        min_value=5,
        max_value=35,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        icon="mdi:home-thermometer",
    ),
    SmartClimateNumberDescription(
        key="away_temperature",
        name="Away Temperature",
        attr=ATTR_AWAY_TEMPERATURE,
        service=SERVICE_SET_AWAY_TEMPERATURE,
        data_key="temperature",
        min_value=5,
        max_value=35,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        icon="mdi:home-export-outline",
    ),
    SmartClimateNumberDescription(
        key="cool_auto_temperature",
        name="Cooling Home Temperature",
        attr=ATTR_COOL_AUTO_TEMPERATURE,
        service=SERVICE_SET_COOL_AUTO_TEMPERATURE,
        data_key="temperature",
        min_value=15,
        max_value=35,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        icon="mdi:snowflake-thermometer",
    ),
    SmartClimateNumberDescription(
        key="cool_away_temperature",
        name="Cooling Away Temperature",
        attr=ATTR_COOL_AWAY_TEMPERATURE,
        service=SERVICE_SET_COOL_AWAY_TEMPERATURE,
        data_key="temperature",
        min_value=15,
        max_value=35,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        icon="mdi:snowflake",
    ),
    SmartClimateNumberDescription(
        key="away_delay_minutes",
        name="Away Delay",
        attr=ATTR_AWAY_DELAY_MINUTES,
        service=SERVICE_SET_AWAY_DELAY,
        data_key="minutes",
        min_value=0,
        max_value=120,
        step=1,
        unit="min",
        icon="mdi:timer-sand",
    ),
    SmartClimateNumberDescription(
        key="default_override_duration",
        name="Default Override Duration",
        attr=ATTR_DEFAULT_OVERRIDE_DURATION,
        service=SERVICE_SET_DEFAULT_OVERRIDE_MODE,
        data_key="duration",
        min_value=1,
        max_value=1440,
        step=1,
        unit="min",
        icon="mdi:timer-cog-outline",
        mode_coupled=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Climate number helpers."""
    async_add_entities(
        SmartClimateNumber(hass, entry, description) for description in NUMBERS
    )


class SmartClimateNumber(SmartClimateChildEntity, NumberEntity):
    """A numeric Smart Climate setting exposed as a native number entity."""

    def __init__(self, hass, entry, description: SmartClimateNumberDescription) -> None:
        super().__init__(hass, entry, description.key)
        self._description = description
        self._attr_name = description.name
        self._attr_native_min_value = description.min_value
        self._attr_native_max_value = description.max_value
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_icon = description.icon
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self._climate_attr(self._description.attr)

    async def async_set_native_value(self, value: float) -> None:
        if self._description.mode_coupled:
            # Duration is set alongside the current default override mode.
            mode = self._climate_attr(ATTR_DEFAULT_OVERRIDE_MODE, "timer")
            await self._call_service(
                self._description.service, mode=mode, duration=int(value)
            )
        else:
            await self._call_service(
                self._description.service, **{self._description.data_key: value}
            )
