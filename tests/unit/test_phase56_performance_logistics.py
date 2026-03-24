"""Phase 56: Performance & Logistics — ~35 tests.

Tests cover:
- 56a: Rally STRtree spatial index (rally + rout cascade)
- 56b: Maintenance → readiness wiring (breakdown, DISABLED, movement speed)
- 56c: Per-era medical/engineering + per-subsystem Weibull shapes
- 56d: VLS reload enforcement (exhaustion logging + checkpoint)
- 56e: Naval posture detection modifiers
- 56f: Gas casualty calibration fields
- 56g: Blockade throughput reduction
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.logistics.maintenance import (
    MaintenanceConfig,
    MaintenanceEngine,
    MaintenanceStatus,
)
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.calibration import CalibrationSchema

from tests.conftest import TS, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEED = 42


def _make_unit(
    entity_id: str,
    side: str = "blue",
    easting: float = 0.0,
    northing: float = 0.0,
    status: UnitStatus = UnitStatus.ACTIVE,
    domain: Domain = Domain.GROUND,
    speed: float = 0.0,
    support_type: str | None = None,
    naval_posture: int | None = None,
) -> Unit:
    """Minimal Unit with position for morale/engagement tests."""
    u = object.__new__(Unit)
    object.__setattr__(u, "entity_id", entity_id)
    object.__setattr__(u, "side", side)
    object.__setattr__(u, "position", Position(easting, northing, 0.0))
    object.__setattr__(u, "status", status)
    object.__setattr__(u, "domain", domain)
    object.__setattr__(u, "speed", speed)
    object.__setattr__(u, "personnel", ["p1", "p2", "p3", "p4"])
    object.__setattr__(u, "equipment", ["e1"])
    if support_type is not None:
        object.__setattr__(u, "support_type", SimpleNamespace(name=support_type))
    if naval_posture is not None:
        object.__setattr__(u, "naval_posture", naval_posture)
    return u


def _make_rout_engine(cascade_radius_m: float = 500.0):
    """Minimal RoutEngine mock with config and callable methods."""
    engine = SimpleNamespace()
    engine._config = SimpleNamespace(cascade_radius_m=cascade_radius_m)
    engine.check_rally = MagicMock(return_value=False)
    engine.rout_cascade = MagicMock(return_value=[])
    return engine


def _make_morale_machine():
    """Mock morale machine that returns STEADY by default."""
    machine = MagicMock()
    machine.check_transition = MagicMock(return_value=MoraleState.STEADY)
    return machine


# =========================================================================
# 56f: Gas casualty calibration fields
# =========================================================================


class TestGasCasualtyCalibration:
    """CalibrationSchema gas casualty fields."""

    def test_defaults_match_hardcoded(self):
        """Default values match previous hardcoded 0.1 floor, 0.8 scaling."""
        cal = CalibrationSchema()
        assert cal.gas_casualty_floor == 0.1
        assert cal.gas_protection_scaling == 0.8

    def test_custom_floor_raises_minimum(self):
        """Custom floor raises the minimum gas casualty modifier."""
        cal = CalibrationSchema(gas_casualty_floor=0.3, gas_protection_scaling=0.8)
        # With full protection (1.0): max(0.3, 1.0 - 1.0 * 0.8) = max(0.3, 0.2) = 0.3
        result = max(cal.gas_casualty_floor, 1.0 - 1.0 * cal.gas_protection_scaling)
        assert result == pytest.approx(0.3)

    def test_custom_scaling_changes_protection(self):
        """Custom scaling changes how much protection matters."""
        cal = CalibrationSchema(gas_casualty_floor=0.1, gas_protection_scaling=0.5)
        # With 0.5 protection: max(0.1, 1.0 - 0.5 * 0.5) = max(0.1, 0.75) = 0.75
        result = max(cal.gas_casualty_floor, 1.0 - 0.5 * cal.gas_protection_scaling)
        assert result == pytest.approx(0.75)


# =========================================================================
# 56c: Weibull per-subsystem CalibrationSchema field
# =========================================================================


class TestWeibullCalibration:
    """CalibrationSchema subsystem_weibull_shapes field."""

    def test_default_empty(self):
        cal = CalibrationSchema()
        assert cal.subsystem_weibull_shapes == {}

    def test_custom_shapes(self):
        cal = CalibrationSchema(
            subsystem_weibull_shapes={"engine": 1.5, "electronics": 1.2},
        )
        assert cal.subsystem_weibull_shapes["engine"] == 1.5

    def test_get_accessor(self):
        cal = CalibrationSchema(
            subsystem_weibull_shapes={"engine": 1.5},
        )
        result = cal.get("subsystem_weibull_shapes", {})
        assert result == {"engine": 1.5}


# =========================================================================
# 56a: Rally STRtree spatial index
# =========================================================================


class TestRallySTRtree:
    """Rally + cascade via STRtree spatial index."""

    def _make_battle_manager(self):
        from stochastic_warfare.simulation.battle import BattleManager
        bus = EventBus()
        return BattleManager(event_bus=bus)

    def _make_ctx(self, morale_states, morale_machine=None, rout_engine=None, cal=None):
        return SimpleNamespace(
            morale_machine=morale_machine or _make_morale_machine(),
            morale_states=morale_states,
            calibration=cal or CalibrationSchema(),
            rout_engine=rout_engine,
        )

    def test_rally_succeeds_with_friendlies_nearby(self):
        """Routing unit rallies when nearby active friendlies exist."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=600.0)
        rout.check_rally.return_value = True

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=100, northing=100)
        friendly = _make_unit("u2", status=UnitStatus.ACTIVE, easting=200, northing=100)
        morale_states = {"u1": MoraleState.ROUTED, "u2": MoraleState.STEADY}
        ctx = self._make_ctx(morale_states, rout_engine=rout)

        bm._execute_morale(
            ctx, {"blue": [routing, friendly]}, {"blue": []}, TS,
        )

        rout.check_rally.assert_called_once()
        args = rout.check_rally.call_args
        assert args[0][1] >= 1  # nearby_count >= 1

    def test_rally_fails_with_no_friendlies(self):
        """Routing unit does not rally when alone."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=600.0)
        rout.check_rally.return_value = False

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=100, northing=100)
        morale_states = {"u1": MoraleState.ROUTED}
        ctx = self._make_ctx(morale_states, rout_engine=rout)

        bm._execute_morale(ctx, {"blue": [routing]}, {"blue": []}, TS)

        rout.check_rally.assert_called_once()
        args = rout.check_rally.call_args
        assert args[0][1] == 0  # nearby_count == 0

    def test_rally_leader_bonus(self):
        """HQ unit nearby sets leader_present flag."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=600.0)
        rout.check_rally.return_value = True

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=100, northing=100)
        hq = _make_unit("u2", status=UnitStatus.ACTIVE, easting=150, northing=100,
                        support_type="HQ")
        morale_states = {"u1": MoraleState.ROUTED, "u2": MoraleState.STEADY}
        ctx = self._make_ctx(morale_states, rout_engine=rout)

        bm._execute_morale(ctx, {"blue": [routing, hq]}, {"blue": []}, TS)

        rout.check_rally.assert_called_once()
        assert rout.check_rally.call_args[0][2] is True  # leader_present

    def test_rally_beyond_radius(self):
        """Friendlies beyond cascade_radius_m are not counted."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=100.0)
        rout.check_rally.return_value = False

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=0, northing=0)
        far = _make_unit("u2", status=UnitStatus.ACTIVE, easting=500, northing=500)
        morale_states = {"u1": MoraleState.ROUTED, "u2": MoraleState.STEADY}
        ctx = self._make_ctx(morale_states, rout_engine=rout)

        bm._execute_morale(ctx, {"blue": [routing, far]}, {"blue": []}, TS)

        rout.check_rally.assert_called_once()
        assert rout.check_rally.call_args[0][1] == 0  # nearby_count

    def test_cascade_within_radius_triggers(self):
        """Rout cascade queries units within radius."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=600.0)

        # morale_machine must return ROUTED for the routing unit so it stays
        # in the newly_routed list after check_transition
        mm = _make_morale_machine()
        def _transition(unit_id, **kw):
            if unit_id == "u1":
                return MoraleState.ROUTED
            return MoraleState.STEADY
        mm.check_transition.side_effect = _transition

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=100, northing=100)
        nearby = _make_unit("u2", status=UnitStatus.ACTIVE, easting=200, northing=100)
        morale_states = {"u1": MoraleState.ROUTED, "u2": MoraleState.STEADY}
        ctx = self._make_ctx(morale_states, morale_machine=mm, rout_engine=rout)

        bm._execute_morale(ctx, {"blue": [routing, nearby]}, {"blue": []}, TS)

        rout.rout_cascade.assert_called_once()
        call_kwargs = rout.rout_cascade.call_args[1]
        assert "u2" in call_kwargs.get("distances_m", {})

    def test_cascade_beyond_radius_excluded(self):
        """Units beyond cascade radius are not in cascade distances."""
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=100.0)

        mm = _make_morale_machine()
        def _transition(unit_id, **kw):
            if unit_id == "u1":
                return MoraleState.ROUTED
            return MoraleState.STEADY
        mm.check_transition.side_effect = _transition

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=0, northing=0)
        far = _make_unit("u2", status=UnitStatus.ACTIVE, easting=5000, northing=5000)
        morale_states = {"u1": MoraleState.ROUTED, "u2": MoraleState.STEADY}
        ctx = self._make_ctx(morale_states, morale_machine=mm, rout_engine=rout)

        bm._execute_morale(ctx, {"blue": [routing, far]}, {"blue": []}, TS)

        rout.rout_cascade.assert_called_once()
        # distances dict should be empty — far unit is outside radius
        call_kwargs = rout.rout_cascade.call_args
        distances = call_kwargs[1].get("distances_m", {})
        assert "u2" not in distances

    def test_multi_unit_distance_regression(self):
        """Regression: all nearby units are counted, not just the last.

        The Phase 42c bug had an indentation error that only checked the
        last unit's distance. Verify multiple units are counted.
        """
        bm = self._make_battle_manager()
        rout = _make_rout_engine(cascade_radius_m=600.0)
        rout.check_rally.return_value = True

        routing = _make_unit("u1", status=UnitStatus.ROUTING, easting=100, northing=100)
        f1 = _make_unit("u2", status=UnitStatus.ACTIVE, easting=150, northing=100)
        f2 = _make_unit("u3", status=UnitStatus.ACTIVE, easting=200, northing=100)
        f3 = _make_unit("u4", status=UnitStatus.ACTIVE, easting=250, northing=100)
        morale_states = {
            "u1": MoraleState.ROUTED,
            "u2": MoraleState.STEADY,
            "u3": MoraleState.STEADY,
            "u4": MoraleState.STEADY,
        }
        ctx = self._make_ctx(morale_states, rout_engine=rout)

        bm._execute_morale(
            ctx, {"blue": [routing, f1, f2, f3]}, {"blue": []}, TS,
        )

        rout.check_rally.assert_called_once()
        assert rout.check_rally.call_args[0][1] == 3  # all 3 counted


# =========================================================================
# 56e: Naval posture detection modifiers
# =========================================================================


class TestNavalPostureDetection:
    """Naval posture → detection range multiplier."""

    def test_anchored_increases_detection(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_DETECT_MULT
        assert _NAVAL_POSTURE_DETECT_MULT[0] == 1.2  # ANCHORED

    def test_underway_baseline(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_DETECT_MULT
        assert _NAVAL_POSTURE_DETECT_MULT[1] == 1.0  # UNDERWAY

    def test_transit_reduces_detection(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_DETECT_MULT
        assert _NAVAL_POSTURE_DETECT_MULT[2] == 0.85  # TRANSIT

    def test_battle_stations_increases_detection(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_DETECT_MULT
        assert _NAVAL_POSTURE_DETECT_MULT[3] == 1.3  # BATTLE_STATIONS


# =========================================================================
# 56b: Maintenance → readiness wiring
# =========================================================================


class TestMaintenanceReadiness:
    """Maintenance breakdown → readiness → DISABLED + movement speed."""

    def test_breakdown_reduces_readiness(self):
        """Equipment breakdown reduces unit readiness."""
        bus = EventBus()
        rng = make_rng(_SEED)
        cfg = MaintenanceConfig(base_mtbf_hours=0.001)  # very low MTBF
        engine = MaintenanceEngine(bus, rng, config=cfg)
        engine.register_equipment("u1", ["eq1", "eq2"])

        # Run enough updates to cause a breakdown
        for _ in range(100):
            engine.update(dt_hours=1.0)
        readiness = engine.get_unit_readiness("u1")
        assert readiness < 1.0

    def test_readiness_zero_disables(self):
        """Unit with all equipment broken has readiness 0.0."""
        bus = EventBus()
        rng = make_rng(_SEED)
        engine = MaintenanceEngine(bus, rng)
        engine.register_equipment("u1", ["eq1"])

        # Force breakdown
        rec = engine.get_record("u1", "eq1")
        rec.status = MaintenanceStatus.AWAITING_PARTS
        rec.condition = 0.0

        assert engine.get_unit_readiness("u1") == 0.0

    def test_repair_restores_readiness(self):
        """Completing repair restores readiness."""
        bus = EventBus()
        rng = make_rng(_SEED)
        cfg = MaintenanceConfig(repair_time_hours=1.0)
        engine = MaintenanceEngine(bus, rng, config=cfg)
        engine.register_equipment("u1", ["eq1"])

        rec = engine.get_record("u1", "eq1")
        rec.status = MaintenanceStatus.AWAITING_PARTS
        rec.condition = 0.0
        assert engine.get_unit_readiness("u1") == 0.0

        engine.start_repair("u1", "eq1", spare_parts_available=10.0)
        engine.complete_repairs(dt_hours=2.0)
        assert engine.get_unit_readiness("u1") > 0.0

    def test_unregistered_unit_readiness(self):
        """Unregistered units return readiness 1.0."""
        bus = EventBus()
        rng = make_rng(_SEED)
        engine = MaintenanceEngine(bus, rng)
        assert engine.get_unit_readiness("nonexistent") == 1.0

    def test_campaign_maintenance_delegates(self):
        """CampaignManager._run_maintenance delegates to engine."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        clock = SimulationClock(
            start=TS, tick_duration=timedelta(seconds=10),
        )
        maint = MagicMock()
        ctx = SimpleNamespace(
            maintenance_engine=maint,
            weather_engine=None,
            clock=clock,
        )

        cm = CampaignManager.__new__(CampaignManager)
        cm._run_maintenance(ctx, dt=60.0)

        maint.update.assert_called_once()
        maint.complete_repairs.assert_called_once()

    def test_no_maintenance_engine_no_error(self):
        """No maintenance engine → _run_maintenance is a no-op."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        ctx = SimpleNamespace(maintenance_engine=None)
        cm = CampaignManager.__new__(CampaignManager)
        cm._run_maintenance(ctx, dt=60.0)  # should not raise


# =========================================================================
# 56c: Per-era medical/engineering + per-subsystem Weibull
# =========================================================================


class TestEraOverrides:
    """Era-specific physics_overrides for medical/engineering."""

    def test_modern_default_medical(self):
        """Modern era has no medical overrides → defaults apply."""
        from stochastic_warfare.core.era import MODERN_ERA_CONFIG
        po = MODERN_ERA_CONFIG.physics_overrides
        assert "treatment_hours_minor" not in po

    def test_ww2_medical_overrides(self):
        from stochastic_warfare.core.era import WW2_ERA_CONFIG
        po = WW2_ERA_CONFIG.physics_overrides
        assert po["treatment_hours_minor"] == 3.0
        assert po["treatment_hours_serious"] == 12.0
        assert po["treatment_hours_critical"] == 36.0
        assert po["repair_time_hours"] == 6.0

    def test_ww1_medical_overrides(self):
        from stochastic_warfare.core.era import WW1_ERA_CONFIG
        po = WW1_ERA_CONFIG.physics_overrides
        assert po["treatment_hours_minor"] == 4.0
        assert po["treatment_hours_serious"] == 24.0

    def test_napoleonic_medical_overrides(self):
        from stochastic_warfare.core.era import NAPOLEONIC_ERA_CONFIG
        po = NAPOLEONIC_ERA_CONFIG.physics_overrides
        assert po["treatment_hours_minor"] == 8.0
        assert po["treatment_hours_serious"] == 48.0

    def test_ancient_medical_overrides(self):
        from stochastic_warfare.core.era import ANCIENT_MEDIEVAL_ERA_CONFIG
        po = ANCIENT_MEDIEVAL_ERA_CONFIG.physics_overrides
        assert po["treatment_hours_minor"] == 24.0
        assert po["treatment_hours_serious"] == 168.0
        assert po["treatment_hours_critical"] == 336.0


class TestWeibullPerSubsystem:
    """Per-subsystem Weibull shape parameters."""

    def test_set_subsystem_shapes(self):
        bus = EventBus()
        rng = make_rng(_SEED)
        engine = MaintenanceEngine(bus, rng)
        engine.set_subsystem_shapes({"engine": 1.5, "electronics": 1.2})
        assert engine._subsystem_shapes["engine"] == 1.5

    def test_prefix_categorization(self):
        """Equipment IDs are categorized by prefix."""
        bus = EventBus()
        rng = make_rng(_SEED)
        engine = MaintenanceEngine(bus, rng)
        engine.set_subsystem_shapes({"engine": 1.5, "electronics": 1.2})

        assert engine._get_subsystem_shape("engine_diesel") == 1.5
        assert engine._get_subsystem_shape("radar_search") == 1.2
        assert engine._get_subsystem_shape("elec_fire_ctrl") == 1.2

    def test_empty_shapes_fallback(self):
        """Empty shapes dict falls back to global weibull_shape_k."""
        bus = EventBus()
        rng = make_rng(_SEED)
        cfg = MaintenanceConfig(weibull_shape_k=1.3)
        engine = MaintenanceEngine(bus, rng, config=cfg)
        assert engine._get_subsystem_shape("anything") == 1.3

    def test_unknown_prefix_fallback(self):
        """Unknown prefix falls back to global shape."""
        bus = EventBus()
        rng = make_rng(_SEED)
        cfg = MaintenanceConfig(weibull_shape_k=1.0)
        engine = MaintenanceEngine(bus, rng, config=cfg)
        engine.set_subsystem_shapes({"engine": 1.5})
        assert engine._get_subsystem_shape("unknown_thing") == 1.0


# =========================================================================
# 56d: VLS reload enforcement
# =========================================================================


class TestVLSEnforcement:
    """VLS exhaustion enforcement and checkpoint persistence."""

    def test_vls_checkpoint_persistence(self):
        """_vls_launches is persisted in get_state/set_state."""
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(event_bus=EventBus())
        bm._vls_launches["unit_1"] = 8

        state = bm.get_state()
        assert state["vls_launches"] == {"unit_1": 8}

        bm2 = BattleManager(event_bus=EventBus())
        bm2.set_state(state)
        assert bm2._vls_launches == {"unit_1": 8}

    def test_vls_empty_by_default(self):
        """Empty VLS launches dict on fresh BattleManager."""
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(event_bus=EventBus())
        state = bm.get_state()
        assert state["vls_launches"] == {}

    def test_vls_set_state_missing_key(self):
        """set_state handles missing vls_launches gracefully."""
        from stochastic_warfare.simulation.battle import BattleManager

        bm = BattleManager(event_bus=EventBus())
        bm._vls_launches["x"] = 5
        bm.set_state({"battles": {}, "next_battle_id": 0})
        assert bm._vls_launches == {}


# =========================================================================
# 56g: Blockade throughput reduction
# =========================================================================


class TestBlockadeThroughput:
    """Blockade degrades SEA transport routes."""

    def _make_supply_network(self):
        from stochastic_warfare.logistics.supply_network import (
            SupplyNetworkEngine,
            SupplyRoute,
            TransportMode,
        )
        bus = EventBus()
        rng = make_rng(_SEED)
        engine = SupplyNetworkEngine(bus, rng)
        # Add routes directly
        engine._routes["sea_1"] = SupplyRoute(
            route_id="sea_1",
            from_node="port_a",
            to_node="port_b",
            transport_mode=TransportMode.SEA,
            distance_m=100_000,
            capacity_tons_per_hour=50.0,
            base_transit_time_hours=10.0,
            condition=1.0,
        )
        engine._routes["road_1"] = SupplyRoute(
            route_id="road_1",
            from_node="depot_a",
            to_node="depot_b",
            transport_mode=TransportMode.ROAD,
            distance_m=50_000,
            capacity_tons_per_hour=20.0,
            base_transit_time_hours=5.0,
            condition=1.0,
        )
        return engine

    def test_blockade_degrades_sea_routes(self):
        """Blockade effectiveness degrades SEA route condition."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        supply = self._make_supply_network()
        blockade = SimpleNamespace(
            blockade_id="bl1",
            sea_zone_ids=["zone_a"],
        )
        disruption = SimpleNamespace(
            active_blockades=lambda: [blockade],
            check_blockade=lambda zone_id: 0.5,
        )
        ctx = SimpleNamespace(
            disruption_engine=disruption,
            supply_network_engine=supply,
        )
        cm = CampaignManager.__new__(CampaignManager)
        cm._update_supply_network(ctx, dt=60.0)

        # SEA route should be degraded
        assert supply._routes["sea_1"].condition < 1.0

    def test_blockade_does_not_affect_road(self):
        """Blockade only degrades SEA routes, not ROAD."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        supply = self._make_supply_network()
        blockade = SimpleNamespace(
            blockade_id="bl1",
            sea_zone_ids=["zone_a"],
        )
        disruption = SimpleNamespace(
            active_blockades=lambda: [blockade],
            check_blockade=lambda zone_id: 0.5,
        )
        ctx = SimpleNamespace(
            disruption_engine=disruption,
            supply_network_engine=supply,
        )
        cm = CampaignManager.__new__(CampaignManager)
        cm._update_supply_network(ctx, dt=60.0)

        assert supply._routes["road_1"].condition == 1.0

    def test_no_blockade_no_degradation(self):
        """No active blockades → routes unaffected."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        supply = self._make_supply_network()
        disruption = SimpleNamespace(
            active_blockades=lambda: [],
            check_blockade=lambda zone_id: 0.0,
        )
        ctx = SimpleNamespace(
            disruption_engine=disruption,
            supply_network_engine=supply,
        )
        cm = CampaignManager.__new__(CampaignManager)
        cm._update_supply_network(ctx, dt=60.0)

        assert supply._routes["sea_1"].condition == 1.0

    def test_no_supply_network_no_error(self):
        """Blockade with no supply network engine → no crash."""
        from stochastic_warfare.simulation.campaign import CampaignManager

        blockade = SimpleNamespace(
            blockade_id="bl1",
            sea_zone_ids=["zone_a"],
        )
        disruption = SimpleNamespace(
            active_blockades=lambda: [blockade],
            check_blockade=lambda zone_id: 0.3,
        )
        ctx = SimpleNamespace(
            disruption_engine=disruption,
            supply_network_engine=None,
        )
        cm = CampaignManager.__new__(CampaignManager)
        cm._update_supply_network(ctx, dt=60.0)  # should not raise
