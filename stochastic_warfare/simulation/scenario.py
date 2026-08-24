"""Compatibility facade for campaign scenarios and runtime context.

Definitions live in responsibility-specific modules.  This facade preserves
the established import path while callers migrate incrementally.
"""

from stochastic_warfare.core.rng import RNGManager as RNGManager
from stochastic_warfare.simulation.context_checkpoint import (
    _CONTEXT_STATE_ENGINE_NAMES as _CONTEXT_STATE_ENGINE_NAMES,
    _json_values_equal as _json_values_equal,
)
from stochastic_warfare.simulation.runtime_context import (
    SimulationContext as SimulationContext,
    SimulationContextStatePlan as SimulationContextStatePlan,
)
from stochastic_warfare.simulation.scenario_config import (
    CampaignScenarioConfig as CampaignScenarioConfig,
    DepotConfig as DepotConfig,
    DoctrineSideAssignment as DoctrineSideAssignment,
    InitialIEDConfig as InitialIEDConfig,
    NON_RUNTIME_SCENARIO_ROOT_FIELDS as NON_RUNTIME_SCENARIO_ROOT_FIELDS,
    ObjectiveConfig as ObjectiveConfig,
    ReinforcementConfig as ReinforcementConfig,
    ReinforcementUnitConfig as ReinforcementUnitConfig,
    ScenarioReferenceError as ScenarioReferenceError,
    SchoolScenarioConfig as SchoolScenarioConfig,
    ScriptedEventConfig as ScriptedEventConfig,
    SideConfig as SideConfig,
    TerrainConfig as TerrainConfig,
    TickResolutionConfig as TickResolutionConfig,
    VictoryConditionConfig as VictoryConditionConfig,
    load_campaign_scenario_config as load_campaign_scenario_config,
    parse_campaign_scenario_config as parse_campaign_scenario_config,
    parse_scenario_start_time as parse_scenario_start_time,
)
from stochastic_warfare.simulation.scenario_loader import (
    ScenarioLoader as ScenarioLoader,
    _parse_weather_state as _parse_weather_state,
    register_dynamic_units as register_dynamic_units,
)

__all__ = [
    "CampaignScenarioConfig",
    "DepotConfig",
    "DoctrineSideAssignment",
    "InitialIEDConfig",
    "NON_RUNTIME_SCENARIO_ROOT_FIELDS",
    "ObjectiveConfig",
    "ReinforcementConfig",
    "ReinforcementUnitConfig",
    "ScenarioLoader",
    "ScenarioReferenceError",
    "SchoolScenarioConfig",
    "ScriptedEventConfig",
    "SideConfig",
    "SimulationContext",
    "SimulationContextStatePlan",
    "TerrainConfig",
    "TickResolutionConfig",
    "VictoryConditionConfig",
    "load_campaign_scenario_config",
    "parse_campaign_scenario_config",
    "parse_scenario_start_time",
    "register_dynamic_units",
]
