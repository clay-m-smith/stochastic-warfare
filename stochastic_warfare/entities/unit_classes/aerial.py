"""Aerial unit types — fixed-wing, rotary-wing, and UAVs."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from stochastic_warfare.core.types import Domain
from stochastic_warfare.entities.base import Unit


class AerialUnitType(enum.IntEnum):
    """Aerial platform classification."""

    # Fixed-wing
    FIGHTER = 0
    ATTACK = 1
    BOMBER = 2
    TRANSPORT = 3
    RECON = 4
    TANKER = 5
    EW = 6
    AEW = 7
    # Rotary-wing
    ATTACK_HELO = 8
    UTILITY_HELO = 9
    RECON_HELO = 10
    CARGO_HELO = 11
    # UAV
    UAV_RECON = 12
    UAV_ARMED = 13
    UAV_LOITERING_MUNITION = 14


class FlightState(enum.IntEnum):
    """Current phase of flight."""

    GROUNDED = 0
    TAXIING = 1
    TAKEOFF = 2
    AIRBORNE = 3
    LANDING = 4
    HOVERING = 5


class AirPosture(enum.IntEnum):
    """Tactical mission posture for air units.

    Orthogonal to :class:`FlightState` (physical flight phase).
    Controls engagement eligibility.
    """

    GROUNDED = 0
    INGRESSING = 1
    ON_STATION = 2
    RETURNING = 3


@dataclass
class AerialUnit(Unit):
    """An aerial-domain unit with flight state and fuel."""

    aerial_type: AerialUnitType = AerialUnitType.FIGHTER
    flight_state: FlightState = FlightState.GROUNDED
    air_posture: AirPosture = AirPosture.GROUNDED
    altitude: float = 0.0  # meters AGL
    fuel_remaining: float = 1.0  # 0.0–1.0 fraction
    service_ceiling: float = 15000.0  # meters
    data_link_range: float | None = None  # None = manned aircraft
    data_link_active: bool = True
    loiter_time_remaining: float = 0.0  # seconds

    def __post_init__(self) -> None:
        self.domain = Domain.AERIAL

    @property
    def is_uav(self) -> bool:
        """Return True if this is an unmanned aerial vehicle."""
        return self.aerial_type in (
            AerialUnitType.UAV_RECON,
            AerialUnitType.UAV_ARMED,
            AerialUnitType.UAV_LOITERING_MUNITION,
        )

    @property
    def is_rotary_wing(self) -> bool:
        """Return True if this is a helicopter."""
        return self.aerial_type in (
            AerialUnitType.ATTACK_HELO,
            AerialUnitType.UTILITY_HELO,
            AerialUnitType.RECON_HELO,
            AerialUnitType.CARGO_HELO,
        )

    def get_state(self) -> dict:
        state = super().get_state()
        state.update(
            {
                "aerial_type": int(self.aerial_type),
                "flight_state": int(self.flight_state),
                "air_posture": int(self.air_posture),
                "altitude": self.altitude,
                "fuel_remaining": self.fuel_remaining,
                "service_ceiling": self.service_ceiling,
                "data_link_range": self.data_link_range,
                "data_link_active": self.data_link_active,
                "loiter_time_remaining": self.loiter_time_remaining,
            }
        )
        return state

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        self.aerial_type = AerialUnitType(state["aerial_type"])
        self.flight_state = FlightState(state["flight_state"])
        self.air_posture = AirPosture(state.get("air_posture", 0))
        self.altitude = state["altitude"]
        self.fuel_remaining = state["fuel_remaining"]
        self.service_ceiling = state["service_ceiling"]
        self.data_link_range = state["data_link_range"]
        self.data_link_active = state["data_link_active"]
        self.loiter_time_remaining = state["loiter_time_remaining"]
