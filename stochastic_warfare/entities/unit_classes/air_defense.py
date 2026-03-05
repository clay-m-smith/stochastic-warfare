"""Air defense unit types — SAMs, AAA, radars."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.base import Unit


class ADUnitType(enum.IntEnum):
    """Air defense system classification."""

    SAM_LONG = 0
    SAM_MEDIUM = 1
    SAM_SHORT = 2
    MANPADS = 3
    AAA = 4
    CIWS = 5
    RADAR_EARLY_WARNING = 6
    RADAR_FIRE_CONTROL = 7
    DEW = 8


class RadarState(enum.IntEnum):
    """Radar emission state."""

    OFF = 0
    STANDBY = 1
    SEARCH = 2
    TRACK = 3
    EMCON = 4


@dataclass
class AirDefenseUnit(Unit):
    """An air defense unit with radar state and engagement parameters."""

    ad_type: ADUnitType = ADUnitType.SAM_MEDIUM
    radar_state: RadarState = RadarState.OFF
    min_engagement_altitude: float = 0.0  # meters
    max_engagement_altitude: float = 0.0
    max_engagement_range: float = 0.0  # meters
    ready_missiles: int = 0
    reload_time: float = 0.0  # seconds

    def __post_init__(self) -> None:
        self.domain = Domain.GROUND

    def can_engage(self, target_altitude: float, target_range: float) -> bool:
        """Return True if the target is within engagement envelope."""
        if self.radar_state < RadarState.SEARCH:
            return False
        if self.ready_missiles <= 0:
            return False
        if target_altitude < self.min_engagement_altitude:
            return False
        if target_altitude > self.max_engagement_altitude:
            return False
        if target_range > self.max_engagement_range:
            return False
        return True

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "ad_type": int(self.ad_type),
                "radar_state": int(self.radar_state),
                "min_engagement_altitude": self.min_engagement_altitude,
                "max_engagement_altitude": self.max_engagement_altitude,
                "max_engagement_range": self.max_engagement_range,
                "ready_missiles": self.ready_missiles,
                "reload_time": self.reload_time,
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.ad_type = ADUnitType(state["ad_type"])
        self.radar_state = RadarState(state["radar_state"])
        self.min_engagement_altitude = state["min_engagement_altitude"]
        self.max_engagement_altitude = state["max_engagement_altitude"]
        self.max_engagement_range = state["max_engagement_range"]
        self.ready_missiles = state["ready_missiles"]
        self.reload_time = state["reload_time"]
