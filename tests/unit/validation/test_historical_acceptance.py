"""Production-backed acceptance proof for Phase 117 historical evidence."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

import pytest
import yaml

import stochastic_warfare.simulation.runtime as runtime_module
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    RuntimeSession,
    SimulationRuntimeFactory,
)
from stochastic_warfare.validation.historical_backtest.artifacts import (
    ClaimBinding,
    CompletedHistoricalArtifact,
    create_completed_artifact,
    create_error_artifact,
    load_historical_artifact,
    write_historical_artifact,
)
from stochastic_warfare.validation.historical_backtest.claims import (
    ClaimSourceKind,
    ClaimDisposition,
    HistoricalClaimLedgerLoader,
    scan_historical_claim_sources,
)
from stochastic_warfare.validation.historical_backtest.common import (
    canonical_sha256,
)
from stochastic_warfare.validation.historical_backtest.runner import (
    HistoricalBacktestResult,
    HistoricalBacktestRunner,
    HistoricalExecutionError,
)
from stochastic_warfare.validation.historical_backtest.studies import (
    HistoricalMetricPlan,
    HistoricalStudyPlan,
    HistoricalStudyLoader,
)


ROOT = Path(__file__).resolve().parents[3]
SCENARIO_RELATIVE = "data/eras/ancient_medieval/scenarios/agincourt/scenario.yaml"
CROSS_SCENARIO_RELATIVE = "data/eras/ancient_medieval/scenarios/hastings/scenario.yaml"
PLAN_RELATIVE = "data/validation/historical_studies/acceptance_fixture.yaml"
LEDGER_RELATIVE = "data/validation/historical_claims.yaml"
ARTIFACT_RELATIVE = "docs/evidence/phase-117/acceptance-fixture.json"
CLAIM_ID = "scenario.agincourt.acceptance-fixture"
CROSS_SCENARIO_CLAIM_ID = "scenario.hastings.cross-scenario-fixture"
STUDY_ID = "agincourt.phase117.acceptance-fixture.v1"
CLAIM_METRICS = (
    "english_active_entities_after_one_tick",
    "french_active_entities_after_one_tick",
)
GATING_METRICS = CLAIM_METRICS
DIAGNOSTIC_METRIC = "english_winner_diagnostic"
EVENT_SCOPE = "One exact production tactical tick from scenario start."
INTENDED_USE = (
    "Verify the repository's production historical-evidence acceptance "
    "boundary for an independently predeclared one-tick integration fixture."
)
FIXED_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

Payload = dict[str, Any]
ArtifactMutation = Callable[[Payload], None]


@dataclass(frozen=True, slots=True)
class AcceptanceRepositoryFixture:
    """Immutable handles for one accepted production execution chain."""

    repository: Path
    artifact: CompletedHistoricalArtifact
    plan: HistoricalStudyPlan
    result: HistoricalBacktestResult
    content_sha256: str
    execution_ledger_sha256: str
    predeclaration_revision: str
    execution_revision: str
    acceptance_revision: str


def _git(
    repository: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout.strip()


def _commit(
    repository: Path,
    message: str,
    *,
    timestamp: str,
) -> str:
    _git(repository, "add", "--all")
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
        },
    )
    _git(repository, "commit", "--quiet", "-m", message, environment=environment)
    return _git(repository, "rev-parse", "HEAD")


def _assert_clean(repository: Path) -> None:
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == ""


def _copy_repository_inputs(repository: Path) -> None:
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(ROOT / "data", repository / "data", ignore=ignored)
    shutil.copytree(
        ROOT / "stochastic_warfare",
        repository / "stochastic_warfare",
        ignore=ignored,
    )
    api_package = repository / "api"
    api_package.mkdir()
    shutil.copy2(ROOT / "api/__init__.py", api_package / "__init__.py")
    script = repository / "scripts/run_historical_backtest.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/run_historical_backtest.py", script)
    shutil.copy2(ROOT / "pyproject.toml", repository / "pyproject.toml")
    shutil.copy2(ROOT / "uv.lock", repository / "uv.lock")
    for scenario_path in sorted((repository / "data").rglob("scenario.yaml")):
        relative = scenario_path.relative_to(repository).as_posix()
        if relative == SCENARIO_RELATIVE:
            continue
        payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.pop("documented_outcomes", None) is not None:
            scenario_path.write_text(
                yaml.safe_dump(payload, sort_keys=False),
                encoding="utf-8",
            )


def _write_yaml(path: Path, payload: Payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _plan_payload(*, predeclaration_revision: str | None) -> Payload:
    return {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "plan_repository_path": PLAN_RELATIVE,
        "claim_ids": [CLAIM_ID, CROSS_SCENARIO_CLAIM_ID],
        "scenario_path": SCENARIO_RELATIVE,
        "data_root": "data",
        "intended_use": INTENDED_USE,
        "limitations": [
            "This one-tick integration fixture is not battle-fidelity or predictive evidence.",
        ],
        "sources": [
            {
                "source_id": "acceptance_fixture_source",
                "url": "https://example.invalid/phase117-acceptance-fixture",
                "citation": "Phase 117 production acceptance integration fixture.",
                "quality": "tertiary",
                "locator": "Test-only claim marker in the copied Agincourt scenario.",
                "accessed_on": "2026-08-02",
                "supported_assertion": (
                    "The copied scenario's exact initial English and French "
                    "entity scopes remain observable after one tactical tick."
                ),
                "conflict_notes": [
                    "This source supports integration plumbing only, not a historical outcome claim.",
                ],
            },
        ],
        "lineage": {
            "validation_source_relationship": "independent",
            "source_uses": [
                {
                    "source_id": "acceptance_fixture_source",
                    "usage": "diagnostic_only",
                    "details": ("The test-only source is not used to author or calibrate production data."),
                },
            ],
            "training_seed_intervals": [],
            "diagnostic_seed_intervals": [],
            "notes": [
                "The fixture has no training or calibration seed lineage.",
            ],
        },
        "held_out_seed_interval": {"first": 31700, "last": 31700},
        "observation_boundary_s": 5.0,
        "maximum_ticks": 1,
        "analysis": {
            "variant_id": "phase117_acceptance_fixture",
            "calibration_patch": {},
        },
        "acceptance_policy": {
            "confidence": 0.95,
            "minimum_joint_coverage": 0.01,
        },
        "gating_metrics": [
            {
                "metric_id": GATING_METRICS[0],
                "name": "English entities active after one tactical tick",
                "source_ids": ["acceptance_fixture_source"],
                "source_range": {"minimum": 0.0, "maximum": 5.0},
                "source_unit": "entity_count",
                "source_event_boundary": EVENT_SCOPE,
                "range_rationale": ("The exact authored English scope contains five initial entities."),
                "extractor": {
                    "extractor_id": "terminal_side_active_count.v1",
                    "event_boundary": "source_synchronous_cutoff",
                    "side": "english",
                    "statuses": ["ACTIVE"],
                    "included_unit_types": [
                        "english_longbowman",
                        "viking_huscarl",
                    ],
                    "roster_scope": "initial_only",
                    "runtime_unit": "entity_count",
                    "conversion": {"scale": 1.0, "offset": 0.0},
                },
            },
            {
                "metric_id": GATING_METRICS[1],
                "name": "French entities active after one tactical tick",
                "source_ids": ["acceptance_fixture_source"],
                "source_range": {"minimum": 0.0, "maximum": 4.0},
                "source_unit": "entity_count",
                "source_event_boundary": EVENT_SCOPE,
                "range_rationale": ("The exact authored French scope contains four initial entities."),
                "extractor": {
                    "extractor_id": "terminal_side_active_count.v1",
                    "event_boundary": "source_synchronous_cutoff",
                    "side": "french",
                    "statuses": ["ACTIVE"],
                    "included_unit_types": [
                        "norman_knight_conroi",
                        "viking_huscarl",
                    ],
                    "roster_scope": "initial_only",
                    "runtime_unit": "entity_count",
                    "conversion": {"scale": 1.0, "offset": 0.0},
                },
            },
        ],
        "diagnostic_metrics": [
            {
                "metric_id": DIAGNOSTIC_METRIC,
                "name": "English public winner diagnostic",
                "source_ids": ["acceptance_fixture_source"],
                "source_range": {"minimum": 0.0, "maximum": 1.0},
                "source_unit": "indicator",
                "source_event_boundary": EVENT_SCOPE,
                "range_rationale": "Winner is diagnostic and cannot affect acceptance.",
                "extractor": {
                    "extractor_id": "terminal_winner_indicator.v1",
                    "event_boundary": "source_synchronous_cutoff",
                    "side": "english",
                    "runtime_unit": "indicator",
                    "conversion": {"scale": 1.0, "offset": 0.0},
                },
            },
        ],
        "artifact_policy": {
            "clean_revision_required_for_promotion": True,
            "immutable_predeclaration_required_for_promotion": True,
            "predeclaration_revision": predeclaration_revision,
        },
    }


def _documented_outcomes(plan_payload: Payload) -> list[Payload]:
    values = (5.0, 4.0)
    outcomes: list[Payload] = []
    for claim_metric, study_metric, value in zip(
        CLAIM_METRICS,
        plan_payload["gating_metrics"],
        values,
        strict=True,
    ):
        metric_contract = HistoricalMetricPlan.model_validate(study_metric)
        outcomes.append(
            {
                "name": claim_metric,
                "value": value,
                "tolerance_factor": 1.0,
                "unit": metric_contract.source_unit,
                "source": "Phase 117 production acceptance integration fixture.",
                "source_quality": 2,
                "notes": ("Test-only typed claim contract; not battle-fidelity evidence."),
                "production_validation_metric": metric_contract.model_dump(
                    mode="json",
                ),
            },
        )
    return outcomes


def _claim_content_sha256(outcomes: list[Payload]) -> str:
    return canonical_sha256(
        {
            "kind": "yaml_path",
            "segments": ["documented_outcomes"],
            "content": outcomes,
        },
    )


def _accepted_bindings() -> list[Payload]:
    return [
        {
            "claim_metric": claim_metric,
            "study_metric_id": study_metric,
        }
        for claim_metric, study_metric in zip(
            CLAIM_METRICS,
            GATING_METRICS,
            strict=True,
        )
    ]


def _ledger_payload(
    *,
    content_sha256: str,
    accepted_artifact_path: str | None = None,
    accepted_artifact_sha256: str | None = None,
    metric_bindings: list[Payload] | None = None,
    accept_cross_scenario: bool = False,
) -> Payload:
    accepted = accepted_artifact_path is not None
    if accepted != (accepted_artifact_sha256 is not None):
        raise ValueError("accepted artifact path and digest must appear together")
    if accept_cross_scenario and not accepted:
        raise ValueError("cross-scenario acceptance requires an artifact")

    def claim_payload(
        *,
        claim_id: str,
        scenario_path: str,
        is_accepted: bool,
    ) -> Payload:
        return {
            "claim_id": claim_id,
            "repository_path": scenario_path,
            "scenario_path": scenario_path,
            "surface": "scenario_documented_outcomes",
            "locator": {
                "kind": "yaml_path",
                "segments": ["documented_outcomes"],
            },
            "content_sha256": content_sha256,
            "disposition": ("production_validated" if is_accepted else "unsupported"),
            "metric_scope": list(CLAIM_METRICS),
            "reason_codes": [
                "explicit_acceptance" if is_accepted else "acceptance_pending",
            ],
            "limitation": ("Integration evidence only; no historical or predictive inference."),
            "current_engine_regression_evidence": False,
            "accepted_evidence": (
                {
                    "study_id": STUDY_ID,
                    "artifact_path": accepted_artifact_path,
                    "artifact_sha256": accepted_artifact_sha256,
                    "metric_bindings": (_accepted_bindings() if metric_bindings is None else metric_bindings),
                }
                if is_accepted
                else None
            ),
        }

    payload: Payload = {
        "schema_version": 2,
        "ledger_id": "phase117.acceptance-fixture.v2",
        "claim_source_scanner_version": 3,
        "claim_source_reviews": [],
        "claims": [
            claim_payload(
                claim_id=CLAIM_ID,
                scenario_path=SCENARIO_RELATIVE,
                is_accepted=accepted and not accept_cross_scenario,
            ),
            claim_payload(
                claim_id=CROSS_SCENARIO_CLAIM_ID,
                scenario_path=CROSS_SCENARIO_RELATIVE,
                is_accepted=accepted and accept_cross_scenario,
            ),
        ],
    }
    payload["ledger_sha256"] = canonical_sha256(payload)
    return payload


def _write_ledger(
    path: Path,
    *,
    content_sha256: str,
    accepted_artifact_path: str | None = None,
    accepted_artifact_sha256: str | None = None,
    metric_bindings: list[Payload] | None = None,
    accept_cross_scenario: bool = False,
) -> Payload:
    payload = _ledger_payload(
        content_sha256=content_sha256,
        accepted_artifact_path=accepted_artifact_path,
        accepted_artifact_sha256=accepted_artifact_sha256,
        metric_bindings=metric_bindings,
        accept_cross_scenario=accept_cross_scenario,
    )
    repository = path.parents[2]
    claims_by_path = {claim["repository_path"]: claim["claim_id"] for claim in payload["claims"]}
    candidate_groups: dict[tuple[str, str], list[Any]] = {}
    for candidate in scan_historical_claim_sources(
        repository,
        source_kinds=frozenset({ClaimSourceKind.SCENARIO_YAML}),
    ):
        candidate_payload = candidate.model_dump(mode="json")
        identity = (
            candidate.source_kind.value,
            canonical_sha256(candidate_payload["matches"]),
        )
        candidate_groups.setdefault(identity, []).append(candidate)
    reviews: list[Payload] = []
    for candidates in candidate_groups.values():
        review = candidates[0].model_dump(mode="json")
        review.pop("repository_path")
        review["source_occurrences"] = len(candidates)
        claim_ids = sorted(
            claim_id
            for candidate in candidates
            if (claim_id := claims_by_path.get(candidate.repository_path)) is not None
        )
        review["claim_ids"] = claim_ids
        review["exclusion"] = (
            {
                "reason_code": "military_historical_fact",
                "rationale": (
                    "The copied fixture source contains military history or "
                    "modeling context, not an accepted simulation outcome claim."
                ),
            }
            if not claim_ids
            else None
        )
        reviews.append(review)
    reviews.sort(
        key=lambda review: (
            review["source_kind"],
            canonical_sha256(review["matches"]),
        ),
    )
    payload["claim_source_reviews"] = reviews
    payload["ledger_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "ledger_sha256"},
    )
    _write_yaml(path, payload)
    return payload


def _mutated_artifact(
    repository: Path,
    artifact: CompletedHistoricalArtifact,
    *,
    name: str,
    mutate: ArtifactMutation,
) -> tuple[str, CompletedHistoricalArtifact]:
    payload = deepcopy(artifact.model_dump(mode="json", exclude_none=False))
    mutate(payload)
    payload["artifact_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"},
    )
    validated = CompletedHistoricalArtifact.model_validate(payload)
    relative_path = f"docs/evidence/negative-{name}.json"
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            validated.model_dump(mode="json", exclude_none=False),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    assert load_historical_artifact(path) == validated
    return relative_path, validated


def _clone_repository(
    source: Path,
    destination: Path,
) -> Path:
    subprocess.run(
        ["git", "clone", "--quiet", "--local", str(source), str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(destination, "config", "user.name", "Phase 117 Acceptance Fixture")
    _git(destination, "config", "user.email", "phase117@example.invalid")
    _assert_clean(destination)
    return destination


def _write_negative_ledger(
    repository: Path,
    *,
    content_sha256: str,
    artifact_path: str,
    artifact_sha256: str,
    metric_bindings: list[Payload] | None = None,
    accept_cross_scenario: bool = False,
) -> Path:
    path = repository / LEDGER_RELATIVE
    _write_ledger(
        path,
        content_sha256=content_sha256,
        accepted_artifact_path=artifact_path,
        accepted_artifact_sha256=artifact_sha256,
        metric_bindings=metric_bindings,
        accept_cross_scenario=accept_cross_scenario,
    )
    return path


def _build_acceptance_repository(
    repository: Path,
) -> AcceptanceRepositoryFixture:
    _copy_repository_inputs(repository)
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "Phase 117 Acceptance Fixture")
    _git(repository, "config", "user.email", "phase117@example.invalid")

    plan_payload = _plan_payload(predeclaration_revision=None)
    documented_outcomes = _documented_outcomes(plan_payload)
    for scenario_relative in (SCENARIO_RELATIVE, CROSS_SCENARIO_RELATIVE):
        scenario_path = repository / scenario_relative
        scenario_payload = yaml.safe_load(
            scenario_path.read_text(encoding="utf-8"),
        )
        assert isinstance(scenario_payload, dict)
        scenario_payload["documented_outcomes"] = documented_outcomes
        _write_yaml(scenario_path, scenario_payload)
    plan_path = repository / PLAN_RELATIVE
    ledger_path = repository / LEDGER_RELATIVE
    content_sha256 = _claim_content_sha256(documented_outcomes)
    _write_yaml(plan_path, plan_payload)
    execution_ledger_payload = _write_ledger(
        ledger_path,
        content_sha256=content_sha256,
    )
    base_revision = _commit(
        repository,
        "Predeclare production acceptance fixture",
        timestamp="2026-08-02T12:00:00+00:00",
    )

    _write_yaml(
        plan_path,
        _plan_payload(predeclaration_revision=base_revision),
    )
    execution_revision = _commit(
        repository,
        "Bind predeclaration revision for clean execution",
        timestamp="2026-08-02T12:01:00+00:00",
    )
    assert base_revision != execution_revision
    _git(repository, "merge-base", "--is-ancestor", base_revision, execution_revision)
    _assert_clean(repository)

    execution_ledger = HistoricalClaimLedgerLoader(repository).load(ledger_path)
    plan = HistoricalStudyLoader(repository).load(plan_path)
    assert plan.promotion_eligible is True
    assert plan.predeclaration_receipt is not None
    assert plan.predeclaration_receipt.revision == base_revision
    assert execution_ledger.ledger_sha256 == execution_ledger_payload["ledger_sha256"]

    prepared = SimulationRuntimeFactory().prepare(
        repository / plan.scenario_path,
        repository / plan.data_root,
        (
            AnalysisVariant(
                variant_id=plan.analysis.variant_id,
                calibration_patch=plan.analysis.calibration_patch,
            ),
        ),
    )
    assert prepared.code_revision.commit == execution_revision
    assert prepared.code_revision.dirty is False
    result = HistoricalBacktestRunner(prepared, plan).run()
    assert result.status == "PASS"
    assert result.evaluation.joint_successes == 1
    assert result.evaluation.passed is True
    assert result.eligibility.promotion_eligible is True
    assert result.eligibility.reason_codes == ()
    assert result.execution.code_revision.commit == execution_revision

    artifact = create_completed_artifact(
        plan=plan,
        result=result,
        execution_ledger_path=LEDGER_RELATIVE,
        execution_ledger_sha256=execution_ledger.ledger_sha256,
        claim_bindings=tuple(
            ClaimBinding(
                claim_id=execution_claim.claim_id,
                repository_path=execution_claim.repository_path,
                content_sha256=execution_claim.content_sha256,
            )
            for execution_claim in (execution_ledger.claim_by_id(claim_id) for claim_id in plan.claim_ids)
        ),
        now=FIXED_TIME,
    )
    artifact_path = repository / ARTIFACT_RELATIVE
    persisted = write_historical_artifact(artifact_path, artifact)
    assert persisted == artifact
    assert load_historical_artifact(artifact_path) == artifact

    _write_ledger(
        ledger_path,
        content_sha256=content_sha256,
        accepted_artifact_path=ARTIFACT_RELATIVE,
        accepted_artifact_sha256=artifact.artifact_sha256,
    )
    acceptance_revision = _commit(
        repository,
        "Accept reload-validated production evidence",
        timestamp="2026-08-02T12:02:00+00:00",
    )
    assert acceptance_revision not in {base_revision, execution_revision}
    _git(repository, "merge-base", "--is-ancestor", execution_revision, acceptance_revision)
    assert _git(repository, "show", f"{acceptance_revision}:{ARTIFACT_RELATIVE}")
    assert _git(repository, "show", f"{acceptance_revision}:{LEDGER_RELATIVE}")
    _assert_clean(repository)

    return AcceptanceRepositoryFixture(
        repository=repository,
        artifact=artifact,
        plan=plan,
        result=result,
        content_sha256=content_sha256,
        execution_ledger_sha256=execution_ledger.ledger_sha256,
        predeclaration_revision=base_revision,
        execution_revision=execution_revision,
        acceptance_revision=acceptance_revision,
    )


@pytest.fixture(scope="module")
def acceptance_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[AcceptanceRepositoryFixture]:
    """Build one production run that every acceptance case reads or clones."""

    repository = tmp_path_factory.mktemp("phase117-acceptance-repository")
    imported_runtime = repository / "stochastic_warfare/simulation/runtime.py"
    with pytest.MonkeyPatch.context() as monkeypatch:
        # Model an isolated import from the synthetic checkout. Production still
        # resolves code identity from runtime.py; data_root remains data-only.
        monkeypatch.setattr(runtime_module, "__file__", str(imported_runtime))
        yield _build_acceptance_repository(repository)


def _clone_acceptance_case(
    fixture: AcceptanceRepositoryFixture,
    tmp_path: Path,
    name: str,
) -> Path:
    _assert_clean(fixture.repository)
    return _clone_repository(fixture.repository, tmp_path / name)


def test_clean_repository_accepts_reload_validated_production_evidence(
    acceptance_repository: AcceptanceRepositoryFixture,
) -> None:
    fixture = acceptance_repository
    repository = fixture.repository
    artifact = fixture.artifact

    assert fixture.predeclaration_revision != fixture.execution_revision
    assert fixture.acceptance_revision not in {
        fixture.predeclaration_revision,
        fixture.execution_revision,
    }
    assert fixture.plan.promotion_eligible is True
    assert fixture.plan.predeclaration_receipt is not None
    assert fixture.plan.predeclaration_receipt.revision == fixture.predeclaration_revision
    assert artifact.execution_ledger_sha256 == fixture.execution_ledger_sha256
    assert artifact.execution.code_revision.commit == fixture.execution_revision
    assert artifact.execution.code_revision.dirty is False
    assert fixture.result.status == "PASS"
    assert fixture.result.evaluation.joint_successes == 1
    assert fixture.result.evaluation.passed is True
    assert fixture.result.eligibility.promotion_eligible is True
    assert fixture.result.eligibility.reason_codes == ()
    assert fixture.result.execution.code_revision.commit == fixture.execution_revision
    assert load_historical_artifact(repository / ARTIFACT_RELATIVE) == artifact

    accepted_ledger = HistoricalClaimLedgerLoader(repository).load(
        repository / LEDGER_RELATIVE,
    )
    accepted_claim = accepted_ledger.claim_by_id(CLAIM_ID)
    assert accepted_claim.disposition is ClaimDisposition.PRODUCTION_VALIDATED
    assert accepted_claim.accepted_evidence is not None
    assert tuple(
        (binding.claim_metric, binding.study_metric_id) for binding in accepted_claim.accepted_evidence.metric_bindings
    ) == tuple(zip(CLAIM_METRICS, GATING_METRICS, strict=True))

    summary = accepted_ledger.scenario_summary(repository / SCENARIO_RELATIVE)
    assert summary.aggregate_disposition is ClaimDisposition.PRODUCTION_VALIDATED
    assert summary.accepted_claim_ids == (CLAIM_ID,)
    assert len(summary.claims) == 1
    assert summary.claims[0].intended_use == INTENDED_USE
    assert summary.claims[0].event_scope == EVENT_SCOPE
    assert summary.claims[0].metric_scope == CLAIM_METRICS
    assert summary.claims[0].current_engine_regression_evidence is False
    assert summary.claims[0].accepted_study_id == STUDY_ID
    assert summary.claims[0].accepted_artifact_path == ARTIFACT_RELATIVE
    cross_summary = accepted_ledger.scenario_summary(
        repository / CROSS_SCENARIO_RELATIVE,
    )
    assert cross_summary.aggregate_disposition is ClaimDisposition.UNSUPPORTED
    assert cross_summary.accepted_claim_ids == ()
    _assert_clean(repository)


@pytest.mark.test_evidence("behavioral_oracle")
def test_final_held_out_run_source_drift_is_a_durable_error(
    acceptance_repository: AcceptanceRepositoryFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _clone_acceptance_case(
        acceptance_repository,
        tmp_path,
        "final-run-source-drift",
    )
    plan = HistoricalStudyLoader(repository).load(repository / PLAN_RELATIVE)
    prepared = SimulationRuntimeFactory().prepare(
        repository / plan.scenario_path,
        repository / plan.data_root,
        (
            AnalysisVariant(
                variant_id=plan.analysis.variant_id,
                calibration_patch=plan.analysis.calibration_patch,
            ),
        ),
    )
    assert prepared.code_revision.dirty is False
    original_run = RuntimeSession.run_to_completion
    drift_path = repository / "stochastic_warfare/simulation/runtime.py"
    drift_marker = "# Post-execution imported-source drift fixture."
    monkeypatch.setattr(runtime_module, "__file__", str(drift_path))

    def run_then_drift(self: RuntimeSession):
        result = original_run(self)
        drift_path.write_text(
            drift_path.read_text(encoding="utf-8")
            + f"\n{drift_marker}\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(RuntimeSession, "run_to_completion", run_then_drift)

    with pytest.raises(
        HistoricalExecutionError,
        match="code changed after runtime execution and observation",
    ) as captured:
        HistoricalBacktestRunner(prepared, plan).run()

    error = captured.value
    artifact = create_error_artifact(
        plan=plan,
        execution_ledger_path=LEDGER_RELATIVE,
        execution_ledger_sha256="a" * 64,
        claim_bindings=tuple(
            ClaimBinding(
                claim_id=claim_id,
                repository_path=plan.scenario_path,
                content_sha256="b" * 64,
            )
            for claim_id in plan.claim_ids
        ),
        failure_stage=error.failure_stage,
        error_code=error.error_code,
        message=str(error),
        preparation=error.preparation,
        completed_runs=error.completed_runs,
        now=FIXED_TIME,
    )
    persisted = write_historical_artifact(
        tmp_path / "final-run-source-drift-error.json",
        artifact,
    )

    assert error.failure_stage == "observation_extraction"
    assert error.completed_runs == ()
    assert persisted.status == "ERROR"
    assert drift_path.read_text(encoding="utf-8").endswith(
        f"\n{drift_marker}\n",
    )


def test_rejects_cross_scenario_claim_promotion(
    acceptance_repository: AcceptanceRepositoryFixture,
    tmp_path: Path,
) -> None:
    repository = _clone_acceptance_case(
        acceptance_repository,
        tmp_path,
        "cross-scenario-promotion",
    )
    ledger_path = _write_negative_ledger(
        repository,
        content_sha256=acceptance_repository.content_sha256,
        artifact_path=ARTIFACT_RELATIVE,
        artifact_sha256=acceptance_repository.artifact.artifact_sha256,
        accept_cross_scenario=True,
    )
    _commit(
        repository,
        "Reject cross-scenario evidence promotion",
        timestamp="2026-08-02T12:09:00+00:00",
    )

    with pytest.raises(ValueError, match="executed a different scenario"):
        HistoricalClaimLedgerLoader(repository).load(ledger_path)

    _assert_clean(repository)


def _incomplete_metric_bindings() -> list[Payload]:
    return _accepted_bindings()[:1]


def _diagnostic_metric_bindings() -> list[Payload]:
    bindings = _accepted_bindings()
    bindings[1] = {
        "claim_metric": CLAIM_METRICS[1],
        "study_metric_id": DIAGNOSTIC_METRIC,
    }
    return bindings


@pytest.mark.parametrize(
    ("case_name", "binding_factory", "expected_message"),
    (
        pytest.param(
            "subset-binding",
            _incomplete_metric_bindings,
            "exact full claim metric bindings",
            id="incomplete-claim-metric-binding",
        ),
        pytest.param(
            "diagnostic-binding",
            _diagnostic_metric_bindings,
            "exact typed study metric identity",
            id="diagnostic-acceptance-binding",
        ),
    ),
)
def test_rejects_invalid_acceptance_metric_bindings(
    acceptance_repository: AcceptanceRepositoryFixture,
    tmp_path: Path,
    case_name: str,
    binding_factory: Callable[[], list[Payload]],
    expected_message: str,
) -> None:
    repository = _clone_acceptance_case(
        acceptance_repository,
        tmp_path,
        case_name,
    )
    ledger_path = _write_negative_ledger(
        repository,
        content_sha256=acceptance_repository.content_sha256,
        artifact_path=ARTIFACT_RELATIVE,
        artifact_sha256=acceptance_repository.artifact.artifact_sha256,
        metric_bindings=binding_factory(),
    )
    _commit(
        repository,
        f"Reject {case_name}",
        timestamp="2026-08-02T12:10:00+00:00",
    )
    with pytest.raises(ValueError, match=expected_message) as error_info:
        HistoricalClaimLedgerLoader(repository).load(ledger_path)

    assert expected_message in str(error_info.value)
    _assert_clean(repository)


def _drift_execution_ledger(payload: Payload) -> None:
    payload["execution_ledger_sha256"] = canonical_sha256(
        "an unrelated execution ledger",
    )


def _use_nonexistent_revision(payload: Payload) -> None:
    nonexistent = "0123456789abcdef0123456789abcdef01234567"
    nonexistent_fingerprint = canonical_sha256(
        {"commit": nonexistent, "dirty": False},
    )
    payload["execution"]["code_revision"]["commit"] = nonexistent
    payload["execution"]["code_revision"]["worktree_fingerprint"] = nonexistent_fingerprint
    for run in payload["execution"]["runs"]:
        run["runtime_provenance"]["code_revision"]["commit"] = nonexistent
        run["runtime_provenance"]["code_revision"]["worktree_fingerprint"] = nonexistent_fingerprint


def _drift_catalog(payload: Payload) -> None:
    drifted = canonical_sha256("tampered catalog")
    payload["execution"]["catalog_revision"] = drifted
    for run in payload["execution"]["runs"]:
        run["runtime_provenance"]["catalog_revision"] = drifted


def _drift_loadout(payload: Payload) -> None:
    drifted = canonical_sha256("tampered loadout")
    payload["execution"]["loaded_roster_loadout_fingerprint"] = drifted
    for run in payload["execution"]["runs"]:
        run["runtime_provenance"]["loaded_roster_loadout_fingerprint"] = drifted


def _drift_assignment(payload: Payload) -> None:
    assignments = payload["execution"]["initial_unit_assignments"]
    assignments[0]["commander_profile_id"] = "tampered_commander"
    for run in payload["execution"]["runs"]:
        provenance = run["runtime_provenance"]
        run_assignments = provenance["initial_unit_assignments"]
        run_assignments[0]["commander_profile_id"] = "tampered_commander"
        provenance["doctrine_assignment_fingerprint"] = canonical_sha256(
            run_assignments + provenance["arriving_unit_assignments"],
        )


@pytest.mark.parametrize(
    ("case_name", "mutation", "expected_message"),
    (
        pytest.param(
            "committed-ledger-drift",
            _drift_execution_ledger,
            "execution ledger drifted",
            id="committed-execution-ledger-drift",
        ),
        pytest.param(
            "missing-execution-revision",
            _use_nonexistent_revision,
            "code/ledger revision cannot be verified",
            id="nonexistent-execution-revision",
        ),
        pytest.param(
            "current-catalog-drift",
            _drift_catalog,
            "production inputs drifted",
            id="current-catalog-drift",
        ),
        pytest.param(
            "current-loadout-drift",
            _drift_loadout,
            "production inputs drifted",
            id="current-loadout-drift",
        ),
        pytest.param(
            "current-assignment-drift",
            _drift_assignment,
            "production inputs drifted",
            id="current-doctrine-assignment-drift",
        ),
    ),
)
def test_rejects_tampered_artifact_evidence(
    acceptance_repository: AcceptanceRepositoryFixture,
    tmp_path: Path,
    case_name: str,
    mutation: ArtifactMutation,
    expected_message: str,
) -> None:
    repository = _clone_acceptance_case(
        acceptance_repository,
        tmp_path,
        case_name,
    )
    artifact_path, artifact = _mutated_artifact(
        repository,
        acceptance_repository.artifact,
        name=case_name,
        mutate=mutation,
    )
    ledger_path = _write_negative_ledger(
        repository,
        content_sha256=acceptance_repository.content_sha256,
        artifact_path=artifact_path,
        artifact_sha256=artifact.artifact_sha256,
    )
    _commit(
        repository,
        f"Reject {case_name}",
        timestamp="2026-08-02T12:12:00+00:00",
    )
    with pytest.raises(ValueError, match=expected_message) as error_info:
        HistoricalClaimLedgerLoader(repository).load(ledger_path)

    assert expected_message in str(error_info.value)
    _assert_clean(repository)


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    "relative_path",
    ("stochastic_warfare/__init__.py", "api/__init__.py"),
    ids=("simulation-source", "api-source"),
)
def test_rejects_relevant_code_drift_after_execution(
    acceptance_repository: AcceptanceRepositoryFixture,
    tmp_path: Path,
    relative_path: str,
) -> None:
    repository = _clone_acceptance_case(
        acceptance_repository,
        tmp_path,
        "relevant-code-drift",
    )
    relevant_source = repository / relative_path
    relevant_source.write_text(
        relevant_source.read_text(encoding="utf-8") + "\n# Relevant post-execution drift fixture.\n",
        encoding="utf-8",
    )
    _commit(
        repository,
        "Introduce relevant post-execution drift",
        timestamp="2026-08-02T12:03:00+00:00",
    )
    with pytest.raises(ValueError, match="code/ledger revision cannot be verified"):
        HistoricalClaimLedgerLoader(repository).load(
            repository / LEDGER_RELATIVE,
        )
    _assert_clean(repository)
