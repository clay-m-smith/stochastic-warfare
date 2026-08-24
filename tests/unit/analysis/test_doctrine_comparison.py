"""Behavioral proofs for the typed Phase 112 doctrine-analysis policy."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest
from pydantic import ValidationError
import yaml

from stochastic_warfare.c2.ai.schools import (
    SchoolAssignmentPlan,
    SchoolRegistry,
)
from stochastic_warfare.c2.events import DecisionMadeEvent
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    DoctrineAnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    DoctrineSideAssignment,
)
from stochastic_warfare.tools.doctrine_compare import (
    DoctrineCompareConfig,
    run_doctrine_comparison,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO_PATH = DATA_DIR / "scenarios" / "test_campaign" / "scenario.yaml"


def _variant(
    variant_id: str,
    assignments: list[tuple[str, str]],
    *,
    calibration_patch: dict[str, Any] | None = None,
) -> AnalysisVariant:
    return AnalysisVariant(
        variant_id=variant_id,
        calibration_patch=calibration_patch or {},
        doctrine_variant=DoctrineAnalysisVariant(
            assignments=[DoctrineSideAssignment(side=side, school_id=school_id) for side, school_id in assignments],
        ),
    )


def _doctrine_source() -> CampaignScenarioConfig:
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO_PATH,
        DATA_DIR,
        (AnalysisVariant(variant_id="source"),),
    )
    payload = prepared.source_config.model_dump(mode="python")
    payload["reinforcements"][0]["arrival_time_s"] = 5.0
    payload["school_config"] = {
        "unit_assignments": {
            "blue_m1a2_0000": "attrition",
            "red_m1a2_0000": "clausewitzian",
        },
    }
    return CampaignScenarioConfig.model_validate(payload)


def _write_doctrine_source(tmp_path: Path) -> Path:
    scenario_path = tmp_path / "doctrine_source.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            _doctrine_source().model_dump(mode="json"),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return scenario_path


def _decision_effect_source() -> CampaignScenarioConfig:
    payload = _doctrine_source().model_dump(mode="python")
    payload["duration_hours"] = 100.0
    payload["victory_conditions"] = [{"type": "time_expired"}]
    payload["commander_config"] = {
        "ooda_speed_base_mult": 0.4,
        "noise_sigma": 0.1,
        "risk_threshold_base": 0.3,
    }
    payload["deployment"] = {"mode": "manual"}
    payload["sides"][0]["units"][0]["position"] = [
        4_000.0,
        5_000.0,
        0.0,
    ]
    payload["sides"][1]["units"][0]["position"] = [
        6_000.0,
        5_000.0,
        0.0,
    ]
    return CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("variants", "match"),
    (
        (
            [_variant("only", [("blue", "maneuverist")])],
            "at least 2",
        ),
        (
            [
                _variant("a", [("blue", "maneuverist")]),
                _variant("b", [("red", "attrition")]),
            ],
            "same exact side set",
        ),
        (
            [
                _variant("a", [("blue", "maneuverist")]),
                _variant("b", [("blue", "maneuverist")]),
            ],
            "distinct assignment policies",
        ),
        (
            [
                _variant(
                    "a",
                    [
                        ("blue", "maneuverist"),
                        ("red", "attrition"),
                    ],
                ),
                _variant(
                    "b",
                    [
                        ("red", "attrition"),
                        ("blue", "maneuverist"),
                    ],
                ),
            ],
            "distinct assignment policies",
        ),
    ),
)
def test_doctrine_compare_rejects_non_comparable_variants(
    variants: list[AnalysisVariant],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        DoctrineCompareConfig(
            scenario_path=str(SCENARIO_PATH),
            variants=variants,
            num_iterations=2,
        )


def test_doctrine_compare_accepts_equivalent_calibration_aliases() -> None:
    config = DoctrineCompareConfig(
        scenario_path=str(SCENARIO_PATH),
        variants=[
            _variant(
                "maneuverist",
                [("blue", "maneuverist")],
                calibration_patch={
                    "morale_degrade_rate_modifier": 0.4,
                },
            ),
            _variant(
                "attrition",
                [("blue", "attrition")],
                calibration_patch={
                    "morale": {
                        "degrade_rate_modifier": 0.4,
                    },
                },
            ),
        ],
        num_iterations=2,
    )

    assert (
        config.variants[0].calibration_patch.to_sparse_patch(mode="json")
        == config.variants[1].calibration_patch.to_sparse_patch(
            mode="json",
        )
    )


def test_doctrine_variant_rejects_duplicate_assignment_sides() -> None:
    with pytest.raises(ValidationError, match="sides must be unique"):
        DoctrineAnalysisVariant(
            assignments=[
                DoctrineSideAssignment(
                    side="blue",
                    school_id="maneuverist",
                ),
                DoctrineSideAssignment(
                    side="blue",
                    school_id="attrition",
                ),
            ]
        )


def test_policy_precedence_arrival_ooda_provenance_and_checkpoint() -> None:
    source = _doctrine_source()
    maneuverist = _variant("maneuverist", [("blue", "maneuverist")])
    attrition = _variant("attrition", [("blue", "attrition")])
    prepared = SimulationRuntimeFactory().prepare_config(
        source,
        DATA_DIR,
        (maneuverist, attrition),
        source_label="<doctrine-proof>",
    )

    maneuver_session = prepared.build(
        "maneuverist",
        seed=112,
        max_ticks=3,
    )
    attrition_session = prepared.build(
        "attrition",
        seed=112,
        max_ticks=3,
    )
    assert maneuver_session.config_fingerprint != attrition_session.config_fingerprint

    maneuver_assignments = {
        assignment.unit_id: assignment.doctrine_school_id for assignment in maneuver_session.initial_unit_assignments
    }
    attrition_assignments = {
        assignment.unit_id: assignment.doctrine_school_id for assignment in attrition_session.initial_unit_assignments
    }
    assert {school_id for unit_id, school_id in maneuver_assignments.items() if unit_id.startswith("blue_")} == {
        "maneuverist"
    }
    assert {school_id for unit_id, school_id in attrition_assignments.items() if unit_id.startswith("blue_")} == {
        "attrition"
    }
    # Red is intentionally unmapped by the runtime policy and therefore
    # retains its lower-precedence exact source assignment.
    assert maneuver_assignments["red_m1a2_0000"] == "clausewitzian"
    assert all(
        school_id is None
        for unit_id, school_id in maneuver_assignments.items()
        if unit_id.startswith("red_") and unit_id != "red_m1a2_0000"
    )

    maneuver_ooda = maneuver_session.context.ooda_engine.get_state()["commanders"]
    attrition_ooda = attrition_session.context.ooda_engine.get_state()["commanders"]
    assert maneuver_ooda["blue_m1a2_0000"]["phase_duration"] < attrition_ooda["blue_m1a2_0000"]["phase_duration"]

    assert maneuver_session.step() is False
    assert attrition_session.step() is False
    checkpoint = maneuver_session.engine.checkpoint()
    maneuver_provenance = maneuver_session.provenance()
    attrition_provenance = attrition_session.provenance()
    for provenance, expected_school in (
        (maneuver_provenance, "maneuverist"),
        (attrition_provenance, "attrition"),
    ):
        assert {
            (
                assignment.side,
                assignment.doctrine_school_id,
            )
            for assignment in provenance.arriving_unit_assignments
        } == {("blue", expected_school)}
        assert len(provenance.arriving_unit_assignments) == 2
        assert len(provenance.doctrine_assignment_fingerprint) == 64

    restored = prepared.build("maneuverist", seed=999, max_ticks=3)
    restored.engine.restore(checkpoint)
    assert restored.context.doctrine_side_assignments == (
        DoctrineSideAssignment(
            side="blue",
            school_id="maneuverist",
        ),
    )
    while not maneuver_session.step():
        pass
    while not restored.step():
        pass
    assert restored.finalize() == maneuver_session.finalize()
    assert restored.context.ooda_engine.get_state() == maneuver_session.context.ooda_engine.get_state()
    assert restored.provenance() == maneuver_session.provenance()


@pytest.mark.test_evidence("behavioral_oracle")
def test_no_analysis_doctrine_retains_commander_derived_schools(
    tmp_path: Path,
) -> None:
    copied_data = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied_data)
    profile_schools = {
        "aggressive_armor": "clausewitzian",
        "cautious_infantry": "attrition",
    }
    for profile_id, school_id in profile_schools.items():
        profile_path = copied_data / "commander_profiles" / f"{profile_id}.yaml"
        payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        payload["school_id"] = school_id
        profile_path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
    scenario_path = copied_data / "scenarios" / "test_campaign" / "scenario.yaml"
    scenario_payload = yaml.safe_load(
        scenario_path.read_text(encoding="utf-8"),
    )
    scenario_payload["school_config"] = {"unit_assignments": {}}
    scenario_payload["reinforcements"][0]["arrival_time_s"] = 5.0
    scenario_path.write_text(
        yaml.safe_dump(scenario_payload, sort_keys=False),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init", "--quiet", str(copied_data)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(copied_data), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(copied_data),
            "-c",
            "user.name=Phase 112 Test",
            "-c",
            "user.email=phase112@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )

    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        copied_data,
        (AnalysisVariant(variant_id="commander-derived"),),
    )
    session = prepared.build(
        "commander-derived",
        seed=112,
        max_ticks=3,
    )

    assert session.context.doctrine_side_assignments == ()
    assert session.loaded_roster == (("blue", 4), ("red", 6))
    assert len(session.initial_unit_assignments) == 10
    assert {(assignment.side, assignment.doctrine_school_id) for assignment in session.initial_unit_assignments} == {
        ("blue", "clausewitzian"),
        ("red", "attrition"),
    }
    assert session.step() is False
    assert session.step() is False
    arrivals = session.provenance().arriving_unit_assignments
    assert len(arrivals) == 2
    assert {
        (
            assignment.side,
            assignment.doctrine_school_id,
        )
        for assignment in arrivals
    } == {("blue", "clausewitzian")}


def test_same_seed_doctrine_variants_change_exercised_decisions() -> None:
    calibration_patch = {"hit_probability_modifier": 0.0}
    maneuverist = _variant(
        "maneuverist",
        [("blue", "maneuverist")],
        calibration_patch=calibration_patch,
    )
    attrition = _variant(
        "attrition",
        [("blue", "attrition")],
        calibration_patch=calibration_patch,
    )
    assert maneuverist.calibration_patch.model_dump(
        mode="json",
        exclude_unset=True,
    ) == attrition.calibration_patch.model_dump(
        mode="json",
        exclude_unset=True,
    )
    prepared = SimulationRuntimeFactory().prepare_config(
        _decision_effect_source(),
        DATA_DIR,
        (maneuverist, attrition),
        source_label="<doctrine-decision-effect>",
    )

    decision_sequences: dict[
        str,
        tuple[tuple[str, str], ...],
    ] = {}
    for variant_id in ("maneuverist", "attrition"):
        session = prepared.build(
            variant_id,
            seed=112,
            max_ticks=80,
        )
        assert session.seed == 112
        assert session.context.calibration.hit_probability_modifier == 0.0
        events: list[DecisionMadeEvent] = []
        session.context.event_bus.subscribe(
            DecisionMadeEvent,
            events.append,
        )
        result = session.run_to_completion()
        assert result.ticks_executed == 80
        blue_decisions = tuple(
            (event.unit_id, event.decision_type) for event in events if event.unit_id.startswith("blue_")
        )
        assert blue_decisions
        decision_sequences[variant_id] = blue_decisions

    assert len(decision_sequences["maneuverist"]) > len(
        decision_sequences["attrition"],
    )


def test_doctrine_comparison_rejects_wrong_arriving_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = _write_doctrine_source(tmp_path)
    original_commit = SchoolRegistry.commit_assignments

    def corrupt_arriving_assignment(
        registry: SchoolRegistry,
        plan: SchoolAssignmentPlan,
        *,
        replace: bool = False,
    ) -> None:
        corrupted = SchoolAssignmentPlan(
            tuple(
                (
                    unit_id,
                    ("attrition" if unit_id == "reinforce_blue_0000_m1a2_0000" else school_id),
                )
                for unit_id, school_id in plan.assignments
            ),
        )
        original_commit(
            registry,
            corrupted,
            replace=replace,
        )

    monkeypatch.setattr(
        SchoolRegistry,
        "commit_assignments",
        corrupt_arriving_assignment,
    )
    config = DoctrineCompareConfig(
        scenario_path=str(scenario_path),
        variants=[
            _variant("maneuverist", [("blue", "maneuverist")]),
            _variant("attrition", [("blue", "attrition")]),
        ],
        metric_names=["ticks_executed"],
        num_iterations=2,
        base_seed=112,
        max_ticks=3,
        data_dir=str(DATA_DIR),
    )

    with pytest.raises(
        RuntimeError,
        match=("arriving unit 'reinforce_blue_0000_m1a2_0000'.*expected 'maneuverist'.*observed 'attrition'"),
    ):
        run_doctrine_comparison(config)


def test_doctrine_comparison_accepts_runs_that_end_before_wave() -> None:
    config = DoctrineCompareConfig(
        scenario_path=str(SCENARIO_PATH),
        variants=[
            _variant("maneuverist", [("blue", "maneuverist")]),
            _variant("attrition", [("blue", "attrition")]),
        ],
        metric_names=["ticks_executed"],
        num_iterations=2,
        base_seed=112,
        max_ticks=1,
        data_dir=str(DATA_DIR),
    )

    result = run_doctrine_comparison(config)

    assert result.seeds == (112, 113)
    assert {run.ticks_executed for item in result.results for run in item.batch.runs} == {1}
    assert all(
        not run.runtime_provenance.arriving_unit_assignments for item in result.results for run in item.batch.runs
    )


def test_doctrine_compare_returns_exact_common_seed_batches(
    tmp_path: Path,
) -> None:
    scenario_path = _write_doctrine_source(tmp_path)
    config = DoctrineCompareConfig(
        scenario_path=str(scenario_path),
        variants=[
            _variant("maneuverist", [("blue", "maneuverist")]),
            _variant("attrition", [("blue", "attrition")]),
        ],
        metric_names=[
            "win_blue",
            "blue_destroyed",
            "red_destroyed",
            "ticks_executed",
        ],
        num_iterations=2,
        base_seed=112,
        max_ticks=3,
        data_dir=str(DATA_DIR),
    )

    result = run_doctrine_comparison(config)

    assert result.seeds == (112, 113)
    assert result.ordered_metrics == tuple(config.metric_names)
    assert [item.variant_id for item in result.results] == [
        "maneuverist",
        "attrition",
    ]
    for item in result.results:
        assert item.batch.seeds == result.seeds
        assert item.batch.ordered_metrics == result.ordered_metrics
        assert len(item.metrics) == 4
        assert all(len(metric.values) == 2 for metric in item.metrics)
        assert all(
            assignment.doctrine_school_id == item.variant_id
            for assignment in item.batch.initial_unit_assignments
            if assignment.side == "blue"
        )
        for run in item.batch.runs:
            assert (
                len(
                    run.runtime_provenance.arriving_unit_assignments,
                )
                == 2
            )
            assert {
                (
                    assignment.side,
                    assignment.doctrine_school_id,
                )
                for assignment in (run.runtime_provenance.arriving_unit_assignments)
            } == {("blue", item.variant_id)}
            assert (
                len(
                    run.runtime_provenance.doctrine_assignment_fingerprint,
                )
                == 64
            )


def test_public_doctrine_comparison_exposes_calibration_outcome_effect() -> None:
    results = [
        run_doctrine_comparison(
            DoctrineCompareConfig(
                scenario_path=str(SCENARIO_PATH),
                variants=[
                    _variant(
                        "maneuverist",
                        [("blue", "maneuverist")],
                        calibration_patch={
                            "hit_probability_modifier": modifier,
                        },
                    ),
                    _variant(
                        "attrition",
                        [("blue", "attrition")],
                        calibration_patch={
                            "hit_probability_modifier": modifier,
                        },
                    ),
                ],
                metric_names=[
                    "blue_destroyed",
                    "red_destroyed",
                ],
                num_iterations=3,
                base_seed=42,
                max_ticks=50,
                data_dir=str(DATA_DIR),
            ),
        )
        for modifier in (0.0, 10.0)
    ]

    for result in results:
        assert result.seeds == (42, 43, 44)
        assert result.base_seed == 42
        assert result.max_ticks == 50
        assert result.ordered_metrics == (
            "blue_destroyed",
            "red_destroyed",
        )
        assert [item.variant_id for item in result.results] == [
            "maneuverist",
            "attrition",
        ]
        for item in result.results:
            batch = item.batch
            assert batch.seeds == (42, 43, 44)
            assert batch.base_seed == 42
            assert batch.max_ticks == 50
            assert batch.authored_roster == batch.loaded_roster
            assert len(batch.source_fingerprint) == 64
            assert len(batch.config_fingerprint) == 64
            assert len(batch.data_revision) == 64
            assert batch.data_file_count > 0
            assert len(batch.catalog_revision) == 64
            assert len(batch.doctrine_catalog_fingerprint) == 64
            assert len(batch.loaded_roster_loadout_fingerprint) == 64
            assert [run.seed for run in batch.runs] == [
                42,
                43,
                44,
            ]
            assert all(run.game_over for run in batch.runs)
            assert {
                assignment.doctrine_school_id
                for assignment in batch.initial_unit_assignments
                if assignment.side == "blue"
            } == {item.variant_id}
            for metric in item.metrics:
                assert len(metric.values) == 3
                assert metric.values == batch.metric_values(metric.metric)
            for run in batch.runs:
                assert run.source_fingerprint == (
                    batch.source_fingerprint
                )
                assert run.config_fingerprint == (
                    batch.config_fingerprint
                )
                assert run.authored_roster == batch.authored_roster
                assert run.loaded_roster == batch.loaded_roster
                provenance = run.runtime_provenance
                assert provenance.code_revision == batch.code_revision
                assert provenance.data_revision == batch.data_revision
                assert provenance.data_file_count == (
                    batch.data_file_count
                )
                assert provenance.catalog_revision == (
                    batch.catalog_revision
                )
                assert (
                    provenance.doctrine_catalog_fingerprint
                    == batch.doctrine_catalog_fingerprint
                )
                assert (
                    provenance.loaded_roster_loadout_fingerprint
                    == batch.loaded_roster_loadout_fingerprint
                )
                assert (
                    provenance.initial_unit_assignments
                    == batch.initial_unit_assignments
                )
                assert (
                    len(
                        provenance.doctrine_assignment_fingerprint,
                    )
                    == 64
                )
                assert (
                    len(
                        provenance.final_roster_loadout_fingerprint,
                    )
                    == 64
                )

    by_modifier = [
        {item.variant_id: item for item in result.results}
        for result in results
    ]
    for variant_id in by_modifier[0]:
        assert (
            by_modifier[0][variant_id].batch.config_fingerprint
            != by_modifier[1][variant_id].batch.config_fingerprint
        )
    assert any(
        by_modifier[0][variant_id].batch.metrics_dict()
        != by_modifier[1][variant_id].batch.metrics_dict()
        for variant_id in by_modifier[0]
    )
