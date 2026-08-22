"""Strict production benchmark gate and workload-transition harness.

The public :func:`run_benchmark` helper remains a measurement-only profiler.
Regression decisions are made only by :func:`run_paired_comparison`.
Intentional workload changes use :func:`run_workload_transition`, which
executes exactly one candidate-owned duration-free production closure at each
endpoint and makes no performance decision.
"""

from __future__ import annotations

import argparse
import cProfile
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
import enum
import hashlib
import inspect
from io import StringIO
import json
import math
import os
from pathlib import Path
import platform
import pstats
import re
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Literal, Mapping, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"
BASELINES_PATH = Path(__file__).with_name("baselines.json")
REFERENCE_COMMIT = "0460ac70be86784bcc6e359ae4202f4bcb938c60"
POLICY_VERSION = 4
RUNTIME_INPUT_POLICY_VERSION = 3
WORKER_RECORDER_MAX_EVENTS = 5_000_000
_LEGACY_FALSE_RECORDER_FIELDS = (
    "strict_extraction_errors",
    "strict_overflow",
)
DEFAULT_MAX_TICKS = 20_000
PAIR_ORDERS: list[list[Literal["reference", "candidate"]]] = [
    ["reference", "candidate"],
    ["candidate", "reference"],
    ["reference", "candidate"],
]
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_STATIC_RUNTIME_SUFFIXES = {
    ".json",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}
_LOADER_DATA_SUFFIXES = {
    ".geojson",
    ".hgt",
    ".nc",
    ".netcdf",
    ".npz",
    ".tif",
    ".tiff",
}
_RUNTIME_TOP_LEVEL = {
    "stochastic_warfare",
    "api",
    "data",
}
_RUNTIME_EXACT_PATHS = {
    ".gitignore",
    "pyproject.toml",
    "uv.lock",
    "scripts/run_paired_benchmark.py",
    "tests/benchmarks/benchmark_suite.py",
    "tests/benchmarks/baselines.json",
}


# ---------------------------------------------------------------------------
# Canonical serialization
# ---------------------------------------------------------------------------


def _canonical_value(value: Any) -> Any:
    """Return a deterministic JSON value or reject unsupported state."""
    if value is None or type(value) in {bool, str, int}:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON rejects non-finite numbers")
        return value
    if isinstance(value, enum.Enum):
        return _canonical_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, BaseModel):
        return _canonical_value(
            value.model_dump(mode="json", exclude_none=False),
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "_asdict"):
        return _canonical_value(value._asdict())
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON mapping keys must be strings")
        return {key: _canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(
            normalized,
            key=canonical_json_bytes,
        )
    if hasattr(value, "tolist"):
        return _canonical_value(value.tolist())
    if hasattr(value, "item"):
        return _canonical_value(value.item())
    raise TypeError(
        f"canonical JSON does not support {type(value).__module__}.{type(value).__qualname__}",
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize *value* as strict canonical UTF-8 JSON."""
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 of :func:`canonical_json_bytes`."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha256(value: str, label: str) -> str:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


# ---------------------------------------------------------------------------
# Typed policy, baseline, worker, and artifact records
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RuntimeSource(_StrictModel):
    """One relative, content-addressed loader input."""

    path: str
    sha256: str
    mode: Literal["100644", "100755"]
    role: str

    @field_validator("path", "role")
    @classmethod
    def _nonempty_trimmed(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("source strings must be non-empty and trimmed")
        if value.startswith("/") or "\\" in value or ".." in Path(value).parts:
            raise ValueError("source paths must be repository-relative POSIX paths")
        return value

    @field_validator("sha256")
    @classmethod
    def _valid_digest(cls, value: str) -> str:
        return _validate_sha256(value, "source sha256")


class RuntimeInputManifest(_StrictModel):
    """Canonical effective workload and every resolved data source."""

    policy_version: Literal[3] = RUNTIME_INPUT_POLICY_VERSION
    scenario_path: str
    scenario_sha256: str
    dependency_lock_sha256: str
    seed: int = Field(strict=True, ge=0)
    max_ticks: int = Field(strict=True, gt=0)
    recorder_config: dict[str, Any]
    effective_inputs: dict[str, Any]
    sources: list[RuntimeSource]
    fingerprint: str

    @field_validator("scenario_sha256", "dependency_lock_sha256", "fingerprint")
    @classmethod
    def _valid_digests(cls, value: str) -> str:
        return _validate_sha256(value, "runtime input digest")

    @model_validator(mode="after")
    def _internally_consistent(self) -> Self:
        if (
            not self.scenario_path
            or self.scenario_path != self.scenario_path.strip()
            or self.scenario_path.startswith("/")
            or "\\" in self.scenario_path
            or ".." in Path(self.scenario_path).parts
        ):
            raise ValueError(
                "runtime scenario path must be repository-relative POSIX",
            )
        paths = [source.path for source in self.sources]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("runtime sources must be unique and path-sorted")
        sources_by_path = {source.path: source for source in self.sources}
        scenario_source = sources_by_path.get(self.scenario_path)
        lock_source = sources_by_path.get("uv.lock")
        if (
            scenario_source is None
            or scenario_source.sha256 != self.scenario_sha256
            or scenario_source.role != "scenario"
        ):
            raise ValueError(
                "runtime sources must contain the exact scenario identity",
            )
        if (
            lock_source is None
            or lock_source.sha256 != self.dependency_lock_sha256
            or lock_source.role != "dependency_lock"
        ):
            raise ValueError(
                "runtime sources must contain the exact dependency lock",
            )
        expected = canonical_sha256(self.fingerprint_payload())
        if self.fingerprint != expected:
            raise ValueError(
                "runtime input fingerprint does not match its canonical payload",
            )
        return self

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "scenario_path": self.scenario_path,
            "scenario_sha256": self.scenario_sha256,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "seed": self.seed,
            "max_ticks": self.max_ticks,
            "recorder_config": self.recorder_config,
            "effective_inputs": self.effective_inputs,
            "sources": [source.model_dump(mode="python") for source in self.sources],
        }


class SemanticEnvelope(_StrictModel):
    """Outcome identity required before any timing comparison."""

    unit_count: int = Field(strict=True, gt=0)
    roster_loadout_digest: str
    winner: str | None
    victory_condition_type: str
    ticks: int = Field(strict=True, gt=0)
    logical_duration_s: float = Field(gt=0.0, allow_inf_nan=False)
    status_counts: dict[str, dict[str, int]]
    event_count: int = Field(strict=True, ge=0)
    event_digest: str

    @field_validator("roster_loadout_digest", "event_digest")
    @classmethod
    def _valid_digest(cls, value: str) -> str:
        return _validate_sha256(value, "semantic digest")

    @model_validator(mode="after")
    def _valid_status_counts(self) -> Self:
        if list(self.status_counts) != sorted(self.status_counts):
            raise ValueError("semantic side status maps must be sorted")
        for side, counts in self.status_counts.items():
            if not side or side != side.strip():
                raise ValueError("semantic side names must be non-empty and trimmed")
            if list(counts) != sorted(counts):
                raise ValueError("semantic status count maps must be sorted")
            if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts.values()):
                raise ValueError("semantic status counts must be non-negative integers")
        if sum(count for counts in self.status_counts.values() for count in counts.values()) != self.unit_count:
            raise ValueError(
                "semantic status counts must equal the exact unit count",
            )
        if not self.victory_condition_type or self.victory_condition_type != self.victory_condition_type.strip():
            raise ValueError(
                "semantic victory condition must be non-empty and trimmed",
            )
        if self.winner is not None and (not self.winner or self.winner != self.winner.strip()):
            raise ValueError("semantic winner must be null or non-empty and trimmed")
        return self


class ReferenceInput(_StrictModel):
    """Compact checked-in identity for an authoritative runtime manifest."""

    scenario_path: str
    scenario_sha256: str
    dependency_lock_sha256: str
    fingerprint: str

    @field_validator(
        "scenario_sha256",
        "dependency_lock_sha256",
        "fingerprint",
    )
    @classmethod
    def _valid_digests(cls, value: str) -> str:
        return _validate_sha256(value, "reference input digest")


class MoraleNeutralCalibration(_StrictModel):
    """Exact zero-pressure morale calibration for a control-plane workload."""

    base_degrade_rate: Literal[0.0]
    base_recover_rate: Literal[0.0]
    casualty_weight: Literal[0.0]
    suppression_weight: Literal[0.0]
    leadership_weight: Literal[0.0]
    cohesion_weight: Literal[0.0]
    force_ratio_weight: Literal[0.0]


class BenchmarkCalibrationPatch(_StrictModel):
    """Typed sparse production calibration used by one benchmark workload."""

    morale: MoraleNeutralCalibration | None = None


class BenchmarkWorkload(_StrictModel):
    """Named effective workload and its exact production calibration patch."""

    name: Literal["default", "morale_neutral_control_plane"]
    calibration_patch: BenchmarkCalibrationPatch

    @model_validator(mode="after")
    def _valid_variant(self) -> Self:
        has_morale_control = self.calibration_patch.morale is not None
        if (self.name == "morale_neutral_control_plane") != has_morale_control:
            raise ValueError(
                "morale-neutral workload name and calibration must agree",
            )
        return self


class BenchmarkPolicy(_StrictModel):
    """Exact version-4 paired-gate or measurement-only policy."""

    policy_version: Literal[4] = POLICY_VERSION
    mode: Literal["gate", "measurement_only"]
    manual: bool
    reference_commit: str | None
    workload: BenchmarkWorkload
    warmup_runs_per_revision: Literal[1] = 1
    timed_pairs: Literal[3] = 3
    pair_orders: list[list[Literal["reference", "candidate"]]]
    maximum_median_slowdown_ratio: float = Field(
        default=1.20,
        gt=0.0,
        allow_inf_nan=False,
    )
    maximum_relative_sample_range: float = Field(
        default=0.20,
        ge=0.0,
        allow_inf_nan=False,
    )
    timing_scope: Literal["SimulationEngine.run"] = "SimulationEngine.run"

    @model_validator(mode="after")
    def _valid_policy(self) -> Self:
        if self.pair_orders != PAIR_ORDERS:
            raise ValueError(
                "paired order must alternate reference/candidate exactly",
            )
        if self.mode == "gate":
            if self.reference_commit is None or not _FULL_COMMIT_PATTERN.fullmatch(self.reference_commit):
                raise ValueError("gating policy requires one full reference commit")
        elif self.reference_commit is not None:
            raise ValueError(
                "measurement-only policy must not imply an authoritative reference",
            )
        return self


class TransitionPolicy(_StrictModel):
    """Duration-free policy for one intentional workload transition."""

    policy_version: Literal[4] = POLICY_VERSION
    mode: Literal["transition_qualified"]
    manual: bool
    reference_commit: str
    workload: BenchmarkWorkload
    closures_per_revision: Literal[1] = 1

    @field_validator("reference_commit")
    @classmethod
    def _full_reference_commit(cls, value: str) -> str:
        if not _FULL_COMMIT_PATTERN.fullmatch(value):
            raise ValueError(
                "transition policy requires one full reference commit",
            )
        return value


class TransitionApproval(_StrictModel):
    """One sourced, digest-bound approval for an exact endpoint difference."""

    surface: Literal[
        "effective_inputs",
        "runtime_input",
        "semantic_envelope",
    ]
    pointer: str
    operation: Literal["add", "remove", "replace"]
    before_sha256: str
    after_sha256: str
    classification: Literal[
        "sensing_aware_standoff_enablement",
        "vvs2_target_domain_expansion",
        "vvs2_loadout_role_correction",
        "derived_runtime_input_fingerprint",
        "derived_roster_loadout_digest",
    ]
    authorities: list[str]
    rationale: str

    @field_validator("pointer")
    @classmethod
    def _canonical_json_pointer(cls, value: str) -> str:
        if value == "":
            return value
        if not value.startswith("/"):
            raise ValueError(
                "transition difference requires a canonical JSON Pointer",
            )
        encoded_tokens: list[str] = []
        for token in value[1:].split("/"):
            decoded: list[str] = []
            index = 0
            while index < len(token):
                character = token[index]
                if character != "~":
                    decoded.append(character)
                    index += 1
                    continue
                if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                    raise ValueError("transition JSON Pointer escaping is invalid")
                decoded.append("~" if token[index + 1] == "0" else "/")
                index += 2
            encoded_tokens.append(
                "".join(decoded).replace("~", "~0").replace("/", "~1"),
            )
        canonical = "/" + "/".join(encoded_tokens)
        if canonical != value:
            raise ValueError("transition JSON Pointer is not canonical")
        return value

    @field_validator("before_sha256", "after_sha256")
    @classmethod
    def _valid_value_digest(cls, value: str) -> str:
        return _validate_sha256(value, "transition value digest")

    @field_validator("rationale")
    @classmethod
    def _nonempty_rationale(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "transition rationale must be non-empty and trimmed",
            )
        return value

    @field_validator("authorities")
    @classmethod
    def _sourced_authorities(cls, value: list[str]) -> list[str]:
        if (
            not value
            or value != sorted(value)
            or len(value) != len(set(value))
            or any(not authority or authority != authority.strip() for authority in value)
        ):
            raise ValueError(
                "transition authorities must be non-empty, unique, and sorted",
            )
        return value


class TransitionEndpoint(_StrictModel):
    """Checked-in exact runtime and semantic identity for one endpoint."""

    runtime_input: ReferenceInput
    semantic_envelope: SemanticEnvelope


class TransitionPredecessorLineage(_StrictModel):
    """Exact version-3 baseline lineage intentionally superseded by v4."""

    format_version: Literal[3]
    policy_version: Literal[3]
    commit: str
    document_sha256: str
    entry_sha256: str

    @field_validator("commit")
    @classmethod
    def _valid_predecessor_commit(cls, value: str) -> str:
        if not _FULL_COMMIT_PATTERN.fullmatch(value):
            raise ValueError(
                "transition predecessor requires a full lowercase commit",
            )
        return value

    @field_validator("document_sha256", "entry_sha256")
    @classmethod
    def _valid_lineage_digest(cls, value: str) -> str:
        return _validate_sha256(value, "transition predecessor digest")


class WorkloadTransitionContract(_StrictModel):
    """Exact approved input and semantic delta for one workload transition."""

    predecessor: TransitionPredecessorLineage
    reference: TransitionEndpoint
    candidate: TransitionEndpoint
    approvals: list[TransitionApproval]

    @model_validator(mode="after")
    def _differences_are_exactly_ordered(self) -> Self:
        if not self.approvals:
            raise ValueError(
                "workload transition requires at least one exact difference",
            )
        keys = [(approval.surface, approval.pointer) for approval in self.approvals]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError(
                "transition approvals must be unique and surface/path-sorted",
            )
        return self


class BaselineEntry(_StrictModel):
    """Strict version-4 baseline entry."""

    scenario_name: str
    scenario_path: str
    policy: BenchmarkPolicy | TransitionPolicy
    reference_input: ReferenceInput | None
    semantic_envelope: SemanticEnvelope | None
    transition_contract: WorkloadTransitionContract | None

    @model_validator(mode="after")
    def _valid_mode_payload(self) -> Self:
        if not self.scenario_name or self.scenario_name != self.scenario_name.strip():
            raise ValueError("scenario_name must be non-empty and trimmed")
        uses_morale_neutral_control = self.policy.workload.name == "morale_neutral_control_plane"
        is_routine_control_plane = self.scenario_name == "73_easting"
        if is_routine_control_plane and not uses_morale_neutral_control:
            raise ValueError(
                "73_easting must use the morale-neutral control-plane workload",
            )
        if not is_routine_control_plane and uses_morale_neutral_control:
            raise ValueError(
                "only the routine 73_easting benchmark may use the morale-neutral control-plane workload",
            )
        if isinstance(self.policy, BenchmarkPolicy) and self.policy.mode == "gate":
            if self.reference_input is None or self.semantic_envelope is None or self.transition_contract is not None:
                raise ValueError(
                    "gating baseline requires reference input and semantics",
                )
            if self.reference_input.scenario_path != self.scenario_path:
                raise ValueError("baseline scenario paths disagree")
        elif isinstance(self.policy, TransitionPolicy):
            if (
                self.reference_input is not None
                or self.semantic_envelope is not None
                or self.transition_contract is None
            ):
                raise ValueError(
                    "transition baseline requires only its exact transition contract",
                )
            endpoints = (
                self.transition_contract.reference,
                self.transition_contract.candidate,
            )
            if any(endpoint.runtime_input.scenario_path != self.scenario_path for endpoint in endpoints):
                raise ValueError("transition baseline scenario paths disagree")
        elif (
            self.reference_input is not None
            or self.semantic_envelope is not None
            or self.transition_contract is not None
        ):
            raise ValueError(
                "measurement-only entries cannot carry a pass/fail baseline",
            )
        return self


class BaselineFile(_StrictModel):
    """Checked-in benchmark baseline document."""

    format_version: Literal[4] = POLICY_VERSION
    description: str
    entries: dict[str, BaselineEntry]

    @model_validator(mode="after")
    def _valid_entries(self) -> Self:
        if list(self.entries) != sorted(self.entries):
            raise ValueError("baseline entries must be scenario-name sorted")
        for key, entry in self.entries.items():
            if key != entry.scenario_name:
                raise ValueError("baseline entry key and scenario_name disagree")
        return self


class WorkerRun(_StrictModel):
    """One revision-local production run."""

    revision: Literal["reference", "candidate"]
    commit: str
    duration_s: float = Field(gt=0.0, allow_inf_nan=False)
    runtime_input: RuntimeInputManifest
    semantic_envelope: SemanticEnvelope

    @field_validator("commit")
    @classmethod
    def _valid_commit(cls, value: str) -> str:
        if not _FULL_COMMIT_PATTERN.fullmatch(value):
            raise ValueError("worker commit must be a full lowercase git SHA")
        return value


class ProductionClosureRun(_StrictModel):
    """Duration-free runtime and semantic closure for one revision."""

    revision: Literal["reference", "candidate"]
    commit: str
    runtime_input: RuntimeInputManifest
    semantic_envelope: SemanticEnvelope

    @field_validator("commit")
    @classmethod
    def _valid_commit(cls, value: str) -> str:
        if not _FULL_COMMIT_PATTERN.fullmatch(value):
            raise ValueError("closure commit must be a full lowercase git SHA")
        return value


class PairSample(_StrictModel):
    pair_index: int = Field(strict=True, ge=0, lt=3)
    order: list[Literal["reference", "candidate"]]
    reference: WorkerRun
    candidate: WorkerRun
    candidate_over_reference: float = Field(gt=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _valid_pair(self) -> Self:
        if self.reference.revision != "reference" or self.candidate.revision != "candidate":
            raise ValueError("paired worker revisions are reversed or mislabeled")
        if self.order != PAIR_ORDERS[self.pair_index]:
            raise ValueError("pair order disagrees with the policy")
        expected = self.candidate.duration_s / self.reference.duration_s
        if not math.isclose(
            self.candidate_over_reference,
            expected,
            rel_tol=1.0e-12,
            abs_tol=0.0,
        ):
            raise ValueError("paired ratio disagrees with raw samples")
        return self


class PerformanceDecision(_StrictModel):
    status: Literal["pass", "fail", "inconclusive"]
    ratios: list[float]
    median_ratio: float = Field(gt=0.0, allow_inf_nan=False)
    reference_relative_range: float = Field(ge=0.0, allow_inf_nan=False)
    candidate_relative_range: float = Field(ge=0.0, allow_inf_nan=False)
    reason: str


_TRANSITION_MISSING = object()


@dataclass(frozen=True)
class _ObservedTransitionDifference:
    surface: Literal[
        "effective_inputs",
        "runtime_input",
        "semantic_envelope",
    ]
    pointer: str
    operation: Literal["add", "remove", "replace"]
    before_sha256: str
    after_sha256: str


def _json_pointer_token(value: str | int) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _transition_value_sha256(value: Any) -> str:
    payload: dict[str, Any] = {
        "present": value is not _TRANSITION_MISSING,
    }
    if value is not _TRANSITION_MISSING:
        payload["value"] = value
    return canonical_sha256(payload)


def compute_transition_differences(
    reference: Any,
    candidate: Any,
    *,
    surface: Literal[
        "effective_inputs",
        "runtime_input",
        "semantic_envelope",
    ],
) -> list[_ObservedTransitionDifference]:
    """Return every canonical leaf difference without assigning approval."""
    raw: list[tuple[str, Any, Any]] = []

    def visit(reference_value: Any, candidate_value: Any, pointer: str) -> None:
        if isinstance(reference_value, Mapping) and isinstance(
            candidate_value,
            Mapping,
        ):
            if not all(isinstance(key, str) for key in (*reference_value.keys(), *candidate_value.keys())):
                raise ValueError(
                    "transition comparison mappings require string keys",
                )
            for key in sorted(set(reference_value) | set(candidate_value)):
                visit(
                    reference_value.get(key, _TRANSITION_MISSING),
                    candidate_value.get(key, _TRANSITION_MISSING),
                    f"{pointer}/{_json_pointer_token(key)}",
                )
            return
        if isinstance(reference_value, list) and isinstance(candidate_value, list):
            for index in range(max(len(reference_value), len(candidate_value))):
                visit(
                    (reference_value[index] if index < len(reference_value) else _TRANSITION_MISSING),
                    (candidate_value[index] if index < len(candidate_value) else _TRANSITION_MISSING),
                    f"{pointer}/{index}",
                )
            return
        if (
            reference_value is not _TRANSITION_MISSING
            and candidate_value is not _TRANSITION_MISSING
            and canonical_json_bytes(reference_value) == canonical_json_bytes(candidate_value)
        ):
            return
        raw.append((pointer, reference_value, candidate_value))

    visit(reference, candidate, "")
    differences = [
        _ObservedTransitionDifference(
            surface=surface,
            pointer=pointer,
            operation=(
                "add"
                if reference_value is _TRANSITION_MISSING
                else "remove"
                if candidate_value is _TRANSITION_MISSING
                else "replace"
            ),
            before_sha256=_transition_value_sha256(reference_value),
            after_sha256=_transition_value_sha256(candidate_value),
        )
        for pointer, reference_value, candidate_value in raw
    ]
    return sorted(differences, key=lambda difference: difference.pointer)


def _validate_transition_endpoint(
    run: ProductionClosureRun,
    endpoint: TransitionEndpoint,
) -> None:
    expected = endpoint.runtime_input
    actual = run.runtime_input
    if (
        actual.scenario_path != expected.scenario_path
        or actual.scenario_sha256 != expected.scenario_sha256
        or actual.dependency_lock_sha256 != expected.dependency_lock_sha256
        or actual.fingerprint != expected.fingerprint
    ):
        raise ValueError(
            f"{run.revision} workload-transition runtime identity differs from its exact endpoint",
        )
    if run.semantic_envelope != endpoint.semantic_envelope:
        raise ValueError(
            f"{run.revision} workload-transition semantics differ from its exact endpoint",
        )


def validate_workload_transition(
    reference: ProductionClosureRun,
    candidate: ProductionClosureRun,
    contract: WorkloadTransitionContract,
) -> list[TransitionApproval]:
    """Reject every unapproved endpoint, immutable input, or semantic delta."""
    if reference.revision != "reference" or candidate.revision != "candidate":
        raise ValueError("workload-transition endpoints are reversed or mislabeled")
    _validate_transition_endpoint(reference, contract.reference)
    _validate_transition_endpoint(candidate, contract.candidate)

    reference_input = reference.runtime_input
    candidate_input = candidate.runtime_input
    invariant_fields = (
        "policy_version",
        "scenario_path",
        "scenario_sha256",
        "dependency_lock_sha256",
        "seed",
        "max_ticks",
        "recorder_config",
        "sources",
    )
    changed_invariants = [
        name for name in invariant_fields if getattr(reference_input, name) != getattr(candidate_input, name)
    ]
    if changed_invariants:
        raise ValueError(
            f"workload-transition immutable inputs differ: {changed_invariants!r}",
        )

    observed = compute_transition_differences(
        reference_input.effective_inputs,
        candidate_input.effective_inputs,
        surface="effective_inputs",
    )
    observed.extend(
        compute_transition_differences(
            {"fingerprint": reference_input.fingerprint},
            {"fingerprint": candidate_input.fingerprint},
            surface="runtime_input",
        )
    )
    observed.extend(
        compute_transition_differences(
            reference.semantic_envelope.model_dump(mode="json"),
            candidate.semantic_envelope.model_dump(mode="json"),
            surface="semantic_envelope",
        )
    )
    observed.sort(key=lambda difference: (difference.surface, difference.pointer))
    approvals = {(approval.surface, approval.pointer): approval for approval in contract.approvals}
    observed_by_key = {(difference.surface, difference.pointer): difference for difference in observed}
    unapproved = sorted(set(observed_by_key) - set(approvals))
    stale = sorted(set(approvals) - set(observed_by_key))
    if unapproved:
        raise ValueError(
            f"unapproved transition differences: {unapproved!r}",
        )
    if stale:
        raise ValueError(f"stale transition approvals: {stale!r}")
    for key, difference in observed_by_key.items():
        approval = approvals[key]
        if (
            approval.operation != difference.operation
            or approval.before_sha256 != difference.before_sha256
            or approval.after_sha256 != difference.after_sha256
        ):
            raise ValueError(
                f"transition approval differs from observed value at {key!r}",
            )
    return list(contract.approvals)


def _verify_transition_predecessor(
    repo_root: Path,
    *,
    scenario_name: str,
    policy: TransitionPolicy,
    contract: WorkloadTransitionContract,
) -> None:
    """Verify the exact v3 document and entry superseded by a transition."""
    lineage = contract.predecessor
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", lineage.commit, "HEAD"],
        cwd=repo_root,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if ancestry.returncode != 0:
        raise ValueError(
            "transition predecessor is not an ancestor of the candidate",
        )
    completed = subprocess.run(
        [
            "git",
            "show",
            f"{lineage.commit}:tests/benchmarks/baselines.json",
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        timeout=120,
    )
    document = completed.stdout
    if hashlib.sha256(document).hexdigest() != lineage.document_sha256:
        raise ValueError(
            "transition predecessor document digest differs from git",
        )
    try:
        raw = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "transition predecessor document is not valid JSON",
        ) from exc
    if not isinstance(raw, dict) or raw.get("format_version") != 3:
        raise ValueError(
            "transition predecessor is not a version-3 baseline document",
        )
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("transition predecessor entries are invalid")
    predecessor_entry = entries.get(scenario_name)
    if not isinstance(predecessor_entry, dict):
        raise ValueError(
            "transition scenario is absent from its predecessor baseline",
        )
    if canonical_sha256(predecessor_entry) != lineage.entry_sha256:
        raise ValueError(
            "transition predecessor entry digest differs from git",
        )
    predecessor_policy = predecessor_entry.get("policy")
    if not isinstance(predecessor_policy, dict):
        raise ValueError("transition predecessor policy is invalid")
    if (
        predecessor_entry.get("scenario_name") != scenario_name
        or predecessor_entry.get("scenario_path") != contract.reference.runtime_input.scenario_path
        or predecessor_policy.get("policy_version") != 3
        or predecessor_policy.get("mode") != "gate"
        or predecessor_policy.get("reference_commit") != policy.reference_commit
        or predecessor_policy.get("workload") != policy.workload.model_dump(mode="json")
        or predecessor_entry.get("reference_input") != contract.reference.runtime_input.model_dump(mode="json")
        or predecessor_entry.get("semantic_envelope") != contract.reference.semantic_envelope.model_dump(mode="json")
    ):
        raise ValueError(
            "transition predecessor does not bind the exact reference endpoint",
        )


class GitIdentity(_StrictModel):
    commit: str
    dirty: bool
    status: list[str]
    runtime_manifest: list[RuntimeSource]

    @field_validator("commit")
    @classmethod
    def _valid_commit(cls, value: str) -> str:
        if not _FULL_COMMIT_PATTERN.fullmatch(value):
            raise ValueError("git identity requires a full lowercase SHA")
        return value

    @model_validator(mode="after")
    def _valid_manifest(self) -> Self:
        paths = [source.path for source in self.runtime_manifest]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("runtime tree manifest must be unique and path-sorted")
        if self.dirty != bool(self.status):
            raise ValueError("git dirty flag must agree with porcelain status")
        return self


class BenchmarkRunnerIdentity(_StrictModel):
    """Exact runner labels recorded by local and hosted comparisons."""

    provider: Literal["local", "github-actions"]
    image: str
    labels: dict[str, str]

    @field_validator("image")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "runner identity strings must be non-empty and trimmed",
            )
        return value

    @field_validator("labels")
    @classmethod
    def _complete_labels(cls, value: dict[str, str]) -> dict[str, str]:
        expected = {
            "image_os",
            "image_version",
            "runner_arch",
            "runner_environment",
            "runner_group",
            "runner_name",
            "runner_os",
        }
        if set(value) != expected or any(not label or label != label.strip() for label in value.values()):
            raise ValueError(
                "runner labels must contain the exact non-empty identity set",
            )
        return value


class BenchmarkEnvironment(_StrictModel):
    """Typed, non-null hardware and software identity for a decision."""

    missing_text_policy: Literal["unavailable"]
    os: str
    kernel: str
    architecture: str
    cpu_model: str
    logical_core_count: int = Field(strict=True, gt=0)
    physical_core_count: int = Field(strict=True, gt=0)
    physical_core_count_source: Literal[
        "psutil",
        "linux_topology",
    ]
    cpu_affinity: list[int]
    total_ram_bytes: int = Field(strict=True, gt=0)
    total_ram_source: Literal["psutil", "sysconf"]
    python_implementation: str
    python_version: str
    dependencies: dict[str, str]
    dependency_lock_sha256: str
    runner_identity: BenchmarkRunnerIdentity
    runner_image: str
    runner_labels: dict[str, str]
    threading_environment: dict[str, str]
    unprofiled_peak_memory_mb: None = None

    @field_validator(
        "os",
        "kernel",
        "architecture",
        "cpu_model",
        "python_implementation",
        "python_version",
        "runner_image",
    )
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError(
                "benchmark environment strings must be non-empty and trimmed",
            )
        return value

    @field_validator("dependency_lock_sha256")
    @classmethod
    def _valid_lock_digest(cls, value: str) -> str:
        return _validate_sha256(value, "environment dependency-lock digest")

    @model_validator(mode="after")
    def _complete_environment(self) -> Self:
        if self.physical_core_count > self.logical_core_count:
            raise ValueError(
                "physical core count cannot exceed logical core count",
            )
        if (
            self.cpu_affinity != sorted(self.cpu_affinity)
            or len(self.cpu_affinity) != len(set(self.cpu_affinity))
            or any(cpu < 0 for cpu in self.cpu_affinity)
        ):
            raise ValueError(
                "CPU affinity must be unique, sorted, and non-negative",
            )
        expected_dependencies = {
            "numpy",
            "scipy",
            "networkx",
            "pydantic",
            "pyproj",
            "PyYAML",
            "shapely",
        }
        if set(self.dependencies) != expected_dependencies or any(
            not value or value != value.strip() for value in self.dependencies.values()
        ):
            raise ValueError(
                "dependency versions must contain the exact benchmark set",
            )
        expected_threading = {
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        }
        if set(self.threading_environment) != expected_threading or any(
            not value or value != value.strip() for value in self.threading_environment.values()
        ):
            raise ValueError(
                "threading environment must contain every declared variable",
            )
        if self.runner_image != self.runner_identity.image or self.runner_labels != self.runner_identity.labels:
            raise ValueError(
                "runner identity aliases must agree exactly",
            )
        return self


class BenchmarkBaselineIdentity(_StrictModel):
    """Exact baseline document and selected-entry identity."""

    authoritative: bool
    source: Literal["checked_in", "custom"]
    document_sha256: str
    entry_sha256: str

    @field_validator("document_sha256", "entry_sha256")
    @classmethod
    def _valid_digests(cls, value: str) -> str:
        return _validate_sha256(value, "baseline digest")

    @model_validator(mode="after")
    def _valid_source(self) -> Self:
        if self.authoritative != (self.source == "checked_in"):
            raise ValueError(
                "baseline authority must agree with its source class",
            )
        return self


class TransitionTimingAssessment(_StrictModel):
    """Explicit refusal to make a timing comparison across workloads."""

    applicability: Literal["not_applicable"] = "not_applicable"
    reason: Literal["workloads_differ"] = "workloads_differ"


class FinalTreeVerification(_StrictModel):
    """Content and production-run bridge from comparison tree to final commit."""

    format_version: Literal[4] = POLICY_VERSION
    created_at_utc: str
    status: Literal["pass"] = "pass"
    comparison_artifact_sha256: str
    scenario_name: str
    comparison_candidate_identity: GitIdentity
    final_identity: GitIdentity
    comparison_runtime_input: RuntimeInputManifest
    comparison_semantic_envelope: SemanticEnvelope
    reproduction_run: WorkerRun

    @field_validator("created_at_utc")
    @classmethod
    def _valid_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "final-tree timestamp must be ISO-8601",
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                "final-tree timestamp must be timezone-aware",
            )
        return value

    @field_validator("comparison_artifact_sha256")
    @classmethod
    def _valid_artifact_digest(cls, value: str) -> str:
        return _validate_sha256(value, "comparison artifact digest")

    @model_validator(mode="after")
    def _internally_consistent(self) -> Self:
        if not self.scenario_name or self.scenario_name != self.scenario_name.strip():
            raise ValueError(
                "verification scenario name must be non-empty and trimmed",
            )
        if self.final_identity.dirty or self.final_identity.status:
            raise ValueError(
                "final-tree verification requires a clean final identity",
            )
        if (
            self.comparison_candidate_identity.dirty
            and self.comparison_candidate_identity.commit == self.final_identity.commit
        ):
            raise ValueError(
                "a dirty comparison tree must advance to a final commit",
            )
        if self.comparison_candidate_identity.runtime_manifest != self.final_identity.runtime_manifest:
            raise ValueError(
                "final runtime manifest differs from comparison candidate",
            )
        if self.reproduction_run.revision != "candidate":
            raise ValueError(
                "final-tree reproduction must be a candidate worker run",
            )
        if self.reproduction_run.commit != self.final_identity.commit:
            raise ValueError(
                "reproduction worker commit differs from final identity",
            )
        if self.reproduction_run.runtime_input != self.comparison_runtime_input:
            raise ValueError(
                "final-tree runtime input differs from comparison candidate",
            )
        if self.reproduction_run.semantic_envelope != self.comparison_semantic_envelope:
            raise ValueError(
                "final-tree semantics differ from comparison candidate",
            )
        manifest_by_path = {source.path: source for source in self.final_identity.runtime_manifest}
        for source in self.reproduction_run.runtime_input.sources:
            final_source = manifest_by_path.get(source.path)
            if final_source is None or final_source.sha256 != source.sha256 or final_source.mode != source.mode:
                raise ValueError(
                    f"final-tree runtime input is not bound to the final identity at {source.path!r}",
                )
        return self


class TransitionFinalTreeVerification(_StrictModel):
    """Duration-free bridge from a transition snapshot to one clean commit."""

    format_version: Literal[4] = POLICY_VERSION
    created_at_utc: str
    status: Literal["transition_qualified"] = "transition_qualified"
    transition_artifact_sha256: str
    scenario_name: str
    transition_candidate_identity: GitIdentity
    final_identity: GitIdentity
    transition_runtime_input: RuntimeInputManifest
    transition_semantic_envelope: SemanticEnvelope
    reproduction_closure: ProductionClosureRun
    timing_assessment: TransitionTimingAssessment

    @field_validator("created_at_utc")
    @classmethod
    def _valid_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "transition final-tree timestamp must be ISO-8601",
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                "transition final-tree timestamp must be timezone-aware",
            )
        return value

    @field_validator("transition_artifact_sha256")
    @classmethod
    def _valid_artifact_digest(cls, value: str) -> str:
        return _validate_sha256(value, "transition artifact digest")

    @model_validator(mode="after")
    def _internally_consistent(self) -> Self:
        if self.final_identity.dirty or self.final_identity.status:
            raise ValueError(
                "transition final-tree verification requires a clean identity",
            )
        if (
            self.transition_candidate_identity.dirty
            and self.transition_candidate_identity.commit == self.final_identity.commit
        ):
            raise ValueError(
                "dirty transition snapshot must advance to a final commit",
            )
        if self.transition_candidate_identity.runtime_manifest != self.final_identity.runtime_manifest:
            raise ValueError(
                "final runtime manifest differs from transition candidate",
            )
        if self.reproduction_closure.revision != "candidate":
            raise ValueError(
                "transition reproduction must be a candidate closure",
            )
        if self.reproduction_closure.commit != self.final_identity.commit:
            raise ValueError(
                "transition reproduction commit differs from final identity",
            )
        if (
            self.reproduction_closure.runtime_input != self.transition_runtime_input
            or self.reproduction_closure.semantic_envelope != self.transition_semantic_envelope
        ):
            raise ValueError(
                "transition final-tree workload differs from candidate endpoint",
            )
        manifest_by_path = {source.path: source for source in self.final_identity.runtime_manifest}
        for source in self.reproduction_closure.runtime_input.sources:
            final_source = manifest_by_path.get(source.path)
            if final_source is None or final_source.sha256 != source.sha256 or final_source.mode != source.mode:
                raise ValueError(
                    f"transition final closure is not bound to the final identity at {source.path!r}",
                )
        return self


class ComparisonArtifact(_StrictModel):
    """Always-written ordinary paired-gate evidence."""

    format_version: Literal[4] = POLICY_VERSION
    created_at_utc: str
    scenario_name: str
    status: Literal["pass", "fail", "inconclusive", "error"]
    errors: list[str]
    policy: BenchmarkPolicy | None
    baseline_identity: BenchmarkBaselineIdentity | None
    environment: BenchmarkEnvironment | None
    reference_identity: GitIdentity | None
    candidate_identity: GitIdentity | None
    warmups: dict[str, WorkerRun]
    pairs: list[PairSample]
    decision: PerformanceDecision | None

    @field_validator("created_at_utc")
    @classmethod
    def _valid_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("artifact timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("artifact timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _internally_consistent(self) -> Self:
        if not self.scenario_name or self.scenario_name != self.scenario_name.strip():
            raise ValueError("artifact scenario name must be non-empty and trimmed")
        if set(self.warmups) - {"reference", "candidate"}:
            raise ValueError("artifact warm-up revision keys are invalid")
        if any(run.revision != revision for revision, run in self.warmups.items()):
            raise ValueError("artifact warm-up revision is mislabeled")
        if [pair.pair_index for pair in self.pairs] != list(
            range(len(self.pairs)),
        ):
            raise ValueError("artifact pair indexes must be contiguous and ordered")

        if self.status == "error":
            if not self.errors or self.decision is not None:
                raise ValueError(
                    "error artifacts require errors and cannot claim a decision",
                )
            return self

        if self.policy is None:
            raise ValueError("decision artifacts require a benchmark policy")
        if self.baseline_identity is None:
            raise ValueError(
                "decision artifacts require an exact baseline identity",
            )
        if self.errors:
            raise ValueError("decision artifacts cannot contain execution errors")
        if set(self.warmups) != {"reference", "candidate"}:
            raise ValueError("decision artifacts require both warm-up runs")
        if self.reference_identity is None or self.candidate_identity is None:
            raise ValueError("decision artifacts require both git identities")
        if self.environment is None:
            raise ValueError(
                "decision artifacts require typed environment metadata",
            )
        if self.reference_identity.commit != self.policy.reference_commit:
            raise ValueError(
                "reference identity disagrees with policy reference commit",
            )
        if self.baseline_identity.authoritative:
            baseline_source = {source.path: source for source in self.candidate_identity.runtime_manifest}.get(
                "tests/benchmarks/baselines.json"
            )
            if baseline_source is None or baseline_source.sha256 != self.baseline_identity.document_sha256:
                raise ValueError(
                    "authoritative baseline is not bound to the candidate runtime manifest",
                )

        identities = {
            "reference": self.reference_identity,
            "candidate": self.candidate_identity,
        }
        all_runs = [
            *self.warmups.values(),
            *[run for pair in self.pairs for run in (pair.reference, pair.candidate)],
        ]
        reference_runtime_input = self.warmups["reference"].runtime_input
        reference_semantics = self.warmups["reference"].semantic_envelope
        for run in all_runs:
            identity = identities[run.revision]
            if run.commit != identity.commit:
                raise ValueError(
                    f"{run.revision} worker commit disagrees with its artifact identity",
                )
            manifest_by_path = {source.path: source for source in identity.runtime_manifest}
            for source in run.runtime_input.sources:
                identity_source = manifest_by_path.get(source.path)
                if (
                    identity_source is None
                    or identity_source.sha256 != source.sha256
                    or identity_source.mode != source.mode
                ):
                    raise ValueError(
                        f"{run.revision} runtime input is not bound to its git identity at {source.path!r}",
                    )
        candidate_runtime_input = self.warmups["candidate"].runtime_input
        if self.environment.dependency_lock_sha256 not in {
            reference_runtime_input.dependency_lock_sha256,
            candidate_runtime_input.dependency_lock_sha256,
        } or (reference_runtime_input.dependency_lock_sha256 != candidate_runtime_input.dependency_lock_sha256):
            raise ValueError(
                "environment dependency lock disagrees with worker inputs",
            )

        if self.policy.mode != "gate":
            raise ValueError(
                "measurement-only entries cannot produce a comparison artifact",
            )
        if len(self.pairs) != self.policy.timed_pairs:
            raise ValueError("decision artifacts require every declared pair")
        if self.decision is None or self.decision.status != self.status:
            raise ValueError("artifact status must equal its paired decision")
        for run in all_runs:
            if run.runtime_input != reference_runtime_input:
                raise ValueError(
                    "artifact worker runtime inputs are not exact matches",
                )
            if run.semantic_envelope != reference_semantics:
                raise ValueError(
                    "artifact worker semantic envelopes are not exact matches",
                )
        recomputed = evaluate_paired_samples(
            self.policy,
            reference_seconds=[pair.reference.duration_s for pair in self.pairs],
            candidate_seconds=[pair.candidate.duration_s for pair in self.pairs],
        )
        if recomputed != self.decision:
            raise ValueError("artifact decision disagrees with its raw samples")
        return self


class TransitionArtifact(_StrictModel):
    """Duration-free, digest-bearing workload-transition evidence."""

    format_version: Literal[4] = POLICY_VERSION
    created_at_utc: str
    scenario_name: str
    status: Literal[
        "transition_qualified",
        "transition_rejected",
        "error",
    ]
    errors: list[str]
    policy: TransitionPolicy | None
    baseline_identity: BenchmarkBaselineIdentity | None
    environment: BenchmarkEnvironment | None
    reference_identity: GitIdentity | None
    candidate_identity: GitIdentity | None
    closures: dict[str, ProductionClosureRun]
    contract: WorkloadTransitionContract | None
    verified_approvals: list[TransitionApproval]
    timing_assessment: TransitionTimingAssessment

    @field_validator("created_at_utc")
    @classmethod
    def _valid_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "transition artifact timestamp must be ISO-8601",
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                "transition artifact timestamp must be timezone-aware",
            )
        return value

    @model_validator(mode="after")
    def _internally_consistent(self) -> Self:
        if not self.scenario_name or self.scenario_name != self.scenario_name.strip():
            raise ValueError(
                "transition scenario name must be non-empty and trimmed",
            )
        if set(self.closures) - {"reference", "candidate"}:
            raise ValueError("transition closure revision keys are invalid")
        if any(closure.revision != revision for revision, closure in self.closures.items()):
            raise ValueError("transition closure revision is mislabeled")
        if self.status != "transition_qualified":
            if not self.errors or self.verified_approvals:
                raise ValueError(
                    "rejected/error transitions require errors and no verified approvals",
                )
            return self

        if self.errors:
            raise ValueError(
                "qualified transition cannot contain execution errors",
            )
        if (
            self.policy is None
            or self.baseline_identity is None
            or self.environment is None
            or self.reference_identity is None
            or self.candidate_identity is None
            or self.contract is None
            or set(self.closures) != {"reference", "candidate"}
        ):
            raise ValueError(
                "qualified transition requires complete policy, baseline, "
                "environment, identities, closures, and contract",
            )
        if self.reference_identity.commit != self.policy.reference_commit:
            raise ValueError(
                "transition reference identity disagrees with policy",
            )
        if self.baseline_identity.authoritative:
            baseline_source = {source.path: source for source in self.candidate_identity.runtime_manifest}.get(
                "tests/benchmarks/baselines.json"
            )
            if baseline_source is None or baseline_source.sha256 != self.baseline_identity.document_sha256:
                raise ValueError(
                    "authoritative transition baseline is not bound to the candidate runtime manifest",
                )

        identities = {
            "reference": self.reference_identity,
            "candidate": self.candidate_identity,
        }
        for revision, closure in self.closures.items():
            identity = identities[revision]
            if closure.commit != identity.commit:
                raise ValueError(
                    f"{revision} closure commit disagrees with its identity",
                )
            manifest_by_path = {source.path: source for source in identity.runtime_manifest}
            for source in closure.runtime_input.sources:
                identity_source = manifest_by_path.get(source.path)
                if (
                    identity_source is None
                    or identity_source.sha256 != source.sha256
                    or identity_source.mode != source.mode
                ):
                    raise ValueError(
                        f"{revision} closure is not bound to its git identity at {source.path!r}",
                    )
        reference = self.closures["reference"]
        candidate = self.closures["candidate"]
        if self.environment.dependency_lock_sha256 != reference.runtime_input.dependency_lock_sha256:
            raise ValueError(
                "transition environment dependency lock disagrees with closure",
            )
        verified = validate_workload_transition(
            reference,
            candidate,
            self.contract,
        )
        if self.verified_approvals != verified:
            raise ValueError(
                "transition artifact approvals differ from verified contract",
            )
        return self


@dataclass(frozen=True)
class BenchmarkResult:
    """One explicit measurement-only production run."""

    scenario_name: str
    unit_count: int
    wall_clock_s: float
    ticks_executed: int
    ticks_per_second: float
    peak_memory_mb: float | None
    hotspots: list[tuple[str, float, int]] = field(default_factory=list)
    seed: int = 42
    winner: str | None = None
    commit: str = "unknown"
    mode: Literal["measurement_only"] = "measurement_only"


class BenchmarkComparisonError(RuntimeError):
    """Raised after a failing comparison artifact has been written."""


class BenchmarkTransitionError(RuntimeError):
    """Raised after rejected/error transition evidence has been written."""


class _WorkloadTransitionRejected(ValueError):
    """Internal distinction between contract rejection and execution error."""


class BenchmarkBaseline:
    """Load strict v4 baselines; legacy unpaired decisions are disabled."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or BASELINES_PATH

    def load_file(self) -> BaselineFile:
        if not self._path.is_file():
            raise FileNotFoundError(f"benchmark baseline not found: {self._path}")
        try:
            return BaselineFile.model_validate_json(
                self._path.read_text(encoding="utf-8"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid version-4 benchmark baseline {self._path}: {exc}",
            ) from exc

    def load(self) -> dict[str, BaselineEntry]:
        return dict(self.load_file().entries)

    def save_file(self, baseline: BaselineFile) -> None:
        payload = baseline.model_dump(mode="json")
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def check_regression(
        self,
        scenario_name: str,
        result: BenchmarkResult,
        margin: float = 0.2,
    ) -> tuple[bool, str]:
        del scenario_name, result, margin
        raise ValueError(
            "legacy unpaired regression decisions are unsupported; use the "
            "version-4 paired comparison harness or label the run "
            "measurement_only",
        )


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------


def _positive_finite_samples(
    samples: list[float],
    *,
    label: str,
    expected: int = 3,
) -> list[float]:
    if len(samples) != expected:
        raise ValueError(f"{label} requires exactly {expected} timed samples")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in samples
    ):
        raise ValueError(f"{label} samples must be finite and strictly positive")
    return [float(value) for value in samples]


def _relative_range(samples: list[float]) -> float:
    median = statistics.median(samples)
    return (max(samples) - min(samples)) / median


def evaluate_paired_samples(
    policy: BenchmarkPolicy,
    *,
    reference_seconds: list[float],
    candidate_seconds: list[float],
) -> PerformanceDecision:
    """Apply the exact version-4 paired gate policy to raw samples."""
    if policy.mode != "gate":
        raise ValueError(
            f"{policy.mode} entries cannot produce a regression decision",
        )
    if policy.maximum_median_slowdown_ratio is None or policy.maximum_relative_sample_range is None:
        raise ValueError("paired gate is missing its timing thresholds")
    reference = _positive_finite_samples(
        reference_seconds,
        label="reference",
        expected=policy.timed_pairs,
    )
    candidate = _positive_finite_samples(
        candidate_seconds,
        label="candidate",
        expected=policy.timed_pairs,
    )
    ratios = [
        candidate_sample / reference_sample
        for reference_sample, candidate_sample in zip(
            reference,
            candidate,
            strict=True,
        )
    ]
    median_ratio = statistics.median(ratios)
    reference_spread = _relative_range(reference)
    candidate_spread = _relative_range(candidate)

    if (
        reference_spread > policy.maximum_relative_sample_range
        or candidate_spread > policy.maximum_relative_sample_range
    ):
        return PerformanceDecision(
            status="inconclusive",
            ratios=ratios,
            median_ratio=median_ratio,
            reference_relative_range=reference_spread,
            candidate_relative_range=candidate_spread,
            reason=("sample dispersion exceeds the declared maximum relative range"),
        )
    if median_ratio > policy.maximum_median_slowdown_ratio:
        return PerformanceDecision(
            status="fail",
            ratios=ratios,
            median_ratio=median_ratio,
            reference_relative_range=reference_spread,
            candidate_relative_range=candidate_spread,
            reason="median paired slowdown exceeds the declared maximum",
        )
    return PerformanceDecision(
        status="pass",
        ratios=ratios,
        median_ratio=median_ratio,
        reference_relative_range=reference_spread,
        candidate_relative_range=candidate_spread,
        reason="paired timing and dispersion satisfy the declared policy",
    )


# ---------------------------------------------------------------------------
# Revision-local production worker
# ---------------------------------------------------------------------------


def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=check,
        timeout=120,
    )


def _full_commit(repo_root: Path) -> str:
    commit = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    if not _FULL_COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("git did not return a full lowercase commit SHA")
    return commit


def _repo_mode(repo_root: Path, relative_path: str) -> Literal["100644", "100755"]:
    path = repo_root / relative_path
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(
            f"runtime source symlinks are unsupported: {relative_path}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"runtime source is not a regular file: {relative_path}",
        )
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return "100755" if metadata.st_mode & executable_bits else "100644"


def _runtime_source(
    repo_root: Path,
    path: Path,
    *,
    role: str,
) -> RuntimeSource:
    resolved_root = repo_root.resolve()
    relative_path = path.relative_to(repo_root).as_posix()
    mode = _repo_mode(repo_root, relative_path)
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"runtime source is outside repository: {path}") from exc
    return RuntimeSource(
        path=relative,
        sha256=_file_sha256(resolved),
        mode=mode,
        role=role,
    )


def _contains_exact_identifier(value: Any, identifiers: set[str]) -> bool:
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, Mapping):
        return any(key in identifiers or _contains_exact_identifier(item, identifiers) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_exact_identifier(item, identifiers) for item in value)
    return False


def _resolved_data_sources(
    repo_root: Path,
    scenario_path: Path,
    identifiers: set[str],
    external_runtime_paths: frozenset[str],
) -> list[RuntimeSource]:
    """Resolve exact catalog files carrying runtime-selected identifiers."""
    import yaml

    sources: dict[str, RuntimeSource] = {}

    def add(path: Path, role: str) -> None:
        source = _runtime_source(repo_root, path, role=role)
        existing = sources.get(source.path)
        if existing is not None and existing.sha256 != source.sha256:
            raise ValueError(f"runtime source path changed during capture: {source.path}")
        sources[source.path] = source

    add(scenario_path, "scenario")
    add(repo_root / "uv.lock", "dependency_lock")

    data_root = repo_root / "data"
    for path in sorted(data_root.rglob("*.yaml")):
        if path.resolve() == scenario_path.resolve():
            continue
        relative_parts = path.relative_to(data_root).parts
        if relative_parts[0] == "scenarios":
            continue
        if relative_parts[0] == "validation":
            continue
        if len(relative_parts) >= 3 and relative_parts[0] == "eras" and relative_parts[2] == "scenarios":
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"cannot inspect runtime data source {path}: {exc}") from exc
        if _contains_exact_identifier(raw, identifiers):
            role = path.relative_to(data_root).parts[0]
            add(path, f"resolved_{role}")
    for relative_path in sorted(external_runtime_paths):
        add(
            repo_root / relative_path,
            "external_runtime_input",
        )
    return [sources[path] for path in sorted(sources)]


def _definition_identifier(value: Any, *names: str) -> str | None:
    for name in names:
        candidate = getattr(value, name, None)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _normalize_scenario_configuration(
    value: dict[str, Any],
) -> dict[str, Any]:
    """Project schema-111 and schema-112 scenarios into one v3 contract."""
    for side in value.get("sides", []):
        if not isinstance(side, dict):
            raise ValueError(
                "normalized scenario side must be a mapping",
            )
        for unit in side.get("units", []):
            if not isinstance(unit, dict):
                raise ValueError(
                    "normalized scenario unit must be a mapping",
                )
            unit.setdefault("position", None)
            overrides = unit.get("overrides")
            if not isinstance(overrides, dict):
                raise ValueError(
                    "normalized scenario unit overrides must be a mapping",
                )
            for field_name in (
                "armor_front",
                "display_name",
                "heading",
            ):
                overrides.setdefault(field_name, None)
    return value


def _normalize_morale_timing_identity(
    effective_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Unify the implicit and explicit discrete-time morale defaults.

    The Phase 112 runtime already interpreted an absent
    ``use_continuous_time`` setting as ``False`` in ``MoraleConfig``. Phase
    113 exposes that same effective default through the typed calibration
    schema. The benchmark policy therefore omits only an exact ``False`` from
    all three compatibility views so the historical implicit default and the
    current explicit default retain one workload identity. ``True`` remains in
    the manifest and changes its fingerprint.
    """
    nested_paths = (
        ("configuration", "calibration_overrides", "morale"),
        ("calibration", "morale"),
    )
    for path in nested_paths:
        value: Any = effective_inputs
        for key in path:
            if not isinstance(value, dict):
                break
            value = value.get(key)
        if isinstance(value, dict) and value.get("use_continuous_time") is False:
            del value["use_continuous_time"]

    calibration_flat = effective_inputs.get("calibration_flat")
    if isinstance(calibration_flat, dict) and calibration_flat.get("morale_use_continuous_time") is False:
        del calibration_flat["morale_use_continuous_time"]
    return effective_inputs


def _build_effective_inputs(context: Any) -> tuple[dict[str, Any], set[str]]:
    """Capture loader-resolved values that determine the workload."""
    units = [unit for side in sorted(context.units_by_side) for unit in context.units_by_side[side]]
    roster: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    unit_definitions: dict[str, Any] = {}
    weapon_definitions: dict[str, Any] = {}
    ammunition_definitions: dict[str, Any] = {}
    sensor_definitions: dict[str, Any] = {}
    signature_definitions: dict[str, Any] = {}

    loaded_unit_definitions = context.unit_loader.definitions()
    for unit in units:
        identifiers.add(unit.unit_type)
        unit_definition = loaded_unit_definitions[unit.unit_type]
        unit_definitions[unit.unit_type] = _canonical_value(unit_definition)
        signature_id = _definition_identifier(
            unit_definition,
            "signature_profile",
            "signature_profile_id",
        )
        if signature_id is not None:
            identifiers.add(signature_id)
            signature_definitions[signature_id] = _canonical_value(
                context.sig_loader.get_profile(signature_id),
            )

        loadout = [resolution.topology() for resolution in context.equipment_resolutions[unit.entity_id]]
        roster.append(
            {
                "side": (unit.side if isinstance(unit.side, str) else unit.side.value),
                "entity_id": unit.entity_id,
                "definition_id": unit.unit_type,
                "position": list(unit.position),
                "loadout": loadout,
            }
        )
        for resolution in context.equipment_resolutions[unit.entity_id]:
            for identifier in (
                resolution.source_equipment.equipment_id,
                resolution.target_id,
                resolution.attached_to_target_id,
            ):
                if isinstance(identifier, str) and identifier:
                    identifiers.add(identifier)

        for attachment in context.unit_weapons[unit.entity_id]:
            weapon_id = attachment.weapon.definition.weapon_id
            identifiers.add(weapon_id)
            weapon_definitions[weapon_id] = _canonical_value(
                attachment.weapon.definition,
            )
            for ammunition in attachment.ammunition:
                ammo_id = ammunition.ammo_id
                identifiers.add(ammo_id)
                ammunition_definitions[ammo_id] = _canonical_value(
                    ammunition,
                )
        for sensor in context.unit_sensors[unit.entity_id]:
            identifiers.add(sensor.sensor_id)
            sensor_definitions[sensor.sensor_id] = _canonical_value(
                sensor.definition,
            )

    commander_profiles: dict[str, Any] = {}
    commander = getattr(context, "commander_engine", None)
    if commander is not None:
        for unit in units:
            profile = commander.get_personality(unit.entity_id)
            if profile is None:
                continue
            profile_id = _definition_identifier(profile, "profile_id")
            if profile_id is not None:
                identifiers.add(profile_id)
                commander_profiles[profile_id] = _canonical_value(profile)

    school_state: dict[str, Any] | None = None
    school_registry = getattr(context, "school_registry", None)
    if school_registry is not None:
        school_state = _canonical_value(school_registry.get_state())
        for school in school_registry.all_schools():
            identifiers.add(school.school_id)

    canonical_config = _canonical_value(context.config)
    if not isinstance(canonical_config, dict):
        raise ValueError(
            "canonical scenario configuration must be a mapping",
        )
    config = _normalize_scenario_configuration(canonical_config)
    era_contract = getattr(context, "era_runtime_contract", None)
    if era_contract is not None:
        # Phase 114 preserves the authored per-resolution values alongside a
        # uniform ``tick_duration_seconds`` shorthand.  Earlier runtimes
        # materialized that shorthand directly into ``tick_resolution``.
        # Benchmark identity describes executed cadence, so project both
        # representations onto the effective contract before comparing the
        # historical reference and current candidate.
        config["tick_resolution"] = {
            "strategic_s": era_contract.strategic_s,
            "operational_s": era_contract.operational_s,
            "tactical_s": era_contract.tactical_s,
        }
    for side in config.get("sides", []):
        for key in ("commander_profile", "doctrine_template"):
            value = side.get(key)
            if isinstance(value, str) and value:
                identifiers.add(value)
    effective = {
        "configuration": config,
        "calibration": _canonical_value(context.calibration),
        "calibration_flat": _canonical_value(context.cal_flat),
        "era": _canonical_value(context.era_config),
        "roster": roster,
        "resolved_definitions": {
            "units": {key: unit_definitions[key] for key in sorted(unit_definitions)},
            "weapons": {key: weapon_definitions[key] for key in sorted(weapon_definitions)},
            "ammunition": {key: ammunition_definitions[key] for key in sorted(ammunition_definitions)},
            "sensors": {key: sensor_definitions[key] for key in sorted(sensor_definitions)},
            "signatures": {key: signature_definitions[key] for key in sorted(signature_definitions)},
            "commander_profiles": {key: commander_profiles[key] for key in sorted(commander_profiles)},
            "schools": school_state,
        },
    }
    return _normalize_morale_timing_identity(effective), identifiers


def _runtime_input_manifest(
    repo_root: Path,
    scenario_path: Path,
    context: Any,
    *,
    seed: int,
    max_ticks: int,
    recorder_config: dict[str, Any],
) -> RuntimeInputManifest:
    effective_inputs, identifiers = _build_effective_inputs(context)
    scenario_relative = scenario_path.relative_to(repo_root).as_posix()
    external_runtime_paths = _scenario_external_runtime_paths(
        repo_root,
        scenario_relative,
    )
    sources = _resolved_data_sources(
        repo_root,
        scenario_path,
        identifiers,
        external_runtime_paths,
    )
    payload = {
        "policy_version": RUNTIME_INPUT_POLICY_VERSION,
        "scenario_path": scenario_relative,
        "scenario_sha256": _file_sha256(scenario_path),
        "dependency_lock_sha256": _file_sha256(repo_root / "uv.lock"),
        "seed": seed,
        "max_ticks": max_ticks,
        "recorder_config": _normalize_recorder_config_identity(
            recorder_config,
        ),
        "effective_inputs": effective_inputs,
        "sources": [source.model_dump(mode="python") for source in sources],
    }
    return RuntimeInputManifest(
        **payload,
        fingerprint=canonical_sha256(payload),
    )


def _normalize_recorder_config_identity(
    recorder_config: dict[str, Any],
) -> dict[str, Any]:
    """Unify only new false strictness fields with legacy recorder behavior.

    Older benchmark revisions predate these fields.  Their absence means the
    same silent-overflow and extraction-fallback behavior now represented by
    an exact ``False``.  A true or otherwise non-false value remains in the
    manifest and therefore changes its fingerprint.
    """
    normalized = dict(recorder_config)
    for field_name in _LEGACY_FALSE_RECORDER_FIELDS:
        if normalized.get(field_name) is False:
            normalized.pop(field_name)
    return normalized


def _strict_recorder(context: Any) -> Any:
    from dataclasses import asdict as strict_asdict

    from stochastic_warfare.simulation.recorder import (
        RecorderConfig,
        SimulationRecorder,
    )

    class StrictBenchmarkRecorder(SimulationRecorder):
        @staticmethod
        def _extract_event_data(event: Any) -> dict[str, Any]:
            data = strict_asdict(event)
            data.pop("timestamp", None)
            data.pop("source", None)
            normalized = _canonical_value(data)
            if not isinstance(normalized, dict):
                raise ValueError("benchmark event payload must be a mapping")
            return normalized

        def _on_event(self, event: Any) -> None:
            if len(self._events) >= self._config.max_events:
                raise RuntimeError(
                    "strict benchmark recorder capacity would drop an event",
                )
            super()._on_event(event)

    config = RecorderConfig(
        max_events=WORKER_RECORDER_MAX_EVENTS,
        snapshot_interval_ticks=0,
        enabled=True,
    )
    return StrictBenchmarkRecorder(context.event_bus, config), config


def _semantic_envelope(
    context: Any,
    run_result: Any,
    recorder: Any,
) -> SemanticEnvelope:
    roster_loadout = [
        {
            "side": side,
            "entity_id": unit.entity_id,
            "definition_id": unit.unit_type,
            "position": list(unit.position),
            "loadout": [resolution.topology() for resolution in context.equipment_resolutions[unit.entity_id]],
        }
        for side in sorted(context.units_by_side)
        for unit in context.units_by_side[side]
    ]
    status_counts: dict[str, dict[str, int]] = {}
    for side in sorted(context.units_by_side):
        counts: dict[str, int] = {}
        for unit in context.units_by_side[side]:
            status = unit.status.name if hasattr(unit.status, "name") else str(unit.status)
            counts[status] = counts.get(status, 0) + 1
        status_counts[side] = {status: counts[status] for status in sorted(counts)}

    events = [
        {
            "tick": event.tick,
            "logical_timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "source": event.source,
            "data": event.data,
        }
        for event in recorder.events
    ]
    if len(events) >= WORKER_RECORDER_MAX_EVENTS:
        raise RuntimeError("strict benchmark recorder reached its capacity")

    victory = run_result.victory_result
    return SemanticEnvelope(
        unit_count=sum(len(units) for units in context.units_by_side.values()),
        roster_loadout_digest=canonical_sha256(roster_loadout),
        winner=victory.winning_side or None,
        victory_condition_type=victory.condition_type,
        ticks=run_result.ticks_executed,
        logical_duration_s=run_result.duration_s,
        status_counts=status_counts,
        event_count=len(events),
        event_digest=canonical_sha256(events),
    )


def _assert_revision_owned(symbol: Any, repo_root: Path) -> None:
    """Reject production code imported from outside the selected worktree."""
    source = Path(inspect.getfile(symbol)).resolve()
    try:
        source.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError(
            f"benchmark imported {symbol!r} outside selected revision: {source}",
        ) from exc


def _historical_reference_runtime(
    *,
    repo_root: Path,
    scenario_path: Path,
    seed: int,
    max_ticks: int,
    workload: BenchmarkWorkload,
) -> tuple[Any, Any, Any, Any]:
    """Construct the exact pre-factory runtime at the fixed reference commit.

    This candidate-owned compatibility adapter is deliberately restricted to
    the immutable Phase-112 reference identity. All production classes and
    data still come from that selected reference worktree.
    """
    if _full_commit(repo_root) != REFERENCE_COMMIT:
        raise RuntimeError(
            f"historical runtime adapter is restricted to the exact reference commit {REFERENCE_COMMIT}",
        )
    status = _git_status(repo_root)
    if status:
        raise RuntimeError(
            f"historical runtime adapter requires a clean reference tree: {status!r}",
        )

    from stochastic_warfare.core.types import Position
    from stochastic_warfare.simulation.engine import (
        EngineConfig,
        SimulationEngine,
    )
    from stochastic_warfare.simulation.scenario import ScenarioLoader
    from stochastic_warfare.simulation.victory import (
        ObjectiveState,
        VictoryEvaluator,
    )

    for symbol in (
        SimulationEngine,
        ScenarioLoader,
        VictoryEvaluator,
    ):
        _assert_revision_owned(symbol, repo_root)

    context = ScenarioLoader(repo_root / "data").load(
        scenario_path,
        seed=seed,
        calibration_overrides=(
            workload.calibration_patch.model_dump(
                mode="python",
                exclude_none=True,
            )
            or None
        ),
    )
    objectives = [
        ObjectiveState(
            objective_id=objective.objective_id,
            position=Position(
                easting=objective.position[0],
                northing=objective.position[1],
                altitude=(objective.position[2] if len(objective.position) == 3 else 0.0),
            ),
            radius_m=objective.radius_m,
        )
        for objective in context.config.objectives
    ]
    victory_evaluator = VictoryEvaluator(
        objectives=objectives,
        conditions=list(context.config.victory_conditions),
        event_bus=context.event_bus,
        max_duration_s=context.config.duration_hours * 3600.0,
    )
    recorder, recorder_config = _strict_recorder(context)
    engine = SimulationEngine(
        context,
        config=EngineConfig(
            max_ticks=max_ticks,
            snapshot_interval_ticks=0,
        ),
        victory_evaluator=victory_evaluator,
        recorder=recorder,
        strict_mode=True,
    )
    return context, engine, recorder, recorder_config


def _benchmark_timer() -> float:
    """Read the ordinary paired worker's timing clock."""
    return time.perf_counter()


def _execute_revision(
    *,
    repo_root: Path,
    scenario_relative: str,
    revision: Literal["reference", "candidate"],
    record_duration: bool,
    seed: int = 42,
    max_ticks: int = DEFAULT_MAX_TICKS,
    workload: BenchmarkWorkload | Mapping[str, Any] | None = None,
) -> WorkerRun | ProductionClosureRun:
    """Run one production revision with explicitly selected evidence scope."""
    repo_root = repo_root.resolve()
    scenario_path = (repo_root / scenario_relative).resolve()
    try:
        scenario_path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("scenario must be inside the selected repository") from exc
    if not scenario_path.is_file():
        raise FileNotFoundError(f"benchmark scenario not found: {scenario_path}")
    if seed != 42:
        raise ValueError("version-3 benchmark policy requires seed 42")

    if workload is None:
        matching_workloads = [
            entry.policy.workload
            for entry in BenchmarkBaseline().load().values()
            if entry.scenario_path == scenario_relative
        ]
        if len(matching_workloads) != 1:
            raise ValueError(
                "benchmark scenario must resolve one checked-in workload",
            )
        resolved_workload = matching_workloads[0]
    else:
        resolved_workload = BenchmarkWorkload.model_validate(workload)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # The candidate-owned compatibility adapter exists only for the exact
    # pre-factory Phase 112 reference.  Promoted references execute through
    # their own production SimulationRuntimeFactory just like candidates.
    if revision == "reference" and _full_commit(repo_root) == REFERENCE_COMMIT:
        context, engine, recorder, recorder_model = _historical_reference_runtime(
            repo_root=repo_root,
            scenario_path=scenario_path,
            seed=seed,
            max_ticks=max_ticks,
            workload=resolved_workload,
        )
    else:
        from stochastic_warfare.simulation.engine import EngineConfig
        from stochastic_warfare.simulation.runtime import (
            AnalysisVariant,
            SimulationRuntimeFactory,
        )

        _assert_revision_owned(SimulationRuntimeFactory, repo_root)
        engine_config = EngineConfig(
            max_ticks=max_ticks,
            snapshot_interval_ticks=0,
        )
        variant = AnalysisVariant(
            variant_id=f"benchmark_{resolved_workload.name}",
            calibration_patch=(
                resolved_workload.calibration_patch.model_dump(
                    mode="python",
                    exclude_none=True,
                )
            ),
        )
        prepared = SimulationRuntimeFactory().prepare(
            scenario_path,
            repo_root / "data",
            (variant,),
        )
        recorder_models: list[Any] = []

        def strict_recorder_factory(context: Any) -> Any:
            recorder, recorder_config = _strict_recorder(context)
            recorder_models.append(recorder_config)
            return recorder

        session = prepared.build(
            variant.variant_id,
            seed=seed,
            max_ticks=max_ticks,
            recorder_factory=strict_recorder_factory,
            engine_config=engine_config,
            strict_mode=True,
        )
        if len(recorder_models) != 1 or session.recorder is None:
            raise RuntimeError(
                "runtime factory did not construct one strict benchmark recorder",
            )
        context = session.context
        engine = session.engine
        recorder = session.recorder
        recorder_model = recorder_models[0]
    runtime_input = _runtime_input_manifest(
        repo_root,
        scenario_path,
        context,
        seed=seed,
        max_ticks=max_ticks,
        recorder_config=recorder_model.model_dump(mode="json"),
    )

    duration: float | None = None
    if record_duration:
        started = _benchmark_timer()
        run_result = engine.run()
        duration = _benchmark_timer() - started
        if not math.isfinite(duration) or duration <= 0.0:
            raise RuntimeError("benchmark worker produced an invalid duration")
    else:
        run_result = engine.run()

    common = {
        "revision": revision,
        "commit": _full_commit(repo_root),
        "runtime_input": runtime_input,
        "semantic_envelope": _semantic_envelope(
            context,
            run_result,
            recorder,
        ),
    }
    if duration is not None:
        return WorkerRun(duration_s=duration, **common)
    return ProductionClosureRun(**common)


def run_revision_worker(
    *,
    repo_root: Path,
    scenario_relative: str,
    revision: Literal["reference", "candidate"],
    seed: int = 42,
    max_ticks: int = DEFAULT_MAX_TICKS,
    workload: BenchmarkWorkload | Mapping[str, Any] | None = None,
) -> WorkerRun:
    """Run one production revision and collect one timing sample."""
    result = _execute_revision(
        repo_root=repo_root,
        scenario_relative=scenario_relative,
        revision=revision,
        record_duration=True,
        seed=seed,
        max_ticks=max_ticks,
        workload=workload,
    )
    if not isinstance(result, WorkerRun):
        raise AssertionError("timed worker returned duration-free evidence")
    return result


def run_revision_closure(
    *,
    repo_root: Path,
    scenario_relative: str,
    revision: Literal["reference", "candidate"],
    seed: int = 42,
    max_ticks: int = DEFAULT_MAX_TICKS,
    workload: BenchmarkWorkload | Mapping[str, Any] | None = None,
) -> ProductionClosureRun:
    """Run one production revision without collecting a timing sample."""
    result = _execute_revision(
        repo_root=repo_root,
        scenario_relative=scenario_relative,
        revision=revision,
        record_duration=False,
        seed=seed,
        max_ticks=max_ticks,
        workload=workload,
    )
    if not isinstance(result, ProductionClosureRun):
        raise AssertionError("duration-free worker returned timing evidence")
    return result


# ---------------------------------------------------------------------------
# Candidate-owned paired driver
# ---------------------------------------------------------------------------


def _is_loader_data_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return bool(path.parts) and path.parts[0] == "data" and path.suffix.lower() in _LOADER_DATA_SUFFIXES


def _is_runtime_path(
    relative_path: str,
    *,
    external_runtime_paths: frozenset[str] = frozenset(),
) -> bool:
    path = Path(relative_path)
    if relative_path in _RUNTIME_EXACT_PATHS:
        return True
    static_runtime_path = (
        bool(path.parts) and path.parts[0] in _RUNTIME_TOP_LEVEL and path.suffix.lower() in _STATIC_RUNTIME_SUFFIXES
    )
    return static_runtime_path or relative_path in external_runtime_paths


def _scenario_external_runtime_paths(
    repo_root: Path,
    scenario_relative: str,
) -> frozenset[str]:
    """Resolve external terrain files the production loader can consume."""
    import yaml

    scenario_path = (repo_root / scenario_relative).resolve()
    try:
        scenario_path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(
            "benchmark scenario must be inside the selected repository",
        ) from exc
    try:
        raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f"cannot inspect benchmark terrain inputs {scenario_path}: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("benchmark scenario root must be a mapping")
    terrain = raw.get("terrain")
    if not isinstance(terrain, dict):
        raise ValueError("benchmark scenario terrain must be a mapping")
    if terrain.get("terrain_source", "procedural") != "real":
        return frozenset()

    try:
        latitude = float(raw.get("latitude", 0.0))
        longitude = float(raw.get("longitude", 0.0))
        width_m = float(terrain["width_m"])
        height_m = float(terrain["height_m"])
        cell_size_m = float(terrain.get("cell_size_m", 100.0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "real-terrain benchmark dimensions are malformed",
        ) from exc
    if not all(
        math.isfinite(value)
        for value in (
            latitude,
            longitude,
            width_m,
            height_m,
            cell_size_m,
        )
    ):
        raise ValueError(
            "real-terrain benchmark coordinates and dimensions must be finite",
        )

    data_dir = Path(terrain.get("data_dir", "data/terrain_raw"))
    cache_dir = Path(terrain.get("cache_dir", "data/terrain_cache"))
    if not data_dir.is_absolute():
        data_dir = repo_root / data_dir
    if not cache_dir.is_absolute():
        cache_dir = repo_root / cache_dir
    resolved_root = repo_root.resolve()
    for label, directory in (
        ("terrain data", data_dir),
        ("terrain cache", cache_dir),
    ):
        try:
            directory.resolve().relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(
                f"{label} directory must be inside the benchmark repository",
            ) from exc

    meters_per_degree_latitude = 111_320.0
    meters_per_degree_longitude = meters_per_degree_latitude * math.cos(math.radians(latitude))
    if meters_per_degree_longitude == 0.0:
        raise ValueError(
            "real-terrain benchmark longitude scale is zero",
        )
    half_height = (height_m / 2.0) / meters_per_degree_latitude
    half_width = (width_m / 2.0) / meters_per_degree_longitude
    south = latitude - half_height
    west = longitude - half_width
    north = latitude + half_height
    east = longitude + half_width

    selected: set[Path] = set()
    tile_names = [
        (
            f"{'N' if tile_latitude >= 0 else 'S'}"
            f"{abs(tile_latitude):02d}"
            f"{'E' if tile_longitude >= 0 else 'W'}"
            f"{abs(tile_longitude):03d}"
        )
        for tile_latitude in range(
            math.floor(south),
            math.floor(north) + 1,
        )
        for tile_longitude in range(
            math.floor(west),
            math.floor(east) + 1,
        )
    ]
    srtm_paths: list[Path] = []
    for tile_name in tile_names:
        for suffix in (".hgt", ".tif", ".tiff"):
            candidate = data_dir / "srtm" / f"{tile_name}{suffix}"
            if candidate.is_file():
                srtm_paths.append(candidate)
                selected.add(candidate)
                break
    if srtm_paths:
        cache_payload = f"srtm:{south:.6f},{west:.6f},{north:.6f},{east:.6f}:{cell_size_m:.2f}"
        cache_key = hashlib.sha256(
            cache_payload.encode(),
        ).hexdigest()[:16]
        cache_path = cache_dir / f"srtm_{cache_key}.npz"
        if cache_path.is_file():
            selected.add(cache_path)

    copernicus_paths = sorted((data_dir / "copernicus").glob("*.tif"))
    if copernicus_paths:
        selected.add(copernicus_paths[0])
    for layer_name in ("roads", "buildings", "railways", "waterways"):
        layer_path = data_dir / "osm" / f"{layer_name}.geojson"
        if layer_path.is_file():
            selected.add(layer_path)

    relative_paths: set[str] = set()
    for selected_path in selected:
        try:
            relative = selected_path.resolve().relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(
                f"external runtime source is outside repository: {selected_path}",
            ) from exc
        if not _is_loader_data_path(relative.as_posix()):
            raise ValueError(
                f"unsupported external runtime source: {relative.as_posix()}",
            )
        relative_paths.add(relative.as_posix())
    return frozenset(relative_paths)


def _git_status(repo_root: Path) -> list[str]:
    output = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout
    return [line for line in output.splitlines() if line]


def _status_path(line: str) -> str:
    raw = line[3:]
    if " -> " in raw:
        raw = raw.split(" -> ", maxsplit=1)[1]
    return raw.strip('"')


def _runtime_tree_manifest(
    repo_root: Path,
    *,
    external_runtime_paths: frozenset[str] = frozenset(),
) -> list[RuntimeSource]:
    tracked = _git(repo_root, "ls-files", "-z").stdout.split("\0")
    untracked = _git(
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout.split("\0")
    relative_paths = sorted(
        {
            path
            for path in [*tracked, *untracked]
            if (
                path
                and _is_runtime_path(
                    path,
                    external_runtime_paths=external_runtime_paths,
                )
            )
        }
    )

    ignored = _git(
        repo_root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
    ).stdout.split("\0")
    ignored_runtime = sorted(
        {
            path
            for path in ignored
            if (
                path
                and _is_runtime_path(
                    path,
                    external_runtime_paths=external_runtime_paths,
                )
            )
        }
    )
    if ignored_runtime:
        raise ValueError(
            f"ignored runtime-affecting files are not benchmarkable: {ignored_runtime!r}",
        )

    return [
        _runtime_source(
            repo_root,
            repo_root / path,
            role="runtime_tree",
        )
        for path in relative_paths
    ]


def _git_identity(
    repo_root: Path,
    *,
    require_clean: bool,
    external_runtime_paths: frozenset[str] = frozenset(),
) -> GitIdentity:
    status = _git_status(repo_root)
    if require_clean and status:
        raise ValueError(
            f"benchmark worktree is dirty: {status!r}",
        )
    manifest = _runtime_tree_manifest(
        repo_root,
        external_runtime_paths=external_runtime_paths,
    )
    manifested = {source.path for source in manifest}
    missing_dirty_runtime = sorted(
        {
            path
            for line in status
            if _is_runtime_path(
                path := _status_path(line),
                external_runtime_paths=external_runtime_paths,
            )
            and path not in manifested
        }
    )
    if missing_dirty_runtime:
        raise ValueError(
            f"dirty runtime paths are absent from the candidate manifest: {missing_dirty_runtime!r}",
        )
    return GitIdentity(
        commit=_full_commit(repo_root),
        dirty=bool(status),
        status=status,
        runtime_manifest=manifest,
    )


def _materialize_candidate_snapshot(
    *,
    candidate_root: Path,
    snapshot_root: Path,
    identity: GitIdentity,
    scenario_relative: str,
    external_runtime_paths: frozenset[str],
) -> None:
    """Create one immutable candidate runtime tree for every paired worker."""
    _git(
        candidate_root,
        "clone",
        "--shared",
        "--no-checkout",
        str(candidate_root),
        str(snapshot_root),
    )
    _git(
        snapshot_root,
        "checkout",
        "--detach",
        identity.commit,
    )
    for expected_source in identity.runtime_manifest:
        source_path = candidate_root / expected_source.path
        current_source = _runtime_source(
            candidate_root,
            source_path,
            role=expected_source.role,
        )
        if current_source != expected_source:
            raise ValueError(
                f"candidate runtime source changed during snapshot capture: {expected_source.path!r}",
            )
        target_path = snapshot_root / expected_source.path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        target_path.chmod(
            0o755 if expected_source.mode == "100755" else 0o644,
        )

    snapshot_external_paths = _scenario_external_runtime_paths(
        snapshot_root,
        scenario_relative,
    )
    if snapshot_external_paths != external_runtime_paths:
        raise ValueError(
            "candidate external runtime closure changed during snapshot",
        )
    snapshot_manifest = _runtime_tree_manifest(
        snapshot_root,
        external_runtime_paths=snapshot_external_paths,
    )
    if snapshot_manifest != identity.runtime_manifest:
        raise ValueError(
            "candidate snapshot runtime manifest differs from captured identity",
        )


def _dependency_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, str] = {}
    for distribution in (
        "numpy",
        "scipy",
        "pydantic",
        "pyproj",
        "PyYAML",
        "shapely",
        "networkx",
    ):
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            versions[distribution] = "unavailable"
    return versions


def _nonempty_environment_text(*candidates: str | None) -> str:
    """Apply the artifact's explicit missing-text policy."""
    for candidate in candidates:
        if candidate is not None and candidate.strip():
            return candidate.strip()
    return "unavailable"


def _cpu_model() -> str:
    """Return a stable non-empty CPU description on local and CI hosts."""
    processor = platform.processor()
    if processor.strip():
        return processor.strip()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() in {"model name", "Hardware"}:
                if value.strip():
                    return value.strip()
    return _nonempty_environment_text(
        platform.uname().processor,
        platform.machine(),
    )


def _logical_core_count(affinity: list[int]) -> int:
    """Return a positive logical-core count on supported and minimal hosts."""
    count = os.cpu_count()
    if isinstance(count, int) and count > 0:
        return count
    if affinity:
        return len(affinity)
    raise RuntimeError("benchmark environment cannot determine logical CPU count")


def _linux_physical_core_count() -> int | None:
    """Read Linux CPU topology without requiring an optional dependency."""
    topology_root = Path("/sys/devices/system/cpu")
    pairs: set[tuple[str, str]] = set()
    for cpu_path in sorted(topology_root.glob("cpu[0-9]*")):
        package_path = cpu_path / "topology" / "physical_package_id"
        core_path = cpu_path / "topology" / "core_id"
        try:
            package_id = package_path.read_text(encoding="utf-8").strip()
            core_id = core_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if package_id and core_id:
            pairs.add((package_id, core_id))
    if pairs:
        return len(pairs)

    cpuinfo = Path("/proc/cpuinfo")
    try:
        records = cpuinfo.read_text(
            encoding="utf-8",
            errors="replace",
        ).split("\n\n")
    except OSError:
        return None
    for record in records:
        fields_by_name: dict[str, str] = {}
        for line in record.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields_by_name[key.strip()] = value.strip()
        package_id = fields_by_name.get("physical id")
        core_id = fields_by_name.get("core id")
        if package_id is not None and core_id is not None:
            pairs.add((package_id, core_id))
    return len(pairs) if pairs else None


def _physical_core_count() -> tuple[int, str]:
    """Return physical cores and the evidence source used to resolve them."""
    try:
        import psutil

        count = psutil.cpu_count(logical=False)
    except ImportError:
        count = None
    if isinstance(count, int) and count > 0:
        return count, "psutil"
    if platform.system() == "Linux":
        count = _linux_physical_core_count()
        if isinstance(count, int) and count > 0:
            return count, "linux_topology"
    raise RuntimeError(
        "benchmark environment cannot determine physical CPU topology",
    )


def _total_ram_bytes() -> tuple[int, str]:
    """Return installed RAM and the evidence source used to resolve it."""
    try:
        import psutil

        total = psutil.virtual_memory().total
    except ImportError:
        total = None
    if isinstance(total, int) and total > 0:
        return total, "psutil"

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        page_size = 0
        page_count = 0
    if isinstance(page_size, int) and isinstance(page_count, int) and page_size > 0 and page_count > 0:
        return page_size * page_count, "sysconf"
    raise RuntimeError("benchmark environment cannot determine total RAM")


def _runner_identity() -> BenchmarkRunnerIdentity:
    provider: Literal["local", "github-actions"] = (
        "github-actions" if os.environ.get("GITHUB_ACTIONS", "").lower() == "true" else "local"
    )
    labels = {
        "image_os": _nonempty_environment_text(
            os.environ.get("ImageOS"),
        ),
        "image_version": _nonempty_environment_text(
            os.environ.get("ImageVersion"),
        ),
        "runner_arch": _nonempty_environment_text(
            os.environ.get("RUNNER_ARCH"),
            platform.machine(),
        ),
        "runner_environment": _nonempty_environment_text(
            os.environ.get("RUNNER_ENVIRONMENT"),
            provider,
        ),
        "runner_group": _nonempty_environment_text(
            os.environ.get("RUNNER_GROUP"),
            provider,
        ),
        "runner_name": _nonempty_environment_text(
            os.environ.get("RUNNER_NAME"),
            platform.node(),
        ),
        "runner_os": _nonempty_environment_text(
            os.environ.get("RUNNER_OS"),
            platform.system(),
        ),
    }
    image = _nonempty_environment_text(
        " ".join(
            value
            for value in (
                os.environ.get("ImageOS", "").strip(),
                os.environ.get("ImageVersion", "").strip(),
            )
            if value
        ),
        f"{platform.system()} {platform.release()}",
    )
    return BenchmarkRunnerIdentity(
        provider=provider,
        image=image,
        labels=labels,
    )


def _environment_metadata(
    repo_root: Path = ROOT,
) -> BenchmarkEnvironment:
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except AttributeError:
        affinity = []
    logical_cores = _logical_core_count(affinity)
    physical_cores, physical_core_source = _physical_core_count()
    total_ram, total_ram_source = _total_ram_bytes()
    thread_variables = {
        key: _nonempty_environment_text(os.environ.get(key))
        for key in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        )
    }
    runner_identity = _runner_identity()
    return BenchmarkEnvironment.model_validate(
        {
            "missing_text_policy": "unavailable",
            "os": _nonempty_environment_text(platform.system()),
            "kernel": _nonempty_environment_text(platform.release()),
            "architecture": _nonempty_environment_text(platform.machine()),
            "cpu_model": _cpu_model(),
            "logical_core_count": logical_cores,
            "physical_core_count": physical_cores,
            "physical_core_count_source": physical_core_source,
            "cpu_affinity": affinity,
            "total_ram_bytes": total_ram,
            "total_ram_source": total_ram_source,
            "python_implementation": _nonempty_environment_text(
                platform.python_implementation(),
            ),
            "python_version": _nonempty_environment_text(
                platform.python_version(),
            ),
            "dependencies": _dependency_versions(),
            "dependency_lock_sha256": _file_sha256(repo_root / "uv.lock"),
            "runner_identity": runner_identity,
            "runner_image": runner_identity.image,
            "runner_labels": runner_identity.labels,
            "threading_environment": thread_variables,
            "unprofiled_peak_memory_mb": None,
        }
    )


def _run_worker_subprocess(
    *,
    worker_path: Path,
    repo_root: Path,
    scenario_relative: str,
    revision: Literal["reference", "candidate"],
    workload: BenchmarkWorkload,
    timeout_s: float,
) -> WorkerRun:
    with tempfile.NamedTemporaryFile(
        prefix=f"sw-{revision}-benchmark-",
        suffix=".json",
        delete=False,
    ) as output_file:
        output_path = Path(output_file.name)
    try:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repo_root)
        completed = subprocess.run(
            [
                sys.executable,
                str(worker_path),
                "worker",
                "--repo-root",
                str(repo_root),
                "--scenario-relative",
                scenario_relative,
                "--revision",
                revision,
                "--workload-json",
                workload.model_dump_json(exclude_none=True),
                "--output",
                str(output_path),
            ],
            cwd=repo_root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{revision} worker failed with exit {completed.returncode}: "
                f"stdout={completed.stdout[-2000:]!r}, "
                f"stderr={completed.stderr[-4000:]!r}",
            )
        if not output_path.is_file():
            raise RuntimeError(f"{revision} worker did not write its result")
        return WorkerRun.model_validate_json(
            output_path.read_text(encoding="utf-8"),
        )
    finally:
        output_path.unlink(missing_ok=True)


def _run_closure_subprocess(
    *,
    worker_path: Path,
    repo_root: Path,
    scenario_relative: str,
    revision: Literal["reference", "candidate"],
    workload: BenchmarkWorkload,
    timeout_s: float,
) -> ProductionClosureRun:
    """Run one worker without sampling or exposing harness timing."""
    with tempfile.NamedTemporaryFile(
        prefix=f"sw-{revision}-closure-",
        suffix=".json",
        delete=False,
    ) as output_file:
        output_path = Path(output_file.name)
    try:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repo_root)
        completed = subprocess.run(
            [
                sys.executable,
                str(worker_path),
                "closure-worker",
                "--repo-root",
                str(repo_root),
                "--scenario-relative",
                scenario_relative,
                "--revision",
                revision,
                "--workload-json",
                workload.model_dump_json(exclude_none=True),
                "--output",
                str(output_path),
            ],
            cwd=repo_root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"{revision} closure worker failed with exit "
                f"{completed.returncode}: stdout={completed.stdout[-2000:]!r}, "
                f"stderr={completed.stderr[-4000:]!r}",
            )
        if not output_path.is_file():
            raise RuntimeError(
                f"{revision} closure worker did not write its result",
            )
        return ProductionClosureRun.model_validate_json(
            output_path.read_text(encoding="utf-8"),
        )
    finally:
        output_path.unlink(missing_ok=True)


def _validate_worker_identity(
    run: WorkerRun,
    *,
    entry: BaselineEntry,
    expected_commit: str,
) -> None:
    if run.commit != expected_commit:
        raise ValueError(
            f"{run.revision} worker commit disagrees with selected tree",
        )
    if entry.reference_input is None or entry.semantic_envelope is None:
        raise ValueError("gating baseline is missing required evidence")
    if run.runtime_input.fingerprint != entry.reference_input.fingerprint:
        raise ValueError(
            f"{run.revision} effective runtime input differs from the authoritative baseline",
        )
    if (
        run.runtime_input.scenario_path != entry.reference_input.scenario_path
        or run.runtime_input.scenario_sha256 != entry.reference_input.scenario_sha256
        or run.runtime_input.dependency_lock_sha256 != entry.reference_input.dependency_lock_sha256
    ):
        raise ValueError(
            f"{run.revision} scenario or dependency-lock identity differs from the authoritative baseline",
        )
    if run.semantic_envelope != entry.semantic_envelope:
        raise ValueError(
            f"{run.revision} semantic outcome differs from the authoritative baseline",
        )


def _write_artifact(path: Path, artifact: ComparisonArtifact) -> str:
    """Atomically persist one independently valid artifact checkpoint."""
    payload = artifact.model_dump(mode="json")
    digest = canonical_sha256(payload)
    document = {
        **payload,
        "artifact_sha256": digest,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return digest


def validate_artifact(
    path: Path,
    *,
    authoritative_baseline_path: Path = BASELINES_PATH,
    require_authoritative: bool = False,
) -> tuple[ComparisonArtifact, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != set(ComparisonArtifact.model_fields) | {"artifact_sha256"}:
        raise ValueError("comparison artifact keys are not exact")
    digest = raw.pop("artifact_sha256")
    _validate_sha256(digest, "artifact digest")
    if digest != canonical_sha256(raw):
        raise ValueError("comparison artifact digest does not match its payload")
    artifact = ComparisonArtifact.model_validate(raw)
    baseline_identity = artifact.baseline_identity
    if require_authoritative and (baseline_identity is None or not baseline_identity.authoritative):
        raise ValueError(
            "closure proof requires the checked-in authoritative baseline",
        )
    if baseline_identity is not None and baseline_identity.authoritative:
        baseline_path = authoritative_baseline_path.resolve()
        if not baseline_path.is_file():
            raise ValueError(
                "authoritative checked-in baseline is unavailable",
            )
        if _file_sha256(baseline_path) != baseline_identity.document_sha256:
            raise ValueError(
                "artifact authoritative baseline digest differs from the checked-in document",
            )
        baseline = BenchmarkBaseline(baseline_path).load_file()
        entry = baseline.entries.get(artifact.scenario_name)
        if entry is None:
            raise ValueError(
                "artifact scenario is absent from authoritative baseline",
            )
        if canonical_sha256(entry.model_dump(mode="json")) != baseline_identity.entry_sha256:
            raise ValueError(
                "artifact baseline entry digest differs from checked-in entry",
            )
        if artifact.policy != entry.policy:
            raise ValueError(
                "artifact policy differs from authoritative baseline",
            )
        if artifact.status != "error":
            if (
                not isinstance(entry.policy, BenchmarkPolicy)
                or entry.policy.mode != "gate"
                or entry.reference_input is None
                or entry.semantic_envelope is None
            ):
                raise ValueError(
                    "authoritative gating entry lacks runtime evidence",
                )
            run = artifact.warmups["candidate"]
            if (
                run.runtime_input.fingerprint != entry.reference_input.fingerprint
                or run.runtime_input.scenario_path != entry.reference_input.scenario_path
                or run.runtime_input.scenario_sha256 != entry.reference_input.scenario_sha256
                or run.runtime_input.dependency_lock_sha256 != entry.reference_input.dependency_lock_sha256
                or run.semantic_envelope != entry.semantic_envelope
            ):
                raise ValueError(
                    "artifact workload differs from authoritative baseline",
                )
    return artifact, digest


def _write_transition_artifact(
    path: Path,
    artifact: TransitionArtifact,
) -> str:
    """Atomically persist one independently valid transition checkpoint."""
    payload = artifact.model_dump(mode="json")
    digest = canonical_sha256(payload)
    document = {**payload, "artifact_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return digest


def validate_transition_artifact(
    path: Path,
    *,
    authoritative_baseline_path: Path = BASELINES_PATH,
    require_authoritative: bool = False,
) -> tuple[TransitionArtifact, str]:
    """Validate a duration-free transition artifact and baseline binding."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = set(TransitionArtifact.model_fields) | {"artifact_sha256"}
    if set(raw) != expected_keys:
        raise ValueError("transition artifact keys are not exact")
    digest = raw.pop("artifact_sha256")
    _validate_sha256(digest, "transition artifact digest")
    if digest != canonical_sha256(raw):
        raise ValueError(
            "transition artifact digest does not match its payload",
        )
    artifact = TransitionArtifact.model_validate(raw)
    baseline_identity = artifact.baseline_identity
    if require_authoritative and (baseline_identity is None or not baseline_identity.authoritative):
        raise ValueError(
            "transition closure requires the checked-in authoritative baseline",
        )
    if baseline_identity is not None and baseline_identity.authoritative:
        baseline_path = authoritative_baseline_path.resolve()
        if not baseline_path.is_file():
            raise ValueError(
                "authoritative transition baseline is unavailable",
            )
        if _file_sha256(baseline_path) != baseline_identity.document_sha256:
            raise ValueError(
                "transition artifact baseline digest differs from checked-in document",
            )
        baseline = BenchmarkBaseline(baseline_path).load_file()
        entry = baseline.entries.get(artifact.scenario_name)
        if entry is None:
            raise ValueError(
                "transition scenario is absent from authoritative baseline",
            )
        if canonical_sha256(entry.model_dump(mode="json")) != baseline_identity.entry_sha256:
            raise ValueError(
                "transition baseline entry digest differs from checked-in entry",
            )
        if (
            not isinstance(entry.policy, TransitionPolicy)
            or artifact.policy != entry.policy
            or artifact.contract != entry.transition_contract
        ):
            raise ValueError(
                "transition policy or contract differs from authoritative baseline",
            )
        if entry.transition_contract is None:
            raise ValueError(
                "authoritative transition lacks its exact contract",
            )
        _verify_transition_predecessor(
            baseline_path.parents[2],
            scenario_name=artifact.scenario_name,
            policy=entry.policy,
            contract=entry.transition_contract,
        )
        if artifact.status == "transition_qualified":
            verified = validate_workload_transition(
                artifact.closures["reference"],
                artifact.closures["candidate"],
                entry.transition_contract,
            )
            if artifact.verified_approvals != verified:
                raise ValueError(
                    "transition artifact approvals differ from authoritative contract",
                )
    return artifact, digest


def _write_final_tree_verification(
    path: Path,
    verification: FinalTreeVerification,
) -> str:
    """Atomically persist one independently digestible final-tree proof."""
    payload = verification.model_dump(mode="json")
    digest = canonical_sha256(payload)
    document = {
        **payload,
        "verification_sha256": digest,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return digest


def validate_final_tree_verification(
    path: Path,
    *,
    comparison_artifact_path: Path,
    authoritative_baseline_path: Path = BASELINES_PATH,
) -> tuple[FinalTreeVerification, str]:
    """Validate a final-tree proof and its exact source comparison artifact."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = set(FinalTreeVerification.model_fields) | {
        "verification_sha256",
    }
    if set(raw) != expected_keys:
        raise ValueError("final-tree verification keys are not exact")
    digest = raw.pop("verification_sha256")
    _validate_sha256(digest, "final-tree verification digest")
    if digest != canonical_sha256(raw):
        raise ValueError(
            "final-tree verification digest does not match its payload",
        )
    verification = FinalTreeVerification.model_validate(raw)
    artifact, artifact_digest = validate_artifact(
        comparison_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
        require_authoritative=True,
    )
    if artifact.status != "pass":
        raise ValueError(
            "final-tree verification requires a passing comparison artifact",
        )
    if artifact.candidate_identity is None:
        raise ValueError(
            "passing comparison artifact has no candidate identity",
        )
    if artifact.policy is None:
        raise ValueError(
            "passing comparison artifact has no benchmark policy",
        )
    comparison_run = artifact.warmups["candidate"]
    if verification.comparison_artifact_sha256 != artifact_digest:
        raise ValueError(
            "final-tree proof references a different comparison artifact",
        )
    if verification.scenario_name != artifact.scenario_name:
        raise ValueError(
            "final-tree proof scenario differs from comparison artifact",
        )
    if verification.comparison_candidate_identity != artifact.candidate_identity:
        raise ValueError(
            "final-tree proof candidate identity differs from comparison artifact",
        )
    if (
        verification.comparison_runtime_input != comparison_run.runtime_input
        or verification.comparison_semantic_envelope != comparison_run.semantic_envelope
    ):
        raise ValueError(
            "final-tree proof workload differs from comparison artifact",
        )
    return verification, digest


def verify_final_tree(
    *,
    comparison_artifact_path: Path,
    verification_path: Path,
    final_root: Path = ROOT,
    worker_timeout_s: float = 900.0,
) -> FinalTreeVerification:
    """Bind a passing paired comparison to one clean final commit."""
    final_root = final_root.resolve()
    comparison_artifact_path = comparison_artifact_path.resolve()
    verification_path = verification_path.resolve()
    for label, evidence_path in (
        ("comparison artifact", comparison_artifact_path),
        ("final-tree verification", verification_path),
    ):
        if evidence_path.is_relative_to(final_root):
            raise ValueError(
                f"{label} must be outside the final worktree so evidence does not dirty the tree being verified",
            )

    authoritative_baseline_path = final_root / "tests" / "benchmarks" / "baselines.json"
    artifact, artifact_digest = validate_artifact(
        comparison_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
        require_authoritative=True,
    )
    if artifact.status != "pass":
        raise ValueError(
            "final-tree verification requires a passing comparison artifact",
        )
    if artifact.candidate_identity is None:
        raise ValueError(
            "passing comparison artifact has no candidate identity",
        )
    comparison_run = artifact.warmups["candidate"]
    external_runtime_paths = _scenario_external_runtime_paths(
        final_root,
        comparison_run.runtime_input.scenario_path,
    )
    final_identity = _git_identity(
        final_root,
        require_clean=True,
        external_runtime_paths=external_runtime_paths,
    )
    if final_identity.runtime_manifest != artifact.candidate_identity.runtime_manifest:
        raise ValueError(
            "final runtime manifest differs from comparison candidate",
        )

    reproduction_run = _run_worker_subprocess(
        worker_path=(final_root / "tests" / "benchmarks" / "benchmark_suite.py"),
        repo_root=final_root,
        scenario_relative=comparison_run.runtime_input.scenario_path,
        revision="candidate",
        workload=artifact.policy.workload,
        timeout_s=worker_timeout_s,
    )
    verification = FinalTreeVerification(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        comparison_artifact_sha256=artifact_digest,
        scenario_name=artifact.scenario_name,
        comparison_candidate_identity=artifact.candidate_identity,
        final_identity=final_identity,
        comparison_runtime_input=comparison_run.runtime_input,
        comparison_semantic_envelope=comparison_run.semantic_envelope,
        reproduction_run=reproduction_run,
    )
    _write_final_tree_verification(verification_path, verification)
    validate_final_tree_verification(
        verification_path,
        comparison_artifact_path=comparison_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
    )
    return verification


def _write_transition_final_tree_verification(
    path: Path,
    verification: TransitionFinalTreeVerification,
) -> str:
    payload = verification.model_dump(mode="json")
    digest = canonical_sha256(payload)
    document = {**payload, "verification_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return digest


def validate_transition_final_tree_verification(
    path: Path,
    *,
    transition_artifact_path: Path,
    authoritative_baseline_path: Path = BASELINES_PATH,
) -> tuple[TransitionFinalTreeVerification, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = set(TransitionFinalTreeVerification.model_fields) | {
        "verification_sha256",
    }
    if set(raw) != expected_keys:
        raise ValueError(
            "transition final-tree verification keys are not exact",
        )
    digest = raw.pop("verification_sha256")
    _validate_sha256(digest, "transition final-tree verification digest")
    if digest != canonical_sha256(raw):
        raise ValueError(
            "transition final-tree digest does not match its payload",
        )
    verification = TransitionFinalTreeVerification.model_validate(raw)
    artifact, artifact_digest = validate_transition_artifact(
        transition_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
        require_authoritative=True,
    )
    if artifact.status != "transition_qualified":
        raise ValueError(
            "transition final-tree proof requires qualified source evidence",
        )
    if artifact.candidate_identity is None:
        raise ValueError(
            "qualified transition has no candidate identity",
        )
    transition_endpoint = artifact.closures["candidate"]
    if verification.transition_artifact_sha256 != artifact_digest:
        raise ValueError(
            "transition final-tree proof references a different artifact",
        )
    if verification.scenario_name != artifact.scenario_name:
        raise ValueError(
            "transition final-tree scenario differs from source artifact",
        )
    if verification.transition_candidate_identity != artifact.candidate_identity:
        raise ValueError(
            "transition final-tree candidate identity differs from artifact",
        )
    if (
        verification.transition_runtime_input != transition_endpoint.runtime_input
        or verification.transition_semantic_envelope != transition_endpoint.semantic_envelope
    ):
        raise ValueError(
            "transition final-tree endpoint differs from source artifact",
        )
    return verification, digest


def verify_transition_final_tree(
    *,
    transition_artifact_path: Path,
    verification_path: Path,
    final_root: Path = ROOT,
    worker_timeout_s: float = 900.0,
) -> TransitionFinalTreeVerification:
    """Bind a qualified transition endpoint to one clean final commit."""
    final_root = final_root.resolve()
    transition_artifact_path = transition_artifact_path.resolve()
    verification_path = verification_path.resolve()
    for label, evidence_path in (
        ("transition artifact", transition_artifact_path),
        ("transition final-tree verification", verification_path),
    ):
        if evidence_path.is_relative_to(final_root):
            raise ValueError(
                f"{label} must be outside the final worktree",
            )
    authoritative_baseline_path = final_root / "tests" / "benchmarks" / "baselines.json"
    artifact, artifact_digest = validate_transition_artifact(
        transition_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
        require_authoritative=True,
    )
    if artifact.status != "transition_qualified":
        raise ValueError(
            "transition final-tree verification requires qualification",
        )
    if artifact.candidate_identity is None or artifact.policy is None:
        raise ValueError(
            "qualified transition lacks candidate identity or policy",
        )
    transition_endpoint = artifact.closures["candidate"]
    external_runtime_paths = _scenario_external_runtime_paths(
        final_root,
        transition_endpoint.runtime_input.scenario_path,
    )
    final_identity = _git_identity(
        final_root,
        require_clean=True,
        external_runtime_paths=external_runtime_paths,
    )
    if final_identity.runtime_manifest != artifact.candidate_identity.runtime_manifest:
        raise ValueError(
            "final runtime manifest differs from transition candidate",
        )
    reproduction = _run_closure_subprocess(
        worker_path=(final_root / "tests" / "benchmarks" / "benchmark_suite.py"),
        repo_root=final_root,
        scenario_relative=transition_endpoint.runtime_input.scenario_path,
        revision="candidate",
        workload=artifact.policy.workload,
        timeout_s=worker_timeout_s,
    )
    verification = TransitionFinalTreeVerification(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        transition_artifact_sha256=artifact_digest,
        scenario_name=artifact.scenario_name,
        transition_candidate_identity=artifact.candidate_identity,
        final_identity=final_identity,
        transition_runtime_input=transition_endpoint.runtime_input,
        transition_semantic_envelope=transition_endpoint.semantic_envelope,
        reproduction_closure=reproduction,
        timing_assessment=TransitionTimingAssessment(),
    )
    _write_transition_final_tree_verification(verification_path, verification)
    validate_transition_final_tree_verification(
        verification_path,
        transition_artifact_path=transition_artifact_path,
        authoritative_baseline_path=authoritative_baseline_path,
    )
    return verification


def run_paired_comparison(
    *,
    scenario_name: str,
    candidate_root: Path = ROOT,
    baseline_path: Path = BASELINES_PATH,
    artifact_path: Path,
    allow_dirty_candidate: bool = False,
    worker_timeout_s: float = 900.0,
) -> ComparisonArtifact:
    """Run an ordinary three-pair gate; transition entries reject explicitly."""
    candidate_root = candidate_root.resolve()
    artifact_path = artifact_path.resolve()
    if artifact_path.is_relative_to(candidate_root):
        raise ValueError(
            "paired benchmark artifacts must be outside the candidate "
            "worktree so evidence checkpoints cannot dirty the measured tree",
        )
    created_at = datetime.now(timezone.utc).isoformat()
    environment: BenchmarkEnvironment | None = None
    entry: BaselineEntry | None = None
    policy: BenchmarkPolicy | None = None
    baseline_identity: BenchmarkBaselineIdentity | None = None
    reference_identity: GitIdentity | None = None
    candidate_identity: GitIdentity | None = None
    warmups: dict[str, WorkerRun] = {}
    pairs: list[PairSample] = []
    errors: list[str] = []
    decision: PerformanceDecision | None = None
    artifact_status: Literal["pass", "fail", "inconclusive", "error"] = "error"

    def checkpoint(stage: str) -> None:
        """Persist valid partial evidence before the next interruptible step."""
        _write_artifact(
            artifact_path,
            ComparisonArtifact(
                created_at_utc=created_at,
                scenario_name=scenario_name,
                status="error",
                errors=[f"comparison in progress: {stage}"],
                policy=policy,
                baseline_identity=baseline_identity,
                environment=environment,
                reference_identity=reference_identity,
                candidate_identity=candidate_identity,
                warmups=warmups,
                pairs=pairs,
                decision=None,
            ),
        )

    checkpoint("initialized")
    try:
        environment = _environment_metadata(candidate_root)
        checkpoint("environment captured")
        baseline = BenchmarkBaseline(baseline_path).load_file()
        if scenario_name not in baseline.entries:
            raise ValueError(f"unknown benchmark scenario {scenario_name!r}")
        entry = baseline.entries[scenario_name]
        if not isinstance(entry.policy, BenchmarkPolicy):
            raise ValueError(
                f"{scenario_name!r} is transition_qualified and cannot run as an ordinary gate",
            )
        policy = entry.policy
        canonical_baseline_path = (candidate_root / "tests" / "benchmarks" / "baselines.json").resolve()
        authoritative = baseline_path.resolve() == canonical_baseline_path
        baseline_identity = BenchmarkBaselineIdentity(
            authoritative=authoritative,
            source="checked_in" if authoritative else "custom",
            document_sha256=_file_sha256(baseline_path),
            entry_sha256=canonical_sha256(
                entry.model_dump(mode="json"),
            ),
        )
        if policy.mode != "gate":
            raise ValueError(
                f"{scenario_name!r} is measurement_only and cannot be gated",
            )
        if policy.reference_commit is None:
            raise ValueError("gating policy has no reference commit")
        checkpoint("policy loaded")

        candidate_external_paths = _scenario_external_runtime_paths(
            candidate_root,
            entry.scenario_path,
        )
        candidate_identity = _git_identity(
            candidate_root,
            require_clean=not allow_dirty_candidate,
            external_runtime_paths=candidate_external_paths,
        )
        checkpoint("candidate identity captured")
        _git(
            candidate_root,
            "cat-file",
            "-e",
            f"{policy.reference_commit}^{{commit}}",
        )
        with tempfile.TemporaryDirectory(
            prefix="sw-paired-benchmark-",
        ) as temporary:
            candidate_snapshot_root = Path(temporary) / "candidate-snapshot"
            _materialize_candidate_snapshot(
                candidate_root=candidate_root,
                snapshot_root=candidate_snapshot_root,
                identity=candidate_identity,
                scenario_relative=entry.scenario_path,
                external_runtime_paths=candidate_external_paths,
            )
            worker_path = candidate_snapshot_root / "tests" / "benchmarks" / "benchmark_suite.py"
            reference_root = Path(temporary) / "reference"
            _git(
                candidate_root,
                "clone",
                "--shared",
                "--no-checkout",
                str(candidate_root),
                str(reference_root),
            )
            _git(
                reference_root,
                "checkout",
                "--detach",
                policy.reference_commit,
            )
            reference_identity = _git_identity(
                reference_root,
                require_clean=True,
                external_runtime_paths=(
                    reference_external_paths := _scenario_external_runtime_paths(
                        reference_root,
                        entry.scenario_path,
                    )
                ),
            )
            if reference_identity.commit != policy.reference_commit:
                raise ValueError("reference checkout resolved the wrong commit")
            checkpoint("reference identity captured")
            if _file_sha256(reference_root / "uv.lock") != _file_sha256(candidate_snapshot_root / "uv.lock"):
                raise ValueError(
                    "reference and candidate dependency locks differ",
                )

            warmups["reference"] = _run_worker_subprocess(
                worker_path=worker_path,
                repo_root=reference_root,
                scenario_relative=entry.scenario_path,
                revision="reference",
                workload=policy.workload,
                timeout_s=worker_timeout_s,
            )
            checkpoint("reference warm-up completed")
            warmups["candidate"] = _run_worker_subprocess(
                worker_path=worker_path,
                repo_root=candidate_snapshot_root,
                scenario_relative=entry.scenario_path,
                revision="candidate",
                workload=policy.workload,
                timeout_s=worker_timeout_s,
            )
            checkpoint("candidate warm-up completed")
            _validate_worker_identity(
                warmups["reference"],
                entry=entry,
                expected_commit=reference_identity.commit,
            )
            _validate_worker_identity(
                warmups["candidate"],
                entry=entry,
                expected_commit=candidate_identity.commit,
            )

            for pair_index, order in enumerate(policy.pair_orders):
                pair_runs: dict[str, WorkerRun] = {}
                for revision in order:
                    root = reference_root if revision == "reference" else candidate_snapshot_root
                    expected_commit = (
                        reference_identity.commit if revision == "reference" else candidate_identity.commit
                    )
                    run = _run_worker_subprocess(
                        worker_path=worker_path,
                        repo_root=root,
                        scenario_relative=entry.scenario_path,
                        revision=revision,
                        workload=policy.workload,
                        timeout_s=worker_timeout_s,
                    )
                    _validate_worker_identity(
                        run,
                        entry=entry,
                        expected_commit=expected_commit,
                    )
                    pair_runs[revision] = run
                reference_run = pair_runs["reference"]
                candidate_run = pair_runs["candidate"]
                pairs.append(
                    PairSample(
                        pair_index=pair_index,
                        order=order,
                        reference=reference_run,
                        candidate=candidate_run,
                        candidate_over_reference=(candidate_run.duration_s / reference_run.duration_s),
                    )
                )
                checkpoint(f"timed pair {pair_index} completed")

            final_reference_identity = _git_identity(
                reference_root,
                require_clean=True,
                external_runtime_paths=reference_external_paths,
            )
            final_snapshot_manifest = _runtime_tree_manifest(
                candidate_snapshot_root,
                external_runtime_paths=candidate_external_paths,
            )
            if final_snapshot_manifest != candidate_identity.runtime_manifest:
                raise ValueError(
                    "candidate snapshot runtime manifest changed during comparison",
                )
            final_candidate_identity = _git_identity(
                candidate_root,
                require_clean=not allow_dirty_candidate,
                external_runtime_paths=candidate_external_paths,
            )
            if final_reference_identity != reference_identity:
                raise ValueError(
                    "reference tree identity changed during comparison",
                )
            if final_candidate_identity != candidate_identity:
                raise ValueError(
                    "candidate tree identity changed during comparison",
                )

        decision = evaluate_paired_samples(
            policy,
            reference_seconds=[pair.reference.duration_s for pair in pairs],
            candidate_seconds=[pair.candidate.duration_s for pair in pairs],
        )
        artifact_status = decision.status
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        artifact_status = "error"

    artifact = ComparisonArtifact(
        created_at_utc=created_at,
        scenario_name=scenario_name,
        status=artifact_status,
        errors=errors,
        policy=policy,
        baseline_identity=baseline_identity,
        environment=environment,
        reference_identity=reference_identity,
        candidate_identity=candidate_identity,
        warmups=warmups,
        pairs=pairs,
        decision=decision,
    )
    _write_artifact(artifact_path, artifact)
    if artifact.status != "pass":
        raise BenchmarkComparisonError(
            f"paired benchmark {scenario_name!r} ended {artifact.status}: "
            f"{errors or ([decision.reason] if decision else [])}",
        )
    return artifact


def run_workload_transition(
    *,
    scenario_name: str,
    candidate_root: Path = ROOT,
    baseline_path: Path = BASELINES_PATH,
    artifact_path: Path,
    allow_dirty_candidate: bool = False,
    worker_timeout_s: float = 900.0,
) -> TransitionArtifact:
    """Run exactly one duration-free production closure at each endpoint."""
    candidate_root = candidate_root.resolve()
    artifact_path = artifact_path.resolve()
    if artifact_path.is_relative_to(candidate_root):
        raise ValueError(
            "transition artifacts must be outside the candidate worktree",
        )
    created_at = datetime.now(timezone.utc).isoformat()
    environment: BenchmarkEnvironment | None = None
    entry: BaselineEntry | None = None
    policy: TransitionPolicy | None = None
    contract: WorkloadTransitionContract | None = None
    baseline_identity: BenchmarkBaselineIdentity | None = None
    reference_identity: GitIdentity | None = None
    candidate_identity: GitIdentity | None = None
    closures: dict[str, ProductionClosureRun] = {}
    verified_approvals: list[TransitionApproval] = []
    errors: list[str] = []
    artifact_status: Literal[
        "transition_qualified",
        "transition_rejected",
        "error",
    ] = "error"

    def checkpoint(stage: str) -> None:
        _write_transition_artifact(
            artifact_path,
            TransitionArtifact(
                created_at_utc=created_at,
                scenario_name=scenario_name,
                status="error",
                errors=[f"transition in progress: {stage}"],
                policy=policy,
                baseline_identity=baseline_identity,
                environment=environment,
                reference_identity=reference_identity,
                candidate_identity=candidate_identity,
                closures=closures,
                contract=contract,
                verified_approvals=[],
                timing_assessment=TransitionTimingAssessment(),
            ),
        )

    checkpoint("initialized")
    try:
        environment = _environment_metadata(candidate_root)
        checkpoint("environment captured")
        baseline = BenchmarkBaseline(baseline_path).load_file()
        if scenario_name not in baseline.entries:
            raise ValueError(f"unknown benchmark scenario {scenario_name!r}")
        entry = baseline.entries[scenario_name]
        if not isinstance(entry.policy, TransitionPolicy):
            raise ValueError(
                f"{scenario_name!r} is {entry.policy.mode} and cannot run as a workload transition",
            )
        if entry.transition_contract is None:
            raise ValueError("transition entry has no exact contract")
        policy = entry.policy
        contract = entry.transition_contract
        canonical_baseline_path = (candidate_root / "tests" / "benchmarks" / "baselines.json").resolve()
        authoritative = baseline_path.resolve() == canonical_baseline_path
        baseline_identity = BenchmarkBaselineIdentity(
            authoritative=authoritative,
            source="checked_in" if authoritative else "custom",
            document_sha256=_file_sha256(baseline_path),
            entry_sha256=canonical_sha256(entry.model_dump(mode="json")),
        )
        _verify_transition_predecessor(
            candidate_root,
            scenario_name=scenario_name,
            policy=policy,
            contract=contract,
        )
        checkpoint("policy loaded")

        candidate_external_paths = _scenario_external_runtime_paths(
            candidate_root,
            entry.scenario_path,
        )
        candidate_identity = _git_identity(
            candidate_root,
            require_clean=not allow_dirty_candidate,
            external_runtime_paths=candidate_external_paths,
        )
        checkpoint("candidate identity captured")
        _git(
            candidate_root,
            "cat-file",
            "-e",
            f"{policy.reference_commit}^{{commit}}",
        )
        with tempfile.TemporaryDirectory(
            prefix="sw-transition-benchmark-",
        ) as temporary:
            candidate_snapshot_root = Path(temporary) / "candidate-snapshot"
            _materialize_candidate_snapshot(
                candidate_root=candidate_root,
                snapshot_root=candidate_snapshot_root,
                identity=candidate_identity,
                scenario_relative=entry.scenario_path,
                external_runtime_paths=candidate_external_paths,
            )
            worker_path = candidate_snapshot_root / "tests" / "benchmarks" / "benchmark_suite.py"
            reference_root = Path(temporary) / "reference"
            _git(
                candidate_root,
                "clone",
                "--shared",
                "--no-checkout",
                str(candidate_root),
                str(reference_root),
            )
            _git(
                reference_root,
                "checkout",
                "--detach",
                policy.reference_commit,
            )
            reference_external_paths = _scenario_external_runtime_paths(
                reference_root,
                entry.scenario_path,
            )
            reference_identity = _git_identity(
                reference_root,
                require_clean=True,
                external_runtime_paths=reference_external_paths,
            )
            if reference_identity.commit != policy.reference_commit:
                raise ValueError("reference checkout resolved the wrong commit")
            checkpoint("reference identity captured")
            if _file_sha256(reference_root / "uv.lock") != _file_sha256(candidate_snapshot_root / "uv.lock"):
                raise _WorkloadTransitionRejected(
                    "reference and candidate dependency locks differ",
                )

            closures["reference"] = _run_closure_subprocess(
                worker_path=worker_path,
                repo_root=reference_root,
                scenario_relative=entry.scenario_path,
                revision="reference",
                workload=policy.workload,
                timeout_s=worker_timeout_s,
            )
            checkpoint("reference closure completed")
            closures["candidate"] = _run_closure_subprocess(
                worker_path=worker_path,
                repo_root=candidate_snapshot_root,
                scenario_relative=entry.scenario_path,
                revision="candidate",
                workload=policy.workload,
                timeout_s=worker_timeout_s,
            )
            checkpoint("candidate closure completed")
            if closures["reference"].commit != reference_identity.commit:
                raise ValueError(
                    "reference closure commit disagrees with selected tree",
                )
            if closures["candidate"].commit != candidate_identity.commit:
                raise ValueError(
                    "candidate closure commit disagrees with selected tree",
                )
            try:
                provisional_approvals = validate_workload_transition(
                    closures["reference"],
                    closures["candidate"],
                    contract,
                )
            except ValueError as exc:
                raise _WorkloadTransitionRejected(str(exc)) from exc

            final_reference_identity = _git_identity(
                reference_root,
                require_clean=True,
                external_runtime_paths=reference_external_paths,
            )
            final_snapshot_manifest = _runtime_tree_manifest(
                candidate_snapshot_root,
                external_runtime_paths=candidate_external_paths,
            )
            if final_snapshot_manifest != candidate_identity.runtime_manifest:
                raise ValueError(
                    "candidate snapshot runtime manifest changed during transition",
                )
            final_candidate_identity = _git_identity(
                candidate_root,
                require_clean=not allow_dirty_candidate,
                external_runtime_paths=candidate_external_paths,
            )
            if final_reference_identity != reference_identity:
                raise ValueError(
                    "reference tree identity changed during transition",
                )
            if final_candidate_identity != candidate_identity:
                raise ValueError(
                    "candidate tree identity changed during transition",
                )
            verified_approvals = provisional_approvals
        artifact_status = "transition_qualified"
    except _WorkloadTransitionRejected as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        artifact_status = "transition_rejected"
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        artifact_status = "error"

    artifact = TransitionArtifact(
        created_at_utc=created_at,
        scenario_name=scenario_name,
        status=artifact_status,
        errors=errors,
        policy=policy,
        baseline_identity=baseline_identity,
        environment=environment,
        reference_identity=reference_identity,
        candidate_identity=candidate_identity,
        closures=closures,
        contract=contract,
        verified_approvals=verified_approvals,
        timing_assessment=TransitionTimingAssessment(),
    )
    _write_transition_artifact(artifact_path, artifact)
    if artifact.status != "transition_qualified":
        raise BenchmarkTransitionError(
            f"workload transition {scenario_name!r} ended {artifact.status}: {errors}",
        )
    return artifact


# ---------------------------------------------------------------------------
# Explicit measurement-only profiler
# ---------------------------------------------------------------------------


def _extract_hotspots(
    profiler: cProfile.Profile,
    top_n: int,
) -> list[tuple[str, float, int]]:
    stats = pstats.Stats(profiler, stream=StringIO())
    stats.sort_stats("cumulative")
    return [
        (f"{filename}:{lineno}({name})", cumulative, calls)
        for (
            filename,
            lineno,
            name,
        ), (
            _primitive_calls,
            calls,
            _total,
            cumulative,
            _callers,
        ) in sorted(
            stats.stats.items(),
            key=lambda item: item[1][3],
            reverse=True,
        )[:top_n]
    ]


def run_benchmark(
    scenario_path: Path,
    seed: int = 42,
    profile: bool = True,
    top_n_hotspots: int = 20,
    calibration_overrides: dict[str, object] | None = None,
) -> BenchmarkResult:
    """Run one production measurement without making a regression claim."""
    from stochastic_warfare.simulation.calibration import CalibrationSchema
    from stochastic_warfare.simulation.engine import EngineConfig
    from stochastic_warfare.simulation.runtime import (
        AnalysisVariant,
        SimulationRuntimeFactory,
    )

    scenario_path = scenario_path.resolve()
    if not scenario_path.is_file():
        raise FileNotFoundError(f"benchmark scenario not found: {scenario_path}")
    unknown_overrides = sorted(set(calibration_overrides or {}) - set(CalibrationSchema.model_fields))
    if unknown_overrides:
        raise ValueError(
            f"unknown benchmark calibration overrides: {unknown_overrides!r}",
        )

    variant = AnalysisVariant(
        variant_id="measurement",
        calibration_patch=calibration_overrides or {},
    )
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        DATA_DIR,
        (variant,),
    )
    session = prepared.build(
        variant.variant_id,
        seed=seed,
        max_ticks=DEFAULT_MAX_TICKS,
        recorder_factory=lambda context: _strict_recorder(context)[0],
        engine_config=EngineConfig(
            max_ticks=DEFAULT_MAX_TICKS,
            snapshot_interval_ticks=0,
        ),
        strict_mode=True,
    )
    if session.recorder is None:
        raise RuntimeError(
            "runtime factory did not construct the benchmark recorder",
        )
    context = session.context
    recorder = session.recorder

    hotspots: list[tuple[str, float, int]] = []
    peak_memory_mb: float | None = None
    if profile:
        tracemalloc.start()
        profiler = cProfile.Profile()
        started = time.perf_counter()
        profiler.enable()
        run_result = session.engine.run()
        profiler.disable()
        duration = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_memory_mb = peak_bytes / (1024 * 1024)
        hotspots = _extract_hotspots(profiler, top_n_hotspots)
    else:
        started = time.perf_counter()
        run_result = session.engine.run()
        duration = time.perf_counter() - started
    if not math.isfinite(duration) or duration <= 0.0:
        raise RuntimeError("measurement produced an invalid duration")

    victory = run_result.victory_result
    ticks = run_result.ticks_executed
    return BenchmarkResult(
        scenario_name=scenario_path.parent.name,
        unit_count=sum(len(units) for units in context.units_by_side.values()),
        wall_clock_s=duration,
        ticks_executed=ticks,
        ticks_per_second=ticks / duration,
        peak_memory_mb=peak_memory_mb,
        hotspots=hotspots,
        seed=seed,
        winner=victory.winning_side or None,
        commit=_full_commit(ROOT),
    )


# ---------------------------------------------------------------------------
# CLI used by the candidate driver and revision workers
# ---------------------------------------------------------------------------


def _worker_command(args: argparse.Namespace) -> int:
    run = run_revision_worker(
        repo_root=args.repo_root,
        scenario_relative=args.scenario_relative,
        revision=args.revision,
        workload=BenchmarkWorkload.model_validate_json(args.workload_json),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            run.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def _closure_worker_command(args: argparse.Namespace) -> int:
    closure = run_revision_closure(
        repo_root=args.repo_root,
        scenario_relative=args.scenario_relative,
        revision=args.revision,
        workload=BenchmarkWorkload.model_validate_json(args.workload_json),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            closure.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def _comparison_command(args: argparse.Namespace) -> int:
    artifact = run_paired_comparison(
        scenario_name=args.scenario,
        candidate_root=args.repo_root,
        baseline_path=args.baseline,
        artifact_path=args.artifact,
        allow_dirty_candidate=args.allow_dirty_candidate,
        worker_timeout_s=args.worker_timeout_seconds,
    )
    _, digest = validate_artifact(
        args.artifact,
        authoritative_baseline_path=(args.repo_root / "tests" / "benchmarks" / "baselines.json"),
    )
    print(
        f"{artifact.scenario_name}: {artifact.status}; artifact_sha256={digest}",
    )
    return 0


def _transition_command(args: argparse.Namespace) -> int:
    artifact = run_workload_transition(
        scenario_name=args.scenario,
        candidate_root=args.repo_root,
        baseline_path=args.baseline,
        artifact_path=args.artifact,
        allow_dirty_candidate=args.allow_dirty_candidate,
        worker_timeout_s=args.worker_timeout_seconds,
    )
    _, digest = validate_transition_artifact(
        args.artifact,
        authoritative_baseline_path=(args.repo_root / "tests" / "benchmarks" / "baselines.json"),
    )
    print(
        f"{artifact.scenario_name}: {artifact.status}; timing=not_applicable; artifact_sha256={digest}",
    )
    return 0


def _final_tree_verification_command(args: argparse.Namespace) -> int:
    raw_artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    if "closures" in raw_artifact:
        verification = verify_transition_final_tree(
            transition_artifact_path=args.artifact,
            verification_path=args.verification,
            final_root=args.repo_root,
            worker_timeout_s=args.worker_timeout_seconds,
        )
        _, digest = validate_transition_final_tree_verification(
            args.verification,
            transition_artifact_path=args.artifact,
            authoritative_baseline_path=(args.repo_root / "tests" / "benchmarks" / "baselines.json"),
        )
    else:
        verification = verify_final_tree(
            comparison_artifact_path=args.artifact,
            verification_path=args.verification,
            final_root=args.repo_root,
            worker_timeout_s=args.worker_timeout_seconds,
        )
        _, digest = validate_final_tree_verification(
            args.verification,
            comparison_artifact_path=args.artifact,
            authoritative_baseline_path=(args.repo_root / "tests" / "benchmarks" / "baselines.json"),
        )
    print(
        f"{verification.scenario_name}: final-tree {verification.status}; "
        f"final_commit={verification.final_identity.commit}; "
        f"verification_sha256={digest}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strict version-4 production benchmark evidence",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    worker = commands.add_parser("worker")
    worker.add_argument("--repo-root", type=Path, required=True)
    worker.add_argument("--scenario-relative", required=True)
    worker.add_argument(
        "--revision",
        choices=("reference", "candidate"),
        required=True,
    )
    worker.add_argument("--workload-json", required=True)
    worker.add_argument("--output", type=Path, required=True)
    worker.set_defaults(handler=_worker_command)

    closure_worker = commands.add_parser("closure-worker")
    closure_worker.add_argument("--repo-root", type=Path, required=True)
    closure_worker.add_argument("--scenario-relative", required=True)
    closure_worker.add_argument(
        "--revision",
        choices=("reference", "candidate"),
        required=True,
    )
    closure_worker.add_argument("--workload-json", required=True)
    closure_worker.add_argument("--output", type=Path, required=True)
    closure_worker.set_defaults(handler=_closure_worker_command)

    compare = commands.add_parser("compare")
    compare.add_argument(
        "--scenario",
        choices=("73_easting", "golan_heights"),
        default="73_easting",
    )
    compare.add_argument("--repo-root", type=Path, default=ROOT)
    compare.add_argument("--baseline", type=Path, default=BASELINES_PATH)
    compare.add_argument("--artifact", type=Path, required=True)
    compare.add_argument("--allow-dirty-candidate", action="store_true")
    compare.add_argument(
        "--worker-timeout-seconds",
        type=float,
        default=900.0,
    )
    compare.set_defaults(handler=_comparison_command)

    transition = commands.add_parser("transition")
    transition.add_argument(
        "--scenario",
        choices=("73_easting", "golan_heights"),
        default="73_easting",
    )
    transition.add_argument("--repo-root", type=Path, default=ROOT)
    transition.add_argument("--baseline", type=Path, default=BASELINES_PATH)
    transition.add_argument("--artifact", type=Path, required=True)
    transition.add_argument("--allow-dirty-candidate", action="store_true")
    transition.add_argument(
        "--worker-timeout-seconds",
        type=float,
        default=900.0,
    )
    transition.set_defaults(handler=_transition_command)

    verify_final = commands.add_parser("verify-final")
    verify_final.add_argument("--repo-root", type=Path, default=ROOT)
    verify_final.add_argument("--artifact", type=Path, required=True)
    verify_final.add_argument("--verification", type=Path, required=True)
    verify_final.add_argument(
        "--worker-timeout-seconds",
        type=float,
        default=900.0,
    )
    verify_final.set_defaults(handler=_final_tree_verification_command)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
