"""Military echelon levels and definitions."""

from __future__ import annotations

import enum

from pydantic import BaseModel


class EchelonLevel(enum.IntEnum):
    """Standard military echelon hierarchy."""

    INDIVIDUAL = 0
    FIRE_TEAM = 1
    SQUAD = 2
    SECTION = 3
    PLATOON = 4
    COMPANY = 5
    BATTALION = 6
    REGIMENT = 7
    BRIGADE = 8
    DIVISION = 9
    CORPS = 10
    ARMY = 11
    ARMY_GROUP = 12
    THEATER = 13


class EchelonDefinition(BaseModel):
    """Properties typical of an echelon level."""

    level: int
    name: str
    typical_size: int
    span_of_control: int
    staff_available: list[str]
    planning_capacity: str  # "none", "basic", "full"


# Standard definitions for US Army echelons.
ECHELON_DEFINITIONS: dict[EchelonLevel, EchelonDefinition] = {
    EchelonLevel.FIRE_TEAM: EchelonDefinition(
        level=1, name="Fire Team", typical_size=4,
        span_of_control=4, staff_available=[], planning_capacity="none",
    ),
    EchelonLevel.SQUAD: EchelonDefinition(
        level=2, name="Squad", typical_size=9,
        span_of_control=3, staff_available=[], planning_capacity="none",
    ),
    EchelonLevel.PLATOON: EchelonDefinition(
        level=4, name="Platoon", typical_size=40,
        span_of_control=4, staff_available=[], planning_capacity="none",
    ),
    EchelonLevel.COMPANY: EchelonDefinition(
        level=5, name="Company", typical_size=150,
        span_of_control=4, staff_available=["S1"], planning_capacity="basic",
    ),
    EchelonLevel.BATTALION: EchelonDefinition(
        level=6, name="Battalion", typical_size=600,
        span_of_control=5, staff_available=["S1", "S2", "S3", "S4"],
        planning_capacity="full",
    ),
    EchelonLevel.BRIGADE: EchelonDefinition(
        level=8, name="Brigade", typical_size=4000,
        span_of_control=5,
        staff_available=["S1", "S2", "S3", "S4", "S6"],
        planning_capacity="full",
    ),
    EchelonLevel.DIVISION: EchelonDefinition(
        level=9, name="Division", typical_size=15000,
        span_of_control=5,
        staff_available=["S1", "S2", "S3", "S4", "S5", "S6"],
        planning_capacity="full",
    ),
}
