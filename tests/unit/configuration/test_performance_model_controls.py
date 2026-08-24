"""Phase 118 strict model-control calibration boundaries."""

from __future__ import annotations

from typing import Any, Callable

import pytest
from pydantic import ValidationError

from api.schemas import (
    BatchSubmitRequest,
    CompareRequest,
    DoctrineSideAssignmentRequest,
    DoctrineVariantRequest,
    RunSubmitRequest,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.performance_flags import (
    LOD_RUNTIME_COMPATIBILITY_DEFAULTS,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)
from stochastic_warfare.tools.comparison import ComparisonConfig
from stochastic_warfare.tools.sensitivity import SweepConfig


DATA_DIR = "data"
UNSUPPORTED_MODEL_CONTROLS = (
    "enable_scan_scheduling",
    "enable_lod",
)
SUPPORTED_EXECUTION_FLAGS = (
    "enable_detection_culling",
    "enable_soa",
    "enable_parallel_detection",
)


def _scenario(calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": "Phase 118 LOD validation",
        "date": "2024-01-01T00:00:00Z",
        "duration_hours": 1.0,
        "terrain": {
            "width_m": 1_000.0,
            "height_m": 1_000.0,
            "terrain_type": "flat_desert",
        },
        "sides": [
            {"side": "blue", "units": []},
            {"side": "red", "units": []},
        ],
        "calibration_overrides": calibration or {},
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"lod_nearby_interval": 0},
        {"lod_distant_interval": -1},
        {"lod_hysteresis_ticks": 0},
        {"lod_nearby_interval": True},
        {"lod_distant_interval": 2.0},
        {"lod_nearby_interval": 6, "lod_distant_interval": 5},
    ],
)
def test_lod_periods_reject_at_every_typed_input_boundary(
    patch: dict[str, Any],
) -> None:
    source = CampaignScenarioConfig.model_validate(_scenario())
    boundaries: tuple[Callable[[], object], ...] = (
        lambda: CalibrationSchema.model_validate(patch),
        lambda: CampaignScenarioConfig.model_validate(_scenario(patch)),
        lambda: load_campaign_scenario_config(
            source_config=source,
            calibration_overrides=patch,
        ),
        lambda: RunSubmitRequest.model_validate(
            {
                "scenario": "calibration_air_ground",
                "config_overrides": patch,
            },
        ),
        lambda: AnalysisVariant(
            variant_id="phase118-invalid-lod",
            calibration_patch=patch,
        ),
    )
    for boundary in boundaries:
        with pytest.raises((ValidationError, ValueError)):
            boundary()


def test_lod_periods_accept_only_canonical_compatibility_defaults() -> None:
    calibration = CalibrationSchema.model_validate(
        {
            "lod_nearby_interval": 5,
            "lod_distant_interval": 20,
            "lod_hysteresis_ticks": 3,
        },
    )

    assert (
        calibration.lod_nearby_interval,
        calibration.lod_distant_interval,
        calibration.lod_hysteresis_ticks,
    ) == (5, 20, 3)


@pytest.mark.parametrize(
    "flag",
    [
        "enable_detection_culling",
        "enable_scan_scheduling",
        "enable_lod",
        "enable_soa",
        "enable_parallel_detection",
    ],
)
@pytest.mark.parametrize("invalid", [0, 1, "false", "true"])
def test_governed_flags_are_strict_booleans(
    flag: str,
    invalid: object,
) -> None:
    with pytest.raises(ValidationError):
        CalibrationSchema.model_validate({flag: invalid})


def _unsupported_message(operation: Callable[[], object]) -> str:
    with pytest.raises((ValidationError, ValueError)) as captured:
        operation()
    return str(captured.value)


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_retired_model_control_activation_rejects_at_typed_boundaries(
    flag: str,
) -> None:
    patch = {flag: True}
    source = CampaignScenarioConfig.model_validate(_scenario())
    source_before = source.model_dump(mode="json")
    boundaries: tuple[Callable[[], object], ...] = (
        lambda: CalibrationSchema.model_validate(patch, strict=True),
        lambda: CampaignScenarioConfig.model_validate(
            _scenario(patch),
            strict=True,
        ),
        lambda: load_campaign_scenario_config(
            source_config=source,
            calibration_overrides=patch,
        ),
        lambda: RunSubmitRequest.model_validate(
            {
                "scenario": "calibration_air_ground",
                "config_overrides": patch,
            },
        ),
        lambda: BatchSubmitRequest.model_validate(
            {
                "scenario": "calibration_air_ground",
                "config_overrides": patch,
            },
        ),
        lambda: CompareRequest.model_validate(
            {
                "scenario": "calibration_air_ground",
                "overrides_a": {},
                "overrides_b": patch,
            },
        ),
        lambda: DoctrineVariantRequest.model_validate(
            {
                "variant_id": "retired-control",
                "assignments": [
                    DoctrineSideAssignmentRequest(
                        side="blue",
                        school_id="western_maneuver",
                    ),
                ],
                "calibration_patch": patch,
            },
        ),
        lambda: AnalysisVariant(
            variant_id="retired-control",
            calibration_patch=patch,
        ),
        lambda: ComparisonConfig(
            scenario_path="data/scenarios/calibration_air_ground/scenario.yaml",
            overrides_b=patch,
        ),
    )

    for boundary in boundaries:
        message = _unsupported_message(boundary)
        assert flag in message
        assert "unsupported" in message.lower()
        assert source.model_dump(mode="json") == source_before


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("lod_nearby_interval", 4),
        ("lod_nearby_interval", 21),
        ("lod_distant_interval", 19),
        ("lod_hysteresis_ticks", 2),
    ),
)
def test_nondefault_lod_controls_are_explicitly_unsupported(
    field: str,
    value: int,
) -> None:
    message = _unsupported_message(
        lambda: CalibrationSchema.model_validate(
            {field: value},
            strict=True,
        ),
    )
    assert field in message
    assert "unsupported" in message.lower()


def test_retired_model_control_defaults_and_explicit_false_remain_accepted() -> None:
    calibration = CalibrationSchema.model_validate(
        {
            "enable_scan_scheduling": False,
            "enable_lod": False,
            "lod_nearby_interval": 5,
            "lod_distant_interval": 20,
            "lod_hysteresis_ticks": 3,
        },
        strict=True,
    )

    assert calibration.enable_scan_scheduling is False
    assert calibration.enable_lod is False
    assert (
        calibration.lod_nearby_interval,
        calibration.lod_distant_interval,
        calibration.lod_hysteresis_ticks,
    ) == (5, 20, 3)


@pytest.mark.parametrize("flag", SUPPORTED_EXECUTION_FLAGS)
def test_supported_execution_flags_still_accept_explicit_true(
    flag: str,
) -> None:
    patch = {flag: True}
    calibration = CalibrationSchema.model_validate(patch, strict=True)
    scenario = CampaignScenarioConfig.model_validate(
        _scenario(patch),
        strict=True,
    )
    variant = AnalysisVariant(
        variant_id=f"supported-{flag}",
        calibration_patch=patch,
    )
    request = RunSubmitRequest.model_validate(
        {
            "scenario": "calibration_air_ground",
            "config_overrides": patch,
        },
    )

    assert getattr(calibration, flag) is True
    assert getattr(scenario.calibration_overrides, flag) is True
    assert getattr(variant.calibration_patch, flag) is True
    assert getattr(request.config_overrides, flag) is True


def test_enable_all_modern_cannot_activate_retired_model_controls() -> None:
    calibration = CalibrationSchema(enable_all_modern=True)

    assert calibration.enable_scan_scheduling is False
    assert calibration.enable_lod is False
    assert not set(UNSUPPORTED_MODEL_CONTROLS).intersection(
        calibration._MODERN_FLAGS,
    )


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_runtime_factory_rejects_construct_bypass_without_mutating_source(
    flag: str,
) -> None:
    source = CampaignScenarioConfig.model_validate(_scenario())
    source_before = source.model_dump(mode="json")
    invalid_patch = CalibrationSchema.model_construct(**{flag: True})
    bypassed_variant = AnalysisVariant.model_construct(
        variant_id=f"bypassed-{flag}",
        calibration_patch=invalid_patch,
        doctrine_variant=None,
    )

    message = _unsupported_message(
        lambda: SimulationRuntimeFactory().prepare_config(
            source,
            DATA_DIR,
            (bypassed_variant,),
            source_label="<phase118-retired-control-bypass>",
        ),
    )
    assert flag in message
    assert "unsupported" in message.lower()
    assert source.model_dump(mode="json") == source_before


@pytest.mark.parametrize("flag", UNSUPPORTED_MODEL_CONTROLS)
def test_sensitivity_rejects_retired_model_control_parameter(flag: str) -> None:
    message = _unsupported_message(
        lambda: SweepConfig(
            scenario_path="data/scenarios/calibration_air_ground/scenario.yaml",
            parameter_name=flag,
            values=[0.0],
        ),
    )
    assert flag in message
    assert "unsupported" in message.lower()


@pytest.mark.parametrize(
    "field",
    tuple(LOD_RUNTIME_COMPATIBILITY_DEFAULTS),
)
def test_sensitivity_rejects_retired_lod_parameter(field: str) -> None:
    message = _unsupported_message(
        lambda: SweepConfig(
            scenario_path="data/scenarios/calibration_air_ground/scenario.yaml",
            parameter_name=field,
            values=[float(LOD_RUNTIME_COMPATIBILITY_DEFAULTS[field])],
        ),
    )
    assert field in message
    assert "unsupported" in message.lower()
