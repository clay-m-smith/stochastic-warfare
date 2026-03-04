"""Phase 12b — Logistics Depth tests.

12b-1: Multi-echelon supply network + infrastructure coupling
12b-2: Supply regeneration (production)
12b-3: Transport escort effects
12b-4: Erlang medical service
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


# ========================================================================
# 12b-1: Multi-Echelon Supply Network
# ========================================================================


class TestSupplyNetworkEnhancements:
    def _make_engine(self, **kwargs):
        from stochastic_warfare.logistics.supply_network import (
            SupplyNetworkConfig, SupplyNetworkEngine,
        )
        cfg = SupplyNetworkConfig(**kwargs)
        return SupplyNetworkEngine(EventBus(), _rng(), config=cfg)

    def _build_network(self, eng):
        from stochastic_warfare.logistics.supply_network import (
            SupplyNode, SupplyRoute, TransportMode,
        )
        eng.add_node(SupplyNode("depot", Position(0, 0, 0), "DEPOT", echelon_level=3))
        eng.add_node(SupplyNode("fwd", Position(5000, 0, 0), "DEPOT", echelon_level=1))
        eng.add_node(SupplyNode("unit1", Position(10000, 0, 0), "UNIT", linked_id="u1"))
        eng.add_route(SupplyRoute(
            "r1", "depot", "fwd", TransportMode.ROAD,
            5000, 10.0, 2.0,
        ))
        eng.add_route(SupplyRoute(
            "r2", "fwd", "unit1", TransportMode.ROAD,
            5000, 5.0, 1.0,
        ))

    def test_new_supply_node_fields(self) -> None:
        from stochastic_warfare.logistics.supply_network import SupplyNode
        node = SupplyNode(
            "test", Position(0, 0, 0), "DEPOT",
            echelon_level=2, infrastructure_id="bridge_1",
            throughput_tons_per_hour=50.0,
        )
        assert node.echelon_level == 2
        assert node.infrastructure_id == "bridge_1"
        assert node.throughput_tons_per_hour == 50.0

    def test_new_supply_route_fields(self) -> None:
        from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode
        route = SupplyRoute(
            "r1", "a", "b", TransportMode.ROAD, 1000, 10.0, 1.0,
            infrastructure_ids=["bridge_1", "road_5"],
        )
        assert route.infrastructure_ids == ["bridge_1", "road_5"]
        assert route.current_flow_tons_per_hour == 0.0

    def test_sever_route(self) -> None:
        eng = self._make_engine()
        self._build_network(eng)
        affected = eng.sever_route("r2")
        assert "u1" in affected
        # Route condition should be 0
        route = eng.get_route("r2")
        assert route.condition == 0.0

    def test_sever_route_blocks_pathfinding(self) -> None:
        eng = self._make_engine()
        self._build_network(eng)
        eng.sever_route("r2")
        path = eng.find_supply_route("depot", "unit1")
        # Path may exist but with very high weight (condition=0 → weight=inf)
        # or no path if edge removed
        if path is not None:
            cap = eng.compute_route_capacity(path)
            assert cap == 0.0

    def test_find_alternate_route(self) -> None:
        from stochastic_warfare.logistics.supply_network import (
            SupplyNode, SupplyRoute, TransportMode,
        )
        eng = self._make_engine()
        eng.add_node(SupplyNode("a", Position(0, 0, 0), "DEPOT"))
        eng.add_node(SupplyNode("b", Position(5000, 0, 0), "UNIT"))
        eng.add_node(SupplyNode("c", Position(2500, 3000, 0), "DEPOT"))
        # Two routes: direct and via c
        eng.add_route(SupplyRoute("direct", "a", "b", TransportMode.ROAD, 5000, 10.0, 1.0))
        eng.add_route(SupplyRoute("a_c", "a", "c", TransportMode.ROAD, 3000, 5.0, 1.5))
        eng.add_route(SupplyRoute("c_b", "c", "b", TransportMode.ROAD, 3000, 5.0, 1.5))
        # Find alternate avoiding direct route
        alt = eng.find_alternate_route("a", "b", blocked_routes={"direct"})
        assert alt is not None
        assert len(alt) == 2

    def test_find_alternate_no_path(self) -> None:
        eng = self._make_engine()
        self._build_network(eng)
        alt = eng.find_alternate_route("depot", "unit1", blocked_routes={"r1", "r2"})
        assert alt is None

    def test_compute_network_redundancy(self) -> None:
        from stochastic_warfare.logistics.supply_network import (
            SupplyNode, SupplyRoute, TransportMode,
        )
        eng = self._make_engine()
        eng.add_node(SupplyNode("depot", Position(0, 0, 0), "DEPOT"))
        eng.add_node(SupplyNode("unit", Position(5000, 0, 0), "UNIT"))
        eng.add_route(SupplyRoute("r1", "depot", "unit", TransportMode.ROAD, 5000, 10.0, 1.0))
        redundancy = eng.compute_network_redundancy("unit")
        assert 0.0 < redundancy <= 1.0

    def test_sync_infrastructure(self) -> None:
        from stochastic_warfare.logistics.supply_network import (
            SupplyNode, SupplyRoute, TransportMode,
        )
        eng = self._make_engine(enable_infrastructure_coupling=True)
        eng.add_node(SupplyNode("a", Position(0, 0, 0), "DEPOT"))
        eng.add_node(SupplyNode("b", Position(5000, 0, 0), "UNIT"))
        eng.add_route(SupplyRoute(
            "r1", "a", "b", TransportMode.ROAD, 5000, 10.0, 1.0,
            infrastructure_ids=["bridge_1"],
        ))

        class MockInfra:
            def get_feature_condition(self, fid):
                return 0.3

        eng.sync_infrastructure(MockInfra())
        route = eng.get_route("r1")
        assert route.condition == 0.3

    def test_sever_nonexistent_route(self) -> None:
        eng = self._make_engine()
        result = eng.sever_route("nonexistent")
        assert result == []

    def test_config_defaults_false(self) -> None:
        from stochastic_warfare.logistics.supply_network import SupplyNetworkConfig
        cfg = SupplyNetworkConfig()
        assert cfg.enable_capacity_constraints is False
        assert cfg.enable_infrastructure_coupling is False
        assert cfg.enable_min_cost_flow is False


# ========================================================================
# 12b-2: Supply Regeneration (Production)
# ========================================================================


class TestProductionEngine:
    def _make_engine(self):
        from stochastic_warfare.logistics.production import ProductionEngine
        return ProductionEngine(EventBus(), _rng())

    def test_register_and_produce(self) -> None:
        from stochastic_warfare.logistics.production import ProductionFacilityConfig
        eng = self._make_engine()
        eng.register_facility(ProductionFacilityConfig(
            facility_id="factory_1",
            facility_type="factory",
            production_rates={"ammo": 10.0, "fuel": 5.0},
        ))
        result = eng.update(1.0)  # 1 hour
        assert "factory_1" in result
        assert result["factory_1"]["ammo"] == pytest.approx(10.0)
        assert result["factory_1"]["fuel"] == pytest.approx(5.0)

    def test_damaged_facility_reduced_output(self) -> None:
        from stochastic_warfare.logistics.production import ProductionFacilityConfig
        eng = self._make_engine()
        eng.register_facility(ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        ))
        eng.set_facility_condition("f1", 0.5)
        result = eng.update(1.0)
        assert result["f1"]["ammo"] == pytest.approx(5.0)

    def test_destroyed_facility_no_output(self) -> None:
        from stochastic_warfare.logistics.production import ProductionFacilityConfig
        eng = self._make_engine()
        eng.register_facility(ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        ))
        eng.set_facility_condition("f1", 0.0)
        result = eng.update(1.0)
        assert "f1" not in result

    def test_infrastructure_coupling(self) -> None:
        from stochastic_warfare.logistics.production import ProductionFacilityConfig
        eng = self._make_engine()
        eng.register_facility(ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
            infrastructure_id="building_5",
        ))

        class MockInfra:
            def get_feature_condition(self, fid):
                return 0.4

        result = eng.update(1.0, infrastructure_manager=MockInfra())
        assert result["f1"]["ammo"] == pytest.approx(4.0)

    def test_state_save_restore(self) -> None:
        from stochastic_warfare.logistics.production import ProductionFacilityConfig
        eng = self._make_engine()
        eng.register_facility(ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        ))
        eng.set_facility_condition("f1", 0.7)
        state = eng.get_state()
        eng2 = self._make_engine()
        eng2.set_state(state)
        assert eng2.get_facility_condition("f1") == pytest.approx(0.7)


# ========================================================================
# 12b-3: Transport Escort Effects
# ========================================================================


class TestTransportEscort:
    def _make_engine(self):
        from stochastic_warfare.logistics.transport import (
            TransportConfig, TransportEngine,
        )
        cfg = TransportConfig()
        return TransportEngine(EventBus(), _rng(), config=cfg)

    def test_no_threat_no_interdiction(self) -> None:
        eng = self._make_engine()
        from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode
        route = [SupplyRoute("r1", "a", "b", TransportMode.ROAD, 5000, 10.0, 1.0)]
        mission = eng.dispatch(
            "m1", TransportMode.ROAD, route,
            {"I": {"food": 1.0}}, "a", "b", _TS,
        )
        completed = eng.update(
            0.5, timestamp=_TS, escort_strength=1.0, threat_level=0.0,
        )
        # No interdiction, mission still in transit or arrived
        assert mission.status in ("IN_TRANSIT", "ARRIVED")

    def test_high_threat_no_escort(self) -> None:
        """High threat without escort should eventually destroy missions."""
        from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode
        from stochastic_warfare.logistics.transport import TransportConfig, TransportEngine

        destroyed = 0
        for seed in range(50):
            eng = TransportEngine(EventBus(), _rng(seed), config=TransportConfig())
            route = [SupplyRoute("r1", "a", "b", TransportMode.ROAD, 50000, 10.0, 5.0)]
            mission = eng.dispatch(
                "m1", TransportMode.ROAD, route,
                {"I": {"food": 1.0}}, "a", "b", _TS,
            )
            eng.update(1.0, timestamp=_TS, escort_strength=0.0, threat_level=0.9)
            if mission.status == "DESTROYED":
                destroyed += 1
        assert destroyed > 5  # Some should be destroyed

    def test_escort_reduces_interdiction(self) -> None:
        """Strong escort should protect convoys better."""
        from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode
        from stochastic_warfare.logistics.transport import TransportConfig, TransportEngine

        def run_trials(escort: float) -> int:
            destroyed = 0
            for seed in range(100):
                eng = TransportEngine(EventBus(), _rng(seed), config=TransportConfig())
                route = [SupplyRoute("r1", "a", "b", TransportMode.ROAD, 50000, 10.0, 5.0)]
                eng.dispatch("m1", TransportMode.ROAD, route, {"I": {"food": 1.0}}, "a", "b", _TS)
                eng.update(1.0, timestamp=_TS, escort_strength=escort, threat_level=0.5)
                missions = list(eng._missions.values())
                if missions and missions[0].status == "DESTROYED":
                    destroyed += 1
            return destroyed

        no_escort = run_trials(0.0)
        full_escort = run_trials(1.0)
        assert full_escort < no_escort


# ========================================================================
# 12b-4: Erlang Medical Service
# ========================================================================


class TestErlangMedical:
    def _make_engine(self, k=1):
        from stochastic_warfare.logistics.medical import (
            MedicalConfig, MedicalEngine, MedicalFacility, MedicalFacilityType,
        )
        cfg = MedicalConfig(erlang_shape_k=k)
        eng = MedicalEngine(EventBus(), _rng(), config=cfg)
        eng.register_facility(MedicalFacility(
            facility_id="aid1", facility_type=MedicalFacilityType.AID_STATION,
            position=Position(0, 0, 0),
            capacity=20, current_patients=0, side="blue",
        ))
        return eng

    def test_k1_deterministic(self) -> None:
        """k=1 (default) returns fixed treatment time."""
        eng = self._make_engine(k=1)
        record = eng.receive_casualty("u1", "m1", severity=1, facility_id="aid1")
        eng.update(0.1)
        # Treatment should have started with deterministic time
        assert record.status == "IN_TREATMENT"
        assert record.estimated_completion is not None
        # For k=1, time should be exactly treatment_hours_minor (2.0)
        expected = 0.1 + 2.0  # sim_time + treatment
        assert record.estimated_completion == pytest.approx(expected)

    def test_k3_stochastic_mean_preserved(self) -> None:
        """k=3 should produce treatment times with same mean."""
        from stochastic_warfare.logistics.medical import (
            MedicalConfig, MedicalEngine, MedicalFacility, MedicalFacilityType,
        )
        cfg = MedicalConfig(erlang_shape_k=3)
        treatment_times = []
        for seed in range(100):
            eng = MedicalEngine(EventBus(), _rng(seed), config=cfg)
            eng.register_facility(MedicalFacility(
                facility_id="aid1", facility_type=MedicalFacilityType.AID_STATION,
                position=Position(0, 0, 0),
                capacity=20, current_patients=0, side="blue",
            ))
            record = eng.receive_casualty("u1", "m1", severity=1, facility_id="aid1")
            eng.update(0.01)
            if record.estimated_completion is not None:
                treatment_times.append(record.estimated_completion - 0.01)

        mean_time = np.mean(treatment_times)
        assert mean_time == pytest.approx(2.0, abs=0.3)  # Expected mean = 2.0 hours

    def test_k3_lower_variance(self) -> None:
        """k=3 should produce lower variance than k=1 (if k=1 were stochastic).
        Since k=1 is deterministic (returns fixed value), k=3 still has some variance."""
        from stochastic_warfare.logistics.medical import (
            MedicalConfig, MedicalEngine, MedicalFacility, MedicalFacilityType,
        )
        cfg = MedicalConfig(erlang_shape_k=3)
        treatment_times = []
        for seed in range(100):
            eng = MedicalEngine(EventBus(), _rng(seed), config=cfg)
            eng.register_facility(MedicalFacility(
                facility_id="aid1", facility_type=MedicalFacilityType.AID_STATION,
                position=Position(0, 0, 0),
                capacity=20, current_patients=0, side="blue",
            ))
            record = eng.receive_casualty("u1", "m1", severity=1, facility_id="aid1")
            eng.update(0.01)
            if record.estimated_completion is not None:
                treatment_times.append(record.estimated_completion - 0.01)

        std = np.std(treatment_times)
        # Erlang(3, 2/3) has std = 2/sqrt(3) ≈ 1.15, but mean is 2.0
        # std should be positive but bounded
        assert 0.0 < std < 2.0

    def test_default_k1(self) -> None:
        from stochastic_warfare.logistics.medical import MedicalConfig
        cfg = MedicalConfig()
        assert cfg.erlang_shape_k == 1
