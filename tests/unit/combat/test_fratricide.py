"""Unit tests for FratricideEngine — risk assessment and deconfliction."""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.combat.fratricide import (
    FratricideConfig,
    FratricideEngine,
    FratricideRisk,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> FratricideEngine:
    config = FratricideConfig(**cfg_kwargs) if cfg_kwargs else None
    return FratricideEngine(EventBus(), _rng(seed), config=config)


# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------


class TestRiskLevels:
    """Base risk from identification level."""

    def test_identified_low_risk(self):
        eng = _make_engine()
        risk = eng.check_fratricide_risk("IDENTIFIED", confidence=0.9)
        assert isinstance(risk, FratricideRisk)
        assert risk.risk < 0.05  # 0.01 * (1 - 0.9*0.8) = 0.01 * 0.28 ~ 0.003

    def test_unknown_high_risk(self):
        eng = _make_engine()
        risk = eng.check_fratricide_risk("UNKNOWN", confidence=0.1)
        assert risk.risk > 0.2  # 0.40 base, low confidence

    def test_classified_moderate_risk(self):
        eng = _make_engine()
        risk = eng.check_fratricide_risk("CLASSIFIED", confidence=0.5)
        # 0.07 * (1 - 0.5*0.8) = 0.07 * 0.6 = 0.042
        assert 0.01 < risk.risk < 0.2

    def test_detected_only_risk(self):
        eng = _make_engine()
        risk = eng.check_fratricide_risk("DETECTED", confidence=0.5)
        # 0.22 * 0.6 = 0.132
        assert risk.risk > 0.05


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------


class TestModifiers:
    """Urban, stress, and visibility multipliers."""

    def test_urban_multiplier(self):
        eng = _make_engine()
        base = eng.check_fratricide_risk("DETECTED", confidence=0.5)
        urban = eng.check_fratricide_risk("DETECTED", confidence=0.5, urban_terrain=True)
        assert urban.risk > base.risk
        assert "urban" in urban.modifiers

    def test_stress_multiplier(self):
        eng = _make_engine()
        calm = eng.check_fratricide_risk("DETECTED", confidence=0.5, stress_level=0.0)
        stressed = eng.check_fratricide_risk("DETECTED", confidence=0.5, stress_level=0.8)
        assert stressed.risk > calm.risk
        assert "stress" in stressed.modifiers

    def test_visibility_multiplier(self):
        eng = _make_engine()
        clear = eng.check_fratricide_risk("DETECTED", confidence=0.5, visibility=1.0)
        poor = eng.check_fratricide_risk("DETECTED", confidence=0.5, visibility=0.2)
        assert poor.risk > clear.risk
        assert "visibility" in poor.modifiers


# ---------------------------------------------------------------------------
# Resolve fratricide
# ---------------------------------------------------------------------------


class TestResolveFratricide:
    """Stochastic fratricide resolution."""

    def test_non_friendly_never_blocked(self):
        """Non-friendly target never triggers fratricide prevention."""
        eng = _make_engine()
        risk = eng.check_fratricide_risk("UNKNOWN", confidence=0.1, target_is_friendly=False)
        blocked = eng.resolve_fratricide(risk, "s1", "t1")
        assert blocked is False

    def test_friendly_with_high_risk_sometimes_blocked(self):
        """Friendly target with high risk should sometimes be blocked."""
        blocked_count = 0
        for i in range(50):
            e = FratricideEngine(EventBus(), _rng(seed=i))
            risk = e.check_fratricide_risk("UNKNOWN", confidence=0.1, target_is_friendly=True)
            if e.resolve_fratricide(risk, "s1", "t1"):
                blocked_count += 1
        assert blocked_count > 0


# ---------------------------------------------------------------------------
# Deconfliction
# ---------------------------------------------------------------------------


class TestDeconflict:
    """Identify friendlies in the danger zone."""

    def test_friendly_in_danger_zone(self):
        eng = _make_engine()
        friendlies = [("f1", Position(0.0, 500.0, 0.0))]
        at_risk = eng.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,  # north
            fire_range_m=1000.0,
            friendlies=friendlies,
        )
        assert "f1" in at_risk

    def test_friendly_outside_danger_zone(self):
        eng = _make_engine()
        friendlies = [("f1", Position(5000.0, 0.0, 0.0))]
        at_risk = eng.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,
            fire_range_m=1000.0,
            friendlies=friendlies,
        )
        assert "f1" not in at_risk

    def test_multiple_friendlies_mixed(self):
        """Some friendlies at risk, some not."""
        eng = _make_engine()
        friendlies = [
            ("f_near", Position(0.0, 400.0, 0.0)),  # In line of fire
            ("f_far", Position(3000.0, 3000.0, 0.0)),  # Way off
        ]
        at_risk = eng.deconflict(
            shooter_pos=Position(0.0, 0.0, 0.0),
            fire_direction_rad=0.0,
            fire_range_m=1000.0,
            friendlies=friendlies,
        )
        assert "f_near" in at_risk
        assert "f_far" not in at_risk


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestFratricideStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=77)
        state = eng.get_state()
        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        # RNG state should match
        assert eng._rng.random() == eng2._rng.random()
