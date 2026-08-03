"""Phase 117 red and acceptance tests for historical-claim integrity."""

from __future__ import annotations

import importlib
import hashlib
import math
from pathlib import Path
import re
from typing import Any

import pytest
import yaml

from stochastic_warfare.validation.historical_backtest.common import (
    canonical_sha256,
)
from stochastic_warfare.validation.historical_data import (
    HistoricalDataLoader,
    HistoricalMetric,
)
from stochastic_warfare.validation.monte_carlo import (
    ComparisonReport,
    MonteCarloResult,
    RunResult,
)


ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "data/validation/historical_claims.yaml"
STUDY_PATH = ROOT / "data/validation/historical_studies/73_easting_phase117.yaml"


def _write_claim_ledger(
    repository: Path,
    claims: list[dict[str, Any]],
    *,
    claim_source_reviews: list[dict[str, Any]] | None = None,
) -> Path:
    reviews = list(claim_source_reviews or [])
    reviewed_paths = {review["repository_path"] for review in reviews}
    scenario_claim_ids_by_path: dict[str, list[str]] = {}
    for claim in claims:
        if claim["surface"] in {
            "scenario_documented_outcomes",
            "scenario_historical_prose",
        }:
            scenario_claim_ids_by_path.setdefault(
                claim["repository_path"],
                [],
            ).append(claim["claim_id"])
    contract = _contract_module()
    for candidate in contract.scan_historical_claim_sources(
        repository,
        source_kinds=frozenset({contract.ClaimSourceKind.SCENARIO_YAML}),
    ):
        claim_ids = scenario_claim_ids_by_path.get(candidate.repository_path, [])
        if claim_ids and candidate.repository_path not in reviewed_paths:
            reviews.append(
                _review_candidate(
                    candidate,
                    claim_ids=sorted(claim_ids),
                ),
            )
    reviews.sort(key=lambda review: (review["source_kind"], review["repository_path"]))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "ledger_id": "phase117.path-integrity.v1",
        "claim_source_scanner_version": 2,
        "claim_source_reviews": reviews,
        "claims": claims,
    }
    payload["ledger_sha256"] = canonical_sha256(payload)
    path = repository / "data/validation/historical_claims.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _claim_source_review(
    *,
    repository_path: str,
    source_kind: str,
    source: str,
    claim_ids: list[str] | None = None,
    exclusion: dict[str, str] | None = None,
    rule_id: str = "historical_status_vocabulary",
    occurrences: int = 1,
) -> dict[str, Any]:
    return {
        "repository_path": repository_path,
        "source_kind": source_kind,
        "source_sha256": hashlib.sha256(
            source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"),
        ).hexdigest(),
        "matches": [{"rule_id": rule_id, "occurrences": occurrences}],
        "claim_ids": claim_ids or [],
        "exclusion": exclusion,
    }


def _review_candidate(
    candidate: Any,
    *,
    claim_ids: list[str] | None = None,
    exclusion_reason: str | None = None,
) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json")
    payload["claim_ids"] = claim_ids or []
    payload["exclusion"] = (
        {
            "reason_code": exclusion_reason,
            "rationale": ("Synthetic scanner control reviewed as mechanism text, not an outcome claim."),
        }
        if exclusion_reason is not None
        else None
    )
    return payload


def _write_synthetic_scenario_claim(
    repository: Path,
    *,
    scenario_id: str = "inventoried",
) -> dict[str, Any]:
    relative = f"data/scenarios/{scenario_id}/scenario.yaml"
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "documented_outcomes:\n- name: synthetic_metric\n",
        encoding="utf-8",
    )
    return _unsupported_claim(
        claim_id=f"scenario.{scenario_id}.documented-outcomes",
        repository_path=relative,
        scenario_path=relative,
        surface="scenario_documented_outcomes",
        locator={"kind": "yaml_path", "segments": ["documented_outcomes"]},
        normalized_content={
            "kind": "yaml_path",
            "segments": ["documented_outcomes"],
            "content": [{"name": "synthetic_metric"}],
        },
    )


def _unsupported_claim(
    *,
    claim_id: str,
    repository_path: str,
    scenario_path: str | None,
    surface: str,
    locator: dict[str, Any],
    normalized_content: dict[str, Any],
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "repository_path": repository_path,
        "scenario_path": scenario_path,
        "surface": surface,
        "locator": locator,
        "content_sha256": canonical_sha256(normalized_content),
        "disposition": "unsupported",
        "metric_scope": (["synthetic_metric"] if surface == "scenario_documented_outcomes" else []),
        "reason_codes": ["synthetic_integrity_control"],
        "limitation": "Synthetic path-integrity control; not historical evidence.",
        "current_engine_regression_evidence": False,
        "accepted_evidence": None,
    }


def _contract_module():
    return importlib.import_module(
        "stochastic_warfare.validation.historical_backtest",
    )


def test_strict_claim_ledger_audits_the_exact_repository_inventory() -> None:
    contract = _contract_module()
    ledger, audit = contract.HistoricalClaimLedgerLoader(ROOT).load_with_audit(
        LEDGER_PATH,
    )

    assert len(ledger.claims) == 243
    assert audit.scenario_collections == 31
    assert audit.scenario_metrics == 83
    assert audit.python_test_surfaces == 25
    assert audit.frontend_test_surfaces == 1
    assert audit.documentation_claims == 164
    assert audit.documentation_claim_paths == 67
    assert audit.api_python_candidate_paths == 2
    assert audit.frontend_public_candidate_paths == 3
    assert audit.frontend_test_candidate_paths == 4
    assert audit.python_test_candidate_paths == 38
    assert audit.public_document_candidate_paths == 103
    assert audit.scenario_yaml_candidate_paths == 34
    assert audit.workflow_document_candidate_paths == 12
    assert audit.claim_bound_source_reviews == 135
    assert audit.reviewed_nonclaim_source_reviews == 61
    assert audit.production_validated_claims == 0
    assert audit.uninventoried_scenario_collections == ()
    assert audit.missing_scenario_collections == ()
    assert audit.unreviewed_claim_source_paths == ()
    assert audit.stale_claim_source_reviews == ()
    assert audit.claim_source_digest_mismatches == ()
    assert audit.claim_source_rule_mismatches == ()
    assert audit.claim_source_binding_errors == ()
    assert audit.forbidden_boolean_historical_apis == ()
    assert audit.digest_mismatches == ()


def test_claim_ledger_rejects_an_in_repository_source_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sources/claim.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        "documented_outcomes:\n- name: synthetic_metric\n",
        encoding="utf-8",
    )
    alias = tmp_path / "claim-alias.yaml"
    alias.symlink_to(source.relative_to(tmp_path))
    normalized = {
        "kind": "yaml_path",
        "segments": ["documented_outcomes"],
        "content": [{"name": "synthetic_metric"}],
    }
    claim = _unsupported_claim(
        claim_id="scenario.synthetic.symlink",
        repository_path="claim-alias.yaml",
        scenario_path="claim-alias.yaml",
        surface="scenario_documented_outcomes",
        locator={"kind": "yaml_path", "segments": ["documented_outcomes"]},
        normalized_content=normalized,
    )
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    contract = _contract_module()

    with pytest.raises(ValueError, match="scenario.synthetic.symlink"):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_scenario_catalog_loader_audits_published_claims_without_packaging_docs(
    tmp_path: Path,
) -> None:
    scenario_path = tmp_path / "data/scenarios/synthetic/scenario.yaml"
    scenario_path.parent.mkdir(parents=True)
    scenario_path.write_text(
        "documented_outcomes:\n- name: synthetic_metric\n",
        encoding="utf-8",
    )
    scenario_claim = _unsupported_claim(
        claim_id="scenario.synthetic.catalog",
        repository_path="data/scenarios/synthetic/scenario.yaml",
        scenario_path="data/scenarios/synthetic/scenario.yaml",
        surface="scenario_documented_outcomes",
        locator={"kind": "yaml_path", "segments": ["documented_outcomes"]},
        normalized_content={
            "kind": "yaml_path",
            "segments": ["documented_outcomes"],
            "content": [{"name": "synthetic_metric"}],
        },
    )
    documentation_claim = _unsupported_claim(
        claim_id="docs.synthetic.missing-package-source",
        repository_path="docs/missing.md",
        scenario_path=None,
        surface="documentation_claim",
        locator={
            "kind": "required_text",
            "text": "Synthetic historical-status disclosure.",
            "expected_occurrences": 1,
        },
        normalized_content={
            "kind": "required_text",
            "text": "Synthetic historical-status disclosure.",
            "occurrences": 1,
        },
    )
    ledger_path = _write_claim_ledger(
        tmp_path,
        [documentation_claim, scenario_claim],
        claim_source_reviews=[
            _claim_source_review(
                repository_path="docs/missing.md",
                source_kind="public_document",
                source="Synthetic historical-status disclosure.\n",
                claim_ids=["docs.synthetic.missing-package-source"],
            ),
        ],
    )
    contract = _contract_module()
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)

    ledger = loader.load_scenario_catalog(ledger_path)

    summary = ledger.scenario_summary(scenario_path)
    assert summary.aggregate_disposition.value == "unsupported"
    assert tuple(claim.claim_id for claim in summary.claims) == ("scenario.synthetic.catalog",)
    with pytest.raises(ValueError, match="docs.synthetic.missing-package-source"):
        loader.load(ledger_path)
    scenario_path.write_text(
        "documented_outcomes:\n- name: drifted_metric\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="scenario.synthetic.catalog"):
        loader.load_scenario_catalog(ledger_path)


def test_closed_vocabulary_scanner_finds_python_and_public_doc_claims(
    tmp_path: Path,
) -> None:
    python_path = tmp_path / "tests/validation/test_synthetic_history.py"
    python_path.parent.mkdir(parents=True)
    python_path.write_text(
        '"""The expected winner matches the historical outcome envelope."""\n'
        "from stochastic_warfare.validation.historical_data import HistoricalMetric\n",
        encoding="utf-8",
    )
    document_path = tmp_path / "docs/report.md"
    document_path.parent.mkdir(parents=True)
    document_path.write_text(
        "# Report\n\nCasualties should match historical data before this is validated.\n",
        encoding="utf-8",
    )
    contract = _contract_module()

    candidates = contract.scan_historical_claim_sources(tmp_path)

    assert tuple(candidate.repository_path for candidate in candidates) == (
        "docs/report.md",
        "tests/validation/test_synthetic_history.py",
    )
    python_rules = {match.rule_id.value for match in candidates[1].matches}
    document_rules = {match.rule_id.value for match in candidates[0].matches}
    assert {
        "historical_outcome_cooccurrence",
        "legacy_claim_api",
        "outcome_envelope",
        "scenario_status_alias",
    } <= python_rules
    assert "historical_outcome_cooccurrence" in document_rules


def test_scanner_v2_discovers_each_runtime_public_test_data_and_workflow_kind(
    tmp_path: Path,
) -> None:
    sources = {
        "api/schemas.py": ("class HistoricalOutcome:\n    current_engine_regression_evidence: bool\n"),
        "frontend/src/pages/scenarios/Status.tsx": (
            "export const Status = () => (\n  <p>This historical outcome is\n  validated.</p>\n)\n"
        ),
        "frontend/src/__tests__/pages/Status.test.tsx": ("const documented_outcomes = []\n"),
        "data/scenarios/prose/scenario.yaml": ("name: prose\n# This historical outcome is validated.\n"),
        ".agents/skills/evaluate-scenarios/SKILL.md": (
            "Never label an outcome historically accurate without evidence.\n"
        ),
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    generated = tmp_path / "frontend/dist/assets/app.js"
    generated.parent.mkdir(parents=True)
    generated.write_text(
        "const claim = 'historical outcome validated'\n",
        encoding="utf-8",
    )
    catalog = tmp_path / "data/weapons/catalog.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        "notes: historical outcome validated\n",
        encoding="utf-8",
    )
    declaration = tmp_path / "frontend/src/historical-status.d.ts"
    declaration.parent.mkdir(parents=True, exist_ok=True)
    declaration.write_text(
        "export interface Status { production_validated: boolean }\n",
        encoding="utf-8",
    )
    contract = _contract_module()

    candidates = contract.scan_historical_claim_sources(tmp_path)

    assert tuple((candidate.source_kind.value, candidate.repository_path) for candidate in candidates) == (
        ("api_python", "api/schemas.py"),
        (
            "frontend_public_source",
            "frontend/src/pages/scenarios/Status.tsx",
        ),
        (
            "frontend_test",
            "frontend/src/__tests__/pages/Status.test.tsx",
        ),
        ("scenario_yaml", "data/scenarios/prose/scenario.yaml"),
        (
            "workflow_document",
            ".agents/skills/evaluate-scenarios/SKILL.md",
        ),
    )
    assert "historical_status_vocabulary" in {match.rule_id.value for match in candidates[0].matches}
    assert "legacy_claim_api" in {match.rule_id.value for match in candidates[2].matches}
    assert generated.relative_to(tmp_path).as_posix() not in {candidate.repository_path for candidate in candidates}
    assert catalog.relative_to(tmp_path).as_posix() not in {candidate.repository_path for candidate in candidates}
    assert declaration.relative_to(tmp_path).as_posix() not in {candidate.repository_path for candidate in candidates}


@pytest.mark.parametrize(
    "status_source",
    (
        "export const status = 'Production validated.'\n",
        "export const status = 'Current-engine regression evidence.'\n",
        "export const productionValidated = true\n",
        "export const currentEngineRegressionEvidence = true\n",
    ),
)
def test_scanner_v2_normalizes_public_status_vocabulary(
    tmp_path: Path,
    status_source: str,
) -> None:
    path = tmp_path / "frontend/src/pages/scenarios/Status.tsx"
    path.parent.mkdir(parents=True)
    path.write_text(status_source, encoding="utf-8")
    contract = _contract_module()

    candidates = contract.scan_historical_claim_sources(tmp_path)

    assert tuple(candidate.repository_path for candidate in candidates) == ("frontend/src/pages/scenarios/Status.tsx",)
    status_matches = tuple(
        match for match in candidates[0].matches if match.rule_id.value == "historical_status_vocabulary"
    )
    assert len(status_matches) == 1
    assert status_matches[0].occurrences == 1


def test_frontend_declaration_review_is_not_a_public_source_kind(
    tmp_path: Path,
) -> None:
    source = "export interface Status { production_validated: boolean }\n"
    contract = _contract_module()
    review = _claim_source_review(
        repository_path="frontend/src/historical-status.d.ts",
        source_kind="frontend_public_source",
        source=source,
        exclusion={
            "reason_code": "metadata_or_visualization_reference",
            "rationale": "Synthetic declaration-file exclusion control for scanner scope.",
        },
    )

    with pytest.raises(ValueError, match="incompatible with its source_kind"):
        contract.ReviewedClaimSource.model_validate(review, strict=True)


@pytest.mark.parametrize(
    ("source_kind", "repository_path", "surface", "source", "token", "append", "packaged"),
    (
        (
            "api_python",
            "api/claims.py",
            "api_claim_surface",
            'STATUS = "Historical validation remains unsupported."\n',
            "Historical validation remains unsupported.",
            'APPENDED = "Historically accurate outcome."\n',
            True,
        ),
        (
            "frontend_public_source",
            "frontend/src/pages/scenarios/Claim.tsx",
            "frontend_claim_surface",
            "export const status = 'Historical validation remains unsupported.'\n",
            "Historical validation remains unsupported.",
            "export const appended = 'Historically accurate outcome.'\n",
            False,
        ),
        (
            "frontend_test",
            "frontend/src/__tests__/pages/Claim.test.tsx",
            "frontend_historical_claim_test",
            "const documented_outcomes = []\n",
            "documented_outcomes",
            "const appended = 'Historically accurate outcome.'\n",
            False,
        ),
        (
            "workflow_document",
            ".agents/skills/backtest/SKILL.md",
            "documentation_claim",
            "Historical validation remains unsupported.\n",
            "Historical validation remains unsupported.",
            "Historically accurate outcomes require accepted evidence.\n",
            False,
        ),
    ),
)
def test_scanner_v2_rejects_claim_appends_to_reviewed_non_scenario_sources(
    tmp_path: Path,
    source_kind: str,
    repository_path: str,
    surface: str,
    source: str,
    token: str,
    append: str,
    packaged: bool,
) -> None:
    scenario_claim = _write_synthetic_scenario_claim(tmp_path)
    path = tmp_path / repository_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    source_claim = _unsupported_claim(
        claim_id=f"source.{source_kind}.claim",
        repository_path=repository_path,
        scenario_path=None,
        surface=surface,
        locator={
            "kind": "required_text",
            "text": token,
            "expected_occurrences": 1,
        },
        normalized_content={
            "kind": "required_text",
            "text": token,
            "occurrences": 1,
        },
    )
    claims = sorted(
        [scenario_claim, source_claim],
        key=lambda claim: claim["claim_id"],
    )
    contract = _contract_module()
    candidate = next(
        candidate
        for candidate in contract.scan_historical_claim_sources(tmp_path)
        if candidate.repository_path == repository_path
    )
    ledger_path = _write_claim_ledger(
        tmp_path,
        claims,
        claim_source_reviews=[
            _review_candidate(
                candidate,
                claim_ids=[source_claim["claim_id"]],
            ),
        ],
    )
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)
    loader.load(ledger_path)
    if packaged:
        loader.load_scenario_catalog(ledger_path)

    path.write_text(source + append, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=rf"claim_source_digest_mismatches=.*{re.escape(repository_path)}",
    ):
        loader.load(ledger_path)
    if packaged:
        with pytest.raises(
            ValueError,
            match=rf"claim_source_digest_mismatches=.*{re.escape(repository_path)}",
        ):
            loader.load_scenario_catalog(ledger_path)


def test_full_and_packaged_loaders_reject_scenario_prose_append(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    contract = _contract_module()
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)
    loader.load(ledger_path)
    loader.load_scenario_catalog(ledger_path)
    scenario_path = tmp_path / claim["repository_path"]
    source = scenario_path.read_text(encoding="utf-8")

    scenario_path.write_text(
        source + "# This historical outcome is validated.\n",
        encoding="utf-8",
    )

    for load in (loader.load, loader.load_scenario_catalog):
        with pytest.raises(
            ValueError,
            match=r"claim_source_digest_mismatches=.*inventoried",
        ):
            load(ledger_path)


def test_full_and_packaged_loaders_reject_unreviewed_scenario_prose(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    extra = tmp_path / "data/scenarios/unreviewed/scenario.yaml"
    extra.parent.mkdir(parents=True)
    extra.write_text(
        "name: unreviewed\n# This historical outcome is validated.\n",
        encoding="utf-8",
    )
    contract = _contract_module()
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)

    for load in (loader.load, loader.load_scenario_catalog):
        with pytest.raises(
            ValueError,
            match=r"unreviewed_claim_source_paths=.*unreviewed",
        ):
            load(ledger_path)


def test_scenario_review_must_bind_collection_and_prose_claims(
    tmp_path: Path,
) -> None:
    documented_claim = _write_synthetic_scenario_claim(tmp_path)
    path = tmp_path / documented_claim["repository_path"]
    source = path.read_text(encoding="utf-8")
    prose_line = "# Historical outcome remains unsupported."
    path.write_text(source + prose_line + "\n", encoding="utf-8")
    prose_claim = _unsupported_claim(
        claim_id="scenario.inventoried.historical-prose",
        repository_path=documented_claim["repository_path"],
        scenario_path=documented_claim["repository_path"],
        surface="scenario_historical_prose",
        locator={"kind": "token_lines", "token": "Historical outcome"},
        normalized_content={
            "kind": "token_lines",
            "token": "Historical outcome",
            "lines": [prose_line],
        },
    )
    claims = sorted(
        [documented_claim, prose_claim],
        key=lambda claim: claim["claim_id"],
    )
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(
        tmp_path,
        source_kinds=frozenset({contract.ClaimSourceKind.SCENARIO_YAML}),
    )[0]
    ledger_path = _write_claim_ledger(
        tmp_path,
        claims,
        claim_source_reviews=[
            _review_candidate(
                candidate,
                claim_ids=[documented_claim["claim_id"]],
            ),
        ],
    )

    with pytest.raises(ValueError, match="must bind every compatible claim"):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_source_digest_is_lf_normalized_and_candidate_order_is_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "api/claims.py"
    path.parent.mkdir(parents=True)
    lf_source = 'STATUS = "Historical validation remains unsupported."\n'
    path.write_text(lf_source, encoding="utf-8")
    contract = _contract_module()
    first = contract.scan_historical_claim_sources(
        tmp_path,
        source_kinds=frozenset({contract.ClaimSourceKind.API_PYTHON}),
    )

    path.write_bytes(lf_source.replace("\n", "\r\n").encode("utf-8"))
    second = contract.scan_historical_claim_sources(
        tmp_path,
        source_kinds=frozenset({contract.ClaimSourceKind.API_PYTHON}),
    )

    assert first == second


def test_scenario_scanner_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "data/scenarios/duplicate/scenario.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "name: first\nname: second\n# Historical outcome validated.\n",
        encoding="utf-8",
    )
    contract = _contract_module()

    with pytest.raises(ValueError, match="cannot scan scenario YAML"):
        contract.scan_historical_claim_sources(
            tmp_path,
            source_kinds=frozenset({contract.ClaimSourceKind.SCENARIO_YAML}),
        )


def test_frontend_test_review_cannot_masquerade_as_public_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "frontend/src/__tests__/Claim.test.tsx"
    path.parent.mkdir(parents=True)
    path.write_text("const documented_outcomes = []\n", encoding="utf-8")
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    review = _review_candidate(
        candidate,
        exclusion_reason="integrity_test_fixture",
    )
    review["source_kind"] = "frontend_public_source"

    with pytest.raises(ValueError, match="incompatible with its source_kind"):
        contract.ReviewedClaimSource.model_validate(review, strict=True)


def test_scanner_v1_ledger_is_rejected_after_v2_migration(tmp_path: Path) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    payload = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
    payload["claim_source_scanner_version"] = 1
    payload["ledger_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "ledger_sha256"},
    )
    ledger_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    contract = _contract_module()

    with pytest.raises(ValueError, match="strict integer 2"):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


@pytest.mark.parametrize(
    ("field", "replacement", "error"),
    (
        ("source_sha256", "0" * 64, "sentinel digest"),
        (
            "exclusion",
            {
                "reason_code": "not_a_claim",
                "rationale": "This scanner candidate is not a historical outcome claim.",
            },
            "unsupported claim-source exclusion reason",
        ),
        (
            "exclusion",
            {
                "reason_code": "future_plan_or_noncapability",
                "rationale": "Not a claim.",
            },
            "rationale must be substantive",
        ),
    ),
)
def test_reviewed_source_schema_rejects_sentinel_or_paper_exclusions(
    tmp_path: Path,
    field: str,
    replacement: Any,
    error: str,
) -> None:
    source_path = tmp_path / "docs/history.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "This proposed historical validation remains future work.\n",
        encoding="utf-8",
    )
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    review = _review_candidate(
        candidate,
        exclusion_reason="future_plan_or_noncapability",
    )
    review[field] = replacement

    with pytest.raises(ValueError, match=error):
        contract.ReviewedClaimSource.model_validate(review, strict=True)


def test_full_loader_rejects_unreviewed_claim_source_then_detects_digest_drift(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    source_path = tmp_path / "tests/validation/test_synthetic_claim.py"
    source_path.parent.mkdir(parents=True)
    source = '"""Current winner asserted against a historical outcome."""\n'
    source_path.write_text(source, encoding="utf-8")
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)

    with pytest.raises(
        ValueError,
        match=r"unreviewed_claim_source_paths=.*test_synthetic_claim.py",
    ):
        loader.load(ledger_path)

    mismatched_review = _review_candidate(
        candidate,
        exclusion_reason="integrity_test_fixture",
    )
    mismatched_review["matches"][0]["occurrences"] += 1
    ledger_path = _write_claim_ledger(
        tmp_path,
        [claim],
        claim_source_reviews=[mismatched_review],
    )
    with pytest.raises(
        ValueError,
        match=r"claim_source_rule_mismatches=.*test_synthetic_claim.py",
    ):
        loader.load(ledger_path)

    ledger_path = _write_claim_ledger(
        tmp_path,
        [claim],
        claim_source_reviews=[
            _review_candidate(
                candidate,
                exclusion_reason="integrity_test_fixture",
            ),
        ],
    )
    ledger = loader.load(ledger_path)
    audit = ledger.audit_repository()
    assert audit.python_test_candidate_paths == 1
    assert audit.reviewed_nonclaim_source_reviews == 1
    assert audit.unreviewed_claim_source_paths == ()

    source_path.write_text(
        source + "# Unrelated edit still requires exact source re-review.\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match=r"claim_source_digest_mismatches=.*test_synthetic_claim.py",
    ):
        loader.load(ledger_path)


def test_claim_source_review_rejects_an_unknown_claim_identity(
    tmp_path: Path,
) -> None:
    scenario_claim = _write_synthetic_scenario_claim(tmp_path)
    source_path = tmp_path / "docs/history.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "This historical outcome remains unsupported.\n",
        encoding="utf-8",
    )
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    ledger_path = _write_claim_ledger(
        tmp_path,
        [scenario_claim],
        claim_source_reviews=[
            _review_candidate(
                candidate,
                claim_ids=["docs.synthetic.unknown"],
            ),
        ],
    )

    with pytest.raises(ValueError, match="references unknown claim"):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_full_loader_rejects_stale_claim_source_review(tmp_path: Path) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    source_path = tmp_path / "docs/history.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "This outcome is not historical validation.\n",
        encoding="utf-8",
    )
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    ledger_path = _write_claim_ledger(
        tmp_path,
        [claim],
        claim_source_reviews=[
            _review_candidate(
                candidate,
                exclusion_reason="future_plan_or_noncapability",
            ),
        ],
    )
    source_path.write_text("Ordinary documentation.\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"stale_claim_source_reviews=.*docs/history.md",
    ):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_generic_python_historical_claim_surface_is_exactly_review_bound(
    tmp_path: Path,
) -> None:
    source = '"""This regression is unsupported as historical validation."""\n'
    source_path = tmp_path / "tests/validation/test_current_regression.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(source, encoding="utf-8")
    claim = _unsupported_claim(
        claim_id="test.validation.current-regression.historical-claim",
        repository_path="tests/validation/test_current_regression.py",
        scenario_path=None,
        surface="python_historical_claim_test",
        locator={
            "kind": "required_text",
            "text": "unsupported as historical validation",
            "expected_occurrences": 1,
        },
        normalized_content={
            "kind": "required_text",
            "text": "unsupported as historical validation",
            "occurrences": 1,
        },
    )
    contract = _contract_module()
    candidate = contract.scan_historical_claim_sources(tmp_path)[0]
    ledger_path = _write_claim_ledger(
        tmp_path,
        [claim],
        claim_source_reviews=[
            _review_candidate(
                candidate,
                claim_ids=[claim["claim_id"]],
            ),
        ],
    )

    ledger = contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)
    from scripts.validate_scenario_data import validate_historical_claim_inventory

    validation, validator_audit = validate_historical_claim_inventory(
        repository_root=tmp_path,
        ledger_path=ledger_path,
    )

    assert ledger.audit_repository().python_test_surfaces == 1
    assert validation.ok
    assert validator_audit is not None
    assert validator_audit.python_test_surfaces == 1


def test_full_and_packaged_loaders_reject_uninventoried_scenario_collection(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    extra = tmp_path / "data/scenarios/uninventoried/scenario.yaml"
    extra.parent.mkdir(parents=True)
    extra.write_text(
        "documented_outcomes:\n- name: concealed_metric\n",
        encoding="utf-8",
    )
    contract = _contract_module()
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)

    for load in (loader.load, loader.load_scenario_catalog):
        with pytest.raises(
            ValueError,
            match=r"uninventoried_scenario_collections=.*uninventoried",
        ):
            load(ledger_path)


def test_loader_reports_an_inventoried_collection_that_was_removed(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    scenario_path = tmp_path / claim["repository_path"]
    scenario_path.write_text("name: collection removed\n", encoding="utf-8")
    contract = _contract_module()

    with pytest.raises(
        ValueError,
        match=r"missing_scenario_collections=.*inventoried",
    ):
        contract.HistoricalClaimLedgerLoader(tmp_path).load(ledger_path)


def test_obsolete_boolean_historical_api_is_unreviewable_in_every_loader(
    tmp_path: Path,
) -> None:
    claim = _write_synthetic_scenario_claim(tmp_path)
    legacy_path = tmp_path / "stochastic_warfare/tools/envelope_check.py"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        "def check_winner_envelope() -> tuple[bool, str]:\n    return True, 'PASS'\n",
        encoding="utf-8",
    )
    ledger_path = _write_claim_ledger(tmp_path, [claim])
    contract = _contract_module()
    loader = contract.HistoricalClaimLedgerLoader(tmp_path)

    for load in (loader.load, loader.load_scenario_catalog):
        with pytest.raises(
            ValueError,
            match=r"forbidden_boolean_historical_apis=.*check_winner_envelope",
        ):
            load(ledger_path)


def test_external_scenario_path_has_a_synthetic_unsupported_summary(
    tmp_path: Path,
) -> None:
    contract = _contract_module()
    ledger = contract.HistoricalClaimLedgerLoader(ROOT).load(LEDGER_PATH)
    external = tmp_path / "external/scenario.yaml"
    external.parent.mkdir(parents=True)
    external.write_text("name: external\n", encoding="utf-8")

    summary = ledger.scenario_summary(external)

    assert summary.aggregate_disposition.value == "unsupported"
    assert summary.accepted_claim_ids == ()
    assert len(summary.claims) == 1
    assert summary.claims[0].reason_codes == ("missing_ledger_identity",)
    assert summary.claims[0].current_engine_regression_evidence is False
    assert str(external) not in summary.model_dump_json()


def test_73_easting_claim_summary_is_conservatively_unsupported() -> None:
    contract = _contract_module()
    ledger = contract.HistoricalClaimLedgerLoader(ROOT).load(LEDGER_PATH)

    summary = ledger.scenario_summary(
        ROOT / "data/scenarios/73_easting/scenario.yaml",
    )

    assert summary.aggregate_disposition.value == "unsupported"
    assert summary.current_engine_regression_evidence is True
    assert summary.accepted_claim_ids == ()
    assert any(
        claim.claim_id == "scenario.73_easting.documented_outcomes"
        and claim.disposition.value == "unsupported"
        and claim.current_engine_regression_evidence is True
        and claim.metric_scope
        == (
            "exchange_ratio",
            "blue_units_destroyed",
            "red_units_destroyed",
            "duration_s",
        )
        for claim in summary.claims
    )


def test_debecka_source_conflict_remains_explicit_and_api_visible() -> None:
    contract = _contract_module()
    ledger = contract.HistoricalClaimLedgerLoader(ROOT).load(LEDGER_PATH)

    claim = ledger.claim_by_id("scenario.debecka_pass.documented_outcomes")
    summary = ledger.scenario_summary(
        ROOT / "data/scenarios/debecka_pass/scenario.yaml",
    )

    assert "authoritative_source_conflicts_with_catalog_metadata" in claim.reason_codes
    assert "2.5 hours" in claim.limitation
    assert "5 T-55s, 3 APCs, and 8 cargo vehicles" in claim.limitation
    assert "4 hours, modal 10 red losses" in claim.limitation
    assert "Javelin-share proxy" in claim.limitation
    public_claim = next(item for item in summary.claims if item.claim_id == claim.claim_id)
    assert public_claim.limitation == claim.limitation
    assert public_claim.current_engine_regression_evidence is claim.current_engine_regression_evidence


def test_phase117_study_plan_is_frozen_and_promotion_ineligible() -> None:
    contract = _contract_module()
    plan = contract.HistoricalStudyLoader(ROOT).load(STUDY_PATH)

    assert plan.study_id == "73_easting.phase117.v1"
    assert plan.held_out_seeds == tuple(range(11700, 11720))
    assert plan.observation_boundary_s == 1380.0
    assert plan.acceptance_policy.confidence == 0.95
    assert plan.acceptance_policy.minimum_joint_coverage == 0.80
    assert plan.lineage.validation_source_relationship.value == "reused"
    assert plan.promotion_eligible is False
    assert tuple(metric.metric_id for metric in plan.gating_metrics) == (
        "iraqi_tanks_destroyed",
        "iraqi_personnel_carriers_destroyed",
        "american_vehicles_destroyed",
        "natural_action_duration_seconds",
    )
    tank_metric, carrier_metric = plan.gating_metrics[:2]
    assert (tank_metric.source_range.minimum, tank_metric.source_range.maximum) == (
        28.0,
        28.0,
    )
    assert tank_metric.extractor.included_unit_types == ("t72m",)
    assert (
        carrier_metric.source_range.minimum,
        carrier_metric.source_range.maximum,
    ) == (16.0, 16.0)
    assert carrier_metric.extractor.included_unit_types == ("bmp1", "bmp2")
    assert tuple(metric.metric_id for metric in plan.diagnostic_metrics) == ("blue_winner",)


def test_joint_exact_bound_requires_twenty_of_twenty() -> None:
    contract = _contract_module()

    perfect = contract.evaluate_joint_coverage(
        metric_in_range=(
            ("red_loss", (True,) * 20),
            ("blue_loss", (True,) * 20),
            ("duration", (True,) * 20),
        ),
        confidence=0.95,
        minimum_joint_coverage=0.80,
    )
    one_miss = contract.evaluate_joint_coverage(
        metric_in_range=(
            ("red_loss", (True,) * 19 + (False,)),
            ("blue_loss", (True,) * 20),
            ("duration", (True,) * 20),
        ),
        confidence=0.95,
        minimum_joint_coverage=0.80,
    )

    assert perfect.joint_successes == 20
    assert perfect.lower_confidence_bound == pytest.approx(
        0.8608916593317348,
    )
    assert perfect.passed is True
    assert one_miss.joint_successes == 19
    assert one_miss.lower_confidence_bound == pytest.approx(
        0.783893835793135,
    )
    assert one_miss.passed is False


def test_legacy_comparison_report_has_no_boolean_validation_verdict() -> None:
    with pytest.raises(ValueError, match="at least one metric"):
        ComparisonReport([])

    report = ComparisonReport(
        HistoricalDataLoader.compare_all(
            {"metric": 1.0},
            [HistoricalMetric(name="metric", value=1.0)],
        ),
    )
    assert not hasattr(report, "all_within_tolerance")
    assert report.passing_count() == 1
    assert report.failing_count() == 0


@pytest.mark.parametrize(
    "runs, message",
    [
        ([], "no runs"),
        ([RunResult(seed=1, metrics={}, terminated_by="test")], "missing metric"),
        (
            [
                RunResult(
                    seed=1,
                    metrics={"metric": math.nan},
                    terminated_by="test",
                ),
            ],
            "non-finite",
        ),
    ],
)
def test_legacy_monte_carlo_vectors_fail_closed(
    runs: list[RunResult],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MonteCarloResult(runs).mean("metric")


def test_legacy_comparator_rejects_duplicate_metric_names() -> None:
    metrics = [
        HistoricalMetric(name="duplicate", value=1.0),
        HistoricalMetric(name="duplicate", value=2.0),
    ]

    with pytest.raises(ValueError, match="duplicate historical metric"):
        HistoricalDataLoader.compare_all({"duplicate": 1.0}, metrics)
