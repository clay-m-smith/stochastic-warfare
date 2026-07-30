"""Current-engine campaign regressions — Golan Heights scenario.

These tests exercise the authored campaign through the production runtime and
verify deterministic execution, metric projection, and campaign plumbing.
They do not establish historical accuracy; catalog-wide historical envelope
acceptance is tracked by REM-030.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.engine import EngineConfig
from stochastic_warfare.validation.ai_validation import AIDecisionValidator
from stochastic_warfare.validation.campaign_data import CampaignDataLoader
from stochastic_warfare.validation.campaign_metrics import CampaignValidationMetrics
from stochastic_warfare.validation.campaign_runner import (
    CampaignRunner,
    CampaignRunnerConfig,
    CampaignRunResult,
)
from stochastic_warfare.validation.monte_carlo import (
    CampaignMonteCarloHarness,
    MonteCarloConfig,
)


# ---------------------------------------------------------------------------
# Paths and fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GOLAN_YAML = DATA_DIR / "scenarios" / "golan_campaign" / "scenario.yaml"


@pytest.fixture(scope="module")
def golan_campaign():
    """Load the Golan campaign YAML once for all tests."""
    if not GOLAN_YAML.exists():
        pytest.skip("Golan campaign YAML not found")
    return CampaignDataLoader().load(GOLAN_YAML)


def _fast_runner() -> CampaignRunner:
    """Runner limited to 20 ticks for fast tests."""
    return CampaignRunner(
        CampaignRunnerConfig(
            data_dir=str(DATA_DIR),
            engine_config=EngineConfig(max_ticks=20),
            snapshot_interval_ticks=10,
        )
    )


@pytest.fixture(scope="module")
def golan_fast_result(golan_campaign):
    """Share one seed-42 production result across read-only checks."""
    return _fast_runner().run(golan_campaign, seed=42)


@pytest.fixture(scope="module")
def golan_replay_result(golan_campaign):
    """Independently replay the seed-42 production run once."""
    return _fast_runner().run(golan_campaign, seed=42)


@pytest.fixture(scope="module")
def golan_fast_mc_result(golan_campaign):
    """Run one bounded three-seed production sample for all consumers."""
    harness = CampaignMonteCarloHarness(
        _fast_runner(),
        MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1),
    )
    return harness.run(golan_campaign)


# ===========================================================================
# Scenario loading
# ===========================================================================


class TestGolanScenarioLoading:
    def test_yaml_parses(self, golan_campaign):
        assert golan_campaign.name.startswith("Golan")

    def test_forces_correct(self, golan_campaign):
        blue = golan_campaign.sides[0]
        red = golan_campaign.sides[1]
        assert blue.side == "blue"
        blue_count = sum(u.get("count", 1) for u in blue.units)
        assert blue_count == 40
        red_count = sum(u.get("count", 1) for u in red.units)
        assert red_count >= 100

    def test_terrain_correct(self, golan_campaign):
        assert golan_campaign.terrain.terrain_type == "hilly_defense"
        assert golan_campaign.terrain.width_m == 15000


# ===========================================================================
# Single run completion
# ===========================================================================


@pytest.mark.slow
class TestGolanSingleRun:
    def test_runs_to_configured_terminal_boundary(self, golan_fast_result):
        assert isinstance(golan_fast_result, CampaignRunResult)
        assert golan_fast_result.seed == 42
        assert golan_fast_result.ticks_executed == 20
        assert golan_fast_result.terminated_by == "max_ticks"

    def test_both_sides_preserve_authored_rosters(self, golan_fast_result):
        assert {side: len(units) for side, units in golan_fast_result.final_units_by_side.items()} == {
            "blue": 40,
            "red": 100,
        }

    def test_terminal_result_is_packaged_consistently(self, golan_fast_result):
        assert golan_fast_result.victory_result.condition_type == (golan_fast_result.terminated_by)
        assert golan_fast_result.victory_result.winning_side == "draw"

    def test_recorder_captures_events(self, golan_fast_result):
        assert golan_fast_result.recorder is not None
        assert golan_fast_result.recorder.event_count() > 0

    def test_morale_states_cover_runtime_roster(self, golan_fast_result):
        assert set(golan_fast_result.final_morale_states) == {
            unit.entity_id for units in golan_fast_result.final_units_by_side.values() for unit in units
        }


# ===========================================================================
# Deterministic replay
# ===========================================================================


@pytest.mark.slow
class TestGolanDeterministicReplay:
    def test_same_seed_semantic_replay_is_exact(self, golan_fast_result, golan_replay_result):
        assert golan_fast_result.run_result == golan_replay_result.run_result
        assert golan_fast_result.ticks_executed == golan_replay_result.ticks_executed
        assert golan_fast_result.terminated_by == golan_replay_result.terminated_by
        assert golan_fast_result.victory_result == golan_replay_result.victory_result
        assert {
            side: [unit.get_state() for unit in units] for side, units in golan_fast_result.final_units_by_side.items()
        } == {
            side: [unit.get_state() for unit in units]
            for side, units in golan_replay_result.final_units_by_side.items()
        }
        assert golan_fast_result.final_morale_states == golan_replay_result.final_morale_states
        assert golan_fast_result.recorder is not None
        assert golan_replay_result.recorder is not None
        assert golan_fast_result.recorder.events == golan_replay_result.recorder.events

    def test_metrics_deterministic(self, golan_fast_result, golan_replay_result):
        m1 = CampaignValidationMetrics.extract_all(golan_fast_result)
        m2 = CampaignValidationMetrics.extract_all(golan_replay_result)
        for key in m1:
            assert m1[key] == m2[key], f"Metric {key} differs between runs"


# ===========================================================================
# Current metric projection (single run)
# ===========================================================================


@pytest.mark.slow
class TestGolanCurrentMetricSingleRun:
    def test_metrics_extracted(self, golan_fast_result):
        metrics = CampaignValidationMetrics.extract_all(golan_fast_result)
        assert set(metrics) == {
            "blue_units_destroyed",
            "red_units_destroyed",
            "blue_units_surviving",
            "red_units_surviving",
            "exchange_ratio",
            "campaign_duration_s",
            "engagement_count",
            "force_ratio_final",
            "blue_territory_control",
            "red_territory_control",
            "blue_ships_sunk",
            "red_ships_sunk",
        }

    def test_campaign_duration_matches_runtime_result(self, golan_fast_result):
        metrics = CampaignValidationMetrics.extract_all(golan_fast_result)
        assert metrics["campaign_duration_s"] == (golan_fast_result.duration_simulated_s)
        assert metrics["campaign_duration_s"] > 0

    def test_status_metrics_match_final_runtime_state(self, golan_fast_result):
        metrics = CampaignValidationMetrics.extract_all(golan_fast_result)
        for side in ("blue", "red"):
            units = golan_fast_result.final_units_by_side[side]
            status_counts = {status: sum(unit.status == status for unit in units) for status in UnitStatus}
            assert sum(status_counts.values()) == len(units)
            assert metrics[f"{side}_units_destroyed"] == float(
                status_counts[UnitStatus.DESTROYED] + status_counts[UnitStatus.SURRENDERED]
            )
            assert metrics[f"{side}_units_surviving"] == float(status_counts[UnitStatus.ACTIVE])


# ===========================================================================
# Bounded production sample and statistic projection (3 runs)
# ===========================================================================


@pytest.mark.slow
class TestGolanProductionSample:
    def test_requested_seed_sample_is_complete(self, golan_fast_mc_result):
        assert golan_fast_mc_result.num_runs == 3
        assert [run.seed for run in golan_fast_mc_result.runs] == [42, 43, 44]

    def test_all_runs_reach_configured_terminal_boundary(self, golan_fast_mc_result):
        for run in golan_fast_mc_result.runs:
            assert "campaign_duration_s" in run.metrics
            assert run.terminated_by == "max_ticks"

    def test_documented_metric_projection_is_complete(self, golan_campaign, golan_fast_mc_result):
        report = golan_fast_mc_result.compare_to_historical(golan_campaign.documented_outcomes)
        assert [item.metric_name for item in report.metric_results] == [
            metric.name for metric in golan_campaign.documented_outcomes
        ]
        for item in report.metric_results:
            assert item.simulated_mean == pytest.approx(golan_fast_mc_result.mean(item.metric_name))

    def test_duration_statistic_is_positive(self, golan_fast_mc_result):
        mean = golan_fast_mc_result.mean("campaign_duration_s")
        assert mean > 0


# ===========================================================================
# AI event projection (bounded current-engine control)
# ===========================================================================


@pytest.mark.slow
class TestGolanAIEventProjection:
    def test_bounded_run_projects_exact_current_event_types(self, golan_fast_result):
        assert golan_fast_result.recorder is not None
        decisions = AIDecisionValidator.extract_decisions(golan_fast_result.recorder)
        event_types = Counter(decision.event_type for decision in decisions)
        assert event_types == Counter(
            {
                "SituationAssessedEvent": 140,
                "OODAPhaseChangeEvent": 160,
            }
        )
        assert "DecisionMadeEvent" not in event_types


# ===========================================================================
# Runtime state coverage
# ===========================================================================


@pytest.mark.slow
class TestGolanRuntimeState:
    def test_runtime_tracks_every_unit_morale_state(self, golan_fast_result):
        assert len(golan_fast_result.final_morale_states) == sum(
            len(units) for units in golan_fast_result.final_units_by_side.values()
        )


# ===========================================================================
# Reinforcements
# ===========================================================================


class TestGolanReinforcements:
    def test_reinforcement_config(self, golan_campaign):
        assert len(golan_campaign.reinforcements) == 2
        assert golan_campaign.reinforcements[0].arrival_time_s == 129600
        assert golan_campaign.reinforcements[1].arrival_time_s == 259200

    def test_reinforcement_units(self, golan_campaign):
        for r in golan_campaign.reinforcements:
            assert r.side == "blue"
            total = sum(u.count for u in r.units)
            assert total == 20
