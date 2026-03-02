"""Tests for detection/events.py — detection-layer event types."""

from __future__ import annotations

from datetime import datetime, timezone

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.detection.events import (
    ClassificationEvent,
    ContactLostEvent,
    DeceptionEvent,
    DetectionEvent,
    IdentificationEvent,
    SubmarineContactEvent,
)

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
SRC = ModuleId.DETECTION


class TestDetectionEvent:
    def test_creation(self) -> None:
        e = DetectionEvent(
            timestamp=TS, source=SRC,
            observer_id="obs-1", target_id="tgt-1", observer_side="blue",
            sensor_type="RADAR", detection_range=5000.0, confidence=0.85,
        )
        assert e.observer_id == "obs-1"
        assert e.target_id == "tgt-1"
        assert e.sensor_type == "RADAR"
        assert e.detection_range == 5000.0
        assert e.confidence == 0.85

    def test_is_event(self) -> None:
        e = DetectionEvent(
            timestamp=TS, source=SRC,
            observer_id="a", target_id="b", observer_side="red",
            sensor_type="VISUAL", detection_range=100.0, confidence=0.5,
        )
        assert isinstance(e, Event)

    def test_frozen(self) -> None:
        e = DetectionEvent(
            timestamp=TS, source=SRC,
            observer_id="a", target_id="b", observer_side="blue",
            sensor_type="THERMAL", detection_range=200.0, confidence=0.7,
        )
        import dataclasses
        assert dataclasses.is_dataclass(e)


class TestClassificationEvent:
    def test_creation(self) -> None:
        e = ClassificationEvent(
            timestamp=TS, source=SRC,
            observer_id="obs-1", target_id="tgt-1", observer_side="blue",
            classified_domain="GROUND", classified_type="ARMOR", confidence=0.7,
        )
        assert e.classified_domain == "GROUND"
        assert e.classified_type == "ARMOR"
        assert isinstance(e, Event)


class TestIdentificationEvent:
    def test_creation(self) -> None:
        e = IdentificationEvent(
            timestamp=TS, source=SRC,
            observer_id="obs-1", target_id="tgt-1", observer_side="blue",
            identified_type="m1a2", confidence=0.95,
        )
        assert e.identified_type == "m1a2"
        assert isinstance(e, Event)


class TestContactLostEvent:
    def test_creation(self) -> None:
        e = ContactLostEvent(
            timestamp=TS, source=SRC,
            side="blue", contact_id="c-42",
            last_known_position=(1000.0, 2000.0, 0.0),
        )
        assert e.side == "blue"
        assert e.contact_id == "c-42"
        assert e.last_known_position == (1000.0, 2000.0, 0.0)
        assert isinstance(e, Event)


class TestSubmarineContactEvent:
    def test_creation(self) -> None:
        e = SubmarineContactEvent(
            timestamp=TS, source=SRC,
            observer_id="ddg-1", target_id="ssn-1", observer_side="blue",
            contact_type="SONAR_PASSIVE", bearing_deg=135.0,
            range_estimate=20000.0, bearing_uncertainty_deg=3.0,
            range_uncertainty=5000.0,
        )
        assert e.contact_type == "SONAR_PASSIVE"
        assert e.bearing_deg == 135.0
        assert e.range_estimate == 20000.0
        assert isinstance(e, Event)


class TestDeceptionEvent:
    def test_creation(self) -> None:
        e = DeceptionEvent(
            timestamp=TS, source=SRC,
            deceiver_id="decoy-1", target_side="red",
            deception_type="DECOY_RADAR",
        )
        assert e.deceiver_id == "decoy-1"
        assert e.target_side == "red"
        assert isinstance(e, Event)
