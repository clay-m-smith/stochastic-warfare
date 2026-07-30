"""Campaign validation runner backed by the production runtime factory.

Provides the campaign analog of :class:`ScenarioRunner`: loads a
:class:`HistoricalCampaign`, executes the authoritative runtime construction
boundary, and packages the result for metric extraction and historical
comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationRunResult,
)
from stochastic_warfare.simulation.recorder import RecorderConfig, SimulationRecorder
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeProvenance,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.victory import VictoryResult
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
    runtime_provenance: RuntimeProvenance | None = None


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

        scenario_config = CampaignDataLoader.to_scenario_config(campaign)
        variant = AnalysisVariant(variant_id="campaign-validation")
        prepared = SimulationRuntimeFactory().prepare_config(
            scenario_config,
            self._config.data_dir,
            (variant,),
            source_label=f"<campaign:{campaign.name}>",
        )
        engine_config = self._config.engine_config
        session = prepared.build(
            "campaign-validation",
            seed=seed,
            max_ticks=engine_config.max_ticks,
            recorder_factory=lambda context: SimulationRecorder(
                context.event_bus,
                RecorderConfig(
                    snapshot_interval_ticks=(
                        self._config.snapshot_interval_ticks
                    ),
                ),
            ),
            engine_config=engine_config,
            campaign_config=self._config.campaign_config,
            battle_config=self._config.battle_config,
        )
        run_result = session.run_to_completion()
        ctx = session.context
        terminated_by = run_result.victory_result.condition_type or "completed"

        return CampaignRunResult(
            seed=seed,
            ticks_executed=run_result.ticks_executed,
            duration_simulated_s=run_result.duration_s,
            victory_result=run_result.victory_result,
            recorder=session.recorder,
            final_units_by_side={
                side: list(units)
                for side, units in ctx.units_by_side.items()
            },
            final_morale_states=dict(ctx.morale_states),
            terminated_by=terminated_by,
            run_result=run_result,
            runtime_provenance=session.provenance(),
        )
