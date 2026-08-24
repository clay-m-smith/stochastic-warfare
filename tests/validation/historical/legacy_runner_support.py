"""Transparent scenario data and cached setup for legacy-runner regressions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from stochastic_warfare.legacy.validation.historical_data import (
    HistoricalDataLoader,
    HistoricalEngagement,
)
from stochastic_warfare.legacy.validation.monte_carlo import (
    MonteCarloConfig,
    MonteCarloHarness,
    MonteCarloResult,
)
from stochastic_warfare.legacy.validation.scenario_runner import (
    ScenarioRunner,
    ScenarioRunnerConfig,
)
from stochastic_warfare.validation.metrics import SimulationResult


@dataclass(frozen=True)
class LegacyScenarioCase:
    """Exact load and result contract for one legacy historical scenario."""

    scenario_id: str
    scenario_path: Path
    max_ticks: int
    monte_carlo_iterations: int
    name_parts: tuple[str, ...]
    blue_personnel: int
    blue_unit_definitions: int
    red_personnel: int | None
    red_unit_definitions: int
    red_unit_count_is_minimum: bool
    terrain_type: str
    terrain_width_m: float | None
    base_elevation_m: float | None
    documented_outcome_minimum: int | None
    documented_outcome_names: tuple[str, ...]
    required_metrics: tuple[str, ...]


EASTING = LegacyScenarioCase(
    scenario_id="73-easting",
    scenario_path=Path("data/scenarios/73_easting/scenario.yaml"),
    max_ticks=2000,
    monte_carlo_iterations=5,
    name_parts=("73 Easting", "Eagle Troop"),
    blue_personnel=120,
    blue_unit_definitions=2,
    red_personnel=500,
    red_unit_definitions=2,
    red_unit_count_is_minimum=True,
    terrain_type="flat_desert",
    terrain_width_m=6000.0,
    base_elevation_m=None,
    documented_outcome_minimum=3,
    documented_outcome_names=(),
    required_metrics=("exchange_ratio", "duration_s"),
)

FALKLANDS = LegacyScenarioCase(
    scenario_id="falklands",
    scenario_path=Path("data/scenarios/falklands_naval/scenario.yaml"),
    max_ticks=1000,
    monte_carlo_iterations=5,
    name_parts=("Falklands",),
    blue_personnel=1200,
    blue_unit_definitions=3,
    red_personnel=None,
    red_unit_definitions=1,
    red_unit_count_is_minimum=False,
    terrain_type="open_ocean",
    terrain_width_m=None,
    base_elevation_m=None,
    documented_outcome_minimum=2,
    documented_outcome_names=("blue_ships_sunk",),
    required_metrics=("blue_ships_sunk",),
)

GOLAN = LegacyScenarioCase(
    scenario_id="golan-heights",
    scenario_path=Path("data/scenarios/golan_heights/scenario.yaml"),
    max_ticks=2000,
    monte_carlo_iterations=3,
    name_parts=("Golan",),
    blue_personnel=160,
    blue_unit_definitions=1,
    red_personnel=2500,
    red_unit_definitions=3,
    red_unit_count_is_minimum=False,
    terrain_type="hilly_defense",
    terrain_width_m=None,
    base_elevation_m=900.0,
    documented_outcome_minimum=None,
    documented_outcome_names=("exchange_ratio", "red_units_destroyed"),
    required_metrics=("exchange_ratio",),
)

LEGACY_SCENARIOS = (EASTING, FALKLANDS, GOLAN)


@cache
def engagement_for(case: LegacyScenarioCase) -> HistoricalEngagement:
    return HistoricalDataLoader().load(case.scenario_path)


@cache
def runner_for(case: LegacyScenarioCase) -> ScenarioRunner:
    config = ScenarioRunnerConfig(
        master_seed=42,
        max_ticks=case.max_ticks,
        data_dir="data",
    )
    return ScenarioRunner(config)


@cache
def single_run_for(case: LegacyScenarioCase) -> SimulationResult:
    return runner_for(case).run(engagement_for(case))


def monte_carlo_for(
    case: LegacyScenarioCase,
    *,
    iterations: int | None = None,
) -> MonteCarloResult:
    count = case.monte_carlo_iterations if iterations is None else iterations
    config = MonteCarloConfig(num_iterations=count, base_seed=42)
    return MonteCarloHarness(runner_for(case), config).run(engagement_for(case))
