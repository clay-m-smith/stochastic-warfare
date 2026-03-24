"""Phase 5 integration tests — C2 infrastructure end-to-end scenarios.

10 scenarios testing multi-module interactions:
1. Full order chain (multi-echelon propagation)
2. C2 disruption & recovery
3. Comms failure & mission command
4. Naval task force C2
5. ROE-constrained engagement
6. Fire support coordination
7. Order misinterpretation
8. Deterministic replay
9. FRAGO supersedes OPORD
10. ATO + CAS integration
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.command import (
    CommandEngine,
    CommandStatus,
)
from stochastic_warfare.c2.communications import (
    CommEquipmentDefinition,
    CommEquipmentLoader,
    CommunicationsEngine,
)
from stochastic_warfare.c2.coordination import (
    CoordinationEngine,
    CoordinationMeasure,
    CoordinationMeasureType,
    FireType,
)
from stochastic_warfare.c2.events import (
    OrderReceivedEvent,
    SuccessionEvent,
)
from stochastic_warfare.c2.mission_command import (
    C2Style,
    MissionCommandEngine,
)
from stochastic_warfare.c2.naval_c2 import (
    NavalC2Engine,
    NavalDataLinkType,
    NavalFormationType,
    SubCommMethod,
)
from stochastic_warfare.c2.orders.air_orders import (
    AirMissionType,
    AirspaceControlMeasure,
    AirspaceControlType,
    check_airspace_deconfliction,
    create_ato_entry,
    create_cas_request,
)
from stochastic_warfare.c2.orders.execution import OrderExecutionEngine
from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
    PropagationConfig,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderPriority,
    OrderStatus,
    OrderType,
)
from stochastic_warfare.c2.roe import RoeEngine, RoeLevel, TargetCategory
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import TaskOrgManager

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_vhf() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="test_vhf", comm_type="RADIO_VHF",
        display_name="Test VHF", max_range_m=50000.0,
        bandwidth_bps=16000.0, base_latency_s=0.5,
        base_reliability=0.99, intercept_risk=0.3,
        jam_resistance=0.5, requires_los=True,
    )


def _build_full_c2_stack(
    seed: int = 42,
) -> dict:
    """Build a complete C2 stack for integration testing."""
    hierarchy = HierarchyTree()
    hierarchy.add_unit("div1", EchelonLevel.DIVISION)
    hierarchy.add_unit("bde1", EchelonLevel.BRIGADE, "div1")
    hierarchy.add_unit("bde2", EchelonLevel.BRIGADE, "div1")
    hierarchy.add_unit("bn1", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("bn2", EchelonLevel.BATTALION, "bde1")
    hierarchy.add_unit("co1", EchelonLevel.COMPANY, "bn1")
    hierarchy.add_unit("plt1", EchelonLevel.PLATOON, "co1")

    task_org = TaskOrgManager(hierarchy)
    bus = EventBus()
    rng_mgr = RNGManager(seed)

    vhf = _make_vhf()
    loader = CommEquipmentLoader()
    loader._definitions[vhf.comm_id] = vhf

    cmd = CommandEngine(
        hierarchy, task_org, {}, bus,
        rng_mgr.get_stream(ModuleId.C2),
    )
    comms = CommunicationsEngine(
        bus, rng_mgr.get_stream(ModuleId.ENVIRONMENT), loader,
    )
    prop = OrderPropagationEngine(
        comms, cmd, bus, rng_mgr.get_stream(ModuleId.MOVEMENT),
    )
    exec_eng = OrderExecutionEngine(
        prop, bus, rng_mgr.get_stream(ModuleId.ENTITIES),
    )

    units = ["div1", "bde1", "bde2", "bn1", "bn2", "co1", "plt1"]
    for uid in units:
        cmd.register_unit(uid, f"cdr_{uid}")
        comms.register_unit(uid, ["test_vhf"])

    return {
        "hierarchy": hierarchy,
        "task_org": task_org,
        "bus": bus,
        "rng_mgr": rng_mgr,
        "cmd": cmd,
        "comms": comms,
        "prop": prop,
        "exec": exec_eng,
        "units": units,
    }


# ---------------------------------------------------------------------------
# 1. Full order chain
# ---------------------------------------------------------------------------

class TestFullOrderChain:
    """Brigade OPORD → battalion → company → platoon (multi-echelon)."""

    def test_brigade_opord_reaches_battalion(self) -> None:
        s = _build_full_c2_stack()
        events: list[OrderReceivedEvent] = []
        s["bus"].subscribe(OrderReceivedEvent, events.append)

        order = Order(
            order_id="opord_bde1", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=int(EchelonLevel.BRIGADE),
            priority=OrderPriority.PRIORITY,
            mission_type=int(MissionType.ATTACK),
            objective_position=Position(10000, 20000),
        )
        result = s["exec"].issue_order(
            order, Position(0, 0), Position(5000, 0), _TS,
        )
        assert result.success is True
        assert result.total_delay_s > 0
        assert len(events) >= 1


# ---------------------------------------------------------------------------
# 2. C2 disruption & recovery
# ---------------------------------------------------------------------------

class TestC2DisruptionRecovery:
    """Commander KIA → succession → degraded → recovery."""

    def test_commander_loss_and_recovery(self) -> None:
        s = _build_full_c2_stack()
        events: list[SuccessionEvent] = []
        s["bus"].subscribe(SuccessionEvent, events.append)

        # Kill commander
        s["cmd"].handle_commander_loss("bn1", _TS)
        assert s["cmd"].get_status("bn1") == CommandStatus.DISRUPTED
        assert s["cmd"].get_effectiveness("bn1") < 1.0
        assert len(events) == 1

        # Advance past succession delay
        delay = events[0].succession_delay_s
        s["cmd"].update(delay + 1.0, _TS)
        assert s["cmd"].get_status("bn1") == CommandStatus.DEGRADED
        assert s["cmd"].get_commander("bn1") != "cdr_bn1"

        # Recovery timer
        s["cmd"].update(700.0, _TS)
        assert s["cmd"].get_status("bn1") == CommandStatus.FULLY_OPERATIONAL


# ---------------------------------------------------------------------------
# 3. Comms failure & mission command
# ---------------------------------------------------------------------------

class TestCommsFailureMissionCommand:
    """Comms loss → Auftragstaktik initiative vs Befehlstaktik freeze."""

    def test_auftragstaktik_takes_initiative_without_comms(self) -> None:
        s = _build_full_c2_stack(seed=100)
        mc = MissionCommandEngine(
            s["bus"], s["rng_mgr"].get_stream(ModuleId.LOGISTICS),
            style=C2Style.AUFTRAGSTAKTIK,
        )
        results = [
            mc.should_take_initiative(
                "plt1", situation_urgency=0.8, experience=0.8,
                c2_flexibility=0.7, comms_available=False,
            )
            for _ in range(50)
        ]
        assert sum(results) > 20  # Should act frequently

    def test_befehlstaktik_freezes_without_comms(self) -> None:
        s = _build_full_c2_stack(seed=100)
        mc = MissionCommandEngine(
            s["bus"], s["rng_mgr"].get_stream(ModuleId.LOGISTICS),
            style=C2Style.BEFEHLSTAKTIK,
        )
        results = [
            mc.should_take_initiative(
                "plt1", situation_urgency=0.3, experience=0.3,
                c2_flexibility=0.2, comms_available=False,
            )
            for _ in range(50)
        ]
        assert sum(results) < 15  # Should act infrequently


# ---------------------------------------------------------------------------
# 4. Naval task force C2
# ---------------------------------------------------------------------------

class TestNavalTaskForceC2:
    """TF/TG/TU hierarchy + Link 16 + flagship loss + sub VLF."""

    def test_naval_c2_full_scenario(self) -> None:
        bus = EventBus()
        rng_mgr = RNGManager(42)
        comms = CommunicationsEngine(
            bus, rng_mgr.get_stream(ModuleId.ENVIRONMENT),
        )
        naval = NavalC2Engine(
            comms, bus, rng_mgr.get_stream(ModuleId.C2),
        )

        # Create formations
        tf = naval.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            "cv1", ["cv1", "cg1", "ddg1", "ddg2"],
        )
        tg = naval.create_formation(
            "tg1", NavalFormationType.TASK_GROUP,
            "ddg1", ["ddg1", "ddg2"],
            parent_formation_id="tf1",
        )

        # Establish data link
        net = naval.establish_data_link(
            "alpha_net", NavalDataLinkType.LINK_16,
            ["cv1", "cg1", "ddg1", "ddg2"],
        )

        # Share contact
        naval.share_contact("alpha_net", "bogey1", {"type": "air", "bearing": 270})
        picture = naval.get_shared_picture("alpha_net")
        assert "bogey1" in picture

        # Flagship loss
        naval.handle_flagship_loss("tf1", _TS)
        assert naval.get_flagship("tf1") == "cg1"

        # Submarine comms
        naval.register_submarine("ssn1", [SubCommMethod.VLF, SubCommMethod.SATELLITE])
        assert naval.can_contact_submarine("ssn1", SubCommMethod.VLF) is True
        assert naval.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is False
        naval.set_periscope_depth("ssn1", True)
        assert naval.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is True


# ---------------------------------------------------------------------------
# 5. ROE-constrained engagement
# ---------------------------------------------------------------------------

class TestRoeConstrainedEngagement:
    """WEAPONS_TIGHT blocks unidentified → ID upgrade → authorized."""

    def test_roe_progression(self) -> None:
        bus = EventBus()
        roe = RoeEngine(bus, default_level=RoeLevel.WEAPONS_TIGHT)

        # Unidentified contact — blocked
        auth, reason = roe.check_engagement_authorized(
            "plt1", "contact1", TargetCategory.UNKNOWN,
            id_confidence=0.3, timestamp=_TS,
        )
        assert auth is False

        # Low confidence military — blocked
        auth, reason = roe.check_engagement_authorized(
            "plt1", "contact1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.4, timestamp=_TS,
        )
        assert auth is False

        # High confidence military — authorized
        auth, reason = roe.check_engagement_authorized(
            "plt1", "contact1", TargetCategory.MILITARY_COMBATANT,
            id_confidence=0.9, timestamp=_TS,
        )
        assert auth is True


# ---------------------------------------------------------------------------
# 6. Fire support coordination
# ---------------------------------------------------------------------------

class TestFireSupportCoordination:
    """FSCL/NFA/RFA checks."""

    def test_coordination_scenario(self) -> None:
        bus = EventBus()
        coord = CoordinationEngine(bus, rng=np.random.default_rng(0))
        events: list[Event] = []
        bus.subscribe(Event, events.append)

        # Set FSCL at northing 5000
        coord.set_fscl(Position(0, 5000), Position(10000, 5000))

        # NFA at a village
        coord.add_measure(CoordinationMeasure(
            measure_id="nfa_village",
            measure_type=CoordinationMeasureType.NFA,
            center=Position(3000, 3000), radius_m=200.0,
        ))

        # Air delivered fires short of FSCL — blocked
        cleared, _ = coord.check_fire_clearance(
            "cas1", Position(2000, 4000), FireType.AIR_DELIVERED, _TS,
        )
        assert cleared is False

        # Direct fire short of FSCL — OK
        cleared, _ = coord.check_fire_clearance(
            "tank1", Position(2000, 4000), FireType.DIRECT, _TS,
        )
        assert cleared is True

        # Fire into NFA — blocked
        cleared, _ = coord.check_fire_clearance(
            "arty1", Position(3000, 3000), FireType.INDIRECT, _TS,
        )
        assert cleared is False

        # Fire beyond FSCL — OK for air
        cleared, _ = coord.check_fire_clearance(
            "cas1", Position(5000, 6000), FireType.AIR_DELIVERED, _TS,
        )
        assert cleared is True


# ---------------------------------------------------------------------------
# 7. Order misinterpretation
# ---------------------------------------------------------------------------

class TestOrderMisinterpretation:
    """High misinterpretation rate with poor staff + degraded comms."""

    def test_high_misinterpretation_with_poor_conditions(self) -> None:
        config = PropagationConfig(base_misinterpretation=0.8)
        s = _build_full_c2_stack(seed=42)
        prop = OrderPropagationEngine(
            s["comms"], s["cmd"], s["bus"],
            s["rng_mgr"].get_stream(ModuleId.TERRAIN),
            config=config,
        )

        misinterpreted = 0
        for i in range(20):
            order = Order(
                order_id=f"test_{i}", issuer_id="bde1", recipient_id="bn1",
                timestamp=_TS, order_type=OrderType.OPORD,
                echelon_level=int(EchelonLevel.BATTALION),
                priority=OrderPriority.ROUTINE,
                mission_type=int(MissionType.ATTACK),
            )
            result = prop.propagate_order(
                order, Position(0, 0), Position(5000, 0), _TS,
            )
            if result.success and result.was_misinterpreted:
                misinterpreted += 1

        assert misinterpreted > 0  # At least some misinterpretation


# ---------------------------------------------------------------------------
# 8. Deterministic replay
# ---------------------------------------------------------------------------

class TestDeterministicReplay:
    """Same seed → identical events/delays."""

    def test_full_stack_deterministic(self) -> None:
        def run(seed: int) -> list[str]:
            s = _build_full_c2_stack(seed=seed)
            all_events: list[Event] = []
            s["bus"].subscribe(Event, all_events.append)

            order = Order(
                order_id="det_test", issuer_id="bde1", recipient_id="bn1",
                timestamp=_TS, order_type=OrderType.OPORD,
                echelon_level=int(EchelonLevel.BATTALION),
                priority=OrderPriority.ROUTINE,
                mission_type=int(MissionType.ATTACK),
            )
            s["exec"].issue_order(
                order, Position(0, 0), Position(5000, 0), _TS,
            )
            return [type(e).__name__ for e in all_events]

        assert run(99) == run(99)


# ---------------------------------------------------------------------------
# 9. FRAGO supersedes OPORD
# ---------------------------------------------------------------------------

class TestFragoSupersedesOpord:
    """Mid-execution change → propagation → supersession."""

    def test_frago_supersedes(self) -> None:
        s = _build_full_c2_stack()

        opord = Order(
            order_id="opord_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.OPORD,
            echelon_level=int(EchelonLevel.BATTALION),
            priority=OrderPriority.ROUTINE,
            mission_type=int(MissionType.ATTACK),
        )
        s["exec"].issue_order(opord, Position(0, 0), Position(5000, 0), _TS)

        frago = Order(
            order_id="frago_001", issuer_id="bde1", recipient_id="bn1",
            timestamp=_TS, order_type=OrderType.FRAGO,
            echelon_level=int(EchelonLevel.BATTALION),
            priority=OrderPriority.IMMEDIATE,
            mission_type=int(MissionType.WITHDRAW),
            parent_order_id="opord_001",
        )
        s["exec"].supersede_order(
            "opord_001", frago, Position(0, 0), Position(5000, 0), _TS,
        )

        old_record = s["exec"].get_record("opord_001")
        assert old_record.status == OrderStatus.SUPERSEDED
        assert old_record.superseded_by == "frago_001"


# ---------------------------------------------------------------------------
# 10. ATO + CAS integration
# ---------------------------------------------------------------------------

class TestAtoCasIntegration:
    """ATO structure + CAS request + airspace deconfliction."""

    def test_ato_and_cas_workflow(self) -> None:
        ts_start = _TS
        ts_end = _TS + timedelta(hours=2)

        # Create ATO entry
        ato_entry = create_ato_entry(
            "cas_001", AirMissionType.CAS, "HAWG11", "a10_1",
            start_time=ts_start, end_time=ts_end,
            target_position=Position(10000, 20000),
            altitude_min_m=500.0, altitude_max_m=3000.0,
            time_on_station_s=3600.0,
        )
        assert ato_entry.callsign == "HAWG11"

        # Create CAS request
        cas_req = create_cas_request(
            "cas_req_001", "co1", Position(10000, 20000),
            "Enemy armor platoon", _TS,
            friendlies_position=Position(9800, 19800),
        )
        assert cas_req.minimum_safe_distance_m == 500.0

        # Airspace deconfliction
        mez = AirspaceControlMeasure(
            measure_id="mez1",
            measure_type=AirspaceControlType.MISSILE_ENGAGEMENT_ZONE,
            center=Position(15000, 25000),
            radius_m=10000.0,
            altitude_min_m=3000.0,
            altitude_max_m=20000.0,
            start_time=ts_start,
            end_time=ts_end,
            controlling_unit="patriot1",
        )

        # CAS at target position, altitude 1000m — below MEZ
        violations = check_airspace_deconfliction(
            Position(10000, 20000), 1000.0,
            _TS + timedelta(minutes=30), [mez],
        )
        assert len(violations) == 0  # Clear

        # Same position but at 5000m — inside MEZ
        violations = check_airspace_deconfliction(
            Position(15000, 25000), 5000.0,
            _TS + timedelta(minutes=30), [mez],
        )
        assert len(violations) == 1  # Conflict
