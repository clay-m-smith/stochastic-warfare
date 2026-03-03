"""Tests for validation.campaign_metrics — campaign-level metric extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.recorder import RecordedEvent, SimulationRecorder
from stochastic_warfare.simulation.victory import VictoryResult
from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics
from stochastic_warfare.validation.campaign_runner import CampaignRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit(entity_id: str, side: str, status: UnitStatus, unit_type: str = "m1a2"):
    """Create a minimal mock unit."""
    return SimpleNamespace(
        entity_id=entity_id,
        side=side,
        status=status,
        unit_type=unit_type,
    )


def _make_result(
    blue_units: list | None = None,
    red_units: list | None = None,
    duration_s: float = 3600.0,
    victory: VictoryResult | None = None,
    recorder: SimulationRecorder | None = None,
) -> CampaignRunResult:
    """Create a CampaignRunResult with mock data."""
    if blue_units is None:
        blue_units = []
    if red_units is None:
        red_units = []
    if victory is None:
        victory = VictoryResult(game_over=True, winning_side="blue", condition_type="time_expired")

    return CampaignRunResult(
        seed=42,
        ticks_executed=100,
        duration_simulated_s=duration_s,
        victory_result=victory,
        recorder=recorder,
        final_units_by_side={"blue": blue_units, "red": red_units},
        final_morale_states={},
        terminated_by=victory.condition_type,
    )


# ===========================================================================
# Units destroyed count
# ===========================================================================


class TestUnitsDestroyedCount:
    def test_no_losses(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
        )
        assert CampaignValidationMetrics.units_destroyed_count(result, "blue") == 0

    def test_all_destroyed(self):
        result = _make_result(
            red_units=[
                _make_unit("r1", "red", UnitStatus.DESTROYED),
                _make_unit("r2", "red", UnitStatus.DESTROYED),
            ],
        )
        assert CampaignValidationMetrics.units_destroyed_count(result, "red") == 2

    def test_surrendered_counts(self):
        result = _make_result(
            red_units=[_make_unit("r1", "red", UnitStatus.SURRENDERED)],
        )
        assert CampaignValidationMetrics.units_destroyed_count(result, "red") == 1

    def test_mixed_statuses(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.DESTROYED),
                _make_unit("b3", "blue", UnitStatus.ACTIVE),
            ],
        )
        assert CampaignValidationMetrics.units_destroyed_count(result, "blue") == 1

    def test_empty_side(self):
        result = _make_result()
        assert CampaignValidationMetrics.units_destroyed_count(result, "blue") == 0

    def test_nonexistent_side(self):
        result = _make_result()
        assert CampaignValidationMetrics.units_destroyed_count(result, "green") == 0


# ===========================================================================
# Units surviving count
# ===========================================================================


class TestUnitsSurvivingCount:
    def test_all_active(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.ACTIVE),
            ],
        )
        assert CampaignValidationMetrics.units_surviving_count(result, "blue") == 2

    def test_some_destroyed(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.DESTROYED),
            ],
        )
        assert CampaignValidationMetrics.units_surviving_count(result, "blue") == 1

    def test_none_active(self):
        result = _make_result(
            red_units=[_make_unit("r1", "red", UnitStatus.DESTROYED)],
        )
        assert CampaignValidationMetrics.units_surviving_count(result, "red") == 0


# ===========================================================================
# Exchange ratio
# ===========================================================================


class TestExchangeRatio:
    def test_normal_ratio(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.DESTROYED),
            ],
            red_units=[
                _make_unit("r1", "red", UnitStatus.DESTROYED),
                _make_unit("r2", "red", UnitStatus.DESTROYED),
                _make_unit("r3", "red", UnitStatus.DESTROYED),
            ],
        )
        ratio = CampaignValidationMetrics.exchange_ratio(result, "blue", "red")
        assert ratio == 3.0

    def test_zero_blue_losses_inf(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
            red_units=[_make_unit("r1", "red", UnitStatus.DESTROYED)],
        )
        assert CampaignValidationMetrics.exchange_ratio(result, "blue", "red") == float("inf")

    def test_zero_both_losses(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
            red_units=[_make_unit("r1", "red", UnitStatus.ACTIVE)],
        )
        assert CampaignValidationMetrics.exchange_ratio(result, "blue", "red") == 0.0

    def test_equal_losses(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.DESTROYED)],
            red_units=[_make_unit("r1", "red", UnitStatus.DESTROYED)],
        )
        assert CampaignValidationMetrics.exchange_ratio(result, "blue", "red") == 1.0


# ===========================================================================
# Campaign duration
# ===========================================================================


class TestCampaignDuration:
    def test_returns_duration(self):
        result = _make_result(duration_s=86400.0)
        assert CampaignValidationMetrics.campaign_duration_s(result) == 86400.0


# ===========================================================================
# Winning side
# ===========================================================================


class TestWinningSide:
    def test_returns_winner(self):
        result = _make_result(
            victory=VictoryResult(game_over=True, winning_side="blue"),
        )
        assert CampaignValidationMetrics.winning_side(result) == "blue"

    def test_no_winner(self):
        result = _make_result(
            victory=VictoryResult(game_over=False),
        )
        assert CampaignValidationMetrics.winning_side(result) == ""


# ===========================================================================
# Victory condition met
# ===========================================================================


class TestVictoryConditionMet:
    def test_force_destroyed(self):
        result = _make_result(
            victory=VictoryResult(
                game_over=True,
                condition_type="force_destroyed",
            ),
        )
        assert CampaignValidationMetrics.victory_condition_met(result) == "force_destroyed"


# ===========================================================================
# Territory control fraction
# ===========================================================================


class TestTerritoryControlFraction:
    def test_all_active(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.ACTIVE),
            ],
        )
        assert CampaignValidationMetrics.territory_control_fraction(result, "blue") == 1.0

    def test_half_destroyed(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.DESTROYED),
            ],
        )
        assert CampaignValidationMetrics.territory_control_fraction(result, "blue") == 0.5

    def test_empty_side(self):
        result = _make_result()
        assert CampaignValidationMetrics.territory_control_fraction(result, "blue") == 0.0


# ===========================================================================
# Force ratio final
# ===========================================================================


class TestForceRatioFinal:
    def test_normal_ratio(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.ACTIVE),
            ],
            red_units=[
                _make_unit("r1", "red", UnitStatus.ACTIVE),
            ],
        )
        assert CampaignValidationMetrics.force_ratio_final(result, "blue", "red") == 2.0

    def test_red_annihilated(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
            red_units=[_make_unit("r1", "red", UnitStatus.DESTROYED)],
        )
        assert CampaignValidationMetrics.force_ratio_final(result, "blue", "red") == float("inf")


# ===========================================================================
# Ships sunk
# ===========================================================================


class TestShipsSunk:
    def test_naval_unit_destroyed(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.DESTROYED, unit_type="type42_destroyer"),
            ],
        )
        assert CampaignValidationMetrics.ships_sunk(result, "blue") == 1

    def test_non_naval_unit_not_counted(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.DESTROYED, unit_type="m1a2"),
            ],
        )
        assert CampaignValidationMetrics.ships_sunk(result, "blue") == 0

    def test_active_naval_not_counted(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE, unit_type="type42_destroyer"),
            ],
        )
        assert CampaignValidationMetrics.ships_sunk(result, "blue") == 0


# ===========================================================================
# Engagement count
# ===========================================================================


class TestEngagementCount:
    def test_no_recorder(self):
        result = _make_result(recorder=None)
        assert CampaignValidationMetrics.engagement_count(result) == 0

    def test_with_recorder_no_engagements(self):
        from stochastic_warfare.core.events import EventBus
        recorder = SimulationRecorder(EventBus())
        result = _make_result(recorder=recorder)
        assert CampaignValidationMetrics.engagement_count(result) == 0


# ===========================================================================
# Extract all
# ===========================================================================


class TestExtractAll:
    def test_returns_all_keys(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
            red_units=[_make_unit("r1", "red", UnitStatus.DESTROYED)],
        )
        metrics = CampaignValidationMetrics.extract_all(result)
        expected_keys = {
            "blue_units_destroyed", "red_units_destroyed",
            "blue_units_surviving", "red_units_surviving",
            "exchange_ratio", "campaign_duration_s",
            "engagement_count", "force_ratio_final",
            "blue_territory_control", "red_territory_control",
            "blue_ships_sunk", "red_ships_sunk",
        }
        assert set(metrics.keys()) == expected_keys

    def test_values_correct(self):
        result = _make_result(
            blue_units=[
                _make_unit("b1", "blue", UnitStatus.ACTIVE),
                _make_unit("b2", "blue", UnitStatus.DESTROYED),
            ],
            red_units=[
                _make_unit("r1", "red", UnitStatus.DESTROYED),
                _make_unit("r2", "red", UnitStatus.DESTROYED),
                _make_unit("r3", "red", UnitStatus.ACTIVE),
            ],
            duration_s=7200.0,
        )
        metrics = CampaignValidationMetrics.extract_all(result)
        assert metrics["blue_units_destroyed"] == 1.0
        assert metrics["red_units_destroyed"] == 2.0
        assert metrics["exchange_ratio"] == 2.0
        assert metrics["campaign_duration_s"] == 7200.0

    def test_all_values_are_float(self):
        result = _make_result(
            blue_units=[_make_unit("b1", "blue", UnitStatus.ACTIVE)],
            red_units=[_make_unit("r1", "red", UnitStatus.ACTIVE)],
        )
        metrics = CampaignValidationMetrics.extract_all(result)
        for k, v in metrics.items():
            assert isinstance(v, float), f"{k} is {type(v)}, expected float"

    def test_custom_side_names(self):
        result = CampaignRunResult(
            seed=42, ticks_executed=10, duration_simulated_s=100,
            victory_result=VictoryResult(game_over=False),
            recorder=None,
            final_units_by_side={
                "israel": [_make_unit("i1", "israel", UnitStatus.ACTIVE)],
                "syria": [_make_unit("s1", "syria", UnitStatus.DESTROYED)],
            },
            final_morale_states={},
            terminated_by="",
        )
        metrics = CampaignValidationMetrics.extract_all(result, "israel", "syria")
        assert metrics["red_units_destroyed"] == 1.0
        assert metrics["blue_units_surviving"] == 1.0

    def test_empty_sides(self):
        result = _make_result()
        metrics = CampaignValidationMetrics.extract_all(result)
        assert metrics["blue_units_destroyed"] == 0.0
        assert metrics["red_units_destroyed"] == 0.0
        assert metrics["exchange_ratio"] == 0.0
