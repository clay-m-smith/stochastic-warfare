"""Adversarial lifecycle and outcome controls for Phase 117 backtests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Callable

import numpy as np
import pytest
import yaml

from scripts import run_historical_backtest as backtest_cli
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.tools._run_helpers import (
    AnalysisRunner,
    validate_serialized_batch_evidence,
)
from stochastic_warfare.validation.historical_backtest import (
    ClaimBinding,
    CompletedHistoricalArtifact,
    HistoricalBacktestResult,
    HistoricalBacktestRunner,
    HistoricalEligibility,
    HistoricalErrorArtifact,
    HistoricalExecutionEvidence,
    HistoricalExecutionError,
    HistoricalPreparationEvidence,
    HistoricalRunEvidence,
    HistoricalStudyPlan,
    MetricObservationReceipt,
    TerminalOutcomeEvidence,
    create_completed_artifact,
    create_error_artifact,
    evaluate_joint_coverage,
    load_historical_artifact,
    write_historical_artifact,
)
from stochastic_warfare.validation.historical_backtest.common import (
    canonical_sha256,
)
from stochastic_warfare.validation.historical_backtest.runner import (
    MetricStatistics,
)


ROOT = Path(__file__).resolve().parents[2]
ERA_CONTROL_PLAN = ROOT / "data/validation/historical_studies/agincourt_era_control_phase117.yaml"
LEDGER_PATH = ROOT / "data/validation/historical_claims.yaml"
FIXED_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class RatioControl:
    """One bounded real production result and its exact ratio plan."""

    plan: HistoricalStudyPlan
    prepared: PreparedScenario
    result: HistoricalBacktestResult


def _era_control_payload() -> dict[str, Any]:
    payload = yaml.safe_load(ERA_CONTROL_PLAN.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _ratio_plan(*, last_seed: int = 21700) -> HistoricalStudyPlan:
    payload = _era_control_payload()
    payload["study_id"] = "agincourt.phase117.exchange-ratio-control.v1"
    payload["held_out_seed_interval"]["last"] = last_seed
    payload["acceptance_policy"] = {
        "confidence": 0.95,
        "minimum_joint_coverage": 0.01 if last_seed == 21700 else 0.80,
    }
    payload["gating_metrics"] = [
        {
            "metric_id": "english_active_to_french_destroyed_ratio",
            "name": "English active to French destroyed control ratio",
            "source_ids": ["repository_agincourt_roster"],
            "source_range": {"minimum": 5.0, "maximum": 5.0},
            "source_unit": "ratio",
            "source_event_boundary": ("One exact production tactical tick from scenario start."),
            "range_rationale": (
                "The implementation control expects five active English entities "
                "and uses the declared zero-denominator rule."
            ),
            "extractor": {
                "extractor_id": "terminal_exchange_ratio.v1",
                "event_boundary": "source_synchronous_cutoff",
                "runtime_unit": "ratio",
                "conversion": {"scale": 1.0, "offset": 0.0},
                "numerator": {
                    "side": "english",
                    "status": "ACTIVE",
                    "included_unit_types": [
                        "english_longbowman",
                        "viking_huscarl",
                    ],
                },
                "denominator": {
                    "side": "french",
                    "status": "DESTROYED",
                    "included_unit_types": [
                        "norman_knight_conroi",
                        "viking_huscarl",
                    ],
                },
                "zero_denominator_rule": "divide_by_one",
                "roster_scope": "initial_only",
            },
        },
    ]
    payload["diagnostic_metrics"] = []
    return HistoricalStudyPlan.model_validate(payload)


def _prepare(plan: HistoricalStudyPlan) -> PreparedScenario:
    return SimulationRuntimeFactory().prepare(
        ROOT / plan.scenario_path,
        ROOT / plan.data_root,
        (
            AnalysisVariant(
                variant_id=plan.analysis.variant_id,
                calibration_patch=plan.analysis.calibration_patch,
            ),
        ),
    )


@pytest.fixture(scope="module")
def production_ratio_control() -> RatioControl:
    plan = _ratio_plan()
    prepared = _prepare(plan)
    result = HistoricalBacktestRunner(prepared, plan).run()
    return RatioControl(plan=plan, prepared=prepared, result=result)


def _unauthored_ratio_scope_plan() -> HistoricalStudyPlan:
    payload = _ratio_plan().model_dump(mode="python", exclude_none=False)
    payload["gating_metrics"][0]["extractor"]["numerator"]["included_unit_types"] = ["definitely_not_authored"]
    return HistoricalStudyPlan.model_validate(payload)


def _nonvehicle_vehicle_count_plan() -> HistoricalStudyPlan:
    payload = _era_control_payload()
    metric = payload["gating_metrics"][0]
    metric["source_unit"] = "vehicle_count"
    metric["extractor"]["runtime_unit"] = "vehicle_count"
    return HistoricalStudyPlan.model_validate(payload)


@pytest.mark.parametrize(
    ("plan_factory", "message"),
    (
        pytest.param(
            _unauthored_ratio_scope_plan,
            "unauthored unit type",
            id="unauthored-unit-type",
        ),
        pytest.param(
            _nonvehicle_vehicle_count_plan,
            "vehicle_count includes non-vehicle unit type",
            id="nonvehicle-vehicle-count",
        ),
    ),
)
def test_public_runner_revalidates_plan_runtime_scope_before_execution(
    production_ratio_control: RatioControl,
    plan_factory: Callable[[], HistoricalStudyPlan],
    message: str,
) -> None:
    plan = plan_factory()

    with pytest.raises(HistoricalExecutionError, match=message) as captured:
        HistoricalBacktestRunner(production_ratio_control.prepared, plan)

    assert captured.value.failure_stage == "runtime_preparation"
    assert captured.value.completed_runs == ()


def test_runner_rejects_a_natural_result_inconsistent_with_the_live_clock(
    production_ratio_control: RatioControl,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run = RuntimeSession.run_to_completion

    def return_impossible_natural_result(self: RuntimeSession):
        result = original_run(self)
        return replace(
            result,
            duration_s=result.duration_s / 2.0,
            victory_result=replace(
                result.victory_result,
                condition_type="force_destroyed",
            ),
        )

    monkeypatch.setattr(
        RuntimeSession,
        "run_to_completion",
        return_impossible_natural_result,
    )
    runner = HistoricalBacktestRunner(
        production_ratio_control.prepared,
        production_ratio_control.plan,
    )

    with pytest.raises(
        HistoricalExecutionError,
        match="result differs from the live production clock",
    ) as captured:
        runner.run()

    assert captured.value.failure_stage == "runtime_execution"
    assert captured.value.completed_runs == ()


def test_preparation_identity_mismatch_remains_durably_publishable(
    production_ratio_control: RatioControl,
    tmp_path: Path,
) -> None:
    plan = production_ratio_control.plan
    drifted = replace(
        production_ratio_control.prepared,
        scenario_path=ROOT / "data/scenarios/73_easting/scenario.yaml",
    )

    with pytest.raises(HistoricalExecutionError) as captured:
        HistoricalBacktestRunner(drifted, plan)

    error = captured.value
    artifact = create_error_artifact(
        plan=plan,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="a" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id=plan.claim_ids[0],
                repository_path=plan.scenario_path,
                content_sha256="b" * 64,
            ),
        ),
        failure_stage=error.failure_stage,
        error_code=error.error_code,
        message=str(error),
        preparation=error.preparation,
        completed_runs=error.completed_runs,
        now=FIXED_TIME,
    )
    target = tmp_path / "preparation-error.json"

    persisted = write_historical_artifact(target, artifact)

    assert error.failure_stage == "runtime_preparation"
    assert error.preparation is None
    assert persisted.status == "ERROR"
    assert load_historical_artifact(target) == artifact


@pytest.fixture(scope="module")
def serialized_analysis_batch(
    production_ratio_control: RatioControl,
) -> dict[str, Any]:
    batch = AnalysisRunner(
        production_ratio_control.prepared,
        ("ticks_executed",),
    ).run_variant(
        production_ratio_control.plan.analysis.variant_id,
        num_iterations=1,
        base_seed=21700,
        max_ticks=1,
    )
    return {
        "statistics": batch.statistics_dict(),
        "raw_metrics": batch.metrics_dict(),
        "ordered_metrics": list(batch.ordered_metrics),
        "provenance": batch.provenance_dict(),
    }


@pytest.mark.parametrize("condition_type", ("ceasefire", "armistice"))
def test_serialized_analysis_accepts_production_negotiated_conditions(
    serialized_analysis_batch: dict[str, Any],
    condition_type: str,
) -> None:
    payload = deepcopy(serialized_analysis_batch)
    payload["provenance"]["runs"][0]["condition_type"] = condition_type

    validate_serialized_batch_evidence(
        payload,
        num_iterations=1,
        base_seed=21700,
        max_ticks=1,
        completed_iterations=1,
    )

    unsupported = deepcopy(payload)
    unsupported["provenance"]["runs"][0]["condition_type"] = f"unsupported-{condition_type}"
    with pytest.raises(
        ValueError,
        match="condition_type is not a supported terminal condition",
    ):
        validate_serialized_batch_evidence(
            unsupported,
            num_iterations=1,
            base_seed=21700,
            max_ticks=1,
            completed_iterations=1,
        )


def test_cli_invalid_plan_rejects_before_publishing_an_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    plan_path = repository / "data/validation/historical_studies/invalid.yaml"
    ledger_path = repository / "data/validation/historical_claims.yaml"
    output_path = repository / "docs/evidence/phase-117/invalid.json"
    plan_path.parent.mkdir(parents=True)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        "schema_version: 1\nstudy_id: invalid\nunexpected_field: true\n",
        encoding="utf-8",
    )
    ledger_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(backtest_cli, "ROOT", repository)
    monkeypatch.setattr(
        backtest_cli.HistoricalClaimLedgerLoader,
        "load",
        lambda _loader, _path: object(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_historical_backtest.py",
            "--ledger",
            str(ledger_path),
            "--plan",
            str(plan_path),
            "--output",
            str(output_path),
        ],
    )

    with pytest.raises(ValueError):
        backtest_cli.main()

    assert not output_path.exists()
    assert not output_path.parent.exists()


@pytest.mark.parametrize("alias_kind", ("ledger", "plan", "output", "output-parent"))
def test_cli_rejects_symlinked_path_aliases_before_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alias_kind: str,
) -> None:
    repository = tmp_path / "repository"
    ledger = repository / "data/validation/historical_claims.yaml"
    plan = repository / "data/validation/historical_studies/study.yaml"
    output = repository / "docs/evidence/phase-117/result.json"
    ledger.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    ledger.write_text("{}\n", encoding="utf-8")
    plan.write_text("{}\n", encoding="utf-8")

    arguments = {"ledger": ledger, "plan": plan, "output": output}
    if alias_kind in {"ledger", "plan"}:
        alias = repository / f"{alias_kind}-alias.yaml"
        alias.symlink_to(arguments[alias_kind])
        arguments[alias_kind] = alias
    elif alias_kind == "output":
        output.write_text('{"preserved": true}\n', encoding="utf-8")
        alias = output.with_name("result-alias.json")
        alias.symlink_to(output)
        arguments["output"] = alias
    else:
        alias_parent = repository / "docs/evidence-alias"
        alias_parent.symlink_to(output.parent, target_is_directory=True)
        arguments["output"] = alias_parent / "result.json"

    monkeypatch.setattr(backtest_cli, "ROOT", repository)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_historical_backtest.py",
            "--ledger",
            str(arguments["ledger"]),
            "--plan",
            str(arguments["plan"]),
            "--output",
            str(arguments["output"]),
        ],
    )

    with pytest.raises(ValueError, match="must not traverse a symlink"):
        backtest_cli.main()

    if output.exists():
        assert output.read_text(encoding="utf-8") == '{"preserved": true}\n'


def test_post_start_fault_persists_only_the_exact_completed_seed_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _era_control_payload()
    payload["study_id"] = "agincourt.phase117.error-prefix-control.v1"
    payload["held_out_seed_interval"]["last"] = 21701
    plan = HistoricalStudyPlan.model_validate(payload)
    prepared = _prepare(plan)
    original_build = PreparedScenario.build
    failed_seed = plan.held_out_seeds[1]

    def fail_second_build(
        self: PreparedScenario,
        variant: object,
        seed: int,
        max_ticks: int,
        *args: object,
        **kwargs: object,
    ) -> object:
        if self is prepared and seed == failed_seed:
            raise RuntimeError("injected second-seed construction fault")
        return original_build(
            self,
            variant,
            seed,
            max_ticks,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(PreparedScenario, "build", fail_second_build)
    runner = HistoricalBacktestRunner(prepared, plan)

    with pytest.raises(HistoricalExecutionError) as caught:
        runner.run()

    error = caught.value
    assert error.failure_stage == "runtime_construction"
    assert error.error_code == "historical_runtime_construction_failed"
    assert tuple(run.seed for run in error.completed_runs) == (plan.held_out_seeds[0],)
    assert failed_seed not in {run.seed for run in error.completed_runs}

    artifact = create_error_artifact(
        plan=plan,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="a" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id=plan.claim_ids[0],
                repository_path=plan.scenario_path,
                content_sha256="b" * 64,
            ),
        ),
        failure_stage=error.failure_stage,
        error_code=error.error_code,
        message=str(error),
        preparation=error.preparation,
        completed_runs=error.completed_runs,
        now=FIXED_TIME,
    )
    target = tmp_path / "post-start-error.json"
    persisted = write_historical_artifact(target, artifact)

    assert isinstance(persisted, HistoricalErrorArtifact)
    assert load_historical_artifact(target) == artifact
    assert tuple(run.seed for run in persisted.completed_runs) == (plan.held_out_seeds[0],)
    assert {
        "evaluation",
        "eligibility",
        "joint_successes",
        "passed",
    }.isdisjoint(persisted.model_dump(mode="json", exclude_none=False))


def test_exchange_ratio_uses_exact_production_scope_and_zero_rule(
    production_ratio_control: RatioControl,
) -> None:
    plan = production_ratio_control.plan
    result = production_ratio_control.result
    run = result.execution.runs[0]
    receipt = run.receipts[0]
    expected_selected_ids = (
        "english_english_longbowman_0000",
        "english_english_longbowman_0001",
        "english_english_longbowman_0002",
        "english_english_longbowman_0003",
        "english_viking_huscarl_0004",
        "french_norman_knight_conroi_0000",
        "french_norman_knight_conroi_0001",
        "french_norman_knight_conroi_0002",
        "french_viking_huscarl_0003",
    )

    assert result.status == "PASS"
    assert result.execution.metric_vectors == (("english_active_to_french_destroyed_ratio", (5.0,)),)
    assert plan.gating_metrics[0].extractor.zero_denominator_rule == "divide_by_one"
    assert receipt.numerator_count == 5.0
    assert receipt.denominator_count == 0.0
    assert receipt.raw_value == receipt.numerator_count / max(
        1.0,
        receipt.denominator_count,
    )
    assert receipt.value == 5.0
    assert receipt.in_source_range is True
    assert tuple(unit.unit_id for unit in receipt.selected_units) == (expected_selected_ids)
    assert tuple(unit.status for unit in receipt.selected_units) == ("ACTIVE",) * 9
    assert receipt.counted_unit_ids == expected_selected_ids[:5]
    assert receipt.terminal_outcome_sha256 == canonical_sha256(
        run.terminal_outcome,
    )
    assert receipt.extractor_sha256 == canonical_sha256(
        plan.gating_metrics[0].extractor,
    )
    assert run.loaded_typed_roster == result.execution.loaded_typed_roster


def _completed_ratio_artifact(control: RatioControl) -> CompletedHistoricalArtifact:
    return create_completed_artifact(
        plan=control.plan,
        result=control.result,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="c" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id=control.plan.claim_ids[0],
                repository_path=control.plan.scenario_path,
                content_sha256="d" * 64,
            ),
        ),
        now=FIXED_TIME,
    )


def _ratio_preparation(
    artifact: CompletedHistoricalArtifact,
) -> HistoricalPreparationEvidence:
    execution = artifact.execution
    return HistoricalPreparationEvidence(
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


def _append_out_of_scope_ratio_unit(payload: dict[str, object], *, error: bool) -> None:
    runs_key = "completed_runs" if error else "execution"
    if error:
        runs = payload[runs_key]
    else:
        execution = payload[runs_key]
        assert isinstance(execution, dict)
        runs = execution["runs"]
    assert isinstance(runs, list)
    run = runs[0]
    assert isinstance(run, dict)
    receipts = run["receipts"]
    assert isinstance(receipts, list)
    receipt = receipts[0]
    assert isinstance(receipt, dict)
    selected = receipt["selected_units"]
    assert isinstance(selected, list)
    selected.append(
        {
            "unit_id": "invented-out-of-scope-unit",
            "unit_type": "out_of_scope_type",
            "side": "english",
            "status": "ACTIVE",
        },
    )


def test_completed_ratio_artifact_rejects_out_of_scope_selected_unit(
    production_ratio_control: RatioControl,
) -> None:
    artifact = _completed_ratio_artifact(production_ratio_control)
    payload = artifact.model_dump(mode="json", exclude_none=False)
    _append_out_of_scope_ratio_unit(payload, error=False)
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )

    with pytest.raises(ValueError, match="out-of-scope unit"):
        CompletedHistoricalArtifact.model_validate(payload)


def test_error_ratio_artifact_rejects_out_of_scope_selected_unit(
    production_ratio_control: RatioControl,
) -> None:
    completed = _completed_ratio_artifact(production_ratio_control)
    error = create_error_artifact(
        plan=completed.plan,
        execution_ledger_path=completed.execution_ledger_path,
        execution_ledger_sha256=completed.execution_ledger_sha256,
        claim_bindings=completed.claim_bindings,
        failure_stage="evidence_construction",
        error_code="historical_evidence_construction_failed",
        message="Synthetic post-execution evidence fault.",
        preparation=_ratio_preparation(completed),
        completed_runs=completed.execution.runs,
        now=FIXED_TIME,
    )
    payload = error.model_dump(mode="json", exclude_none=False)
    _append_out_of_scope_ratio_unit(payload, error=True)
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )

    with pytest.raises(ValueError, match="out-of-scope unit"):
        HistoricalErrorArtifact.model_validate(payload)


def _metric_statistics(values: tuple[float, ...]) -> MetricStatistics:
    array = np.asarray(values, dtype=float)
    return MetricStatistics(
        mean=float(np.mean(array)),
        median=float(np.median(array)),
        std=float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        minimum=float(np.min(array)),
        maximum=float(np.max(array)),
        p5=float(np.percentile(array, 5)),
        p95=float(np.percentile(array, 95)),
        n=int(array.size),
    )


def _clone_ratio_run(
    base: HistoricalRunEvidence,
    *,
    seed: int,
    numerator_active: int,
) -> HistoricalRunEvidence:
    terminal_payload = base.terminal_outcome.model_dump(mode="python")
    terminal_payload["seed"] = seed
    terminal = TerminalOutcomeEvidence.model_validate(terminal_payload)

    receipt_payload = base.receipts[0].model_dump(mode="python")
    selected = [unit.model_dump(mode="python") for unit in base.receipts[0].selected_units]
    english_indexes = [
        index for index, unit in enumerate(selected) if unit["side"] == "english" and unit["status"] == "ACTIVE"
    ]
    for index in english_indexes[numerator_active:]:
        selected[index]["status"] = "ROUTING"
    numerator_ids = tuple(
        unit["unit_id"] for unit in selected if unit["side"] == "english" and unit["status"] == "ACTIVE"
    )
    denominator_ids = tuple(
        unit["unit_id"] for unit in selected if unit["side"] == "french" and unit["status"] == "DESTROYED"
    )
    denominator_count = float(len(denominator_ids))
    value = float(len(numerator_ids)) / max(1.0, denominator_count)
    receipt_payload.update(
        {
            "seed": seed,
            "selected_units": selected,
            "counted_unit_ids": numerator_ids + denominator_ids,
            "numerator_count": float(len(numerator_ids)),
            "denominator_count": denominator_count,
            "raw_value": value,
            "value": value,
            "in_source_range": value == 5.0,
            "terminal_outcome_sha256": canonical_sha256(terminal),
        },
    )
    receipt = MetricObservationReceipt.model_validate(receipt_payload)

    run_payload = base.model_dump(mode="python")
    run_payload.update(
        {
            "seed": seed,
            "terminal_outcome": terminal,
            "receipts": (receipt,),
        },
    )
    return HistoricalRunEvidence.model_validate(run_payload)


def _artifact_with_ratio_observations(
    control: RatioControl,
    *,
    outside_index: int | None,
) -> object:
    plan = _ratio_plan(last_seed=21719)
    base_run = control.result.execution.runs[0]
    runs = tuple(
        _clone_ratio_run(
            base_run,
            seed=seed,
            numerator_active=4 if index == outside_index else 5,
        )
        for index, seed in enumerate(plan.held_out_seeds)
    )
    metric_id = plan.gating_metrics[0].metric_id
    values = tuple(run.receipts[0].value for run in runs)
    execution_payload = control.result.execution.model_dump(mode="python")
    execution_payload.update(
        {
            "seeds": plan.held_out_seeds,
            "metric_vectors": ((metric_id, values),),
            "metric_statistics": ((metric_id, _metric_statistics(values)),),
            "runs": runs,
        },
    )
    execution = HistoricalExecutionEvidence.model_validate(execution_payload)
    metric_in_range = tuple(run.receipts[0].in_source_range for run in runs)
    evaluation = evaluate_joint_coverage(
        metric_in_range=((metric_id, metric_in_range),),
        confidence=plan.acceptance_policy.confidence,
        minimum_joint_coverage=(plan.acceptance_policy.minimum_joint_coverage),
    )
    reasons: list[str] = []
    if not evaluation.passed:
        reasons.append("study_failed")
    if execution.code_revision.dirty:
        reasons.append("dirty_revision")
    reasons.extend(
        (
            "validation_source_lineage_unknown",
            "plan_not_immutably_predeclared",
        ),
    )
    result = HistoricalBacktestResult(
        status="PASS" if evaluation.passed else "FAIL",
        plan_sha256=plan.plan_sha256,
        execution=execution,
        evaluation=evaluation,
        eligibility=HistoricalEligibility(
            promotion_eligible=False,
            reason_codes=tuple(reasons),
        ),
    )
    return create_completed_artifact(
        plan=plan,
        result=result,
        execution_ledger_path="data/validation/historical_claims.yaml",
        execution_ledger_sha256="c" * 64,
        claim_bindings=(
            ClaimBinding(
                claim_id=plan.claim_ids[0],
                repository_path=plan.scenario_path,
                content_sha256="d" * 64,
            ),
        ),
        now=FIXED_TIME,
    )


def test_one_observation_crossing_fixed_envelope_changes_joint_verdict(
    production_ratio_control: RatioControl,
) -> None:
    inside = _artifact_with_ratio_observations(
        production_ratio_control,
        outside_index=None,
    )
    outside = _artifact_with_ratio_observations(
        production_ratio_control,
        outside_index=19,
    )

    assert inside.plan == outside.plan
    assert inside.plan_sha256 == outside.plan_sha256
    assert inside.execution.metric_vectors == (("english_active_to_french_destroyed_ratio", (5.0,) * 20),)
    assert outside.execution.metric_vectors == (
        (
            "english_active_to_french_destroyed_ratio",
            (5.0,) * 19 + (4.0,),
        ),
    )
    assert inside.evaluation.joint_successes == 20
    assert outside.evaluation.joint_successes == 19
    assert inside.evaluation.lower_confidence_bound == pytest.approx(
        0.860891659332,
    )
    assert outside.evaluation.lower_confidence_bound == pytest.approx(
        0.783893835793,
    )
    assert inside.status == "PASS"
    assert outside.status == "FAIL"
    assert inside.evaluation.passed is True
    assert outside.evaluation.passed is False
    assert outside.evaluation.joint_in_range == (True,) * 19 + (False,)


def test_cli_converts_evidence_construction_failure_to_durable_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = ROOT / ".pytest_cache/phase117/evidence-construction-error.json"

    def reject_completed_artifact(**_kwargs: object) -> None:
        raise RuntimeError("injected completed-artifact construction fault")

    monkeypatch.setattr(
        backtest_cli,
        "create_completed_artifact",
        reject_completed_artifact,
    )
    monkeypatch.setattr(
        backtest_cli,
        "_artifact_output",
        lambda _path: output_path,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_historical_backtest.py",
            "--ledger",
            str(LEDGER_PATH),
            "--plan",
            str(ERA_CONTROL_PLAN),
            "--output",
            str(ROOT / "docs/evidence/phase-117/injected-error.json"),
        ],
    )

    exit_code = backtest_cli.main()
    reported = json.loads(capsys.readouterr().out)
    persisted = load_historical_artifact(output_path)

    assert exit_code == 2
    assert isinstance(persisted, HistoricalErrorArtifact)
    assert persisted.status == "ERROR"
    assert persisted.failure_stage == "evidence_construction"
    assert persisted.error_code == "historical_evidence_construction_failed"
    assert tuple(run.seed for run in persisted.completed_runs) == (persisted.plan.held_out_seeds)
    assert persisted.preparation is not None
    assert persisted.preparation.scenario_path == persisted.plan.scenario_path
    assert reported == {
        "artifact": str(output_path.relative_to(ROOT)),
        "artifact_sha256": persisted.artifact_sha256,
        "completed_runs": 1,
        "error_code": "historical_evidence_construction_failed",
        "failure_stage": "evidence_construction",
        "status": "ERROR",
    }
