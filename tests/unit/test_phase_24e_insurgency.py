"""Tests for Phase 24e — Insurgency & COIN Pipeline.

Tests radicalization pipeline, cell lifecycle (formation, activation,
operations, discovery, destruction), and COIN integration with
CivilianManager and DisruptionEngine.
"""

from __future__ import annotations


import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.logistics.disruption import DisruptionEngine
from stochastic_warfare.population.civilians import (
    CivilianDisposition,
    CivilianManager,
    CivilianRegion,
)
from stochastic_warfare.population.insurgency import (
    CellStatus,
    InsurgencyConfig,
    InsurgencyEngine,
    InsurgentCell,
)

from tests.conftest import TS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POS_A = Position(1000.0, 2000.0, 0.0)
POS_B = Position(3000.0, 4000.0, 0.0)
POS_C = Position(5000.0, 6000.0, 0.0)


def _make_engine(
    event_bus,
    rng,
    config: InsurgencyConfig | None = None,
) -> InsurgencyEngine:
    return InsurgencyEngine(event_bus, rng, config)


def _register_with_collateral(
    engine: InsurgencyEngine,
    region_id: str = "r1",
    population: int = 10000,
) -> None:
    """Register a region with defaults."""
    engine.register_region(region_id, population=population)


def _pump_radicalization(
    engine: InsurgencyEngine,
    dt_hours: float = 10.0,
    collateral: float = 0.5,
    region_id: str = "r1",
    economic_factor: float = 0.0,
    aid: float = 0.0,
    protection: float = 0.0,
    psyop: float = 0.0,
) -> None:
    """Run one radicalization update with given parameters."""
    engine.update_radicalization(
        dt_hours=dt_hours,
        collateral_by_region={region_id: collateral},
        military_presence_by_region={region_id: protection},
        economic_factor=economic_factor,
        aid_by_region={region_id: aid},
        psyop_by_region={region_id: psyop},
        timestamp=TS,
    )


# ===========================================================================
# TestRadicalizationPipeline
# ===========================================================================


class TestRadicalizationPipeline:
    """Radicalization growth and de-radicalization dynamics."""

    def test_collateral_drives_sympathizer_growth(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.8)
        state = engine.get_radicalization("r1")
        assert state.sympathizer_fraction > 0.0

    def test_aid_reduces_sympathizer_fraction(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        # First grow some sympathizers
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.8)
        frac_before = engine.get_radicalization("r1").sympathizer_fraction
        assert frac_before > 0.0
        # Now apply aid with no collateral
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.0, aid=1.0)
        frac_after = engine.get_radicalization("r1").sympathizer_fraction
        assert frac_after < frac_before

    def test_economic_opportunity_reduces_sympathizers(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.8)
        frac_before = engine.get_radicalization("r1").sympathizer_fraction
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.0, economic_factor=1.0)
        frac_after = engine.get_radicalization("r1").sympathizer_fraction
        assert frac_after < frac_before

    def test_sympathizer_to_supporter_transition(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        # Build up sympathizers over several ticks
        for _ in range(5):
            _pump_radicalization(engine, dt_hours=10.0, collateral=0.8)
        state = engine.get_radicalization("r1")
        assert state.supporter_fraction > 0.0

    def test_supporter_to_cell_member_transition(self, event_bus, rng):
        engine = _make_engine(event_bus, rng, InsurgencyConfig(
            k_collateral=0.05,  # fast radicalization
            sympathizer_to_supporter_rate=0.1,
            supporter_to_cell_member_rate=0.05,
        ))
        _register_with_collateral(engine, population=10000)
        # Many ticks to build pipeline
        for _ in range(20):
            _pump_radicalization(engine, dt_hours=5.0, collateral=0.9)
        state = engine.get_radicalization("r1")
        assert state.cell_member_count > 0

    def test_multiple_regions_independent(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        engine.register_region("r1", population=5000)
        engine.register_region("r2", population=5000)
        # Collateral only in r1
        engine.update_radicalization(
            dt_hours=10.0,
            collateral_by_region={"r1": 0.9, "r2": 0.0},
            military_presence_by_region={},
            economic_factor=0.0,
            aid_by_region={},
            psyop_by_region={},
            timestamp=TS,
        )
        s1 = engine.get_radicalization("r1")
        s2 = engine.get_radicalization("r2")
        assert s1.sympathizer_fraction > s2.sympathizer_fraction

    def test_fractions_clamped_to_unit_interval(self, event_bus, rng):
        engine = _make_engine(event_bus, rng, InsurgencyConfig(
            k_collateral=10.0,  # extremely high rate
        ))
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=100.0, collateral=1.0)
        state = engine.get_radicalization("r1")
        assert state.sympathizer_fraction <= 1.0
        assert state.supporter_fraction <= 1.0

    def test_zero_collateral_only_baseline(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.0)
        state = engine.get_radicalization("r1")
        # Only baseline growth (k_economic_baseline * dt)
        expected = 10.0 * 0.001
        assert state.sympathizer_fraction == pytest.approx(expected, abs=0.01)

    def test_military_protection_reduces_radicalization(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.5, protection=0.0)
        frac_no_protect = engine.get_radicalization("r1").sympathizer_fraction

        engine2 = _make_engine(event_bus, np.random.Generator(np.random.PCG64(42)))
        _register_with_collateral(engine2)
        _pump_radicalization(engine2, dt_hours=10.0, collateral=0.5, protection=1.0)
        frac_protect = engine2.get_radicalization("r1").sympathizer_fraction

        assert frac_protect < frac_no_protect

    def test_psyop_reduces_radicalization(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.5, psyop=0.0)
        frac_no_psyop = engine.get_radicalization("r1").sympathizer_fraction

        engine2 = _make_engine(event_bus, np.random.Generator(np.random.PCG64(42)))
        _register_with_collateral(engine2)
        _pump_radicalization(engine2, dt_hours=10.0, collateral=0.5, psyop=1.0)
        frac_psyop = engine2.get_radicalization("r1").sympathizer_fraction

        assert frac_psyop < frac_no_psyop


# ===========================================================================
# TestCellFormation
# ===========================================================================


class TestCellFormation:
    """Cell creation from radicalization pipeline."""

    def _setup_cell_members(self, engine, region_id="r1", count=6):
        """Directly set cell_member_count for testing."""
        state = engine.get_radicalization(region_id)
        state.cell_member_count = count

    def test_cell_created_at_threshold(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=5)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert isinstance(cell, InsurgentCell)

    def test_no_cell_below_threshold(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=4)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is None

    def test_cell_starts_dormant(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=5)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.status == CellStatus.DORMANT

    def test_capabilities_ied_only(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=5)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.capabilities == ["ied"]

    def test_capabilities_ied_sabotage(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=8)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.capabilities == ["ied", "sabotage"]

    def test_capabilities_all(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=12)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.capabilities == ["ied", "sabotage", "ambush"]

    def test_no_duplicate_cell_per_region(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=10)
        cell1 = engine.check_cell_formation("r1", timestamp=TS)
        assert cell1 is not None
        cell2 = engine.check_cell_formation("r1", timestamp=TS)
        assert cell2 is None

    def test_cell_unique_id(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        engine.register_region("r1", population=5000)
        engine.register_region("r2", population=5000)
        engine.get_radicalization("r1").cell_member_count = 6
        engine.get_radicalization("r2").cell_member_count = 6
        c1 = engine.check_cell_formation("r1", timestamp=TS)
        c2 = engine.check_cell_formation("r2", timestamp=TS)
        assert c1 is not None and c2 is not None
        assert c1.cell_id != c2.cell_id

    def test_cell_concealment_starts_at_one(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        self._setup_cell_members(engine, count=5)
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.concealment == 1.0


# ===========================================================================
# TestCellActivation
# ===========================================================================


class TestCellActivation:
    """Cell activation lifecycle."""

    def _make_cell(self, engine, event_bus, rng, region_id="r1", count=6):
        _register_with_collateral(engine)
        engine.get_radicalization(region_id).cell_member_count = count
        cell = engine.check_cell_formation(region_id, timestamp=TS)
        assert cell is not None
        return cell

    def test_activate_dormant_to_active(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_cell(engine, event_bus, rng)
        assert cell.status == CellStatus.DORMANT
        engine.activate_cell(cell.cell_id, "triggered", TS)
        assert engine.get_cell(cell.cell_id).status == CellStatus.ACTIVE

    def test_already_active_stays_active(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_cell(engine, event_bus, rng)
        engine.activate_cell(cell.cell_id, "first", TS)
        engine.activate_cell(cell.cell_id, "second", TS)
        assert engine.get_cell(cell.cell_id).status == CellStatus.ACTIVE

    def test_reason_does_not_error(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_cell(engine, event_bus, rng)
        # Should not raise regardless of reason content
        engine.activate_cell(cell.cell_id, "some detailed reason", TS)

    def test_destroyed_cell_stays_destroyed(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_cell(engine, event_bus, rng)
        engine.destroy_cell(cell.cell_id, TS)
        engine.activate_cell(cell.cell_id, "attempt", TS)
        assert engine.get_cell(cell.cell_id).status == CellStatus.DESTROYED

    def test_multiple_cells_active(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        engine.register_region("r1", population=5000)
        engine.register_region("r2", population=5000)
        engine.get_radicalization("r1").cell_member_count = 6
        engine.get_radicalization("r2").cell_member_count = 6
        c1 = engine.check_cell_formation("r1", timestamp=TS)
        c2 = engine.check_cell_formation("r2", timestamp=TS)
        assert c1 is not None and c2 is not None
        engine.activate_cell(c1.cell_id, "go", TS)
        engine.activate_cell(c2.cell_id, "go", TS)
        active = engine.get_active_cells()
        assert len(active) == 2


# ===========================================================================
# TestCellOperations
# ===========================================================================


class TestCellOperations:
    """Cell operations execution and effects."""

    def _make_active_cell(
        self, engine, region_id="r1", count=12, population=10000
    ):
        """Create and activate a cell with full capabilities."""
        engine.register_region(region_id, population=population)
        engine.get_radicalization(region_id).cell_member_count = count
        cell = engine.check_cell_formation(region_id, timestamp=TS)
        assert cell is not None
        engine.activate_cell(cell.cell_id, "test", TS)
        return cell

    def test_ied_emplacement_result(self, event_bus, rng):
        # Use high operation rate to guarantee result
        cfg = InsurgencyConfig(k_ied_emplacement=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A, POS_B],
            military_targets=[POS_C],
            timestamp=TS,
        )
        ied_results = [r for r in results if r.operation_type == "ied_emplacement"]
        assert len(ied_results) >= 1
        assert ied_results[0].cell_id == cell.cell_id

    def test_sabotage_result(self, event_bus, rng):
        cfg = InsurgencyConfig(k_sabotage=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        sab_results = [r for r in results if r.operation_type == "sabotage"]
        assert len(sab_results) >= 1

    def test_ambush_result(self, event_bus, rng):
        cfg = InsurgencyConfig(k_ambush=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        ambush_results = [r for r in results if r.operation_type == "ambush"]
        assert len(ambush_results) >= 1

    def test_concealment_degrades_with_operations(self, event_bus, rng):
        cfg = InsurgencyConfig(
            k_ied_emplacement=100.0,
            concealment_degradation_per_op=0.1,
        )
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        assert cell.concealment == 1.0
        engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        updated_cell = engine.get_cell(cell.cell_id)
        assert updated_cell.concealment < 1.0

    def test_operations_count_increments(self, event_bus, rng):
        cfg = InsurgencyConfig(k_ied_emplacement=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        assert cell.operations_count == 0
        engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[],
            timestamp=TS,
        )
        assert engine.get_cell(cell.cell_id).operations_count > 0

    def test_no_capability_no_operation(self, event_bus, rng):
        """Cell with only IED capability does not produce sabotage/ambush."""
        cfg = InsurgencyConfig(
            k_ied_emplacement=100.0,
            k_sabotage=100.0,
            k_ambush=100.0,
        )
        engine = _make_engine(event_bus, rng, cfg)
        # Only 5 members -> only IED capability
        cell = self._make_active_cell(engine, count=5)
        assert cell.capabilities == ["ied"]
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        for r in results:
            assert r.operation_type == "ied_emplacement"

    def test_dormant_cell_no_operations(self, event_bus, rng):
        cfg = InsurgencyConfig(k_ied_emplacement=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        engine.register_region("r1", population=10000)
        engine.get_radicalization("r1").cell_member_count = 6
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        assert cell.status == CellStatus.DORMANT
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        assert len(results) == 0

    def test_success_correlates_with_concealment(self, event_bus):
        """High concealment cells succeed more than low concealment cells."""
        from stochastic_warfare.core.events import EventBus as EB

        high_conc_successes = 0
        low_conc_successes = 0
        n_trials = 50

        cfg = InsurgencyConfig(
            k_ied_emplacement=100.0,
            concealment_degradation_per_op=0.0,
        )

        for seed in range(n_trials):
            # High concealment trial
            rng_h = np.random.Generator(np.random.PCG64(seed))
            eng = _make_engine(EB(), rng_h, cfg)
            eng.register_region("r1", population=10000)
            eng.get_radicalization("r1").cell_member_count = 6
            cell = eng.check_cell_formation("r1", timestamp=TS)
            assert cell is not None
            eng.activate_cell(cell.cell_id, "test", TS)
            # concealment stays at 1.0 (default)
            results = eng.execute_cell_operations(1.0, [POS_A], [], TS)
            high_conc_successes += sum(1 for r in results if r.success)

            # Low concealment trial
            rng_l = np.random.Generator(np.random.PCG64(seed + 10000))
            eng2 = _make_engine(EB(), rng_l, cfg)
            eng2.register_region("r1", population=10000)
            eng2.get_radicalization("r1").cell_member_count = 6
            cell2 = eng2.check_cell_formation("r1", timestamp=TS)
            assert cell2 is not None
            eng2.activate_cell(cell2.cell_id, "test", TS)
            eng2.get_cell(cell2.cell_id).concealment = 0.1
            results2 = eng2.execute_cell_operations(1.0, [POS_A], [], TS)
            low_conc_successes += sum(1 for r in results2 if r.success)

        assert high_conc_successes >= low_conc_successes

    def test_multiple_operations_one_tick(self, event_bus, rng):
        cfg = InsurgencyConfig(
            k_ied_emplacement=100.0,
            k_sabotage=100.0,
            k_ambush=100.0,
        )
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine, count=12)
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[POS_A],
            military_targets=[POS_C],
            timestamp=TS,
        )
        types = {r.operation_type for r in results}
        # With rates=100 and dt=1, all three should trigger
        assert len(types) >= 2  # at least two different op types

    def test_empty_positions_no_ied(self, event_bus, rng):
        cfg = InsurgencyConfig(k_ied_emplacement=100.0)
        engine = _make_engine(event_bus, rng, cfg)
        cell = self._make_active_cell(engine)
        results = engine.execute_cell_operations(
            dt_hours=1.0,
            high_traffic_positions=[],  # no positions
            military_targets=[],
            timestamp=TS,
        )
        ied_results = [r for r in results if r.operation_type == "ied_emplacement"]
        assert len(ied_results) == 0


# ===========================================================================
# TestCellDiscovery
# ===========================================================================


class TestCellDiscovery:
    """Cell discovery via intelligence sources."""

    def _make_active_exposed_cell(self, engine, concealment=0.0):
        """Create an active cell with low concealment (easy to discover)."""
        engine.register_region("r1", population=10000)
        engine.get_radicalization("r1").cell_member_count = 6
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        engine.activate_cell(cell.cell_id, "test", TS)
        # Directly set concealment
        engine.get_cell(cell.cell_id).concealment = concealment
        return cell

    def test_humint_discovery_high_quality(self, event_bus):
        """HUMINT with high quality and low concealment discovers cell."""
        # p_discover = (1 - 0) * 0.05 * 1.0 = 0.05 per trial
        # With 100 trials, P(at least one) = 1 - 0.95^100 > 0.99
        discovered = False
        for seed in range(100):
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = _make_engine(event_bus, rng)
            cell = self._make_active_exposed_cell(engine, concealment=0.0)
            if engine.attempt_cell_discovery(cell.cell_id, "humint", 1.0, TS):
                discovered = True
                break
        assert discovered

    def test_sigint_discovery(self, event_bus):
        # p_discover = (1 - 0) * 0.02 * 1.0 = 0.02 per trial
        # With 200 trials, P(at least one) = 1 - 0.98^200 > 0.98
        discovered = False
        for seed in range(200):
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = _make_engine(event_bus, rng)
            cell = self._make_active_exposed_cell(engine, concealment=0.0)
            if engine.attempt_cell_discovery(cell.cell_id, "sigint", 1.0, TS):
                discovered = True
                break
        assert discovered

    def test_pattern_analysis_discovery(self, event_bus):
        # p_discover = (1 - 0) * 0.01 * 1.0 = 0.01 per trial
        # With 500 trials, P(at least one) = 1 - 0.99^500 > 0.99
        discovered = False
        for seed in range(500):
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = _make_engine(event_bus, rng)
            cell = self._make_active_exposed_cell(engine, concealment=0.0)
            if engine.attempt_cell_discovery(
                cell.cell_id, "pattern_analysis", 1.0, TS
            ):
                discovered = True
                break
        assert discovered

    def test_low_concealment_increases_discovery(self, event_bus):
        """Low concealment should yield higher discovery rate than high."""
        low_conc_discoveries = 0
        high_conc_discoveries = 0
        n = 100

        for seed in range(n):
            # Low concealment
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = _make_engine(event_bus, rng)
            cell = self._make_active_exposed_cell(engine, concealment=0.0)
            if engine.attempt_cell_discovery(cell.cell_id, "humint", 1.0, TS):
                low_conc_discoveries += 1

            # High concealment
            rng2 = np.random.Generator(np.random.PCG64(seed + 10000))
            engine2 = _make_engine(event_bus, rng2)
            cell2 = self._make_active_exposed_cell(engine2, concealment=1.0)
            if engine2.attempt_cell_discovery(cell2.cell_id, "humint", 1.0, TS):
                high_conc_discoveries += 1

        assert low_conc_discoveries > high_conc_discoveries

    def test_high_concealment_unlikely_discovery(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_active_exposed_cell(engine, concealment=1.0)
        # With concealment=1.0, p_discover = (1-1.0) * rate * quality = 0
        result = engine.attempt_cell_discovery(cell.cell_id, "humint", 1.0, TS)
        assert result is False

    def test_discovered_cell_status(self, event_bus):
        for seed in range(20):
            rng = np.random.Generator(np.random.PCG64(seed))
            engine = _make_engine(event_bus, rng)
            cell = self._make_active_exposed_cell(engine, concealment=0.0)
            if engine.attempt_cell_discovery(cell.cell_id, "humint", 1.0, TS):
                assert engine.get_cell(cell.cell_id).status == CellStatus.DISCOVERED
                break

    def test_destroyed_cell_not_discoverable(self, event_bus, rng):
        engine = _make_engine(event_bus, rng)
        cell = self._make_active_exposed_cell(engine, concealment=0.0)
        engine.destroy_cell(cell.cell_id, TS)
        result = engine.attempt_cell_discovery(cell.cell_id, "humint", 1.0, TS)
        assert result is False


# ===========================================================================
# TestCOINDynamics
# ===========================================================================


class TestCOINDynamics:
    """Integration tests: COIN strategy effects and cross-module wiring."""

    def test_kinetic_approach_increases_recruitment(self, event_bus, rng):
        """High collateral -> kinetic approach -> sympathizer growth."""
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        _pump_radicalization(engine, dt_hours=10.0, collateral=1.0)
        state = engine.get_radicalization("r1")
        # High collateral should produce significant sympathizer fraction
        assert state.sympathizer_fraction > 0.05

    def test_population_centric_reduces_recruitment(self, event_bus, rng):
        """High aid + protection + psyop -> reduced sympathizers."""
        engine = _make_engine(event_bus, rng)
        _register_with_collateral(engine)
        # Grow sympathizers first
        _pump_radicalization(engine, dt_hours=10.0, collateral=0.5)
        frac_after_collateral = engine.get_radicalization("r1").sympathizer_fraction
        # Now apply population-centric approach
        _pump_radicalization(
            engine,
            dt_hours=10.0,
            collateral=0.0,
            aid=1.0,
            protection=1.0,
            psyop=1.0,
            economic_factor=1.0,
        )
        frac_after_coin = engine.get_radicalization("r1").sympathizer_fraction
        assert frac_after_coin < frac_after_collateral

    def test_civilian_manager_get_regions_by_disposition(self, event_bus, rng):
        """CivilianManager.get_regions_by_disposition works correctly."""
        mgr = CivilianManager(event_bus, rng)
        mgr.register_region(CivilianRegion(
            region_id="hostile_1",
            center=POS_A,
            radius_m=500.0,
            population=1000,
            disposition=CivilianDisposition.HOSTILE,
        ))
        mgr.register_region(CivilianRegion(
            region_id="neutral_1",
            center=POS_B,
            radius_m=500.0,
            population=2000,
            disposition=CivilianDisposition.NEUTRAL,
        ))
        mgr.register_region(CivilianRegion(
            region_id="hostile_2",
            center=POS_C,
            radius_m=500.0,
            population=3000,
            disposition=CivilianDisposition.HOSTILE,
        ))
        hostile = mgr.get_regions_by_disposition(CivilianDisposition.HOSTILE)
        assert len(hostile) == 2
        neutral = mgr.get_regions_by_disposition(CivilianDisposition.NEUTRAL)
        assert len(neutral) == 1
        friendly = mgr.get_regions_by_disposition(CivilianDisposition.FRIENDLY)
        assert len(friendly) == 0

    def test_disruption_engine_apply_insurgent_sabotage(self, event_bus, rng):
        """DisruptionEngine.apply_insurgent_sabotage creates interdiction zone."""
        de = DisruptionEngine(event_bus, rng)
        zone = de.apply_insurgent_sabotage(
            position=POS_A,
            intensity=0.7,
            cell_id="cell_abc",
            target_type="bridge",
            timestamp=TS,
        )
        assert zone.zone_id == "insurgent_sabotage_cell_abc_bridge"
        assert zone.position == POS_A
        assert zone.radius_m == 200.0
        assert zone.intensity == pytest.approx(0.7)
        assert zone.source == "insurgent"
        # Verify it's in the engine's zone list
        assert len(de.active_zones()) == 1

    def test_state_roundtrip(self, event_bus, rng):
        """InsurgencyEngine state serialization roundtrip."""
        engine = _make_engine(event_bus, rng)
        engine.register_region("r1", population=5000)
        engine.get_radicalization("r1").sympathizer_fraction = 0.3
        engine.get_radicalization("r1").cell_member_count = 7
        cell = engine.check_cell_formation("r1", timestamp=TS)
        assert cell is not None
        engine.activate_cell(cell.cell_id, "test", TS)

        state = engine.get_state()

        # Restore into fresh engine
        rng2 = np.random.Generator(np.random.PCG64(99))
        engine2 = _make_engine(event_bus, rng2)
        engine2.set_state(state)

        s2 = engine2.get_radicalization("r1")
        assert s2.sympathizer_fraction == pytest.approx(0.3)
        assert s2.cell_member_count == 7

        restored_cell = engine2.get_cell(cell.cell_id)
        assert restored_cell.status == CellStatus.ACTIVE
        assert restored_cell.region_id == "r1"
