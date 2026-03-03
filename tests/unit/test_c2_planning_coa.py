"""Tests for COA development and wargaming (c2.planning.coa).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.c2.events import COASelectedEvent
from stochastic_warfare.c2.orders.types import MissionType
from stochastic_warfare.c2.planning.coa import (
    COA,
    COAConfig,
    COAEngine,
    COAScore,
    COATimeline,
    FireSupportPlan,
    ManeuverType,
    TaskAssignment,
    WargameResult,
)
from stochastic_warfare.c2.planning.mission_analysis import (
    MissionAnalysisResult,
    Task,
    TaskType,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId, Position
from tests.conftest import DEFAULT_SEED, TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(
    unit_id: str = "co_a",
    mission_type: int = MissionType.ATTACK,
) -> MissionAnalysisResult:
    """Create a minimal MissionAnalysisResult for testing."""
    # Build a restated mission that contains the mission type keyword
    try:
        name = MissionType(mission_type).name.lower().replace("_", " ")
    except ValueError:
        name = "attack"

    return MissionAnalysisResult(
        unit_id=unit_id,
        order_id="ord_001",
        timestamp=TS,
        specified_tasks=(Task("t1", TaskType.SPECIFIED, "Attack objective", 0),),
        implied_tasks=(Task("t2", TaskType.IMPLIED, "Suppress overwatchers", 1),),
        essential_tasks=(Task("t1", TaskType.SPECIFIED, "Attack objective", 0),),
        intel_requirements=(),
        risks=(),
        constraints=(),
        key_terrain_positions=(Position(1000, 1000, 0),),
        restated_mission=f"Unit co_a {name}s to accomplish the mission",
    )


def _make_engine(
    event_bus: EventBus | None = None,
    rng: np.random.Generator | None = None,
    config: COAConfig | None = None,
) -> COAEngine:
    """Create a COAEngine with defaults."""
    return COAEngine(
        event_bus=event_bus or EventBus(),
        rng=rng or make_rng(),
        config=config,
    )


def _develop_and_wargame(
    engine: COAEngine,
    unit_id: str = "co_a",
    mission_type: int = MissionType.ATTACK,
    friendly_power: float = 100.0,
    subordinate_ids: list[str] | None = None,
    enemy_power: float = 80.0,
    supply_level: float = 1.0,
    terrain_advantage: float = 0.0,
    echelon: int = 4,
) -> list[COA]:
    """Develop COAs and wargame them all, returning COAs with results."""
    analysis = _make_analysis(unit_id, mission_type)
    subs = subordinate_ids or ["plt_1", "plt_2", "plt_3"]

    coas = engine.develop_coas(
        unit_id=unit_id,
        analysis=analysis,
        friendly_power=friendly_power,
        subordinate_ids=subs,
        contacts=3,
        enemy_power=enemy_power,
        supply_level=supply_level,
        terrain_advantage=terrain_advantage,
        echelon=echelon,
    )

    # Wargame each COA
    from dataclasses import replace
    wargamed: list[COA] = []
    for coa in coas:
        result = engine.wargame_coa(
            coa,
            friendly_power=friendly_power,
            enemy_power=enemy_power,
            supply_level=supply_level,
            terrain_advantage=terrain_advantage,
        )
        wargamed.append(replace(coa, wargame_result=result))

    return wargamed


# ---------------------------------------------------------------------------
# ManeuverType enum
# ---------------------------------------------------------------------------


class TestManeuverType:
    """Tests for ManeuverType enum values."""

    def test_frontal_attack_value(self) -> None:
        assert ManeuverType.FRONTAL_ATTACK == 0

    def test_flanking_value(self) -> None:
        assert ManeuverType.FLANKING == 1

    def test_envelopment_value(self) -> None:
        assert ManeuverType.ENVELOPMENT == 2

    def test_defense_in_depth_value(self) -> None:
        assert ManeuverType.DEFENSE_IN_DEPTH == 5

    def test_all_values_unique(self) -> None:
        values = [m.value for m in ManeuverType]
        assert len(values) == len(set(values))

    def test_count(self) -> None:
        assert len(ManeuverType) == 10


# ---------------------------------------------------------------------------
# Frozen dataclass creation
# ---------------------------------------------------------------------------


class TestTaskAssignment:
    """Tests for TaskAssignment creation."""

    def test_create(self) -> None:
        ta = TaskAssignment(
            subordinate_id="plt_1",
            task_description="Main effort",
            effort_weight=0.6,
        )
        assert ta.subordinate_id == "plt_1"
        assert ta.effort_weight == 0.6
        assert ta.position is None

    def test_with_position(self) -> None:
        pos = Position(100, 200, 0)
        ta = TaskAssignment("plt_1", "Attack", 0.5, position=pos)
        assert ta.position == pos

    def test_frozen(self) -> None:
        ta = TaskAssignment("plt_1", "Attack", 0.5)
        with pytest.raises(AttributeError):
            ta.effort_weight = 0.9  # type: ignore[misc]


class TestFireSupportPlan:
    """Tests for FireSupportPlan creation."""

    def test_create(self) -> None:
        fsp = FireSupportPlan(
            priority_target="OBJ ALPHA",
            allocation=0.8,
            trigger="at_h_hour",
        )
        assert fsp.priority_target == "OBJ ALPHA"
        assert fsp.allocation == 0.8
        assert fsp.trigger == "at_h_hour"


class TestCOATimeline:
    """Tests for COATimeline creation."""

    def test_create(self) -> None:
        tl = COATimeline(
            phase_name="Shape",
            duration_s=3600.0,
            actions=("Suppress", "Fix"),
        )
        assert tl.phase_name == "Shape"
        assert len(tl.actions) == 2


class TestWargameResult:
    """Tests for WargameResult creation."""

    def test_create(self) -> None:
        wr = WargameResult(
            estimated_friendly_losses=0.1,
            estimated_enemy_losses=0.4,
            estimated_duration_s=7200.0,
            probability_of_success=0.75,
            risk_level="LOW",
        )
        assert wr.probability_of_success == 0.75
        assert wr.risk_level == "LOW"


class TestCOAScore:
    """Tests for COAScore creation."""

    def test_create(self) -> None:
        score = COAScore(
            mission_accomplishment=0.8,
            force_preservation=0.7,
            tempo=0.6,
            simplicity=0.9,
            total=0.75,
        )
        assert score.total == 0.75


class TestCOACreation:
    """Tests for COA creation with defaults."""

    def test_minimal(self) -> None:
        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        assert coa.fire_support is None
        assert coa.timeline == ()
        assert coa.wargame_result is None
        assert coa.score is None

    def test_with_all_fields(self) -> None:
        ta = TaskAssignment("plt_1", "Attack", 0.6)
        fsp = FireSupportPlan("OBJ", 0.8, "at_h_hour")
        tl = COATimeline("Shape", 3600.0, ("Suppress",))
        wr = WargameResult(0.1, 0.4, 7200.0, 0.75, "LOW")
        sc = COAScore(0.8, 0.7, 0.6, 0.9, 0.75)

        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(ta,),
            fire_support=fsp,
            timeline=(tl,),
            wargame_result=wr,
            score=sc,
        )
        assert coa.fire_support is not None
        assert len(coa.timeline) == 1


# ---------------------------------------------------------------------------
# develop_coas
# ---------------------------------------------------------------------------


class TestDevelopCOAs:
    """Tests for COAEngine.develop_coas."""

    def test_offensive_produces_correct_maneuver_types(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis(mission_type=MissionType.ATTACK)
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        types = [c.maneuver_type for c in coas]
        assert ManeuverType.FRONTAL_ATTACK in types
        assert ManeuverType.FLANKING in types
        assert ManeuverType.ENVELOPMENT in types

    def test_defensive_produces_correct_types(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis(mission_type=MissionType.DEFEND)
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=5,
            enemy_power=120.0,
            supply_level=1.0,
            terrain_advantage=0.5,
            echelon=6,
        )
        types = [c.maneuver_type for c in coas]
        assert ManeuverType.DEFENSE_IN_DEPTH in types
        assert ManeuverType.MOBILE_DEFENSE in types
        assert ManeuverType.DELAY in types

    def test_respects_max_coas(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        config = COAConfig(max_coas=2)
        engine = COAEngine(event_bus, rng, config)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        assert len(coas) <= 2

    def test_assigns_subordinates(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        for coa in coas:
            assigned_ids = {ta.subordinate_id for ta in coa.task_assignments}
            # Every task assignment should reference a valid subordinate
            assert assigned_ids.issubset({"plt_1", "plt_2"})

    def test_one_subordinate_only_frontal(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1"],
            contacts=2,
            enemy_power=50.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        assert len(coas) == 1
        assert coas[0].maneuver_type == ManeuverType.FRONTAL_ATTACK

    def test_two_subordinates_includes_flanking(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2"],
            contacts=2,
            enemy_power=50.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        types = [c.maneuver_type for c in coas]
        assert ManeuverType.FLANKING in types

    def test_task_assignments_effort_sum(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Task assignment effort weights should sum to approximately 1.0."""
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        for coa in coas:
            total_effort = sum(ta.effort_weight for ta in coa.task_assignments)
            assert 0.9 <= total_effort <= 1.1, (
                f"COA {coa.name}: total effort {total_effort:.2f} not ~1.0"
            )

    def test_defensive_no_mobile_below_battalion(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Mobile defense requires echelon >= battalion (6)."""
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis(mission_type=MissionType.DEFEND)
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=5,
            enemy_power=120.0,
            supply_level=1.0,
            terrain_advantage=0.5,
            echelon=4,  # company -- below battalion
        )
        types = [c.maneuver_type for c in coas]
        assert ManeuverType.MOBILE_DEFENSE not in types

    def test_coa_ids_contain_unit_id(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis(unit_id="co_alpha")
        coas = engine.develop_coas(
            unit_id="co_alpha",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        for coa in coas:
            assert "co_alpha" in coa.coa_id

    def test_offensive_main_effort_directions(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Frontal=0, flanking=90, envelopment=180."""
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        directions = {c.maneuver_type: c.main_effort_direction for c in coas}
        assert directions[ManeuverType.FRONTAL_ATTACK] == 0.0
        assert directions[ManeuverType.FLANKING] == 90.0
        assert directions[ManeuverType.ENVELOPMENT] == 180.0

    def test_each_coa_has_timeline(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        for coa in coas:
            assert len(coa.timeline) == 3  # 3 phases

    def test_each_coa_has_fire_support(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        for coa in coas:
            assert coa.fire_support is not None

    def test_delay_no_terrain_advantage_no_delay_coa(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Delay COA requires terrain_advantage > 0."""
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis(mission_type=MissionType.DEFEND)
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=5,
            enemy_power=120.0,
            supply_level=1.0,
            terrain_advantage=0.0,  # no terrain advantage
            echelon=6,
        )
        types = [c.maneuver_type for c in coas]
        assert ManeuverType.DELAY not in types


# ---------------------------------------------------------------------------
# wargame_coa
# ---------------------------------------------------------------------------


class TestWargameCOA:
    """Tests for COAEngine.wargame_coa."""

    def test_produces_valid_results(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        result = engine.wargame_coa(coa, 100.0, 80.0, 1.0, 0.0)
        assert 0.0 <= result.estimated_friendly_losses <= 1.0
        assert 0.0 <= result.estimated_enemy_losses <= 1.0
        assert 0.0 <= result.probability_of_success <= 1.0
        assert result.estimated_duration_s > 0
        assert result.risk_level in ("LOW", "MODERATE", "HIGH", "EXTREME")

    def test_friendly_advantage_high_success(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """3:1 advantage should yield high probability of success."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        result = engine.wargame_coa(coa, 300.0, 100.0, 1.0, 0.0)
        assert result.probability_of_success > 0.6

    def test_enemy_advantage_low_success(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """1:3 disadvantage should yield low probability."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        result = engine.wargame_coa(coa, 100.0, 300.0, 1.0, 0.0)
        assert result.probability_of_success < 0.4

    def test_supply_shortage_increases_losses(self, event_bus: EventBus) -> None:
        """Low supply should increase friendly losses."""
        rng1 = make_rng(100)
        rng2 = make_rng(100)
        engine1 = COAEngine(event_bus, rng1)
        engine2 = COAEngine(EventBus(), rng2)
        coa = COA(
            coa_id="co_a_coa_0",
            name="Frontal Attack",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        result_good_supply = engine1.wargame_coa(coa, 100.0, 100.0, 1.0, 0.0)
        result_low_supply = engine2.wargame_coa(coa, 100.0, 100.0, 0.3, 0.0)
        assert result_low_supply.estimated_friendly_losses > result_good_supply.estimated_friendly_losses

    def test_terrain_advantage_helps_defender(self, event_bus: EventBus) -> None:
        """Defensive maneuver with terrain should reduce enemy effectiveness."""
        rng1 = make_rng(200)
        rng2 = make_rng(200)
        engine1 = COAEngine(event_bus, rng1)
        engine2 = COAEngine(EventBus(), rng2)
        coa = COA(
            coa_id="co_a_coa_0",
            name="Defense in Depth",
            maneuver_type=ManeuverType.DEFENSE_IN_DEPTH,
            main_effort_direction=0.0,
            task_assignments=(),
        )
        result_no_terrain = engine1.wargame_coa(coa, 100.0, 100.0, 1.0, 0.0)
        result_with_terrain = engine2.wargame_coa(coa, 100.0, 100.0, 1.0, 1.0)
        # Defense in depth reduces enemy power via terrain_defense_mult,
        # so friendly losses should be lower with terrain
        assert result_with_terrain.estimated_friendly_losses <= result_no_terrain.estimated_friendly_losses

    def test_flanking_bonus(self, event_bus: EventBus) -> None:
        """Flanking should outperform frontal for same forces."""
        rng1 = make_rng(300)
        rng2 = make_rng(300)
        engine1 = COAEngine(event_bus, rng1)
        engine2 = COAEngine(EventBus(), rng2)
        frontal = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        flanking = COA(
            coa_id="coa_1", name="Flanking",
            maneuver_type=ManeuverType.FLANKING,
            main_effort_direction=90.0, task_assignments=(),
        )
        r_frontal = engine1.wargame_coa(frontal, 100.0, 100.0, 1.0, 0.0)
        r_flanking = engine2.wargame_coa(flanking, 100.0, 100.0, 1.0, 0.0)
        # Flanking adds bonus to friendly power, so should have better success
        assert r_flanking.probability_of_success > r_frontal.probability_of_success

    def test_envelopment_bonus(self, event_bus: EventBus) -> None:
        """Envelopment should outperform flanking."""
        rng1 = make_rng(400)
        rng2 = make_rng(400)
        engine1 = COAEngine(event_bus, rng1)
        engine2 = COAEngine(EventBus(), rng2)
        flanking = COA(
            coa_id="coa_0", name="Flanking",
            maneuver_type=ManeuverType.FLANKING,
            main_effort_direction=90.0, task_assignments=(),
        )
        envelopment = COA(
            coa_id="coa_1", name="Envelopment",
            maneuver_type=ManeuverType.ENVELOPMENT,
            main_effort_direction=180.0, task_assignments=(),
        )
        r_flanking = engine1.wargame_coa(flanking, 100.0, 100.0, 1.0, 0.0)
        r_envelopment = engine2.wargame_coa(envelopment, 100.0, 100.0, 1.0, 0.0)
        assert r_envelopment.probability_of_success > r_flanking.probability_of_success

    def test_risk_level_extreme(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Heavily outnumbered should produce HIGH or EXTREME risk."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        result = engine.wargame_coa(coa, 50.0, 300.0, 1.0, 0.0)
        assert result.risk_level in ("HIGH", "EXTREME")

    def test_risk_level_low(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Overwhelming advantage should produce LOW risk."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        result = engine.wargame_coa(coa, 500.0, 50.0, 1.0, 0.0)
        assert result.risk_level == "LOW"

    def test_deterministic_same_seed(self, event_bus: EventBus) -> None:
        """Same seed should produce identical wargame results."""
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        engine1 = COAEngine(event_bus, make_rng(42))
        r1 = engine1.wargame_coa(coa, 100.0, 100.0, 1.0, 0.0)

        engine2 = COAEngine(EventBus(), make_rng(42))
        r2 = engine2.wargame_coa(coa, 100.0, 100.0, 1.0, 0.0)

        assert r1.probability_of_success == r2.probability_of_success
        assert r1.estimated_friendly_losses == r2.estimated_friendly_losses

    def test_zero_enemy_power(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Zero enemy should mean zero friendly losses, high success."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        result = engine.wargame_coa(coa, 100.0, 0.0, 1.0, 0.0)
        # With zero enemy, loop should exit immediately
        assert result.estimated_friendly_losses < 0.01
        assert result.probability_of_success > 0.9

    def test_equal_forces(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Equal forces should produce roughly even results."""
        engine = COAEngine(event_bus, rng)
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        result = engine.wargame_coa(coa, 100.0, 100.0, 1.0, 0.0)
        # With equal forces and frontal, success should be near 0.5
        assert 0.3 <= result.probability_of_success <= 0.7


# ---------------------------------------------------------------------------
# compare_coas
# ---------------------------------------------------------------------------


class TestCompareCOAs:
    """Tests for COAEngine.compare_coas."""

    def test_sorts_by_score_descending(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine, friendly_power=100.0, enemy_power=80.0)
        ranked = engine.compare_coas(coas)
        scores = [c.score.total for c in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_sets_score_on_each(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)
        for coa in ranked:
            assert coa.score is not None

    def test_mission_accomplishment_from_probability(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine, friendly_power=200.0, enemy_power=50.0)
        ranked = engine.compare_coas(coas)
        for coa in ranked:
            assert coa.score is not None
            assert coa.wargame_result is not None
            assert coa.score.mission_accomplishment == coa.wargame_result.probability_of_success

    def test_force_preservation_from_losses(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)
        for coa in ranked:
            assert coa.score is not None
            assert coa.wargame_result is not None
            expected = 1.0 - coa.wargame_result.estimated_friendly_losses
            assert abs(coa.score.force_preservation - expected) < 1e-9

    def test_simplicity_higher_for_simpler_maneuvers(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)
        # Find frontal and envelopment
        frontal_score = None
        envelopment_score = None
        for coa in ranked:
            if coa.maneuver_type == ManeuverType.FRONTAL_ATTACK:
                frontal_score = coa.score.simplicity
            elif coa.maneuver_type == ManeuverType.ENVELOPMENT:
                envelopment_score = coa.score.simplicity
        if frontal_score is not None and envelopment_score is not None:
            assert frontal_score > envelopment_score

    def test_custom_weights(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        """Custom score weights should change the total."""
        config = COAConfig(
            score_weights={
                "mission": 1.0,
                "preservation": 0.0,
                "tempo": 0.0,
                "simplicity": 0.0,
            },
        )
        engine = COAEngine(event_bus, rng, config)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)
        for coa in ranked:
            # With only mission weight, total should equal mission_accomplishment
            assert abs(coa.score.total - coa.score.mission_accomplishment) < 1e-9


# ---------------------------------------------------------------------------
# select_coa
# ---------------------------------------------------------------------------


class TestSelectCOA:
    """Tests for COAEngine.select_coa."""

    def test_returns_coa_from_list(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)
        selected = engine.select_coa(ranked, ts=TS)
        assert selected in ranked

    def test_aggressive_bias(self, event_bus: EventBus) -> None:
        """Aggressive commander should more often pick risky COAs.

        Run multiple selections and check tendency.
        """
        # Create COAs with controlled risk levels
        low_risk_coa = COA(
            coa_id="co_a_coa_0", name="Safe",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
            wargame_result=WargameResult(0.05, 0.3, 7200.0, 0.7, "LOW"),
            score=COAScore(0.7, 0.95, 0.5, 0.9, 0.75),
        )
        high_risk_coa = COA(
            coa_id="co_a_coa_1", name="Risky",
            maneuver_type=ManeuverType.ENVELOPMENT,
            main_effort_direction=180.0, task_assignments=(),
            wargame_result=WargameResult(0.35, 0.6, 7200.0, 0.8, "HIGH"),
            score=COAScore(0.8, 0.65, 0.5, 0.5, 0.65),
        )
        ranked = [low_risk_coa, high_risk_coa]

        # Aggressive commander
        risky_count = 0
        n_trials = 200
        for i in range(n_trials):
            engine = COAEngine(EventBus(), make_rng(i))
            selected = engine.select_coa(
                ranked, risk_tolerance=0.9, aggression=0.9, ts=TS,
            )
            if selected.coa_id == "co_a_coa_1":
                risky_count += 1

        # Aggressive commander should pick risky COA more often
        assert risky_count > n_trials * 0.3

    def test_cautious_bias(self, event_bus: EventBus) -> None:
        """Cautious commander should more often pick safe COAs."""
        low_risk_coa = COA(
            coa_id="co_a_coa_0", name="Safe",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
            wargame_result=WargameResult(0.05, 0.3, 7200.0, 0.7, "LOW"),
            score=COAScore(0.7, 0.95, 0.5, 0.9, 0.75),
        )
        high_risk_coa = COA(
            coa_id="co_a_coa_1", name="Risky",
            maneuver_type=ManeuverType.ENVELOPMENT,
            main_effort_direction=180.0, task_assignments=(),
            wargame_result=WargameResult(0.35, 0.6, 7200.0, 0.8, "HIGH"),
            score=COAScore(0.8, 0.65, 0.5, 0.5, 0.65),
        )
        ranked = [low_risk_coa, high_risk_coa]

        # Cautious commander
        safe_count = 0
        n_trials = 200
        for i in range(n_trials):
            engine = COAEngine(EventBus(), make_rng(i))
            selected = engine.select_coa(
                ranked, risk_tolerance=0.1, aggression=0.1, ts=TS,
            )
            if selected.coa_id == "co_a_coa_0":
                safe_count += 1

        # Cautious commander should pick safe COA more often
        assert safe_count > n_trials * 0.4

    def test_publishes_coa_selected_event(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        coas = _develop_and_wargame(engine)
        ranked = engine.compare_coas(coas)

        events_received: list[COASelectedEvent] = []
        event_bus.subscribe(COASelectedEvent, events_received.append)

        engine.select_coa(ranked, ts=TS)
        assert len(events_received) == 1
        evt = events_received[0]
        assert evt.coa_id.startswith("co_a_coa_")
        assert evt.risk_level in ("LOW", "MODERATE", "HIGH", "EXTREME")

    def test_deterministic_same_seed(self, event_bus: EventBus) -> None:
        """Same seed should select the same COA."""
        low_risk_coa = COA(
            coa_id="co_a_coa_0", name="Safe",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
            wargame_result=WargameResult(0.05, 0.3, 7200.0, 0.7, "LOW"),
            score=COAScore(0.7, 0.95, 0.5, 0.9, 0.75),
        )
        high_risk_coa = COA(
            coa_id="co_a_coa_1", name="Risky",
            maneuver_type=ManeuverType.ENVELOPMENT,
            main_effort_direction=180.0, task_assignments=(),
            wargame_result=WargameResult(0.35, 0.6, 7200.0, 0.8, "HIGH"),
            score=COAScore(0.8, 0.65, 0.5, 0.5, 0.65),
        )
        ranked = [low_risk_coa, high_risk_coa]

        engine1 = COAEngine(EventBus(), make_rng(42))
        s1 = engine1.select_coa(ranked, ts=TS)

        engine2 = COAEngine(EventBus(), make_rng(42))
        s2 = engine2.select_coa(ranked, ts=TS)

        assert s1.coa_id == s2.coa_id

    def test_empty_raises(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        with pytest.raises(ValueError, match="No COAs"):
            engine.select_coa([], ts=TS)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end: develop -> wargame -> compare -> select."""

    def test_pipeline(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        engine = COAEngine(event_bus, rng)
        analysis = _make_analysis()

        # 1. Develop
        coas = engine.develop_coas(
            unit_id="co_a",
            analysis=analysis,
            friendly_power=100.0,
            subordinate_ids=["plt_1", "plt_2", "plt_3"],
            contacts=3,
            enemy_power=80.0,
            supply_level=1.0,
            terrain_advantage=0.0,
            echelon=4,
        )
        assert len(coas) >= 1

        # 2. Wargame
        from dataclasses import replace
        wargamed: list[COA] = []
        for coa in coas:
            result = engine.wargame_coa(coa, 100.0, 80.0, 1.0, 0.0)
            wargamed.append(replace(coa, wargame_result=result))

        # 3. Compare
        ranked = engine.compare_coas(wargamed)
        assert all(c.score is not None for c in ranked)

        # 4. Select
        events_received: list[COASelectedEvent] = []
        event_bus.subscribe(COASelectedEvent, events_received.append)

        selected = engine.select_coa(ranked, ts=TS)
        assert selected in ranked
        assert len(events_received) == 1


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    """Tests for get_state / set_state round-trip."""

    def test_round_trip(self, event_bus: EventBus) -> None:
        engine1 = COAEngine(event_bus, make_rng(42))

        # Do some work to advance RNG state
        coa = COA(
            coa_id="coa_0", name="Frontal",
            maneuver_type=ManeuverType.FRONTAL_ATTACK,
            main_effort_direction=0.0, task_assignments=(),
        )
        engine1.wargame_coa(coa, 100.0, 80.0, 1.0, 0.0)

        state = engine1.get_state()

        # Create fresh engine and restore
        engine2 = COAEngine(EventBus(), make_rng(999))
        engine2.set_state(state)

        state2 = engine2.get_state()
        assert state["develop_count"] == state2["develop_count"]
        assert state["wargame_count"] == state2["wargame_count"]

        # RNG should now produce same values
        r1 = engine1.wargame_coa(coa, 100.0, 80.0, 1.0, 0.0)
        r2 = engine2.wargame_coa(coa, 100.0, 80.0, 1.0, 0.0)
        assert r1.probability_of_success == r2.probability_of_success
