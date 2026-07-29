"""Era framework — era definitions, configuration, and pre-defined presets.

Each era specifies which engine subsystems are active, which sensor types
are available, and any physics or tick-resolution overrides.  The engine
core is era-agnostic; eras are primarily **data packages** plus targeted
engine gating.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# ---------------------------------------------------------------------------
# Era enum
# ---------------------------------------------------------------------------


class Era(str, Enum):
    """Historical era identifier."""

    MODERN = "modern"
    WW2 = "ww2"
    WW1 = "ww1"
    NAPOLEONIC = "napoleonic"
    ANCIENT_MEDIEVAL = "ancient_medieval"


# ---------------------------------------------------------------------------
# Era configuration
# ---------------------------------------------------------------------------

EraFeature = Literal[
    "ew",
    "space",
    "cbrn",
    "gps",
    "thermal_sights",
    "data_links",
    "pgm",
]


class EraConfig(BaseModel):
    """Configuration describing which subsystems and capabilities are
    available in a given era.

    Parameters
    ----------
    era:
        Which era this config represents.
    disabled_modules:
        Set of module keys that are disabled for this era.
        Known keys: ``"ew"``, ``"space"``, ``"cbrn"``, ``"gps"``,
        ``"thermal_sights"``, ``"data_links"``, ``"pgm"``.
    available_sensor_types:
        If non-empty, only these sensor types are allowed.  Empty set
        means all sensor types are available (modern default).
    physics_overrides:
        Arbitrary key-value physics parameter overrides for this era.
    tick_resolution_overrides:
        Override tick durations.  Keys: ``"strategic_s"``,
        ``"operational_s"``, ``"tactical_s"``.
    """

    model_config = ConfigDict(extra="forbid")

    era: Era = Era.MODERN
    disabled_modules: set[EraFeature] = Field(default_factory=set)
    available_sensor_types: set[str] = Field(default_factory=set)
    physics_overrides: dict[str, Any] = Field(default_factory=dict)
    tick_resolution_overrides: dict[str, float] = Field(default_factory=dict)

    def feature_enabled(self, feature: EraFeature) -> bool:
        """Return whether an era permits one declared runtime feature."""
        return feature not in self.disabled_modules

    @field_serializer(
        "disabled_modules",
        "available_sensor_types",
        when_used="json",
    )
    def _serialize_sets(self, values: set[str]) -> list[str]:
        """Serialize unordered capability sets in stable lexical order."""
        return sorted(values)


# ---------------------------------------------------------------------------
# Pre-defined era configs
# ---------------------------------------------------------------------------

MODERN_ERA_CONFIG = EraConfig(era=Era.MODERN)

WW2_ERA_CONFIG = EraConfig(
    era=Era.WW2,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={
        "VISUAL",
        "RADAR",
        "PASSIVE_SONAR",
        "ACTIVE_SONAR",
    },
    physics_overrides={
        "treatment_hours_minor": 3.0,
        "treatment_hours_serious": 12.0,
        "treatment_hours_critical": 36.0,
        "repair_time_hours": 6.0,
    },
)

WW1_ERA_CONFIG = EraConfig(
    era=Era.WW1,
    disabled_modules={
        "ew",
        "space",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL", "PASSIVE_SONAR"},
    physics_overrides={
        "c2_delay_multiplier": 5.0,
        "cbrn_nuclear_enabled": False,
        "treatment_hours_minor": 4.0,
        "treatment_hours_serious": 24.0,
        "treatment_hours_critical": 72.0,
        "repair_time_hours": 8.0,
    },
)

NAPOLEONIC_ERA_CONFIG = EraConfig(
    era=Era.NAPOLEONIC,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL"},
    physics_overrides={
        "c2_delay_multiplier": 8.0,
        "cbrn_nuclear_enabled": False,
        "treatment_hours_minor": 8.0,
        "treatment_hours_serious": 48.0,
        "treatment_hours_critical": 168.0,
    },
)

ANCIENT_MEDIEVAL_ERA_CONFIG = EraConfig(
    era=Era.ANCIENT_MEDIEVAL,
    disabled_modules={
        "ew",
        "space",
        "cbrn",
        "gps",
        "thermal_sights",
        "data_links",
        "pgm",
    },
    available_sensor_types={"VISUAL"},
    physics_overrides={
        "c2_delay_multiplier": 12.0,
        "cbrn_nuclear_enabled": False,
        "treatment_hours_minor": 24.0,
        "treatment_hours_serious": 168.0,
        "treatment_hours_critical": 336.0,
    },
)

_ERA_REGISTRY: dict[str, EraConfig] = {
    "modern": MODERN_ERA_CONFIG.model_copy(deep=True),
    "ww2": WW2_ERA_CONFIG.model_copy(deep=True),
    "ww1": WW1_ERA_CONFIG.model_copy(deep=True),
    "napoleonic": NAPOLEONIC_ERA_CONFIG.model_copy(deep=True),
    "ancient_medieval": ANCIENT_MEDIEVAL_ERA_CONFIG.model_copy(deep=True),
}


def get_era_config(era_name: str) -> EraConfig:
    """Return an isolated registered era configuration.

    Raises
    ------
    ValueError
        If ``era_name`` is not registered.
    """
    normalized_name = era_name.lower()
    try:
        config = _ERA_REGISTRY[normalized_name]
    except KeyError as exc:
        registered = ", ".join(sorted(_ERA_REGISTRY))
        raise ValueError(
            f"Unknown era {era_name!r}; registered eras: {registered}",
        ) from exc
    return config.model_copy(deep=True)


def register_era_config(era_name: str, config: EraConfig) -> None:
    """Validate and register an isolated custom era configuration."""
    validated = EraConfig.model_validate(
        config.model_dump(mode="python"),
    )
    _ERA_REGISTRY[era_name.lower()] = validated.model_copy(deep=True)
