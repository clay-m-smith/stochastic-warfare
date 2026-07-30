"""Phase 112 production proofs for commander and unit-data integrity."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from stochastic_warfare.c2.ai.commander import (
    CommanderEngine,
    CommanderProfileLoader,
    CommanderScenarioConfig,
)
from stochastic_warfare.c2.events import DecisionMadeEvent
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.loader import (
    MissingUnitDefinitionError,
    UnitLoader,
)
from stochastic_warfare.entities.personnel import SkillLevel
from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
from stochastic_warfare.entities.unit_classes.naval import NavalUnit
from stochastic_warfare.entities.unit_classes.support import SupportUnit
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.force_builder import (
    InitialUnitConfig,
    RuntimeForceBuilder,
    RuntimeForceBuildError,
    RuntimeUnitSpec,
    UnitInstanceOverrides,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    ScenarioLoader,
    load_campaign_scenario_config,
)
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeSession,
    SimulationRuntimeFactory,
)


DATA_DIR = Path("data")
REINFORCEMENT_SCENARIO = DATA_DIR / "scenarios" / "test_campaign_reinforce" / "scenario.yaml"
RUNTIME_MAX_TICKS = 1_000_000


def _scenario_paths() -> list[Path]:
    return sorted(DATA_DIR.rglob("scenario.yaml"))


def _commander_catalog(era: str) -> CommanderProfileLoader:
    loader = CommanderProfileLoader(DATA_DIR / "commander_profiles")
    directories = [DATA_DIR / "commander_profiles"]
    if era != "modern":
        directories.append(DATA_DIR / "eras" / era / "commanders")
    loader.load_directories(directories)
    return loader


def _reinforcement_config() -> CampaignScenarioConfig:
    source = load_campaign_scenario_config(REINFORCEMENT_SCENARIO)
    return load_campaign_scenario_config(
        None,
        source_config=source,
        calibration_overrides={},
    )


def _build_commander_runtime(
    config: CampaignScenarioConfig,
    *,
    scenario_path: Path,
    variant_id: str,
    engagement_detection_range_m: float,
) -> RuntimeSession:
    prepared = SimulationRuntimeFactory().prepare_config(
        config,
        DATA_DIR,
        (AnalysisVariant(variant_id=variant_id),),
        source_label=str(scenario_path.resolve()),
    )
    return prepared.build(
        variant_id,
        seed=112,
        max_ticks=RUNTIME_MAX_TICKS,
        engine_config=EngineConfig(
            max_ticks=RUNTIME_MAX_TICKS,
            resolution_closing_range_mult=0.0,
        ),
        campaign_config=CampaignConfig(
            engagement_detection_range_m=engagement_detection_range_m,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
    )


def _reinforcement_runtime(
    *,
    future_override: bool = True,
) -> tuple[CampaignScenarioConfig, Any, SimulationEngine]:
    raw = _reinforcement_config().model_dump(mode="python")
    if future_override:
        raw["commander_config"] = {
            "assignments": {
                "reinforce_blue_0000_m1a2_0000": "balanced_default",
            },
        }
    config = CampaignScenarioConfig.model_validate(raw)
    session = _build_commander_runtime(
        config,
        scenario_path=REINFORCEMENT_SCENARIO,
        variant_id="phase112-commander-reinforcement",
        engagement_detection_range_m=1_000.0,
    )
    return config, session.context, session.engine


def _unit_ids(context: Any) -> dict[str, list[str]]:
    return {side: [unit.entity_id for unit in units] for side, units in context.units_by_side.items()}


def _decoded_checkpoint(engine: SimulationEngine) -> dict[str, Any]:
    return json.loads(engine.checkpoint().decode("utf-8"))


def test_all_74_shipped_commander_references_resolve_and_corrections_are_exact() -> None:
    references: list[tuple[Path, str, str]] = []
    catalogs: dict[str, CommanderProfileLoader] = {}
    configs: dict[Path, CampaignScenarioConfig] = {}
    for scenario_path in _scenario_paths():
        config = load_campaign_scenario_config(scenario_path)
        configs[scenario_path] = config
        catalog = catalogs.setdefault(
            config.era,
            _commander_catalog(config.era),
        )
        for side in config.sides:
            if side.commander_profile:
                catalog.get_definition(side.commander_profile)
                references.append(
                    (scenario_path, side.side, side.commander_profile),
                )

    assert len(references) == 74
    expected = {
        ("khafji", "red"): "aggressive_armor",
        ("debecka_pass", "red"): "aggressive_armor",
        ("fallujah_phase_line_fran", "red"): "insurgent_leader",
        ("bint_jbeil_2006", "red"): "insurgent_leader",
        ("ins_hanit_2006", "blue"): "naval_surface",
        ("ins_hanit_2006", "red"): "insurgent_leader",
    }
    actual = {
        (scenario_path.parent.name, side): profile
        for scenario_path, side, profile in references
        if (scenario_path.parent.name, side) in expected
    }
    assert actual == expected

    for scenario_name, profiles in {
        "suwalki_gap": {
            "blue": "joint_campaign",
            "red": "aggressive_armor",
        },
        "korean_peninsula": {
            "blue": "cautious_infantry",
            "red": "aggressive_armor",
        },
    }.items():
        path = DATA_DIR / "scenarios" / scenario_name / "scenario.yaml"
        config = configs[path]
        assert {side.side: side.commander_profile for side in config.sides} == profiles
        with open(path, encoding="utf-8") as scenario_file:
            raw = yaml.safe_load(scenario_file)
        assert "side_defaults" not in raw.get("commander_config", {})


def test_all_shipped_enabled_commander_rosters_assign_initial_and_arriving_units() -> None:
    loaded_scenarios = 0
    initial_unit_count = 0
    arriving_unit_count = 0

    for scenario_path in _scenario_paths():
        config = load_campaign_scenario_config(scenario_path)
        if not any(side.commander_profile for side in config.sides):
            continue
        assert all(side.commander_profile for side in config.sides)

        context = ScenarioLoader(DATA_DIR).load(scenario_path, seed=112)
        commander = context.commander_engine
        assert commander is not None
        side_profiles = {side.side: side.commander_profile for side in config.sides}
        overrides = config.commander_config.assignments if config.commander_config is not None else {}
        initial_units = context.all_units()
        initial_ids = [unit.entity_id for unit in initial_units]
        assert len(initial_ids) == len(set(initial_ids))
        assert set(commander.assignments()) == set(initial_ids)
        assert set(context.ooda_engine.get_state()["commanders"]) == set(
            initial_ids,
        )
        assert {unit.entity_id: commander.assignments()[unit.entity_id] for unit in initial_units} == {
            unit.entity_id: overrides.get(
                unit.entity_id,
                side_profiles[unit.side],
            )
            for unit in initial_units
        }

        engine = SimulationEngine(context)
        entries = engine.campaign_manager._reinforcements
        assert len(entries) == len(config.reinforcements)
        expected_arrivals = sum(unit.count for wave in config.reinforcements for unit in wave.units)
        if entries:
            arrivals = engine.campaign_manager.check_reinforcements(
                context,
                elapsed_s=max(entry.actual_arrival_time_s for entry in entries),
            )
        else:
            arrivals = []
        assert len(arrivals) == expected_arrivals
        assert all(entry.arrived for entry in entries)

        final_units = context.all_units()
        final_ids = [unit.entity_id for unit in final_units]
        assignments = commander.assignments()
        assert len(final_ids) == len(set(final_ids))
        assert len(assignments) == len(final_ids)
        assert set(assignments) == set(final_ids)
        assert set(context.ooda_engine.get_state()["commanders"]) == set(
            final_ids,
        )
        assert {unit.entity_id: assignments[unit.entity_id] for unit in final_units} == {
            unit.entity_id: overrides.get(
                unit.entity_id,
                side_profiles[unit.side],
            )
            for unit in final_units
        }

        loaded_scenarios += 1
        initial_unit_count += len(initial_units)
        arriving_unit_count += len(arrivals)

    assert (
        loaded_scenarios,
        initial_unit_count,
        arriving_unit_count,
        initial_unit_count + arriving_unit_count,
    ) == (37, 1_750, 89, 1_839)


def test_commander_activation_truth_table_and_strict_tuning() -> None:
    baseline = load_campaign_scenario_config(
        DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml",
    ).model_dump(mode="python")

    all_blank = copy.deepcopy(baseline)
    for side in all_blank["sides"]:
        side["commander_profile"] = ""
    all_blank["commander_config"] = None
    disabled_config = CampaignScenarioConfig.model_validate(all_blank)
    assert disabled_config.commander_config is None
    disabled_context = ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml",
        seed=112,
        scenario_config=disabled_config,
    )
    assert disabled_context.commander_engine is None
    assert disabled_context.ooda_engine.get_state()["commanders"] == {}
    assert "commander_engine" not in disabled_context.get_state()

    partial = copy.deepcopy(all_blank)
    partial["sides"][0]["commander_profile"] = "aggressive_armor"
    with pytest.raises(
        ValidationError,
        match="populated for every side",
    ):
        CampaignScenarioConfig.model_validate(partial)

    blank_with_config = copy.deepcopy(all_blank)
    blank_with_config["commander_config"] = {}
    with pytest.raises(
        ValidationError,
        match="requires canonical commander_profile",
    ):
        CampaignScenarioConfig.model_validate(blank_with_config)

    for payload in (
        {"side_defaults": {"blue": "balanced_default"}},
        {"noise_sigma": 1},
        {"noise_sigma": True},
        {"noise_sigma": float("nan")},
        {"ooda_speed_base_mult": 0.0},
        {"risk_threshold_base": float("inf")},
        {"unknown_tuning": 0.1},
    ):
        with pytest.raises(ValidationError):
            CommanderScenarioConfig.model_validate(payload)


def test_commander_catalog_duplicate_ids_reject_atomically(
    tmp_path: Path,
) -> None:
    initial_dir = tmp_path / "initial"
    conflicting_dir = tmp_path / "conflicting"
    initial_dir.mkdir()
    conflicting_dir.mkdir()

    def write_profile(path: Path, profile_id: str) -> None:
        path.write_text(
            yaml.safe_dump(
                {
                    "profile_id": profile_id,
                    "display_name": profile_id,
                    "description": "Phase 112 duplicate-ID probe",
                    "aggression": 0.5,
                    "caution": 0.5,
                    "flexibility": 0.5,
                    "initiative": 0.5,
                    "experience": 0.5,
                }
            ),
            encoding="utf-8",
        )

    write_profile(initial_dir / "baseline.yaml", "phase112_baseline")
    write_profile(conflicting_dir / "a_staged.yaml", "phase112_staged")
    write_profile(conflicting_dir / "z_duplicate.yaml", "phase112_baseline")

    loader = CommanderProfileLoader(initial_dir)
    loader.load_all()
    before = dict(loader.definitions())
    with pytest.raises(ValueError, match="Duplicate commander profile_id"):
        loader.load_directories((conflicting_dir,))

    assert dict(loader.definitions()) == before
    assert loader.available_profiles() == ["phase112_baseline"]


@pytest.mark.parametrize(
    ("assignments", "expected"),
    [
        (
            {"blue_m1a2_9999": "balanced_default"},
            "unknown initial or future unit IDs",
        ),
        (
            {
                "reinforce_blue_9999_m1a2_0000": ("balanced_default"),
            },
            "unknown initial or future unit IDs",
        ),
        (
            {
                "blue_m1a2_0000": ("phase112_unknown_commander_profile"),
            },
            "unknown profile",
        ),
    ],
)
def test_unknown_commander_assignments_reject_before_any_runtime_commit(
    monkeypatch: pytest.MonkeyPatch,
    assignments: dict[str, str],
    expected: str,
) -> None:
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    raw = load_campaign_scenario_config(scenario_path).model_dump(
        mode="python",
    )
    raw["commander_config"] = {"assignments": assignments}
    invalid_config = CampaignScenarioConfig.model_validate(raw)
    constructed_ids: list[str] = []
    committed_plans: list[Any] = []
    original_create = UnitLoader.create_unit
    original_commit = CommanderEngine.commit_assignments

    def record_create(
        self: UnitLoader,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        constructed_ids.append(str(kwargs["entity_id"]))
        return original_create(self, *args, **kwargs)

    def record_commit(
        self: CommanderEngine,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        committed_plans.append(args[0])
        original_commit(self, *args, **kwargs)

    monkeypatch.setattr(UnitLoader, "create_unit", record_create)
    monkeypatch.setattr(
        CommanderEngine,
        "commit_assignments",
        record_commit,
    )

    with pytest.raises(ValueError, match=expected):
        ScenarioLoader(DATA_DIR).load(
            scenario_path,
            seed=112,
            scenario_config=invalid_config,
        )

    assert constructed_ids == []
    assert committed_plans == []


@pytest.mark.parametrize(
    "assignments",
    [
        {"": "balanced_default"},
        {" blue_m1a2_0000": "balanced_default"},
        {"blue_m1a2_0000": ""},
        {"blue_m1a2_0000": " balanced_default"},
    ],
)
def test_empty_or_untrimmed_commander_assignment_ids_reject_preconstruction(
    monkeypatch: pytest.MonkeyPatch,
    assignments: dict[str, str],
) -> None:
    constructed_ids: list[str] = []
    committed_plans: list[Any] = []
    original_create = UnitLoader.create_unit
    original_commit = CommanderEngine.commit_assignments

    def record_create(
        self: UnitLoader,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        constructed_ids.append(str(kwargs["entity_id"]))
        return original_create(self, *args, **kwargs)

    def record_commit(
        self: CommanderEngine,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        committed_plans.append(args[0])
        original_commit(self, *args, **kwargs)

    monkeypatch.setattr(UnitLoader, "create_unit", record_create)
    monkeypatch.setattr(
        CommanderEngine,
        "commit_assignments",
        record_commit,
    )
    raw = load_campaign_scenario_config(
        DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml",
    ).model_dump(mode="python")
    raw["commander_config"] = {"assignments": assignments}

    with pytest.raises(ValidationError, match="non-empty trimmed strings"):
        CampaignScenarioConfig.model_validate(raw)

    assert constructed_ids == []
    assert committed_plans == []


def test_duplicate_commander_assignment_yaml_key_rejects_preconstruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    duplicate_path = tmp_path / "duplicate-commander-assignment.yaml"
    duplicate_path.write_text(
        source_path.read_text(encoding="utf-8")
        + """

commander_config:
  assignments:
    blue_m1a2_0000: aggressive_armor
    blue_m1a2_0000: balanced_default
""",
        encoding="utf-8",
    )
    constructed_ids: list[str] = []
    committed_plans: list[Any] = []
    original_create = UnitLoader.create_unit
    original_commit = CommanderEngine.commit_assignments

    def record_create(
        self: UnitLoader,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        constructed_ids.append(str(kwargs["entity_id"]))
        return original_create(self, *args, **kwargs)

    def record_commit(
        self: CommanderEngine,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        committed_plans.append(args[0])
        original_commit(self, *args, **kwargs)

    monkeypatch.setattr(UnitLoader, "create_unit", record_create)
    monkeypatch.setattr(
        CommanderEngine,
        "commit_assignments",
        record_commit,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate YAML mapping key 'blue_m1a2_0000'",
    ):
        ScenarioLoader(DATA_DIR).load(duplicate_path, seed=112)

    assert constructed_ids == []
    assert committed_plans == []


@pytest.mark.parametrize(
    ("mutation", "invalid_value", "expected"),
    [
        ("role", "TACTICAL_WIZARD", "crew role"),
        ("skill", "EXPERT", "crew skill"),
        ("category", "MAGIC_SENSOR", "equipment category"),
        ("ground_type", "HOVER_TANK", "ground_type"),
        ("ground_type", None, "requires ground_type"),
    ],
)
def test_unit_catalog_enums_reject_eagerly_without_partial_registration(
    tmp_path: Path,
    mutation: str,
    invalid_value: str | None,
    expected: str,
) -> None:
    payload: dict[str, Any] = {
        "unit_type": "phase112_invalid_enum",
        "domain": "ground",
        "display_name": "Phase 112 invalid enum probe",
        "ground_type": "LIGHT_INFANTRY",
        "max_speed": 1.0,
        "crew": [
            {
                "role": "COMMANDER",
                "count": 1,
                "skill": "TRAINED",
            }
        ],
        "equipment": [
            {
                "name": "Naked Eye Observation",
                "category": "SENSOR",
            }
        ],
    }
    if mutation in {"role", "skill"}:
        payload["crew"][0][mutation] = invalid_value
    elif mutation == "category":
        payload["equipment"][0]["category"] = invalid_value
    else:
        payload[mutation] = invalid_value
    path = tmp_path / f"{mutation}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    loader = UnitLoader(tmp_path)

    with pytest.raises(ValueError, match=expected):
        loader.load_definition(path)

    assert loader.available_types() == []


@pytest.mark.parametrize(
    ("domain", "subtype_field", "invalid_value", "expected"),
    [
        ("orbital", "ground_type", "LIGHT_INFANTRY", "Unknown domain"),
        ("aerial", "aerial_type", "SPACE_FIGHTER", "aerial_type"),
        ("naval", "naval_type", "SPACE_CRUISER", "naval_type"),
        ("ground", "ad_type", "MAGIC_SAM", "ad_type"),
        ("ground", "support_type", "MAGIC_SUPPORT", "support_type"),
    ],
)
def test_domain_and_specialized_subtype_enums_reject_eagerly(
    tmp_path: Path,
    domain: str,
    subtype_field: str,
    invalid_value: str,
    expected: str,
) -> None:
    payload: dict[str, Any] = {
        "unit_type": "phase112_invalid_subtype",
        "domain": domain,
        "display_name": "Phase 112 invalid subtype probe",
        subtype_field: invalid_value,
        "max_speed": 1.0,
        "crew": [
            {
                "role": "COMMANDER",
                "count": 1,
                "skill": "TRAINED",
            }
        ],
        "equipment": [
            {
                "name": "Naked Eye Observation",
                "category": "SENSOR",
            }
        ],
    }
    path = tmp_path / f"{subtype_field}.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    loader = UnitLoader(tmp_path)

    with pytest.raises(ValueError, match=expected):
        loader.load_definition(path)

    assert loader.available_types() == []


def test_runtime_force_builder_constructs_every_specialized_schema_branch() -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    builder = RuntimeForceBuilder(
        unit_loader=loader,
        rng=np.random.default_rng(112),
    )
    unit_types = ("f16c", "ddg51", "patriot", "hemtt")
    units = builder.build_units(
        tuple(
            RuntimeUnitSpec(
                entity_id=f"blue_{unit_type}_0000",
                unit_type=unit_type,
                side="blue",
                position=Position(float(index), 0.0, 0.0),
            )
            for index, unit_type in enumerate(unit_types)
        )
    )

    assert tuple(type(unit) for unit in units) == (
        AerialUnit,
        NavalUnit,
        AirDefenseUnit,
        SupportUnit,
    )
    assert tuple(unit.unit_type for unit in units) == unit_types


@pytest.mark.parametrize(
    "payload",
    [
        {"speed": 10.0},
        {"training_level": True},
        {"training_level": -0.1},
        {"armor_front": float("inf")},
        {"display_name": " untrimmed"},
    ],
)
def test_initial_unit_overrides_are_strict_and_typed(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        InitialUnitConfig.model_validate(
            {
                "unit_type": "m1a2",
                "overrides": payload,
            }
        )


@pytest.mark.parametrize("unit_type", ("f16c", "patriot", "hemtt"))
def test_armor_front_override_rejects_aerial_ad_and_support_before_rng_use(
    unit_type: str,
) -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    rng = np.random.default_rng(112)
    builder = RuntimeForceBuilder(unit_loader=loader, rng=rng)
    before_rng = copy.deepcopy(rng.bit_generator.state)

    with pytest.raises(
        RuntimeForceBuildError,
        match="incompatible with armor_front override",
    ):
        builder.build_units(
            (
                RuntimeUnitSpec(
                    entity_id=f"blue_{unit_type}_0000",
                    unit_type=unit_type,
                    side="blue",
                    position=Position(0.0, 0.0, 0.0),
                    overrides=UnitInstanceOverrides(armor_front=10.0),
                ),
            )
        )

    assert rng.bit_generator.state == before_rng


def test_initial_overrides_apply_through_runtime_force_boundary() -> None:
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    raw = load_campaign_scenario_config(scenario_path).model_dump(
        mode="python",
    )
    raw["sides"][0]["units"][0]["overrides"] = {
        "training_level": 0.91,
        "armor_front": 777.0,
        "heading": 123.0,
        "display_name": "Phase 112 Runtime Tank",
    }
    config = CampaignScenarioConfig.model_validate(raw)

    context = ScenarioLoader(DATA_DIR).load(
        scenario_path,
        seed=112,
        scenario_config=config,
    )

    assert len(context.units_by_side["blue"]) == 4
    for unit in context.units_by_side["blue"]:
        assert unit.training_level == 0.91
        assert unit.armor_front == 777.0
        assert unit.heading == 123.0
        assert unit.name == "Phase 112 Runtime Tank"


@pytest.mark.parametrize(
    (
        "scenario_name",
        "expected_counts",
        "old_guard_id",
        "expected_ticks",
        "expected_winner",
    ),
    [
        (
            "austerlitz",
            {"french": 10, "coalition": 9},
            "french_french_old_guard_0005",
            300,
            "french",
        ),
        (
            "waterloo",
            {"french": 11, "british": 9},
            "french_french_old_guard_0004",
            490,
            "british",
        ),
    ],
)
def test_napoleonic_rosters_and_old_guard_survive_completed_runtime(
    scenario_name: str,
    expected_counts: dict[str, int],
    old_guard_id: str,
    expected_ticks: int,
    expected_winner: str,
) -> None:
    scenario_path = DATA_DIR / "eras" / "napoleonic" / "scenarios" / scenario_name / "scenario.yaml"
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        DATA_DIR,
        (AnalysisVariant(variant_id="phase112-old-guard"),),
    )
    session = prepared.build(
        "phase112-old-guard",
        seed=112,
        max_ticks=10_000,
    )
    context = session.context

    assert {side: len(units) for side, units in context.units_by_side.items()} == expected_counts
    old_guard = next(unit for unit in context.units_by_side["french"] if unit.unit_type == "french_old_guard")
    assert old_guard.entity_id == old_guard_id
    assert old_guard.status is UnitStatus.ACTIVE
    assert old_guard.personnel[0].skill is SkillLevel.ELITE
    assert context.commander_engine is not None
    assert context.commander_engine.assignments()[old_guard_id] == "napoleon_grande_armee"
    assert len(session.initial_unit_assignments) == sum(
        expected_counts.values(),
    )

    result = session.run_to_completion()

    assert result.ticks_executed == expected_ticks
    assert result.victory_result.game_over is True
    assert result.victory_result.condition_type == "force_destroyed"
    assert result.victory_result.winning_side == expected_winner
    assert old_guard.status is UnitStatus.ACTIVE
    assert {side: len(units) for side, units in context.units_by_side.items()} == expected_counts
    assert len(session.provenance().initial_unit_assignments) == sum(
        expected_counts.values(),
    )
    assert session.provenance().arriving_unit_assignments == ()


def test_future_override_is_absent_until_arrival_then_assignment_is_exact() -> None:
    _, context, engine = _reinforcement_runtime()
    commander = context.commander_engine
    assert commander is not None
    future_id = "reinforce_blue_0000_m1a2_0000"
    initial_ids = {unit.entity_id for unit in context.all_units()}
    assert set(commander.assignments()) == initial_ids
    assert future_id not in commander.assignments()
    assert set(context.ooda_engine.get_state()["commanders"]) == initial_ids
    assert future_id not in context.ooda_engine.get_state()["commanders"]

    engine.step()

    arrived_ids = {unit.entity_id for unit in context.all_units() if unit.entity_id not in initial_ids}
    assert arrived_ids == {
        "reinforce_blue_0000_m1a2_0000",
        "reinforce_blue_0000_m1a2_0001",
    }
    assignments = commander.assignments()
    assert set(assignments) == {unit.entity_id for unit in context.all_units()}
    assert set(context.ooda_engine.get_state()["commanders"]) == {unit.entity_id for unit in context.all_units()}
    assert assignments[future_id] == "balanced_default"
    assert assignments["reinforce_blue_0000_m1a2_0001"] == "aggressive_armor"
    assert commander.get_ooda_speed_multiplier(future_id) != commander.get_ooda_speed_multiplier(
        "reinforce_blue_0000_m1a2_0001",
    )

    _, replay_context, replay = _reinforcement_runtime()
    replay.step()
    assert replay_context.commander_engine is not None
    assert replay.checkpoint() == engine.checkpoint()


def test_dynamic_commander_commit_failure_rolls_back_and_retries_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, context, engine = _reinforcement_runtime()
    commander = context.commander_engine
    assert commander is not None
    entry = engine.campaign_manager._reinforcements[0]
    before_units = _unit_ids(context)
    before_weapon_ids = set(context.unit_weapons)
    before_sensor_ids = set(context.unit_sensors)
    before_morale = dict(context.morale_states)
    before_morale_machine = copy.deepcopy(
        context.morale_machine.get_state(),
    )
    before_commander = copy.deepcopy(commander.get_state())
    before_ooda = copy.deepcopy(context.ooda_engine.get_state())
    entities_rng = context.rng_manager.get_stream(ModuleId.ENTITIES)
    c2_rng = context.rng_manager.get_stream(ModuleId.C2)
    before_entities_rng = copy.deepcopy(entities_rng.bit_generator.state)
    before_c2_rng = copy.deepcopy(c2_rng.bit_generator.state)
    original_commit = commander.commit_assignments
    calls = 0

    def fail_once(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("phase112 injected commander commit failure")
        original_commit(*args, **kwargs)

    monkeypatch.setattr(commander, "commit_assignments", fail_once)
    with pytest.raises(
        RuntimeError,
        match="phase112 injected commander commit failure",
    ):
        engine.campaign_manager.check_reinforcements(
            context,
            elapsed_s=3_600.0,
        )

    assert calls == 2
    assert entry.arrived is False
    assert _unit_ids(context) == before_units
    assert set(context.unit_weapons) == before_weapon_ids
    assert set(context.unit_sensors) == before_sensor_ids
    assert context.morale_states == before_morale
    assert context.morale_machine.get_state() == before_morale_machine
    assert commander.get_state() == before_commander
    assert context.ooda_engine.get_state() == before_ooda
    assert entities_rng.bit_generator.state == before_entities_rng
    assert c2_rng.bit_generator.state == before_c2_rng

    monkeypatch.setattr(commander, "commit_assignments", original_commit)
    arrived = engine.campaign_manager.check_reinforcements(
        context,
        elapsed_s=3_600.0,
    )
    assert entry.arrived is True
    assert len(arrived) == 2
    assert set(commander.assignments()) == {unit.entity_id for unit in context.all_units()}

    _, control_context, control = _reinforcement_runtime()
    control.campaign_manager.check_reinforcements(
        control_context,
        elapsed_s=3_600.0,
    )
    assert engine.checkpoint() == control.checkpoint()


def test_commander_checkpoint_restore_and_continuation_are_exact_and_atomic() -> None:
    _, source_context, source = _reinforcement_runtime()
    source.step()
    valid_checkpoint = source.checkpoint()
    valid_state = json.loads(valid_checkpoint.decode("utf-8"))
    assert valid_state["checkpoint_version"] == 112

    _, target_context, target = _reinforcement_runtime()
    before_rejection = target.checkpoint()
    invalid = copy.deepcopy(valid_state)
    missing_id = "reinforce_blue_0000_m1a2_0000"
    invalid["context"]["commander_engine"]["assignments"].pop(missing_id)
    with pytest.raises(
        ValueError,
        match="Commander assignment topology",
    ):
        target.set_state(invalid)
    assert target.checkpoint() == before_rejection

    invalid_ooda = copy.deepcopy(valid_state)
    invalid_ooda["context"]["ooda_engine"]["commanders"].pop(missing_id)
    with pytest.raises(
        ValueError,
        match="OODA commander topology",
    ):
        target.set_state(invalid_ooda)
    assert target.checkpoint() == before_rejection

    impossible_timer = copy.deepcopy(valid_state)
    timer_state = impossible_timer["context"]["ooda_engine"]["commanders"][missing_id]
    timer_state["phase_timer"] = timer_state["phase_duration"] + 1.0
    with pytest.raises(
        ValueError,
        match="phase_timer may not exceed phase_duration",
    ):
        target.set_state(impossible_timer)
    assert target.checkpoint() == before_rejection

    invalid_sentinel = copy.deepcopy(valid_state)
    sentinel_state = invalid_sentinel["context"]["ooda_engine"]["commanders"][missing_id]
    sentinel_state["phase_duration"] = 0.0
    sentinel_state["phase_timer"] = 0.0
    with pytest.raises(
        ValueError,
        match="zero-duration state requires phase_timer=-1",
    ):
        target.set_state(invalid_sentinel)
    assert target.checkpoint() == before_rejection

    target.restore(valid_checkpoint)
    assert _decoded_checkpoint(target) == valid_state
    assert target_context.commander_engine is not None
    assert source_context.commander_engine is not None
    assert target_context.commander_engine.assignments() == source_context.commander_engine.assignments()

    source.step()
    target.step()
    assert target.checkpoint() == source.checkpoint()


def test_profiles_change_production_ooda_and_decision_state() -> None:
    scenario_path = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"
    source = load_campaign_scenario_config(scenario_path)
    runtimes: dict[
        str,
        tuple[Any, SimulationEngine, list[DecisionMadeEvent]],
    ] = {}
    for profile_id in ("aggressive_armor", "balanced_default"):
        raw = source.model_dump(mode="python")
        raw["reinforcements"] = []
        raw["sides"][0]["units"] = [
            {
                "unit_type": "m1a2",
                "count": 1,
                "position": [1_000.0, 5_000.0],
            }
        ]
        raw["sides"][1]["units"] = [
            {
                "unit_type": "m1a2",
                "count": 1,
                "position": [9_000.0, 5_000.0],
            }
        ]
        raw["commander_config"] = {
            "assignments": {
                "blue_m1a2_0000": profile_id,
            },
        }
        raw["behavior_rules"] = {
            "blue": {"hold_position": True},
            "red": {"hold_position": True},
        }
        config = CampaignScenarioConfig.model_validate(raw)
        session = _build_commander_runtime(
            config,
            scenario_path=scenario_path,
            variant_id=f"phase112-personality-{profile_id}",
            engagement_detection_range_m=15_000.0,
        )
        decision_events: list[DecisionMadeEvent] = []
        session.context.event_bus.subscribe(
            DecisionMadeEvent,
            decision_events.append,
        )
        runtimes[profile_id] = (
            session.context,
            session.engine,
            decision_events,
        )

    aggressive_context, aggressive_engine, aggressive_events = runtimes["aggressive_armor"]
    balanced_context, balanced_engine, balanced_events = runtimes["balanced_default"]
    unit_id = "blue_m1a2_0000"
    aggressive_initial = aggressive_context.ooda_engine.get_state()["commanders"][unit_id]
    balanced_initial = balanced_context.ooda_engine.get_state()["commanders"][unit_id]
    multiplier_ratio = balanced_context.commander_engine.get_ooda_speed_multiplier(
        unit_id
    ) / aggressive_context.commander_engine.get_ooda_speed_multiplier(
        unit_id,
    )
    assert (balanced_initial["phase_duration"] / aggressive_initial["phase_duration"]) == pytest.approx(
        multiplier_ratio
    )

    for _ in range(100):
        aggressive_engine.step()
        balanced_engine.step()

    aggressive_after = aggressive_context.ooda_engine.get_state()["commanders"][unit_id]
    balanced_after = balanced_context.ooda_engine.get_state()["commanders"][unit_id]
    assert aggressive_after != balanced_after
    assert aggressive_context.decision_engine.get_state()["decision_count"] > 0
    assert balanced_context.decision_engine.get_state()["decision_count"] > 0
    assert len(aggressive_events) == 3
    assert len(balanced_events) == 3
    aggressive_sequence = [
        (
            event.timestamp,
            event.unit_id,
            event.decision_type,
            event.confidence,
        )
        for event in aggressive_events
    ]
    balanced_sequence = [
        (
            event.timestamp,
            event.unit_id,
            event.decision_type,
            event.confidence,
        )
        for event in balanced_events
    ]
    assert aggressive_sequence != balanced_sequence
    assert aggressive_events[0].unit_id == balanced_events[0].unit_id
    assert aggressive_events[0].decision_type == "COUNTERATTACK"
    assert balanced_events[0].decision_type == "RESERVE"
    assert aggressive_events[0].timestamp < balanced_events[0].timestamp


def test_enabled_aggregation_commander_restore_is_explicitly_unsupported() -> None:
    _, context, engine = _reinforcement_runtime()
    context.aggregation_engine._config.enable_aggregation = True
    before = engine.checkpoint()

    with pytest.raises(
        ValueError,
        match="aggregation is unsupported",
    ):
        engine.restore(before)

    assert engine.checkpoint() == before


def test_runtime_builder_does_not_reclassify_constructor_keyerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    rng = np.random.default_rng(112)
    builder = RuntimeForceBuilder(unit_loader=loader, rng=rng)
    before_rng = copy.deepcopy(rng.bit_generator.state)

    def fail_constructor(*args: Any, **kwargs: Any) -> Any:
        raise KeyError("phase112 constructor invariant")

    monkeypatch.setattr(loader, "create_unit", fail_constructor)
    with pytest.raises(KeyError, match="phase112 constructor invariant"):
        builder.build_units(
            (
                RuntimeUnitSpec(
                    entity_id="blue_m1a2_0000",
                    unit_type="m1a2",
                    side="blue",
                    position=Position(0.0, 0.0, 0.0),
                    overrides=UnitInstanceOverrides(),
                ),
            )
        )

    assert rng.bit_generator.state == before_rng
    with pytest.raises(
        MissingUnitDefinitionError,
        match="phase112_missing_unit",
    ):
        loader.get_definition("phase112_missing_unit")


@pytest.mark.parametrize(
    "mutation",
    (
        {"position": Position(float("nan"), 0.0, 0.0)},
        {"position": (0.0, 0.0, 0.0)},
        {"unit_type": " m1a2"},
        {"side": " blue"},
        {"overrides": {}},
        {"manually_positioned": 1},
    ),
)
def test_runtime_builder_rejects_malformed_specs_before_rng_use(
    mutation: dict[str, Any],
) -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    rng = np.random.default_rng(112)
    builder = RuntimeForceBuilder(unit_loader=loader, rng=rng)
    before_rng = copy.deepcopy(rng.bit_generator.state)
    values: dict[str, Any] = {
        "entity_id": "phase112_preflight",
        "unit_type": "m1a2",
        "side": "blue",
        "position": Position(0.0, 0.0, 0.0),
        "overrides": UnitInstanceOverrides(),
        "manually_positioned": False,
    }
    values.update(mutation)

    with pytest.raises(RuntimeForceBuildError):
        builder.build_units((RuntimeUnitSpec(**values),))

    assert rng.bit_generator.state == before_rng


def test_runtime_builder_revalidates_mutated_typed_overrides_before_rng_use() -> None:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    rng = np.random.default_rng(112)
    builder = RuntimeForceBuilder(unit_loader=loader, rng=rng)
    before_rng = copy.deepcopy(rng.bit_generator.state)
    overrides = UnitInstanceOverrides(training_level=0.8)
    overrides.training_level = float("nan")

    with pytest.raises(RuntimeForceBuildError, match="mutated invalid"):
        builder.build_units(
            (
                RuntimeUnitSpec(
                    entity_id="phase112_mutated_override",
                    unit_type="m1a2",
                    side="blue",
                    position=Position(0.0, 0.0, 0.0),
                    overrides=overrides,
                ),
            )
        )

    assert rng.bit_generator.state == before_rng
