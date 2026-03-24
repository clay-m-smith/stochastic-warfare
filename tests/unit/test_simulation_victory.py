"""Tests for simulation victory condition evaluator.

Uses shared fixtures from conftest.py: event_bus, sim_clock.
"""

from __future__ import annotations


import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.scenario import VictoryConditionConfig
from stochastic_warfare.simulation.victory import (
    ObjectiveControlChangedEvent,
    ObjectiveState,
    ObjectiveType,
    VictoryConditionType,
    VictoryDeclaredEvent,
    VictoryEvaluator,
    VictoryEvaluatorConfig,
    VictoryResult,
)

from tests.conftest import make_clock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    eid: str,
    pos: Position,
    side: str,
    status: UnitStatus = UnitStatus.ACTIVE,
) -> Unit:
    """Create a minimal Unit for testing."""
    return Unit(
        entity_id=eid,
        position=pos,
        side=side,
        status=status,
    )


def _make_objective(
    oid: str,
    pos: Position,
    radius: float = 500.0,
) -> ObjectiveState:
    """Create an ObjectiveState for testing."""
    return ObjectiveState(
        objective_id=oid,
        position=pos,
        radius_m=radius,
    )


def _vc(
    ctype: str,
    side: str = "",
    **params: object,
) -> VictoryConditionConfig:
    """Shorthand to build a VictoryConditionConfig."""
    return VictoryConditionConfig(type=ctype, side=side, params=dict(params))


# ---------------------------------------------------------------------------
# TestObjectiveState
# ---------------------------------------------------------------------------


class TestObjectiveState:
    """Tests for the ObjectiveState dataclass."""

    def test_creation(self) -> None:
        obj = ObjectiveState(
            objective_id="obj1",
            position=Position(100.0, 200.0),
            radius_m=300.0,
        )
        assert obj.objective_id == "obj1"
        assert obj.radius_m == 300.0

    def test_defaults(self) -> None:
        obj = _make_objective("obj1", Position(0.0, 0.0))
        assert obj.controlling_side == ""
        assert obj.contested is False

    def test_mutability(self) -> None:
        obj = _make_objective("obj1", Position(0.0, 0.0))
        obj.controlling_side = "blue"
        obj.contested = True
        assert obj.controlling_side == "blue"
        assert obj.contested is True

    def test_position(self) -> None:
        pos = Position(500.0, 600.0, 10.0)
        obj = _make_objective("obj1", pos)
        assert obj.position.easting == 500.0
        assert obj.position.northing == 600.0
        assert obj.position.altitude == 10.0


# ---------------------------------------------------------------------------
# TestVictoryResult
# ---------------------------------------------------------------------------


class TestVictoryResult:
    """Tests for the VictoryResult frozen dataclass."""

    def test_frozen(self) -> None:
        r = VictoryResult(game_over=True, winning_side="blue")
        with pytest.raises(AttributeError):
            r.game_over = False  # type: ignore[misc]

    def test_game_over_true(self) -> None:
        r = VictoryResult(
            game_over=True,
            winning_side="blue",
            condition_type="force_destroyed",
            message="test",
            tick=5,
        )
        assert r.game_over is True
        assert r.winning_side == "blue"
        assert r.condition_type == "force_destroyed"
        assert r.tick == 5

    def test_default_values(self) -> None:
        r = VictoryResult(game_over=False)
        assert r.winning_side == ""
        assert r.condition_type == ""
        assert r.message == ""
        assert r.tick == 0


# ---------------------------------------------------------------------------
# TestVictoryEvaluator — territory_control
# ---------------------------------------------------------------------------


class TestTerritoryControl:
    """Tests for territory_control victory condition."""

    def test_no_objectives_not_game_over(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is False

    def test_single_objective_controlled(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0))
        obj.controlling_side = "blue"
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is True
        assert result.winning_side == "blue"
        assert result.condition_type == "territory_control"

    def test_multiple_objectives_threshold_not_met(self, event_bus: EventBus) -> None:
        obj1 = _make_objective("obj1", Position(100.0, 100.0))
        obj2 = _make_objective("obj2", Position(200.0, 200.0))
        obj1.controlling_side = "blue"
        # obj2 not controlled by blue
        ev = VictoryEvaluator(
            objectives=[obj1, obj2],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is False

    def test_multiple_objectives_threshold_met(self, event_bus: EventBus) -> None:
        obj1 = _make_objective("obj1", Position(100.0, 100.0))
        obj2 = _make_objective("obj2", Position(200.0, 200.0))
        obj1.controlling_side = "blue"
        obj2.controlling_side = "blue"
        ev = VictoryEvaluator(
            objectives=[obj1, obj2],
            conditions=[_vc("territory_control", side="blue", threshold=0.5)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is True

    def test_contested_objective_not_counted(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0))
        obj.controlling_side = "blue"
        obj.contested = True
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is False

    def test_empty_units_no_change(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0))
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        ev.update_objective_control({"blue": [], "red": []})
        # No units in range — retains empty controlling_side
        assert obj.controlling_side == ""

    def test_specific_side_required(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0))
        obj.controlling_side = "red"
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[_vc("territory_control", side="blue", threshold=1.0)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        # Red controls it, but condition requires blue
        assert result.game_over is False

    def test_half_threshold(self, event_bus: EventBus) -> None:
        obj1 = _make_objective("obj1", Position(100.0, 100.0))
        obj2 = _make_objective("obj2", Position(200.0, 200.0))
        obj1.controlling_side = "blue"
        # obj2 uncontrolled
        ev = VictoryEvaluator(
            objectives=[obj1, obj2],
            conditions=[_vc("territory_control", side="blue", threshold=0.5)],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {"blue": [], "red": []}, {}, {})
        assert result.game_over is True
        assert result.winning_side == "blue"


# ---------------------------------------------------------------------------
# TestVictoryEvaluator — force_destroyed
# ---------------------------------------------------------------------------


class TestForceDestroyed:
    """Tests for force_destroyed victory condition."""

    def test_below_threshold_not_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red"),
            _make_unit("r2", Position(0, 0), "red"),
            _make_unit("r3", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed", side="blue")],
            event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        # 1/3 destroyed < 0.7 threshold
        assert result.game_over is False

    def test_at_threshold_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.DESTROYED),
            _make_unit("r2", Position(0, 0), "red", UnitStatus.DESTROYED),
            _make_unit("r3", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed", side="blue")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.7),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        # 3/3 = 1.0 >= 0.7
        assert result.game_over is True
        assert result.winning_side == "blue"

    def test_all_destroyed_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.DESTROYED),
            _make_unit("r2", Position(0, 0), "red", UnitStatus.SURRENDERED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        assert result.game_over is True

    def test_only_counts_destroyed_and_surrendered(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.ACTIVE),
            _make_unit("r2", Position(0, 0), "red", UnitStatus.DISABLED),
            _make_unit("r3", Position(0, 0), "red", UnitStatus.ROUTING),
            _make_unit("r4", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        # Only 1/4 DESTROYED — DISABLED and ROUTING don't count
        assert result.game_over is False

    def test_reports_correct_losing_side(self, event_bus: EventBus) -> None:
        units_blue = [
            _make_unit("b1", Position(0, 0), "blue", UnitStatus.DESTROYED),
            _make_unit("b2", Position(0, 0), "blue", UnitStatus.DESTROYED),
        ]
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.ACTIVE),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": units_blue, "red": units_red}, {}, {},
        )
        assert result.game_over is True
        # blue is destroyed, winner should be red (the other side)
        assert result.winning_side == "red"
        assert "blue" in result.message

    def test_explicit_winning_side(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed", side="blue")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        assert result.game_over is True
        assert result.winning_side == "blue"


# ---------------------------------------------------------------------------
# TestVictoryEvaluator — time_expired
# ---------------------------------------------------------------------------


class TestTimeExpired:
    """Tests for time_expired victory condition."""

    def test_before_duration_not_game_over(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("time_expired", side="blue", max_duration_s=3600)],
            event_bus=event_bus,
        )
        clock = make_clock(tick_s=10.0, elapsed_s=0.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is False

    def test_at_duration_game_over(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("time_expired", side="blue", max_duration_s=100)],
            event_bus=event_bus,
        )
        # Advance clock to exactly 100s
        clock = make_clock(tick_s=10.0, elapsed_s=100.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is True
        assert result.winning_side == "blue"
        assert result.condition_type == "time_expired"

    def test_past_duration_game_over(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("time_expired", side="red", max_duration_s=50)],
            event_bus=event_bus,
        )
        clock = make_clock(tick_s=10.0, elapsed_s=100.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is True
        assert result.winning_side == "red"

    def test_uses_max_duration_s_from_constructor(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("time_expired", side="blue")],
            event_bus=event_bus,
            max_duration_s=100.0,
        )
        clock = make_clock(tick_s=10.0, elapsed_s=100.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is True


# ---------------------------------------------------------------------------
# TestVictoryEvaluator — morale_collapsed
# ---------------------------------------------------------------------------


class TestMoraleCollapsed:
    """Tests for morale_collapsed victory condition."""

    def test_below_threshold_not_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red"),
            _make_unit("r2", Position(0, 0), "red"),
            _make_unit("r3", Position(0, 0), "red"),
        ]
        morale = {
            "r1": MoraleState.STEADY,
            "r2": MoraleState.SHAKEN,
            "r3": MoraleState.ROUTED,
        }
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("morale_collapsed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.6),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, morale, {},
        )
        # 1/3 routed < 0.6 threshold
        assert result.game_over is False

    def test_at_threshold_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red"),
            _make_unit("r2", Position(0, 0), "red"),
            _make_unit("r3", Position(0, 0), "red"),
        ]
        morale = {
            "r1": MoraleState.ROUTED,
            "r2": MoraleState.SURRENDERED,
            "r3": MoraleState.SHAKEN,
        }
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("morale_collapsed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.6),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, morale, {},
        )
        # 2/3 >= 0.6
        assert result.game_over is True
        assert result.condition_type == "morale_collapsed"

    def test_only_counts_routed_and_surrendered(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red"),
            _make_unit("r2", Position(0, 0), "red"),
        ]
        morale = {
            "r1": MoraleState.BROKEN,
            "r2": MoraleState.SHAKEN,
        }
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("morale_collapsed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, morale, {},
        )
        # BROKEN and SHAKEN < ROUTED — neither counts
        assert result.game_over is False

    def test_reports_correct_side(self, event_bus: EventBus) -> None:
        units_blue = [_make_unit("b1", Position(0, 0), "blue")]
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        morale = {
            "b1": MoraleState.SURRENDERED,
            "r1": MoraleState.STEADY,
        }
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("morale_collapsed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": units_blue, "red": units_red}, morale, {},
        )
        assert result.game_over is True
        # blue collapsed → winner is red
        assert result.winning_side == "red"

    def test_integer_morale_values(self, event_bus: EventBus) -> None:
        """Morale states can be passed as raw ints."""
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        morale = {"r1": 3}  # 3 == MoraleState.ROUTED
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("morale_collapsed")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(morale_collapse_threshold=0.5),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, morale, {},
        )
        assert result.game_over is True


# ---------------------------------------------------------------------------
# TestVictoryEvaluator — supply_exhausted
# ---------------------------------------------------------------------------


class TestSupplyExhausted:
    """Tests for supply_exhausted victory condition."""

    def test_above_threshold_not_game_over(self, event_bus: EventBus) -> None:
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        supply = {"r1": 0.8}
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("supply_exhausted")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(supply_exhaustion_threshold=0.2),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, supply,
        )
        assert result.game_over is False

    def test_below_threshold_game_over(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red"),
            _make_unit("r2", Position(0, 0), "red"),
        ]
        supply = {"r1": 0.05, "r2": 0.10}
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("supply_exhausted")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(supply_exhaustion_threshold=0.2),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, supply,
        )
        # avg = 0.075 < 0.2
        assert result.game_over is True
        assert result.condition_type == "supply_exhausted"

    def test_empty_supply_states_skip(self, event_bus: EventBus) -> None:
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("supply_exhausted")],
            event_bus=event_bus,
        )
        clock = make_clock()
        # No supply entries for any unit
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        assert result.game_over is False

    def test_reports_correct_side(self, event_bus: EventBus) -> None:
        units_blue = [_make_unit("b1", Position(0, 0), "blue")]
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        supply = {"b1": 0.01, "r1": 0.9}
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("supply_exhausted")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(supply_exhaustion_threshold=0.2),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": units_blue, "red": units_red}, {}, supply,
        )
        assert result.game_over is True
        # blue is exhausted → winner is red
        assert result.winning_side == "red"

    def test_at_threshold_not_exhausted(self, event_bus: EventBus) -> None:
        """Supply at exactly the threshold is NOT exhausted (< not <=)."""
        units_red = [_make_unit("r1", Position(0, 0), "red")]
        supply = {"r1": 0.2}
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("supply_exhausted")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(supply_exhaustion_threshold=0.2),
        )
        clock = make_clock()
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, supply,
        )
        assert result.game_over is False


# ---------------------------------------------------------------------------
# TestObjectiveControl
# ---------------------------------------------------------------------------


class TestObjectiveControl:
    """Tests for update_objective_control."""

    def test_units_in_range_controls(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        blue_unit = _make_unit("b1", Position(150.0, 150.0), "blue")
        ev.update_objective_control({"blue": [blue_unit], "red": []})
        assert obj.controlling_side == "blue"
        assert obj.contested is False

    def test_both_sides_contested(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        blue_unit = _make_unit("b1", Position(120.0, 120.0), "blue")
        red_unit = _make_unit("r1", Position(130.0, 130.0), "red")
        ev.update_objective_control({"blue": [blue_unit], "red": [red_unit]})
        assert obj.contested is True

    def test_no_units_retains_previous(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        obj.controlling_side = "red"
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        # All units far away
        blue_unit = _make_unit("b1", Position(9000.0, 9000.0), "blue")
        ev.update_objective_control({"blue": [blue_unit], "red": []})
        assert obj.controlling_side == "red"

    def test_distance_calculation(self, event_bus: EventBus) -> None:
        """Unit exactly at radius boundary is within range."""
        obj = _make_objective("obj1", Position(0.0, 0.0), radius=500.0)
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        # Distance = sqrt(300^2 + 400^2) = 500 = radius (on boundary)
        unit = _make_unit("b1", Position(300.0, 400.0), "blue")
        ev.update_objective_control({"blue": [unit], "red": []})
        assert obj.controlling_side == "blue"


# ---------------------------------------------------------------------------
# TestCheckpointRestore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Tests for get_state / set_state."""

    def test_get_state_captures_objectives(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 200.0), radius=300.0)
        obj.controlling_side = "blue"
        obj.contested = True
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        state = ev.get_state()
        assert "objectives" in state
        assert "obj1" in state["objectives"]
        assert state["objectives"]["obj1"]["controlling_side"] == "blue"
        assert state["objectives"]["obj1"]["contested"] is True

    def test_set_state_restores_objectives(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 200.0), radius=300.0)
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        state = {
            "objectives": {
                "obj1": {
                    "objective_id": "obj1",
                    "position": (100.0, 200.0, 0.0),
                    "radius_m": 300.0,
                    "controlling_side": "red",
                    "contested": False,
                },
            },
        }
        ev.set_state(state)
        assert obj.controlling_side == "red"
        assert obj.contested is False

    def test_round_trip(self, event_bus: EventBus) -> None:
        obj1 = _make_objective("obj1", Position(100.0, 200.0), radius=300.0)
        obj2 = _make_objective("obj2", Position(500.0, 600.0), radius=400.0)
        obj1.controlling_side = "blue"
        obj2.controlling_side = "red"
        obj2.contested = True

        ev = VictoryEvaluator(
            objectives=[obj1, obj2],
            conditions=[],
            event_bus=event_bus,
        )
        state = ev.get_state()

        # Reset objectives
        obj1.controlling_side = ""
        obj1.contested = False
        obj2.controlling_side = ""
        obj2.contested = False

        ev.set_state(state)
        assert obj1.controlling_side == "blue"
        assert obj2.controlling_side == "red"
        assert obj2.contested is True

    def test_get_state_includes_position_and_radius(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 200.0, 50.0), radius=300.0)
        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        state = ev.get_state()
        obj_state = state["objectives"]["obj1"]
        assert obj_state["position"] == (100.0, 200.0, 50.0)
        assert obj_state["radius_m"] == 300.0


# ---------------------------------------------------------------------------
# TestEvents
# ---------------------------------------------------------------------------


class TestEvents:
    """Tests for event publishing."""

    def test_victory_declared_event(self, event_bus: EventBus) -> None:
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        captured: list[VictoryDeclaredEvent] = []
        event_bus.subscribe(VictoryDeclaredEvent, captured.append)

        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("force_destroyed", side="blue")],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock()
        ev.evaluate(clock, {"blue": [], "red": units_red}, {}, {})
        assert len(captured) == 1
        assert captured[0].winning_side == "blue"
        assert captured[0].condition_type == "force_destroyed"

    def test_objective_control_changed_event(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        captured: list[ObjectiveControlChangedEvent] = []
        event_bus.subscribe(ObjectiveControlChangedEvent, captured.append)

        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        unit = _make_unit("b1", Position(100.0, 100.0), "blue")
        ev.update_objective_control({"blue": [unit], "red": []})
        assert len(captured) == 1
        assert captured[0].objective_id == "obj1"
        assert captured[0].old_side == ""
        assert captured[0].new_side == "blue"

    def test_no_event_when_control_unchanged(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        obj.controlling_side = "blue"
        captured: list[ObjectiveControlChangedEvent] = []
        event_bus.subscribe(ObjectiveControlChangedEvent, captured.append)

        ev = VictoryEvaluator(
            objectives=[obj],
            conditions=[],
            event_bus=event_bus,
        )
        unit = _make_unit("b1", Position(100.0, 100.0), "blue")
        ev.update_objective_control({"blue": [unit], "red": []})
        # Same side — no change event
        assert len(captured) == 0


# ---------------------------------------------------------------------------
# TestEnums
# ---------------------------------------------------------------------------


class TestEnums:
    """Tests for ObjectiveType and VictoryConditionType enums."""

    def test_objective_type_values(self) -> None:
        assert ObjectiveType.TERRITORY == 0
        assert ObjectiveType.KEY_TERRAIN == 1
        assert ObjectiveType.INFRASTRUCTURE == 2

    def test_victory_condition_type_values(self) -> None:
        assert VictoryConditionType.TERRITORY_CONTROL == 0
        assert VictoryConditionType.FORCE_DESTROYED == 1
        assert VictoryConditionType.TIME_EXPIRED == 2
        assert VictoryConditionType.MORALE_COLLAPSED == 3
        assert VictoryConditionType.SUPPLY_EXHAUSTED == 4


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case tests."""

    def test_get_objective_state_found(self, event_bus: EventBus) -> None:
        obj = _make_objective("obj1", Position(0, 0))
        ev = VictoryEvaluator(
            objectives=[obj], conditions=[], event_bus=event_bus,
        )
        assert ev.get_objective_state("obj1") is obj

    def test_get_objective_state_not_found(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[], conditions=[], event_bus=event_bus,
        )
        assert ev.get_objective_state("nonexistent") is None

    def test_evaluate_returns_first_condition(self, event_bus: EventBus) -> None:
        """When multiple conditions are satisfied, the first one wins."""
        units_red = [
            _make_unit("r1", Position(0, 0), "red", UnitStatus.DESTROYED),
        ]
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[
                _vc("force_destroyed", side="blue"),
                _vc("time_expired", side="red", max_duration_s=1),
            ],
            event_bus=event_bus,
            config=VictoryEvaluatorConfig(force_destroyed_threshold=0.5),
        )
        clock = make_clock(tick_s=10.0, elapsed_s=100.0)
        result = ev.evaluate(
            clock, {"blue": [], "red": units_red}, {}, {},
        )
        # force_destroyed is first in the list
        assert result.condition_type == "force_destroyed"

    def test_no_conditions_not_game_over(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[], conditions=[], event_bus=event_bus,
        )
        clock = make_clock()
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is False

    def test_destroyed_units_not_counted_for_objective_control(
        self, event_bus: EventBus,
    ) -> None:
        """Only ACTIVE units count for objective proximity."""
        obj = _make_objective("obj1", Position(100.0, 100.0), radius=500.0)
        ev = VictoryEvaluator(
            objectives=[obj], conditions=[], event_bus=event_bus,
        )
        destroyed_unit = _make_unit(
            "b1", Position(100.0, 100.0), "blue", UnitStatus.DESTROYED,
        )
        ev.update_objective_control({"blue": [destroyed_unit], "red": []})
        # Destroyed unit should not count
        assert obj.controlling_side == ""

    def test_tick_in_result(self, event_bus: EventBus) -> None:
        ev = VictoryEvaluator(
            objectives=[], conditions=[], event_bus=event_bus,
        )
        clock = make_clock(tick_s=10.0, elapsed_s=50.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.tick == 5  # 50s / 10s per tick

    def test_zero_max_duration_no_time_expiry(self, event_bus: EventBus) -> None:
        """max_duration_s=0 means no time limit."""
        ev = VictoryEvaluator(
            objectives=[],
            conditions=[_vc("time_expired", side="blue")],
            event_bus=event_bus,
            max_duration_s=0.0,
        )
        clock = make_clock(tick_s=10.0, elapsed_s=999990.0)
        result = ev.evaluate(clock, {}, {}, {})
        assert result.game_over is False
