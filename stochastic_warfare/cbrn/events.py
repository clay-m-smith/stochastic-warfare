"""CBRN-domain events published on the EventBus.

Covers chemical/biological agent releases, nuclear detonations, contamination
detection/clearing, MOPP level changes, CBRN casualties, decontamination
operations, EMP effects, and fallout plumes.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


# ---------------------------------------------------------------------------
# Release & detonation events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CBRNReleaseEvent(Event):
    """Published when a CBRN agent is released into the environment."""

    release_id: str
    agent_id: str
    agent_category: int
    position_easting: float
    position_northing: float
    quantity_kg: float
    delivery_method: str


@dataclass(frozen=True)
class NuclearDetonationEvent(Event):
    """Published when a nuclear weapon detonates."""

    weapon_id: str
    position_easting: float
    position_northing: float
    yield_kt: float
    airburst: bool


# ---------------------------------------------------------------------------
# Contamination events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContaminationDetectedEvent(Event):
    """Published when contamination is first detected in a cell."""

    cell_row: int
    cell_col: int
    agent_id: str
    concentration_mg_m3: float


@dataclass(frozen=True)
class ContaminationClearedEvent(Event):
    """Published when contamination drops below threshold in a cell."""

    cell_row: int
    cell_col: int
    agent_id: str


# ---------------------------------------------------------------------------
# Protection & MOPP events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MOPPLevelChangedEvent(Event):
    """Published when a unit changes MOPP level."""

    unit_id: str
    previous_level: int
    new_level: int


# ---------------------------------------------------------------------------
# Casualty & medical events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CBRNCasualtyEvent(Event):
    """Published when a unit suffers CBRN casualties."""

    unit_id: str
    agent_id: str
    casualties_incapacitated: int
    casualties_lethal: int
    dosage_ct: float


# ---------------------------------------------------------------------------
# Decontamination events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecontaminationStartedEvent(Event):
    """Published when a unit begins a decontamination operation."""

    unit_id: str
    decon_type: int
    estimated_duration_s: float


@dataclass(frozen=True)
class DecontaminationCompletedEvent(Event):
    """Published when a decontamination operation completes."""

    unit_id: str
    decon_type: int
    effectiveness: float


# ---------------------------------------------------------------------------
# Nuclear-specific events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EMPEvent(Event):
    """Published when a nuclear EMP affects the theater."""

    center_easting: float
    center_northing: float
    radius_m: float
    affected_unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class FalloutPlumeEvent(Event):
    """Published when a fallout plume forms after a ground burst."""

    detonation_id: str
    initial_center_easting: float
    initial_center_northing: float
    wind_direction_rad: float
    estimated_plume_length_m: float
