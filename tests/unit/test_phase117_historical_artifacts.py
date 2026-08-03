"""Focused fail-closed controls for Phase 117 plans and artifacts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import math
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from stochastic_warfare.simulation.scenario import load_campaign_scenario_config
from stochastic_warfare.validation.historical_backtest import artifacts as artifact_module
from stochastic_warfare.validation.historical_backtest.artifacts import (
    ClaimBinding,
    CompletedHistoricalArtifact,
    create_completed_artifact,
    create_error_artifact,
    load_historical_artifact,
    write_historical_artifact,
)
from stochastic_warfare.validation.historical_backtest.common import (
    canonical_sha256,
    require_relative_posix_path,
)
from stochastic_warfare.validation.historical_backtest.evaluator import (
    evaluate_joint_coverage,
)
from stochastic_warfare.validation.historical_backtest.claims import (
    ClaimSourceKind,
    HistoricalClaimLedgerLoader,
    scan_historical_claim_sources,
)
from stochastic_warfare.validation.historical_backtest.runner import (
    CodeRevisionEvidence,
    HistoricalBacktestResult,
    HistoricalEligibility,
    HistoricalExecutionEvidence,
    HistoricalPreparationEvidence,
    HistoricalRunEvidence,
    MetricObservationReceipt,
    MetricStatistics,
    RuntimeProvenanceEvidence,
    TerminalOutcomeEvidence,
    UnitAssignmentEvidence,
    UnitIdentityEvidence,
    UnitStatusObservation,
)
from stochastic_warfare.validation.historical_backtest.studies import (
    HistoricalStudyLoader,
    HistoricalStudyPlan,
    validate_historical_runtime_scope,
)


ROOT = Path(__file__).resolve().parents[2]
STUDY_PATH = ROOT / "data/validation/historical_studies/73_easting_phase117.yaml"
SCENARIO_PATH = ROOT / "data/scenarios/73_easting/scenario.yaml"
FIXED_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

PlanPayload = dict[str, Any]
ArtifactPayload = dict[str, Any]


@pytest.fixture
def isolated_study_repository(tmp_path: Path) -> Path:
    """Create the minimum real-file boundary needed by the strict plan loader."""
    repository = tmp_path / "repository"
    scenario = repository / "data/scenarios/73_easting/scenario.yaml"
    scenario.parent.mkdir(parents=True)
    scenario.write_text(SCENARIO_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return repository


def _phase117_plan_payload() -> PlanPayload:
    payload = yaml.safe_load(STUDY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload.setdefault(
        "claim_ids",
        ["scenario.73_easting.documented_outcomes"],
    )
    payload["plan_repository_path"] = "data/validation/historical_studies/study.yaml"
    return payload


@pytest.mark.parametrize(
    "value",
    (
        ".",
        "data//validation/study.yaml",
        "data/validation/study.yaml/",
        "./data/validation/study.yaml",
    ),
)
def test_repository_relative_path_rejects_noncanonical_spelling(value: str) -> None:
    with pytest.raises(ValueError, match="repository-relative POSIX path"):
        require_relative_posix_path(value, field_name="repository_path")


def _write_plan(repository: Path, payload: PlanPayload) -> Path:
    path = repository / "data/validation/historical_studies/study.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _overlap_held_out_seed(payload: PlanPayload) -> None:
    payload["lineage"]["training_seed_intervals"].append(
        {"first": 11700, "last": 11700},
    )


def _add_analysis_patch(payload: PlanPayload) -> None:
    payload["analysis"]["calibration_patch"] = {"combat.hit_probability": 1.0}


def _make_nineteen_seed_policy_impossible(payload: PlanPayload) -> None:
    payload["held_out_seed_interval"]["last"] = 11718
    payload["acceptance_policy"]["minimum_joint_coverage"] = 0.86


def _make_winner_the_only_gate(payload: PlanPayload) -> None:
    payload["gating_metrics"] = payload["diagnostic_metrics"]
    payload["diagnostic_metrics"] = []


def _use_unsupported_extractor(payload: PlanPayload) -> None:
    payload["gating_metrics"][0]["extractor"]["extractor_id"] = "arbitrary_python.v1"


def _split_source_boundaries(payload: PlanPayload) -> None:
    payload["diagnostic_metrics"][0]["source_event_boundary"] = "An unrelated campaign boundary."


def _omit_source_uses(payload: PlanPayload) -> None:
    payload["lineage"]["source_uses"] = []


def _use_hostless_source_url(payload: PlanPayload) -> None:
    payload["sources"][0]["url"] = "https://"


def _coerce_schema_version(payload: PlanPayload) -> None:
    payload["schema_version"] = True


def _coerce_required_policy_flag(payload: PlanPayload) -> None:
    payload["artifact_policy"]["clean_revision_required_for_promotion"] = 1


def _declare_excessive_held_out_interval(payload: PlanPayload) -> None:
    payload["held_out_seed_interval"]["last"] = payload["held_out_seed_interval"]["first"] + 1_000


def _use_unstable_study_id(payload: PlanPayload) -> None:
    payload["study_id"] = "Bad Study / 117"


def _use_unstable_claim_id(payload: PlanPayload) -> None:
    payload["claim_ids"] = ["Bad Claim / 117"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_overlap_held_out_seed, "held-out seed interval overlaps prior seeds"),
        (_add_analysis_patch, "empty calibration_patch"),
        (
            _make_nineteen_seed_policy_impossible,
            "cannot reach the declared joint coverage policy",
        ),
        (_make_winner_the_only_gate, "winner-only gating"),
        (_use_unsupported_extractor, "extractor_id"),
        (_split_source_boundaries, "share one source event boundary"),
        (_omit_source_uses, "completely reference declared sources"),
        (_use_hostless_source_url, "valid HTTP\\(S\\) URL"),
        (_coerce_schema_version, "strict integer 1"),
        (_coerce_required_policy_flag, "strict boolean true"),
        (
            _declare_excessive_held_out_interval,
            "maximum of 1000 production runs",
        ),
        (_use_unstable_study_id, "only lowercase letters"),
        (_use_unstable_claim_id, "only lowercase letters"),
    ],
    ids=(
        "overlapping-seeds",
        "nonempty-analysis-patch",
        "impossible-nineteen-seed-policy",
        "winner-only-gating",
        "unsupported-extractor",
        "split-source-boundaries",
        "missing-source-use",
        "hostless-source-url",
        "coerced-schema-version",
        "coerced-policy-flag",
        "excessive-held-out-interval",
        "unstable-study-id",
        "unstable-claim-id",
    ),
)
def test_study_loader_rejects_invalid_plan_before_execution(
    isolated_study_repository: Path,
    mutate: Callable[[PlanPayload], None],
    message: str,
) -> None:
    payload = _phase117_plan_payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        HistoricalStudyLoader(isolated_study_repository).load(
            _write_plan(isolated_study_repository, payload),
        )


def test_study_loader_rejects_duplicate_yaml_keys(
    isolated_study_repository: Path,
) -> None:
    path = isolated_study_repository / "data/validation/historical_studies/study.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: 1\n" + STUDY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate YAML mapping key 'schema_version'"):
        HistoricalStudyLoader(isolated_study_repository).load(path)


def test_study_loader_rejects_a_symlinked_input_alias(
    isolated_study_repository: Path,
) -> None:
    plan_path = _write_plan(
        isolated_study_repository,
        _phase117_plan_payload(),
    )
    alias = isolated_study_repository / "study-alias.yaml"
    alias.symlink_to(plan_path)

    with pytest.raises(ValueError, match="must not traverse a symlink"):
        HistoricalStudyLoader(isolated_study_repository).load(alias)


def test_study_loader_rejects_an_unauthored_unit_type(
    isolated_study_repository: Path,
) -> None:
    payload = _phase117_plan_payload()
    payload["gating_metrics"][0]["extractor"]["included_unit_types"] = [
        "invented_vehicle",
    ]

    with pytest.raises(ValueError, match="unauthored unit type"):
        HistoricalStudyLoader(isolated_study_repository).load(
            _write_plan(isolated_study_repository, payload),
        )


def test_study_contract_rejects_arbitrary_same_unit_conversion() -> None:
    payload = _synthetic_plan().model_dump(mode="python", exclude_none=False)
    payload["gating_metrics"][0]["extractor"]["conversion"] = {
        "scale": 999.0,
        "offset": 17.0,
    }

    with pytest.raises(ValueError, match="closed lossless conversion"):
        HistoricalStudyPlan.model_validate(payload)


def test_large_prior_seed_intervals_use_interval_arithmetic() -> None:
    payload = _phase117_plan_payload()
    payload["lineage"]["training_seed_intervals"] = [
        {"first": 0, "last": 10**12},
    ]
    payload["held_out_seed_interval"] = {
        "first": 10**12 + 1,
        "last": 10**12 + 20,
    }

    plan = HistoricalStudyPlan.model_validate(payload)

    assert plan.lineage.training_seed_intervals[0].count == 10**12 + 1
    assert plan.held_out_seeds == tuple(range(10**12 + 1, 10**12 + 21))


def test_study_contract_rejects_duration_unreachable_after_unit_conversion() -> None:
    payload = _phase117_plan_payload()
    metric = next(
        metric for metric in payload["gating_metrics"] if metric["metric_id"] == "natural_action_duration_seconds"
    )
    metric["source_range"] = {"minimum": 30.0, "maximum": 30.0}
    metric["source_unit"] = "minutes"
    metric["extractor"]["conversion"] = {
        "scale": 1.0 / 60.0,
        "offset": 0.0,
    }

    with pytest.raises(ValueError, match="no reachable value"):
        HistoricalStudyPlan.model_validate(payload)


@pytest.mark.parametrize(
    "usage",
    ("scenario_metadata_authoring", "scenario_calibration", "unknown"),
)
def test_study_contract_rejects_false_independent_source_lineage(
    usage: str,
) -> None:
    payload = _phase117_plan_payload()
    payload["lineage"]["validation_source_relationship"] = "independent"
    payload["lineage"]["source_uses"][0]["usage"] = usage

    with pytest.raises(ValueError, match="contradicts the complete source uses"):
        HistoricalStudyPlan.model_validate(payload)


def test_vehicle_count_rejects_nonvehicle_ground_entities() -> None:
    path = ROOT / "data/validation/historical_studies/agincourt_era_control_phase117.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["gating_metrics"][0]["source_unit"] = "vehicle_count"
    payload["gating_metrics"][0]["extractor"]["runtime_unit"] = "vehicle_count"
    plan = HistoricalStudyPlan.model_validate(payload)
    config = load_campaign_scenario_config(ROOT / plan.scenario_path)

    with pytest.raises(ValueError, match="non-vehicle unit type"):
        validate_historical_runtime_scope(
            plan,
            config,
            data_root=ROOT / plan.data_root,
        )


def test_runtime_scope_rejects_an_authored_type_absent_from_effective_catalog() -> None:
    path = ROOT / "data/validation/historical_studies/agincourt_era_control_phase117.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["gating_metrics"][0]["extractor"]["included_unit_types"][0] = "invented_entity_type"
    plan = HistoricalStudyPlan.model_validate(payload)
    config = load_campaign_scenario_config(ROOT / plan.scenario_path)
    config_payload = config.model_dump(mode="python")
    config_payload["sides"][0]["units"][0]["unit_type"] = "invented_entity_type"
    invented_config = type(config).model_validate(config_payload)

    with pytest.raises(ValueError, match="has no effective definition"):
        validate_historical_runtime_scope(
            plan,
            invented_config,
            data_root=ROOT / plan.data_root,
        )


def _synthetic_plan(*, expected_duration: float = 10.0) -> HistoricalStudyPlan:
    return HistoricalStudyPlan.model_validate(
        {
            "schema_version": 1,
            "study_id": "phase117.synthetic-artifact.v1",
            "plan_repository_path": ("data/validation/historical_studies/synthetic.yaml"),
            "claim_ids": ["synthetic.phase117.claim"],
            "scenario_path": "data/scenarios/synthetic/scenario.yaml",
            "data_root": "data",
            "intended_use": "Exercise receipt-recomputed artifact integrity.",
            "limitations": ["Synthetic integrity fixture; not historical evidence."],
            "sources": [
                {
                    "source_id": "synthetic_fixture_source",
                    "url": "https://example.invalid/phase117-fixture",
                    "citation": "Synthetic Phase 117 integrity fixture.",
                    "quality": "tertiary",
                    "locator": "test fixture",
                    "accessed_on": date(2026, 8, 2),
                    "supported_assertion": "A ten-second synthetic terminal duration.",
                    "conflict_notes": [],
                },
            ],
            "lineage": {
                "validation_source_relationship": "independent",
                "source_uses": [
                    {
                        "source_id": "synthetic_fixture_source",
                        "usage": "diagnostic_only",
                        "details": "Used only to exercise the artifact contract.",
                    },
                ],
                "training_seed_intervals": [],
                "diagnostic_seed_intervals": [],
                "notes": ["The fixture has no calibration or training lineage."],
            },
            "held_out_seed_interval": {"first": 20000, "last": 20019},
            "observation_boundary_s": 10.0,
            "maximum_ticks": 2,
            "analysis": {
                "variant_id": "phase117_synthetic",
                "calibration_patch": {},
            },
            "acceptance_policy": {
                "confidence": 0.95,
                "minimum_joint_coverage": 0.80,
            },
            "gating_metrics": [
                {
                    "metric_id": "terminal_duration",
                    "name": "Synthetic natural terminal duration",
                    "source_ids": ["synthetic_fixture_source"],
                    "source_range": {
                        "minimum": expected_duration,
                        "maximum": expected_duration,
                    },
                    "source_unit": "seconds",
                    "source_event_boundary": "Synthetic natural terminal.",
                    "range_rationale": "The fixture declares exactly ten seconds.",
                    "extractor": {
                        "extractor_id": "time_to_natural_terminal_seconds.v1",
                        "event_boundary": "source_synchronous_cutoff",
                        "runtime_unit": "seconds",
                        "conversion": {"scale": 1.0, "offset": 0.0},
                    },
                },
            ],
            "diagnostic_metrics": [
                {
                    "metric_id": "blue_winner",
                    "name": "Synthetic blue winner diagnostic",
                    "source_ids": ["synthetic_fixture_source"],
                    "source_range": {"minimum": 1.0, "maximum": 1.0},
                    "source_unit": "indicator",
                    "source_event_boundary": "Synthetic natural terminal.",
                    "range_rationale": "Winner remains diagnostic only.",
                    "extractor": {
                        "extractor_id": "terminal_winner_indicator.v1",
                        "event_boundary": "source_synchronous_cutoff",
                        "side": "blue",
                        "runtime_unit": "indicator",
                        "conversion": {"scale": 1.0, "offset": 0.0},
                    },
                },
            ],
            "artifact_policy": {
                "clean_revision_required_for_promotion": True,
                "immutable_predeclaration_required_for_promotion": True,
                "predeclaration_revision": None,
            },
        },
    )


def _constant_statistics(value: float, sample_size: int) -> MetricStatistics:
    return MetricStatistics(
        mean=value,
        median=value,
        std=0.0,
        minimum=value,
        maximum=value,
        p5=value,
        p95=value,
        n=sample_size,
    )


def _synthetic_completed_artifact(
    *,
    expected_duration: float = 10.0,
    winning_side: str = "blue",
    ticks_executed: int = 2,
) -> CompletedHistoricalArtifact:
    plan = _synthetic_plan(expected_duration=expected_duration)
    source_fingerprint = "1" * 64
    config_fingerprint = "2" * 64
    era_config_sha256 = "3" * 64
    era_runtime_contract_sha256 = "4" * 64
    code_revision = CodeRevisionEvidence(
        commit="b" * 40,
        dirty=False,
        worktree_fingerprint=canonical_sha256(
            {"commit": "b" * 40, "dirty": False},
        ),
    )
    initial_assignments = (
        UnitAssignmentEvidence(
            unit_id="blue-1",
            side="blue",
            commander_profile_id=None,
            doctrine_school_id=None,
        ),
        UnitAssignmentEvidence(
            unit_id="red-1",
            side="red",
            commander_profile_id=None,
            doctrine_school_id=None,
        ),
    )
    provenance = RuntimeProvenanceEvidence(
        code_revision=code_revision,
        data_revision="6" * 64,
        data_file_count=1,
        catalog_revision="7" * 64,
        doctrine_catalog_fingerprint="8" * 64,
        doctrine_assignment_fingerprint=canonical_sha256(initial_assignments),
        loaded_roster_loadout_fingerprint="a" * 64,
        final_roster_loadout_fingerprint="a" * 64,
        initial_unit_assignments=initial_assignments,
        arriving_unit_assignments=(),
    )
    loaded_typed_roster = (
        UnitIdentityEvidence(
            unit_id="blue-1",
            unit_type="synthetic_blue_unit",
            side="blue",
        ),
        UnitIdentityEvidence(
            unit_id="red-1",
            unit_type="synthetic_red_unit",
            side="red",
        ),
    )
    duration_metric = plan.gating_metrics[0]
    winner_metric = plan.diagnostic_metrics[0]
    winner_value = float(winning_side == "blue")
    runs: list[HistoricalRunEvidence] = []
    for seed in plan.held_out_seeds:
        terminal = TerminalOutcomeEvidence(
            seed=seed,
            ticks_executed=ticks_executed,
            duration_s=10.0,
            winning_side=winning_side,
            condition_type="force_destroyed",
            game_over=True,
            natural_terminal=True,
            right_censored=False,
        )
        terminal_sha256 = canonical_sha256(terminal)
        common_receipt = {
            "seed": seed,
            "source_fingerprint": source_fingerprint,
            "config_fingerprint": config_fingerprint,
            "event_boundary": "source_synchronous_cutoff",
            "observation_time_s": 10.0,
            "natural_terminal": True,
            "right_censored": False,
            "scale": 1.0,
            "offset": 0.0,
            "selected_units": (),
            "counted_unit_ids": (),
            "numerator_count": None,
            "denominator_count": None,
            "effective_era_id": "synthetic-era",
            "era_config_sha256": era_config_sha256,
            "era_runtime_contract_sha256": era_runtime_contract_sha256,
            "terminal_outcome_sha256": terminal_sha256,
        }
        duration_receipt = MetricObservationReceipt(
            **common_receipt,
            metric_id=duration_metric.metric_id,
            extractor_id=duration_metric.extractor.extractor_id,
            extractor_sha256=canonical_sha256(duration_metric.extractor),
            runtime_unit="seconds",
            source_unit="seconds",
            raw_value=10.0,
            value=10.0,
            in_source_range=expected_duration == 10.0,
        )
        winner_receipt = MetricObservationReceipt(
            **common_receipt,
            metric_id=winner_metric.metric_id,
            extractor_id=winner_metric.extractor.extractor_id,
            extractor_sha256=canonical_sha256(winner_metric.extractor),
            runtime_unit="indicator",
            source_unit="indicator",
            raw_value=winner_value,
            value=winner_value,
            in_source_range=winner_value == 1.0,
        )
        runs.append(
            HistoricalRunEvidence(
                seed=seed,
                source_fingerprint=source_fingerprint,
                config_fingerprint=config_fingerprint,
                loaded_roster=(("blue", 1), ("red", 1)),
                loaded_typed_roster=loaded_typed_roster,
                terminal_outcome=terminal,
                runtime_provenance=provenance,
                receipts=(duration_receipt, winner_receipt),
            ),
        )

    sample_size = len(plan.held_out_seeds)
    gating_in_range = (expected_duration == 10.0,) * sample_size
    evaluation = evaluate_joint_coverage(
        metric_in_range=((duration_metric.metric_id, gating_in_range),),
        confidence=plan.acceptance_policy.confidence,
        minimum_joint_coverage=plan.acceptance_policy.minimum_joint_coverage,
    )
    execution = HistoricalExecutionEvidence(
        scenario_path=plan.scenario_path,
        data_root=plan.data_root,
        variant_id=plan.analysis.variant_id,
        ordered_metrics=(duration_metric.metric_id, winner_metric.metric_id),
        seeds=plan.held_out_seeds,
        maximum_ticks=plan.maximum_ticks,
        observation_boundary_s=plan.observation_boundary_s,
        source_fingerprint=source_fingerprint,
        config_fingerprint=config_fingerprint,
        authored_roster=(("blue", 1), ("red", 1)),
        authored_typed_roster=(
            ("blue", "synthetic_blue_unit", 1),
            ("red", "synthetic_red_unit", 1),
        ),
        loaded_roster=(("blue", 1), ("red", 1)),
        loaded_typed_roster=loaded_typed_roster,
        code_revision=code_revision,
        data_revision=provenance.data_revision,
        data_file_count=provenance.data_file_count,
        catalog_revision=provenance.catalog_revision,
        doctrine_catalog_fingerprint=provenance.doctrine_catalog_fingerprint,
        loaded_roster_loadout_fingerprint=(provenance.loaded_roster_loadout_fingerprint),
        initial_unit_assignments=initial_assignments,
        effective_era_id="synthetic-era",
        era_config_sha256=era_config_sha256,
        era_runtime_contract_sha256=era_runtime_contract_sha256,
        predeclaration_receipt=None,
        metric_vectors=(
            (duration_metric.metric_id, (10.0,) * sample_size),
            (winner_metric.metric_id, (winner_value,) * sample_size),
        ),
        metric_statistics=(
            (
                duration_metric.metric_id,
                _constant_statistics(10.0, sample_size),
            ),
            (
                winner_metric.metric_id,
                _constant_statistics(winner_value, sample_size),
            ),
        ),
        runs=tuple(runs),
    )
    eligibility = HistoricalEligibility(
        promotion_eligible=False,
        reason_codes=(
            ("plan_not_immutably_predeclared",)
            if evaluation.passed
            else ("study_failed", "plan_not_immutably_predeclared")
        ),
    )
    result = HistoricalBacktestResult(
        status="PASS" if evaluation.passed else "FAIL",
        plan_sha256=plan.plan_sha256,
        execution=execution,
        evaluation=evaluation,
        eligibility=eligibility,
    )
    return create_completed_artifact(
        plan=plan,
        result=result,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="c" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id="synthetic.phase117.claim",
                repository_path=plan.scenario_path,
                content_sha256="d" * 64,
            ),
        ),
        now=FIXED_TIME,
    )


def test_completed_artifact_round_trips_through_atomic_writer(tmp_path: Path) -> None:
    artifact = _synthetic_completed_artifact()
    target = tmp_path / "nested/evidence.json"
    target.parent.mkdir()
    target.write_text('{"stale": true}\n', encoding="utf-8")

    published = write_historical_artifact(target, artifact)

    assert published == artifact
    assert load_historical_artifact(target) == artifact
    assert tuple(target.parent.glob(f".{target.name}.*.tmp")) == ()


def test_completed_artifact_rejects_natural_time_inconsistent_with_ticks() -> None:
    with pytest.raises(ValueError, match="logical tick cadence"):
        _synthetic_completed_artifact(ticks_executed=1)


@pytest.mark.parametrize("alias_kind", ("target", "parent"))
def test_artifact_loader_rejects_symlink_aliases(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    artifact = _synthetic_completed_artifact()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    real_target = real_parent / "evidence.json"
    write_historical_artifact(real_target, artifact)

    if alias_kind == "target":
        alias = tmp_path / "evidence-alias.json"
        alias.symlink_to(real_target)
    else:
        alias_parent = tmp_path / "parent-alias"
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        alias = alias_parent / real_target.name

    with pytest.raises(ValueError, match="must not traverse a symlink"):
        load_historical_artifact(alias)


@pytest.mark.parametrize("alias_kind", ("target", "parent"))
def test_artifact_writer_rejects_symlink_aliases_without_mutating_destination(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    artifact = _synthetic_completed_artifact()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    real_target = real_parent / "evidence.json"
    real_target.write_text('{"preserved": true}\n', encoding="utf-8")

    if alias_kind == "target":
        alias = tmp_path / "evidence-alias.json"
        alias.symlink_to(real_target)
    else:
        alias_parent = tmp_path / "parent-alias"
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        alias = alias_parent / real_target.name

    with pytest.raises(ValueError, match="must not traverse a symlink"):
        write_historical_artifact(alias, artifact)

    assert real_target.read_text(encoding="utf-8") == '{"preserved": true}\n'


def test_completed_execution_rejects_winner_outside_authored_sides() -> None:
    with pytest.raises(ValueError, match=r"not a (?:loaded|authored) side or draw"):
        _synthetic_completed_artifact(winning_side="invented-side")


def test_unit_status_receipt_rejects_invented_runtime_status() -> None:
    with pytest.raises(ValueError, match="production UnitStatus"):
        UnitStatusObservation(
            unit_id="blue-1",
            unit_type="synthetic_blue_unit",
            side="blue",
            status="INVENTED",
        )


def test_completed_artifact_rejects_invented_terminal_condition() -> None:
    artifact = _synthetic_completed_artifact()
    payload = deepcopy(artifact.model_dump(mode="json", exclude_none=False))
    for run in payload["execution"]["runs"]:
        terminal = run["terminal_outcome"]
        terminal["condition_type"] = "invented-condition"
        terminal_sha256 = canonical_sha256(terminal)
        for receipt in run["receipts"]:
            receipt["terminal_outcome_sha256"] = terminal_sha256
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )

    with pytest.raises(
        ValueError,
        match="not a supported production terminal condition",
    ):
        CompletedHistoricalArtifact.model_validate(payload)


@pytest.mark.parametrize("condition_type", ("ceasefire", "armistice"))
def test_historical_terminal_evidence_accepts_production_negotiated_conditions(
    condition_type: str,
) -> None:
    outcome = TerminalOutcomeEvidence(
        seed=117,
        ticks_executed=1,
        duration_s=5.0,
        winning_side="draw",
        condition_type=condition_type,
        game_over=True,
        natural_terminal=True,
        right_censored=False,
    )

    assert outcome.condition_type == condition_type


def test_atomic_writer_preserves_existing_target_when_staged_reload_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _synthetic_completed_artifact()
    target = tmp_path / "evidence.json"
    target.write_text('{"stale": true}\n', encoding="utf-8")

    def reject_staged_artifact(_path: Path) -> None:
        raise ValueError("synthetic staged validation failure")

    monkeypatch.setattr(
        artifact_module,
        "load_historical_artifact",
        reject_staged_artifact,
    )

    with pytest.raises(ValueError, match="staged validation failure"):
        write_historical_artifact(target, artifact)

    assert target.read_text(encoding="utf-8") == '{"stale": true}\n'
    assert tuple(tmp_path.glob(f".{target.name}.*.tmp")) == ()


def _tamper_raw_receipt(payload: ArtifactPayload) -> None:
    payload["execution"]["runs"][0]["receipts"][0]["raw_value"] = 11.0


def _tamper_metric_vector(payload: ArtifactPayload) -> None:
    payload["execution"]["metric_vectors"][0][1][0] = 11.0


def _tamper_metric_statistics(payload: ArtifactPayload) -> None:
    payload["execution"]["metric_statistics"][0][1]["mean"] = 9.0


def _tamper_verdict(payload: ArtifactPayload) -> None:
    payload["status"] = "FAIL"


def _tamper_era_identity(payload: ArtifactPayload) -> None:
    payload["execution"]["effective_era_id"] = "tampered-era"


def _tamper_static_provenance(payload: ArtifactPayload) -> None:
    payload["execution"]["code_revision"]["commit"] = "e" * 40


def _tamper_doctrine_assignment_fingerprint(payload: ArtifactPayload) -> None:
    payload["execution"]["runs"][0]["runtime_provenance"]["doctrine_assignment_fingerprint"] = "e" * 64


def _tamper_outer_schema_version(payload: ArtifactPayload) -> None:
    payload["schema_version"] = True


def _tamper_nested_plan_schema_version(payload: ArtifactPayload) -> None:
    payload["plan"]["schema_version"] = 1.0


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_raw_receipt,
        _tamper_metric_vector,
        _tamper_metric_statistics,
        _tamper_verdict,
        _tamper_era_identity,
        _tamper_static_provenance,
        _tamper_doctrine_assignment_fingerprint,
        _tamper_outer_schema_version,
        _tamper_nested_plan_schema_version,
    ],
    ids=(
        "raw-receipt",
        "metric-vector",
        "metric-statistics",
        "verdict",
        "era-identity",
        "static-provenance",
        "doctrine-assignment-fingerprint",
        "outer-schema-version",
        "nested-plan-schema-version",
    ),
)
def test_recomputed_outer_digest_does_not_conceal_semantic_tampering(
    tamper: Callable[[ArtifactPayload], None],
) -> None:
    artifact = _synthetic_completed_artifact()
    payload = deepcopy(artifact.model_dump(mode="json", exclude_none=False))
    tamper(payload)
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )

    assert payload["artifact_sha256"] != artifact.artifact_sha256
    with pytest.raises(ValueError):
        CompletedHistoricalArtifact.model_validate(payload)


def test_error_artifact_has_no_metric_or_study_verdict() -> None:
    plan = _synthetic_plan()

    artifact = create_error_artifact(
        plan=plan,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="c" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id="synthetic.phase117.claim",
                repository_path=plan.scenario_path,
                content_sha256="d" * 64,
            ),
        ),
        failure_stage="runtime_preparation",
        error_code="historical_runtime_preparation_failed",
        message="Synthetic post-start execution fault.",
        preparation=None,
        completed_runs=(),
        now=FIXED_TIME,
    )

    payload = artifact.model_dump(mode="json", exclude_none=False)
    assert artifact.status == "ERROR"
    assert {"evaluation", "eligibility", "verdict", "passed"}.isdisjoint(payload)


def test_runtime_preparation_error_rejects_unrelated_preparation() -> None:
    completed = _synthetic_completed_artifact()
    execution = completed.execution
    preparation = HistoricalPreparationEvidence(
        scenario_path="data/scenarios/unrelated/scenario.yaml",
        data_root=execution.data_root,
        variant_id=execution.variant_id,
        source_fingerprint=execution.source_fingerprint,
        config_fingerprint=execution.config_fingerprint,
        authored_roster=execution.authored_roster,
        authored_typed_roster=execution.authored_typed_roster,
        code_revision=execution.code_revision,
        data_revision=execution.data_revision,
        data_file_count=execution.data_file_count,
        effective_era_id=execution.effective_era_id,
        era_config_sha256=execution.era_config_sha256,
        era_runtime_contract_sha256=execution.era_runtime_contract_sha256,
        predeclaration_receipt=execution.predeclaration_receipt,
    )

    with pytest.raises(ValueError, match="preparation evidence differs"):
        create_error_artifact(
            plan=completed.plan,
            execution_ledger_path=completed.execution_ledger_path,
            execution_ledger_sha256=completed.execution_ledger_sha256,
            claim_bindings=completed.claim_bindings,
            failure_stage="runtime_preparation",
            error_code="historical_runtime_preparation_failed",
            message="Synthetic mismatched preparation fault.",
            preparation=preparation,
            completed_runs=(),
            now=FIXED_TIME,
        )


def test_error_artifact_rejects_tampered_prefix_era_and_provenance() -> None:
    completed = _synthetic_completed_artifact()
    execution = completed.execution
    preparation = HistoricalPreparationEvidence(
        scenario_path=execution.scenario_path,
        data_root=execution.data_root,
        variant_id=execution.variant_id,
        source_fingerprint=execution.source_fingerprint,
        config_fingerprint=execution.config_fingerprint,
        authored_roster=execution.authored_roster,
        authored_typed_roster=execution.authored_typed_roster,
        code_revision=execution.code_revision,
        data_revision=execution.data_revision,
        data_file_count=execution.data_file_count,
        effective_era_id=execution.effective_era_id,
        era_config_sha256=execution.era_config_sha256,
        era_runtime_contract_sha256=execution.era_runtime_contract_sha256,
        predeclaration_receipt=execution.predeclaration_receipt,
    )
    error = create_error_artifact(
        plan=completed.plan,
        execution_ledger_path=completed.execution_ledger_path,
        execution_ledger_sha256=completed.execution_ledger_sha256,
        claim_bindings=completed.claim_bindings,
        failure_stage="runtime_execution",
        error_code="historical_runtime_execution_failed",
        message="Synthetic post-start execution fault.",
        preparation=preparation,
        completed_runs=(execution.runs[0],),
        now=FIXED_TIME,
    )
    payload = error.model_dump(mode="json", exclude_none=False)
    payload["completed_runs"][0]["runtime_provenance"]["data_file_count"] = 2
    for receipt in payload["completed_runs"][0]["receipts"]:
        receipt["effective_era_id"] = "tampered-era"
        receipt["era_config_sha256"] = "e" * 64
        receipt["era_runtime_contract_sha256"] = "f" * 64
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )

    with pytest.raises(ValueError):
        artifact_module.HistoricalErrorArtifact.model_validate(payload)


def test_joint_evaluation_schema_rejects_coerced_counts_and_booleans() -> None:
    evaluation = evaluate_joint_coverage(
        metric_in_range=(("metric", (True,) * 20),),
        confidence=0.95,
        minimum_joint_coverage=0.80,
    )
    payload = evaluation.model_dump(mode="json")
    payload["metric_in_range"][0][1][0] = 1
    payload["joint_in_range"][0] = 1
    payload["sample_size"] = "20"
    payload["passed"] = 1

    with pytest.raises(ValueError):
        type(evaluation).model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confidence", "0.95"),
        ("confidence", True),
        ("confidence", math.nan),
        ("minimum_joint_coverage", "0.80"),
        ("minimum_joint_coverage", False),
        ("minimum_joint_coverage", math.inf),
    ],
    ids=(
        "string-confidence",
        "boolean-confidence",
        "nonfinite-confidence",
        "string-minimum-coverage",
        "boolean-minimum-coverage",
        "nonfinite-minimum-coverage",
    ),
)
def test_joint_evaluator_rejects_non_strict_probabilities(
    field: str,
    value: object,
) -> None:
    arguments: dict[str, object] = {
        "metric_in_range": (("metric", (True,) * 20),),
        "confidence": 0.95,
        "minimum_joint_coverage": 0.80,
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=field):
        evaluate_joint_coverage(**arguments)


def test_claim_ledger_rejects_missing_accepted_artifact(tmp_path: Path) -> None:
    source_path = tmp_path / "data/scenarios/synthetic/scenario.yaml"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "documented_outcomes:\n- name: truth_metric\n",
        encoding="utf-8",
    )
    normalized_claim = {
        "kind": "yaml_path",
        "segments": ["documented_outcomes"],
        "content": [{"name": "truth_metric"}],
    }
    claim = {
        "claim_id": "scenario.synthetic.accepted",
        "repository_path": "data/scenarios/synthetic/scenario.yaml",
        "scenario_path": "data/scenarios/synthetic/scenario.yaml",
        "surface": "scenario_documented_outcomes",
        "locator": {
            "kind": "yaml_path",
            "segments": ["documented_outcomes"],
        },
        "content_sha256": canonical_sha256(normalized_claim),
        "disposition": "production_validated",
        "metric_scope": ["truth_metric"],
        "reason_codes": ["explicit_acceptance"],
        "limitation": "Synthetic loader rejection control.",
        "current_engine_regression_evidence": False,
        "accepted_evidence": {
            "study_id": "synthetic.accepted.v1",
            "artifact_path": "docs/evidence/missing.json",
            "artifact_sha256": hashlib.sha256(b"missing artifact").hexdigest(),
            "metric_bindings": [
                {
                    "claim_metric": "truth_metric",
                    "study_metric_id": "truth_metric",
                },
            ],
        },
    }
    payload = {
        "schema_version": 1,
        "ledger_id": "synthetic.acceptance.v1",
        "claim_source_scanner_version": 2,
        "claim_source_reviews": [],
        "claims": [claim],
    }
    candidate = scan_historical_claim_sources(
        tmp_path,
        source_kinds=frozenset({ClaimSourceKind.SCENARIO_YAML}),
    )[0]
    review = candidate.model_dump(mode="json")
    review["claim_ids"] = [claim["claim_id"]]
    review["exclusion"] = None
    payload["claim_source_reviews"] = [review]
    payload["ledger_sha256"] = canonical_sha256(payload)
    ledger_path = tmp_path / "ledger.yaml"
    ledger_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unavailable or invalid"):
        HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_diagnostic_winner_change_cannot_rescue_a_gating_failure() -> None:
    blue_winner = _synthetic_completed_artifact(
        expected_duration=9.0,
        winning_side="blue",
    )
    red_winner = _synthetic_completed_artifact(
        expected_duration=9.0,
        winning_side="red",
    )

    assert blue_winner.execution.metric_vectors[0] == red_winner.execution.metric_vectors[0]
    assert blue_winner.execution.metric_vectors[1] != red_winner.execution.metric_vectors[1]
    assert blue_winner.evaluation == red_winner.evaluation
    assert blue_winner.status == red_winner.status == "FAIL"
