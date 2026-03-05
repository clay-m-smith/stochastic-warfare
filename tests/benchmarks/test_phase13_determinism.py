"""Phase 13c-2: Determinism verification tests.

Ensures all Phase 13 optimizations produce bit-for-bit identical results
compared to pre-optimization (or reference) implementations.
"""

import types

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_heightmap(rows=20, cols=20, cell_size=100.0, data=None):
    from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig

    cfg = HeightmapConfig(cell_size=cell_size, origin_easting=0.0, origin_northing=0.0)
    if data is None:
        data = np.zeros((rows, cols), dtype=np.float64)
    return Heightmap(data, cfg)


def _make_los(rows=20, cols=20, cell_size=100.0, data=None):
    from stochastic_warfare.terrain.los import LOSEngine

    return LOSEngine(_make_heightmap(rows, cols, cell_size, data))


def _make_unit(entity_id, side="blue", pos=Position(0, 0), unit_type="infantry"):
    return Unit(entity_id=entity_id, position=pos, side=side, unit_type=unit_type)


def _make_ctx(units_by_side=None, morale_states=None):
    ctx = types.SimpleNamespace()
    ctx.units_by_side = units_by_side or {}
    ctx.unit_weapons = {}
    ctx.unit_sensors = {}
    ctx.morale_states = morale_states if morale_states is not None else {}
    ctx.stockpile_manager = None
    return ctx


# ---------------------------------------------------------------------------
# LOS cache determinism
# ---------------------------------------------------------------------------


class TestLOSCacheDeterminism:
    """Multi-tick selective cache produces same results as full clear."""

    def test_selective_vs_full_clear(self):
        """Selective invalidation + re-query matches full clear + re-query."""
        rng = np.random.default_rng(42)
        data = rng.uniform(0, 200, size=(30, 30)).astype(np.float64)
        los1 = _make_los(data=data)
        los2 = _make_los(data=data)

        observer = Position(1500.0, 1500.0)
        targets = [Position(500 + i * 200, 1000) for i in range(10)]

        for t in targets:
            los1.check_los(observer, t, observer_height=2.0)
            los2.check_los(observer, t, observer_height=2.0)

        # Selective invalidation on los1
        obs_cell = los1._hm.enu_to_grid(observer)
        los1.invalidate_cells({obs_cell})
        # Full clear on los2
        los2.clear_los_cache()

        for t in targets:
            r1 = los1.check_los(observer, t, observer_height=2.0)
            r2 = los2.check_los(observer, t, observer_height=2.0)
            assert r1.visible == r2.visible
            if r1.grazing_distance is not None and r2.grazing_distance is not None:
                assert r1.grazing_distance == pytest.approx(r2.grazing_distance, rel=1e-10)

    def test_cached_result_identical_to_uncached(self):
        """A cached LOS result matches a fresh computation."""
        rng = np.random.default_rng(99)
        data = rng.uniform(0, 150, size=(25, 25)).astype(np.float64)
        los = _make_los(data=data)

        obs = Position(1200.0, 1200.0)
        tgt = Position(2000.0, 800.0)

        r1 = los.check_los(obs, tgt, observer_height=1.8)
        r2 = los.check_los(obs, tgt, observer_height=1.8)  # hits cache
        assert r1 == r2

        # Clear and recompute
        los.clear_los_cache()
        r3 = los.check_los(obs, tgt, observer_height=1.8)
        assert r1.visible == r3.visible
        if r1.grazing_distance is not None:
            assert r1.grazing_distance == pytest.approx(r3.grazing_distance, rel=1e-10)


# ---------------------------------------------------------------------------
# Kalman cache determinism
# ---------------------------------------------------------------------------


class TestKalmanCacheDeterminism:
    """Kalman F/Q caching produces identical results."""

    def test_cached_predict_identical(self):
        from stochastic_warfare.detection.estimation import (
            EstimationConfig,
            StateEstimator,
            Track,
            TrackState,
            TrackStatus,
        )
        from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        ci = ContactInfo(
            level=ContactLevel.DETECTED,
            domain_estimate=None,
            type_estimate=None,
            specific_estimate=None,
            confidence=0.5,
        )
        ts = TrackState(
            position=np.array([1000.0, 2000.0]),
            velocity=np.array([10.0, -5.0]),
            covariance=np.eye(4) * 100.0,
            last_update_time=0.0,
        )
        track = Track(track_id="t0", side="blue", contact_info=ci, state=ts)

        # First predict (no cache)
        est.predict(track, 5.0)
        state1 = track.state.position.copy(), track.state.velocity.copy(), track.state.covariance.copy()

        # Reset track
        track.state = TrackState(
            position=np.array([1000.0, 2000.0]),
            velocity=np.array([10.0, -5.0]),
            covariance=np.eye(4) * 100.0,
            last_update_time=0.0,
        )

        # Second predict (hits cache)
        est.predict(track, 5.0)
        state2 = track.state.position.copy(), track.state.velocity.copy(), track.state.covariance.copy()

        np.testing.assert_array_equal(state1[0], state2[0])
        np.testing.assert_array_equal(state1[1], state2[1])
        np.testing.assert_array_equal(state1[2], state2[2])

    def test_different_dt_not_contaminated(self):
        from stochastic_warfare.detection.estimation import (
            EstimationConfig,
            StateEstimator,
            Track,
            TrackState,
        )
        from stochastic_warfare.detection.identification import ContactInfo, ContactLevel

        est = StateEstimator(rng=np.random.default_rng(0), config=EstimationConfig())
        ci = ContactInfo(
            level=ContactLevel.DETECTED,
            domain_estimate=None,
            type_estimate=None,
            specific_estimate=None,
            confidence=0.5,
        )

        def make_track():
            return Track(
                track_id="t0", side="blue", contact_info=ci,
                state=TrackState(
                    position=np.array([0.0, 0.0]),
                    velocity=np.array([10.0, 0.0]),
                    covariance=np.eye(4) * 100.0,
                    last_update_time=0.0,
                ),
            )

        # Predict with dt=5
        t1 = make_track()
        est.predict(t1, 5.0)
        pos5 = t1.state.position.copy()

        # Predict with dt=10
        t2 = make_track()
        est.predict(t2, 10.0)
        pos10 = t2.state.position.copy()

        # dt=10 should move farther than dt=5
        assert pos10[0] > pos5[0]

        # Predict with dt=5 again — should match first
        t3 = make_track()
        est.predict(t3, 5.0)
        np.testing.assert_array_equal(t3.state.position, pos5)


# ---------------------------------------------------------------------------
# RK4 trajectory determinism
# ---------------------------------------------------------------------------


class TestRK4Determinism:
    """RK4 trajectory produces identical results across runs."""

    def test_trajectory_deterministic(self):
        from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
        from stochastic_warfare.combat.ballistics import BallisticsConfig, BallisticsEngine

        weapon = WeaponDefinition(
            weapon_id="det_gun", display_name="Det Gun", category="GUN",
            caliber_mm=120, muzzle_velocity_mps=1700, max_range_m=4000,
            base_accuracy_mrad=0.3, rate_of_fire_rpm=6,
        )
        ammo = AmmoDefinition(
            ammo_id="det_round", display_name="Det Round", ammo_type="apfsds",
            mass_kg=4.5, diameter_mm=30, drag_coefficient=0.3,
        )

        results = []
        for _ in range(3):
            rng = np.random.default_rng(42)
            engine = BallisticsEngine(rng, BallisticsConfig(integration_step_s=0.01))
            result = engine.compute_trajectory(weapon, ammo, Position(0, 0, 0), 5.0, 90.0)
            results.append(result)

        for i in range(1, len(results)):
            assert results[0].impact_position.easting == pytest.approx(results[i].impact_position.easting, rel=1e-10)
            assert results[0].impact_position.northing == pytest.approx(results[i].impact_position.northing, rel=1e-10)
            assert results[0].time_of_flight_s == pytest.approx(results[i].time_of_flight_s, rel=1e-10)


# ---------------------------------------------------------------------------
# Aggregation round-trip determinism
# ---------------------------------------------------------------------------


class TestAggregationDeterminism:
    """Aggregate -> disaggregate produces identical unit state."""

    def test_roundtrip_unit_state(self):
        from stochastic_warfare.simulation.aggregation import AggregationConfig, AggregationEngine

        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        units = [
            _make_unit("u0", "blue", Position(100, 200), "infantry"),
            _make_unit("u1", "blue", Position(300, 400), "infantry"),
            _make_unit("u2", "blue", Position(500, 600), "armor"),
        ]
        morale = {"u0": MoraleState.STEADY, "u1": MoraleState.SHAKEN, "u2": MoraleState.STEADY}
        ctx = _make_ctx({"blue": list(units)}, dict(morale))

        engine = AggregationEngine(config=config, rng=np.random.default_rng(0))
        agg = engine.aggregate([u.entity_id for u in units], ctx)
        assert agg is not None

        engine.disaggregate(agg.aggregate_id, ctx)

        restored = {u.entity_id: u for u in ctx.units_by_side["blue"]}
        assert "u0" in restored
        assert "u1" in restored
        assert "u2" in restored
        assert restored["u0"].position.easting == pytest.approx(100.0)
        assert restored["u1"].position.northing == pytest.approx(400.0)
        assert restored["u2"].unit_type == "armor"
        assert ctx.morale_states["u0"] == MoraleState.STEADY
        assert ctx.morale_states["u1"] == MoraleState.SHAKEN

    def test_deterministic_aggregate_ids(self):
        from stochastic_warfare.simulation.aggregation import AggregationConfig, AggregationEngine

        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        ids = []
        for _ in range(3):
            engine = AggregationEngine(config=config, rng=np.random.default_rng(0))
            units = [_make_unit(f"u{i}", "blue") for i in range(4)]
            ctx = _make_ctx({"blue": list(units)})
            agg = engine.aggregate([u.entity_id for u in units], ctx)
            ids.append(agg.aggregate_id)
        assert ids[0] == ids[1] == ids[2]

    def test_state_persistence_roundtrip(self):
        from stochastic_warfare.simulation.aggregation import AggregationConfig, AggregationEngine

        config = AggregationConfig(enable_aggregation=True, min_units_to_aggregate=2)
        engine1 = AggregationEngine(config=config, rng=np.random.default_rng(0))
        units = [_make_unit(f"u{i}", "blue", Position(i * 100, 0)) for i in range(4)]
        ctx = _make_ctx({"blue": list(units)})
        engine1.aggregate([u.entity_id for u in units], ctx)

        state = engine1.get_state()
        engine2 = AggregationEngine(config=config, rng=np.random.default_rng(0))
        engine2.set_state(state)

        agg1 = list(engine1.active_aggregates.values())[0]
        agg2 = list(engine2.active_aggregates.values())[0]
        assert agg1.aggregate_id == agg2.aggregate_id
        assert agg1.position.easting == pytest.approx(agg2.position.easting)
        assert len(agg1.constituent_snapshots) == len(agg2.constituent_snapshots)


# ---------------------------------------------------------------------------
# Auto-resolve PRNG isolation
# ---------------------------------------------------------------------------


class TestAutoResolvePRNGIsolation:
    """Auto-resolve uses its own PRNG stream without contaminating others."""

    def test_auto_resolve_deterministic(self):
        from datetime import datetime

        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.simulation.battle import BattleConfig, BattleContext, BattleManager

        config = BattleConfig(auto_resolve_enabled=True, auto_resolve_max_units=20)
        results = []
        for _ in range(3):
            rng = np.random.default_rng(42)
            bus = EventBus()
            mgr = BattleManager(event_bus=bus, config=config)

            blue_units = [_make_unit(f"b{i}", "blue") for i in range(5)]
            red_units = [_make_unit(f"r{i}", "red") for i in range(5)]
            units_by_side = {"blue": blue_units, "red": red_units}

            battle = BattleContext(
                battle_id="test_battle",
                start_tick=0,
                start_time=datetime(2024, 1, 1),
                involved_sides=["blue", "red"],
            )
            result = mgr.auto_resolve(battle, units_by_side, rng)
            results.append(result)

        for i in range(1, len(results)):
            assert results[0].winner == results[i].winner
            assert results[0].side_losses == results[i].side_losses
            assert results[0].duration_s == results[i].duration_s


# ---------------------------------------------------------------------------
# Viewshed determinism
# ---------------------------------------------------------------------------


class TestViewshedDeterminism:
    """Viewshed produces identical results across runs."""

    def test_viewshed_deterministic(self):
        rng = np.random.default_rng(77)
        data = rng.uniform(0, 100, size=(15, 15)).astype(np.float64)
        los = _make_los(data=data)
        obs = Position(750.0, 750.0)

        v1 = los.visible_area(obs, max_range=2000.0, observer_height=2.0)
        los.clear_los_cache()
        v2 = los.visible_area(obs, max_range=2000.0, observer_height=2.0)
        np.testing.assert_array_equal(v1, v2)

    def test_viewshed_matches_individual_los(self):
        """Viewshed result for each cell matches individual check_los."""
        rng = np.random.default_rng(55)
        data = rng.uniform(0, 50, size=(10, 10)).astype(np.float64)
        los = _make_los(data=data)
        obs = Position(500.0, 500.0)

        viewshed = los.visible_area(obs, max_range=2000.0, observer_height=2.0)
        los.clear_los_cache()

        # Spot-check a few cells
        for r in range(0, 10, 3):
            for c in range(0, 10, 3):
                tgt = los._hm.grid_to_enu(r, c)
                result = los.check_los(obs, tgt, observer_height=2.0)
                assert viewshed[r, c] == result.visible, f"Mismatch at ({r},{c})"
