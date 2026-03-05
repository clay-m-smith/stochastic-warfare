"""Shared types and physical constants used across all modules."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Semantic type aliases
# ---------------------------------------------------------------------------

SimulationTime = datetime
"""UTC datetime representing a point in simulation time."""

Meters = float
Seconds = float
Degrees = float
Radians = float

# ---------------------------------------------------------------------------
# Position types
# ---------------------------------------------------------------------------


class Position(NamedTuple):
    """ENU (East-North-Up) position in meters, relative to scenario origin."""

    easting: float
    northing: float
    altitude: float = 0.0


class GeodeticPosition(NamedTuple):
    """WGS-84 geodetic position."""

    latitude: float
    longitude: float
    altitude: float = 0.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ModuleId(str, enum.Enum):
    """Identifiers for simulation subsystems (used as PRNG stream keys)."""

    CORE = "core"
    COMBAT = "combat"
    MOVEMENT = "movement"
    DETECTION = "detection"
    MORALE = "morale"
    ENVIRONMENT = "environment"
    LOGISTICS = "logistics"
    C2 = "c2"
    ENTITIES = "entities"
    TERRAIN = "terrain"
    POPULATION = "population"
    AIR_CAMPAIGN = "air_campaign"
    EW = "ew"
    SPACE = "space"
    CBRN = "cbrn"
    ESCALATION = "escalation"


class Domain(enum.IntEnum):
    """Operational domain for a unit or platform."""

    GROUND = 0
    AERIAL = 1
    NAVAL = 2
    SUBMARINE = 3
    AMPHIBIOUS = 4


class Side(str, enum.Enum):
    """Force allegiance."""

    BLUE = "blue"
    RED = "red"
    NEUTRAL = "neutral"
    CIVILIAN = "civilian"


class TickResolution(enum.Enum):
    """Granularity of a simulation tick."""

    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

SPEED_OF_LIGHT: Meters = 299_792_458.0
"""Speed of light in vacuum (m/s)."""

STANDARD_GRAVITY: float = 9.80665
"""Standard gravitational acceleration (m/s^2)."""

EARTH_MEAN_RADIUS: Meters = 6_371_000.0
"""Mean radius of Earth (m)."""

STANDARD_LAPSE_RATE: float = 0.0065
"""ISA temperature lapse rate (K/m)."""
