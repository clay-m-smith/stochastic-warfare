"""EW-layer events published on the EventBus.

Covers jamming activation/deactivation, emitter detection, ECCM activation,
GPS spoofing detection, decoy deployment, and SIGINT reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Electronic Attack events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JammingActivatedEvent(Event):
    """Published when a jammer begins active jamming."""

    jammer_id: str
    target_area_center: Position
    radius_m: float
    jam_type: int  # JamTechnique value


@dataclass(frozen=True)
class JammingDeactivatedEvent(Event):
    """Published when a jammer ceases jamming."""

    jammer_id: str


@dataclass(frozen=True)
class DecoyDeployedEvent(Event):
    """Published when an electronic decoy is deployed."""

    unit_id: str
    decoy_type: int  # EWDecoyType value
    position: Position


@dataclass(frozen=True)
class GPSSpoofingDetectedEvent(Event):
    """Published when a unit detects GPS spoofing."""

    unit_id: str
    detection_delay_s: float


# ---------------------------------------------------------------------------
# Electronic Protection events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ECCMActivatedEvent(Event):
    """Published when a unit activates ECCM measures."""

    unit_id: str
    technique: int  # ECCMTechnique value


# ---------------------------------------------------------------------------
# Electronic Support events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmitterDetectedEvent(Event):
    """Published when a SIGINT collector detects an emitter."""

    detector_id: str
    emitter_id: str
    estimated_position: Position
    uncertainty_m: float
    freq_ghz: float
    power_dbm: float


@dataclass(frozen=True)
class SIGINTReportEvent(Event):
    """Published when a SIGINT report is generated."""

    collector_id: str
    emitter_id: str
    intel_type: int  # SIGINTType value
    confidence: float
