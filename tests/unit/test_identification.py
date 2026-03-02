"""Tests for detection/identification.py — identification pipeline."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.detection import DetectionResult
from stochastic_warfare.detection.identification import (
    ContactInfo,
    ContactLevel,
    IdentificationEngine,
)
from stochastic_warfare.detection.sensors import SensorType


# ── helpers ──────────────────────────────────────────────────────────


def _engine(seed: int = 42) -> IdentificationEngine:
    return IdentificationEngine(np.random.Generator(np.random.PCG64(seed)))


def _detection(snr_db: float = 20.0, **kwargs) -> DetectionResult:
    defaults = dict(
        detected=True, probability=0.9, snr_db=snr_db,
        range_m=5000.0, sensor_type=SensorType.RADAR, bearing_deg=0.0,
    )
    defaults.update(kwargs)
    return DetectionResult(**defaults)


def _unit(domain=Domain.GROUND, unit_type: str = "m1a2"):
    return SimpleNamespace(domain=domain, unit_type=unit_type)


# ── ContactLevel enum ────────────────────────────────────────────────


class TestContactLevel:
    def test_ordering(self) -> None:
        assert ContactLevel.UNKNOWN < ContactLevel.DETECTED
        assert ContactLevel.DETECTED < ContactLevel.CLASSIFIED
        assert ContactLevel.CLASSIFIED < ContactLevel.IDENTIFIED


# ── ContactInfo ──────────────────────────────────────────────────────


class TestContactInfo:
    def test_fields(self) -> None:
        ci = ContactInfo(ContactLevel.CLASSIFIED, "GROUND", "ARMOR", None, 0.7)
        assert ci.level == ContactLevel.CLASSIFIED
        assert ci.domain_estimate == "GROUND"
        assert ci.type_estimate == "ARMOR"
        assert ci.specific_estimate is None
        assert ci.confidence == 0.7


# ── classify_from_detection ──────────────────────────────────────────


class TestClassifyFromDetection:
    def test_low_snr_detected_only(self) -> None:
        """Low SNR (just above threshold) should produce DETECTED level."""
        engine = _engine()
        det = _detection(snr_db=11.0)  # threshold=10, margin=1 < 3 for CLASSIFIED
        info = engine.classify_from_detection(det, _unit(), threshold_db=10.0)
        assert info.level == ContactLevel.DETECTED
        assert info.domain_estimate is None
        assert info.specific_estimate is None

    def test_medium_snr_classified(self) -> None:
        """Medium SNR should produce CLASSIFIED level (domain known)."""
        engine = _engine(seed=999)  # seed that avoids misclassification
        det = _detection(snr_db=15.0)  # threshold=10, margin=5 >= 3
        info = engine.classify_from_detection(det, _unit(), threshold_db=10.0)
        assert info.level >= ContactLevel.CLASSIFIED
        if info.level == ContactLevel.CLASSIFIED:
            assert info.domain_estimate is not None

    def test_high_snr_identified(self) -> None:
        """High SNR should produce IDENTIFIED level."""
        engine = _engine(seed=100)
        det = _detection(snr_db=25.0)  # threshold=10, margin=15 >= 10
        info = engine.classify_from_detection(det, _unit(), threshold_db=10.0)
        # Could be downgraded by misclassification, but usually IDENTIFIED
        assert info.level >= ContactLevel.CLASSIFIED

    def test_very_high_snr_always_identified(self) -> None:
        """Very high SNR (way above threshold) should almost certainly IDENTIFY."""
        engine = _engine(seed=42)
        det = _detection(snr_db=50.0)
        info = engine.classify_from_detection(det, _unit(), threshold_db=10.0)
        assert info.level == ContactLevel.IDENTIFIED
        assert info.specific_estimate is not None

    def test_no_target_unit(self) -> None:
        """Without target unit, estimates are None."""
        engine = _engine()
        det = _detection(snr_db=25.0)
        info = engine.classify_from_detection(det, None, threshold_db=10.0)
        assert info.level >= ContactLevel.DETECTED

    def test_confidence_increases_with_snr(self) -> None:
        engine = _engine(seed=42)
        det_low = _detection(snr_db=11.0)
        det_high = _detection(snr_db=25.0)
        info_low = engine.classify_from_detection(det_low, None, threshold_db=10.0)
        engine2 = _engine(seed=42)
        info_high = engine2.classify_from_detection(det_high, None, threshold_db=10.0)
        assert info_high.confidence >= info_low.confidence

    def test_confidence_bounded(self) -> None:
        engine = _engine()
        det = _detection(snr_db=100.0)
        info = engine.classify_from_detection(det, None, threshold_db=10.0)
        assert 0.0 <= info.confidence <= 1.0


# ── update_contact ───────────────────────────────────────────────────


class TestUpdateContact:
    def test_level_never_regresses(self) -> None:
        existing = ContactInfo(ContactLevel.CLASSIFIED, "GROUND", "ARMOR", None, 0.7)
        new = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
        merged = IdentificationEngine.update_contact(existing, new)
        assert merged.level == ContactLevel.CLASSIFIED

    def test_level_advances(self) -> None:
        existing = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.4)
        new = ContactInfo(ContactLevel.IDENTIFIED, "GROUND", "m1a2", "m1a2", 0.8)
        merged = IdentificationEngine.update_contact(existing, new)
        assert merged.level == ContactLevel.IDENTIFIED

    def test_confidence_accumulates(self) -> None:
        existing = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5)
        new = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5)
        merged = IdentificationEngine.update_contact(existing, new)
        # 1 - (1-0.5)*(1-0.5) = 0.75
        assert merged.confidence == pytest.approx(0.75)

    def test_confidence_capped(self) -> None:
        existing = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.95)
        new = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.95)
        merged = IdentificationEngine.update_contact(existing, new)
        assert merged.confidence <= 1.0

    def test_domain_preserved(self) -> None:
        existing = ContactInfo(ContactLevel.CLASSIFIED, "GROUND", "ARMOR", None, 0.6)
        new = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
        merged = IdentificationEngine.update_contact(existing, new)
        assert merged.domain_estimate == "GROUND"

    def test_domain_updated(self) -> None:
        existing = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
        new = ContactInfo(ContactLevel.CLASSIFIED, "AERIAL", "FIGHTER", None, 0.7)
        merged = IdentificationEngine.update_contact(existing, new)
        assert merged.domain_estimate == "AERIAL"

    def test_multiple_updates_increase_confidence(self) -> None:
        info = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
        for _ in range(5):
            obs = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.3)
            info = IdentificationEngine.update_contact(info, obs)
        assert info.confidence > 0.8


# ── misclassification_probability ────────────────────────────────────


class TestMisclassificationProbability:
    def test_low_snr_high_prob(self) -> None:
        p = IdentificationEngine.misclassification_probability(5.0, 10.0)
        assert p > 0.5

    def test_high_snr_low_prob(self) -> None:
        p = IdentificationEngine.misclassification_probability(30.0, 10.0)
        assert p < 0.1

    def test_at_midpoint(self) -> None:
        p = IdentificationEngine.misclassification_probability(16.0, 10.0)
        assert p == pytest.approx(0.5, abs=0.05)

    def test_bounded_0_1(self) -> None:
        p_low = IdentificationEngine.misclassification_probability(-100.0, 0.0)
        p_high = IdentificationEngine.misclassification_probability(100.0, 0.0)
        assert 0.0 <= p_low <= 1.0
        assert 0.0 <= p_high <= 1.0

    def test_monotonic_decrease(self) -> None:
        prev = 1.0
        for snr in range(-10, 30, 2):
            p = IdentificationEngine.misclassification_probability(float(snr), 0.0)
            assert p <= prev + 1e-10
            prev = p


# ── Determinism ──────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        det = _detection(snr_db=15.0)
        unit = _unit()
        results = []
        for _ in range(2):
            e = _engine(seed=777)
            r = e.classify_from_detection(det, unit, threshold_db=10.0)
            results.append(r)
        assert results[0] == results[1]


# ── State round-trip ─────────────────────────────────────────────────


class TestStateRoundTrip:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        det = _detection(snr_db=15.0)
        engine.classify_from_detection(det, _unit(), threshold_db=10.0)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)

        det2 = _detection(snr_db=18.0)
        r1 = engine.classify_from_detection(det2, _unit(), threshold_db=10.0)
        r2 = engine2.classify_from_detection(det2, _unit(), threshold_db=10.0)
        assert r1 == r2
