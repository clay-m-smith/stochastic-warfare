"""Immutable runtime-calibration ownership and checkpoint contracts."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from stochastic_warfare.simulation.calibration import ResolvedCalibration
from stochastic_warfare.simulation.performance_flags import (
    resolve_cross_bound_runtime_performance_flags,
)
from stochastic_warfare.simulation.scenario import ScenarioLoader


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO = DATA_DIR / "scenarios" / "calibration_air_ground" / "scenario.yaml"


def test_loader_compiles_one_stable_resolved_calibration_owner() -> None:
    context = ScenarioLoader(DATA_DIR).load(SCENARIO, seed=118)
    owner = context.resolved_calibration

    assert type(owner) is ResolvedCalibration
    assert context.cal_flat is owner
    assert resolve_cross_bound_runtime_performance_flags(
        authored_configuration=context.config.calibration_overrides,
        typed_calibration=context.calibration,
        flat_calibration=owner,
    ).enable_detection_culling is True

    checkpoint = context.get_state()
    context.set_state(copy.deepcopy(checkpoint))

    assert context.resolved_calibration is owner
    assert context.cal_flat is owner
    assert context.get_state() == checkpoint


def test_runtime_calibration_replacement_and_nested_mutation_reject() -> None:
    context = ScenarioLoader(DATA_DIR).load(SCENARIO, seed=118)
    owner = context.cal_flat

    with pytest.raises(
        AttributeError,
        match="stable ResolvedCalibration ownership binding",
    ):
        context.cal_flat = owner.to_dict()  # type: ignore[misc]
    with pytest.raises(TypeError):
        owner["enable_fog_of_war"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        owner["weapon_assignments"]["unit"] = "weapon"

    assert context.cal_flat is owner
