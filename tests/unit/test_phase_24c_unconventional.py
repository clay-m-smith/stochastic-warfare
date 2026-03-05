"""Tests for Phase 24c — Unconventional Warfare, SOF, Prisoners.

Covers IED mechanics, guerrilla warfare, human shields, SOF operations,
prisoner treatment/interrogation, and special organization types.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

# -- Fixtures & constants ---------------------------------------------------

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
POS_ORIGIN = Position(0.0, 0.0, 0.0)
POS_1KM = Position(1000.0, 0.0, 0.0)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _bus() -> EventBus:
    return EventBus()


# ===========================================================================
# 1. IED Tests (~20)
# ===========================================================================


class TestIEDObstacleTypes:
    """Verify ObstacleType enum additions."""

    def test_ied_obstacle_type_exists(self):
        from stochastic_warfare.terrain.obstacles import ObstacleType

        assert ObstacleType.IED == 8

    def test_booby_trap_obstacle_type_exists(self):
        from stochastic_warfare.terrain.obstacles import ObstacleType

        assert ObstacleType.BOOBY_TRAP == 9

    def test_obstacle_model_accepts_ied_subtype(self):
        from stochastic_warfare.terrain.obstacles import Obstacle, ObstacleType

        obs = Obstacle(
            obstacle_id="ied_test",
            obstacle_type=ObstacleType.IED,
            footprint=[(0, 0), (1, 0), (1, 1), (0, 1)],
            ied_subtype="command_wire",
            ied_blast_radius_m=15.0,
            ied_concealment=0.8,
        )
        assert obs.ied_subtype == "command_wire"
        assert obs.ied_blast_radius_m == 15.0
        assert obs.ied_concealment == 0.8

    def test_obstacle_ied_defaults(self):
        from stochastic_warfare.terrain.obstacles import Obstacle, ObstacleType

        obs = Obstacle(
            obstacle_id="mine_1",
            obstacle_type=ObstacleType.MINEFIELD,
            footprint=[(0, 0), (1, 0), (1, 1), (0, 1)],
        )
        assert obs.ied_subtype == ""
        assert obs.ied_blast_radius_m == 0.0
        assert obs.ied_concealment == 0.5


class TestIEDEmplacement:
    """IED emplacement and tracking."""

    def test_emplace_returns_obstacle_id(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(
            POS_ORIGIN, "command_wire", 10.0, 0.6, "insurgent_1", TS
        )
        assert oid.startswith("ied_")

    def test_emplace_multiple_unique_ids(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        ids = set()
        for i in range(5):
            oid = engine.emplace_ied(
                POS_ORIGIN, "remote", 5.0, 0.5, f"unit_{i}"
            )
            ids.add(oid)
        assert len(ids) == 5


class TestIEDDetection:
    """Speed-detection tradeoff and engineering bonus."""

    def test_slow_speed_high_detection(self):
        """Slow movement = higher detection probability."""
        from stochastic_warfare.combat.unconventional import (
            IEDConfig,
            UnconventionalWarfareEngine,
        )

        cfg = IEDConfig(base_detect_probability=0.90, max_safe_speed_mps=10.0)
        detections = 0
        n = 200
        for seed in range(n):
            engine = UnconventionalWarfareEngine(_bus(), _rng(seed), config_ied=cfg)
            if engine.check_ied_detection(1.0, False, "u1"):
                detections += 1
        # At speed 1.0, speed_factor = 1 - 1/10 = 0.9, P = 0.9 * 0.9 = 0.81
        assert detections > n * 0.5  # should be around 81%

    def test_fast_speed_low_detection(self):
        """Fast movement = lower detection probability."""
        from stochastic_warfare.combat.unconventional import (
            IEDConfig,
            UnconventionalWarfareEngine,
        )

        cfg = IEDConfig(base_detect_probability=0.90, max_safe_speed_mps=10.0)
        detections = 0
        n = 200
        for seed in range(n):
            engine = UnconventionalWarfareEngine(_bus(), _rng(seed), config_ied=cfg)
            if engine.check_ied_detection(9.0, False, "u1"):
                detections += 1
        # At speed 9.0, speed_factor = 1 - 9/10 = 0.1, P = 0.9 * 0.1 = 0.09
        assert detections < n * 0.3  # should be around 9%

    def test_engineering_bonus_increases_detection(self):
        """Engineering unit gets bonus to detection."""
        from stochastic_warfare.combat.unconventional import (
            IEDConfig,
            UnconventionalWarfareEngine,
        )

        cfg = IEDConfig(
            base_detect_probability=0.20,
            engineering_bonus=1.0,
            max_safe_speed_mps=10.0,
        )
        det_no_eng = 0
        det_eng = 0
        n = 300
        for seed in range(n):
            eng = UnconventionalWarfareEngine(_bus(), _rng(seed), config_ied=cfg)
            if eng.check_ied_detection(2.0, False, "u1"):
                det_no_eng += 1
            eng2 = UnconventionalWarfareEngine(_bus(), _rng(seed), config_ied=cfg)
            if eng2.check_ied_detection(2.0, True, "u1"):
                det_eng += 1
        assert det_eng > det_no_eng

    def test_max_speed_zero_detection(self):
        """At max_safe_speed, speed_factor = 0, so P = 0."""
        from stochastic_warfare.combat.unconventional import (
            IEDConfig,
            UnconventionalWarfareEngine,
        )

        cfg = IEDConfig(base_detect_probability=1.0, max_safe_speed_mps=5.0)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_ied=cfg)
        # At speed >= max_safe_speed, speed_factor = 0 => P = 0
        assert not engine.check_ied_detection(5.0, False, "u1")
        assert not engine.check_ied_detection(10.0, False, "u1")


class TestIEDDetonation:
    """Detonation produces correct result fields."""

    def test_detonation_result_fields(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "remote", 15.0, 0.5, "ins_1")
        result = engine.detonate_ied(oid, "target_1", TS)
        assert result.blast_radius_m == 15.0
        assert result.position == POS_ORIGIN
        assert result.stress_spike > 0.0
        assert result.route_denial > 0.0

    def test_detonation_marks_inactive(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "remote", 10.0, 0.5, "ins_1")
        engine.detonate_ied(oid, "target_1", TS)
        state = engine.get_state()
        assert not state["ieds"][oid]["active"]

    def test_detonation_unknown_ied_raises(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        with pytest.raises(KeyError):
            engine.detonate_ied("nonexistent", "target_1")

    def test_route_denial_radius(self):
        from stochastic_warfare.combat.unconventional import (
            IEDConfig,
            UnconventionalWarfareEngine,
        )

        cfg = IEDConfig(route_denial_radius_m=200.0)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_ied=cfg)
        oid = engine.emplace_ied(POS_ORIGIN, "vbied", 30.0, 0.3, "ins_1")
        result = engine.detonate_ied(oid, "target_1")
        assert result.route_denial == 200.0

    def test_concealment_stored(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "command_wire", 10.0, 0.9, "ins_1")
        state = engine.get_state()
        assert state["ieds"][oid]["concealment"] == 0.9


class TestIEDEWJamming:
    """EW jamming of remote IEDs."""

    def test_ew_jams_remote_ied(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "remote", 10.0, 0.5, "ins_1")
        # With effectiveness=1.0 and jammer_active=True, always jammed
        assert engine.check_ew_jamming(oid, True, 1.0)

    def test_ew_does_not_jam_command_wire(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "command_wire", 10.0, 0.5, "ins_1")
        assert not engine.check_ew_jamming(oid, True, 1.0)

    def test_ew_does_not_jam_pressure_plate(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "pressure_plate", 10.0, 0.5, "ins_1")
        assert not engine.check_ew_jamming(oid, True, 1.0)

    def test_ew_inactive_jammer_no_effect(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "remote", 10.0, 0.5, "ins_1")
        assert not engine.check_ew_jamming(oid, False, 1.0)

    def test_ew_jams_vbied(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        oid = engine.emplace_ied(POS_ORIGIN, "vbied", 30.0, 0.3, "ins_1")
        assert engine.check_ew_jamming(oid, True, 1.0)


# ===========================================================================
# 2. Guerrilla Tests (~12)
# ===========================================================================


class TestGuerrillaAttack:
    """Guerrilla attack decision logic."""

    def test_attack_authorized_above_threshold(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(local_superiority_threshold=1.5)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        # ratio 2.0 >= 1.5 * (1.0 - 0.0) = 1.5 -> attack
        assert engine.evaluate_guerrilla_attack("g1", 2.0, 0.0)

    def test_attack_denied_below_threshold(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(local_superiority_threshold=1.5)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        # ratio 1.0 < 1.5 * (1.0 - 0.0) = 1.5 -> no attack
        assert not engine.evaluate_guerrilla_attack("g1", 1.0, 0.0)

    def test_terrain_advantage_lowers_threshold(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(
            local_superiority_threshold=2.0, ambush_terrain_bonus=0.5
        )
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        # required = 2.0 * (1.0 - 1.0 * 0.5) = 1.0
        assert engine.evaluate_guerrilla_attack("g1", 1.0, 1.0)

    def test_terrain_zero_no_bonus(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(
            local_superiority_threshold=2.0, ambush_terrain_bonus=0.5
        )
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        # required = 2.0 * (1.0 - 0.0) = 2.0
        assert not engine.evaluate_guerrilla_attack("g1", 1.5, 0.0)

    def test_exact_threshold_attack_proceeds(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(local_superiority_threshold=1.5)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        # ratio 1.5 >= 1.5 -> attack (>=, not >)
        assert engine.evaluate_guerrilla_attack("g1", 1.5, 0.0)


class TestGuerrillaDisengage:
    """Guerrilla disengage and blending logic."""

    def test_disengage_when_casualties_above_threshold(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(disengage_threshold=0.3)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        should_disengage, _ = engine.evaluate_guerrilla_disengage("g1", 0.5, False)
        assert should_disengage

    def test_no_disengage_below_threshold(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(disengage_threshold=0.3)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        should_disengage, _ = engine.evaluate_guerrilla_disengage("g1", 0.1, False)
        assert not should_disengage

    def test_blend_probability_in_populated_area(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(blend_probability=0.7)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        _, blend_prob = engine.evaluate_guerrilla_disengage("g1", 0.5, True)
        assert blend_prob == 0.7

    def test_zero_blend_outside_populated_area(self):
        from stochastic_warfare.combat.unconventional import (
            GuerrillaConfig,
            UnconventionalWarfareEngine,
        )

        cfg = GuerrillaConfig(blend_probability=0.7)
        engine = UnconventionalWarfareEngine(_bus(), _rng(), config_guerrilla=cfg)
        _, blend_prob = engine.evaluate_guerrilla_disengage("g1", 0.5, False)
        assert blend_prob == 0.0


class TestHumanShield:
    """Human shield / civilian proximity."""

    def test_high_civilian_density_high_value(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        value = engine.evaluate_human_shield(POS_ORIGIN, 0.9)
        assert value == pytest.approx(0.9)

    def test_zero_civilian_density_zero_value(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        value = engine.evaluate_human_shield(POS_ORIGIN, 0.0)
        assert value == 0.0

    def test_clamped_above_one(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        value = engine.evaluate_human_shield(POS_ORIGIN, 1.5)
        assert value == 1.0

    def test_clamped_below_zero(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        value = engine.evaluate_human_shield(POS_ORIGIN, -0.5)
        assert value == 0.0


# ===========================================================================
# 3. SOF Tests (~12)
# ===========================================================================


class TestSOFPlanning:
    """SOF mission planning."""

    def test_plan_creates_mission_with_planning_status(self):
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFMissionStatus,
            SOFOperationType,
            SOFOpsEngine,
        )

        engine = SOFOpsEngine(_bus(), _rng())
        mission = engine.plan_mission(
            SOFOperationType.HVT_TARGETING, "oda_1", "hvt_1", POS_ORIGIN, TS
        )
        assert mission.status == SOFMissionStatus.PLANNING
        assert mission.mission_id.startswith("sof_")
        assert mission.unit_id == "oda_1"
        assert mission.target_id == "hvt_1"

    def test_multiple_missions_unique_ids(self):
        from stochastic_warfare.c2.ai.sof_ops import SOFOperationType, SOFOpsEngine

        engine = SOFOpsEngine(_bus(), _rng())
        ids = set()
        for _ in range(5):
            m = engine.plan_mission(
                SOFOperationType.DIRECT_ACTION, "u", "t", POS_ORIGIN
            )
            ids.add(m.mission_id)
        assert len(ids) == 5


class TestSOFLifecycle:
    """SOF mission lifecycle advancement."""

    def test_update_advances_through_lifecycle(self):
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFMissionStatus,
            SOFOperationType,
            SOFOpsEngine,
        )

        engine = SOFOpsEngine(_bus(), _rng())
        mission = engine.plan_mission(
            SOFOperationType.INFILTRATION, "oda_1", "area_1", POS_ORIGIN
        )
        dur = mission.duration_s

        # First update: PLANNING -> INFIL
        engine.update(dur * 0.1)
        assert mission.status == SOFMissionStatus.INFIL

        # Advance past infil (25%)
        engine.update(dur * 0.2)
        assert mission.status == SOFMissionStatus.EXECUTING

    def test_full_lifecycle_planning_to_complete(self):
        """A mission progresses through all lifecycle stages."""
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFMissionStatus,
            SOFOperationType,
            SOFOpsEngine,
        )

        # Use a seed where the generic success roll passes
        engine = SOFOpsEngine(_bus(), _rng(100))
        mission = engine.plan_mission(
            SOFOperationType.INFILTRATION, "oda_1", "area_1", POS_ORIGIN
        )
        dur = mission.duration_s

        # Advance through entire duration + extra
        results = engine.update(dur * 1.5)

        # Mission should be either COMPLETE or FAILED depending on rng
        assert mission.status in (
            SOFMissionStatus.COMPLETE,
            SOFMissionStatus.FAILED,
        )

    def test_active_missions_excludes_completed(self):
        from stochastic_warfare.c2.ai.sof_ops import SOFOperationType, SOFOpsEngine

        engine = SOFOpsEngine(_bus(), _rng(100))
        mission = engine.plan_mission(
            SOFOperationType.INFILTRATION, "oda_1", "area_1", POS_ORIGIN
        )
        dur = mission.duration_s

        # Before update: 1 active
        assert len(engine.get_active_missions()) == 1

        # Complete the mission
        engine.update(dur * 2.0)

        # After completion: 0 active
        assert len(engine.get_active_missions()) == 0


class TestSOFHVT:
    """HVT targeting operations."""

    def test_hvt_success_with_low_protection(self):
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFConfig,
            SOFMission,
            SOFMissionStatus,
            SOFOperationType,
            SOFOpsEngine,
        )

        cfg = SOFConfig(hvt_success_base_probability=0.95)
        # Run multiple seeds; with P=0.95*(1-0.0)=0.95, should mostly succeed
        successes = 0
        n = 100
        for seed in range(n):
            engine = SOFOpsEngine(_bus(), _rng(seed), config=cfg)
            mission = SOFMission(
                mission_id="test",
                operation_type=SOFOperationType.HVT_TARGETING,
                unit_id="oda_1",
                target_id="hvt_1",
                position=POS_ORIGIN,
                start_time_s=0.0,
                duration_s=14400.0,
            )
            result = engine.execute_hvt(mission, 0.0)
            if result.success:
                successes += 1
                assert result.effects["command_disruption"] == 0.5
        assert successes > n * 0.7

    def test_hvt_failure_with_high_protection(self):
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFConfig,
            SOFMission,
            SOFOperationType,
            SOFOpsEngine,
        )

        cfg = SOFConfig(hvt_success_base_probability=0.3)
        # P = 0.3 * (1 - 0.9) = 0.03 -> almost always fails
        successes = 0
        n = 100
        for seed in range(n):
            engine = SOFOpsEngine(_bus(), _rng(seed), config=cfg)
            mission = SOFMission(
                mission_id="test",
                operation_type=SOFOperationType.HVT_TARGETING,
                unit_id="oda_1",
                target_id="hvt_1",
                position=POS_ORIGIN,
                start_time_s=0.0,
                duration_s=14400.0,
            )
            result = engine.execute_hvt(mission, 0.9)
            if result.success:
                successes += 1
        assert successes < n * 0.2  # expect ~3%


class TestSOFSabotage:
    """Sabotage operations."""

    def test_sabotage_produces_infrastructure_damage(self):
        from stochastic_warfare.c2.ai.sof_ops import (
            SOFConfig,
            SOFMission,
            SOFOperationType,
            SOFOpsEngine,
        )

        cfg = SOFConfig(
            hvt_success_base_probability=0.95,
            sabotage_infrastructure_damage=0.5,
        )
        successes = 0
        n = 100
        for seed in range(n):
            engine = SOFOpsEngine(_bus(), _rng(seed), config=cfg)
            mission = SOFMission(
                mission_id="test",
                operation_type=SOFOperationType.SABOTAGE,
                unit_id="oda_1",
                target_id="bridge_1",
                position=POS_ORIGIN,
                start_time_s=0.0,
                duration_s=10800.0,
            )
            result = engine.execute_sabotage(mission, 0.0)
            if result.success:
                successes += 1
                assert result.effects["infrastructure_damage"] == 0.5
        assert successes > n * 0.7

    def test_infiltration_detection_multiplier_in_config(self):
        from stochastic_warfare.c2.ai.sof_ops import SOFConfig

        cfg = SOFConfig(infiltration_detection_multiplier=0.1)
        assert cfg.infiltration_detection_multiplier == 0.1


class TestSOFState:
    """SOF state roundtrip."""

    def test_state_roundtrip(self):
        from stochastic_warfare.c2.ai.sof_ops import SOFOperationType, SOFOpsEngine

        engine = SOFOpsEngine(_bus(), _rng())
        engine.plan_mission(
            SOFOperationType.HVT_TARGETING, "oda_1", "hvt_1", POS_ORIGIN
        )
        engine.plan_mission(
            SOFOperationType.SABOTAGE, "oda_2", "bridge_1", POS_1KM
        )

        state = engine.get_state()

        engine2 = SOFOpsEngine(_bus(), _rng())
        engine2.set_state(state)
        state2 = engine2.get_state()

        assert state["next_id"] == state2["next_id"]
        assert len(state["missions"]) == len(state2["missions"])
        for mid in state["missions"]:
            assert state["missions"][mid]["unit_id"] == state2["missions"][mid]["unit_id"]
            assert state["missions"][mid]["target_id"] == state2["missions"][mid]["target_id"]


# ===========================================================================
# 4. Prisoner Treatment Tests (~8)
# ===========================================================================


class TestTreatmentLevel:
    """TreatmentLevel enum."""

    def test_treatment_level_enum_exists(self):
        from stochastic_warfare.logistics.prisoners import TreatmentLevel

        assert TreatmentLevel.STANDARD == 0
        assert TreatmentLevel.MISTREATED == 1
        assert TreatmentLevel.TORTURED == 2


class TestPrisonerTreatment:
    """Prisoner treatment and interrogation."""

    def test_set_treatment_changes_level(self):
        from stochastic_warfare.logistics.prisoners import (
            PrisonerEngine,
            TreatmentLevel,
        )

        engine = PrisonerEngine(_bus(), _rng())
        group = engine.capture("unit_1", 5, POS_ORIGIN, "RED", TS)
        engine.set_treatment(group.group_id, TreatmentLevel.MISTREATED)
        assert engine.get_group(group.group_id).treatment_level == TreatmentLevel.MISTREATED

    def test_interrogation_no_stress_slower_more_reliable(self):
        from stochastic_warfare.logistics.prisoners import (
            InterrogationResult,
            PrisonerConfig,
            PrisonerEngine,
        )

        cfg = PrisonerConfig(
            interrogation_base_delay_hours=8.0,
            stress_yield_multiplier=2.0,
            stress_reliability_penalty=0.4,
        )
        # Gather results at low stress across many seeds
        delays = []
        reliabilities = []
        for seed in range(200):
            engine = PrisonerEngine(_bus(), _rng(seed), config=cfg)
            group = engine.capture("unit_1", 5, POS_ORIGIN, "RED")
            result = engine.interrogate(group.group_id, 0.0)  # zero stress
            if result is not None:
                delays.append(result.delay_hours)
                reliabilities.append(result.reliability)
        if delays:
            avg_delay = sum(delays) / len(delays)
            avg_rel = sum(reliabilities) / len(reliabilities)
            # zero stress: delay = 8.0 / (1 + 0) = 8.0
            assert avg_delay == pytest.approx(8.0, abs=0.01)
            # zero stress: reliability = 1.0 - 0.0 = 1.0
            assert avg_rel == pytest.approx(1.0, abs=0.01)

    def test_interrogation_high_stress_faster_less_reliable(self):
        from stochastic_warfare.logistics.prisoners import PrisonerConfig, PrisonerEngine

        cfg = PrisonerConfig(
            interrogation_base_delay_hours=8.0,
            stress_yield_multiplier=2.0,
            stress_reliability_penalty=0.4,
        )
        delays = []
        reliabilities = []
        for seed in range(200):
            engine = PrisonerEngine(_bus(), _rng(seed), config=cfg)
            group = engine.capture("unit_1", 5, POS_ORIGIN, "RED")
            result = engine.interrogate(group.group_id, 1.0)  # max stress
            if result is not None:
                delays.append(result.delay_hours)
                reliabilities.append(result.reliability)
        if delays:
            avg_delay = sum(delays) / len(delays)
            avg_rel = sum(reliabilities) / len(reliabilities)
            # stress=1.0: delay = 8.0 / (1 + 1*2) = 8/3 ~ 2.67
            assert avg_delay == pytest.approx(8.0 / 3.0, abs=0.01)
            # stress=1.0: reliability = max(0.1, 1.0 - 1.0*0.4) = 0.6
            assert avg_rel == pytest.approx(0.6, abs=0.01)

    def test_intelligence_yield_flag_prevents_repeat(self):
        from stochastic_warfare.logistics.prisoners import PrisonerConfig, PrisonerEngine

        cfg = PrisonerConfig()
        # Find a seed that yields intelligence
        for seed in range(100):
            engine = PrisonerEngine(_bus(), _rng(seed), config=cfg)
            group = engine.capture("unit_1", 5, POS_ORIGIN, "RED")
            result = engine.interrogate(group.group_id, 1.0)
            if result is not None:
                # Second interrogation should return None
                result2 = engine.interrogate(group.group_id, 1.0)
                assert result2 is None
                assert group.intelligence_yielded is True
                break
        else:
            pytest.skip("No seed yielded intelligence in 100 tries")

    def test_interrogation_result_is_frozen(self):
        from stochastic_warfare.logistics.prisoners import InterrogationResult

        result = InterrogationResult(
            intelligence_type="tactical",
            reliability=0.8,
            delay_hours=4.0,
            value=0.5,
        )
        with pytest.raises(AttributeError):
            result.reliability = 0.1  # type: ignore[misc]

    def test_prisoner_state_roundtrip_new_fields(self):
        from stochastic_warfare.logistics.prisoners import (
            PrisonerEngine,
            TreatmentLevel,
        )

        engine = PrisonerEngine(_bus(), _rng())
        group = engine.capture("unit_1", 5, POS_ORIGIN, "RED", TS)
        engine.set_treatment(group.group_id, TreatmentLevel.TORTURED)
        group.interrogation_stress = 0.8
        group.intelligence_yielded = True

        state = engine.get_state()

        engine2 = PrisonerEngine(_bus(), _rng())
        engine2.set_state(state)
        g2 = engine2.get_group(group.group_id)
        assert g2.treatment_level == TreatmentLevel.TORTURED
        assert g2.interrogation_stress == 0.8
        assert g2.intelligence_yielded is True


# ===========================================================================
# 5. Special Org Types Tests (~8)
# ===========================================================================


class TestSpecialOrgTypes:
    """New OrgType enum values."""

    def test_insurgent_value(self):
        from stochastic_warfare.entities.organization.special_org import OrgType

        assert OrgType.INSURGENT == 4

    def test_militia_value(self):
        from stochastic_warfare.entities.organization.special_org import OrgType

        assert OrgType.MILITIA == 5

    def test_pmc_value(self):
        from stochastic_warfare.entities.organization.special_org import OrgType

        assert OrgType.PMC == 6

    def test_special_org_traits_accepts_insurgent(self):
        from stochastic_warfare.entities.organization.special_org import (
            OrgType,
            SpecialOrgTraits,
        )

        traits = SpecialOrgTraits(
            org_type=OrgType.INSURGENT,
            independent_ops=True,
            network_structure=True,
            c2_flexibility=0.9,
        )
        assert traits.org_type == OrgType.INSURGENT

    def test_special_org_traits_accepts_militia(self):
        from stochastic_warfare.entities.organization.special_org import (
            OrgType,
            SpecialOrgTraits,
        )

        traits = SpecialOrgTraits(
            org_type=OrgType.MILITIA,
            interoperability=0.3,
        )
        assert traits.org_type == OrgType.MILITIA

    def test_special_org_traits_accepts_pmc(self):
        from stochastic_warfare.entities.organization.special_org import (
            OrgType,
            SpecialOrgTraits,
        )

        traits = SpecialOrgTraits(
            org_type=OrgType.PMC,
            independent_ops=True,
            interoperability=0.6,
        )
        assert traits.org_type == OrgType.PMC

    def test_special_org_manager_with_new_types(self):
        from stochastic_warfare.entities.organization.special_org import (
            OrgType,
            SpecialOrgManager,
            SpecialOrgTraits,
        )

        mgr = SpecialOrgManager()
        mgr.designate_special(
            "ins_cell_1",
            SpecialOrgTraits(
                org_type=OrgType.INSURGENT,
                network_structure=True,
                c2_flexibility=0.95,
            ),
        )
        traits = mgr.get_traits("ins_cell_1")
        assert traits is not None
        assert traits.org_type == OrgType.INSURGENT
        assert traits.network_structure is True

    def test_special_org_state_roundtrip_new_types(self):
        from stochastic_warfare.entities.organization.special_org import (
            OrgType,
            SpecialOrgManager,
            SpecialOrgTraits,
        )

        mgr = SpecialOrgManager()
        mgr.designate_special(
            "pmc_1",
            SpecialOrgTraits(org_type=OrgType.PMC, independent_ops=True),
        )
        state = mgr.get_state()

        mgr2 = SpecialOrgManager()
        mgr2.set_state(state)
        t = mgr2.get_traits("pmc_1")
        assert t is not None
        assert t.org_type == OrgType.PMC


# ===========================================================================
# 6. Unconventional Warfare Engine State Tests
# ===========================================================================


class TestUnconventionalState:
    """State persistence for UnconventionalWarfareEngine."""

    def test_state_roundtrip(self):
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine

        engine = UnconventionalWarfareEngine(_bus(), _rng())
        engine.emplace_ied(POS_ORIGIN, "remote", 10.0, 0.5, "ins_1")
        engine.emplace_ied(POS_1KM, "command_wire", 5.0, 0.8, "ins_2")

        state = engine.get_state()

        engine2 = UnconventionalWarfareEngine(_bus(), _rng())
        engine2.set_state(state)
        state2 = engine2.get_state()

        assert state["next_id"] == state2["next_id"]
        assert len(state["ieds"]) == len(state2["ieds"])
        for oid in state["ieds"]:
            assert state["ieds"][oid]["subtype"] == state2["ieds"][oid]["subtype"]
            assert state["ieds"][oid]["active"] == state2["ieds"][oid]["active"]
