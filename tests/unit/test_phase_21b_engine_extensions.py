"""Phase 21b tests — WW1 engine extensions.

Tests for:
- TrenchSystemEngine (spatial queries, cover, movement, bombardment)
- BarrageEngine (standing, creeping, suppression, friendly fire)
- GasWarfareEngine (cylinder release, gas bombardment, mask mapping)
- Cross-engine integration
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.conftest import make_rng


# ---------------------------------------------------------------------------
# TrenchSystemEngine tests
# ---------------------------------------------------------------------------

class TestTrenchConfig:
    """TrenchConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchConfig
        cfg = TrenchConfig()
        assert cfg.cover_fire_trench == 0.85
        assert cfg.movement_along == 0.5

    def test_custom_values(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchConfig
        cfg = TrenchConfig(cover_fire_trench=0.90, movement_crossing=0.1)
        assert cfg.cover_fire_trench == 0.90
        assert cfg.movement_crossing == 0.1


class TestTrenchSegment:
    """TrenchSegment validation."""

    def test_create_segment(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchSegment, TrenchType
        seg = TrenchSegment(
            trench_id="t1",
            trench_type=TrenchType.FIRE_TRENCH,
            side="british",
            points=[[0, 0], [100, 0]],
        )
        assert seg.trench_id == "t1"
        assert seg.condition == 1.0

    def test_wire_and_dugout(self) -> None:
        from stochastic_warfare.terrain.trenches import TrenchSegment, TrenchType
        seg = TrenchSegment(
            trench_id="t2",
            trench_type=TrenchType.FIRE_TRENCH,
            side="german",
            points=[[0, 0], [50, 0]],
            has_wire=True,
            has_dugout=True,
        )
        assert seg.has_wire
        assert seg.has_dugout


class TestTrenchSystemEngine:
    """TrenchSystemEngine spatial queries."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.terrain.trenches import (
            TrenchConfig,
            TrenchSegment,
            TrenchSystemEngine,
            TrenchType,
        )
        eng = TrenchSystemEngine(TrenchConfig())
        # British fire trench running east-west at y=100
        eng.add_trench(TrenchSegment(
            trench_id="brit_fire",
            trench_type=TrenchType.FIRE_TRENCH,
            side="british",
            points=[[0, 100], [500, 100]],
            has_wire=True,
            has_dugout=True,
        ))
        # British support trench at y=200
        eng.add_trench(TrenchSegment(
            trench_id="brit_support",
            trench_type=TrenchType.SUPPORT_TRENCH,
            side="british",
            points=[[0, 200], [500, 200]],
        ))
        # Communication trench connecting
        eng.add_trench(TrenchSegment(
            trench_id="brit_comm",
            trench_type=TrenchType.COMMUNICATION_TRENCH,
            side="british",
            points=[[250, 100], [250, 200]],
        ))
        # German fire trench at y=500
        eng.add_trench(TrenchSegment(
            trench_id="ger_fire",
            trench_type=TrenchType.FIRE_TRENCH,
            side="german",
            points=[[0, 500], [500, 500]],
            has_wire=True,
            has_dugout=True,
        ))
        # No man's land
        eng.add_no_mans_land((0, 100), (500, 100), width_m=400.0)
        return eng

    def test_query_in_fire_trench(self, engine) -> None:
        result = engine.query_trench(250.0, 100.0)
        assert result.in_trench is True
        assert result.trench_id == "brit_fire"

    def test_query_outside_trench(self, engine) -> None:
        result = engine.query_trench(250.0, 50.0)
        assert result.in_trench is False

    def test_fire_trench_cover(self, engine) -> None:
        cover = engine.cover_value_at(250.0, 100.0)
        assert cover == pytest.approx(0.85)  # fire trench

    def test_support_trench_cover(self, engine) -> None:
        # Query at x=100 to avoid overlap with comm trench at x=250
        cover = engine.cover_value_at(100.0, 200.0)
        assert cover == pytest.approx(0.70)

    def test_comm_trench_cover(self, engine) -> None:
        cover = engine.cover_value_at(250.0, 150.0)
        assert cover == pytest.approx(0.50)

    def test_no_cover_outside(self, engine) -> None:
        cover = engine.cover_value_at(250.0, 50.0)
        assert cover == 0.0

    def test_movement_along_trench(self, engine) -> None:
        """Moving east along an east-west trench → along factor."""
        factor = engine.movement_factor_at(250.0, 100.0, heading_deg=90.0)
        assert factor == pytest.approx(0.5)

    def test_movement_crossing_trench(self, engine) -> None:
        """Moving north across an east-west trench → crossing factor."""
        factor = engine.movement_factor_at(250.0, 100.0, heading_deg=0.0)
        assert factor == pytest.approx(0.3)

    def test_movement_no_mans_land(self, engine) -> None:
        """Movement in no-man's-land is very slow."""
        factor = engine.movement_factor_at(250.0, 300.0, heading_deg=0.0)
        assert factor == pytest.approx(0.2)

    def test_movement_normal_terrain(self, engine) -> None:
        """Movement outside trenches and NML is normal."""
        factor = engine.movement_factor_at(250.0, 700.0, heading_deg=0.0)
        assert factor == pytest.approx(1.0)

    def test_is_no_mans_land(self, engine) -> None:
        assert engine.is_no_mans_land(250.0, 250.0) is True

    def test_not_no_mans_land(self, engine) -> None:
        assert engine.is_no_mans_land(250.0, 700.0) is False

    def test_bombardment_degrades_condition(self, engine) -> None:
        engine.apply_bombardment(250.0, 100.0, 50.0, intensity=1.0)
        seg = engine._segments["brit_fire"]
        assert seg.condition < 1.0

    def test_bombardment_returns_affected(self, engine) -> None:
        affected = engine.apply_bombardment(250.0, 100.0, 50.0, intensity=0.5)
        assert "brit_fire" in affected

    def test_damaged_trench_reduced_cover(self, engine) -> None:
        # Damage the trench
        engine._segments["brit_fire"].condition = 0.5
        cover = engine.cover_value_at(250.0, 100.0)
        assert cover == pytest.approx(0.85 * 0.5)

    def test_wire_and_dugout_query(self, engine) -> None:
        result = engine.query_trench(250.0, 100.0)
        assert result.has_wire is True
        assert result.has_dugout is True

    def test_query_correct_side(self, engine) -> None:
        result = engine.query_trench(250.0, 500.0)
        assert result.side == "german"

    def test_state_roundtrip(self, engine) -> None:
        state = engine.get_state()
        from stochastic_warfare.terrain.trenches import TrenchSystemEngine
        eng2 = TrenchSystemEngine()
        eng2.set_state(state)
        assert "brit_fire" in eng2._segments
        assert eng2.cover_value_at(250.0, 100.0) == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# BarrageEngine tests
# ---------------------------------------------------------------------------


class TestBarrageConfig:
    """BarrageConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageConfig
        cfg = BarrageConfig()
        assert cfg.creeping_advance_rate_mps == pytest.approx(0.833)

    def test_custom_density(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageConfig
        cfg = BarrageConfig(casualty_rate_per_round_hectare=0.001)
        assert cfg.casualty_rate_per_round_hectare == 0.001

    def test_friendly_fire_zone(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageConfig
        cfg = BarrageConfig()
        assert cfg.friendly_fire_zone_m == 100.0


class TestBarrageEngine:
    """BarrageEngine mechanics."""

    @pytest.fixture()
    def engine(self):
        from stochastic_warfare.combat.barrage import BarrageConfig, BarrageEngine
        return BarrageEngine(
            config=BarrageConfig(),
            rng=make_rng(42),
        )

    def test_create_standing_barrage(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        zone = engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, fire_density=200.0,
        )
        assert zone.active is True
        assert zone.advance_rate_mps == 0.0

    def test_create_creeping_barrage(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        zone = engine.create_barrage(
            "b2", BarrageType.CREEPING, "british",
            500.0, 500.0, heading_deg=0.0,
        )
        assert zone.advance_rate_mps > 0

    def test_standing_barrage_effects(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, width_m=200.0, depth_m=100.0,
            fire_density=200.0,
        )
        effects = engine.compute_effects(500.0, 500.0)
        assert effects["suppression_p"] > 0
        assert effects["casualty_p"] > 0

    def test_no_effects_outside_zone(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, width_m=200.0, depth_m=100.0,
        )
        effects = engine.compute_effects(0.0, 0.0)
        assert effects["suppression_p"] == 0.0
        assert effects["casualty_p"] == 0.0

    def test_dugout_reduces_casualties(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, fire_density=200.0,
        )
        open_effects = engine.compute_effects(500.0, 500.0, in_dugout=False)
        dugout_effects = engine.compute_effects(500.0, 500.0, in_dugout=True)
        assert dugout_effects["casualty_p"] < open_effects["casualty_p"]

    def test_creeping_advance(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        zone = engine.create_barrage(
            "b1", BarrageType.CREEPING, "british",
            500.0, 500.0, heading_deg=0.0,  # advancing north
        )
        initial_n = zone.center_northing
        engine.update(60.0)  # 1 minute
        # Should advance ~50m north
        assert zone.center_northing > initial_n
        assert zone.center_northing == pytest.approx(
            initial_n + 0.833 * 60.0, abs=5.0,
        )

    def test_barrage_expiry(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        zone = engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, duration_s=100.0,
        )
        engine.update(101.0)
        assert zone.active is False

    def test_drift_accumulates(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        zone = engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0,
        )
        engine.update(600.0)  # 10 minutes
        # Drift should be non-zero (stochastic, but extremely unlikely to be 0)
        assert zone.drift_easting_m != 0.0 or zone.drift_northing_m != 0.0

    def test_friendly_fire_risk(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0,
        )
        ff_risk = engine.check_friendly_fire(500.0, 500.0, "british")
        assert ff_risk > 0

    def test_no_friendly_fire_other_side(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0,
        )
        ff_risk = engine.check_friendly_fire(500.0, 500.0, "german")
        assert ff_risk == 0.0

    def test_no_friendly_fire_far_away(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0,
        )
        ff_risk = engine.check_friendly_fire(0.0, 0.0, "british")
        assert ff_risk == 0.0

    def test_is_safe_to_advance_behind(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.CREEPING, "british",
            500.0, 500.0, heading_deg=0.0,
        )
        # Position well behind (south of) barrage center
        assert engine.is_safe_to_advance(500.0, 300.0, "b1") is True

    def test_not_safe_to_advance_at_barrage(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage(
            "b1", BarrageType.CREEPING, "british",
            500.0, 500.0, heading_deg=0.0,
        )
        # Position at same location as barrage
        assert engine.is_safe_to_advance(500.0, 500.0, "b1") is False

    def test_active_barrages(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        engine.create_barrage("b1", BarrageType.STANDING, "british", 100, 100)
        engine.create_barrage("b2", BarrageType.STANDING, "british", 200, 200)
        assert len(engine.active_barrages) == 2

    def test_trench_degradation(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageType
        from stochastic_warfare.terrain.trenches import (
            TrenchConfig, TrenchSegment, TrenchSystemEngine, TrenchType,
        )
        trench_eng = TrenchSystemEngine(TrenchConfig())
        trench_eng.add_trench(TrenchSegment(
            trench_id="t1",
            trench_type=TrenchType.FIRE_TRENCH,
            side="german",
            points=[[400, 500], [600, 500]],
        ))
        engine.create_barrage(
            "b1", BarrageType.STANDING, "british",
            500.0, 500.0, fire_density=500.0,
        )
        engine.update(60.0, trench_engine=trench_eng)
        assert trench_eng._segments["t1"].condition < 1.0

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        engine.create_barrage("b1", BarrageType.STANDING, "british", 100, 100)
        state = engine.get_state()
        eng2 = BarrageEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert "b1" in eng2._barrages
        assert eng2._barrages["b1"].active is True


# ---------------------------------------------------------------------------
# GasWarfareEngine tests
# ---------------------------------------------------------------------------


class TestGasWarfareConfig:
    """GasWarfareConfig validation."""

    def test_default_values(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig
        cfg = GasWarfareConfig()
        assert cfg.cylinder_release_duration_s == 300.0

    def test_custom_shell_mass(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareConfig
        cfg = GasWarfareConfig(shell_gas_mass_kg=2.0)
        assert cfg.shell_gas_mass_kg == 2.0


class TestGasWarfareEnums:
    """Gas warfare enums."""

    def test_delivery_methods(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasDeliveryMethod
        assert GasDeliveryMethod.CYLINDER_RELEASE == 0
        assert GasDeliveryMethod.ARTILLERY_SHELL == 1
        assert GasDeliveryMethod.PROJECTOR == 2

    def test_mask_types(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        assert GasMaskType.NONE == 0
        assert GasMaskType.SMALL_BOX_RESPIRATOR == 3


class TestGasWarfareEngine:
    """GasWarfareEngine delivery and mask mapping."""

    @pytest.fixture()
    def mock_cbrn(self):
        """Mock CBRN engine."""
        cbrn = MagicMock()
        cbrn.release_agent = MagicMock(side_effect=lambda **kw: f"puff_{id(kw)}")
        return cbrn

    @pytest.fixture()
    def engine(self, mock_cbrn):
        from stochastic_warfare.combat.gas_warfare import (
            GasWarfareConfig,
            GasWarfareEngine,
        )
        return GasWarfareEngine(
            config=GasWarfareConfig(),
            cbrn_engine=mock_cbrn,
            rng=make_rng(42),
        )

    def test_wind_favorable(self, engine) -> None:
        assert engine.check_wind_favorable(3.0, 180.0, 0.0) is True

    def test_wind_too_calm(self, engine) -> None:
        assert engine.check_wind_favorable(0.5, 180.0, 0.0) is False

    def test_wind_too_fast(self, engine) -> None:
        assert engine.check_wind_favorable(10.0, 180.0, 0.0) is False

    def test_wind_wrong_direction(self, engine) -> None:
        # Wind blows from north (0°), gas goes south (180°), target is north (0°)
        assert engine.check_wind_favorable(3.0, 0.0, 0.0) is False

    def test_cylinder_release_creates_puffs(self, engine, mock_cbrn) -> None:
        puffs = engine.execute_cylinder_release(
            "chlorine", (0, 0), (100, 0), num_release_points=5,
        )
        assert len(puffs) == 5
        assert mock_cbrn.release_agent.call_count == 5

    def test_cylinder_release_mass(self, engine, mock_cbrn) -> None:
        engine.execute_cylinder_release(
            "chlorine", (0, 0), (100, 0), num_release_points=1,
        )
        call_kw = mock_cbrn.release_agent.call_args
        # 100m front * 20 kg/m = 2000 kg total for 1 point
        assert call_kw.kwargs["quantity_kg"] == pytest.approx(2000.0)

    def test_gas_bombardment(self, engine, mock_cbrn) -> None:
        puffs = engine.execute_gas_bombardment(
            "phosgene", 500.0, 500.0, num_shells=10,
        )
        assert len(puffs) == 10
        assert mock_cbrn.release_agent.call_count == 10

    def test_gas_bombardment_shell_mass(self, engine, mock_cbrn) -> None:
        engine.execute_gas_bombardment(
            "phosgene", 500.0, 500.0, num_shells=1,
        )
        call_kw = mock_cbrn.release_agent.call_args
        assert call_kw.kwargs["quantity_kg"] == pytest.approx(1.5)

    def test_projector_salvo(self, engine, mock_cbrn) -> None:
        puffs = engine.execute_projector_salvo(
            "phosgene", 500.0, 500.0, num_projectors=20,
        )
        assert len(puffs) == 20

    def test_projector_mass(self, engine, mock_cbrn) -> None:
        engine.execute_projector_salvo(
            "phosgene", 500.0, 500.0, num_projectors=1,
        )
        call_kw = mock_cbrn.release_agent.call_args
        assert call_kw.kwargs["quantity_kg"] == pytest.approx(14.0)

    def test_mask_none_to_mopp_0(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        mopp = engine.set_unit_gas_mask("unit_1", GasMaskType.NONE)
        assert mopp == 0

    def test_mask_cloth_to_mopp_1(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        mopp = engine.set_unit_gas_mask("unit_1", GasMaskType.IMPROVISED_CLOTH)
        assert mopp == 1

    def test_mask_ph_to_mopp_2(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        mopp = engine.set_unit_gas_mask("unit_1", GasMaskType.PH_HELMET)
        assert mopp == 2

    def test_mask_sbr_to_mopp_3(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        mopp = engine.set_unit_gas_mask("unit_1", GasMaskType.SMALL_BOX_RESPIRATOR)
        assert mopp == 3

    def test_get_mopp_level_default(self, engine) -> None:
        assert engine.get_unit_mopp_level("unknown") == 0

    def test_get_mopp_level_after_set(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import GasMaskType
        engine.set_unit_gas_mask("u1", GasMaskType.SMALL_BOX_RESPIRATOR)
        assert engine.get_unit_mopp_level("u1") == 3

    def test_no_cbrn_engine_safe(self) -> None:
        """Engine works without CBRN engine (returns empty lists)."""
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
        eng = GasWarfareEngine(cbrn_engine=None, rng=np.random.default_rng(0))
        puffs = eng.execute_cylinder_release("chlorine", (0, 0), (100, 0))
        assert puffs == []

    def test_state_roundtrip(self, engine) -> None:
        from stochastic_warfare.combat.gas_warfare import (
            GasMaskType,
            GasWarfareEngine,
        )
        engine.set_unit_gas_mask("u1", GasMaskType.PH_HELMET)
        state = engine.get_state()
        eng2 = GasWarfareEngine(rng=np.random.default_rng(0))
        eng2.set_state(state)
        assert eng2.get_unit_mopp_level("u1") == 2


# ---------------------------------------------------------------------------
# Cross-engine integration tests
# ---------------------------------------------------------------------------


class TestCrossEngineIntegration:
    """Cross-engine integration between trenches, barrage, and gas."""

    def test_bombardment_degrades_trench_cover(self) -> None:
        from stochastic_warfare.terrain.trenches import (
            TrenchConfig, TrenchSegment, TrenchSystemEngine, TrenchType,
        )
        eng = TrenchSystemEngine()
        eng.add_trench(TrenchSegment(
            trench_id="t1",
            trench_type=TrenchType.FIRE_TRENCH,
            side="german",
            points=[[0, 0], [100, 0]],
        ))
        # Heavy bombardment
        eng.apply_bombardment(50.0, 0.0, 20.0, intensity=5.0)
        cover = eng.cover_value_at(50.0, 0.0)
        assert cover < 0.85  # less than pristine

    def test_barrage_then_gas_in_trench(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine, GasMaskType

        barrage = BarrageEngine(rng=make_rng(1))
        gas = GasWarfareEngine(cbrn_engine=None, rng=make_rng(2))

        # Both can operate on same area
        barrage.create_barrage("b1", BarrageType.STANDING, "british", 500, 500)
        gas.set_unit_gas_mask("u1", GasMaskType.SMALL_BOX_RESPIRATOR)

        effects = barrage.compute_effects(500.0, 500.0)
        mopp = gas.get_unit_mopp_level("u1")
        assert effects["suppression_p"] > 0
        assert mopp == 3

    def test_modern_era_no_engines(self) -> None:
        """Verify no WW1 engines on modern context."""
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from datetime import datetime, timezone, timedelta
        config = CampaignScenarioConfig(
            name="modern_test", date="2024-01-01", duration_hours=1.0,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )
        assert ctx.trench_engine is None
        assert ctx.barrage_engine is None
        assert ctx.gas_warfare_engine is None

    def test_engines_in_state_roundtrip(self) -> None:
        """WW1 engines persist in SimulationContext state."""
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
            TerrainConfig,
            SideConfig,
        )
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from stochastic_warfare.terrain.trenches import TrenchSystemEngine
        from stochastic_warfare.combat.barrage import BarrageEngine
        from datetime import datetime, timezone, timedelta

        config = CampaignScenarioConfig(
            name="ww1_test", date="1916-07-01", duration_hours=1.0,
            era="ww1",
            terrain=TerrainConfig(width_m=1000, height_m=1000, terrain_type="trench_warfare"),
            sides=[
                SideConfig(side="a", units=[]),
                SideConfig(side="b", units=[]),
            ],
        )
        rng_mgr = RNGManager(42)
        trench_eng = TrenchSystemEngine()
        barrage_eng = BarrageEngine(rng=make_rng(1))

        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(1916, 7, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=5),
            ),
            rng_manager=rng_mgr,
            event_bus=EventBus(),
            trench_engine=trench_eng,
            barrage_engine=barrage_eng,
        )
        state = ctx.get_state()
        assert "trench_engine" in state
        assert "barrage_engine" in state
