"""Tamper-evident, atomically published historical backtest artifacts."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any, Literal, Mapping

from pydantic import field_validator, model_validator

from .common import (
    StrictFrozenModel,
    canonical_sha256,
    canonical_value,
    require_no_symlink_path,
    require_relative_posix_path,
    require_trimmed,
)
from .evaluator import JointCoverageEvaluation, evaluate_joint_coverage
from .runner import (
    HistoricalBacktestResult,
    HistoricalEligibility,
    HistoricalExecutionEvidence,
    HistoricalPreparationEvidence,
    HistoricalRunEvidence,
    MetricObservationReceipt,
    UnitStatusObservation,
)
from .studies import (
    HistoricalMetricPlan,
    HistoricalStudyPlan,
    RatioComponent,
    SourceLineageRelationship,
    TerminalExchangeRatioV1,
    TerminalSideActiveCountV1,
    TerminalSideDestroyedCountV1,
    TerminalWinnerIndicatorV1,
    TimeToNaturalTerminalSecondsV1,
    PredeclarationReceipt,
    predeclaration_contract_sha256,
)


class ClaimBinding(StrictFrozenModel):
    """Stable claim identity bound without a circular full-ledger digest."""

    claim_id: str
    repository_path: str
    content_sha256: str

    @field_validator("claim_id", mode="before")
    @classmethod
    def _claim_id(cls, value: Any) -> str:
        return require_trimmed(value, field_name="claim_id")

    @field_validator("repository_path", mode="before")
    @classmethod
    def _path(cls, value: Any) -> str:
        return require_relative_posix_path(
            value,
            field_name="repository_path",
        )

    @field_validator("content_sha256", mode="before")
    @classmethod
    def _digest(cls, value: Any) -> str:
        return _digest(value, field_name="content_sha256")


def _digest(value: Any, *, field_name: str) -> str:
    text = require_trimmed(value, field_name=field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _timestamp(value: Any) -> str:
    text = require_trimmed(value, field_name="created_at_utc")
    if not text.endswith("Z"):
        raise ValueError("created_at_utc must use a UTC Z suffix")
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("created_at_utc must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError("created_at_utc must be UTC")
    return text


class CompletedHistoricalArtifact(StrictFrozenModel):
    """A complete PASS/FAIL artifact whose verdict is receipt-recomputable."""

    schema_version: Literal[1]
    study_id: str
    status: Literal["PASS", "FAIL"]
    created_at_utc: str
    plan: HistoricalStudyPlan
    plan_sha256: str
    execution_ledger_path: str
    execution_ledger_sha256: str
    claim_bindings: tuple[ClaimBinding, ...]
    execution: HistoricalExecutionEvidence
    evaluation: JointCoverageEvaluation
    eligibility: HistoricalEligibility
    limitations: tuple[str, ...]
    artifact_sha256: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be the strict integer 1")
        return value

    @field_validator("created_at_utc", mode="before")
    @classmethod
    def _created(cls, value: Any) -> str:
        return _timestamp(value)

    @field_validator("execution_ledger_path", mode="before")
    @classmethod
    def _ledger_path(cls, value: Any) -> str:
        return require_relative_posix_path(
            value,
            field_name="execution_ledger_path",
        )

    @field_validator(
        "plan_sha256",
        "execution_ledger_sha256",
        "artifact_sha256",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _complete_and_recomputable(self) -> CompletedHistoricalArtifact:
        _validate_completed_artifact(self)
        expected_digest = canonical_sha256(
            self.model_dump(
                mode="json",
                exclude={"artifact_sha256"},
            ),
        )
        if self.artifact_sha256 != expected_digest:
            raise ValueError("historical artifact digest does not match")
        return self


class HistoricalErrorArtifact(StrictFrozenModel):
    """Post-start operational error evidence with no outcome verdict."""

    schema_version: Literal[1]
    study_id: str
    status: Literal["ERROR"]
    created_at_utc: str
    plan: HistoricalStudyPlan
    plan_sha256: str
    execution_ledger_path: str
    execution_ledger_sha256: str
    claim_bindings: tuple[ClaimBinding, ...]
    failure_stage: Literal[
        "runtime_preparation",
        "runtime_construction",
        "runtime_execution",
        "observation_extraction",
        "evaluation",
        "evidence_construction",
    ]
    error_code: str
    message: str
    preparation: HistoricalPreparationEvidence | None
    completed_runs: tuple[HistoricalRunEvidence, ...]
    limitations: tuple[str, ...]
    artifact_sha256: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be the strict integer 1")
        return value

    @field_validator("created_at_utc", mode="before")
    @classmethod
    def _created(cls, value: Any) -> str:
        return _timestamp(value)

    @field_validator("execution_ledger_path", mode="before")
    @classmethod
    def _ledger_path(cls, value: Any) -> str:
        return require_relative_posix_path(
            value,
            field_name="execution_ledger_path",
        )

    @field_validator(
        "plan_sha256",
        "execution_ledger_sha256",
        "artifact_sha256",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("failure_stage", "error_code", "message", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _error_consistency(self) -> HistoricalErrorArtifact:
        if self.study_id != self.plan.study_id:
            raise ValueError("error artifact study identity differs from plan")
        if self.plan_sha256 != self.plan.plan_sha256:
            raise ValueError("error artifact plan digest differs from plan")
        if tuple(binding.claim_id for binding in self.claim_bindings) != self.plan.claim_ids:
            raise ValueError("error claim bindings differ from the ordered study claims")
        if not any(binding.repository_path == self.plan.scenario_path for binding in self.claim_bindings):
            raise ValueError("error study claims do not bind the scenario")
        if self.limitations != self.plan.limitations:
            raise ValueError("error artifact limitations differ from the plan")
        if self.error_code != f"historical_{self.failure_stage}_failed":
            raise ValueError("error code differs from the failure stage")
        if self.failure_stage == "runtime_preparation":
            if self.completed_runs:
                raise ValueError("runtime preparation errors cannot contain completed runs")
        elif self.preparation is None:
            raise ValueError("post-preparation errors require preparation evidence")
        if self.preparation is not None and (
            self.preparation.scenario_path != self.plan.scenario_path
            or self.preparation.data_root != self.plan.data_root
            or self.preparation.variant_id != self.plan.analysis.variant_id
        ):
            raise ValueError("error preparation evidence differs from the study plan")
        _validate_predeclaration_receipt(
            self.plan,
            None if self.preparation is None else self.preparation.predeclaration_receipt,
        )
        if tuple(run.seed for run in self.completed_runs) != self.plan.held_out_seeds[: len(self.completed_runs)]:
            raise ValueError("error artifact completed runs are not a held-out prefix")
        metrics = self.plan.gating_metrics + self.plan.diagnostic_metrics
        first_run = self.completed_runs[0] if self.completed_runs else None
        for run in self.completed_runs:
            _validate_terminal_boundary(self.plan, run)
            if tuple(receipt.metric_id for receipt in run.receipts) != tuple(metric.metric_id for metric in metrics):
                raise ValueError("error run does not contain every ordered metric")
            if first_run is not None and (
                run.source_fingerprint != first_run.source_fingerprint
                or run.config_fingerprint != first_run.config_fingerprint
                or run.loaded_roster != first_run.loaded_roster
                or run.loaded_typed_roster != first_run.loaded_typed_roster
                or run.runtime_provenance.code_revision != first_run.runtime_provenance.code_revision
                or run.runtime_provenance.data_revision != first_run.runtime_provenance.data_revision
                or run.runtime_provenance.data_file_count != first_run.runtime_provenance.data_file_count
                or run.runtime_provenance.catalog_revision != first_run.runtime_provenance.catalog_revision
                or run.runtime_provenance.doctrine_catalog_fingerprint
                != first_run.runtime_provenance.doctrine_catalog_fingerprint
                or run.runtime_provenance.loaded_roster_loadout_fingerprint
                != first_run.runtime_provenance.loaded_roster_loadout_fingerprint
                or run.runtime_provenance.initial_unit_assignments
                != first_run.runtime_provenance.initial_unit_assignments
            ):
                raise ValueError("error run static provenance changed within the prefix")
            if self.preparation is not None and (
                run.source_fingerprint != self.preparation.source_fingerprint
                or run.config_fingerprint != self.preparation.config_fingerprint
                or run.loaded_roster != self.preparation.authored_roster
                or {
                    (unit.side, unit.unit_type): sum(
                        candidate.side == unit.side and candidate.unit_type == unit.unit_type
                        for candidate in run.loaded_typed_roster
                    )
                    for unit in run.loaded_typed_roster
                }
                != {(side, unit_type): count for side, unit_type, count in self.preparation.authored_typed_roster}
                or run.runtime_provenance.code_revision != self.preparation.code_revision
                or run.runtime_provenance.data_revision != self.preparation.data_revision
                or run.runtime_provenance.data_file_count != self.preparation.data_file_count
                or any(
                    receipt.effective_era_id != self.preparation.effective_era_id
                    or receipt.era_config_sha256 != self.preparation.era_config_sha256
                    or receipt.era_runtime_contract_sha256 != self.preparation.era_runtime_contract_sha256
                    for receipt in run.receipts
                )
            ):
                raise ValueError("error run identity differs from preparation evidence")
            if self.preparation is None:  # pragma: no cover - guarded above.
                raise ValueError("completed error runs require preparation evidence")
            for metric, receipt in zip(metrics, run.receipts, strict=True):
                _validate_receipt(
                    receipt,
                    metric,
                    run,
                    self.preparation,
                )
        expected_digest = canonical_sha256(
            self.model_dump(
                mode="json",
                exclude={"artifact_sha256"},
            ),
        )
        if self.artifact_sha256 != expected_digest:
            raise ValueError("historical error artifact digest does not match")
        return self


HistoricalArtifact = CompletedHistoricalArtifact | HistoricalErrorArtifact


def _validate_predeclaration_receipt(
    plan: HistoricalStudyPlan,
    receipt: PredeclarationReceipt | None,
) -> None:
    if receipt is None:
        return
    if (
        receipt.revision != plan.artifact_policy.predeclaration_revision
        or receipt.plan_repository_path != plan.plan_repository_path
        or receipt.contract_sha256 != predeclaration_contract_sha256(plan)
    ):
        raise ValueError("predeclaration receipt differs from the study contract")


def _validate_terminal_boundary(
    plan: HistoricalStudyPlan,
    run: HistoricalRunEvidence,
) -> None:
    terminal = run.terminal_outcome
    if terminal.duration_s > plan.observation_boundary_s or terminal.ticks_executed > plan.maximum_ticks:
        raise ValueError("terminal outcome exceeds the study boundary")
    expected_duration = plan.observation_boundary_s * terminal.ticks_executed / plan.maximum_ticks
    if terminal.duration_s != expected_duration:
        raise ValueError(
            "terminal outcome duration disagrees with logical tick cadence",
        )
    if terminal.right_censored and (
        terminal.duration_s != plan.observation_boundary_s or terminal.ticks_executed != plan.maximum_ticks
    ):
        raise ValueError("right-censored outcome does not equal the study boundary")


def _expected_selected_identities(
    run: HistoricalRunEvidence,
    *,
    side: str,
    included_unit_types: tuple[str, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (unit.unit_id, unit.unit_type, unit.side)
        for unit_type in included_unit_types
        for unit in sorted(
            (
                candidate
                for candidate in run.loaded_typed_roster
                if candidate.side == side and candidate.unit_type == unit_type
            ),
            key=lambda candidate: candidate.unit_id,
        )
    )


def _expected_eligibility(
    plan: HistoricalStudyPlan,
    execution: HistoricalExecutionEvidence,
    passed: bool,
) -> HistoricalEligibility:
    reasons: list[str] = []
    if not passed:
        reasons.append("study_failed")
    if execution.code_revision.dirty:
        reasons.append("dirty_revision")
    if plan.lineage.validation_source_relationship is SourceLineageRelationship.REUSED:
        reasons.append("validation_source_reused")
    elif plan.lineage.validation_source_relationship is SourceLineageRelationship.UNKNOWN:
        reasons.append("validation_source_lineage_unknown")
    if plan.artifact_policy.predeclaration_revision is None:
        reasons.append("plan_not_immutably_predeclared")
    elif execution.predeclaration_receipt is None:
        reasons.append("plan_predeclaration_not_repository_verified")
    return HistoricalEligibility(
        promotion_eligible=not reasons,
        reason_codes=tuple(reasons),
    )


_ReceiptIdentityEvidence = HistoricalExecutionEvidence | HistoricalPreparationEvidence
_CountComponent = RatioComponent | TerminalSideActiveCountV1 | TerminalSideDestroyedCountV1


def _validate_receipt_identity(
    receipt: MetricObservationReceipt,
    metric: HistoricalMetricPlan,
    run: HistoricalRunEvidence,
    identity: _ReceiptIdentityEvidence,
) -> None:
    extractor = metric.extractor
    terminal = run.terminal_outcome
    if (
        receipt.seed != run.seed
        or receipt.metric_id != metric.metric_id
        or receipt.extractor_id != extractor.extractor_id
        or receipt.extractor_sha256 != canonical_sha256(extractor)
        or receipt.event_boundary != extractor.event_boundary
        or receipt.runtime_unit != extractor.runtime_unit
        or receipt.source_unit != metric.source_unit
        or receipt.scale != extractor.conversion.scale
        or receipt.offset != extractor.conversion.offset
        or receipt.observation_time_s != terminal.duration_s
        or receipt.natural_terminal != terminal.natural_terminal
        or receipt.right_censored != terminal.right_censored
        or receipt.source_fingerprint != identity.source_fingerprint
        or receipt.config_fingerprint != identity.config_fingerprint
        or receipt.effective_era_id != identity.effective_era_id
        or receipt.era_config_sha256 != identity.era_config_sha256
        or receipt.era_runtime_contract_sha256 != identity.era_runtime_contract_sha256
        or receipt.terminal_outcome_sha256 != canonical_sha256(terminal)
    ):
        raise ValueError(f"receipt {receipt.metric_id!r} identity is inconsistent")


def _validate_component_scope(
    selected_units: tuple[UnitStatusObservation, ...],
    run: HistoricalRunEvidence,
    *,
    metric_id: str,
    side: str,
    included_unit_types: tuple[str, ...],
) -> None:
    observed_identities = tuple((unit.unit_id, unit.unit_type, unit.side) for unit in selected_units)
    expected_identities = _expected_selected_identities(
        run,
        side=side,
        included_unit_types=included_unit_types,
    )
    if observed_identities != expected_identities:
        raise ValueError(
            f"receipt {metric_id!r} selected scope differs from the loaded typed roster",
        )


def _count_component_observation(
    selected_units: tuple[UnitStatusObservation, ...],
    run: HistoricalRunEvidence,
    component: _CountComponent,
    *,
    metric_id: str,
) -> tuple[float, tuple[str, ...]]:
    _validate_component_scope(
        selected_units,
        run,
        metric_id=metric_id,
        side=component.side,
        included_unit_types=component.included_unit_types,
    )
    status = component.status if isinstance(component, RatioComponent) else component.statuses[0]
    counted = tuple(unit.unit_id for unit in selected_units if unit.status == status)
    return float(len(counted)), counted


def _recompute_receipt_observation(
    receipt: MetricObservationReceipt,
    metric: HistoricalMetricPlan,
    run: HistoricalRunEvidence,
) -> tuple[float, tuple[str, ...]]:
    extractor = metric.extractor
    terminal = run.terminal_outcome
    expected_counted: tuple[str, ...] = ()
    if isinstance(
        extractor,
        (TerminalSideDestroyedCountV1, TerminalSideActiveCountV1),
    ):
        raw_value, expected_counted = _count_component_observation(
            receipt.selected_units,
            run,
            extractor,
            metric_id=metric.metric_id,
        )
    elif isinstance(extractor, TimeToNaturalTerminalSecondsV1):
        raw_value = terminal.duration_s
        if receipt.selected_units or receipt.counted_unit_ids:
            raise ValueError("duration receipt must not carry unit observations")
    elif isinstance(extractor, TerminalWinnerIndicatorV1):
        raw_value = float(terminal.winning_side == extractor.side)
        if receipt.selected_units or receipt.counted_unit_ids:
            raise ValueError("winner receipt must not carry unit observations")
    elif isinstance(extractor, TerminalExchangeRatioV1):
        allowed_scopes = (
            (
                extractor.numerator.side,
                set(extractor.numerator.included_unit_types),
            ),
            (
                extractor.denominator.side,
                set(extractor.denominator.included_unit_types),
            ),
        )
        if any(
            not any(unit.side == side and unit.unit_type in unit_types for side, unit_types in allowed_scopes)
            for unit in receipt.selected_units
        ):
            raise ValueError("ratio receipt contains an out-of-scope unit")
        numerator_units = tuple(
            unit
            for unit in receipt.selected_units
            if unit.side == extractor.numerator.side and unit.unit_type in extractor.numerator.included_unit_types
        )
        denominator_units = tuple(
            unit
            for unit in receipt.selected_units
            if unit.side == extractor.denominator.side and unit.unit_type in extractor.denominator.included_unit_types
        )
        if receipt.selected_units != numerator_units + denominator_units:
            raise ValueError("ratio receipt component ordering is inconsistent")
        numerator, numerator_ids = _count_component_observation(
            numerator_units,
            run,
            extractor.numerator,
            metric_id=metric.metric_id,
        )
        denominator, denominator_ids = _count_component_observation(
            denominator_units,
            run,
            extractor.denominator,
            metric_id=metric.metric_id,
        )
        if receipt.numerator_count != numerator or receipt.denominator_count != denominator:
            raise ValueError("ratio receipt component counts are inconsistent")
        raw_value = numerator / max(1.0, denominator)
        expected_counted = numerator_ids + denominator_ids
    else:  # pragma: no cover - the plan extractor union is closed.
        raise ValueError(f"unsupported receipt extractor {extractor!r}")
    return raw_value, expected_counted


def _validate_receipt(
    receipt: MetricObservationReceipt,
    metric: HistoricalMetricPlan,
    run: HistoricalRunEvidence,
    identity: _ReceiptIdentityEvidence,
) -> None:
    _validate_receipt_identity(receipt, metric, run, identity)
    raw_value, expected_counted = _recompute_receipt_observation(
        receipt,
        metric,
        run,
    )
    extractor = metric.extractor
    value = raw_value * extractor.conversion.scale + extractor.conversion.offset
    in_range = metric.source_range.minimum <= value <= metric.source_range.maximum
    if isinstance(extractor, TimeToNaturalTerminalSecondsV1) and run.terminal_outcome.right_censored:
        in_range = False
    if (
        receipt.raw_value != raw_value
        or receipt.value != value
        or receipt.counted_unit_ids != expected_counted
        or receipt.in_source_range is not in_range
    ):
        raise ValueError(f"receipt {receipt.metric_id!r} observation is inconsistent")


def _validate_completed_artifact(artifact: CompletedHistoricalArtifact) -> None:
    plan = artifact.plan
    execution = artifact.execution
    if artifact.study_id != plan.study_id or artifact.plan_sha256 != plan.plan_sha256:
        raise ValueError("completed artifact study/plan identity differs")
    if tuple(binding.claim_id for binding in artifact.claim_bindings) != plan.claim_ids:
        raise ValueError("claim bindings differ from the ordered study claims")
    if not any(binding.repository_path == plan.scenario_path for binding in artifact.claim_bindings):
        raise ValueError("study claims do not bind the executed scenario")
    if artifact.limitations != plan.limitations:
        raise ValueError("artifact limitations differ from the plan")
    if (
        execution.scenario_path != plan.scenario_path
        or execution.data_root != plan.data_root
        or execution.seeds != plan.held_out_seeds
        or execution.maximum_ticks != plan.maximum_ticks
        or execution.observation_boundary_s != plan.observation_boundary_s
        or execution.variant_id != plan.analysis.variant_id
    ):
        raise ValueError("execution contract differs from the plan")
    _validate_predeclaration_receipt(plan, execution.predeclaration_receipt)
    metrics = plan.gating_metrics + plan.diagnostic_metrics
    if execution.ordered_metrics != tuple(metric.metric_id for metric in metrics):
        raise ValueError("execution metric order differs from the plan")
    for run in execution.runs:
        _validate_terminal_boundary(plan, run)
        for metric, receipt in zip(metrics, run.receipts, strict=True):
            _validate_receipt(receipt, metric, run, execution)
    metric_in_range = tuple(
        (
            metric.metric_id,
            tuple(run.receipts[index].in_source_range for run in execution.runs),
        )
        for index, metric in enumerate(plan.gating_metrics)
    )
    expected_evaluation = evaluate_joint_coverage(
        metric_in_range=metric_in_range,
        confidence=plan.acceptance_policy.confidence,
        minimum_joint_coverage=plan.acceptance_policy.minimum_joint_coverage,
    )
    if artifact.evaluation != expected_evaluation:
        raise ValueError("artifact evaluation differs from recomputed receipts")
    expected_status = "PASS" if expected_evaluation.passed else "FAIL"
    if artifact.status != expected_status:
        raise ValueError("artifact status differs from recomputed verdict")
    if artifact.eligibility != _expected_eligibility(
        plan,
        execution,
        expected_evaluation.passed,
    ):
        raise ValueError("artifact eligibility differs from its evidence")


def _utc_text(now: datetime | None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() != timezone.utc.utcoffset(current):
        raise ValueError("artifact clock must be timezone-aware UTC")
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def create_completed_artifact(
    *,
    plan: HistoricalStudyPlan,
    result: HistoricalBacktestResult,
    execution_ledger_path: str,
    execution_ledger_sha256: str,
    claim_bindings: tuple[ClaimBinding, ...],
    now: datetime | None = None,
) -> CompletedHistoricalArtifact:
    """Build and fully revalidate one completed artifact."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "study_id": plan.study_id,
        "status": result.status,
        "created_at_utc": _utc_text(now),
        "plan": plan.model_dump(mode="json", exclude_none=False),
        "plan_sha256": result.plan_sha256,
        "execution_ledger_path": execution_ledger_path,
        "execution_ledger_sha256": execution_ledger_sha256,
        "claim_bindings": [binding.model_dump(mode="json") for binding in claim_bindings],
        "execution": result.execution.model_dump(mode="json"),
        "evaluation": result.evaluation.model_dump(mode="json"),
        "eligibility": result.eligibility.model_dump(mode="json"),
        "limitations": list(plan.limitations),
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    return CompletedHistoricalArtifact.model_validate(payload)


def create_error_artifact(
    *,
    plan: HistoricalStudyPlan,
    execution_ledger_path: str,
    execution_ledger_sha256: str,
    claim_bindings: tuple[ClaimBinding, ...],
    failure_stage: str,
    error_code: str,
    message: str,
    preparation: HistoricalPreparationEvidence | None,
    completed_runs: tuple[HistoricalRunEvidence, ...],
    now: datetime | None = None,
) -> HistoricalErrorArtifact:
    """Build typed post-start error evidence without a verdict field."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "study_id": plan.study_id,
        "status": "ERROR",
        "created_at_utc": _utc_text(now),
        "plan": plan.model_dump(mode="json", exclude_none=False),
        "plan_sha256": plan.plan_sha256,
        "execution_ledger_path": execution_ledger_path,
        "execution_ledger_sha256": execution_ledger_sha256,
        "claim_bindings": [binding.model_dump(mode="json") for binding in claim_bindings],
        "failure_stage": failure_stage,
        "error_code": error_code,
        "message": message,
        "preparation": (None if preparation is None else preparation.model_dump(mode="json")),
        "completed_runs": [run.model_dump(mode="json") for run in completed_runs],
        "limitations": list(plan.limitations),
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    return HistoricalErrorArtifact.model_validate(payload)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_historical_artifact(path: Path) -> HistoricalArtifact:
    """Load, digest-check, and semantically recompute one artifact."""
    require_no_symlink_path(path, field_name="historical artifact path")
    raw = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON constant {value!r}"),
        ),
    )
    if not isinstance(raw, Mapping):
        raise ValueError("historical artifact root must be a mapping")
    canonical_value(raw)
    status = raw.get("status")
    if status == "ERROR":
        return HistoricalErrorArtifact.model_validate(raw)
    if status in {"PASS", "FAIL"}:
        return CompletedHistoricalArtifact.model_validate(raw)
    raise ValueError(f"unsupported historical artifact status {status!r}")


def write_historical_artifact(
    path: Path,
    artifact: HistoricalArtifact,
) -> HistoricalArtifact:
    """Atomically publish, reload, and compare one complete artifact."""
    require_no_symlink_path(path, field_name="historical artifact path")
    target = path.absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    require_no_symlink_path(target, field_name="historical artifact path")
    serialized = (
        json.dumps(
            artifact.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        staged = load_historical_artifact(temporary_path)
        if staged != artifact:
            raise RuntimeError("staged historical artifact changed on reload")
        os.replace(temporary_path, target)
        temporary_path = None
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_descriptor = os.open(target.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        loaded = load_historical_artifact(target)
        if loaded != artifact:
            raise RuntimeError("published historical artifact changed on reload")
        return loaded
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
