"""Regression contracts for three scenarios executed by the legacy runner.

These tests preserve loader, execution, metric, replay, and Monte Carlo
coverage. They do not establish historical outcome validity.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.validation.metrics import EngagementMetrics
from tests.validation.historical.legacy_runner_support import (
    EASTING,
    FALKLANDS,
    GOLAN,
    LEGACY_SCENARIOS,
    LegacyScenarioCase,
    engagement_for,
    monte_carlo_for,
    runner_for,
    single_run_for,
)


def _case_id(case: LegacyScenarioCase) -> str:
    return case.scenario_id


class TestScenarioLoading:
    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_loads_scenario(self, case: LegacyScenarioCase) -> None:
        engagement = engagement_for(case)
        for name_part in case.name_parts:
            assert name_part in engagement.name

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_blue_forces(self, case: LegacyScenarioCase) -> None:
        forces = engagement_for(case).blue_forces
        assert forces.personnel_total == case.blue_personnel
        assert len(forces.units) == case.blue_unit_definitions

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_red_forces(self, case: LegacyScenarioCase) -> None:
        forces = engagement_for(case).red_forces
        if case.red_personnel is not None:
            assert forces.personnel_total == case.red_personnel
        if case.red_unit_count_is_minimum:
            assert len(forces.units) >= case.red_unit_definitions
        else:
            assert len(forces.units) == case.red_unit_definitions

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_terrain(self, case: LegacyScenarioCase) -> None:
        terrain = engagement_for(case).terrain
        assert terrain.terrain_type == case.terrain_type
        if case.terrain_width_m is not None:
            assert terrain.width_m == case.terrain_width_m
        if case.base_elevation_m is not None:
            assert terrain.base_elevation_m == case.base_elevation_m

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_documented_outcomes(self, case: LegacyScenarioCase) -> None:
        outcomes = engagement_for(case).documented_outcomes
        if case.documented_outcome_minimum is not None:
            assert len(outcomes) >= case.documented_outcome_minimum
        names = {outcome.name for outcome in outcomes}
        for expected_name in case.documented_outcome_names:
            assert expected_name in names

    def test_easting_calibration_overrides(self) -> None:
        assert (
            "hit_probability_modifier"
            in engagement_for(
                EASTING,
            ).calibration_overrides
        )

    def test_easting_behavior_rules(self) -> None:
        rules = engagement_for(EASTING).behavior_rules
        assert "blue" in rules
        assert "red" in rules

    def test_golan_terrain_features(self) -> None:
        features = engagement_for(GOLAN).terrain.features
        ridge_count = sum(1 for feature in features if feature["type"] == "ridge")
        assert ridge_count >= 1

    def test_golan_blue_holds_position(self) -> None:
        assert engagement_for(GOLAN).behavior_rules["blue"]["hold_position"] is True


class TestSingleRun:
    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_simulation_completes(self, case: LegacyScenarioCase) -> None:
        assert single_run_for(case).ticks_executed > 0

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_has_final_states(self, case: LegacyScenarioCase) -> None:
        assert len(single_run_for(case).units_final) > 0

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_has_events(self, case: LegacyScenarioCase) -> None:
        assert len(single_run_for(case).event_log) > 0

    def test_easting_terminated(self) -> None:
        assert single_run_for(EASTING).terminated_by != ""

    @pytest.mark.parametrize(
        ("case", "side", "expected_count"),
        (
            pytest.param(EASTING, "blue", None, id="73-easting-blue"),
            pytest.param(EASTING, "red", None, id="73-easting-red"),
            pytest.param(GOLAN, "blue", 40, id="golan-blue"),
            pytest.param(GOLAN, "red", 250, id="golan-red"),
        ),
    )
    def test_side_present(
        self,
        case: LegacyScenarioCase,
        side: str,
        expected_count: int | None,
    ) -> None:
        units = [unit for unit in single_run_for(case).units_final if unit.side == side]
        if expected_count is None:
            assert len(units) > 0
        else:
            assert len(units) == expected_count

    def test_falklands_blue_naval_present(self) -> None:
        naval = [
            unit
            for unit in single_run_for(FALKLANDS).units_final
            if unit.side == "blue" and unit.unit_type in ("type42_destroyer", "type22_frigate")
        ]
        assert len(naval) > 0


class TestMetricExtraction:
    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_metrics_extracted(self, case: LegacyScenarioCase) -> None:
        metrics = EngagementMetrics.extract_all(single_run_for(case))
        for metric_name in case.required_metrics:
            assert metric_name in metrics

    @pytest.mark.parametrize(
        "case",
        (EASTING, FALKLANDS),
        ids=_case_id,
    )
    def test_duration_positive(self, case: LegacyScenarioCase) -> None:
        metrics = EngagementMetrics.extract_all(single_run_for(case))
        assert metrics["duration_s"] > 0

    def test_easting_some_combat_occurred(self) -> None:
        assert len(single_run_for(EASTING).event_log) > 0

    def test_golan_some_red_losses(self) -> None:
        result = single_run_for(GOLAN)
        metrics = EngagementMetrics.extract_all(result)
        assert (
            metrics["red_units_destroyed"] > 0 or metrics["red_personnel_casualties"] > 0 or len(result.event_log) > 10
        )


class TestDeterministicReplay:
    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_same_seed_same_result(self, case: LegacyScenarioCase) -> None:
        runner = runner_for(case)
        engagement = engagement_for(case)
        first = EngagementMetrics.extract_all(runner.run(engagement, seed=42))
        second = EngagementMetrics.extract_all(runner.run(engagement, seed=42))
        for key in first:
            assert first[key] == second[key], f"Mismatch on {key}: {first[key]} != {second[key]}"

    def test_easting_different_seed_changes_events(self) -> None:
        runner = runner_for(EASTING)
        engagement = engagement_for(EASTING)
        first = runner.run(engagement, seed=42)
        second = runner.run(engagement, seed=999)
        # Aggregate envelopes may coincide; the event stream must expose the draw.
        assert first.event_log != second.event_log


class TestMonteCarloFast:
    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_mc_runs(self, case: LegacyScenarioCase) -> None:
        result = monte_carlo_for(case)
        assert result.num_runs == case.monte_carlo_iterations

    @pytest.mark.parametrize("case", LEGACY_SCENARIOS, ids=_case_id)
    def test_mc_comparison(self, case: LegacyScenarioCase) -> None:
        result = monte_carlo_for(case)
        report = result.compare_to_historical(
            engagement_for(case).documented_outcomes,
        )
        assert len(report.metric_results) > 0

    def test_easting_mc_statistics(self) -> None:
        assert monte_carlo_for(EASTING).mean("duration_s") > 0


@pytest.mark.slow
class TestMonteCarloFull:
    def test_easting_1000_run_convergence(self) -> None:
        result = monte_carlo_for(EASTING, iterations=1000)
        assert result.num_runs == 1000
        lower, upper = result.confidence_interval("duration_s", 0.95)
        assert upper - lower < result.mean("duration_s")
