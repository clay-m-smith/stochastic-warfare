"""Strict repository-wide historical-claim disposition ledger.

The ledger inventories claims; it does not execute simulations or infer a
historical verdict from legacy metadata.  Every inventoried surface is bound
to normalized source content and an absent scenario identity is conservatively
reported as unsupported.
"""

from __future__ import annotations

import ast
import hashlib
import io
import math
import re
import subprocess
import tokenize
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Mapping, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from stochastic_warfare.core.strict_yaml import load_yaml_unique

from .common import (
    canonical_sha256 as _canonical_sha256,
    require_relative_posix_path,
    require_stable_id,
    require_trimmed as _trimmed_text,
    resolve_repository_path,
)

if TYPE_CHECKING:
    from .artifacts import CompletedHistoricalArtifact


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HISTORICAL_TERM = r"(?:histor(?:ic|ical|ically)|real[- ]world|source[- ]backed)"
_OUTCOME_CLAIM_TERM = (
    r"(?:accept(?:ance|ed)?|accur(?:acy|ate)|backtests?|"
    r"calibrat(?:e|ed|ion)|casualt(?:y|ies)|destroy(?:ed|uctions?)?|"
    r"durations?|evidence|exchange[-_ ]?ratios?|fidelity|loss(?:es)?|"
    r"matches?|outcomes?|passes?|plausib(?:le|ility)|predictive|"
    r"results?|toleran(?:ce|ces|t)|validat(?:e|ed|ion)|verdicts?|"
    r"win(?:ner|ners|rate|rates)?)"
)
_HISTORICAL_OUTCOME_PATTERN = re.compile(
    rf"(?:\b{_HISTORICAL_TERM}\b.{{0,160}}\b{_OUTCOME_CLAIM_TERM}\b|"
    rf"\b{_OUTCOME_CLAIM_TERM}\b.{{0,160}}\b{_HISTORICAL_TERM}\b)",
    re.IGNORECASE,
)
_OUTCOME_ENVELOPE_PATTERN = re.compile(
    r"\b(?:historical[-_ ]+)?(?:outcome|winner|casualt(?:y|ies)|loss(?:es)?|"
    r"duration|exchange[-_ ]?ratio)[-_ ]+envelopes?\b",
    re.IGNORECASE,
)
_HISTORICAL_STATUS_PATTERN = re.compile(
    r"\b(?:historical[-_ ]+(?:accuracy|evidence|fidelity|validation|verdict)|"
    r"production[-_ ]+validated|"
    r"current[-_ ]+engine[-_ ]+regression[-_ ]+(?:evidence|only)|"
    r"predictive[-_ ]+calibration)\b",
    re.IGNORECASE,
)
_SCENARIO_STATUS_PATTERN = re.compile(
    r"\b(?:(?:golden|validated|calibrated)[-_ ]+scenarios?|"
    r"scenarios?[-_ ]+(?:validated|calibrated)|"
    r"(?:correct|expected)[-_ ]+(?:[a-z0-9]+[-_ ]+){0,2}winners?|"
    r"HISTORICAL_WINNERS)\b",
    re.IGNORECASE,
)
_LEGACY_CLAIM_API_PATTERN = re.compile(
    r"\b(?:documented_outcomes|HistoricalMetric|compare_to_historical|"
    r"ComparisonReport)\b",
)
_LEGACY_BOOLEAN_API_PATTERN = re.compile(
    r"\bcheck_(?:winner|duration|casualty)_envelope\b",
)
_REGRESSION_SNAPSHOT_PATTERN = re.compile(
    r"\b(?:CURRENT_ENGINE_TERMINAL_SNAPSHOT|PHASE_73_CURRENT_TERMINALS)\b",
)
_OBSOLETE_BOOLEAN_API_NAMES = frozenset(
    {
        "all_within_tolerance",
        "check_casualty_envelope",
        "check_duration_envelope",
        "check_winner_envelope",
    },
)


class ClaimDisposition(str, Enum):
    """The only repository-supported historical-claim classifications."""

    PRODUCTION_VALIDATED = "production_validated"
    CURRENT_ENGINE_REGRESSION_ONLY = "current_engine_regression_only"
    UNSUPPORTED = "unsupported"


class ClaimSurface(str, Enum):
    """Closed claim-surface vocabulary used by the Phase 117 inventory."""

    SCENARIO_DOCUMENTED_OUTCOMES = "scenario_documented_outcomes"
    SCENARIO_HISTORICAL_PROSE = "scenario_historical_prose"
    PYTHON_DOCUMENTED_OUTCOMES_TEST = "python_documented_outcomes_test"
    PYTHON_HISTORICAL_CLAIM_TEST = "python_historical_claim_test"
    CURRENT_ENGINE_REGRESSION_SNAPSHOT = "current_engine_regression_snapshot"
    DUPLICATED_REGRESSION_TABLE = "duplicated_regression_table"
    DOCUMENTATION_CLAIM = "documentation_claim"
    API_CLAIM_SURFACE = "api_claim_surface"
    FRONTEND_CLAIM_SURFACE = "frontend_claim_surface"
    FRONTEND_HISTORICAL_CLAIM_TEST = "frontend_historical_claim_test"


class ClaimSourceKind(str, Enum):
    """Closed repository source kinds inspected by the claim scanner."""

    API_PYTHON = "api_python"
    FRONTEND_PUBLIC_SOURCE = "frontend_public_source"
    FRONTEND_TEST = "frontend_test"
    PYTHON_TEST = "python_test"
    PUBLIC_DOCUMENT = "public_document"
    SCENARIO_YAML = "scenario_yaml"
    WORKFLOW_DOCUMENT = "workflow_document"


class ClaimSourceRule(str, Enum):
    """Closed candidate vocabulary; ledger data cannot weaken these rules."""

    HISTORICAL_OUTCOME_COOCCURRENCE = "historical_outcome_cooccurrence"
    HISTORICAL_STATUS_VOCABULARY = "historical_status_vocabulary"
    LEGACY_BOOLEAN_API = "legacy_boolean_api"
    LEGACY_CLAIM_API = "legacy_claim_api"
    OUTCOME_ENVELOPE = "outcome_envelope"
    REGRESSION_SNAPSHOT = "regression_snapshot"
    SCENARIO_STATUS_ALIAS = "scenario_status_alias"


class ClaimSourceExclusionReason(str, Enum):
    """Specific reviewed reasons a lexical candidate is not an outcome claim."""

    CURRENT_REGRESSION_IMPORT_CONTROL = "current_regression_import_control"
    DEPLOYMENT_LABEL_ONLY = "deployment_label_only"
    FUTURE_PLAN_OR_NONCAPABILITY = "future_plan_or_noncapability"
    INTEGRITY_TEST_FIXTURE = "integrity_test_fixture"
    METADATA_OR_VISUALIZATION_REFERENCE = "metadata_or_visualization_reference"
    MILITARY_HISTORICAL_FACT = "military_historical_fact"
    MODEL_OR_EQUIPMENT_ACCURACY = "model_or_equipment_accuracy"
    REVISION_BENCHMARK_REFERENCE = "revision_benchmark_reference"
    STORED_STATE_HISTORY_IDENTIFIER = "stored_state_history_identifier"
    WORKFLOW_METHOD_OR_GUARD = "workflow_method_or_guard"


_PYTHON_TEST_CLAIM_SURFACES = frozenset(
    {
        ClaimSurface.CURRENT_ENGINE_REGRESSION_SNAPSHOT,
        ClaimSurface.DUPLICATED_REGRESSION_TABLE,
        ClaimSurface.PYTHON_DOCUMENTED_OUTCOMES_TEST,
        ClaimSurface.PYTHON_HISTORICAL_CLAIM_TEST,
    },
)
_CLAIM_SURFACES_BY_SOURCE_KIND: Mapping[
    ClaimSourceKind,
    frozenset[ClaimSurface],
] = {
    ClaimSourceKind.API_PYTHON: frozenset({ClaimSurface.API_CLAIM_SURFACE}),
    ClaimSourceKind.FRONTEND_PUBLIC_SOURCE: frozenset(
        {ClaimSurface.FRONTEND_CLAIM_SURFACE},
    ),
    ClaimSourceKind.FRONTEND_TEST: frozenset(
        {ClaimSurface.FRONTEND_HISTORICAL_CLAIM_TEST},
    ),
    ClaimSourceKind.PYTHON_TEST: _PYTHON_TEST_CLAIM_SURFACES,
    ClaimSourceKind.PUBLIC_DOCUMENT: frozenset(
        {ClaimSurface.DOCUMENTATION_CLAIM},
    ),
    ClaimSourceKind.SCENARIO_YAML: frozenset(
        {
            ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES,
            ClaimSurface.SCENARIO_HISTORICAL_PROSE,
        },
    ),
    ClaimSourceKind.WORKFLOW_DOCUMENT: frozenset(
        {ClaimSurface.DOCUMENTATION_CLAIM},
    ),
}
_REVIEWED_CLAIM_SURFACES = frozenset(
    surface for surfaces in _CLAIM_SURFACES_BY_SOURCE_KIND.values() for surface in surfaces
)
_ALL_CLAIM_SOURCE_KINDS = frozenset(ClaimSourceKind)
_PACKAGED_CLAIM_SOURCE_KINDS = frozenset(
    {
        ClaimSourceKind.API_PYTHON,
        ClaimSourceKind.SCENARIO_YAML,
    },
)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _sha256(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _ordered_tuple(value: Any, *, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an ordered list")
    return tuple(value)


def _repository_relative_path(value: Any, *, field_name: str) -> str:
    try:
        return require_relative_posix_path(value, field_name=field_name)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a normalized repository-relative path",
        ) from exc


def _is_frontend_test_source(repository_path: str) -> bool:
    parts = repository_path.split("/")
    filename = parts[-1]
    return "__tests__" in parts or bool(
        re.search(r"\.(?:spec|test)\.tsx?$", filename),
    )


def _is_frontend_declaration_source(repository_path: str) -> bool:
    return repository_path.endswith(".d.ts")


def _claim_source_path_matches_kind(
    repository_path: str,
    source_kind: ClaimSourceKind,
) -> bool:
    if source_kind is ClaimSourceKind.API_PYTHON:
        return repository_path.startswith("api/") and repository_path.endswith(
            ".py",
        )
    if source_kind in {
        ClaimSourceKind.FRONTEND_PUBLIC_SOURCE,
        ClaimSourceKind.FRONTEND_TEST,
    }:
        is_frontend_source = repository_path.startswith(
            "frontend/src/",
        ) and repository_path.endswith((".ts", ".tsx"))
        if _is_frontend_declaration_source(repository_path):
            return False
        is_test = _is_frontend_test_source(repository_path)
        return is_frontend_source and (is_test if source_kind is ClaimSourceKind.FRONTEND_TEST else not is_test)
    if source_kind is ClaimSourceKind.PYTHON_TEST:
        return repository_path.startswith("tests/") and repository_path.endswith(
            ".py",
        )
    if source_kind is ClaimSourceKind.PUBLIC_DOCUMENT:
        return repository_path in {"README.md", "CLAUDE.md"} or (
            repository_path.startswith("docs/") and repository_path.endswith(".md")
        )
    if source_kind is ClaimSourceKind.SCENARIO_YAML:
        return repository_path.startswith("data/") and repository_path.endswith(
            "/scenario.yaml",
        )
    if source_kind is ClaimSourceKind.WORKFLOW_DOCUMENT:
        return bool(
            re.fullmatch(
                r"\.(?:agents|claude)/skills/(?:[^/]+/)*SKILL\.md",
                repository_path,
            ),
        )
    return False


class ClaimSourceRuleMatch(_StrictFrozenModel):
    """One scanner rule and its exact occurrence count in a source file."""

    rule_id: ClaimSourceRule
    occurrences: int

    @field_validator("rule_id", mode="before")
    @classmethod
    def _valid_rule_id(cls, value: Any) -> ClaimSourceRule:
        if isinstance(value, ClaimSourceRule):
            return value
        if not isinstance(value, str):
            raise ValueError("rule_id must be a strict claim-source rule string")
        try:
            return ClaimSourceRule(value)
        except ValueError as exc:
            raise ValueError(f"unsupported claim-source rule {value!r}") from exc

    @field_validator("occurrences", mode="before")
    @classmethod
    def _valid_occurrences(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("claim-source rule occurrences must be a positive integer")
        return value


class ReviewedClaimSourceExclusion(_StrictFrozenModel):
    """Human review for an exact digest-bound nonclaim candidate source."""

    reason_code: ClaimSourceExclusionReason
    rationale: str

    @field_validator("reason_code", mode="before")
    @classmethod
    def _valid_reason_code(cls, value: Any) -> ClaimSourceExclusionReason:
        if isinstance(value, ClaimSourceExclusionReason):
            return value
        if not isinstance(value, str):
            raise ValueError("reason_code must be a strict exclusion-reason string")
        try:
            return ClaimSourceExclusionReason(value)
        except ValueError as exc:
            raise ValueError(f"unsupported claim-source exclusion reason {value!r}") from exc

    @field_validator("rationale", mode="before")
    @classmethod
    def _valid_rationale(cls, value: Any) -> str:
        rationale = _trimmed_text(value, field_name="claim-source exclusion rationale")
        if len(rationale) < 20:
            raise ValueError("claim-source exclusion rationale must be substantive")
        return rationale


class ReviewedClaimSource(_StrictFrozenModel):
    """Exact review of one freshly discovered claim-candidate source file."""

    repository_path: str
    source_kind: ClaimSourceKind
    source_sha256: str
    matches: tuple[ClaimSourceRuleMatch, ...]
    claim_ids: tuple[str, ...]
    exclusion: ReviewedClaimSourceExclusion | None

    @field_validator("repository_path", mode="before")
    @classmethod
    def _valid_repository_path(cls, value: Any) -> str:
        return _repository_relative_path(value, field_name="claim-source repository_path")

    @field_validator("source_kind", mode="before")
    @classmethod
    def _valid_source_kind(cls, value: Any) -> ClaimSourceKind:
        if isinstance(value, ClaimSourceKind):
            return value
        if not isinstance(value, str):
            raise ValueError("source_kind must be a strict claim-source kind string")
        try:
            return ClaimSourceKind(value)
        except ValueError as exc:
            raise ValueError(f"unsupported claim-source kind {value!r}") from exc

    @field_validator("source_sha256", mode="before")
    @classmethod
    def _valid_source_digest(cls, value: Any) -> str:
        digest = _sha256(value, field_name="claim-source source_sha256")
        if len(set(digest)) == 1:
            raise ValueError("claim-source source_sha256 must not be a sentinel digest")
        return digest

    @field_validator("matches", "claim_ids", mode="before")
    @classmethod
    def _ordered_fields(cls, value: Any, info: Any) -> tuple[Any, ...]:
        return _ordered_tuple(value, field_name=info.field_name)

    @field_validator("claim_ids")
    @classmethod
    def _valid_claim_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for claim_id in value:
            require_stable_id(claim_id, field_name="claim-source claim ID")
        if value != tuple(sorted(set(value))):
            raise ValueError("claim-source claim_ids must be sorted and duplicate-free")
        return value

    @model_validator(mode="after")
    def _consistent_review(self) -> Self:
        if not self.matches:
            raise ValueError("claim-source review needs at least one scanner match")
        rule_ids = tuple(match.rule_id.value for match in self.matches)
        if rule_ids != tuple(sorted(set(rule_ids))):
            raise ValueError("claim-source matches must be sorted and duplicate-free")
        if bool(self.claim_ids) == (self.exclusion is not None):
            raise ValueError(
                "claim-source review requires either claim_ids or one reviewed exclusion",
            )
        if not _claim_source_path_matches_kind(
            self.repository_path,
            self.source_kind,
        ):
            raise ValueError(
                "claim-source path is incompatible with its source_kind: "
                f"{self.repository_path!r} / {self.source_kind.value!r}",
            )
        return self


class HistoricalClaimSourceCandidate(_StrictFrozenModel):
    """Fresh deterministic scanner output before its human disposition."""

    repository_path: str
    source_kind: ClaimSourceKind
    source_sha256: str
    matches: tuple[ClaimSourceRuleMatch, ...]


def _normalized_source_text(source: str) -> str:
    """Normalize platform newlines without erasing authored claim wording."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _source_sha256(source: str) -> str:
    return hashlib.sha256(
        _normalized_source_text(source).encode("utf-8"),
    ).hexdigest()


def _searchable_unit(value: str) -> str:
    camel_spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return re.sub(r"\s+", " ", camel_spaced).strip()


def _python_semantic_units(source: str, *, repository_path: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source, filename=repository_path)
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        comments = tuple(
            token.string.removeprefix("#").strip()
            for token in tokens
            if token.type == tokenize.COMMENT and token.string.removeprefix("#").strip()
        )
    except (SyntaxError, tokenize.TokenError) as exc:
        raise ValueError(
            f"cannot scan Python historical-claim source {repository_path!r}",
        ) from exc
    strings = tuple(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip()
    )
    symbols = tuple(
        node.name for node in ast.walk(tree) if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    )

    def target_names(target: ast.expr) -> tuple[str, ...]:
        if isinstance(target, ast.Name):
            return (target.id,)
        if isinstance(target, (ast.List, ast.Tuple)):
            return tuple(name for element in target.elts for name in target_names(element))
        if isinstance(target, ast.Starred):
            return target_names(target.value)
        return ()

    assigned_symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assigned_symbols.extend(target_names(target))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            assigned_symbols.extend(target_names(node.target))
    return tuple(
        unit for value in (*strings, *comments, *symbols, *assigned_symbols) if (unit := _searchable_unit(value))
    )


def _markdown_semantic_units(source: str) -> tuple[str, ...]:
    """Return deterministic prose/table/code blocks without a Markdown dependency."""
    units: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            unit = _searchable_unit(" ".join(paragraph))
            if unit:
                units.append(unit)
            paragraph.clear()

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("|") and line.endswith("|"):
            flush()
            units.append(_searchable_unit(line))
            continue
        paragraph.append(line)
    flush()
    return tuple(units)


def _typescript_semantic_units(source: str) -> tuple[str, ...]:
    """Expose authored identifiers, comments, strings, and JSX prose."""
    return _markdown_semantic_units(source)


def _scenario_yaml_semantic_units(
    source: str,
    *,
    repository_path: str,
) -> tuple[str, ...]:
    """Validate strict YAML while retaining authored comments as claim prose."""
    try:
        load_yaml_unique(source)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(
            f"cannot scan scenario YAML historical-claim source {repository_path!r}",
        ) from exc
    return _markdown_semantic_units(source)


def _pattern_occurrences(
    pattern: re.Pattern[str],
    values: tuple[str, ...],
) -> int:
    return sum(len(tuple(pattern.finditer(value))) for value in values)


def _claim_source_rule_matches(
    source: str,
    *,
    repository_path: str,
    source_kind: ClaimSourceKind,
) -> tuple[ClaimSourceRuleMatch, ...]:
    normalized = _normalized_source_text(source)
    if source_kind in {
        ClaimSourceKind.API_PYTHON,
        ClaimSourceKind.PYTHON_TEST,
    }:
        semantic_units = _python_semantic_units(
            normalized,
            repository_path=repository_path,
        )
    elif source_kind in {
        ClaimSourceKind.FRONTEND_PUBLIC_SOURCE,
        ClaimSourceKind.FRONTEND_TEST,
    }:
        semantic_units = _typescript_semantic_units(normalized)
    elif source_kind is ClaimSourceKind.SCENARIO_YAML:
        semantic_units = _scenario_yaml_semantic_units(
            normalized,
            repository_path=repository_path,
        )
    else:
        semantic_units = _markdown_semantic_units(normalized)

    counts: dict[ClaimSourceRule, int] = {
        ClaimSourceRule.HISTORICAL_OUTCOME_COOCCURRENCE: _pattern_occurrences(
            _HISTORICAL_OUTCOME_PATTERN,
            semantic_units,
        ),
        ClaimSourceRule.HISTORICAL_STATUS_VOCABULARY: len(
            tuple(
                _HISTORICAL_STATUS_PATTERN.finditer(
                    _searchable_unit(normalized),
                ),
            ),
        ),
        ClaimSourceRule.LEGACY_BOOLEAN_API: len(
            tuple(_LEGACY_BOOLEAN_API_PATTERN.finditer(normalized)),
        ),
        ClaimSourceRule.LEGACY_CLAIM_API: len(
            tuple(_LEGACY_CLAIM_API_PATTERN.finditer(normalized)),
        ),
        ClaimSourceRule.OUTCOME_ENVELOPE: _pattern_occurrences(
            _OUTCOME_ENVELOPE_PATTERN,
            semantic_units,
        ),
        ClaimSourceRule.REGRESSION_SNAPSHOT: len(
            tuple(_REGRESSION_SNAPSHOT_PATTERN.finditer(normalized)),
        ),
        ClaimSourceRule.SCENARIO_STATUS_ALIAS: (
            _pattern_occurrences(_SCENARIO_STATUS_PATTERN, semantic_units)
            if source_kind
            in {
                ClaimSourceKind.API_PYTHON,
                ClaimSourceKind.FRONTEND_PUBLIC_SOURCE,
                ClaimSourceKind.FRONTEND_TEST,
                ClaimSourceKind.PUBLIC_DOCUMENT,
                ClaimSourceKind.SCENARIO_YAML,
                ClaimSourceKind.WORKFLOW_DOCUMENT,
            }
            or repository_path.startswith("tests/validation/")
            else len(tuple(re.finditer(r"\bHISTORICAL_WINNERS\b", normalized)))
        ),
    }
    return tuple(
        ClaimSourceRuleMatch(
            rule_id=rule_id,
            occurrences=counts[rule_id],
        )
        for rule_id in sorted(counts, key=lambda item: item.value)
        if counts[rule_id]
    )


def scan_historical_claim_sources(
    repository_root: str | Path,
    *,
    source_kinds: frozenset[ClaimSourceKind] | None = None,
) -> tuple[HistoricalClaimSourceCandidate, ...]:
    """Discover every closed-vocabulary candidate in the selected source kinds."""
    root = Path(repository_root).resolve(strict=True)
    selected_kinds = _ALL_CLAIM_SOURCE_KINDS if source_kinds is None else frozenset(source_kinds)
    if any(not isinstance(kind, ClaimSourceKind) for kind in selected_kinds):
        raise ValueError("source_kinds must contain only ClaimSourceKind values")
    discovered: dict[str, ClaimSourceKind] = {}

    def register(path: Path, source_kind: ClaimSourceKind) -> None:
        if source_kind not in selected_kinds:
            return
        repository_path = path.relative_to(root).as_posix()
        existing = discovered.get(repository_path)
        if existing is not None and existing is not source_kind:
            raise ValueError(
                "historical-claim source matched multiple kinds: "
                f"{repository_path!r} / {existing.value!r} / "
                f"{source_kind.value!r}",
            )
        discovered[repository_path] = source_kind

    tests_root = root / "tests"
    if tests_root.is_dir():
        for path in tests_root.rglob("*.py"):
            register(path, ClaimSourceKind.PYTHON_TEST)

    for root_document in ("README.md", "CLAUDE.md"):
        if (root / root_document).exists():
            register(root / root_document, ClaimSourceKind.PUBLIC_DOCUMENT)
    docs_root = root / "docs"
    if docs_root.is_dir():
        for path in docs_root.rglob("*.md"):
            register(path, ClaimSourceKind.PUBLIC_DOCUMENT)

    api_root = root / "api"
    if api_root.is_dir():
        for path in api_root.rglob("*.py"):
            register(path, ClaimSourceKind.API_PYTHON)

    frontend_root = root / "frontend/src"
    if frontend_root.is_dir():
        for path in frontend_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
                continue
            relative = path.relative_to(root).as_posix()
            if _is_frontend_declaration_source(relative):
                continue
            register(
                path,
                (
                    ClaimSourceKind.FRONTEND_TEST
                    if _is_frontend_test_source(relative)
                    else ClaimSourceKind.FRONTEND_PUBLIC_SOURCE
                ),
            )

    data_root = root / "data"
    if data_root.is_dir():
        for path in data_root.rglob("scenario.yaml"):
            register(path, ClaimSourceKind.SCENARIO_YAML)

    for workflow_root in (root / ".agents/skills", root / ".claude/skills"):
        if workflow_root.is_dir():
            for path in workflow_root.rglob("SKILL.md"):
                register(path, ClaimSourceKind.WORKFLOW_DOCUMENT)

    candidates: list[HistoricalClaimSourceCandidate] = []
    for repository_path, source_kind in sorted(
        discovered.items(),
        key=lambda item: (item[1].value, item[0]),
    ):
        if not _claim_source_path_matches_kind(repository_path, source_kind):
            raise ValueError(
                "discovered historical-claim source has an invalid kind/path: "
                f"{repository_path!r} / {source_kind.value!r}",
            )
        path = resolve_repository_path(
            root,
            repository_path,
            field_name="historical claim candidate source",
        )
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(
                f"cannot read historical-claim source {repository_path!r}",
            ) from exc
        matches = _claim_source_rule_matches(
            source,
            repository_path=repository_path,
            source_kind=source_kind,
        )
        if not matches:
            continue
        candidates.append(
            HistoricalClaimSourceCandidate(
                repository_path=repository_path,
                source_kind=source_kind,
                source_sha256=_source_sha256(source),
                matches=matches,
            ),
        )
    return tuple(candidates)


def _obsolete_boolean_historical_apis(repository_root: Path) -> tuple[str, ...]:
    """Find unreviewable boolean historical verdict APIs in production code."""
    violations: set[str] = set()
    for relative_root in (
        Path("stochastic_warfare/tools"),
        Path("stochastic_warfare/validation"),
    ):
        source_root = repository_root / relative_root
        if not source_root.is_dir():
            continue
        for path in sorted(source_root.rglob("*.py")):
            relative = path.relative_to(repository_root).as_posix()
            checked_path = resolve_repository_path(
                repository_root,
                relative,
                field_name="historical verdict production source",
            )
            try:
                source = checked_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
            except (OSError, UnicodeError, SyntaxError) as exc:
                raise ValueError(
                    f"cannot audit historical verdict production source {relative!r}",
                ) from exc
            for node in ast.walk(tree):
                if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                    if node.name in _OBSOLETE_BOOLEAN_API_NAMES:
                        violations.add(f"{relative}:{node.name}")
                        continue
                    contract = f"{node.name} {ast.get_docstring(node) or ''}"
                    if (
                        re.search(r"histor|envelope|backtest", contract, re.IGNORECASE)
                        and node.returns is not None
                        and re.search(r"\bbool\b", ast.unparse(node.returns))
                    ):
                        violations.add(f"{relative}:{node.name}")
                elif (isinstance(node, ast.Attribute) and node.attr == "all_within_tolerance") or (
                    isinstance(node, ast.Name) and node.id == "all_within_tolerance"
                ):
                    violations.add(f"{relative}:all_within_tolerance")
    return tuple(sorted(violations))


class YamlPathLocator(_StrictFrozenModel):
    """Select one exact subtree from strict YAML."""

    kind: Literal["yaml_path"]
    segments: tuple[str, ...]

    @field_validator("segments", mode="before")
    @classmethod
    def _ordered_segments(cls, value: Any) -> tuple[Any, ...]:
        return _ordered_tuple(value, field_name="segments")

    @field_validator("segments")
    @classmethod
    def _valid_segments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("segments must be non-empty")
        for segment in value:
            _trimmed_text(segment, field_name="YAML path segment")
        return value


class TokenLinesLocator(_StrictFrozenModel):
    """Select every exact source line containing one token."""

    kind: Literal["token_lines"]
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def _valid_token(cls, value: Any) -> str:
        return _trimmed_text(value, field_name="token")


class PythonSymbolLocator(_StrictFrozenModel):
    """Select one exact top-level Python definition or assignment."""

    kind: Literal["python_symbol"]
    symbol: str

    @field_validator("symbol", mode="before")
    @classmethod
    def _valid_symbol(cls, value: Any) -> str:
        return _trimmed_text(value, field_name="symbol")


class RequiredTextLocator(_StrictFrozenModel):
    """Require an exact truthful control string to remain present."""

    kind: Literal["required_text"]
    text: str
    expected_occurrences: int

    @field_validator("text", mode="before")
    @classmethod
    def _valid_text(cls, value: Any) -> str:
        return _trimmed_text(value, field_name="required text")

    @field_validator("expected_occurrences", mode="before")
    @classmethod
    def _valid_occurrences(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("expected_occurrences must be a positive integer")
        return value


class ForbiddenTextLocator(_StrictFrozenModel):
    """Require an obsolete or unsupported claim string to remain absent."""

    kind: Literal["forbidden_text"]
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _valid_text(cls, value: Any) -> str:
        return _trimmed_text(value, field_name="forbidden text")


ClaimLocator = Annotated[
    YamlPathLocator | TokenLinesLocator | PythonSymbolLocator | RequiredTextLocator | ForbiddenTextLocator,
    Field(discriminator="kind"),
]


class AcceptedMetricBinding(_StrictFrozenModel):
    """Exact claim metric mapped to one accepted gating metric."""

    claim_metric: str
    study_metric_id: str

    @field_validator("claim_metric", "study_metric_id", mode="before")
    @classmethod
    def _valid_text(cls, value: Any, info: Any) -> str:
        return _trimmed_text(value, field_name=info.field_name)


class AcceptedHistoricalEvidence(_StrictFrozenModel):
    """One explicitly accepted production backtest artifact."""

    study_id: str
    artifact_path: str
    artifact_sha256: str
    metric_bindings: tuple[AcceptedMetricBinding, ...]

    @field_validator("study_id", mode="before")
    @classmethod
    def _valid_study_id(cls, value: Any) -> str:
        return require_stable_id(value, field_name="study_id")

    @field_validator("artifact_path", mode="before")
    @classmethod
    def _valid_artifact_path(cls, value: Any) -> str:
        path = _repository_relative_path(value, field_name="artifact_path")
        if not path.startswith("docs/evidence/") or not path.endswith(".json"):
            raise ValueError("artifact_path must be a JSON file below docs/evidence")
        return path

    @field_validator("artifact_sha256", mode="before")
    @classmethod
    def _valid_artifact_digest(cls, value: Any) -> str:
        digest = _sha256(value, field_name="artifact_sha256")
        if len(set(digest)) == 1:
            raise ValueError("artifact_sha256 must not be a sentinel digest")
        return digest

    @field_validator("metric_bindings", mode="before")
    @classmethod
    def _ordered_bindings(cls, value: Any) -> tuple[Any, ...]:
        return _ordered_tuple(value, field_name="metric_bindings")

    @model_validator(mode="after")
    def _unique_bindings(self) -> Self:
        claim_metrics = tuple(binding.claim_metric for binding in self.metric_bindings)
        study_metrics = tuple(binding.study_metric_id for binding in self.metric_bindings)
        if len(claim_metrics) != len(set(claim_metrics)):
            raise ValueError("accepted claim metric bindings must be duplicate-free")
        if len(study_metrics) != len(set(study_metrics)):
            raise ValueError("accepted study metric bindings must be duplicate-free")
        if any(
            claim_metric != study_metric
            for claim_metric, study_metric in zip(
                claim_metrics,
                study_metrics,
                strict=True,
            )
        ):
            raise ValueError(
                "accepted claim metrics must use the exact typed study metric identity",
            )
        return self


class HistoricalClaim(_StrictFrozenModel):
    """One exact repository claim and its conservative disposition."""

    claim_id: str
    repository_path: str
    scenario_path: str | None
    surface: ClaimSurface
    locator: ClaimLocator
    content_sha256: str
    disposition: ClaimDisposition
    metric_scope: tuple[str, ...]
    reason_codes: tuple[str, ...]
    limitation: str
    current_engine_regression_evidence: bool
    accepted_evidence: AcceptedHistoricalEvidence | None

    @field_validator("surface", mode="before")
    @classmethod
    def _valid_surface(cls, value: Any) -> ClaimSurface:
        if isinstance(value, ClaimSurface):
            return value
        if not isinstance(value, str):
            raise ValueError("surface must be a strict claim-surface string")
        try:
            return ClaimSurface(value)
        except ValueError as exc:
            raise ValueError(f"unsupported claim surface {value!r}") from exc

    @field_validator("disposition", mode="before")
    @classmethod
    def _valid_disposition(cls, value: Any) -> ClaimDisposition:
        if isinstance(value, ClaimDisposition):
            return value
        if not isinstance(value, str):
            raise ValueError("disposition must be a strict disposition string")
        try:
            return ClaimDisposition(value)
        except ValueError as exc:
            raise ValueError(f"unsupported claim disposition {value!r}") from exc

    @field_validator("claim_id", mode="before")
    @classmethod
    def _valid_claim_id(cls, value: Any) -> str:
        return require_stable_id(value, field_name="claim_id")

    @field_validator("repository_path", mode="before")
    @classmethod
    def _valid_repository_path(cls, value: Any) -> str:
        return _repository_relative_path(
            value,
            field_name="repository_path",
        )

    @field_validator("scenario_path", mode="before")
    @classmethod
    def _valid_scenario_path(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _repository_relative_path(value, field_name="scenario_path")

    @field_validator("content_sha256", mode="before")
    @classmethod
    def _valid_content_digest(cls, value: Any) -> str:
        return _sha256(value, field_name="content_sha256")

    @field_validator("metric_scope", "reason_codes", mode="before")
    @classmethod
    def _ordered_fields(cls, value: Any, info: Any) -> tuple[Any, ...]:
        return _ordered_tuple(value, field_name=info.field_name)

    @field_validator("metric_scope")
    @classmethod
    def _valid_metric_scope(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        for metric in value:
            _trimmed_text(metric, field_name="metric name")
        if len(value) != len(set(value)):
            raise ValueError("metric_scope must be duplicate-free")
        return value

    @field_validator("reason_codes")
    @classmethod
    def _valid_reason_codes(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not value:
            raise ValueError("reason_codes must be non-empty")
        for reason in value:
            require_stable_id(reason, field_name="reason code")
        if len(value) != len(set(value)):
            raise ValueError("reason_codes must be duplicate-free")
        return value

    @field_validator("limitation", mode="before")
    @classmethod
    def _valid_limitation(cls, value: Any) -> str:
        return _trimmed_text(value, field_name="limitation")

    @model_validator(mode="after")
    def _consistent_classification(self) -> Self:
        scenario_surface = self.surface in {
            ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES,
            ClaimSurface.SCENARIO_HISTORICAL_PROSE,
        }
        if scenario_surface and self.scenario_path != self.repository_path:
            raise ValueError(
                "scenario claim scenario_path must equal repository_path",
            )
        if self.surface is ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES:
            if not self.metric_scope:
                raise ValueError(
                    "scenario documented_outcomes claim needs metric_scope",
                )
            if not isinstance(self.locator, YamlPathLocator):
                raise ValueError(
                    "scenario documented_outcomes requires yaml_path locator",
                )
        elif self.surface is not ClaimSurface.SCENARIO_HISTORICAL_PROSE and self.metric_scope:
            raise ValueError(
                "metric_scope is reserved for scenario historical claims",
            )
        if (self.disposition is ClaimDisposition.PRODUCTION_VALIDATED) != (self.accepted_evidence is not None):
            raise ValueError(
                "production_validated and accepted_evidence must appear together",
            )
        if self.accepted_evidence is not None:
            bound_claim_metrics = tuple(binding.claim_metric for binding in self.accepted_evidence.metric_bindings)
            if not self.metric_scope or bound_claim_metrics != self.metric_scope:
                raise ValueError(
                    "production_validated requires exact full claim metric bindings",
                )
        if (
            self.disposition is ClaimDisposition.CURRENT_ENGINE_REGRESSION_ONLY
            and not self.current_engine_regression_evidence
        ):
            raise ValueError(
                "current_engine_regression_only requires regression evidence",
            )
        return self


class ClaimLedgerAudit(_StrictFrozenModel):
    """Fresh repository inventory and digest-audit result."""

    scenario_collections: int
    scenario_metrics: int
    python_test_surfaces: int
    frontend_test_surfaces: int
    documentation_claims: int
    documentation_claim_paths: int
    api_python_candidate_paths: int
    frontend_public_candidate_paths: int
    frontend_test_candidate_paths: int
    python_test_candidate_paths: int
    public_document_candidate_paths: int
    scenario_yaml_candidate_paths: int
    workflow_document_candidate_paths: int
    claim_bound_source_reviews: int
    reviewed_nonclaim_source_reviews: int
    production_validated_claims: int
    uninventoried_scenario_collections: tuple[str, ...]
    missing_scenario_collections: tuple[str, ...]
    unreviewed_claim_source_paths: tuple[str, ...]
    stale_claim_source_reviews: tuple[str, ...]
    claim_source_digest_mismatches: tuple[str, ...]
    claim_source_rule_mismatches: tuple[str, ...]
    claim_source_binding_errors: tuple[str, ...]
    forbidden_boolean_historical_apis: tuple[str, ...]
    digest_mismatches: tuple[str, ...]


class HistoricalClaimSummary(_StrictFrozenModel):
    """Public claim-level scenario classification."""

    claim_id: str
    disposition: ClaimDisposition
    reason_codes: tuple[str, ...]
    limitation: str
    intended_use: str
    metric_scope: tuple[str, ...]
    event_scope: str
    current_engine_regression_evidence: bool
    accepted_study_id: str | None
    accepted_artifact_path: str | None


class ScenarioHistoricalValidationSummary(_StrictFrozenModel):
    """Conservative aggregation for one exact scenario source path."""

    claims: tuple[HistoricalClaimSummary, ...]
    aggregate_disposition: ClaimDisposition
    accepted_claim_ids: tuple[str, ...]
    current_engine_regression_evidence: bool
    ledger_sha256: str


class HistoricalClaimLedger(_StrictFrozenModel):
    """Strict loaded ledger bound to one repository tree."""

    schema_version: Literal[1]
    ledger_id: str
    claim_source_scanner_version: Literal[2]
    claim_source_reviews: tuple[ReviewedClaimSource, ...]
    claims: tuple[HistoricalClaim, ...]
    ledger_sha256: str

    _repository_root: Path = PrivateAttr()
    _ledger_path: Path = PrivateAttr()
    _accepted_artifacts: dict[str, Any] = PrivateAttr(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be the strict integer 1")
        return value

    @field_validator("ledger_id", mode="before")
    @classmethod
    def _valid_ledger_id(cls, value: Any) -> str:
        return require_stable_id(value, field_name="ledger_id")

    @field_validator("claim_source_scanner_version", mode="before")
    @classmethod
    def _claim_source_scanner_version(cls, value: Any) -> int:
        if type(value) is not int or value != 2:
            raise ValueError("claim_source_scanner_version must be the strict integer 2")
        return value

    @field_validator("claim_source_reviews", "claims", mode="before")
    @classmethod
    def _ordered_collections(cls, value: Any, info: Any) -> tuple[Any, ...]:
        return _ordered_tuple(value, field_name=info.field_name)

    @field_validator("ledger_sha256", mode="before")
    @classmethod
    def _valid_ledger_digest(cls, value: Any) -> str:
        return _sha256(value, field_name="ledger_sha256")

    @model_validator(mode="after")
    def _unique_claims(self) -> Self:
        claim_ids = [claim.claim_id for claim in self.claims]
        if not claim_ids:
            raise ValueError("claims must be non-empty")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        if claim_ids != sorted(claim_ids):
            raise ValueError("claims must be ordered by stable claim_id")
        locator_keys = [
            (
                claim.repository_path,
                _canonical_sha256(claim.locator.model_dump(mode="json")),
            )
            for claim in self.claims
        ]
        if len(locator_keys) != len(set(locator_keys)):
            raise ValueError("claim path/locator identities must be unique")

        review_keys = [(review.source_kind.value, review.repository_path) for review in self.claim_source_reviews]
        if review_keys != sorted(set(review_keys)):
            raise ValueError(
                "claim-source reviews must be sorted and path-unique",
            )
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        relevant_claim_ids: set[str] = set()
        bound_claim_ids: set[str] = set()
        for claim in self.claims:
            if claim.surface in _REVIEWED_CLAIM_SURFACES:
                relevant_claim_ids.add(claim.claim_id)
        for review in self.claim_source_reviews:
            allowed_surfaces = _CLAIM_SURFACES_BY_SOURCE_KIND[review.source_kind]
            for claim_id in review.claim_ids:
                claim = claims_by_id.get(claim_id)
                if claim is None:
                    raise ValueError(
                        f"claim-source review references unknown claim {claim_id!r}",
                    )
                if claim.repository_path != review.repository_path or claim.surface not in allowed_surfaces:
                    raise ValueError(
                        f"claim-source review has incompatible claim {claim_id!r}",
                    )
            compatible_ids = tuple(
                sorted(
                    claim.claim_id
                    for claim in self.claims
                    if claim.repository_path == review.repository_path and claim.surface in allowed_surfaces
                ),
            )
            if review.exclusion is not None:
                if compatible_ids:
                    raise ValueError(
                        f"claim-source exclusion cannot conceal compatible ledger claims: {review.repository_path!r}",
                    )
                continue
            if review.claim_ids != compatible_ids:
                raise ValueError(
                    f"claim-source review must bind every compatible claim on its path: {review.repository_path!r}",
                )
            bound_claim_ids.update(review.claim_ids)
        if bound_claim_ids != relevant_claim_ids:
            missing = tuple(sorted(relevant_claim_ids - bound_claim_ids))
            extra = tuple(sorted(bound_claim_ids - relevant_claim_ids))
            raise ValueError(
                "claim-source reviews do not exactly bind claim-bearing source claims: "
                f"missing={missing!r} extra={extra!r}",
            )
        return self

    def claim_by_id(self, claim_id: str) -> HistoricalClaim:
        """Return one exact strict claim or reject an absent identity."""
        stable_id = require_stable_id(claim_id, field_name="claim_id")
        for claim in self.claims:
            if claim.claim_id == stable_id:
                return claim
        raise KeyError(stable_id)

    def _resolve_repository_path(self, relative_path: str) -> Path:
        return resolve_repository_path(
            self._repository_root,
            relative_path,
            field_name="claim repository_path",
        )

    @staticmethod
    def _python_symbol_source(source: str, symbol: str) -> str:
        tree = ast.parse(source)
        matches: list[ast.AST] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol:
                    matches.append(node)
            elif isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == symbol for target in node.targets):
                    matches.append(node)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == symbol:
                    matches.append(node)
        if len(matches) != 1:
            raise ValueError(
                f"Python symbol {symbol!r} resolved {len(matches)} times",
            )
        selected = ast.get_source_segment(source, matches[0])
        if selected is None:
            raise ValueError(f"Cannot extract Python symbol {symbol!r}")
        return selected.replace("\r\n", "\n").strip()

    def _normalized_claim_content(self, claim: HistoricalClaim) -> Any:
        path = self._resolve_repository_path(claim.repository_path)
        locator = claim.locator
        if isinstance(locator, YamlPathLocator):
            raw = load_yaml_unique(path.read_text(encoding="utf-8"))
            selected: Any = raw
            for segment in locator.segments:
                if not isinstance(selected, Mapping) or segment not in selected:
                    raise ValueError(
                        f"YAML locator for {claim.claim_id!r} is absent at {segment!r}",
                    )
                selected = selected[segment]
            return {
                "kind": locator.kind,
                "segments": list(locator.segments),
                "content": selected,
            }
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if isinstance(locator, TokenLinesLocator):
            lines = [line for line in source.splitlines() if locator.token in line]
            if not lines:
                raise ValueError(
                    f"Token {locator.token!r} is absent for {claim.claim_id!r}",
                )
            return {
                "kind": locator.kind,
                "token": locator.token,
                "lines": lines,
            }
        if isinstance(locator, PythonSymbolLocator):
            return {
                "kind": locator.kind,
                "symbol": locator.symbol,
                "source": self._python_symbol_source(source, locator.symbol),
            }
        if isinstance(locator, RequiredTextLocator):
            occurrences = source.count(locator.text)
            if occurrences != locator.expected_occurrences:
                raise ValueError(
                    f"Required text for {claim.claim_id!r} occurred "
                    f"{occurrences} times, expected "
                    f"{locator.expected_occurrences}",
                )
            return {
                "kind": locator.kind,
                "text": locator.text,
                "occurrences": occurrences,
            }
        if isinstance(locator, ForbiddenTextLocator):
            occurrences = source.count(locator.text)
            if occurrences:
                raise ValueError(
                    f"Forbidden text for {claim.claim_id!r} occurred {occurrences} times",
                )
            return {
                "kind": locator.kind,
                "text": locator.text,
                "occurrences": 0,
            }
        raise TypeError(f"Unsupported claim locator {type(locator).__name__}")

    def _digest_mismatches(
        self,
        claims: tuple[HistoricalClaim, ...] | None = None,
    ) -> tuple[str, ...]:
        mismatches: list[str] = []
        for claim in self.claims if claims is None else claims:
            try:
                normalized = self._normalized_claim_content(claim)
                if claim.surface is ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES:
                    outcomes = normalized.get("content")
                    if not isinstance(outcomes, list):
                        raise ValueError("documented_outcomes must be a list")
                    names = tuple(outcome.get("name") if isinstance(outcome, Mapping) else None for outcome in outcomes)
                    if (
                        any(not isinstance(name, str) or not name or name != name.strip() for name in names)
                        or len(names) != len(set(names))
                        or names != claim.metric_scope
                    ):
                        raise ValueError(
                            "documented_outcomes names do not exactly match metric_scope",
                        )
                observed = _canonical_sha256(normalized)
            except (OSError, SyntaxError, TypeError, ValueError):
                mismatches.append(claim.claim_id)
                continue
            if observed != claim.content_sha256:
                mismatches.append(claim.claim_id)
        return tuple(mismatches)

    def _resolve_accepted_artifact(self, relative_path: str) -> Path:
        return resolve_repository_path(
            self._repository_root,
            relative_path,
            field_name="accepted artifact path",
        )

    def _load_accepted_artifact(
        self,
        claim_id: str,
        accepted: AcceptedHistoricalEvidence,
        loaded_by_path: dict[Path, CompletedHistoricalArtifact],
    ) -> tuple[Path, CompletedHistoricalArtifact]:
        from .artifacts import CompletedHistoricalArtifact, load_historical_artifact

        try:
            artifact_path = self._resolve_accepted_artifact(
                accepted.artifact_path,
            )
            artifact = loaded_by_path.get(artifact_path)
            if artifact is None:
                artifact = load_historical_artifact(artifact_path)
                loaded_by_path[artifact_path] = artifact
        except (OSError, TypeError, ValueError) as exc:
            raise ValueError(
                f"accepted artifact for {claim_id!r} is unavailable or invalid",
            ) from exc
        if not isinstance(artifact, CompletedHistoricalArtifact):
            raise ValueError(
                f"accepted artifact for {claim_id!r} is not completed evidence",
            )
        return artifact_path, artifact

    @staticmethod
    def _validate_accepted_reference(
        claim: HistoricalClaim,
        accepted: AcceptedHistoricalEvidence,
        artifact: CompletedHistoricalArtifact,
    ) -> None:
        if (
            artifact.artifact_sha256 != accepted.artifact_sha256
            or artifact.study_id != accepted.study_id
            or artifact.status != "PASS"
            or not artifact.eligibility.promotion_eligible
            or artifact.eligibility.reason_codes
            or artifact.execution.code_revision.dirty
        ):
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} is not promotion-eligible PASS evidence",
            )

    def _validate_claim_metric_evidence(
        self,
        claim: HistoricalClaim,
        accepted: AcceptedHistoricalEvidence,
        artifact: CompletedHistoricalArtifact,
    ) -> None:
        from .studies import HistoricalMetricPlan

        gating_metrics = {metric.metric_id: metric for metric in artifact.plan.gating_metrics}
        bound_study_metrics = tuple(binding.study_metric_id for binding in accepted.metric_bindings)
        if any(metric_id not in gating_metrics for metric_id in bound_study_metrics):
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} does not bind every claim metric to a gating metric",
            )
        if claim.surface is not ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES:
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} lacks a typed scenario outcome surface",
            )
        if (
            claim.scenario_path is None
            or claim.repository_path != claim.scenario_path
            or claim.scenario_path != artifact.plan.scenario_path
            or claim.scenario_path != artifact.execution.scenario_path
        ):
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} executed a different scenario",
            )
        normalized_claim = self._normalized_claim_content(claim)
        outcomes = normalized_claim.get("content")
        if not isinstance(outcomes, list):
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} has no typed outcome collection",
            )
        outcome_by_name = {
            outcome.get("name"): outcome
            for outcome in outcomes
            if isinstance(outcome, Mapping) and isinstance(outcome.get("name"), str)
        }
        for metric_binding in accepted.metric_bindings:
            outcome = outcome_by_name.get(metric_binding.claim_metric)
            gating_metric = gating_metrics[metric_binding.study_metric_id]
            if outcome is None:
                raise ValueError(
                    f"accepted artifact for {claim.claim_id!r} is missing a bound claim metric",
                )
            try:
                claim_metric_contract = HistoricalMetricPlan.model_validate(
                    outcome.get("production_validation_metric"),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"accepted artifact for {claim.claim_id!r} lacks an exact typed claim metric contract",
                ) from exc
            claim_value = outcome.get("value")
            if (
                claim_metric_contract != gating_metric
                or claim_metric_contract.metric_id != metric_binding.study_metric_id
                or outcome.get("unit") != gating_metric.source_unit
                or isinstance(claim_value, bool)
                or not isinstance(claim_value, (int, float))
                or not math.isfinite(float(claim_value))
                or not gating_metric.source_range.minimum <= float(claim_value) <= gating_metric.source_range.maximum
            ):
                raise ValueError(
                    f"accepted artifact for {claim.claim_id!r} claim/study metric semantics differ",
                )
        bindings = {binding.claim_id: binding for binding in artifact.claim_bindings}
        binding = bindings.get(claim.claim_id)
        if binding is None or (
            binding.repository_path != claim.repository_path or binding.content_sha256 != claim.content_sha256
        ):
            raise ValueError(
                f"accepted artifact for {claim.claim_id!r} does not bind the current claim",
            )

    def _verify_accepted_artifact(
        self,
        artifact: CompletedHistoricalArtifact,
        *,
        claim_id: str,
        canonical_ledger_path: str,
    ) -> None:
        from stochastic_warfare.simulation.runtime import (
            AnalysisVariant,
            SimulationRuntimeFactory,
        )

        from .studies import HistoricalStudyLoader

        if artifact.execution_ledger_path != canonical_ledger_path:
            raise ValueError(
                f"accepted artifact for {claim_id!r} used a noncanonical execution ledger",
            )
        receipt = artifact.execution.predeclaration_receipt
        if receipt is None:
            raise ValueError(
                f"accepted artifact for {claim_id!r} lacks predeclaration evidence",
            )
        commit = artifact.execution.code_revision.commit
        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "merge-base",
                    "--is-ancestor",
                    commit,
                    "HEAD",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "merge-base",
                    "--is-ancestor",
                    receipt.revision,
                    commit,
                ],
                check=True,
                capture_output=True,
            )
            committed_ledger = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "show",
                    f"{commit}:{artifact.execution_ledger_path}",
                ],
                check=True,
                capture_output=True,
            ).stdout.decode("utf-8")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "diff",
                    "--quiet",
                    commit,
                    "HEAD",
                    "--",
                    "stochastic_warfare",
                    "api",
                    "scripts/run_historical_backtest.py",
                    "pyproject.toml",
                    "uv.lock",
                ],
                check=True,
                capture_output=True,
            )
        except (
            OSError,
            subprocess.CalledProcessError,
            UnicodeDecodeError,
        ) as exc:
            raise ValueError(
                f"accepted artifact for {claim_id!r} code/ledger revision cannot be verified",
            ) from exc
        committed_ledger_raw = load_yaml_unique(io.StringIO(committed_ledger))
        if not isinstance(committed_ledger_raw, Mapping):
            raise ValueError(
                f"accepted artifact for {claim_id!r} execution ledger is invalid",
            )
        committed_ledger_model = HistoricalClaimLedger.model_validate(
            committed_ledger_raw,
        )
        committed_ledger_payload = dict(committed_ledger_raw)
        committed_ledger_digest = committed_ledger_payload.pop(
            "ledger_sha256",
            None,
        )
        if (
            committed_ledger_digest != artifact.execution_ledger_sha256
            or _canonical_sha256(committed_ledger_payload) != artifact.execution_ledger_sha256
        ):
            raise ValueError(
                f"accepted artifact for {claim_id!r} execution ledger drifted",
            )
        committed_by_id = {entry.claim_id: entry for entry in committed_ledger_model.claims}
        for artifact_binding in artifact.claim_bindings:
            committed_claim = committed_by_id.get(artifact_binding.claim_id)
            if committed_claim is None or (
                committed_claim.repository_path != artifact_binding.repository_path
                or committed_claim.content_sha256 != artifact_binding.content_sha256
            ):
                raise ValueError(
                    f"accepted artifact for {claim_id!r} is not bound to its execution ledger claims",
                )
        loaded_plan = HistoricalStudyLoader(self._repository_root).load(
            self._repository_root / receipt.plan_repository_path,
        )
        if loaded_plan.plan_sha256 != artifact.plan_sha256 or loaded_plan.predeclaration_receipt != receipt:
            raise ValueError(
                f"accepted artifact for {claim_id!r} plan proof drifted",
            )
        prepared = SimulationRuntimeFactory().prepare(
            self._repository_root / loaded_plan.scenario_path,
            self._repository_root / loaded_plan.data_root,
            (
                AnalysisVariant(
                    variant_id=loaded_plan.analysis.variant_id,
                    calibration_patch=loaded_plan.analysis.calibration_patch,
                ),
            ),
        )
        variant = prepared.variant(loaded_plan.analysis.variant_id)
        session = prepared.build(
            variant,
            seed=loaded_plan.held_out_seeds[0],
            max_ticks=loaded_plan.maximum_ticks,
        )
        units_by_id = {
            unit.entity_id: unit for side_units in session.context.units_by_side.values() for unit in side_units
        }
        current_typed_roster = tuple(
            (
                assignment.unit_id,
                units_by_id[assignment.unit_id].unit_type,
                assignment.side,
            )
            for assignment in session.initial_unit_assignments
        )
        artifact_typed_roster = tuple(
            (unit.unit_id, unit.unit_type, unit.side) for unit in artifact.execution.loaded_typed_roster
        )
        current_assignments = tuple(
            (
                assignment.unit_id,
                assignment.side,
                assignment.commander_profile_id,
                assignment.doctrine_school_id,
            )
            for assignment in session.initial_unit_assignments
        )
        artifact_assignments = tuple(
            (
                assignment.unit_id,
                assignment.side,
                assignment.commander_profile_id,
                assignment.doctrine_school_id,
            )
            for assignment in artifact.execution.initial_unit_assignments
        )
        if (
            prepared.code_revision.dirty
            or prepared.source_fingerprint != artifact.execution.source_fingerprint
            or variant.config_fingerprint != artifact.execution.config_fingerprint
            or prepared.authored_roster != artifact.execution.authored_roster
            or prepared.data_revision != artifact.execution.data_revision
            or prepared.data_file_count != artifact.execution.data_file_count
            or variant.era_runtime_contract.selected_registry_id != artifact.execution.effective_era_id
            or _canonical_sha256(variant.era_config.model_dump(mode="json")) != artifact.execution.era_config_sha256
            or _canonical_sha256(
                variant.era_runtime_contract.model_dump(mode="json"),
            )
            != artifact.execution.era_runtime_contract_sha256
            or session.loaded_roster != artifact.execution.loaded_roster
            or current_typed_roster != artifact_typed_roster
            or session.catalog_revision != artifact.execution.catalog_revision
            or session.doctrine_catalog_fingerprint != artifact.execution.doctrine_catalog_fingerprint
            or session.loaded_roster_loadout_fingerprint != artifact.execution.loaded_roster_loadout_fingerprint
            or current_assignments != artifact_assignments
        ):
            raise ValueError(
                f"accepted artifact for {claim_id!r} production inputs drifted",
            )

    def _validate_accepted_evidence(self) -> None:
        accepted_artifacts: dict[str, CompletedHistoricalArtifact] = {}
        loaded_by_path: dict[Path, CompletedHistoricalArtifact] = {}
        verified_artifacts: set[tuple[Path, str]] = set()
        canonical_ledger_path = self._ledger_path.relative_to(
            self._repository_root,
        ).as_posix()
        for claim in self.claims:
            accepted = claim.accepted_evidence
            if accepted is None:
                continue
            artifact_path, artifact = self._load_accepted_artifact(
                claim.claim_id,
                accepted,
                loaded_by_path,
            )
            self._validate_accepted_reference(claim, accepted, artifact)
            artifact_identity = (artifact_path, artifact.artifact_sha256)
            if artifact_identity not in verified_artifacts:
                self._verify_accepted_artifact(
                    artifact,
                    claim_id=claim.claim_id,
                    canonical_ledger_path=canonical_ledger_path,
                )
                verified_artifacts.add(artifact_identity)
            self._validate_claim_metric_evidence(claim, accepted, artifact)
            accepted_artifacts[claim.claim_id] = artifact
        object.__setattr__(self, "_accepted_artifacts", accepted_artifacts)

    def _scenario_collection_inventory(self) -> dict[str, int]:
        """Return every exact shipped documented-outcome collection."""
        actual_collections: dict[str, int] = {}
        for scenario_path in sorted(
            (self._repository_root / "data").rglob("scenario.yaml"),
        ):
            relative = scenario_path.relative_to(
                self._repository_root,
            ).as_posix()
            checked_path = resolve_repository_path(
                self._repository_root,
                relative,
                field_name="scenario collection source",
            )
            raw = load_yaml_unique(checked_path.read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping) or "documented_outcomes" not in raw:
                continue
            outcomes = raw["documented_outcomes"]
            if not isinstance(outcomes, list) or not outcomes:
                raise ValueError(
                    f"documented_outcomes must be a non-empty list: {scenario_path}",
                )
            names = [outcome.get("name") if isinstance(outcome, Mapping) else None for outcome in outcomes]
            if any(not isinstance(name, str) or not name or name != name.strip() for name in names) or len(
                names
            ) != len(set(names)):
                raise ValueError(
                    f"documented_outcomes must have unique non-empty names: {scenario_path}",
                )
            actual_collections[relative] = len(outcomes)
        return actual_collections

    def _audit_repository(
        self,
        *,
        claim_source_kinds: frozenset[ClaimSourceKind],
        audited_claims: tuple[HistoricalClaim, ...],
    ) -> ClaimLedgerAudit:
        actual_collections = self._scenario_collection_inventory()

        inventoried = {
            claim.repository_path for claim in self.claims if claim.surface is ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES
        }
        uninventoried = tuple(sorted(set(actual_collections) - inventoried))
        missing = tuple(sorted(inventoried - set(actual_collections)))

        candidates = scan_historical_claim_sources(
            self._repository_root,
            source_kinds=claim_source_kinds,
        )
        candidate_by_path = {candidate.repository_path: candidate for candidate in candidates}
        selected_reviews = tuple(
            review for review in self.claim_source_reviews if review.source_kind in claim_source_kinds
        )
        review_by_path = {review.repository_path: review for review in selected_reviews}
        unreviewed_sources = tuple(
            sorted(set(candidate_by_path) - set(review_by_path)),
        )
        stale_reviews = tuple(
            sorted(set(review_by_path) - set(candidate_by_path)),
        )
        common_paths = tuple(
            sorted(set(candidate_by_path) & set(review_by_path)),
        )
        source_digest_mismatches = tuple(
            path for path in common_paths if candidate_by_path[path].source_sha256 != review_by_path[path].source_sha256
        )
        source_rule_mismatches = tuple(
            path
            for path in common_paths
            if candidate_by_path[path].source_kind is not review_by_path[path].source_kind
            or candidate_by_path[path].matches != review_by_path[path].matches
        )

        binding_errors: list[str] = []
        for review in selected_reviews:
            allowed = _CLAIM_SURFACES_BY_SOURCE_KIND[review.source_kind]
            compatible_ids = tuple(
                sorted(
                    claim.claim_id
                    for claim in self.claims
                    if claim.repository_path == review.repository_path and claim.surface in allowed
                ),
            )
            if review.exclusion is None and review.claim_ids != compatible_ids:
                binding_errors.append(review.repository_path)
            if review.exclusion is not None and compatible_ids:
                binding_errors.append(review.repository_path)

        return ClaimLedgerAudit(
            scenario_collections=len(actual_collections),
            scenario_metrics=sum(actual_collections.values()),
            python_test_surfaces=sum(
                claim.surface
                in {
                    ClaimSurface.PYTHON_DOCUMENTED_OUTCOMES_TEST,
                    ClaimSurface.PYTHON_HISTORICAL_CLAIM_TEST,
                }
                for claim in self.claims
            ),
            frontend_test_surfaces=sum(
                claim.surface is ClaimSurface.FRONTEND_HISTORICAL_CLAIM_TEST for claim in self.claims
            ),
            documentation_claims=sum(claim.surface is ClaimSurface.DOCUMENTATION_CLAIM for claim in self.claims),
            documentation_claim_paths=len(
                {claim.repository_path for claim in self.claims if claim.surface is ClaimSurface.DOCUMENTATION_CLAIM},
            ),
            api_python_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.API_PYTHON for candidate in candidates
            ),
            frontend_public_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.FRONTEND_PUBLIC_SOURCE for candidate in candidates
            ),
            frontend_test_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.FRONTEND_TEST for candidate in candidates
            ),
            python_test_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.PYTHON_TEST for candidate in candidates
            ),
            public_document_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.PUBLIC_DOCUMENT for candidate in candidates
            ),
            scenario_yaml_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.SCENARIO_YAML for candidate in candidates
            ),
            workflow_document_candidate_paths=sum(
                candidate.source_kind is ClaimSourceKind.WORKFLOW_DOCUMENT for candidate in candidates
            ),
            claim_bound_source_reviews=sum(bool(review.claim_ids) for review in self.claim_source_reviews),
            reviewed_nonclaim_source_reviews=sum(review.exclusion is not None for review in self.claim_source_reviews),
            production_validated_claims=sum(
                claim.disposition is ClaimDisposition.PRODUCTION_VALIDATED for claim in self.claims
            ),
            uninventoried_scenario_collections=uninventoried,
            missing_scenario_collections=missing,
            unreviewed_claim_source_paths=unreviewed_sources,
            stale_claim_source_reviews=stale_reviews,
            claim_source_digest_mismatches=source_digest_mismatches,
            claim_source_rule_mismatches=source_rule_mismatches,
            claim_source_binding_errors=tuple(sorted(set(binding_errors))),
            forbidden_boolean_historical_apis=(_obsolete_boolean_historical_apis(self._repository_root)),
            digest_mismatches=self._digest_mismatches(audited_claims),
        )

    def audit_repository(self) -> ClaimLedgerAudit:
        """Recompute the complete shipped scenario and claim inventory."""
        return self._audit_repository(
            claim_source_kinds=_ALL_CLAIM_SOURCE_KINDS,
            audited_claims=self.claims,
        )

    def scenario_summary(
        self,
        scenario_path: str | Path,
    ) -> ScenarioHistoricalValidationSummary:
        """Return the conservative claim aggregation for one exact path."""
        raw_path = Path(scenario_path)
        lexical = raw_path.absolute() if raw_path.is_absolute() else (self._repository_root / raw_path).absolute()
        if lexical.is_relative_to(self._repository_root):
            relative = lexical.relative_to(self._repository_root).as_posix()
            try:
                resolve_repository_path(
                    self._repository_root,
                    relative,
                    field_name="scenario_path",
                    require_file=False,
                )
            except ValueError:
                summary_identity = f"repository-alias:{relative}"
                matching: tuple[HistoricalClaim, ...] = ()
            else:
                summary_identity = relative
                matching = tuple(claim for claim in self.claims if claim.scenario_path == relative)
        else:
            summary_identity = f"external:{lexical.as_posix()}"
            matching = ()

        if not matching:
            synthetic_id = (
                "synthetic.unsupported."
                + hashlib.sha256(
                    summary_identity.encode("utf-8"),
                ).hexdigest()[:16]
            )
            summaries = (
                HistoricalClaimSummary(
                    claim_id=synthetic_id,
                    disposition=ClaimDisposition.UNSUPPORTED,
                    reason_codes=("missing_ledger_identity",),
                    limitation=(
                        "No inventoried claim or accepted production evidence exists for this scenario source."
                    ),
                    intended_use=(
                        "Unsupported-status disclosure only; no inventoried historical claim identity exists."
                    ),
                    metric_scope=(),
                    event_scope="No inventoried production event boundary.",
                    current_engine_regression_evidence=False,
                    accepted_study_id=None,
                    accepted_artifact_path=None,
                ),
            )
            return ScenarioHistoricalValidationSummary(
                claims=summaries,
                aggregate_disposition=ClaimDisposition.UNSUPPORTED,
                accepted_claim_ids=(),
                current_engine_regression_evidence=False,
                ledger_sha256=self.ledger_sha256,
            )

        summaries_list: list[HistoricalClaimSummary] = []
        accepted_families: set[tuple[str, str, str]] = set()
        for claim in matching:
            accepted = claim.accepted_evidence
            if accepted is not None:
                artifact = self._accepted_artifacts[claim.claim_id]
                event_scope = artifact.plan.gating_metrics[0].source_event_boundary
                intended_use = artifact.plan.intended_use
                accepted_families.add(
                    (artifact.study_id, intended_use, event_scope),
                )
            elif claim.disposition is ClaimDisposition.CURRENT_ENGINE_REGRESSION_ONLY:
                intended_use = "Current-engine regression disclosure only."
                event_scope = "Scenario execution boundary; not a validated historical event boundary."
            else:
                intended_use = "Unsupported-status and catalog-history disclosure only."
                event_scope = (
                    "Legacy documented outcome collection; no validated production event boundary."
                    if claim.surface is ClaimSurface.SCENARIO_DOCUMENTED_OUTCOMES
                    else "Scenario prose; no validated production event boundary."
                )
            summaries_list.append(
                HistoricalClaimSummary(
                    claim_id=claim.claim_id,
                    disposition=claim.disposition,
                    reason_codes=claim.reason_codes,
                    limitation=claim.limitation,
                    intended_use=intended_use,
                    metric_scope=claim.metric_scope,
                    event_scope=event_scope,
                    current_engine_regression_evidence=(claim.current_engine_regression_evidence),
                    accepted_study_id=(None if accepted is None else accepted.study_id),
                    accepted_artifact_path=(None if accepted is None else accepted.artifact_path),
                ),
            )
        summaries = tuple(summaries_list)
        dispositions = {claim.disposition for claim in matching}
        if ClaimDisposition.UNSUPPORTED in dispositions:
            aggregate = ClaimDisposition.UNSUPPORTED
        elif ClaimDisposition.CURRENT_ENGINE_REGRESSION_ONLY in dispositions:
            aggregate = ClaimDisposition.CURRENT_ENGINE_REGRESSION_ONLY
        elif dispositions == {ClaimDisposition.PRODUCTION_VALIDATED} and len(accepted_families) == 1:
            aggregate = ClaimDisposition.PRODUCTION_VALIDATED
        else:
            aggregate = ClaimDisposition.UNSUPPORTED
        return ScenarioHistoricalValidationSummary(
            claims=summaries,
            aggregate_disposition=aggregate,
            accepted_claim_ids=tuple(
                claim.claim_id for claim in matching if claim.disposition is ClaimDisposition.PRODUCTION_VALIDATED
            ),
            current_engine_regression_evidence=any(claim.current_engine_regression_evidence for claim in matching),
            ledger_sha256=self.ledger_sha256,
        )


class HistoricalClaimLedgerLoader:
    """Load and source-audit one exact checked-in claim ledger."""

    def __init__(self, repository_root: str | Path) -> None:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            raise ValueError(f"repository_root is not a directory: {root}")
        self._repository_root = root

    def _ledger_path(self, path: str | Path) -> Path:
        raw_path = Path(path)
        lexical = raw_path.absolute() if raw_path.is_absolute() else (self._repository_root / raw_path).absolute()
        try:
            relative = lexical.relative_to(self._repository_root).as_posix()
        except ValueError as exc:
            raise ValueError("ledger path escapes repository root") from exc
        return resolve_repository_path(
            self._repository_root,
            relative,
            field_name="historical claim ledger path",
        )

    def _load(
        self,
        path: str | Path,
        *,
        scenario_catalog_only: bool,
    ) -> tuple[HistoricalClaimLedger, ClaimLedgerAudit]:
        ledger_path = self._ledger_path(path)
        raw = load_yaml_unique(ledger_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("historical claim ledger root must be a mapping")
        ledger = HistoricalClaimLedger.model_validate(raw, strict=True)
        payload = dict(raw)
        persisted_digest = payload.pop("ledger_sha256", None)
        if persisted_digest != _canonical_sha256(payload):
            raise ValueError("historical claim ledger digest does not match")
        object.__setattr__(ledger, "_repository_root", self._repository_root)
        object.__setattr__(ledger, "_ledger_path", ledger_path)
        audited_claims = (
            tuple(
                claim
                for claim in ledger.claims
                if claim.scenario_path is not None or claim.surface is ClaimSurface.API_CLAIM_SURFACE
            )
            if scenario_catalog_only
            else ledger.claims
        )
        audit = ledger._audit_repository(
            claim_source_kinds=(_PACKAGED_CLAIM_SOURCE_KINDS if scenario_catalog_only else _ALL_CLAIM_SOURCE_KINDS),
            audited_claims=audited_claims,
        )
        failures = {
            "uninventoried_scenario_collections": audit.uninventoried_scenario_collections,
            "missing_scenario_collections": audit.missing_scenario_collections,
            "unreviewed_claim_source_paths": audit.unreviewed_claim_source_paths,
            "stale_claim_source_reviews": audit.stale_claim_source_reviews,
            "claim_source_digest_mismatches": audit.claim_source_digest_mismatches,
            "claim_source_rule_mismatches": audit.claim_source_rule_mismatches,
            "claim_source_binding_errors": audit.claim_source_binding_errors,
            "forbidden_boolean_historical_apis": audit.forbidden_boolean_historical_apis,
            "digest_mismatches": audit.digest_mismatches,
        }
        populated_failures = tuple(f"{name}={values!r}" for name, values in failures.items() if values)
        if populated_failures:
            raise ValueError(
                "historical claim repository audit failed: " + "; ".join(populated_failures),
            )
        ledger._validate_accepted_evidence()
        return ledger, audit

    def load(self, path: str | Path) -> HistoricalClaimLedger:
        """Load and source-audit every repository claim."""
        ledger, _audit = self._load(path, scenario_catalog_only=False)
        return ledger

    def load_with_audit(
        self,
        path: str | Path,
    ) -> tuple[HistoricalClaimLedger, ClaimLedgerAudit]:
        """Load every claim and return the exact verified repository audit."""
        return self._load(path, scenario_catalog_only=False)

    def load_scenario_catalog(
        self,
        path: str | Path,
    ) -> HistoricalClaimLedger:
        """Load the exact ledger while auditing every API-published claim."""
        ledger, _audit = self._load(path, scenario_catalog_only=True)
        return ledger


__all__ = [
    "AcceptedHistoricalEvidence",
    "ClaimDisposition",
    "ClaimLedgerAudit",
    "ClaimSourceExclusionReason",
    "ClaimSourceKind",
    "ClaimSourceRule",
    "ClaimSourceRuleMatch",
    "ClaimSurface",
    "HistoricalClaim",
    "HistoricalClaimLedger",
    "HistoricalClaimLedgerLoader",
    "HistoricalClaimSourceCandidate",
    "HistoricalClaimSummary",
    "ReviewedClaimSource",
    "ReviewedClaimSourceExclusion",
    "ScenarioHistoricalValidationSummary",
    "scan_historical_claim_sources",
]
