"""Campaign-level historical data models and loader.

Extends the engagement-level :mod:`historical_data` with campaign-specific
structures — multi-day duration, AI expectations, reinforcement schedules,
and logistics.  :class:`HistoricalCampaign` wraps :class:`CampaignScenarioConfig`
fields plus ``documented_outcomes`` and ``ai_expectations`` for validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator
from stochastic_warfare.simulation.calibration import CalibrationSchema

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ObjectiveConfig,
    ReinforcementConfig,
    SideConfig,
    TerrainConfig,
    TickResolutionConfig,
    VictoryConditionConfig,
)
from stochastic_warfare.validation.historical_data import HistoricalMetric

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AI behavior expectations
# ---------------------------------------------------------------------------


class AIExpectation(BaseModel):
    """Expected AI behavior within a time window.

    Used by :class:`AIDecisionValidator` to verify that AI commanders
    make contextually appropriate decisions during campaign validation.
    """

    side: str
    time_range_s: list[float]  # [start_s, end_s]
    expected_posture: str  # "attack", "defend", "withdraw", "culminate"
    description: str = ""
    tolerance: str = "moderate"  # "strict" | "moderate" | "loose"

    @field_validator("time_range_s")
    @classmethod
    def _valid_range(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError("time_range_s must have exactly [start, end]")
        if v[0] < 0 or v[1] < 0:
            raise ValueError("time_range_s values must be non-negative")
        if v[0] >= v[1]:
            raise ValueError("time_range_s start must be < end")
        return v

    @field_validator("tolerance")
    @classmethod
    def _valid_tolerance(cls, v: str) -> str:
        allowed = {"strict", "moderate", "loose"}
        if v not in allowed:
            raise ValueError(f"tolerance must be one of {allowed}; got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Historical campaign model
# ---------------------------------------------------------------------------


class HistoricalCampaign(BaseModel):
    """Complete campaign scenario for validation against historical data.

    Embeds the same fields as :class:`CampaignScenarioConfig` plus
    historical comparison data (``documented_outcomes``, ``sources``,
    ``ai_expectations``).
    """

    # --- Campaign scenario fields (mirror CampaignScenarioConfig) ---
    name: str
    date: str
    duration_hours: float
    latitude: float = 0.0
    longitude: float = 0.0
    tick_resolution: TickResolutionConfig = TickResolutionConfig()
    weather_conditions: dict[str, Any] = {}
    terrain: TerrainConfig
    sides: list[SideConfig]
    objectives: list[ObjectiveConfig] = []
    victory_conditions: list[VictoryConditionConfig] = []
    reinforcements: list[ReinforcementConfig] = []
    calibration_overrides: CalibrationSchema = CalibrationSchema()

    # --- Historical validation fields ---
    documented_outcomes: list[HistoricalMetric] = []
    sources: list[str] = []
    ai_expectations: list[AIExpectation] = []

    @field_validator("sides")
    @classmethod
    def _at_least_two_sides(cls, v: list[SideConfig]) -> list[SideConfig]:
        if len(v) < 2:
            raise ValueError("campaign requires at least 2 sides")
        return v

    @field_validator("duration_hours")
    @classmethod
    def _positive_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_hours must be positive")
        return v


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class CampaignDataLoader:
    """Load campaign-level historical scenarios from YAML files."""

    def load(self, path: Path) -> HistoricalCampaign:
        """Load a single campaign definition from *path*.

        Parameters
        ----------
        path:
            Path to the campaign scenario YAML file.

        Returns
        -------
        HistoricalCampaign
            Validated campaign model ready for runner consumption.
        """
        with open(path) as f:
            raw = yaml.safe_load(f)
        campaign = HistoricalCampaign.model_validate(raw)
        logger.info("Loaded campaign %r from %s", campaign.name, path)
        return campaign

    @staticmethod
    def to_scenario_config(campaign: HistoricalCampaign) -> CampaignScenarioConfig:
        """Convert a :class:`HistoricalCampaign` to :class:`CampaignScenarioConfig`.

        Strips validation-only fields (documented_outcomes, sources,
        ai_expectations) and returns a config suitable for
        :class:`ScenarioLoader.load`.
        """
        return CampaignScenarioConfig(
            name=campaign.name,
            date=campaign.date,
            duration_hours=campaign.duration_hours,
            latitude=campaign.latitude,
            longitude=campaign.longitude,
            tick_resolution=campaign.tick_resolution,
            weather_conditions=campaign.weather_conditions,
            terrain=campaign.terrain,
            sides=campaign.sides,
            objectives=campaign.objectives,
            victory_conditions=campaign.victory_conditions,
            reinforcements=campaign.reinforcements,
            calibration_overrides=campaign.calibration_overrides,
        )
