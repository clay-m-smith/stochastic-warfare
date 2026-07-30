"""Current-engine campaign regressions — Falklands San Carlos scenario.

These tests exercise the authored campaign through the production runtime and
verify deterministic execution, metric projection, and campaign plumbing.
They do not establish historical accuracy; catalog-wide historical envelope
acceptance is tracked by REM-030.
"""

from __future__ import annotations

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
FALKLANDS_YAML = DATA_DIR / "scenarios" / "falklands_campaign" / "scenario.yaml"


@pytest.fixture(scope="module")
def falklands_campaign():
    """Load the Falklands campaign YAML once for all tests."""
    if not FALKLANDS_YAML.exists():
        pytest.skip("Falklands campaign YAML not found")
    return CampaignDataLoader().load(FALKLANDS_YAML)


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
def falklands_fast_result(falklands_campaign):
    """Share one seed-42 production result across read-only checks."""
    return _fast_runner().run(falklands_campaign, seed=42)


@pytest.fixture(scope="module")
def falklands_replay_result(falklands_campaign):
    """Independently replay the seed-42 production run once."""
    return _fast_runner().run(falklands_campaign, seed=42)


@pytest.fixture(scope="module")
def falklands_fast_mc_result(falklands_campaign):
    """Run one bounded three-seed production sample for all consumers."""
    harness = CampaignMonteCarloHarness(
        _fast_runner(),
        MonteCarloConfig(num_iterations=3, base_seed=42, max_workers=1),
    )
    return harness.run(falklands_campaign)


# ===========================================================================
# Scenario loading
# ===========================================================================


class TestFalklandsScenarioLoading:
    def test_yaml_parses(self, falklands_campaign):
        assert falklands_campaign.name.startswith("Falklands")

    def test_forces_correct(self, falklands_campaign):
        blue = falklands_campaign.sides[0]
        red = falklands_campaign.sides[1]
        assert blue.side == "blue"
        assert red.side == "red"
        blue_count = sum(u.get("count", 1) for u in blue.units)
        assert blue_count == 16  # 4 Type 42 + 4 Type 22 + 8 Sea Harrier

    def test_terrain_ocean(self, falklands_campaign):
        assert falklands_campaign.terrain.terrain_type == "open_ocean"
        assert falklands_campaign.terrain.width_m == 100000


# ===========================================================================
# Single run completion
# ===========================================================================


@pytest.mark.slow
class TestFalklandsSingleRun:
    def test_runs_to_configured_terminal_boundary(self, falklands_fast_result):
        assert isinstance(falklands_fast_result, CampaignRunResult)
        assert falklands_fast_result.seed == 42
        assert falklands_fast_result.ticks_executed == 20
        assert falklands_fast_result.terminated_by == "max_ticks"

    def test_both_sides_preserve_authored_rosters(self, falklands_fast_result):
        assert {side: len(units) for side, units in falklands_fast_result.final_units_by_side.items()} == {
            "blue": 16,
            "red": 8,
        }

    def test_naval_roster_is_instantiated(self, falklands_fast_result):
        blue_types = [getattr(unit, "unit_type", "") for unit in falklands_fast_result.final_units_by_side["blue"]]
        assert blue_types.count("type42_destroyer") == 4
        assert blue_types.count("type22_frigate") == 4
        assert blue_types.count("sea_harrier") == 8

    def test_recorder_captures_events(self, falklands_fast_result):
        assert falklands_fast_result.recorder is not None
        assert falklands_fast_result.recorder.event_count() > 0

    def test_terminal_result_is_packaged_consistently(self, falklands_fast_result):
        assert falklands_fast_result.victory_result.condition_type == (falklands_fast_result.terminated_by)
        assert falklands_fast_result.victory_result.winning_side == "draw"


# ===========================================================================
# Deterministic replay
# ===========================================================================


@pytest.mark.slow
class TestFalklandsDeterministicReplay:
    def test_same_seed_semantic_replay_is_exact(self, falklands_fast_result, falklands_replay_result):
        assert falklands_fast_result.run_result == falklands_replay_result.run_result
        assert falklands_fast_result.ticks_executed == falklands_replay_result.ticks_executed
        assert falklands_fast_result.terminated_by == falklands_replay_result.terminated_by
        assert falklands_fast_result.victory_result == falklands_replay_result.victory_result
        assert {
            side: [unit.get_state() for unit in units]
            for side, units in falklands_fast_result.final_units_by_side.items()
        } == {
            side: [unit.get_state() for unit in units]
            for side, units in falklands_replay_result.final_units_by_side.items()
        }
        assert falklands_fast_result.final_morale_states == falklands_replay_result.final_morale_states
        assert falklands_fast_result.recorder is not None
        assert falklands_replay_result.recorder is not None
        assert falklands_fast_result.recorder.events == falklands_replay_result.recorder.events

    def test_metrics_deterministic(self, falklands_fast_result, falklands_replay_result):
        m1 = CampaignValidationMetrics.extract_all(falklands_fast_result)
        m2 = CampaignValidationMetrics.extract_all(falklands_replay_result)
        for key in m1:
            assert m1[key] == m2[key], f"Metric {key} differs"


# ===========================================================================
# Current metric projection (single run)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsCurrentMetricSingleRun:
    def test_metrics_extracted(self, falklands_fast_result):
        metrics = CampaignValidationMetrics.extract_all(falklands_fast_result)
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

    def test_campaign_duration_matches_runtime_result(self, falklands_fast_result):
        metrics = CampaignValidationMetrics.extract_all(falklands_fast_result)
        assert metrics["campaign_duration_s"] == (falklands_fast_result.duration_simulated_s)
        assert metrics["campaign_duration_s"] > 0


# ===========================================================================
# Bounded production sample and statistic projection (3 runs)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsProductionSample:
    def test_requested_seed_sample_is_complete(self, falklands_fast_mc_result):
        assert falklands_fast_mc_result.num_runs == 3
        assert [run.seed for run in falklands_fast_mc_result.runs] == [42, 43, 44]

    def test_all_runs_reach_configured_terminal_boundary(self, falklands_fast_mc_result):
        for run in falklands_fast_mc_result.runs:
            assert "blue_ships_sunk" in run.metrics
            assert run.terminated_by == "max_ticks"

    def test_documented_metric_projection_is_complete(self, falklands_campaign, falklands_fast_mc_result):
        report = falklands_fast_mc_result.compare_to_historical(falklands_campaign.documented_outcomes)
        assert [item.metric_name for item in report.metric_results] == [
            metric.name for metric in falklands_campaign.documented_outcomes
        ]
        for item in report.metric_results:
            assert item.simulated_mean == pytest.approx(falklands_fast_mc_result.mean(item.metric_name))

    def test_duration_statistic_is_positive(self, falklands_fast_mc_result):
        mean = falklands_fast_mc_result.mean("campaign_duration_s")
        assert mean > 0


# ===========================================================================
# AI event projection (bounded current-engine control)
# ===========================================================================


@pytest.mark.slow
class TestFalklandsAIEventProjection:
    def test_bounded_run_has_no_projected_ai_events(self, falklands_fast_result):
        assert falklands_fast_result.recorder is not None
        assert falklands_fast_result.recorder.event_count() > 0
        decisions = AIDecisionValidator.extract_decisions(falklands_fast_result.recorder)
        assert decisions == []


# ===========================================================================
# Naval-specific metrics
# ===========================================================================


@pytest.mark.slow
class TestFalklandsNavalMetrics:
    def test_ships_sunk_metric_matches_final_naval_state(self, falklands_fast_result):
        metrics = CampaignValidationMetrics.extract_all(falklands_fast_result)
        expected = sum(
            1
            for unit in falklands_fast_result.final_units_by_side["blue"]
            if getattr(unit, "unit_type", "")
            in {
                "type42_destroyer",
                "type22_frigate",
            }
            and unit.status in {UnitStatus.DESTROYED, UnitStatus.SURRENDERED}
        )
        assert metrics["blue_ships_sunk"] == expected

    def test_red_destroyed_metric_matches_final_unit_state(self, falklands_fast_result):
        metrics = CampaignValidationMetrics.extract_all(falklands_fast_result)
        expected = sum(
            1
            for unit in falklands_fast_result.final_units_by_side["red"]
            if unit.status in {UnitStatus.DESTROYED, UnitStatus.SURRENDERED}
        )
        assert metrics["red_units_destroyed"] == expected

    def test_reinforcements_configured(self, falklands_campaign):
        waves = falklands_campaign.reinforcements
        assert [
            (
                wave.side,
                wave.arrival_time_s,
                tuple((unit.unit_type, unit.count) for unit in wave.units),
            )
            for wave in waves
        ] == [
            ("red", 172800.0, (("super_etendard", 2),)),
            ("red", 345600.0, (("super_etendard", 2),)),
        ]
        assert sum(unit.count for wave in waves for unit in wave.units) == 4
