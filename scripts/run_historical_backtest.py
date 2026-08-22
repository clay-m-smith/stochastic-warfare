"""Execute one strict production historical backtest and publish its artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.validation.historical_backtest import (
    ClaimBinding,
    HistoricalBacktestRunner,
    HistoricalClaimLedgerLoader,
    HistoricalExecutionError,
    HistoricalStudyLoader,
    create_completed_artifact,
    create_error_artifact,
    write_historical_artifact,
)
from stochastic_warfare.validation.historical_backtest.common import (
    require_no_symlink_path,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data/validation/historical_claims.yaml"
DEFAULT_PLAN = ROOT / "data/validation/historical_studies/73_easting_phase117.yaml"
EVIDENCE_OUTPUT_ROOT = ROOT / "artifacts/evidence/phase-117"
DEFAULT_OUTPUT = EVIDENCE_OUTPUT_ROOT / "73-easting-phase117.json"


def _within_repository(path: Path, *, field_name: str) -> Path:
    require_no_symlink_path(path, field_name=field_name)
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"{field_name} must remain within the repository")
    return resolved


def _artifact_output(path: Path) -> Path:
    resolved = _within_repository(path, field_name="output")
    evidence_root = (ROOT / "artifacts/evidence/phase-117").resolve()
    if not resolved.is_relative_to(evidence_root) or resolved.suffix != ".json":
        raise ValueError(
            "output must be a JSON file below artifacts/evidence/phase-117",
        )
    return resolved


def main() -> int:
    """Run the predeclared study; FAIL is completed evidence, ERROR is not."""
    parser = argparse.ArgumentParser(
        description="Run a typed production historical backtest",
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    ledger_path = _within_repository(args.ledger, field_name="ledger")
    plan_path = _within_repository(args.plan, field_name="plan")
    output_path = _artifact_output(args.output)
    execution_ledger_path = ledger_path.relative_to(ROOT).as_posix()
    ledger = HistoricalClaimLedgerLoader(ROOT).load(ledger_path)
    plan = HistoricalStudyLoader(ROOT).load(plan_path)
    bindings = tuple(
        ClaimBinding(
            claim_id=claim.claim_id,
            repository_path=claim.repository_path,
            content_sha256=claim.content_sha256,
        )
        for claim in (ledger.claim_by_id(claim_id) for claim_id in plan.claim_ids)
    )
    try:
        prepared = SimulationRuntimeFactory().prepare(
            ROOT / plan.scenario_path,
            ROOT / plan.data_root,
            (
                AnalysisVariant(
                    variant_id=plan.analysis.variant_id,
                    calibration_patch=plan.analysis.calibration_patch,
                ),
            ),
        )
        runner = HistoricalBacktestRunner(prepared, plan)
        result = runner.run()
    except HistoricalExecutionError as exc:
        artifact = create_error_artifact(
            plan=plan,
            execution_ledger_path=execution_ledger_path,
            execution_ledger_sha256=ledger.ledger_sha256,
            claim_bindings=bindings,
            failure_stage=exc.failure_stage,
            error_code=exc.error_code,
            message=str(exc),
            preparation=exc.preparation,
            completed_runs=exc.completed_runs,
        )
    except Exception as exc:
        message = " ".join(str(exc).split())[:1000] or type(exc).__name__
        artifact = create_error_artifact(
            plan=plan,
            execution_ledger_path=execution_ledger_path,
            execution_ledger_sha256=ledger.ledger_sha256,
            claim_bindings=bindings,
            failure_stage="runtime_preparation",
            error_code="historical_runtime_preparation_failed",
            message=message,
            preparation=None,
            completed_runs=(),
        )
    else:
        try:
            artifact = create_completed_artifact(
                plan=plan,
                result=result,
                execution_ledger_path=execution_ledger_path,
                execution_ledger_sha256=ledger.ledger_sha256,
                claim_bindings=bindings,
            )
            prepared.assert_source_identity(
                stage="before historical artifact publication",
            )
        except Exception as exc:
            message = " ".join(str(exc).split())[:1000] or type(exc).__name__
            artifact = create_error_artifact(
                plan=plan,
                execution_ledger_path=execution_ledger_path,
                execution_ledger_sha256=ledger.ledger_sha256,
                claim_bindings=bindings,
                failure_stage="evidence_construction",
                error_code="historical_evidence_construction_failed",
                message=message,
                preparation=runner.preparation,
                completed_runs=result.execution.runs,
            )

    persisted = write_historical_artifact(output_path, artifact)
    if persisted.status == "ERROR":
        print(
            json.dumps(
                {
                    "artifact": str(output_path.relative_to(ROOT)),
                    "artifact_sha256": persisted.artifact_sha256,
                    "completed_runs": len(persisted.completed_runs),
                    "error_code": persisted.error_code,
                    "failure_stage": persisted.failure_stage,
                    "status": persisted.status,
                },
                sort_keys=True,
            ),
        )
        return 2

    print(
        json.dumps(
            {
                "artifact": str(output_path.relative_to(ROOT)),
                "artifact_sha256": persisted.artifact_sha256,
                "joint_successes": persisted.evaluation.joint_successes,
                "lower_confidence_bound": (persisted.evaluation.lower_confidence_bound),
                "promotion_eligible": (persisted.eligibility.promotion_eligible),
                "runs": len(persisted.execution.runs),
                "status": persisted.status,
            },
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
