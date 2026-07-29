"""Phase 107 red tests for effective, validated era feature gates.

These tests deliberately exercise ``ScenarioLoader`` rather than the
validation runner.  REM-007 is not satisfied by declaring era metadata: the
effective era configuration must control optional engines and reject
impossible unit loadouts on the production path.
"""

from __future__ import annotations

import copy
from pathlib import Path

from pydantic import ValidationError
import pytest
import yaml

import stochastic_warfare.core.era as era_module
from stochastic_warfare.core.era import EraConfig, get_era_config, register_era_config
from stochastic_warfare.simulation.scenario import ScenarioLoader


_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_BASE_SCENARIO = _DATA_DIR / "scenarios" / "test_scenario" / "scenario.yaml"
_CUSTOM_ERA = "phase107_test_era"

_ERA_FEATURES = {
    "ew",
    "space",
    "cbrn",
    "gps",
    "thermal_sights",
    "data_links",
    "pgm",
}

_OPTIONAL_SUITES = (
    ("ew", "ew_config", "enable_ew", "ew_engine"),
    ("space", "space_config", "enable_space", "space_engine"),
    ("cbrn", "cbrn_config", "enable_cbrn", "cbrn_engine"),
)


@pytest.fixture(autouse=True)
def _isolate_era_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep custom registrations and mutation probes local to each test."""
    monkeypatch.setattr(
        era_module,
        "_ERA_REGISTRY",
        copy.deepcopy(era_module._ERA_REGISTRY),
    )


def _base_scenario_data() -> dict:
    with _BASE_SCENARIO.open(encoding="utf-8") as scenario_file:
        return yaml.safe_load(scenario_file)


def _write_scenario(
    tmp_path: Path,
    data: dict,
    *,
    filename: str = "scenario.yaml",
) -> Path:
    scenario_path = tmp_path / filename
    scenario_path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return scenario_path


def _load_custom_era(
    tmp_path: Path,
    *,
    disabled_modules: set[str] | None = None,
    available_sensor_types: set[str] | None = None,
    config_blocks: dict[str, dict] | None = None,
    blue_unit_type: str | None = None,
) -> object:
    era_config = EraConfig(
        disabled_modules=disabled_modules or set(),
        available_sensor_types=available_sensor_types or set(),
    )
    register_era_config(_CUSTOM_ERA, era_config)

    raw = _base_scenario_data()
    raw["era"] = _CUSTOM_ERA
    for field in ("ew_config", "space_config", "cbrn_config"):
        raw.pop(field, None)
    effective_blocks = copy.deepcopy(config_blocks or {})
    space_block = effective_blocks.get("space_config")
    if (
        isinstance(space_block, dict)
        and space_block.get("enable_space") is True
    ):
        space_block.setdefault(
            "constellation_ids",
            ["keyhole_optical"],
        )
    raw.update(effective_blocks)
    if blue_unit_type is not None:
        raw["sides"][0]["units"] = [{"unit_type": blue_unit_type, "count": 1}]

    scenario_path = _write_scenario(tmp_path, raw)
    return ScenarioLoader(_DATA_DIR).load(scenario_path, seed=107)


def _feature_names(config: EraConfig) -> set[str]:
    return {
        feature.value if hasattr(feature, "value") else str(feature)
        for feature in config.disabled_modules
    }


def _assert_actionable_gate_error(
    error: pytest.ExceptionInfo[ValueError],
    *,
    feature: str,
    offending_clues: tuple[str, ...],
) -> None:
    message = str(error.value).lower()
    assert feature.lower() in message
    assert any(clue.lower() in message for clue in offending_clues)


def test_era_config_accepts_exactly_the_seven_declared_features() -> None:
    config = EraConfig(disabled_modules=_ERA_FEATURES)

    assert _feature_names(config) == _ERA_FEATURES


def test_era_config_rejects_misspelled_feature_gate_field() -> None:
    with pytest.raises(ValidationError, match="disabled_moduls"):
        EraConfig.model_validate({"disabled_moduls": ["gps"]})

    with pytest.raises(ValidationError, match="orbital_lasers"):
        EraConfig(disabled_modules={"orbital_lasers"})


def test_unknown_unregistered_scenario_era_is_rejected(
    tmp_path: Path,
) -> None:
    raw = _base_scenario_data()
    raw["era"] = "phase107_unregistered"
    scenario_path = _write_scenario(tmp_path, raw)

    with pytest.raises(ValueError) as error:
        ScenarioLoader(_DATA_DIR).load(scenario_path, seed=107)

    message = str(error.value).lower()
    assert "era" in message
    assert "phase107_unregistered" in message


def test_registry_returns_isolated_effective_configs() -> None:
    registered = EraConfig(disabled_modules={"space"})
    register_era_config(_CUSTOM_ERA, registered)

    first = get_era_config(_CUSTOM_ERA)
    second = get_era_config(_CUSTOM_ERA)
    first.disabled_modules.add("ew")

    assert first is not second
    assert first is not registered
    assert _feature_names(second) == {"space"}
    assert _feature_names(registered) == {"space"}


def test_registry_revalidates_mutated_config_at_public_boundary() -> None:
    mutated = EraConfig()
    mutated.disabled_modules.add("orbital_lasers")  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="orbital_lasers"):
        register_era_config(_CUSTOM_ERA, mutated)


@pytest.mark.parametrize(
    ("feature", "config_field", "enable_field", "engine_field"),
    _OPTIONAL_SUITES,
)
def test_missing_optional_suite_is_absent_from_runtime_and_checkpoint(
    tmp_path: Path,
    feature: str,
    config_field: str,
    enable_field: str,
    engine_field: str,
) -> None:
    del feature, config_field, enable_field

    context = _load_custom_era(tmp_path)

    assert getattr(context, engine_field) is None
    assert engine_field not in context.get_state()


@pytest.mark.parametrize(
    ("feature", "config_field", "enable_field", "engine_field"),
    _OPTIONAL_SUITES,
)
def test_false_optional_suite_is_absent_from_runtime_and_checkpoint(
    tmp_path: Path,
    feature: str,
    config_field: str,
    enable_field: str,
    engine_field: str,
) -> None:
    del feature

    context = _load_custom_era(
        tmp_path,
        config_blocks={config_field: {enable_field: False}},
    )

    assert getattr(context, engine_field) is None
    assert engine_field not in context.get_state()


@pytest.mark.parametrize(
    ("feature", "config_field", "enable_field", "engine_field"),
    _OPTIONAL_SUITES,
)
def test_enabled_optional_suite_is_present_in_runtime_and_checkpoint(
    tmp_path: Path,
    feature: str,
    config_field: str,
    enable_field: str,
    engine_field: str,
) -> None:
    del feature

    context = _load_custom_era(
        tmp_path,
        config_blocks={config_field: {enable_field: True}},
    )

    assert getattr(context, engine_field) is not None
    assert engine_field in context.get_state()


@pytest.mark.parametrize(
    ("feature", "config_field", "enable_field", "engine_field"),
    _OPTIONAL_SUITES,
)
def test_disabled_optional_suite_cannot_be_explicitly_enabled(
    tmp_path: Path,
    feature: str,
    config_field: str,
    enable_field: str,
    engine_field: str,
) -> None:
    del engine_field

    with pytest.raises(ValueError) as error:
        _load_custom_era(
            tmp_path,
            disabled_modules={feature},
            config_blocks={config_field: {enable_field: True}},
        )

    _assert_actionable_gate_error(
        error,
        feature=feature,
        offending_clues=(config_field, enable_field, "disabled"),
    )


def test_space_can_remain_enabled_with_its_gps_child_disabled(
    tmp_path: Path,
) -> None:
    context = _load_custom_era(
        tmp_path,
        disabled_modules={"gps"},
        config_blocks={"space_config": {"enable_space": True}},
    )

    assert context.space_engine is not None
    assert context.space_engine.gps_engine is None
    assert context.space_engine.get_gps_cep("blue", 0.0) == 100.0
    assert "gps_engine" not in context.get_state()["space_engine"]


def test_thermal_sights_gate_rejects_thermal_sensor_loadout(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError) as error:
        _load_custom_era(
            tmp_path,
            disabled_modules={"thermal_sights"},
            blue_unit_type="us_m1a2_sep",
        )

    _assert_actionable_gate_error(
        error,
        feature="thermal_sights",
        offending_clues=("thermal", "thermal_sight", "us_m1a2_sep", "citv"),
    )


def test_available_sensor_types_rejects_unavailable_loaded_sensor(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError) as error:
        _load_custom_era(
            tmp_path,
            available_sensor_types={"VISUAL"},
            blue_unit_type="us_m1a2_sep",
        )

    _assert_actionable_gate_error(
        error,
        feature="available_sensor_types",
        offending_clues=("nvg", "active_ir_sight", "t72m", "tpn-3-49"),
    )


def test_data_links_gate_rejects_finite_link_uav_loadout(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError) as error:
        _load_custom_era(
            tmp_path,
            disabled_modules={"data_links"},
            blue_unit_type="dragon_eye_uav",
        )

    _assert_actionable_gate_error(
        error,
        feature="data_links",
        offending_clues=("dragon_eye_uav", "data_link_range", "data link"),
    )


def test_pgm_gate_rejects_guided_weapon_or_ammunition_loadout(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError) as error:
        _load_custom_era(
            tmp_path,
            disabled_modules={"pgm"},
            blue_unit_type="javelin_team",
        )

    _assert_actionable_gate_error(
        error,
        feature="pgm",
        offending_clues=("javelin", "guidance", "guided", "ir"),
    )


def test_checkpoint_rejects_changed_effective_era_gate(
    tmp_path: Path,
) -> None:
    context = _load_custom_era(tmp_path)
    checkpoint = context.get_state()
    checkpoint["era_config"]["disabled_modules"] = ["ew"]

    with pytest.raises(ValueError) as error:
        context.set_state(checkpoint)

    message = str(error.value).lower()
    assert "era" in message
    assert "disabled_modules" in message or "feature gate" in message


def test_checkpoint_era_sets_are_canonical_and_order_insensitive(
    tmp_path: Path,
) -> None:
    context = _load_custom_era(
        tmp_path,
        disabled_modules={"ew", "space", "cbrn"},
        available_sensor_types={
            "VISUAL",
            "THERMAL",
            "RADAR",
            "ESM",
            "NVG",
            "ACTIVE_SONAR",
            "PASSIVE_SONAR",
        },
    )
    checkpoint = context.get_state()
    assert checkpoint["era_config"]["disabled_modules"] == [
        "cbrn",
        "ew",
        "space",
    ]
    assert checkpoint["era_config"]["available_sensor_types"] == sorted(
        checkpoint["era_config"]["available_sensor_types"],
    )

    checkpoint["era_config"]["disabled_modules"].reverse()
    checkpoint["era_config"]["available_sensor_types"].reverse()

    context.set_state(checkpoint)
