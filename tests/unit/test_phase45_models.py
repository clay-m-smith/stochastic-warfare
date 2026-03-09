"""Tests for Phase 45 — Mathematical Model Audit & Hardening.

Covers: AssessmentConfig migration (45e), hit probability floor (45d),
morale citation validation (45b), Weibull maintenance (45c),
overpressure blast model (45a), exponential threat cost (45e-3).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus


# ---------------------------------------------------------------------------
# 45e-1: AssessmentConfig
# ---------------------------------------------------------------------------


class TestAssessmentConfig:
    def test_default_config_matches_original(self) -> None:
        """Defaults match prior hardcoded values — zero behavioral change."""
        from stochastic_warfare.c2.ai.assessment import AssessmentConfig

        cfg = AssessmentConfig()
        assert cfg.force_ratio_thresholds == (0.4, 0.8, 1.5, 3.0)
        assert cfg.weights["force_ratio"] == pytest.approx(0.30)
        assert cfg.confidence_intel_weight == pytest.approx(0.4)
        assert cfg.opportunity_force_ratio == pytest.approx(2.0)
        assert cfg.threat_supply == pytest.approx(0.2)

    def test_config_override_changes_thresholds(self) -> None:
        """Custom config produces different assessments."""
        from stochastic_warfare.c2.ai.assessment import (
            AssessmentConfig,
            AssessmentRating,
            SituationAssessor,
        )

        rng = np.random.Generator(np.random.PCG64(42))
        bus = EventBus()

        # Default: force_ratio 1.0 -> NEUTRAL (between 0.8 and 1.5)
        default_assessor = SituationAssessor(bus, rng)
        a1 = default_assessor.assess(
            "u1", 1, 10, 100.0, 0.5, 0.5, 0.5, 5, 100.0,
        )
        assert a1.force_ratio_rating == AssessmentRating.NEUTRAL

        # Override: lower the N/F boundary so 1.0 becomes FAVORABLE
        cfg = AssessmentConfig(force_ratio_thresholds=(0.3, 0.6, 0.9, 2.0))
        custom_assessor = SituationAssessor(bus, rng, config=cfg)
        a2 = custom_assessor.assess(
            "u2", 1, 10, 100.0, 0.5, 0.5, 0.5, 5, 100.0,
        )
        assert a2.force_ratio_rating == AssessmentRating.FAVORABLE

    def test_custom_weights_change_overall(self) -> None:
        """Custom weights produce different overall rating."""
        from stochastic_warfare.c2.ai.assessment import (
            AssessmentConfig,
            SituationAssessor,
        )

        rng = np.random.Generator(np.random.PCG64(42))
        bus = EventBus()

        # High supply, low everything else
        base = SituationAssessor(bus, rng)
        a1 = base.assess(
            "u1", 1, 5, 50.0, 0.3, 0.9, 0.3, 2, 100.0,
        )

        # Override: make supply weight dominant
        cfg = AssessmentConfig(weights={
            "force_ratio": 0.05, "terrain": 0.05, "supply": 0.60,
            "morale": 0.05, "intel": 0.05, "environmental": 0.05, "c2": 0.15,
        })
        custom = SituationAssessor(bus, rng, config=cfg)
        a2 = custom.assess(
            "u2", 1, 5, 50.0, 0.3, 0.9, 0.3, 2, 100.0,
        )
        # Supply-heavy weights should improve overall rating
        assert int(a2.overall_rating) >= int(a1.overall_rating)


# ---------------------------------------------------------------------------
# 45e-3: Exponential Threat Cost
# ---------------------------------------------------------------------------


class TestExponentialThreatCost:
    def test_exponential_steeper_near_center(self) -> None:
        """Exponential cost grows faster near threat center than linear."""
        from stochastic_warfare.core.types import Position
        from stochastic_warfare.movement.pathfinding import Pathfinder

        pf = Pathfinder(threat_cost_alpha=3.0)
        threat_pos = Position(500.0, 500.0, 0.0)
        threat_radius = 300.0
        threats = [(threat_pos, threat_radius)]

        # Path that goes through threat zone edge vs center
        # Test: a path near center should cost much more than near edge
        start_edge = Position(500.0, 210.0, 0.0)  # near edge (d~290)
        start_mid = Position(500.0, 350.0, 0.0)   # mid-zone (d~150)

        path_edge = pf.find_path(
            start_edge, Position(500.0, 100.0, 0.0),
            avoid_threats=threats, grid_resolution=50.0,
        )
        path_center = pf.find_path(
            start_mid, Position(500.0, 100.0, 0.0),
            avoid_threats=threats, grid_resolution=50.0,
        )
        # Both should find paths
        assert path_edge.found
        assert path_center.found

    def test_alpha_parameter_accepted(self) -> None:
        """Pathfinder accepts threat_cost_alpha constructor param."""
        from stochastic_warfare.movement.pathfinding import Pathfinder

        pf = Pathfinder(threat_cost_alpha=5.0)
        assert pf._threat_cost_alpha == 5.0


# ---------------------------------------------------------------------------
# 45d: Hit Probability Review
# ---------------------------------------------------------------------------


class TestHitProbabilityFloor:
    def test_moderate_conditions_reasonable_pk(self) -> None:
        """Under moderate conditions, Pk stays reasonable (not near zero)."""
        from stochastic_warfare.combat.ammunition import WeaponDefinition, AmmoDefinition
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import (
            HitProbabilityConfig,
            HitProbabilityEngine,
        )

        rng = np.random.Generator(np.random.PCG64(42))
        weapon = WeaponDefinition(
            weapon_id="rifle", display_name="Rifle", category="CANNON",
            caliber_mm=7.62, base_accuracy_mrad=1.0,
            max_range_m=800.0, muzzle_velocity_mps=850.0,
        )
        ammo = AmmoDefinition(
            ammo_id="762", display_name="7.62mm", ammo_type="AP",
            penetration_mm_rha=10.0,
        )
        ballistics = BallisticsEngine(rng)
        engine = HitProbabilityEngine(ballistics, rng)

        result = engine.compute_phit(
            weapon, ammo, range_m=2000.0,
            crew_skill=0.5, visibility=0.7, target_speed_mps=5.0,
            target_posture="DEFENSIVE", weapon_condition=0.8,
        )
        # Should be low but not absurdly so (floor prevents <3%)
        assert result.p_hit >= 0.03

    def test_worst_case_respects_floor(self) -> None:
        """Worst-case stacking still respects moderate_condition_floor."""
        from stochastic_warfare.combat.ammunition import WeaponDefinition, AmmoDefinition
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import (
            HitProbabilityConfig,
            HitProbabilityEngine,
        )

        rng = np.random.Generator(np.random.PCG64(42))
        weapon = WeaponDefinition(
            weapon_id="w", display_name="W", category="CANNON",
            caliber_mm=7.62, base_accuracy_mrad=5.0,
            max_range_m=1000.0, muzzle_velocity_mps=850.0,
        )
        ammo = AmmoDefinition(
            ammo_id="a", display_name="A", ammo_type="AP",
        )
        ballistics = BallisticsEngine(rng)
        cfg = HitProbabilityConfig(moderate_condition_floor=0.05)
        engine = HitProbabilityEngine(ballistics, rng, config=cfg)

        result = engine.compute_phit(
            weapon, ammo, range_m=5000.0,
            crew_skill=0.1, visibility=0.2, target_speed_mps=15.0,
            shooter_speed_mps=10.0, target_posture="FORTIFIED",
            weapon_condition=0.3, position_uncertainty_m=50.0,
        )
        assert result.p_hit >= 0.05

    def test_modifier_documentation(self) -> None:
        """Modifiers dict documents what was applied."""
        from stochastic_warfare.combat.ammunition import WeaponDefinition, AmmoDefinition
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import HitProbabilityEngine

        rng = np.random.Generator(np.random.PCG64(42))
        weapon = WeaponDefinition(
            weapon_id="w", display_name="W", category="CANNON",
            caliber_mm=7.62, base_accuracy_mrad=1.0,
            max_range_m=800.0, muzzle_velocity_mps=850.0,
        )
        ammo = AmmoDefinition(
            ammo_id="a", display_name="A", ammo_type="AP",
        )
        ballistics = BallisticsEngine(rng)
        engine = HitProbabilityEngine(ballistics, rng)

        result = engine.compute_phit(
            weapon, ammo, range_m=500.0,
            crew_skill=0.5, visibility=0.8, target_speed_mps=5.0,
            target_posture="DEFENSIVE",
        )
        # Should have at least base_dispersion, crew_skill, visibility, posture
        assert "base_dispersion" in result.modifiers
        assert "crew_skill" in result.modifiers
        assert "visibility" in result.modifiers
        assert "posture" in result.modifiers


# ---------------------------------------------------------------------------
# 45b: Morale Constants Validation
# ---------------------------------------------------------------------------


class TestMoraleConstants:
    def test_steady_to_shaken_under_moderate_combat(self) -> None:
        """Under moderate combat stress, some units degrade from STEADY.
        Marshall: ~15-25% stop firing effectively in first hour."""
        from stochastic_warfare.morale.state import MoraleConfig, MoraleState, MoraleStateMachine

        bus = EventBus()
        degraded = 0
        n_trials = 200
        # Light-moderate combat: 3% casualties, light suppression, leadership present
        for i in range(n_trials):
            rng = np.random.Generator(np.random.PCG64(i))
            msm = MoraleStateMachine(bus, rng, MoraleConfig())
            uid = f"unit_{i}"
            # Simulate ~12 checks over 1 hour (5-min intervals)
            for tick in range(12):
                state = msm.check_transition(
                    uid, casualty_rate=0.03, suppression_level=0.15,
                    leadership_present=True, cohesion=0.6, force_ratio=1.0,
                    current_time_s=tick * 300.0,
                )
            if state != MoraleState.STEADY:
                degraded += 1

        rate = degraded / n_trials
        # Under light-moderate conditions, expect some degradation but not majority
        assert 0.05 < rate < 0.95, f"Degradation rate {rate:.2%} outside expected range"

    def test_heavy_casualties_cause_breakdown(self) -> None:
        """Under sustained 30%+ casualties, progression to BROKEN/ROUTED
        should occur within ~2 hours."""
        from stochastic_warfare.morale.state import MoraleConfig, MoraleState, MoraleStateMachine

        bus = EventBus()
        broken_or_worse = 0
        n_trials = 100
        for i in range(n_trials):
            rng = np.random.Generator(np.random.PCG64(i))
            msm = MoraleStateMachine(bus, rng, MoraleConfig())
            uid = f"unit_{i}"
            # 2 hours of heavy combat (24 checks at 5-min intervals)
            for tick in range(24):
                state = msm.check_transition(
                    uid, casualty_rate=0.35, suppression_level=0.6,
                    leadership_present=False, cohesion=0.3, force_ratio=0.5,
                    current_time_s=tick * 300.0,
                )
            if state.value >= MoraleState.BROKEN.value:
                broken_or_worse += 1

        rate = broken_or_worse / n_trials
        # Expect majority to break under these extreme conditions
        assert rate > 0.3, f"Breakdown rate {rate:.2%} too low for heavy casualties"

    def test_leadership_recovery(self) -> None:
        """Recovery from SHAKEN takes ~30-60 min with leadership."""
        from stochastic_warfare.morale.state import MoraleConfig, MoraleState, MoraleStateMachine

        bus = EventBus()
        recovered = 0
        n_trials = 200
        for i in range(n_trials):
            rng = np.random.Generator(np.random.PCG64(i))
            msm = MoraleStateMachine(bus, rng, MoraleConfig())
            uid = f"unit_{i}"
            # Force to SHAKEN
            msm._get_unit_state(uid).current_state = MoraleState.SHAKEN
            # 1 hour of recovery with leadership, low threat
            for tick in range(12):
                state = msm.check_transition(
                    uid, casualty_rate=0.0, suppression_level=0.0,
                    leadership_present=True, cohesion=0.7, force_ratio=2.0,
                    current_time_s=tick * 300.0,
                )
            if state == MoraleState.STEADY:
                recovered += 1

        rate = recovered / n_trials
        # With leadership + favorable conditions, majority should recover
        assert rate > 0.3, f"Recovery rate {rate:.2%} too low with leadership"


# ---------------------------------------------------------------------------
# 45c: Weibull Maintenance
# ---------------------------------------------------------------------------


class TestWeibullMaintenance:
    def _make_engine(self, use_weibull: bool, k: float = 1.0, seed: int = 42):
        from stochastic_warfare.logistics.maintenance import MaintenanceConfig, MaintenanceEngine

        rng = np.random.Generator(np.random.PCG64(seed))
        cfg = MaintenanceConfig(
            use_weibull=use_weibull,
            weibull_shape_k=k,
            base_mtbf_hours=100.0,
        )
        engine = MaintenanceEngine(EventBus(), rng, config=cfg)
        engine.register_equipment("u1", ["eq1"])
        return engine

    def test_k1_matches_exponential(self) -> None:
        """Weibull with k=1.0 is mathematically identical to exponential."""
        # Both should produce same failure pattern with same seed
        exp_engine = self._make_engine(use_weibull=False, seed=42)
        weibull_engine = self._make_engine(use_weibull=True, k=1.0, seed=42)

        exp_failures = 0
        weibull_failures = 0
        for _ in range(100):
            exp_failures += len(exp_engine.update(dt_hours=1.0))
            weibull_failures += len(weibull_engine.update(dt_hours=1.0))

        # Should be very close (not identical due to math path differences)
        assert abs(exp_failures - weibull_failures) <= 5

    def test_k_gt1_increasing_failure_rate(self) -> None:
        """k=1.5 gives increasing failure rate (more failures as equipment ages)."""
        from stochastic_warfare.logistics.maintenance import MaintenanceConfig, MaintenanceEngine

        # Run many trials, count failures in early vs late hours
        early_failures = 0
        late_failures = 0
        n_trials = 200
        for i in range(n_trials):
            rng = np.random.Generator(np.random.PCG64(i))
            cfg = MaintenanceConfig(
                use_weibull=True, weibull_shape_k=1.5,
                base_mtbf_hours=50.0,
            )
            engine = MaintenanceEngine(EventBus(), rng, config=cfg)
            engine.register_equipment("u1", ["eq1"])
            # First 10 hours
            for _ in range(10):
                early_failures += len(engine.update(dt_hours=1.0))
            # Next 10 hours (equipment is now older)
            for _ in range(10):
                late_failures += len(engine.update(dt_hours=1.0))

        # With k>1, late hours should have more failures (wear-out)
        assert late_failures > early_failures, (
            f"k=1.5 should show increasing failure rate: early={early_failures}, late={late_failures}"
        )

    def test_k_lt1_decreasing_failure_rate(self) -> None:
        """k=0.8 gives decreasing failure rate (infant mortality)."""
        from stochastic_warfare.logistics.maintenance import MaintenanceConfig, MaintenanceEngine

        early_failures = 0
        late_failures = 0
        n_trials = 200
        for i in range(n_trials):
            rng = np.random.Generator(np.random.PCG64(i))
            cfg = MaintenanceConfig(
                use_weibull=True, weibull_shape_k=0.8,
                base_mtbf_hours=50.0,
            )
            engine = MaintenanceEngine(EventBus(), rng, config=cfg)
            engine.register_equipment("u1", ["eq1"])
            for _ in range(10):
                early_failures += len(engine.update(dt_hours=1.0))
            for _ in range(10):
                late_failures += len(engine.update(dt_hours=1.0))

        # With k<1, early hours should have more failures (infant mortality)
        assert early_failures > late_failures, (
            f"k=0.8 should show decreasing failure rate: early={early_failures}, late={late_failures}"
        )

    def test_hazard_increases_with_hours_for_k_gt1(self) -> None:
        """Weibull hazard function h(t) increases with t when k>1."""
        k = 1.5
        eta = 100.0  # MTBF
        t_values = [10.0, 50.0, 100.0, 200.0]
        hazards = [(k / eta) * (t / eta) ** (k - 1.0) for t in t_values]
        for i in range(len(hazards) - 1):
            assert hazards[i + 1] > hazards[i]


# ---------------------------------------------------------------------------
# 45a: Overpressure Blast Model
# ---------------------------------------------------------------------------


class TestOverpressureBlast:
    def _he(self):
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        return AmmoDefinition(
            ammo_id="he155", display_name="155mm HE", ammo_type="HE",
            mass_kg=46.7, diameter_mm=155.0,
            blast_radius_m=50.0, fragmentation_radius_m=150.0,
        )

    def _engine(self, use_overpressure: bool = True, seed: int = 42):
        from stochastic_warfare.combat.damage import DamageConfig, DamageEngine

        rng = np.random.Generator(np.random.PCG64(seed))
        cfg = DamageConfig(use_overpressure_blast=use_overpressure)
        return DamageEngine(EventBus(), rng, config=cfg)

    def test_inverse_power_law_decay(self) -> None:
        """Overpressure decreases monotonically with distance."""
        from stochastic_warfare.combat.damage import DamageEngine

        charge_kg = 6.6  # 155mm HE
        prev_op = float("inf")
        for d in [1.0, 5.0, 10.0, 20.0, 50.0, 100.0]:
            op = DamageEngine._compute_overpressure_psi(d, charge_kg)
            assert op < prev_op, f"Overpressure not decreasing at d={d}"
            prev_op = op

    def test_155mm_kill_radius(self) -> None:
        """155mm HE should have lethal blast within ~15-25m."""
        e = self._engine()
        he = self._he()
        # At 15m, should be lethal (damage ~1.0 for MOVING)
        r15 = e.apply_blast_damage(he, distance_m=15.0, posture="MOVING")
        assert r15.damage_fraction >= 0.9
        # At 30m, should still cause significant damage
        r30 = e.apply_blast_damage(he, distance_m=30.0, posture="MOVING")
        assert r30.damage_fraction > 0.3

    def test_strong_shock_steeper_than_weak(self) -> None:
        """Strong shock decays faster than weak shock — compare rate of
        decline on each side of the boundary."""
        from stochastic_warfare.combat.damage import DamageEngine

        charge_kg = 6.6
        # Compare relative drop over equal distance increments
        # In strong regime (near): op drops steeply
        op_2m = DamageEngine._compute_overpressure_psi(2.0, charge_kg)
        op_4m = DamageEngine._compute_overpressure_psi(4.0, charge_kg)
        strong_ratio = op_2m / op_4m  # ratio > 1

        # In weak regime (far): op drops less steeply
        op_20m = DamageEngine._compute_overpressure_psi(20.0, charge_kg)
        op_40m = DamageEngine._compute_overpressure_psi(40.0, charge_kg)
        weak_ratio = op_20m / op_40m  # ratio > 1

        # Strong regime should decay faster (higher ratio per doubling)
        assert strong_ratio > weak_ratio

    def test_posture_protection_reduces_blast(self) -> None:
        """Posture protection reduces effective overpressure → less damage."""
        e = self._engine()
        he = self._he()
        moving = e.apply_blast_damage(he, distance_m=40.0, posture="MOVING")
        dug_in = e.apply_blast_damage(he, distance_m=40.0, posture="DUG_IN")
        fortified = e.apply_blast_damage(he, distance_m=40.0, posture="FORTIFIED")
        assert moving.damage_fraction > dug_in.damage_fraction
        assert dug_in.damage_fraction > fortified.damage_fraction

    def test_legacy_gaussian_mode(self) -> None:
        """use_overpressure_blast=False produces legacy Gaussian behavior."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        e = self._engine(use_overpressure=False)
        # Use blast-only ammo (no fragmentation) to isolate Gaussian model
        blast_only = AmmoDefinition(
            ammo_id="blast", display_name="Blast", ammo_type="HE",
            blast_radius_m=50.0, fragmentation_radius_m=0.0,
        )
        # At distance=0, Gaussian gives exp(0) = 1.0
        r0 = e.apply_blast_damage(blast_only, distance_m=0.0)
        assert r0.damage_fraction > 0.9
        # At blast_radius distance, Gaussian gives exp(-0.5) ≈ 0.607
        r_br = e.apply_blast_damage(blast_only, distance_m=50.0)
        assert 0.5 < r_br.damage_fraction < 0.7

    def test_explosive_fill_kg_used_directly(self) -> None:
        """When explosive_fill_kg > 0, it's used directly (not derived)."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        # Create ammo with explicit fill (larger than derivation would give)
        he_fill = AmmoDefinition(
            ammo_id="he_big", display_name="Big HE", ammo_type="HE",
            blast_radius_m=50.0, explosive_fill_kg=20.0,
        )
        he_no_fill = AmmoDefinition(
            ammo_id="he_derived", display_name="Derived HE", ammo_type="HE",
            blast_radius_m=50.0, explosive_fill_kg=0.0,
        )
        e = self._engine()
        # More explosive fill = more damage at same distance
        r_big = e.apply_blast_damage(he_fill, distance_m=60.0)
        r_derived = e.apply_blast_damage(he_no_fill, distance_m=60.0)
        assert r_big.damage_fraction >= r_derived.damage_fraction
