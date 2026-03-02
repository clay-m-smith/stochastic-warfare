"""Tests for combat/fratricide.py."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.fratricide import (
    FratricideConfig,
    FratricideEngine,
    FratricideRisk,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> FratricideEngine:
    return FratricideEngine(EventBus(), _rng(seed))


class TestCheckFratricideRisk:
    def test_identified_high_confidence_low_risk(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk("IDENTIFIED", confidence=0.95)
        assert risk.risk < 0.05

    def test_detected_only_high_risk(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk("DETECTED", confidence=0.3)
        assert risk.risk > 0.10

    def test_unknown_very_high_risk(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk("UNKNOWN", confidence=0.0)
        assert risk.risk > 0.30

    def test_classified_moderate_risk(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk("CLASSIFIED", confidence=0.5)
        assert 0.01 < risk.risk < 0.30

    def test_high_confidence_reduces_risk(self) -> None:
        e = _engine()
        low_conf = e.check_fratricide_risk("CLASSIFIED", confidence=0.2)
        high_conf = e.check_fratricide_risk("CLASSIFIED", confidence=0.9)
        assert high_conf.risk < low_conf.risk

    def test_poor_visibility_increases_risk(self) -> None:
        e = _engine()
        clear = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, visibility=1.0)
        dark = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, visibility=0.2)
        assert dark.risk > clear.risk

    def test_urban_terrain_increases_risk(self) -> None:
        e = _engine()
        open_terrain = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, urban_terrain=False)
        urban = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, urban_terrain=True)
        assert urban.risk > open_terrain.risk

    def test_stress_increases_risk(self) -> None:
        e = _engine()
        calm = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, stress_level=0.0)
        stressed = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, stress_level=0.8)
        assert stressed.risk > calm.risk

    def test_risk_capped(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk(
            "UNKNOWN", confidence=0.0, visibility=0.1,
            urban_terrain=True, stress_level=1.0,
        )
        assert risk.risk <= 0.99

    def test_modifiers_in_result(self) -> None:
        e = _engine()
        risk = e.check_fratricide_risk("CLASSIFIED", confidence=0.5, visibility=0.5)
        assert "base" in risk.modifiers
        assert "confidence" in risk.modifiers
        assert "visibility" in risk.modifiers


class TestResolveFratricide:
    def test_not_friendly_always_safe(self) -> None:
        e = _engine()
        risk = FratricideRisk(risk=0.5, is_friendly=False, modifiers={})
        result = e.resolve_fratricide(risk, "s1", "t1")
        assert result is False

    def test_friendly_with_high_risk(self) -> None:
        # Run many trials — high risk should sometimes cause fratricide
        hits = 0
        for seed in range(100):
            eng = _engine(seed)
            risk = FratricideRisk(risk=0.5, is_friendly=True, modifiers={})
            if eng.resolve_fratricide(risk, "s1", "t1"):
                hits += 1
        assert 20 < hits < 80  # Should be around 50

    def test_friendly_low_risk_rarely_fratricide(self) -> None:
        hits = 0
        for seed in range(200):
            eng = _engine(seed)
            risk = FratricideRisk(risk=0.02, is_friendly=True, modifiers={})
            if eng.resolve_fratricide(risk, "s1", "t1"):
                hits += 1
        assert hits < 20


class TestDeconflict:
    def test_friendly_in_line_of_fire(self) -> None:
        e = _engine()
        at_risk = e.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,  # Due north
            fire_range_m=2000.0,
            friendlies=[("f1", Position(0.0, 1000.0, 0.0))],
        )
        assert "f1" in at_risk

    def test_friendly_behind_shooter_safe(self) -> None:
        e = _engine()
        at_risk = e.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,  # Due north
            fire_range_m=2000.0,
            friendlies=[("f1", Position(0.0, -500.0, 0.0))],
        )
        assert "f1" not in at_risk

    def test_friendly_far_away_safe(self) -> None:
        e = _engine()
        at_risk = e.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,
            fire_range_m=2000.0,
            friendlies=[("f1", Position(5000.0, 5000.0, 0.0))],
        )
        assert "f1" not in at_risk

    def test_friendly_perpendicular_safe(self) -> None:
        e = _engine()
        at_risk = e.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,  # Due north
            fire_range_m=2000.0,
            friendlies=[("f1", Position(2000.0, 1000.0, 0.0))],
        )
        assert "f1" not in at_risk

    def test_multiple_friendlies(self) -> None:
        e = _engine()
        at_risk = e.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,
            fire_range_m=2000.0,
            friendlies=[
                ("f1", Position(0.0, 500.0, 0.0)),
                ("f2", Position(5000.0, 0.0, 0.0)),
                ("f3", Position(50.0, 1500.0, 0.0)),
            ],
        )
        assert "f1" in at_risk
        assert "f2" not in at_risk
        assert "f3" in at_risk


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        risk = FratricideRisk(risk=0.5, is_friendly=True, modifiers={})
        e.resolve_fratricide(risk, "s1", "t1")
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.resolve_fratricide(risk, "s1", "t1")
        r2 = e2.resolve_fratricide(risk, "s1", "t1")
        assert r1 == r2
