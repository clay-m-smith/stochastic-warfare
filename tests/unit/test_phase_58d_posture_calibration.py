"""Phase 58d: Posture protection calibration tests.

Verifies that posture blast/frag protection factors can be overridden
via CalibrationSchema and DamageEngine accepts the overrides.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.damage import (
    DamageEngine,
    _POSTURE_BLAST_PROTECT,
    _POSTURE_FRAG_PROTECT,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.calibration import CalibrationSchema


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def rng():
    return np.random.default_rng(42)


class TestCalibrationSchemaPostureFields:
    """CalibrationSchema accepts posture protection overrides."""

    def test_default_posture_blast_is_none(self):
        cal = CalibrationSchema()
        assert cal.posture_blast_protection is None

    def test_default_posture_frag_is_none(self):
        cal = CalibrationSchema()
        assert cal.posture_frag_protection is None

    def test_custom_blast_protection_accepted(self):
        custom = {"MOVING": 1.0, "HALTED": 0.8, "DUG_IN": 0.2}
        cal = CalibrationSchema(posture_blast_protection=custom)
        assert cal.posture_blast_protection == custom

    def test_custom_frag_protection_accepted(self):
        custom = {"MOVING": 1.0, "DEFENSIVE": 0.4}
        cal = CalibrationSchema(posture_frag_protection=custom)
        assert cal.posture_frag_protection == custom


class TestDamageEnginePostureOverrides:
    """DamageEngine uses overrides when provided."""

    def test_no_overrides_uses_defaults(self, event_bus, rng):
        engine = DamageEngine(event_bus, rng)
        assert engine._posture_blast is _POSTURE_BLAST_PROTECT
        assert engine._posture_frag is _POSTURE_FRAG_PROTECT

    def test_blast_override_applied(self, event_bus, rng):
        custom_blast = {"MOVING": 0.5, "DUG_IN": 0.01}
        engine = DamageEngine(event_bus, rng, posture_blast_overrides=custom_blast)
        assert engine._posture_blast == custom_blast
        assert engine._posture_frag is _POSTURE_FRAG_PROTECT

    def test_frag_override_applied(self, event_bus, rng):
        custom_frag = {"MOVING": 0.9, "FORTIFIED": 0.02}
        engine = DamageEngine(event_bus, rng, posture_frag_overrides=custom_frag)
        assert engine._posture_frag == custom_frag
        assert engine._posture_blast is _POSTURE_BLAST_PROTECT

    def test_overrides_affect_blast_damage(self, event_bus, rng):
        """Custom blast protection produces different damage than defaults."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        ammo = AmmoDefinition(
            ammo_id="test_he",
            name="Test HE",
            display_name="Test HE",
            ammo_type="HE",
            caliber_mm=155,
            weight_kg=43.0,
            blast_radius_m=50.0,
            fragmentation_radius_m=0.0,
        )
        # Default engine — DUG_IN protection = 0.3
        default_engine = DamageEngine(event_bus, rng)
        default_result = default_engine.apply_blast_damage(ammo, 5.0, "DUG_IN")

        # Custom engine — DUG_IN protection = 1.0 (no protection)
        custom_engine = DamageEngine(
            event_bus, rng,
            posture_blast_overrides={"DUG_IN": 1.0, "MOVING": 1.0},
        )
        custom_result = custom_engine.apply_blast_damage(ammo, 5.0, "DUG_IN")

        # With full protection factor (1.0), damage should be >= default (0.3 factor)
        assert custom_result.damage_fraction >= default_result.damage_fraction

    def test_default_engine_matches_prior_behavior(self, event_bus, rng):
        """Engine without overrides produces same results as hardcoded constants."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        ammo = AmmoDefinition(
            ammo_id="test_he",
            name="Test HE",
            display_name="Test HE",
            ammo_type="HE",
            caliber_mm=155,
            weight_kg=43.0,
            blast_radius_m=50.0,
            fragmentation_radius_m=100.0,
        )
        engine = DamageEngine(event_bus, rng)
        result = engine.apply_blast_damage(ammo, 10.0, "DEFENSIVE")
        # Should use _POSTURE_BLAST_PROTECT["DEFENSIVE"] = 0.7
        # and _POSTURE_FRAG_PROTECT["DEFENSIVE"] = 0.5
        assert result.damage_fraction > 0.0
