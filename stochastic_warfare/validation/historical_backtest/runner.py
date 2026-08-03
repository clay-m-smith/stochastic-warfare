"""Factory-owned production execution and scoped historical observations."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Literal

import numpy as np
from pydantic import field_validator, model_validator

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.engine import (
    PRODUCTION_TERMINAL_CONDITION_TYPES,
)
from stochastic_warfare.simulation.runtime import (
    CodeRevision,
    PreparedScenario,
    RuntimeProvenance,
    RuntimeSession,
)

from .common import (
    StrictFrozenModel,
    canonical_sha256,
    require_relative_posix_path,
    require_trimmed,
)
from .evaluator import JointCoverageEvaluation, evaluate_joint_coverage
from .studies import (
    HistoricalMetricPlan,
    HistoricalStudyPlan,
    PredeclarationReceipt,
    RatioComponent,
    SourceLineageRelationship,
    TerminalExchangeRatioV1,
    TerminalSideActiveCountV1,
    TerminalSideDestroyedCountV1,
    TerminalWinnerIndicatorV1,
    TimeToNaturalTerminalSecondsV1,
    validate_historical_runtime_scope,
)


class CodeRevisionEvidence(StrictFrozenModel):
    """Exact Git worktree revision bound to repository-predeclared evidence."""

    commit: str
    dirty: bool
    worktree_fingerprint: str

    @field_validator("commit", mode="before")
    @classmethod
    def _commit(cls, value: Any) -> str:
        text = require_trimmed(value, field_name="commit")
        if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
            raise ValueError("commit must be a lowercase 40-hex revision")
        return text

    @field_validator("worktree_fingerprint", mode="before")
    @classmethod
    def _worktree_fingerprint(cls, value: Any) -> str:
        return _digest(value, field_name="worktree_fingerprint")

    @field_validator("dirty", mode="before")
    @classmethod
    def _dirty(cls, value: Any) -> bool:
        if type(value) is not bool:
            raise ValueError("dirty must be a strict boolean")
        return value

    @model_validator(mode="after")
    def _clean_identity(self) -> CodeRevisionEvidence:
        if not self.dirty and self.worktree_fingerprint != canonical_sha256(
            {"commit": self.commit, "dirty": False},
        ):
            raise ValueError(
                "clean worktree fingerprint differs from the code revision",
            )
        return self


def _digest(value: Any, *, field_name: str) -> str:
    text = require_trimmed(value, field_name=field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _roster_entries(
    value: Any,
    *,
    field_name: str,
    typed: bool,
) -> tuple[tuple[Any, ...], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field_name} must be a nonempty ordered list")
    width = 3 if typed else 2
    result: list[tuple[Any, ...]] = []
    identities: set[Any] = set()
    for entry in value:
        if not isinstance(entry, (list, tuple)) or len(entry) != width:
            raise ValueError(f"{field_name} entries must have exactly {width} fields")
        side = require_trimmed(entry[0], field_name=f"{field_name} side")
        if typed:
            unit_type = require_trimmed(entry[1], field_name=f"{field_name} unit type")
            count = entry[2]
            identity: Any = (side, unit_type)
            normalized = (side, unit_type, count)
        else:
            count = entry[1]
            identity = side
            normalized = (side, count)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError(f"{field_name} counts must be positive strict integers")
        if identity in identities:
            raise ValueError(f"{field_name} identities must be duplicate-free")
        identities.add(identity)
        result.append(normalized)
    return tuple(result)


class UnitAssignmentEvidence(StrictFrozenModel):
    """One exact production command/doctrine assignment."""

    unit_id: str
    side: str
    commander_profile_id: str | None
    doctrine_school_id: str | None

    @field_validator("unit_id", "side", mode="before")
    @classmethod
    def _required_text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator("commander_profile_id", "doctrine_school_id", mode="before")
    @classmethod
    def _optional_text(cls, value: Any, info: Any) -> str | None:
        if value is None:
            return None
        return require_trimmed(value, field_name=info.field_name)


class RuntimeProvenanceEvidence(StrictFrozenModel):
    """Complete per-run production provenance exposed by RuntimeSession."""

    code_revision: CodeRevisionEvidence
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    doctrine_assignment_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    final_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitAssignmentEvidence, ...]
    arriving_unit_assignments: tuple[UnitAssignmentEvidence, ...]

    @field_validator(
        "data_revision",
        "catalog_revision",
        "doctrine_catalog_fingerprint",
        "doctrine_assignment_fingerprint",
        "loaded_roster_loadout_fingerprint",
        "final_roster_loadout_fingerprint",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("data_file_count", mode="before")
    @classmethod
    def _file_count(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("data_file_count must be a positive strict integer")
        return value

    @model_validator(mode="after")
    def _assignment_topology(self) -> RuntimeProvenanceEvidence:
        initial_ids = tuple(item.unit_id for item in self.initial_unit_assignments)
        arriving_ids = tuple(item.unit_id for item in self.arriving_unit_assignments)
        if len(initial_ids) != len(set(initial_ids)):
            raise ValueError("initial unit assignments must be duplicate-free")
        if len(arriving_ids) != len(set(arriving_ids)):
            raise ValueError("arriving unit assignments must be duplicate-free")
        if set(initial_ids).intersection(arriving_ids):
            raise ValueError("initial and arriving unit assignments must be disjoint")
        if self.doctrine_assignment_fingerprint != canonical_sha256(
            self.initial_unit_assignments + self.arriving_unit_assignments,
        ):
            raise ValueError(
                "doctrine assignment fingerprint differs from ordered assignments",
            )
        return self


class HistoricalPreparationEvidence(StrictFrozenModel):
    """Factory-completed evidence available before the first runtime build."""

    scenario_path: str
    data_root: str
    variant_id: str
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    authored_typed_roster: tuple[tuple[str, str, int], ...]
    code_revision: CodeRevisionEvidence
    data_revision: str
    data_file_count: int
    effective_era_id: str
    era_config_sha256: str
    era_runtime_contract_sha256: str
    predeclaration_receipt: PredeclarationReceipt | None

    @field_validator("scenario_path", "data_root", mode="before")
    @classmethod
    def _paths(cls, value: Any, info: Any) -> str:
        return require_relative_posix_path(value, field_name=info.field_name)

    @field_validator("variant_id", "effective_era_id", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator(
        "source_fingerprint",
        "config_fingerprint",
        "data_revision",
        "era_config_sha256",
        "era_runtime_contract_sha256",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("authored_roster", mode="before")
    @classmethod
    def _roster(cls, value: Any) -> tuple[tuple[str, int], ...]:
        return _roster_entries(value, field_name="authored_roster", typed=False)

    @field_validator("authored_typed_roster", mode="before")
    @classmethod
    def _typed_roster(cls, value: Any) -> tuple[tuple[str, str, int], ...]:
        return _roster_entries(value, field_name="authored_typed_roster", typed=True)

    @field_validator("data_file_count", mode="before")
    @classmethod
    def _file_count(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("data_file_count must be a positive strict integer")
        return value

    @model_validator(mode="after")
    def _roster_consistency(self) -> HistoricalPreparationEvidence:
        if _typed_roster_totals(self.authored_typed_roster) != self.authored_roster:
            raise ValueError("prepared authored typed roster differs from authored roster")
        return self


class TerminalOutcomeEvidence(StrictFrozenModel):
    """Public simulation outcome at natural termination or study cutoff."""

    seed: int
    ticks_executed: int
    duration_s: float
    winning_side: str
    condition_type: str
    game_over: bool
    natural_terminal: bool
    right_censored: bool

    @field_validator("seed", mode="before")
    @classmethod
    def _seed(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("seed must be a non-negative strict integer")
        return value

    @field_validator("ticks_executed", mode="before")
    @classmethod
    def _ticks(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("ticks_executed must be a positive strict integer")
        return value

    @field_validator("winning_side", "condition_type", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator(
        "game_over",
        "natural_terminal",
        "right_censored",
        mode="before",
    )
    @classmethod
    def _booleans(cls, value: Any, info: Any) -> bool:
        if type(value) is not bool:
            raise ValueError(f"{info.field_name} must be a strict boolean")
        return value

    @field_validator("duration_s", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("duration_s must be finite and non-negative")
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError("duration_s must be finite and non-negative")
        return number

    @model_validator(mode="after")
    def _terminal_semantics(self) -> TerminalOutcomeEvidence:
        if not self.game_over:
            raise ValueError("historical observation requires a public terminal result")
        if self.natural_terminal == self.right_censored:
            raise ValueError(
                "terminal outcome must be exactly natural or right-censored",
            )
        if self.right_censored != (self.condition_type == "max_ticks"):
            raise ValueError("right-censoring must correspond exactly to max_ticks")
        if self.condition_type not in PRODUCTION_TERMINAL_CONDITION_TYPES:
            raise ValueError("condition_type is not a supported production terminal condition")
        return self


class UnitStatusObservation(StrictFrozenModel):
    """One exact typed unit considered by a scoped extractor."""

    unit_id: str
    unit_type: str
    side: str
    status: str

    @field_validator("unit_id", "unit_type", "side", "status", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        text = require_trimmed(value, field_name=info.field_name)
        if info.field_name == "status" and text not in UnitStatus.__members__:
            raise ValueError("status is not a production UnitStatus name")
        return text

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in UnitStatus.__members__:
            raise ValueError(f"unsupported unit status {value!r}")
        return value


class UnitIdentityEvidence(StrictFrozenModel):
    """One exact initial production unit identity before observation."""

    unit_id: str
    unit_type: str
    side: str

    @field_validator("unit_id", "unit_type", "side", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)


class MetricObservationReceipt(StrictFrozenModel):
    """Recomputable typed evidence for one metric in one production run."""

    seed: int
    metric_id: str
    extractor_id: str
    extractor_sha256: str
    source_fingerprint: str
    config_fingerprint: str
    event_boundary: str
    observation_time_s: float
    natural_terminal: bool
    right_censored: bool
    runtime_unit: str
    source_unit: str
    scale: float
    offset: float
    raw_value: float
    value: float
    in_source_range: bool
    selected_units: tuple[UnitStatusObservation, ...]
    counted_unit_ids: tuple[str, ...]
    numerator_count: float | None
    denominator_count: float | None
    effective_era_id: str
    era_config_sha256: str
    era_runtime_contract_sha256: str
    terminal_outcome_sha256: str

    @field_validator("seed", mode="before")
    @classmethod
    def _seed(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("seed must be a non-negative strict integer")
        return value

    @field_validator(
        "metric_id",
        "extractor_id",
        "event_boundary",
        "runtime_unit",
        "source_unit",
        "effective_era_id",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator(
        "extractor_sha256",
        "source_fingerprint",
        "config_fingerprint",
        "era_config_sha256",
        "era_runtime_contract_sha256",
        "terminal_outcome_sha256",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("natural_terminal", "right_censored", "in_source_range", mode="before")
    @classmethod
    def _booleans(cls, value: Any, info: Any) -> bool:
        if type(value) is not bool:
            raise ValueError(f"{info.field_name} must be a strict boolean")
        return value

    @field_validator(
        "observation_time_s",
        "scale",
        "offset",
        "raw_value",
        "value",
        "numerator_count",
        "denominator_count",
        mode="before",
    )
    @classmethod
    def _finite(cls, value: Any, info: Any) -> float | None:
        if value is None and info.field_name in {
            "numerator_count",
            "denominator_count",
        }:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be finite")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{info.field_name} must be finite")
        return number

    @model_validator(mode="after")
    def _receipt_consistency(self) -> MetricObservationReceipt:
        if self.natural_terminal == self.right_censored:
            raise ValueError("receipt must be exactly natural or right-censored")
        selected_ids = tuple(unit.unit_id for unit in self.selected_units)
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("receipt selected unit IDs must be duplicate-free")
        if len(self.counted_unit_ids) != len(set(self.counted_unit_ids)):
            raise ValueError("receipt counted unit IDs must be duplicate-free")
        if not set(self.counted_unit_ids) <= set(selected_ids):
            raise ValueError("receipt counted IDs must be selected units")
        is_ratio = self.extractor_id == "terminal_exchange_ratio.v1"
        if is_ratio != (self.numerator_count is not None and self.denominator_count is not None):
            raise ValueError(
                "only exchange-ratio receipts carry numerator/denominator counts",
            )
        if is_ratio and (self.numerator_count < 0.0 or self.denominator_count < 0.0):
            raise ValueError("exchange-ratio component counts must be non-negative")
        if self.value != self.raw_value * self.scale + self.offset:
            raise ValueError("receipt value is inconsistent with its conversion")
        return self


class MetricStatistics(StrictFrozenModel):
    """Derived statistics retained beside every exact raw vector."""

    mean: float
    median: float
    std: float
    minimum: float
    maximum: float
    p5: float
    p95: float
    n: int

    @field_validator("mean", "median", "std", "minimum", "maximum", "p5", "p95", mode="before")
    @classmethod
    def _finite(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be finite")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{info.field_name} must be finite")
        return number

    @field_validator("n", mode="before")
    @classmethod
    def _sample_size(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("n must be a positive strict integer")
        return value

    @model_validator(mode="after")
    def _ordered_summary(self) -> MetricStatistics:
        if not self.minimum <= self.p5 <= self.median <= self.p95 <= self.maximum:
            raise ValueError("metric quantiles must be ordered within min/max")
        if self.std < 0.0:
            raise ValueError("metric standard deviation must be non-negative")
        return self


def _assignment_counts_match(
    roster: tuple[tuple[str, int], ...],
    assignments: tuple[UnitAssignmentEvidence, ...],
) -> bool:
    counts = {side: 0 for side, _ in roster}
    if len(counts) != len(roster):
        return False
    for assignment in assignments:
        if assignment.side not in counts:
            return False
        counts[assignment.side] += 1
    return tuple((side, counts[side]) for side, _ in roster) == roster


def _typed_roster_totals(
    roster: tuple[tuple[str, str, int], ...],
) -> tuple[tuple[str, int], ...]:
    totals: dict[str, int] = {}
    identities: set[tuple[str, str]] = set()
    for side, unit_type, count in roster:
        if (
            not side
            or not unit_type
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or (side, unit_type) in identities
        ):
            raise ValueError("authored typed roster contains an invalid or duplicate entry")
        identities.add((side, unit_type))
        totals.setdefault(side, 0)
        totals[side] += count
    return tuple(totals.items())


def _loaded_type_counts(
    roster: tuple[UnitIdentityEvidence, ...],
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for unit in roster:
        identity = (unit.side, unit.unit_type)
        counts[identity] = counts.get(identity, 0) + 1
    return counts


class HistoricalRunEvidence(StrictFrozenModel):
    """Complete production outcome, provenance, and receipts for one seed."""

    seed: int
    source_fingerprint: str
    config_fingerprint: str
    loaded_roster: tuple[tuple[str, int], ...]
    loaded_typed_roster: tuple[UnitIdentityEvidence, ...]
    terminal_outcome: TerminalOutcomeEvidence
    runtime_provenance: RuntimeProvenanceEvidence
    receipts: tuple[MetricObservationReceipt, ...]

    @field_validator("seed", mode="before")
    @classmethod
    def _seed(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("seed must be a non-negative strict integer")
        return value

    @field_validator("source_fingerprint", "config_fingerprint", mode="before")
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("loaded_roster", mode="before")
    @classmethod
    def _loaded_roster(cls, value: Any) -> tuple[tuple[str, int], ...]:
        return _roster_entries(value, field_name="loaded_roster", typed=False)

    @model_validator(mode="after")
    def _seed_and_identity_match(self) -> HistoricalRunEvidence:
        if self.terminal_outcome.seed != self.seed:
            raise ValueError("run and terminal-outcome seeds differ")
        if self.terminal_outcome.winning_side not in {
            *(side for side, _ in self.loaded_roster),
            "draw",
        }:
            raise ValueError("terminal winner is not a loaded side or draw")
        if any(receipt.seed != self.seed for receipt in self.receipts):
            raise ValueError("run contains a receipt for another seed")
        if any(
            receipt.source_fingerprint != self.source_fingerprint
            or receipt.config_fingerprint != self.config_fingerprint
            for receipt in self.receipts
        ):
            raise ValueError("run receipt source/config identity differs")
        if not _assignment_counts_match(
            self.loaded_roster,
            self.runtime_provenance.initial_unit_assignments,
        ):
            raise ValueError("run loaded roster differs from initial assignments")
        typed_ids = tuple(unit.unit_id for unit in self.loaded_typed_roster)
        assignments = self.runtime_provenance.initial_unit_assignments
        if (
            len(typed_ids) != len(set(typed_ids))
            or typed_ids != tuple(assignment.unit_id for assignment in assignments)
            or any(
                unit.side != assignment.side
                for unit, assignment in zip(
                    self.loaded_typed_roster,
                    assignments,
                    strict=True,
                )
            )
        ):
            raise ValueError("run typed roster differs from initial assignments")
        if any(receipt.terminal_outcome_sha256 != canonical_sha256(self.terminal_outcome) for receipt in self.receipts):
            raise ValueError("run receipt terminal identity differs")
        return self


class HistoricalExecutionEvidence(StrictFrozenModel):
    """Immutable factory-owned evidence for the complete held-out batch."""

    scenario_path: str
    data_root: str
    variant_id: str
    ordered_metrics: tuple[str, ...]
    seeds: tuple[int, ...]
    maximum_ticks: int
    observation_boundary_s: float
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    authored_typed_roster: tuple[tuple[str, str, int], ...]
    loaded_roster: tuple[tuple[str, int], ...]
    loaded_typed_roster: tuple[UnitIdentityEvidence, ...]
    code_revision: CodeRevisionEvidence
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitAssignmentEvidence, ...]
    effective_era_id: str
    era_config_sha256: str
    era_runtime_contract_sha256: str
    predeclaration_receipt: PredeclarationReceipt | None
    metric_vectors: tuple[tuple[str, tuple[float, ...]], ...]
    metric_statistics: tuple[tuple[str, MetricStatistics], ...]
    runs: tuple[HistoricalRunEvidence, ...]

    @field_validator("scenario_path", "data_root", mode="before")
    @classmethod
    def _paths(cls, value: Any, info: Any) -> str:
        return require_relative_posix_path(value, field_name=info.field_name)

    @field_validator("authored_roster", "loaded_roster", mode="before")
    @classmethod
    def _rosters(cls, value: Any, info: Any) -> tuple[tuple[str, int], ...]:
        return _roster_entries(value, field_name=info.field_name, typed=False)

    @field_validator("authored_typed_roster", mode="before")
    @classmethod
    def _typed_roster(cls, value: Any) -> tuple[tuple[str, str, int], ...]:
        return _roster_entries(value, field_name="authored_typed_roster", typed=True)

    @field_validator("ordered_metrics", mode="before")
    @classmethod
    def _metrics(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("ordered_metrics must be a nonempty ordered list")
        result = tuple(require_trimmed(item, field_name="metric ID") for item in value)
        if len(result) != len(set(result)):
            raise ValueError("ordered_metrics must be duplicate-free")
        return result

    @field_validator("seeds", mode="before")
    @classmethod
    def _seeds(cls, value: Any) -> tuple[int, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("seeds must be a nonempty ordered list")
        result = tuple(value)
        if any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in result):
            raise ValueError("seeds must contain non-negative strict integers")
        if len(result) != len(set(result)):
            raise ValueError("seeds must be duplicate-free")
        return result

    @field_validator("metric_vectors", mode="before")
    @classmethod
    def _vectors(cls, value: Any) -> tuple[tuple[str, tuple[float, ...]], ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("metric_vectors must be a nonempty ordered list")
        result: list[tuple[str, tuple[float, ...]]] = []
        for entry in value:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError("metric vector entries must contain an ID and vector")
            metric_id = require_trimmed(entry[0], field_name="metric vector ID")
            if not isinstance(entry[1], (list, tuple)) or not entry[1]:
                raise ValueError("metric vectors must be nonempty ordered lists")
            vector: list[float] = []
            for item in entry[1]:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise ValueError("metric vectors must contain finite numbers")
                number = float(item)
                if not math.isfinite(number):
                    raise ValueError("metric vectors must contain finite numbers")
                vector.append(number)
            result.append((metric_id, tuple(vector)))
        return tuple(result)

    @field_validator("variant_id", "effective_era_id", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator(
        "source_fingerprint",
        "config_fingerprint",
        "data_revision",
        "catalog_revision",
        "doctrine_catalog_fingerprint",
        "loaded_roster_loadout_fingerprint",
        "era_config_sha256",
        "era_runtime_contract_sha256",
        mode="before",
    )
    @classmethod
    def _digests(cls, value: Any, info: Any) -> str:
        return _digest(value, field_name=info.field_name)

    @field_validator("maximum_ticks", "data_file_count", mode="before")
    @classmethod
    def _positive_ints(cls, value: Any, info: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{info.field_name} must be a positive strict integer")
        return value

    @field_validator("observation_boundary_s", mode="before")
    @classmethod
    def _boundary(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("observation_boundary_s must be finite and positive")
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError("observation_boundary_s must be finite and positive")
        return number

    @model_validator(mode="after")
    def _complete_batch(self) -> HistoricalExecutionEvidence:
        if tuple(run.seed for run in self.runs) != self.seeds:
            raise ValueError("execution runs must exactly match ordered seeds")
        if not self.ordered_metrics or len(self.ordered_metrics) != len(
            set(self.ordered_metrics),
        ):
            raise ValueError("ordered_metrics must be nonempty and duplicate-free")
        for run in self.runs:
            if tuple(receipt.metric_id for receipt in run.receipts) != self.ordered_metrics:
                raise ValueError("every run must contain every ordered receipt exactly once")
            provenance = run.runtime_provenance
            if run.terminal_outcome.winning_side not in {
                *(side for side, _ in self.authored_roster),
                "draw",
            }:
                raise ValueError("terminal winner is not an authored side or draw")
            if (
                run.source_fingerprint != self.source_fingerprint
                or run.config_fingerprint != self.config_fingerprint
                or run.loaded_roster != self.loaded_roster
                or run.loaded_typed_roster != self.loaded_typed_roster
                or provenance.code_revision != self.code_revision
                or provenance.data_revision != self.data_revision
                or provenance.data_file_count != self.data_file_count
                or provenance.catalog_revision != self.catalog_revision
                or provenance.doctrine_catalog_fingerprint != self.doctrine_catalog_fingerprint
                or provenance.loaded_roster_loadout_fingerprint != self.loaded_roster_loadout_fingerprint
                or provenance.initial_unit_assignments != self.initial_unit_assignments
                or any(
                    receipt.effective_era_id != self.effective_era_id
                    or receipt.era_config_sha256 != self.era_config_sha256
                    or receipt.era_runtime_contract_sha256 != self.era_runtime_contract_sha256
                    for receipt in run.receipts
                )
            ):
                raise ValueError("run identity/provenance differs from execution summary")
        if not _assignment_counts_match(self.loaded_roster, self.initial_unit_assignments):
            raise ValueError("execution loaded roster differs from initial assignments")
        if _typed_roster_totals(self.authored_typed_roster) != self.authored_roster:
            raise ValueError("authored typed roster differs from authored roster")
        if self.loaded_roster != self.authored_roster:
            raise ValueError("loaded roster differs from authored roster")
        if not _assignment_counts_match(
            self.loaded_roster,
            tuple(
                UnitAssignmentEvidence(
                    unit_id=unit.unit_id,
                    side=unit.side,
                    commander_profile_id=None,
                    doctrine_school_id=None,
                )
                for unit in self.loaded_typed_roster
            ),
        ):
            raise ValueError("loaded typed roster differs from loaded roster")
        authored_type_counts = {(side, unit_type): count for side, unit_type, count in self.authored_typed_roster}
        if _loaded_type_counts(self.loaded_typed_roster) != authored_type_counts:
            raise ValueError("loaded typed roster differs from authored typed roster")
        if tuple(metric for metric, _ in self.metric_vectors) != self.ordered_metrics:
            raise ValueError("metric_vectors must exactly match ordered_metrics")
        if tuple(metric for metric, _ in self.metric_statistics) != self.ordered_metrics:
            raise ValueError("metric_statistics must exactly match ordered_metrics")
        for index, (metric, values) in enumerate(self.metric_vectors):
            if len(values) != len(self.seeds) or any(
                values[run_index] != self.runs[run_index].receipts[index].value for run_index in range(len(self.runs))
            ):
                raise ValueError(
                    f"metric vector {metric!r} does not match observation receipts",
                )
            expected = _metric_statistics(values)
            if self.metric_statistics[index] != (metric, expected):
                raise ValueError(
                    f"metric statistics {metric!r} do not match its vector",
                )
        return self


class HistoricalEligibility(StrictFrozenModel):
    """Artifact promotion eligibility before explicit ledger acceptance."""

    promotion_eligible: bool
    reason_codes: tuple[str, ...]

    @field_validator("promotion_eligible", mode="before")
    @classmethod
    def _validated(cls, value: Any) -> bool:
        if type(value) is not bool:
            raise ValueError("promotion_eligible must be a strict boolean")
        return value

    @field_validator("reason_codes", mode="before")
    @classmethod
    def _reasons(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("reason_codes must be an ordered list")
        result = tuple(require_trimmed(item, field_name="reason code") for item in value)
        if len(result) != len(set(result)):
            raise ValueError("reason_codes must be duplicate-free")
        return result

    @model_validator(mode="after")
    def _promotion_semantics(self) -> HistoricalEligibility:
        if self.promotion_eligible == bool(self.reason_codes):
            raise ValueError("eligibility must be validated exactly when no reasons exist")
        return self


class HistoricalBacktestResult(StrictFrozenModel):
    """Completed production backtest before durable artifact wrapping."""

    status: Literal["PASS", "FAIL"]
    plan_sha256: str
    execution: HistoricalExecutionEvidence
    evaluation: JointCoverageEvaluation
    eligibility: HistoricalEligibility

    @field_validator("plan_sha256", mode="before")
    @classmethod
    def _plan_digest(cls, value: Any) -> str:
        return _digest(value, field_name="plan_sha256")

    @model_validator(mode="after")
    def _verdict_consistency(self) -> HistoricalBacktestResult:
        expected_status = "PASS" if self.evaluation.passed else "FAIL"
        if self.status != expected_status:
            raise ValueError("backtest status disagrees with joint evaluation")
        if self.eligibility.promotion_eligible and (self.status != "PASS" or self.eligibility.reason_codes):
            raise ValueError("production validation requires eligible PASS evidence")
        return self


class HistoricalExecutionError(RuntimeError):
    """Typed post-plan execution failure with completed run evidence."""

    def __init__(
        self,
        *,
        failure_stage: str,
        error_code: str,
        message: str,
        preparation: HistoricalPreparationEvidence | None,
        completed_runs: tuple[HistoricalRunEvidence, ...],
    ) -> None:
        super().__init__(message)
        self.failure_stage = failure_stage
        self.error_code = error_code
        self.preparation = preparation
        self.completed_runs = completed_runs


def _code_revision(value: CodeRevision) -> CodeRevisionEvidence:
    return CodeRevisionEvidence.model_validate(asdict(value))


def _runtime_provenance(value: RuntimeProvenance) -> RuntimeProvenanceEvidence:
    return RuntimeProvenanceEvidence.model_validate(asdict(value))


def _metric_statistics(values: tuple[float, ...]) -> MetricStatistics:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("metric statistics require a complete finite vector")
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


def _units_for_component(
    session: RuntimeSession,
    *,
    side: str,
    included_unit_types: tuple[str, ...],
) -> tuple[Unit, ...]:
    initial_ids = {assignment.unit_id for assignment in session.initial_unit_assignments}
    by_type: dict[str, list[Unit]] = {unit_type: [] for unit_type in included_unit_types}
    for unit in session.context.units_by_side[side]:
        if unit.entity_id in initial_ids and unit.unit_type in by_type:
            by_type[unit.unit_type].append(unit)
    ordered: list[Unit] = []
    for unit_type in included_unit_types:
        ordered.extend(sorted(by_type[unit_type], key=lambda unit: unit.entity_id))
    return tuple(ordered)


def _unit_observations(
    units: tuple[Unit, ...],
) -> tuple[UnitStatusObservation, ...]:
    return tuple(
        UnitStatusObservation(
            unit_id=unit.entity_id,
            unit_type=unit.unit_type,
            side=str(unit.side),
            status=unit.status.name,
        )
        for unit in units
    )


def _loaded_typed_roster(session: RuntimeSession) -> tuple[UnitIdentityEvidence, ...]:
    units = {unit.entity_id: unit for side_units in session.context.units_by_side.values() for unit in side_units}
    if set(units) != {assignment.unit_id for assignment in session.initial_unit_assignments}:
        raise RuntimeError("initial assignment topology differs from the loaded units")
    return tuple(
        UnitIdentityEvidence(
            unit_id=assignment.unit_id,
            unit_type=units[assignment.unit_id].unit_type,
            side=assignment.side,
        )
        for assignment in session.initial_unit_assignments
    )


def _authored_typed_roster(source_config: Any) -> tuple[tuple[str, str, int], ...]:
    counts: dict[tuple[str, str], int] = {}
    for side in source_config.sides:
        for unit in side.units:
            identity = (side.side, unit.unit_type)
            counts.setdefault(identity, 0)
            counts[identity] += unit.count
    return tuple((side, unit_type, count) for (side, unit_type), count in counts.items())


def _preparation_evidence(
    prepared: PreparedScenario,
    plan: HistoricalStudyPlan,
) -> HistoricalPreparationEvidence:
    data_parts = tuple(part for part in plan.data_root.split("/") if part)
    repository_root = prepared.data_root.resolve()
    for _ in data_parts:
        repository_root = repository_root.parent
    try:
        scenario_path = (
            prepared.scenario_path.resolve()
            .relative_to(
                repository_root,
            )
            .as_posix()
        )
        data_root = (
            prepared.data_root.resolve()
            .relative_to(
                repository_root,
            )
            .as_posix()
        )
    except ValueError as exc:
        raise ValueError(
            "prepared scenario/data paths cannot be represented in the study repository",
        ) from exc
    variant = prepared.variant(plan.analysis.variant_id)
    return HistoricalPreparationEvidence(
        scenario_path=scenario_path,
        data_root=data_root,
        variant_id=variant.variant_id,
        source_fingerprint=prepared.source_fingerprint,
        config_fingerprint=variant.config_fingerprint,
        authored_roster=prepared.authored_roster,
        authored_typed_roster=_authored_typed_roster(prepared.source_config),
        code_revision=_code_revision(prepared.code_revision),
        data_revision=prepared.data_revision,
        data_file_count=prepared.data_file_count,
        effective_era_id=variant.era_runtime_contract.selected_registry_id,
        era_config_sha256=canonical_sha256(
            variant.era_config.model_dump(mode="json"),
        ),
        era_runtime_contract_sha256=canonical_sha256(
            variant.era_runtime_contract.model_dump(mode="json"),
        ),
        predeclaration_receipt=plan.predeclaration_receipt,
    )


def _count_component(
    session: RuntimeSession,
    component: Any,
) -> tuple[float, tuple[UnitStatusObservation, ...], tuple[str, ...]]:
    units = _units_for_component(
        session,
        side=component.side,
        included_unit_types=component.included_unit_types,
    )
    status_name = component.status if isinstance(component, RatioComponent) else component.statuses[0]
    target_status = UnitStatus[status_name]
    selected = _unit_observations(units)
    counted = tuple(unit.entity_id for unit in units if unit.status == target_status)
    return float(len(counted)), selected, counted


def _metric_receipt(
    *,
    plan: HistoricalMetricPlan,
    session: RuntimeSession,
    result: Any,
    effective_era_id: str,
    era_config_sha256: str,
    era_runtime_contract_sha256: str,
) -> MetricObservationReceipt:
    extractor = plan.extractor
    right_censored = result.victory_result.condition_type == "max_ticks"
    natural_terminal = not right_censored
    selected: tuple[UnitStatusObservation, ...] = ()
    counted: tuple[str, ...] = ()
    numerator_count: float | None = None
    denominator_count: float | None = None

    if isinstance(
        extractor,
        (TerminalSideDestroyedCountV1, TerminalSideActiveCountV1),
    ):
        raw_value, selected, counted = _count_component(session, extractor)
    elif isinstance(extractor, TimeToNaturalTerminalSecondsV1):
        raw_value = float(result.duration_s)
    elif isinstance(extractor, TerminalWinnerIndicatorV1):
        raw_value = float(result.victory_result.game_over and result.victory_result.winning_side == extractor.side)
    elif isinstance(extractor, TerminalExchangeRatioV1):
        numerator, numerator_units, numerator_counted = _count_component(
            session,
            extractor.numerator,
        )
        denominator, denominator_units, denominator_counted = _count_component(
            session,
            extractor.denominator,
        )
        raw_value = numerator / max(1.0, denominator)
        numerator_count = numerator
        denominator_count = denominator
        selected = numerator_units + denominator_units
        counted = numerator_counted + denominator_counted
    else:
        raise ValueError(f"Unsupported extractor {extractor!r}")

    value = raw_value * extractor.conversion.scale + extractor.conversion.offset
    in_range = plan.source_range.minimum <= value <= plan.source_range.maximum
    if isinstance(extractor, TimeToNaturalTerminalSecondsV1) and right_censored:
        in_range = False
    terminal_payload = {
        "seed": session.seed,
        "ticks_executed": result.ticks_executed,
        "duration_s": result.duration_s,
        "winning_side": result.victory_result.winning_side,
        "condition_type": result.victory_result.condition_type,
        "game_over": result.victory_result.game_over,
        "natural_terminal": natural_terminal,
        "right_censored": right_censored,
    }
    return MetricObservationReceipt(
        seed=session.seed,
        metric_id=plan.metric_id,
        extractor_id=extractor.extractor_id,
        extractor_sha256=canonical_sha256(extractor),
        source_fingerprint=session.source_fingerprint,
        config_fingerprint=session.config_fingerprint,
        event_boundary=extractor.event_boundary,
        observation_time_s=float(result.duration_s),
        natural_terminal=natural_terminal,
        right_censored=right_censored,
        runtime_unit=extractor.runtime_unit,
        source_unit=plan.source_unit,
        scale=extractor.conversion.scale,
        offset=extractor.conversion.offset,
        raw_value=raw_value,
        value=value,
        in_source_range=in_range,
        selected_units=selected,
        counted_unit_ids=counted,
        numerator_count=numerator_count,
        denominator_count=denominator_count,
        effective_era_id=effective_era_id,
        era_config_sha256=era_config_sha256,
        era_runtime_contract_sha256=era_runtime_contract_sha256,
        terminal_outcome_sha256=canonical_sha256(terminal_payload),
    )


class HistoricalBacktestRunner:
    """Build fresh production sessions and observe them before disposal."""

    def __init__(
        self,
        prepared: PreparedScenario,
        plan: HistoricalStudyPlan,
    ) -> None:
        if not isinstance(prepared, PreparedScenario):
            raise TypeError("prepared must be a PreparedScenario")
        self._plan = plan
        self._prepared = prepared
        self._failure_stage = "runtime_construction"
        self._completed_runs: tuple[HistoricalRunEvidence, ...] = ()
        try:
            self._preparation = _preparation_evidence(prepared, plan)
            self._validate_prepared_contract()
        except Exception as exc:
            message = " ".join(str(exc).split())[:1000] or type(exc).__name__
            preparation = getattr(self, "_preparation", None)
            if preparation is not None and (
                preparation.scenario_path != plan.scenario_path
                or preparation.data_root != plan.data_root
                or preparation.variant_id != plan.analysis.variant_id
            ):
                preparation = None
            raise HistoricalExecutionError(
                failure_stage="runtime_preparation",
                error_code="historical_runtime_preparation_failed",
                message=message,
                preparation=preparation,
                completed_runs=(),
            ) from exc

    @property
    def preparation(self) -> HistoricalPreparationEvidence:
        """Return immutable production-preparation evidence for error reporting."""
        return self._preparation

    def _validate_prepared_contract(self) -> None:
        data_parts = tuple(part for part in self._plan.data_root.split("/") if part)
        if len(self._prepared.data_root.parents) < len(data_parts):
            raise ValueError("prepared data root cannot be bound to the study plan")
        repository_root = self._prepared.data_root
        for _ in data_parts:
            repository_root = repository_root.parent
        expected_data_root = (repository_root / self._plan.data_root).resolve()
        expected_scenario = (repository_root / self._plan.scenario_path).resolve()
        if (
            self._prepared.data_root.resolve() != expected_data_root
            or self._prepared.scenario_path.resolve() != expected_scenario
        ):
            raise ValueError("prepared scenario/data paths differ from the study plan")
        if len(self._prepared.variants) != 1:
            raise ValueError("historical runner requires exactly one prepared variant")
        variant = self._prepared.variant(self._plan.analysis.variant_id)
        source_config = self._prepared.source_config
        if variant.config != source_config:
            raise ValueError("historical prepared variant must not alter source configuration")
        validate_historical_runtime_scope(
            self._plan,
            source_config,
            data_root=self._prepared.data_root,
        )

    def run(self) -> HistoricalBacktestResult:
        """Execute every seed or raise typed evidence for a post-start fault."""
        self._failure_stage = "runtime_construction"
        self._completed_runs = ()
        try:
            return self._run_validated()
        except HistoricalExecutionError:
            raise
        except Exception as exc:
            message = " ".join(str(exc).split())[:1000]
            if not message:
                message = type(exc).__name__
            raise HistoricalExecutionError(
                failure_stage=self._failure_stage,
                error_code=f"historical_{self._failure_stage}_failed",
                message=message,
                preparation=self._preparation,
                completed_runs=self._completed_runs,
            ) from exc

    def _run_validated(self) -> HistoricalBacktestResult:
        """Execute the validated plan through fresh factory-owned sessions."""
        prepared = self._prepared
        variant = prepared.variant(self._plan.analysis.variant_id)
        effective_era_id = variant.era_runtime_contract.selected_registry_id
        era_config_sha256 = canonical_sha256(
            variant.era_config.model_dump(mode="json"),
        )
        era_runtime_contract_sha256 = canonical_sha256(
            variant.era_runtime_contract.model_dump(mode="json"),
        )
        ordered_plans = self._plan.gating_metrics + self._plan.diagnostic_metrics
        ordered_metrics = tuple(metric.metric_id for metric in ordered_plans)
        runs: list[HistoricalRunEvidence] = []
        loaded_roster: tuple[tuple[str, int], ...] | None = None
        batch_loaded_typed_roster: tuple[UnitIdentityEvidence, ...] | None = None
        static_provenance: RuntimeProvenance | None = None

        for seed in self._plan.held_out_seeds:
            self._failure_stage = "runtime_construction"
            session = prepared.build(
                variant,
                seed=seed,
                max_ticks=self._plan.maximum_ticks,
            )
            run_loaded_typed_roster = _loaded_typed_roster(session)
            if (
                session.context.era_runtime_contract.selected_registry_id != effective_era_id
                or canonical_sha256(
                    session.context.era_config.model_dump(mode="json"),
                )
                != era_config_sha256
                or canonical_sha256(
                    session.context.era_runtime_contract.model_dump(mode="json"),
                )
                != era_runtime_contract_sha256
            ):
                raise RuntimeError("effective era identity changed during construction")

            self._failure_stage = "runtime_execution"
            result = session.run_to_completion()
            live_result = session.finalize()
            if (
                result.ticks_executed != live_result.ticks_executed
                or result.duration_s != live_result.duration_s
                or result.victory_result != live_result.victory_result
            ):
                raise RuntimeError(
                    "runtime result differs from the live production clock or terminal state",
                )
            if result.duration_s > self._plan.observation_boundary_s:
                raise RuntimeError("runtime exceeded the source-synchronous cutoff")
            if (
                result.victory_result.condition_type == "max_ticks"
                and result.duration_s != self._plan.observation_boundary_s
            ):
                raise RuntimeError("cutoff-censored runtime ended at the wrong time")
            self._failure_stage = "observation_extraction"
            runtime_provenance = session.provenance()
            receipts = tuple(
                _metric_receipt(
                    plan=metric,
                    session=session,
                    result=result,
                    effective_era_id=effective_era_id,
                    era_config_sha256=era_config_sha256,
                    era_runtime_contract_sha256=era_runtime_contract_sha256,
                )
                for metric in ordered_plans
            )
            natural_terminal = result.victory_result.condition_type != "max_ticks"
            terminal = TerminalOutcomeEvidence(
                seed=seed,
                ticks_executed=result.ticks_executed,
                duration_s=result.duration_s,
                winning_side=result.victory_result.winning_side,
                condition_type=result.victory_result.condition_type,
                game_over=result.victory_result.game_over,
                natural_terminal=natural_terminal,
                right_censored=not natural_terminal,
            )
            if any(receipt.terminal_outcome_sha256 != canonical_sha256(terminal) for receipt in receipts):
                raise RuntimeError("receipt terminal digest construction drifted")

            if loaded_roster is None:
                loaded_roster = session.loaded_roster
                batch_loaded_typed_roster = run_loaded_typed_roster
                static_provenance = runtime_provenance
            elif session.loaded_roster != loaded_roster:
                raise RuntimeError("loaded roster changed between held-out runs")
            elif run_loaded_typed_roster != batch_loaded_typed_roster:
                raise RuntimeError("loaded typed roster changed between held-out runs")
            elif static_provenance is None:
                raise RuntimeError("static provenance was not initialized")
            elif (
                runtime_provenance.code_revision != static_provenance.code_revision
                or runtime_provenance.data_revision != static_provenance.data_revision
                or runtime_provenance.data_file_count != static_provenance.data_file_count
                or runtime_provenance.catalog_revision != static_provenance.catalog_revision
                or runtime_provenance.doctrine_catalog_fingerprint != static_provenance.doctrine_catalog_fingerprint
                or runtime_provenance.loaded_roster_loadout_fingerprint
                != static_provenance.loaded_roster_loadout_fingerprint
                or runtime_provenance.initial_unit_assignments != static_provenance.initial_unit_assignments
            ):
                raise RuntimeError("static provenance changed between held-out runs")

            run_evidence = HistoricalRunEvidence(
                seed=seed,
                source_fingerprint=session.source_fingerprint,
                config_fingerprint=session.config_fingerprint,
                loaded_roster=session.loaded_roster,
                loaded_typed_roster=run_loaded_typed_roster,
                terminal_outcome=terminal,
                runtime_provenance=_runtime_provenance(runtime_provenance),
                receipts=receipts,
            )
            prepared.assert_source_identity(
                stage="after runtime execution and observation",
            )
            runs.append(run_evidence)
            self._completed_runs = tuple(runs)

        if loaded_roster is None or batch_loaded_typed_roster is None or static_provenance is None:
            raise RuntimeError("historical backtest produced no completed runs")
        self._failure_stage = "evaluation"
        metric_in_range = tuple(
            (
                metric.metric_id,
                tuple(run.receipts[index].in_source_range for run in runs),
            )
            for index, metric in enumerate(self._plan.gating_metrics)
        )
        evaluation = evaluate_joint_coverage(
            metric_in_range=metric_in_range,
            confidence=self._plan.acceptance_policy.confidence,
            minimum_joint_coverage=(self._plan.acceptance_policy.minimum_joint_coverage),
        )
        reasons: list[str] = []
        if not evaluation.passed:
            reasons.append("study_failed")
        if static_provenance.code_revision.dirty:
            reasons.append("dirty_revision")
        if self._plan.lineage.validation_source_relationship is SourceLineageRelationship.REUSED:
            reasons.append("validation_source_reused")
        elif self._plan.lineage.validation_source_relationship is SourceLineageRelationship.UNKNOWN:
            reasons.append("validation_source_lineage_unknown")
        if self._plan.artifact_policy.predeclaration_revision is None:
            reasons.append("plan_not_immutably_predeclared")
        elif self._plan.predeclaration_receipt is None:
            reasons.append("plan_predeclaration_not_repository_verified")

        self._failure_stage = "evidence_construction"
        execution = HistoricalExecutionEvidence(
            scenario_path=self._plan.scenario_path,
            data_root=self._plan.data_root,
            variant_id=variant.variant_id,
            ordered_metrics=ordered_metrics,
            seeds=self._plan.held_out_seeds,
            maximum_ticks=self._plan.maximum_ticks,
            observation_boundary_s=self._plan.observation_boundary_s,
            source_fingerprint=prepared.source_fingerprint,
            config_fingerprint=variant.config_fingerprint,
            authored_roster=prepared.authored_roster,
            authored_typed_roster=_authored_typed_roster(
                prepared.source_config,
            ),
            loaded_roster=loaded_roster,
            loaded_typed_roster=batch_loaded_typed_roster,
            code_revision=_code_revision(static_provenance.code_revision),
            data_revision=static_provenance.data_revision,
            data_file_count=static_provenance.data_file_count,
            catalog_revision=static_provenance.catalog_revision,
            doctrine_catalog_fingerprint=(static_provenance.doctrine_catalog_fingerprint),
            loaded_roster_loadout_fingerprint=(static_provenance.loaded_roster_loadout_fingerprint),
            initial_unit_assignments=tuple(
                UnitAssignmentEvidence.model_validate(asdict(assignment))
                for assignment in static_provenance.initial_unit_assignments
            ),
            effective_era_id=effective_era_id,
            era_config_sha256=era_config_sha256,
            era_runtime_contract_sha256=era_runtime_contract_sha256,
            predeclaration_receipt=self._plan.predeclaration_receipt,
            metric_vectors=tuple(
                (
                    metric_id,
                    tuple(run.receipts[index].value for run in runs),
                )
                for index, metric_id in enumerate(ordered_metrics)
            ),
            metric_statistics=tuple(
                (
                    metric_id,
                    _metric_statistics(
                        tuple(run.receipts[index].value for run in runs),
                    ),
                )
                for index, metric_id in enumerate(ordered_metrics)
            ),
            runs=tuple(runs),
        )
        prepared.assert_source_identity(
            stage="after historical evidence construction",
        )
        status: Literal["PASS", "FAIL"] = "PASS" if evaluation.passed else "FAIL"
        return HistoricalBacktestResult(
            status=status,
            plan_sha256=self._plan.plan_sha256,
            execution=execution,
            evaluation=evaluation,
            eligibility=HistoricalEligibility(
                promotion_eligible=not reasons,
                reason_codes=tuple(reasons),
            ),
        )
