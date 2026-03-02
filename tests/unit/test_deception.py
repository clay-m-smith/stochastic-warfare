"""Tests for detection/deception.py — decoys, camouflage, feints."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.deception import (
    Decoy,
    DeceptionEngine,
    DeceptionType,
)
from stochastic_warfare.detection.signatures import (
    EMSignature,
    SignatureProfile,
    VisualSignature,
)


# ── helpers ──────────────────────────────────────────────────────────


def _engine(seed: int = 42) -> DeceptionEngine:
    return DeceptionEngine(rng=np.random.Generator(np.random.PCG64(seed)))


# ── DeceptionType enum ────────────────────────────────────────────────


class TestDeceptionType:
    def test_values(self) -> None:
        assert DeceptionType.DECOY_VISUAL == 0
        assert DeceptionType.DECOY_THERMAL == 1
        assert DeceptionType.DECOY_RADAR == 2
        assert DeceptionType.DECOY_ACOUSTIC == 3
        assert DeceptionType.FEINT == 4
        assert DeceptionType.FALSE_EMISSIONS == 5
        assert DeceptionType.CAMOUFLAGE == 6


# ── Decoy deployment ─────────────────────────────────────────────────


class TestDeployDecoy:
    def test_basic(self) -> None:
        engine = _engine()
        decoy = engine.deploy_decoy(Position(1000.0, 2000.0, 0.0), DeceptionType.DECOY_RADAR)
        assert decoy.active is True
        assert decoy.effectiveness == 1.0
        assert decoy.decoy_id.startswith("decoy-")

    def test_custom_signature(self) -> None:
        engine = _engine()
        sig = SignatureProfile(
            profile_id="custom", unit_type="decoy",
            visual=VisualSignature(cross_section_m2=20.0),
        )
        decoy = engine.deploy_decoy(Position(0.0, 0.0, 0.0), DeceptionType.DECOY_VISUAL, signature=sig)
        assert decoy.signature.visual.cross_section_m2 == 20.0

    def test_multiple_decoys(self) -> None:
        engine = _engine()
        d1 = engine.deploy_decoy(Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR)
        d2 = engine.deploy_decoy(Position(1000.0, 0.0, 0.0), DeceptionType.DECOY_THERMAL)
        assert d1.decoy_id != d2.decoy_id
        assert len(engine.active_decoys()) == 2


# ── Decoy degradation ────────────────────────────────────────────────


class TestUpdateDecoys:
    def test_effectiveness_degrades(self) -> None:
        engine = _engine()
        decoy = engine.deploy_decoy(
            Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR,
            degradation_rate=0.1,
        )
        engine.update_decoys(dt=5.0)
        assert decoy.effectiveness == pytest.approx(0.5)

    def test_deactivates_at_zero(self) -> None:
        engine = _engine()
        decoy = engine.deploy_decoy(
            Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR,
            degradation_rate=0.1,
        )
        engine.update_decoys(dt=20.0)
        assert decoy.effectiveness == 0.0
        assert decoy.active is False

    def test_inactive_not_updated(self) -> None:
        engine = _engine()
        decoy = engine.deploy_decoy(Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR)
        decoy.active = False
        decoy.effectiveness = 0.5
        engine.update_decoys(dt=10.0)
        assert decoy.effectiveness == 0.5  # unchanged

    def test_active_decoys_filter(self) -> None:
        engine = _engine()
        d1 = engine.deploy_decoy(Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR)
        d2 = engine.deploy_decoy(Position(1000.0, 0.0, 0.0), DeceptionType.DECOY_THERMAL)
        d2.active = False
        active = engine.active_decoys()
        assert len(active) == 1
        assert active[0].decoy_id == d1.decoy_id


# ── Remove decoy ──────────────────────────────────────────────────────


class TestRemoveDecoy:
    def test_remove(self) -> None:
        engine = _engine()
        decoy = engine.deploy_decoy(Position(0.0, 0.0, 0.0), DeceptionType.DECOY_RADAR)
        engine.remove_decoy(decoy.decoy_id)
        assert len(engine.active_decoys()) == 0


# ── Camouflage modifier ──────────────────────────────────────────────


class TestCamouflageModifier:
    def test_moving_no_prep(self) -> None:
        mod = DeceptionEngine.camouflage_modifier(posture=0)
        assert mod == pytest.approx(1.0)

    def test_fortified(self) -> None:
        mod = DeceptionEngine.camouflage_modifier(posture=4)
        assert mod < 0.5

    def test_preparation_time(self) -> None:
        mod_0h = DeceptionEngine.camouflage_modifier(posture=2, preparation_time_hours=0.0)
        mod_4h = DeceptionEngine.camouflage_modifier(posture=2, preparation_time_hours=4.0)
        assert mod_4h < mod_0h

    def test_terrain_concealment(self) -> None:
        mod_open = DeceptionEngine.camouflage_modifier(terrain_concealment=0.0)
        mod_forest = DeceptionEngine.camouflage_modifier(terrain_concealment=0.8)
        assert mod_forest < mod_open

    def test_bounded(self) -> None:
        mod = DeceptionEngine.camouflage_modifier(posture=4, preparation_time_hours=10.0, terrain_concealment=1.0)
        assert 0.3 <= mod <= 1.0


# ── False emission ────────────────────────────────────────────────────


class TestFalseEmission:
    def test_creation(self) -> None:
        engine = _engine()
        em = engine.false_emission(Position(0.0, 0.0, 0.0), 9.4, 60.0)
        assert em.emitting is True
        assert em.power_dbm == 60.0
        assert em.frequency_ghz == 9.4


# ── Feint assessment ──────────────────────────────────────────────────


class TestFeintAssessment:
    def test_small_force_low(self) -> None:
        score = DeceptionEngine.feint_assessment(1)
        assert score < 0.5

    def test_large_force_higher(self) -> None:
        score_1 = DeceptionEngine.feint_assessment(1)
        score_10 = DeceptionEngine.feint_assessment(10)
        assert score_10 > score_1

    def test_movement_helps(self) -> None:
        score_static = DeceptionEngine.feint_assessment(5, average_speed=0.0)
        score_moving = DeceptionEngine.feint_assessment(5, average_speed=10.0)
        assert score_moving > score_static

    def test_bounded(self) -> None:
        score = DeceptionEngine.feint_assessment(100, average_speed=100.0)
        assert score <= 1.0


# ── Decoy state round-trip ───────────────────────────────────────────


class TestDecoyState:
    def test_roundtrip(self) -> None:
        decoy = Decoy(
            decoy_id="d-1", position=Position(100.0, 200.0, 0.0),
            deception_type=DeceptionType.DECOY_RADAR,
            signature=SignatureProfile(profile_id="d-1", unit_type="decoy"),
            effectiveness=0.75, active=True,
        )
        state = decoy.get_state()
        decoy2 = Decoy(
            decoy_id="", position=Position(0, 0, 0),
            deception_type=DeceptionType.DECOY_VISUAL,
            signature=SignatureProfile(profile_id="", unit_type=""),
        )
        decoy2.set_state(state)
        assert decoy2.decoy_id == "d-1"
        assert decoy2.effectiveness == 0.75
        assert decoy2.position == Position(100.0, 200.0, 0.0)


# ── Engine state round-trip ───────────────────────────────────────────


class TestEngineState:
    def test_roundtrip(self) -> None:
        engine = _engine(seed=42)
        engine.deploy_decoy(Position(100.0, 200.0, 0.0), DeceptionType.DECOY_RADAR)
        state = engine.get_state()

        engine2 = _engine(seed=0)
        engine2.set_state(state)
        assert len(engine2.active_decoys()) == 1
        assert engine2._decoy_counter == 1
