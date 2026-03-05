"""Phase 25b — Battle loop OODA fix tests.

Tests that the OBSERVE phase uses real morale/supply data, caches
the assessment, and the DECIDE phase retrieves the cached assessment
plus real commander personality.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

_MINIMAL_SIDES = [
    {"side": "blue", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
    {"side": "red", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
]


def _minimal_config() -> CampaignScenarioConfig:
    return CampaignScenarioConfig.model_validate({
        "name": "test",
        "date": "2024-06-15",
        "duration_hours": 1.0,
        "terrain": {"width_m": 1000, "height_m": 1000, "cell_size_m": 100},
        "sides": _MINIMAL_SIDES,
    })


def _make_unit(entity_id: str, side: str = "blue") -> Unit:
    return Unit(
        entity_id=entity_id,
        unit_type="infantry_platoon",
        side=side,
        position=Position(100.0, 100.0, 0.0),
        speed=5.0,
    )


def _make_ctx(**overrides: Any) -> SimulationContext:
    return SimulationContext(
        config=overrides.pop("config", _minimal_config()),
        clock=SimulationClock(start=TS, tick_duration=timedelta(seconds=10)),
        rng_manager=RNGManager(42),
        event_bus=EventBus(),
        **overrides,
    )


def _make_bm() -> BattleManager:
    return BattleManager(EventBus())


# =========================================================================
# 1. Assessment cache
# =========================================================================


class TestAssessmentCache:
    """Assessment cache for OBSERVE → DECIDE pipeline."""

    def test_cache_initialized_empty(self) -> None:
        bm = _make_bm()
        assert bm._cached_assessments == {}

    def test_observe_caches_assessment(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessment = MagicMock()
        mock_assessor = MagicMock()
        mock_assessor.assess.return_value = mock_assessment

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=mock_assessor,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": [_make_unit("e1", "red")]},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)
        assert "u1" in bm._cached_assessments
        assert bm._cached_assessments["u1"] is mock_assessment

    def test_decide_retrieves_cached_assessment(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessment = MagicMock()
        mock_assessment.force_ratio = 2.0
        mock_assessment.supply_level = 0.8
        mock_assessment.morale_level = 0.9
        mock_assessment.intel_quality = 0.6
        mock_assessment.c2_effectiveness = 1.0
        bm._cached_assessments["u1"] = mock_assessment

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        # decide() should have been called with the cached assessment
        call_args = mock_decision.decide.call_args
        assert call_args[1]["assessment"] is mock_assessment

    def test_decide_fallback_when_no_cache(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        # No cached assessment

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        # decide() should still be called, with assessment=None
        call_args = mock_decision.decide.call_args
        assert call_args[1]["assessment"] is None

    def test_cache_not_in_get_state(self) -> None:
        bm = _make_bm()
        bm._cached_assessments["u1"] = MagicMock()
        state = bm.get_state()
        # Cache is transient — should NOT be in state
        assert "cached_assessments" not in state

    def test_multiple_units_cached_independently(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessor = MagicMock()
        assess1 = MagicMock()
        assess2 = MagicMock()
        mock_assessor.assess.side_effect = [assess1, assess2]

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=mock_assessor,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={
                "blue": [_make_unit("u1"), _make_unit("u2")],
                "red": [_make_unit("e1", "red")],
            },
            morale_states={},
        )
        bm._process_ooda_completions(
            ctx,
            [("u1", OODAPhase.OBSERVE), ("u2", OODAPhase.OBSERVE)],
            TS,
        )
        assert bm._cached_assessments["u1"] is assess1
        assert bm._cached_assessments["u2"] is assess2

    def test_cache_updates_on_new_observe(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        old_assessment = MagicMock()
        bm._cached_assessments["u1"] = old_assessment

        new_assessment = MagicMock()
        mock_assessor = MagicMock()
        mock_assessor.assess.return_value = new_assessment

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=mock_assessor,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": [_make_unit("e1", "red")]},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)
        assert bm._cached_assessments["u1"] is new_assessment

    def test_cache_persists_across_ticks(self) -> None:
        bm = _make_bm()
        bm._cached_assessments["u1"] = MagicMock()
        # Cache should survive between ticks (no automatic clearing)
        assert "u1" in bm._cached_assessments


# =========================================================================
# 2. Real morale
# =========================================================================


class TestRealMorale:
    """Morale level derived from MoraleState enum."""

    def test_steady_is_1(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        ctx = _make_ctx(morale_states={"u1": MoraleState.STEADY})
        result = BattleManager._get_unit_morale_level(ctx, "u1")
        assert result == 1.0

    def test_shaken_is_075(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        ctx = _make_ctx(morale_states={"u1": MoraleState.SHAKEN})
        result = BattleManager._get_unit_morale_level(ctx, "u1")
        assert result == 0.75

    def test_broken_is_05(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        ctx = _make_ctx(morale_states={"u1": MoraleState.BROKEN})
        result = BattleManager._get_unit_morale_level(ctx, "u1")
        assert result == 0.5

    def test_routed_is_025(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        ctx = _make_ctx(morale_states={"u1": MoraleState.ROUTED})
        result = BattleManager._get_unit_morale_level(ctx, "u1")
        assert result == 0.25

    def test_surrendered_is_0(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        ctx = _make_ctx(morale_states={"u1": MoraleState.SURRENDERED})
        result = BattleManager._get_unit_morale_level(ctx, "u1")
        assert result == 0.0

    def test_missing_unit_default(self) -> None:
        ctx = _make_ctx(morale_states={})
        result = BattleManager._get_unit_morale_level(ctx, "missing")
        assert result == 0.7  # sensible default


# =========================================================================
# 3. Real supply
# =========================================================================


class TestRealSupply:
    """Supply level queried from stockpile manager."""

    def test_stockpile_query(self) -> None:
        mock_stockpile = MagicMock()
        mock_stockpile.get_supply_state.return_value = 0.6
        ctx = _make_ctx(stockpile_manager=mock_stockpile)
        result = BattleManager._get_unit_supply_level(ctx, "u1")
        assert result == 0.6

    def test_no_stockpile_returns_1(self) -> None:
        ctx = _make_ctx(stockpile_manager=None)
        result = BattleManager._get_unit_supply_level(ctx, "u1")
        assert result == 1.0

    def test_exception_returns_1(self) -> None:
        mock_stockpile = MagicMock()
        mock_stockpile.get_supply_state.side_effect = RuntimeError("boom")
        ctx = _make_ctx(stockpile_manager=mock_stockpile)
        result = BattleManager._get_unit_supply_level(ctx, "u1")
        assert result == 1.0

    def test_no_get_supply_state_method_returns_1(self) -> None:
        mock_stockpile = MagicMock(spec=[])
        ctx = _make_ctx(stockpile_manager=mock_stockpile)
        result = BattleManager._get_unit_supply_level(ctx, "u1")
        assert result == 1.0

    def test_observe_passes_real_supply(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessor = MagicMock()
        mock_assessor.assess.return_value = MagicMock()

        mock_stockpile = MagicMock()
        mock_stockpile.get_supply_state.return_value = 0.4

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=mock_assessor,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            stockpile_manager=mock_stockpile,
            units_by_side={"blue": [_make_unit("u1")], "red": [_make_unit("e1", "red")]},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)

        call_args = mock_assessor.assess.call_args
        assert call_args[1]["supply_level"] == 0.4


# =========================================================================
# 4. Personality in DECIDE
# =========================================================================


class TestPersonalityInDecide:
    """Commander personality passed to decide()."""

    def test_personality_from_commander(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_personality = MagicMock()
        mock_commander = MagicMock()
        mock_commander.get_personality.return_value = mock_personality

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=mock_commander,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        call_args = mock_decision.decide.call_args
        assert call_args[1]["personality"] is mock_personality

    def test_no_commander_personality_none(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        call_args = mock_decision.decide.call_args
        assert call_args[1]["personality"] is None

    def test_personality_none_when_unassigned(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_commander = MagicMock()
        mock_commander.get_personality.return_value = None  # unassigned

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=mock_commander,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        call_args = mock_decision.decide.call_args
        assert call_args[1]["personality"] is None

    def test_commander_queried_per_unit(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_commander = MagicMock()
        mock_commander.get_personality.side_effect = [MagicMock(), MagicMock()]
        mock_commander.get_ooda_speed_multiplier.return_value = 1.0

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=mock_commander,
            school_registry=None,
            units_by_side={
                "blue": [_make_unit("u1"), _make_unit("u2")],
                "red": [],
            },
            morale_states={},
        )
        bm._process_ooda_completions(
            ctx,
            [("u1", OODAPhase.DECIDE), ("u2", OODAPhase.DECIDE)],
            TS,
        )
        calls = mock_commander.get_personality.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "u1"
        assert calls[1][0][0] == "u2"

    def test_personality_correct_per_unit(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        p1 = MagicMock(name="personality_1")
        p2 = MagicMock(name="personality_2")
        mock_commander = MagicMock()
        mock_commander.get_personality.side_effect = [p1, p2]
        mock_commander.get_ooda_speed_multiplier.return_value = 1.0

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=mock_commander,
            school_registry=None,
            units_by_side={
                "blue": [_make_unit("u1"), _make_unit("u2")],
                "red": [],
            },
            morale_states={},
        )
        bm._process_ooda_completions(
            ctx,
            [("u1", OODAPhase.DECIDE), ("u2", OODAPhase.DECIDE)],
            TS,
        )
        decide_calls = mock_decision.decide.call_args_list
        assert decide_calls[0][1]["personality"] is p1
        assert decide_calls[1][1]["personality"] is p2


# =========================================================================
# 5. School integration with real data
# =========================================================================


class TestSchoolIntegration:
    """School adjustments use real assessment data."""

    def test_school_gets_real_force_ratio(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessment = MagicMock()
        mock_assessment.force_ratio = 3.0
        mock_assessment.supply_level = 0.9
        mock_assessment.morale_level = 0.8
        mock_assessment.intel_quality = 0.7
        mock_assessment.c2_effectiveness = 1.0
        bm._cached_assessments["u1"] = mock_assessment

        mock_school = MagicMock()
        mock_school.get_ooda_multiplier.return_value = 1.0
        mock_school.get_assessment_weight_overrides.return_value = None
        mock_school.get_decision_score_adjustments.return_value = {"attack": 0.1}
        mock_school.definition.opponent_modeling_enabled = False

        mock_registry = MagicMock()
        mock_registry.get_for_unit.return_value = mock_school

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=mock_registry,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        # School should have received real assessment summary
        call_args = mock_school.get_decision_score_adjustments.call_args
        summary = call_args[1]["assessment_summary"]
        assert summary["force_ratio"] == 3.0
        assert summary["supply_level"] == 0.9

    def test_opponent_modeling_uses_real_data(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_assessment = MagicMock()
        mock_assessment.force_ratio = 2.0
        mock_assessment.supply_level = 0.8
        mock_assessment.morale_level = 0.9
        mock_assessment.intel_quality = 0.6
        mock_assessment.c2_effectiveness = 1.0
        bm._cached_assessments["u1"] = mock_assessment

        mock_school = MagicMock()
        mock_school.get_ooda_multiplier.return_value = 1.0
        mock_school.get_assessment_weight_overrides.return_value = None
        mock_school.get_decision_score_adjustments.return_value = {"attack": 0.1}
        mock_school.definition.opponent_modeling_enabled = True
        mock_school.predict_opponent_action.return_value = {"defend": 0.8}
        mock_school.adjust_scores_for_opponent.return_value = {"attack": 0.15}

        mock_registry = MagicMock()
        mock_registry.get_for_unit.return_value = mock_school

        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        u1 = _make_unit("u1", "blue")
        e1 = _make_unit("e1", "red")
        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=mock_registry,
            units_by_side={"blue": [u1], "red": [e1]},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        # Opponent modeling should have been called
        mock_school.predict_opponent_action.assert_called_once()
        call_args = mock_school.predict_opponent_action.call_args
        assert call_args[1]["opponent_power"] == 1.0  # 1 enemy unit

    def test_no_school_no_adjustments(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_decision = MagicMock()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=mock_decision,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

        call_args = mock_decision.decide.call_args
        assert call_args[1]["school_adjustments"] is None


# =========================================================================
# 6. Assessment summary builder
# =========================================================================


class TestAssessmentSummaryBuilder:
    """_build_assessment_summary uses real or fallback data."""

    def test_with_real_assessment(self) -> None:
        mock_assessment = MagicMock()
        mock_assessment.force_ratio = 2.5
        mock_assessment.supply_level = 0.7
        mock_assessment.morale_level = 0.9
        mock_assessment.intel_quality = 0.4
        mock_assessment.c2_effectiveness = 0.8

        ctx = _make_ctx(units_by_side={"blue": [], "red": []})
        summary = BattleManager._build_assessment_summary(ctx, "u1", mock_assessment)
        assert summary["force_ratio"] == 2.5
        assert summary["supply_level"] == 0.7
        assert summary["morale_level"] == 0.9

    def test_fallback_no_assessment(self) -> None:
        u1 = _make_unit("u1", "blue")
        e1 = _make_unit("e1", "red")
        e2 = _make_unit("e2", "red")

        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": [e1, e2]},
            morale_states={},
            stockpile_manager=None,
        )
        summary = BattleManager._build_assessment_summary(ctx, "u1", None)
        assert summary["force_ratio"] == 0.5  # 1 friendly / 2 enemy
        assert summary["supply_level"] == 1.0  # fallback
        assert summary["morale_level"] == 0.7  # default

    def test_fallback_with_morale(self) -> None:
        from stochastic_warfare.morale.state import MoraleState

        u1 = _make_unit("u1", "blue")
        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": []},
            morale_states={"u1": MoraleState.SHAKEN},
            stockpile_manager=None,
        )
        summary = BattleManager._build_assessment_summary(ctx, "u1", None)
        assert summary["morale_level"] == 0.75

    def test_fallback_with_stockpile(self) -> None:
        u1 = _make_unit("u1", "blue")
        mock_stockpile = MagicMock()
        mock_stockpile.get_supply_state.return_value = 0.3
        ctx = _make_ctx(
            units_by_side={"blue": [u1], "red": []},
            morale_states={},
            stockpile_manager=mock_stockpile,
        )
        summary = BattleManager._build_assessment_summary(ctx, "u1", None)
        assert summary["supply_level"] == 0.3


# =========================================================================
# 7. Backward compatibility
# =========================================================================


class TestBackwardCompat:
    """No engines → same behavior as before."""

    def test_no_assessor_skips_observe(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)
        assert "u1" not in bm._cached_assessments

    def test_no_decision_engine_skips_decide(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        bm = _make_bm()
        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ACT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=None,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": []},
            morale_states={},
        )
        # Should not raise
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.DECIDE)], TS)

    def test_observe_passes_real_morale(self) -> None:
        from stochastic_warfare.c2.ai.ooda import OODAPhase
        from stochastic_warfare.morale.state import MoraleState

        bm = _make_bm()
        mock_assessor = MagicMock()
        mock_assessor.assess.return_value = MagicMock()

        mock_ooda = MagicMock()
        mock_ooda.tactical_acceleration = 1.0
        mock_ooda.advance_phase.return_value = OODAPhase.ORIENT

        ctx = _make_ctx(
            ooda_engine=mock_ooda,
            assessor=mock_assessor,
            decision_engine=None,
            commander_engine=None,
            school_registry=None,
            units_by_side={"blue": [_make_unit("u1")], "red": [_make_unit("e1", "red")]},
            morale_states={"u1": MoraleState.BROKEN},
        )
        bm._process_ooda_completions(ctx, [("u1", OODAPhase.OBSERVE)], TS)

        call_args = mock_assessor.assess.call_args
        assert call_args[1]["morale_level"] == 0.5  # BROKEN

    def test_set_state_clears_assessment_cache(self) -> None:
        """Checkpoint restore must clear transient assessment cache."""
        bm = _make_bm()
        bm._cached_assessments["u1"] = MagicMock()
        bm._cached_assessments["u2"] = MagicMock()
        assert len(bm._cached_assessments) == 2

        bm.set_state({"battles": {}, "next_battle_id": 0})
        assert len(bm._cached_assessments) == 0
