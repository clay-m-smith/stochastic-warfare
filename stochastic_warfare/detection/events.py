"""Detection-layer events published on the EventBus."""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


@dataclass(frozen=True)
class DetectionEvent(Event):
    """Published when a sensor detects a target."""

    observer_id: str
    target_id: str
    observer_side: str
    sensor_type: str
    detection_range: float
    confidence: float


@dataclass(frozen=True)
class ClassificationEvent(Event):
    """Published when a detected contact is classified (domain/type)."""

    observer_id: str
    target_id: str
    observer_side: str
    classified_domain: str
    classified_type: str
    confidence: float


@dataclass(frozen=True)
class IdentificationEvent(Event):
    """Published when a classified contact is positively identified."""

    observer_id: str
    target_id: str
    observer_side: str
    identified_type: str
    confidence: float


@dataclass(frozen=True)
class ContactLostEvent(Event):
    """Published when a side loses track of a contact."""

    side: str
    contact_id: str
    last_known_position: tuple[float, float, float]


@dataclass(frozen=True)
class SubmarineContactEvent(Event):
    """Published for underwater contacts with bearing/range estimates."""

    observer_id: str
    target_id: str
    observer_side: str
    contact_type: str
    bearing_deg: float
    range_estimate: float
    bearing_uncertainty_deg: float
    range_uncertainty: float


@dataclass(frozen=True)
class DeceptionEvent(Event):
    """Published when a deception operation is initiated."""

    deceiver_id: str
    target_side: str
    deception_type: str
