"""Era framework — era definitions, configuration, and pre-defined presets.

Each era specifies which engine subsystems are active, which sensor types
are available, and any physics or tick-resolution overrides.  The engine
core is era-agnostic; eras are primarily **data packages** plus targeted
engine gating.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


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

    era: Era = Era.MODERN
    disabled_modules: set[str] = set()
    available_sensor_types: set[str] = set()
    physics_overrides: dict[str, Any] = {}
    tick_resolution_overrides: dict[str, float] = {}


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
    available_sensor_types={"VISUAL"},
    physics_overrides={
        "c2_delay_multiplier": 5.0,
        "cbrn_nuclear_enabled": False,
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
    },
)

_ERA_REGISTRY: dict[str, EraConfig] = {
    "modern": MODERN_ERA_CONFIG,
    "ww2": WW2_ERA_CONFIG,
    "ww1": WW1_ERA_CONFIG,
    "napoleonic": NAPOLEONIC_ERA_CONFIG,
    "ancient_medieval": ANCIENT_MEDIEVAL_ERA_CONFIG,
}


def get_era_config(era_name: str) -> EraConfig:
    """Look up a pre-defined era config by name.

    Returns :data:`MODERN_ERA_CONFIG` for unknown names.
    """
    return _ERA_REGISTRY.get(era_name.lower(), MODERN_ERA_CONFIG)


def register_era_config(era_name: str, config: EraConfig) -> None:
    """Register a custom era configuration."""
    _ERA_REGISTRY[era_name.lower()] = config
