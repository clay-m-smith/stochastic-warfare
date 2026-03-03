"""Campaign runner — wraps ScenarioLoader + SimulationEngine for validation.

Provides the campaign analog of :class:`ScenarioRunner`: loads a
:class:`HistoricalCampaign`, wires all domain modules via
:class:`ScenarioLoader`, runs the campaign through :class:`SimulationEngine`,
and packages the result for metric extraction and historical comparison.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine, SimulationRunResult
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.recorder import RecorderConfig, SimulationRecorder
from stochastic_warfare.simulation.scenario import ScenarioLoader, SimulationContext
from stochastic_warfare.simulation.victory import (
    ObjectiveState,
    VictoryEvaluator,
    VictoryEvaluatorConfig,
    VictoryResult,
)
from stochastic_warfare.validation.campaign_data import CampaignDataLoader, HistoricalCampaign

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CampaignRunnerConfig(BaseModel):
    """Configuration for the campaign runner."""

    data_dir: str = "data"
    engine_config: EngineConfig = EngineConfig()
    campaign_config: CampaignConfig = CampaignConfig()
    battle_config: BattleConfig = BattleConfig()
    snapshot_interval_ticks: int = 100


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class CampaignRunResult:
    """Result of a single campaign validation run.

    Contains all data needed for metric extraction and AI validation.
    """

    seed: int
    ticks_executed: int
    duration_simulated_s: float
    victory_result: VictoryResult
    recorder: SimulationRecorder | None
    final_units_by_side: dict[str, list[Any]]
    final_morale_states: dict[str, Any]
    terminated_by: str
    run_result: SimulationRunResult | None = None


# ---------------------------------------------------------------------------
# Campaign runner
# ---------------------------------------------------------------------------


class CampaignRunner:
    """Run a historical campaign scenario through the full simulation engine.

    Wraps :class:`ScenarioLoader` and :class:`SimulationEngine` into a
    single ``run()`` call suitable for Monte Carlo iteration.

    Parameters
    ----------
    config:
        Runner configuration.  Defaults are used when ``None``.
    """

    def __init__(self, config: CampaignRunnerConfig | None = None) -> None:
        self._config = config or CampaignRunnerConfig()

    def run(
        self,
        campaign: HistoricalCampaign,
        seed: int | None = None,
    ) -> CampaignRunResult:
        """Execute one campaign run.

        Parameters
        ----------
        campaign:
            Historical campaign scenario definition.
        seed:
            Master PRNG seed.  Defaults to 42 if not specified.

        Returns
        -------
        CampaignRunResult
            Complete result with recorder, final states, and victory info.
        """
        seed = seed if seed is not None else 42

        # 1. Convert to CampaignScenarioConfig and write temp YAML
        scenario_config = CampaignDataLoader.to_scenario_config(campaign)
        config_dict = scenario_config.model_dump()

        # Write temp YAML for ScenarioLoader
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            yaml.dump(config_dict, tmp, default_flow_style=False)
            tmp_path = Path(tmp.name)

        try:
            # 2. Load scenario via ScenarioLoader
            data_dir = Path(self._config.data_dir)
            loader = ScenarioLoader(data_dir)
            ctx = loader.load(tmp_path, seed=seed)
        finally:
            # Clean up temp file
            try:
                tmp_path.unlink()
            except OSError:
                pass

        # 3. Create victory evaluator from config
        victory_evaluator = self._create_victory_evaluator(ctx, campaign)

        # 4. Create recorder
        recorder = SimulationRecorder(
            ctx.event_bus,
            RecorderConfig(
                snapshot_interval_ticks=self._config.snapshot_interval_ticks,
            ),
        )

        # 5. Create and run engine
        engine_config = self._config.engine_config
        engine = SimulationEngine(
            ctx,
            config=engine_config,
            campaign_config=self._config.campaign_config,
            battle_config=self._config.battle_config,
            victory_evaluator=victory_evaluator,
            recorder=recorder,
        )

        run_result = engine.run()

        # 6. Package result
        terminated_by = run_result.victory_result.condition_type or "completed"

        return CampaignRunResult(
            seed=seed,
            ticks_executed=run_result.ticks_executed,
            duration_simulated_s=run_result.duration_s,
            victory_result=run_result.victory_result,
            recorder=recorder,
            final_units_by_side={
                side: list(units)
                for side, units in ctx.units_by_side.items()
            },
            final_morale_states=dict(ctx.morale_states),
            terminated_by=terminated_by,
            run_result=run_result,
        )

    def _create_victory_evaluator(
        self,
        ctx: SimulationContext,
        campaign: HistoricalCampaign,
    ) -> VictoryEvaluator:
        """Build a VictoryEvaluator from the campaign configuration."""
        from stochastic_warfare.core.types import Position

        objectives = []
        for obj_cfg in campaign.objectives:
            pos = Position(
                easting=obj_cfg.position[0],
                northing=obj_cfg.position[1],
                altitude=0.0,
            )
            objectives.append(
                ObjectiveState(
                    objective_id=obj_cfg.objective_id,
                    position=pos,
                    radius_m=obj_cfg.radius_m,
                )
            )

        max_duration_s = campaign.duration_hours * 3600.0

        return VictoryEvaluator(
            objectives=objectives,
            conditions=campaign.victory_conditions,
            event_bus=ctx.event_bus,
            max_duration_s=max_duration_s,
        )
