"""Compatibility contracts for the mechanical scenario-module split."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation import context_checkpoint
from stochastic_warfare.simulation import runtime_context
from stochastic_warfare.simulation import scenario as facade
from stochastic_warfare.simulation import scenario_config
from stochastic_warfare.simulation import scenario_loader


pytestmark = pytest.mark.test_evidence("structural_only")


def test_compatibility_facade_reexports_owner_identity() -> None:
    """The legacy path exposes the definition object, not a wrapper copy."""
    owners = {
        "CampaignScenarioConfig": scenario_config,
        "DepotConfig": scenario_config,
        "DoctrineSideAssignment": scenario_config,
        "InitialIEDConfig": scenario_config,
        "NON_RUNTIME_SCENARIO_ROOT_FIELDS": scenario_config,
        "ObjectiveConfig": scenario_config,
        "ReinforcementConfig": scenario_config,
        "ReinforcementUnitConfig": scenario_config,
        "ScenarioReferenceError": scenario_config,
        "SchoolScenarioConfig": scenario_config,
        "ScriptedEventConfig": scenario_config,
        "SideConfig": scenario_config,
        "TerrainConfig": scenario_config,
        "TickResolutionConfig": scenario_config,
        "VictoryConditionConfig": scenario_config,
        "load_campaign_scenario_config": scenario_config,
        "parse_campaign_scenario_config": scenario_config,
        "parse_scenario_start_time": scenario_config,
        "SimulationContext": runtime_context,
        "SimulationContextStatePlan": runtime_context,
        "ScenarioLoader": scenario_loader,
        "register_dynamic_units": scenario_loader,
    }
    assert {
        name: getattr(facade, name) is getattr(owner, name)
        for name, owner in owners.items()
    } == dict.fromkeys(owners, True)


def test_checkpoint_private_compatibility_symbols_preserve_identity() -> None:
    """Current internal callers retain the checkpoint-owner identities."""
    assert (
        facade._CONTEXT_STATE_ENGINE_NAMES
        is context_checkpoint._CONTEXT_STATE_ENGINE_NAMES
    )
    assert facade._json_values_equal is context_checkpoint._json_values_equal


def test_facade_declares_only_supported_public_scenario_surface() -> None:
    """Wildcard imports remain bounded to the deliberate compatibility API."""
    assert set(facade.__all__) == {
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
    }
