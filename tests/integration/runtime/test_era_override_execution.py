"""Phase 114 red proofs for executable, typed era overrides.

The tests use a production ``ScenarioLoader`` context and
``SimulationEngine.step()``.  Dictionary presence is deliberately not
accepted as behavioral evidence for REM-018.
"""

from __future__ import annotations

import copy
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError
import pytest
import yaml

import stochastic_warfare.core.era as era_module
import stochastic_warfare.simulation.scenario as scenario_module
from stochastic_warfare.core.era import EraConfig, register_era_config
from stochastic_warfare.core.types import Position
from stochastic_warfare.logistics.medical import (
    CasualtyRecord,
    MedicalConfig,
    MedicalFacility,
    MedicalFacilityType,
)
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.era_runtime import EraRuntimeContract
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    SimulationContext,
)


_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _ROOT / "data"
_BASE_SCENARIO = _DATA_DIR / "scenarios" / "test_scenario" / "scenario.yaml"
_CUSTOM_ERA = "phase114_red_era"


@pytest.fixture(autouse=True)
def _isolate_era_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        era_module,
        "_ERA_REGISTRY",
        copy.deepcopy(era_module._ERA_REGISTRY),
    )


def _scenario_data() -> dict:
    with _BASE_SCENARIO.open(encoding="utf-8") as scenario_file:
        data = yaml.safe_load(scenario_file)
    data["era"] = _CUSTOM_ERA
    data["sides"][0]["units"] = [{"unit_type": "m1a2", "count": 1}]
    data["sides"][1]["units"] = [{"unit_type": "t72m", "count": 1}]
    return data


def _load(tmp_path: Path, data: dict, era_config: EraConfig):
    register_era_config(_CUSTOM_ERA, era_config)
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return ScenarioLoader(_DATA_DIR).load(scenario_path, seed=114)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_mach", 0.8),
        ("c2_delay_multiplier", 5.0),
        ("cbrn_nuclear_enabled", False),
        ("treatment_hours_minor", True),
        ("repair_time_hours", "6.0"),
        ("treatment_hours_serious", 0.0),
        ("treatment_hours_critical", float("nan")),
    ),
)
def test_physics_override_schema_rejects_unknown_or_invalid_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError, match=field):
        EraConfig(physics_overrides={field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("tactial_s", 7.0),
        ("tactical_s", False),
        ("operational_s", "13.0"),
        ("strategic_s", None),
        ("strategic_s", -1.0),
        ("operational_s", float("inf")),
        ("strategic_s", 1e-7),
        ("operational_s", 1.5e-6),
        ("tactical_s", 1e308),
        ("strategic_s", 1e12),
    ),
)
def test_tick_override_schema_rejects_unknown_or_invalid_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError, match=field):
        EraConfig(tick_resolution_overrides={field: value})


def test_registration_revalidates_mutated_input_and_preserves_registry() -> None:
    original = EraConfig(
        tick_resolution_overrides={"strategic_s": 11.0},
    )
    register_era_config(_CUSTOM_ERA, original)
    before = era_module.get_era_config(_CUSTOM_ERA)
    invalid_type = EraConfig(
        tick_resolution_overrides={"strategic_s": 17.0},
    )
    object.__setattr__(
        invalid_type.tick_resolution_overrides,
        "strategic_s",
        True,
    )
    invalid_null = EraConfig(
        physics_overrides={"repair_time_hours": 1.0},
    )
    object.__setattr__(
        invalid_null.physics_overrides,
        "repair_time_hours",
        None,
    )
    invalid_nested_extra = EraConfig()
    object.__setattr__(
        invalid_nested_extra.physics_overrides,
        "invented_nested",
        1.0,
    )
    invalid_outer_extra = EraConfig()
    object.__setattr__(invalid_outer_extra, "invented_outer", 1.0)

    for invalid, match in (
        (invalid_type, "strategic_s"),
        (invalid_null, "repair_time_hours"),
        (invalid_nested_extra, "invented_nested"),
        (invalid_outer_extra, "invented_outer"),
    ):
        with pytest.raises(ValueError, match=match):
            register_era_config(_CUSTOM_ERA, invalid)
        assert era_module.get_era_config(_CUSTOM_ERA) == before

    retrieved = era_module.get_era_config(_CUSTOM_ERA)
    retrieved.disabled_modules.add("ew")
    assert "ew" not in era_module.get_era_config(
        _CUSTOM_ERA,
    ).disabled_modules


@pytest.mark.parametrize(
    ("source", "value", "match"),
    (
        ("resolution", 1e-7, "strategic_s"),
        ("resolution", 1.5e-6, "strategic_s"),
        ("resolution", 1e308, "strategic_s"),
        ("uniform", 1e-7, "tick_duration_seconds"),
        ("uniform", 1e308, "tick_duration_seconds"),
    ),
)
def test_scenario_tick_sources_reject_clock_quantization_or_overflow(
    source: str,
    value: float,
    match: str,
) -> None:
    data = _scenario_data()
    if source == "resolution":
        data.pop("tick_duration_seconds")
        data["tick_resolution"]["strategic_s"] = value
    else:
        data["tick_duration_seconds"] = value

    with pytest.raises(ValidationError, match=match):
        CampaignScenarioConfig.model_validate(data)


def test_minimum_exact_clock_resolution_executes_without_quantization(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    data.pop("tick_duration_seconds")
    context = _load(
        tmp_path,
        data,
        EraConfig(tick_resolution_overrides={"tactical_s": 1e-6}),
    )
    engine = SimulationEngine(
        context,
        campaign_config=CampaignConfig(enable_strategic_movement=False),
    )

    assert engine.step() is False
    assert context.clock.elapsed.total_seconds() == 1e-6


def test_direct_loader_rejects_unreachable_calendar_horizon_before_rng(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _scenario_data()
    data.pop("tick_duration_seconds")
    data["tick_resolution"]["strategic_s"] = 260_000_000_000.0

    def unexpected_rng_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"RNG constructed before horizon rejection: {args!r} {kwargs!r}")

    monkeypatch.setattr(
        scenario_module,
        "RNGManager",
        unexpected_rng_construction,
    )

    with pytest.raises(ValueError, match="execution horizon"):
        _load(tmp_path, data, EraConfig())


def test_direct_loader_rejects_invalid_horizon_source_before_rng(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _scenario_data()
    data["date"] = " 2024-01-01 "

    def unexpected_rng_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"RNG constructed before source rejection: {args!r} {kwargs!r}")

    monkeypatch.setattr(
        scenario_module,
        "RNGManager",
        unexpected_rng_construction,
    )

    with pytest.raises(ValidationError, match="date"):
        _load(tmp_path, data, EraConfig())


def test_direct_loader_rejects_separately_overflowing_final_interval_before_rng(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _scenario_data()
    data["date"] = "2024-01-01T00:00:00.000030+00:00"
    data["duration_hours"] = 69_916_175.999_999_99
    data.pop("tick_duration_seconds")
    data["tick_resolution"] = {
        "strategic_s": 31e-6,
        "operational_s": 1e-6,
        "tactical_s": 1e-6,
    }

    def unexpected_rng_construction(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"RNG constructed before overflow rejection: {args!r} {kwargs!r}")

    monkeypatch.setattr(
        scenario_module,
        "RNGManager",
        unexpected_rng_construction,
    )

    with pytest.raises(ValueError, match="execution horizon"):
        _load(tmp_path, data, EraConfig())


def test_tactical_override_changes_production_logical_time(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    data.pop("tick_duration_seconds")
    data["tick_resolution"] = {
        "strategic_s": 31.0,
        "operational_s": 23.0,
        "tactical_s": 5.0,
    }
    context = _load(
        tmp_path,
        data,
        EraConfig(tick_resolution_overrides={"tactical_s": 17.0}),
    )
    engine = SimulationEngine(
        context,
        campaign_config=CampaignConfig(enable_strategic_movement=False),
    )

    engine.step()

    assert context.clock.elapsed.total_seconds() == 17.0


def test_minor_treatment_override_changes_production_completion_time(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    data["tick_duration_seconds"] = 3600.0
    declared = _load(
        tmp_path,
        data,
        EraConfig(physics_overrides={"treatment_hours_minor": 1.0}),
    )
    omitted = _load(tmp_path, data, EraConfig())

    def admit_minor(
        context: SimulationContext,
        suffix: str,
    ) -> CasualtyRecord:
        facility = MedicalFacility(
            facility_id=f"phase114-aid-{suffix}",
            facility_type=MedicalFacilityType.AID_STATION,
            position=Position(0.0, 0.0, 0.0),
            capacity=100,
        )
        context.medical_engine.register_facility(facility)
        return context.medical_engine.receive_casualty(
            unit_id=context.units_by_side["blue"][0].entity_id,
            member_id=f"phase114-casualty-{suffix}",
            severity=1,
            facility_id=facility.facility_id,
        )

    declared_casualty = admit_minor(declared, "declared")
    omitted_casualty = admit_minor(omitted, "omitted")
    declared_engine = SimulationEngine(
        declared,
        campaign_config=CampaignConfig(
            enable_maintenance=False,
            enable_strategic_movement=False,
        ),
    )
    omitted_engine = SimulationEngine(
        omitted,
        campaign_config=CampaignConfig(
            enable_maintenance=False,
            enable_strategic_movement=False,
        ),
    )

    for _ in range(2):
        declared_engine.step()
        omitted_engine.step()

    assert declared_casualty.outcome == "RTD"
    assert omitted_casualty.outcome is None


def test_checkpoint_exposes_effective_format_116_contract(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    context = _load(
        tmp_path,
        data,
        EraConfig(physics_overrides={"repair_time_hours": 6.0}),
    )
    state = SimulationEngine(context).get_state()

    assert state["checkpoint_version"] == 118
    assert set(state["context"]["era_runtime_contract"]) == {
        "selected_registry_id",
        "era",
        "strategic_s",
        "operational_s",
        "tactical_s",
        "treatment_hours_minor",
        "treatment_hours_serious",
        "treatment_hours_critical",
        "repair_time_hours",
    }
    assert state["context"]["era_runtime_contract"]["repair_time_hours"] == 6.0


def test_uniform_cadence_conflicts_with_era_tick_declaration(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    data["tick_duration_seconds"] = 5.0

    with pytest.raises(
        ValueError,
        match="tick_duration_seconds cannot be combined",
    ):
        _load(
            tmp_path,
            data,
            EraConfig(tick_resolution_overrides={"tactical_s": 7.0}),
        )


def test_sparse_contract_preserves_authored_and_destination_defaults(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    data.pop("tick_duration_seconds")
    data["tick_resolution"] = {
        "strategic_s": 31.0,
        "operational_s": 23.0,
        "tactical_s": 5.0,
    }
    context = _load(
        tmp_path,
        data,
        EraConfig(physics_overrides={"treatment_hours_minor": 1.5}),
    )
    contract = context.era_runtime_contract

    assert contract is not None
    assert (
        contract.strategic_s,
        contract.operational_s,
        contract.tactical_s,
    ) == (31.0, 23.0, 5.0)
    assert contract.treatment_hours_minor == 1.5
    assert contract.treatment_hours_serious == MedicalConfig().treatment_hours_serious
    assert contract.treatment_hours_critical == MedicalConfig().treatment_hours_critical


def test_prepared_inputs_must_be_paired_and_match_scenario_identity(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    register_era_config(_CUSTOM_ERA, EraConfig())
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    config = EraConfig()

    with pytest.raises(ValueError, match="must be supplied together"):
        ScenarioLoader(_DATA_DIR).load(
            scenario_path,
            scenario_config=None,
            era_config=config,
        )

    mismatched = EraRuntimeContract.resolve(
        selected_registry_id="different-era-id",
        era_config=config,
        strategic_s=3600.0,
        operational_s=300.0,
        tactical_s=5.0,
        tick_duration_seconds=data.get("tick_duration_seconds"),
    )
    with pytest.raises(ValueError, match="registry identity"):
        ScenarioLoader(_DATA_DIR).load(
            scenario_path,
            era_config=config,
            era_runtime_contract=mismatched,
        )


def test_runtime_rejects_clock_consumer_and_nested_era_drift(
    tmp_path: Path,
) -> None:
    data = _scenario_data()
    context = _load(
        tmp_path,
        data,
        EraConfig(physics_overrides={"repair_time_hours": 6.0}),
    )
    engine = SimulationEngine(context)

    with pytest.raises(ValidationError, match="frozen"):
        context.medical_engine.config.treatment_hours_minor = 99.0
    with pytest.raises(ValidationError, match="frozen"):
        context.maintenance_engine.config.repair_time_hours = 99.0
    with pytest.raises(AttributeError, match="stable EraRuntimeContract"):
        context.era_runtime_contract = context.era_runtime_contract

    original_elapsed = context.clock.elapsed
    context.clock.set_tick_duration(timedelta(seconds=99.0))
    with pytest.raises(RuntimeError, match="clock duration diverges"):
        engine.step()
    assert context.clock.elapsed == original_elapsed

    isolated = _load(
        tmp_path,
        data,
        EraConfig(physics_overrides={"repair_time_hours": 6.0}),
    )
    isolated.era_config.disabled_modules.add("ew")
    with pytest.raises(RuntimeError, match="changed after runtime"):
        SimulationEngine(isolated).step()


def test_loadout_builder_era_snapshot_is_isolated_and_checked(
    tmp_path: Path,
) -> None:
    context = _load(tmp_path, _scenario_data(), EraConfig())
    builder = context.loadout_builder
    assert builder is not None
    returned = builder.era_config
    returned.disabled_modules.add("ew")
    assert "ew" not in builder.era_config.disabled_modules

    builder._era_config.disabled_modules.add("ew")
    with pytest.raises(RuntimeError, match="LoadoutBuilder era gates"):
        SimulationEngine(context).step()
