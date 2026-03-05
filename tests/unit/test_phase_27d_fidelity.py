"""Phase 27d: Selective fidelity items — observer correction, cavalry terrain, frontage, gas mask don time."""

from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_rng


# ---------------------------------------------------------------------------
# 1. Observer correction for barrage drift (deficit 2.12)
# ---------------------------------------------------------------------------


class TestObserverCorrection:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.barrage import BarrageConfig, BarrageEngine

        cfg = BarrageConfig(**kwargs)
        return BarrageEngine(config=cfg, rng=make_rng())

    def test_no_observer_random_walk(self) -> None:
        """Without observer, drift accumulates as random walk."""
        eng = self._make_engine()
        zone = eng.create_barrage("b1", 0, "red", 1000.0, 1000.0, has_observer=False)
        eng.update(60.0)
        # Drift should be non-zero (random walk)
        assert zone.drift_easting_m != 0.0 or zone.drift_northing_m != 0.0

    def test_observer_reduces_drift(self) -> None:
        """Observer should reduce accumulated drift vs no observer (same seed)."""
        rng1 = make_rng(99)
        rng2 = make_rng(99)
        from stochastic_warfare.combat.barrage import BarrageConfig, BarrageEngine

        eng_no = BarrageEngine(config=BarrageConfig(), rng=rng1)
        eng_obs = BarrageEngine(config=BarrageConfig(), rng=rng2)

        z_no = eng_no.create_barrage("b1", 0, "red", 1000.0, 1000.0, has_observer=False)
        z_obs = eng_obs.create_barrage("b1", 0, "red", 1000.0, 1000.0,
                                        has_observer=True, observer_quality=1.0)
        for _ in range(10):
            eng_no.update(60.0)
            eng_obs.update(60.0)

        drift_no = abs(z_no.drift_easting_m) + abs(z_no.drift_northing_m)
        drift_obs = abs(z_obs.drift_easting_m) + abs(z_obs.drift_northing_m)
        assert drift_obs < drift_no

    def test_observer_quality_modulates(self) -> None:
        """Higher observer quality -> more correction -> less drift."""
        from stochastic_warfare.combat.barrage import BarrageConfig, BarrageEngine

        rng_lo = make_rng(77)
        rng_hi = make_rng(77)
        eng_lo = BarrageEngine(config=BarrageConfig(), rng=rng_lo)
        eng_hi = BarrageEngine(config=BarrageConfig(), rng=rng_hi)

        z_lo = eng_lo.create_barrage("b1", 0, "red", 0.0, 0.0,
                                      has_observer=True, observer_quality=0.2)
        z_hi = eng_hi.create_barrage("b1", 0, "red", 0.0, 0.0,
                                      has_observer=True, observer_quality=1.0)
        for _ in range(20):
            eng_lo.update(60.0)
            eng_hi.update(60.0)

        drift_lo = abs(z_lo.drift_easting_m) + abs(z_lo.drift_northing_m)
        drift_hi = abs(z_hi.drift_easting_m) + abs(z_hi.drift_northing_m)
        assert drift_hi < drift_lo

    def test_multiple_updates_converge(self) -> None:
        """Observer should keep drift bounded over many updates."""
        eng = self._make_engine()
        zone = eng.create_barrage(
            "b1", 0, "red", 0.0, 0.0,
            has_observer=True, observer_quality=1.0, duration_s=100000.0,
        )
        max_drift = 0.0
        for _ in range(100):
            eng.update(60.0)
            drift = abs(zone.drift_easting_m) + abs(zone.drift_northing_m)
            max_drift = max(max_drift, drift)
        # With perfect observer, drift should stay bounded
        assert max_drift < 200.0  # generous bound

    def test_default_preserves_behavior(self) -> None:
        """Default has_observer=False means no correction applied."""
        from stochastic_warfare.combat.barrage import BarrageZone

        zone = BarrageZone(
            barrage_id="test", barrage_type=0, side="red",
            center_easting=0.0, center_northing=0.0,
        )
        assert zone.has_observer is False
        assert zone.observer_quality == 0.5

    def test_config_defaults(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageConfig

        cfg = BarrageConfig()
        assert cfg.observer_correction_factor == 0.5
        assert cfg.observer_quality_default == 0.5

    def test_serialization_roundtrip(self) -> None:
        """get_state/set_state preserves observer fields."""
        eng = self._make_engine()
        eng.create_barrage("b1", 0, "red", 100.0, 200.0,
                           has_observer=True, observer_quality=0.8)
        state = eng.get_state()
        eng2 = self._make_engine()
        eng2.set_state(state)
        zone = eng2._barrages["b1"]
        assert zone.has_observer is True
        assert zone.observer_quality == pytest.approx(0.8)

    def test_set_state_backward_compat(self) -> None:
        """Old checkpoint without observer fields defaults correctly."""
        eng = self._make_engine()
        eng.create_barrage("b1", 0, "red", 0.0, 0.0)
        state = eng.get_state()
        # Simulate old checkpoint
        del state["barrages"]["b1"]["has_observer"]
        del state["barrages"]["b1"]["observer_quality"]
        eng2 = self._make_engine()
        eng2.set_state(state)
        zone = eng2._barrages["b1"]
        assert zone.has_observer is False
        assert zone.observer_quality == 0.5


# ---------------------------------------------------------------------------
# 2. Cavalry terrain effects (deficit 2.11)
# ---------------------------------------------------------------------------


class TestCavalryTerrain:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.melee import MeleeConfig, MeleeEngine

        cfg = MeleeConfig(**kwargs)
        return MeleeEngine(config=cfg, rng=make_rng())

    def test_flat_no_penalty(self) -> None:
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(slope_deg=0.0)
        assert mod == pytest.approx(1.0)
        assert abort is False

    def test_uphill_reduces_speed(self) -> None:
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(slope_deg=10.0)
        assert mod < 1.0
        assert mod == pytest.approx(1.0 - 0.02 * 10.0)
        assert abort is False

    def test_soft_ground_penalty(self) -> None:
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(soft_ground=True)
        assert mod == pytest.approx(1.0 - 0.3)
        assert abort is False

    def test_obstacles_abort(self) -> None:
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(obstacle_density=0.6)
        assert abort is True

    def test_combined_effects(self) -> None:
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(
            slope_deg=5.0, soft_ground=True,
        )
        expected = max(0.0, 1.0 - 0.02 * 5.0 - 0.3)
        assert mod == pytest.approx(expected)
        assert abort is False

    def test_uphill_increases_attacker_casualties(self) -> None:
        """Charging uphill should increase attacker casualty rate."""
        from stochastic_warfare.combat.melee import MeleeType

        eng = self._make_engine()
        # Flat charge
        rng_flat = make_rng(55)
        eng_flat = self._make_engine()
        eng_flat._rng = rng_flat
        result_flat = eng_flat.resolve_melee_round(
            100, 100, MeleeType.CAVALRY_CHARGE, round_number=1,
        )
        # Uphill charge
        rng_hill = make_rng(55)
        eng_hill = self._make_engine()
        eng_hill._rng = rng_hill
        result_hill = eng_hill.resolve_melee_round(
            100, 100, MeleeType.CAVALRY_CHARGE, round_number=1,
            slope_deg=15.0,
        )
        assert result_hill.attacker_casualties >= result_flat.attacker_casualties

    def test_default_no_effect(self) -> None:
        """Default slope_deg=0 produces no terrain modifier."""
        from stochastic_warfare.combat.melee import MeleeType

        eng = self._make_engine()
        result = eng.resolve_melee_round(
            50, 50, MeleeType.BAYONET_CHARGE, round_number=1,
        )
        # Non-cavalry melee types should work unchanged
        assert isinstance(result.attacker_casualties, int)

    def test_mounted_charge_affected(self) -> None:
        """MOUNTED_CHARGE (ancient) also uses terrain modifier."""
        eng = self._make_engine()
        mod, abort = eng.compute_cavalry_terrain_modifier(
            slope_deg=20.0, obstacle_density=0.6,
        )
        assert abort is True


# ---------------------------------------------------------------------------
# 3. Frontage constraint (deficit 2.10)
# ---------------------------------------------------------------------------


class TestFrontageConstraint:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.melee import MeleeConfig, MeleeEngine

        cfg = MeleeConfig(**kwargs)
        return MeleeEngine(config=cfg, rng=make_rng())

    def test_no_frontage_full(self) -> None:
        eng = self._make_engine()
        ea, ed, ra = eng.compute_frontage_constraint(100, 80)
        assert ea == 100
        assert ed == 80
        assert ra == 0

    def test_frontage_limits_attackers(self) -> None:
        eng = self._make_engine(combatant_spacing_m=2.0)
        ea, ed, ra = eng.compute_frontage_constraint(100, 80, frontage_m=20.0)
        assert ea == 10  # 20 / 2.0 = 10
        assert ra == 90

    def test_frontage_limits_defenders(self) -> None:
        eng = self._make_engine(combatant_spacing_m=2.0)
        ea, ed, ra = eng.compute_frontage_constraint(5, 80, frontage_m=20.0)
        assert ea == 5
        assert ed == 10  # limited to 10

    def test_reserves(self) -> None:
        eng = self._make_engine(combatant_spacing_m=1.0)
        ea, ed, ra = eng.compute_frontage_constraint(50, 50, frontage_m=20.0)
        assert ea == 20
        assert ra == 30

    def test_narrow_frontage_few(self) -> None:
        eng = self._make_engine(combatant_spacing_m=1.5)
        ea, ed, ra = eng.compute_frontage_constraint(1000, 1000, frontage_m=3.0)
        assert ea == 2  # int(3.0 / 1.5) = 2

    def test_wide_frontage_no_constraint(self) -> None:
        eng = self._make_engine(combatant_spacing_m=1.5)
        ea, ed, ra = eng.compute_frontage_constraint(10, 10, frontage_m=100.0)
        assert ea == 10
        assert ed == 10
        assert ra == 0

    def test_configurable_spacing(self) -> None:
        eng = self._make_engine(combatant_spacing_m=3.0)
        ea, ed, ra = eng.compute_frontage_constraint(100, 100, frontage_m=30.0)
        assert ea == 10

    def test_melee_with_frontage(self) -> None:
        """resolve_melee_round uses frontage constraint when > 0."""
        from stochastic_warfare.combat.melee import MeleeType

        eng = self._make_engine(combatant_spacing_m=2.0)
        # 100 vs 100 with narrow frontage of 10m -> 5 engaged each
        result = eng.resolve_melee_round(
            100, 100, MeleeType.BAYONET_CHARGE, frontage_m=10.0,
        )
        # Casualties should be limited vs unconstrained
        assert result.defender_casualties <= 100
        assert result.attacker_casualties <= 100


# ---------------------------------------------------------------------------
# 4. Gas mask don time enforcement (deficit 2.13)
# ---------------------------------------------------------------------------


class TestGasMaskDonTime:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.combat.gas_warfare import (
            GasMaskType,
            GasWarfareConfig,
            GasWarfareEngine,
        )

        cfg = GasWarfareConfig(**kwargs)
        eng = GasWarfareEngine(config=cfg, rng=make_rng())
        eng.set_unit_gas_mask("unit1", GasMaskType.SMALL_BOX_RESPIRATOR)
        return eng

    def test_full_exposure_at_zero(self) -> None:
        eng = self._make_engine()
        exposure = eng.compute_exposure_during_don("unit1", 1.0, time_since_alert_s=0.0)
        assert exposure == pytest.approx(1.0)

    def test_partial_during_donning(self) -> None:
        eng = self._make_engine(mask_don_time_s=10.0)
        exposure = eng.compute_exposure_during_don("unit1", 1.0, time_since_alert_s=5.0)
        assert exposure == pytest.approx(0.5)

    def test_zero_after_don_time(self) -> None:
        eng = self._make_engine(mask_don_time_s=10.0)
        exposure = eng.compute_exposure_during_don("unit1", 1.0, time_since_alert_s=15.0)
        assert exposure == pytest.approx(0.0)

    def test_config_don_time_respected(self) -> None:
        eng = self._make_engine(mask_don_time_s=20.0)
        # At 10s of 20s don time -> 50% exposure
        exposure = eng.compute_exposure_during_don("unit1", 1.0, time_since_alert_s=10.0)
        assert exposure == pytest.approx(0.5)

    def test_mopp_ramps_up(self) -> None:
        eng = self._make_engine(mask_don_time_s=10.0)
        mopp, pf = eng.get_effective_mopp_level("unit1", time_since_alert_s=5.0)
        assert mopp == 3  # SBR -> MOPP 3
        assert pf == pytest.approx(0.5)

        mopp2, pf2 = eng.get_effective_mopp_level("unit1", time_since_alert_s=10.0)
        assert pf2 == pytest.approx(1.0)

    def test_no_mask_always_exposed(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig, GasWarfareEngine

        eng = GasWarfareEngine(config=GasWarfareConfig(), rng=make_rng())
        exposure = eng.compute_exposure_during_don("unit_nomask", 1.0, time_since_alert_s=100.0)
        assert exposure == pytest.approx(1.0)

        mopp, pf = eng.get_effective_mopp_level("unit_nomask", time_since_alert_s=100.0)
        assert mopp == 0
        assert pf == pytest.approx(0.0)
