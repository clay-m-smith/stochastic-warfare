"""Strict, predeclared historical backtest study plans."""

from __future__ import annotations

import io
import math
import subprocess
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, HttpUrl, PrivateAttr, TypeAdapter, field_validator, model_validator

from stochastic_warfare.entities.loader import load_effective_unit_loader
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)

from .common import (
    StrictFrozenModel,
    canonical_sha256,
    load_unique_mapping,
    require_no_symlink_path,
    require_relative_posix_path,
    require_stable_id,
    require_trimmed,
    resolve_repository_path,
)
from .evaluator import exact_binomial_lower_bound


_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_MAX_HELD_OUT_RUNS = 1_000


class SourceLineageRelationship(StrEnum):
    """Declared relationship between validation evidence and authored data."""

    INDEPENDENT = "independent"
    REUSED = "reused"
    UNKNOWN = "unknown"


class SeedInterval(StrictFrozenModel):
    """One inclusive, ordered seed interval."""

    first: int
    last: int

    @field_validator("first", "last", mode="before")
    @classmethod
    def _strict_seed(cls, value: Any, info: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{info.field_name} must be a non-negative strict integer")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> SeedInterval:
        if self.last < self.first:
            raise ValueError("seed interval last must be greater than or equal to first")
        return self

    @property
    def count(self) -> int:
        """Return interval cardinality without materializing its seeds."""
        return self.last - self.first + 1

    def first_overlap(self, other: SeedInterval) -> int | None:
        """Return the first shared seed, or ``None`` for disjoint intervals."""
        overlap = max(self.first, other.first)
        return overlap if overlap <= min(self.last, other.last) else None


class HistoricalSource(StrictFrozenModel):
    """One source and the exact assertion it supports."""

    source_id: str
    url: str
    citation: str
    quality: Literal["primary", "secondary", "tertiary"]
    locator: str
    accessed_on: date
    supported_assertion: str
    conflict_notes: tuple[str, ...]

    @field_validator(
        "source_id",
        "citation",
        "locator",
        "supported_assertion",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator("url", mode="before")
    @classmethod
    def _url(cls, value: Any) -> str:
        text = require_trimmed(value, field_name="url")
        try:
            _HTTP_URL_ADAPTER.validate_python(text)
        except ValueError as exc:
            raise ValueError("url must be a valid HTTP(S) URL") from exc
        return text

    @field_validator("conflict_notes", mode="before")
    @classmethod
    def _conflicts(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("conflict_notes must be an ordered list")
        return tuple(require_trimmed(note, field_name="conflict_notes entry") for note in value)


class SourceUse(StrictFrozenModel):
    """Disclosed use of one source in scenario authoring or calibration."""

    source_id: str
    usage: Literal[
        "scenario_metadata_authoring",
        "scenario_calibration",
        "diagnostic_only",
        "unknown",
    ]
    details: str

    @field_validator("source_id", "details", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)


class StudyLineage(StrictFrozenModel):
    """Complete declared source and RNG lineage for one study."""

    validation_source_relationship: SourceLineageRelationship
    source_uses: tuple[SourceUse, ...]
    training_seed_intervals: tuple[SeedInterval, ...]
    diagnostic_seed_intervals: tuple[SeedInterval, ...]
    notes: tuple[str, ...]

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("lineage notes must be a nonempty ordered list")
        return tuple(require_trimmed(note, field_name="lineage note") for note in value)

    @model_validator(mode="after")
    def _ordered_disjoint_intervals(self) -> StudyLineage:
        labelled = (
            ("training", self.training_seed_intervals),
            ("diagnostic", self.diagnostic_seed_intervals),
        )
        for label, intervals in labelled:
            ordered = tuple((item.first, item.last) for item in intervals)
            if ordered != tuple(sorted(ordered)):
                raise ValueError(f"{label} seed intervals must be ordered")
            for previous, current in zip(intervals, intervals[1:]):
                overlap = previous.first_overlap(current)
                if overlap is not None:
                    raise ValueError(
                        f"{label} seed intervals overlap at {overlap}",
                    )

        training_index = 0
        diagnostic_index = 0
        training = self.training_seed_intervals
        diagnostic = self.diagnostic_seed_intervals
        while training_index < len(training) and diagnostic_index < len(diagnostic):
            training_interval = training[training_index]
            diagnostic_interval = diagnostic[diagnostic_index]
            overlap = training_interval.first_overlap(diagnostic_interval)
            if overlap is not None:
                raise ValueError(
                    f"training and diagnostic seed intervals overlap at {overlap}",
                )
            if training_interval.last < diagnostic_interval.last:
                training_index += 1
            else:
                diagnostic_index += 1
        return self


class UnitConversion(StrictFrozenModel):
    """Explicit affine conversion from runtime to source units."""

    scale: float
    offset: float

    @field_validator("scale", "offset", mode="before")
    @classmethod
    def _finite(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be finite")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{info.field_name} must be finite")
        if info.field_name == "scale" and number == 0.0:
            raise ValueError("scale must be nonzero")
        return number


class ExtractorBase(StrictFrozenModel):
    """Fields common to every closed extractor definition."""

    event_boundary: Literal["source_synchronous_cutoff"]
    runtime_unit: str
    conversion: UnitConversion

    @field_validator("runtime_unit", mode="before")
    @classmethod
    def _runtime_unit(cls, value: Any) -> str:
        return require_trimmed(value, field_name="runtime_unit")


class TerminalSideDestroyedCountV1(ExtractorBase):
    """Count destroyed initial units in one exact typed side scope."""

    extractor_id: Literal["terminal_side_destroyed_count.v1"]
    side: str
    statuses: tuple[Literal["DESTROYED"], ...]
    included_unit_types: tuple[str, ...]
    roster_scope: Literal["initial_only"]

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> str:
        return require_trimmed(value, field_name="side")

    @field_validator("included_unit_types", mode="before")
    @classmethod
    def _unit_types(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("included_unit_types must be a nonempty ordered list")
        normalized = tuple(require_trimmed(item, field_name="included_unit_types entry") for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("included_unit_types must be duplicate-free")
        return normalized

    @model_validator(mode="after")
    def _one_status(self) -> TerminalSideDestroyedCountV1:
        if self.statuses != ("DESTROYED",):
            raise ValueError("destroyed-count statuses must be exactly [DESTROYED]")
        return self


class TerminalSideActiveCountV1(ExtractorBase):
    """Count active initial units in one exact typed side scope."""

    extractor_id: Literal["terminal_side_active_count.v1"]
    side: str
    statuses: tuple[Literal["ACTIVE"], ...]
    included_unit_types: tuple[str, ...]
    roster_scope: Literal["initial_only"]

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> str:
        return require_trimmed(value, field_name="side")

    @field_validator("included_unit_types", mode="before")
    @classmethod
    def _unit_types(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("included_unit_types must be a nonempty ordered list")
        normalized = tuple(require_trimmed(item, field_name="included_unit_types entry") for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("included_unit_types must be duplicate-free")
        return normalized

    @model_validator(mode="after")
    def _one_status(self) -> TerminalSideActiveCountV1:
        if self.statuses != ("ACTIVE",):
            raise ValueError("active-count statuses must be exactly [ACTIVE]")
        return self


class TimeToNaturalTerminalSecondsV1(ExtractorBase):
    """Observe public duration and flag cutoff-only completion as censored."""

    extractor_id: Literal["time_to_natural_terminal_seconds.v1"]


class TerminalWinnerIndicatorV1(ExtractorBase):
    """Observe one side's public terminal winner indicator."""

    extractor_id: Literal["terminal_winner_indicator.v1"]
    side: str

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> str:
        return require_trimmed(value, field_name="side")


class RatioComponent(StrictFrozenModel):
    """One explicit scoped status count used by an exchange ratio."""

    side: str
    status: Literal["ACTIVE", "DESTROYED"]
    included_unit_types: tuple[str, ...]

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> str:
        return require_trimmed(value, field_name="side")

    @field_validator("included_unit_types", mode="before")
    @classmethod
    def _unit_types(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("ratio included_unit_types must be nonempty")
        result = tuple(require_trimmed(item, field_name="ratio included unit type") for item in value)
        if len(result) != len(set(result)):
            raise ValueError("ratio included_unit_types must be duplicate-free")
        return result


class TerminalExchangeRatioV1(ExtractorBase):
    """Compute one explicit scoped terminal exchange ratio."""

    extractor_id: Literal["terminal_exchange_ratio.v1"]
    numerator: RatioComponent
    denominator: RatioComponent
    zero_denominator_rule: Literal["divide_by_one"]
    roster_scope: Literal["initial_only"]


ExtractorPlan = Annotated[
    TerminalSideDestroyedCountV1
    | TerminalSideActiveCountV1
    | TimeToNaturalTerminalSecondsV1
    | TerminalWinnerIndicatorV1
    | TerminalExchangeRatioV1,
    Field(discriminator="extractor_id"),
]


class SourceRange(StrictFrozenModel):
    """Inclusive source-backed range in the declared source unit."""

    minimum: float
    maximum: float

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def _finite(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be finite")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{info.field_name} must be finite")
        return number

    @model_validator(mode="after")
    def _ordered(self) -> SourceRange:
        if self.maximum < self.minimum:
            raise ValueError("source range maximum must not be below minimum")
        return self


class HistoricalMetricPlan(StrictFrozenModel):
    """One sourced metric and its closed production extractor."""

    metric_id: str
    name: str
    source_ids: tuple[str, ...]
    source_range: SourceRange
    source_unit: str
    source_event_boundary: str
    range_rationale: str
    extractor: ExtractorPlan

    @field_validator(
        "metric_id",
        "name",
        "source_unit",
        "source_event_boundary",
        "range_rationale",
        mode="before",
    )
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator("source_ids", mode="before")
    @classmethod
    def _source_ids(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("source_ids must be a nonempty ordered list")
        result = tuple(require_trimmed(item, field_name="source_ids entry") for item in value)
        if len(result) != len(set(result)):
            raise ValueError("source_ids must be duplicate-free")
        return result

    @model_validator(mode="after")
    def _compatible_units(self) -> HistoricalMetricPlan:
        extractor = self.extractor
        if isinstance(
            extractor,
            (TerminalSideDestroyedCountV1, TerminalSideActiveCountV1),
        ):
            allowed_runtime_units = {"entity_count", "vehicle_count"}
        elif isinstance(extractor, TimeToNaturalTerminalSecondsV1):
            allowed_runtime_units = {"seconds"}
        elif isinstance(extractor, TerminalWinnerIndicatorV1):
            allowed_runtime_units = {"indicator"}
        elif isinstance(extractor, TerminalExchangeRatioV1):
            allowed_runtime_units = {"ratio"}
        else:  # pragma: no cover - the discriminated union is closed above.
            raise ValueError(f"unsupported extractor {extractor!r}")
        if extractor.runtime_unit not in allowed_runtime_units:
            raise ValueError(
                f"extractor {extractor.extractor_id!r} has an unsupported runtime unit",
            )

        allowed_conversions = {
            ("seconds", "minutes"): (1.0 / 60.0, 0.0),
            ("ratio", "percent"): (100.0, 0.0),
        }
        expected_conversion = (
            (1.0, 0.0)
            if self.source_unit == extractor.runtime_unit
            else allowed_conversions.get(
                (extractor.runtime_unit, self.source_unit),
            )
        )
        actual_conversion = (
            extractor.conversion.scale,
            extractor.conversion.offset,
        )
        if expected_conversion is None or actual_conversion != expected_conversion:
            raise ValueError(
                "source/runtime units require an exact closed lossless conversion",
            )
        return self


class AcceptancePolicy(StrictFrozenModel):
    """Predeclared joint stochastic acceptance policy."""

    confidence: float
    minimum_joint_coverage: float

    @field_validator("confidence", "minimum_joint_coverage", mode="before")
    @classmethod
    def _probability(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be a finite probability")
        number = float(value)
        if not math.isfinite(number) or not 0.0 < number < 1.0:
            raise ValueError(f"{info.field_name} must be in (0, 1)")
        return number


class StudyAnalysis(StrictFrozenModel):
    """Factory-owned runtime variant; calibration changes are forbidden."""

    variant_id: str
    calibration_patch: dict[str, Any]

    @field_validator("variant_id", mode="before")
    @classmethod
    def _variant_id(cls, value: Any) -> str:
        return require_trimmed(value, field_name="variant_id")

    @field_validator("calibration_patch", mode="before")
    @classmethod
    def _empty_patch(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value:
            raise ValueError("historical studies require an empty calibration_patch")
        return {}


class PredeclarationReceipt(StrictFrozenModel):
    """Auditable repository proof that a study contract predates execution."""

    revision: str
    plan_repository_path: str
    contract_sha256: str

    @field_validator("revision", mode="before")
    @classmethod
    def _revision(cls, value: Any) -> str:
        text = require_trimmed(value, field_name="revision")
        if len(text) != 40 or any(character not in "0123456789abcdef" for character in text) or len(set(text)) == 1:
            raise ValueError("revision must be a non-sentinel lowercase 40-hex commit")
        return text

    @field_validator("plan_repository_path", mode="before")
    @classmethod
    def _path(cls, value: Any) -> str:
        return require_relative_posix_path(
            value,
            field_name="plan_repository_path",
        )

    @field_validator("contract_sha256", mode="before")
    @classmethod
    def _digest(cls, value: Any) -> str:
        text = require_trimmed(value, field_name="contract_sha256")
        if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
            raise ValueError("contract_sha256 must be a lowercase SHA-256 digest")
        return text


class ArtifactPolicy(StrictFrozenModel):
    """Promotion requirements that remain distinct from PASS/FAIL."""

    clean_revision_required_for_promotion: Literal[True]
    immutable_predeclaration_required_for_promotion: Literal[True]
    predeclaration_revision: str | None

    @field_validator(
        "clean_revision_required_for_promotion",
        "immutable_predeclaration_required_for_promotion",
        mode="before",
    )
    @classmethod
    def _required_true(cls, value: Any, info: Any) -> bool:
        if type(value) is not bool or value is not True:
            raise ValueError(f"{info.field_name} must be the strict boolean true")
        return value

    @field_validator("predeclaration_revision", mode="before")
    @classmethod
    def _revision(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = require_trimmed(value, field_name="predeclaration_revision")
        if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
            raise ValueError("predeclaration_revision must be a lowercase 40-hex commit")
        if len(set(text)) == 1:
            raise ValueError("predeclaration_revision must not be a sentinel digest")
        return text


class HistoricalStudyPlan(StrictFrozenModel):
    """Complete source, lineage, runtime, metric, and acceptance declaration."""

    schema_version: Literal[1]
    study_id: str
    plan_repository_path: str
    claim_ids: tuple[str, ...]
    scenario_path: str
    data_root: str
    intended_use: str
    limitations: tuple[str, ...]
    sources: tuple[HistoricalSource, ...]
    lineage: StudyLineage
    held_out_seed_interval: SeedInterval
    observation_boundary_s: float
    maximum_ticks: int
    analysis: StudyAnalysis
    acceptance_policy: AcceptancePolicy
    gating_metrics: tuple[HistoricalMetricPlan, ...]
    diagnostic_metrics: tuple[HistoricalMetricPlan, ...]
    artifact_policy: ArtifactPolicy

    _predeclaration_receipt: PredeclarationReceipt | None = PrivateAttr(
        default=None,
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be the strict integer 1")
        return value

    @field_validator("study_id", mode="before")
    @classmethod
    def _study_id(cls, value: Any, info: Any) -> str:
        return require_stable_id(value, field_name=info.field_name)

    @field_validator("intended_use", mode="before")
    @classmethod
    def _text(cls, value: Any, info: Any) -> str:
        return require_trimmed(value, field_name=info.field_name)

    @field_validator("claim_ids", mode="before")
    @classmethod
    def _claim_ids(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("claim_ids must be a nonempty ordered list")
        result = tuple(require_stable_id(item, field_name="claim ID") for item in value)
        if len(result) != len(set(result)):
            raise ValueError("claim_ids must be duplicate-free")
        return result

    @field_validator(
        "plan_repository_path",
        "scenario_path",
        "data_root",
        mode="before",
    )
    @classmethod
    def _path(cls, value: Any, info: Any) -> str:
        return require_relative_posix_path(value, field_name=info.field_name)

    @field_validator("limitations", mode="before")
    @classmethod
    def _limitations(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("limitations must be a nonempty ordered list")
        return tuple(require_trimmed(item, field_name="limitation") for item in value)

    @field_validator("observation_boundary_s", mode="before")
    @classmethod
    def _boundary(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("observation_boundary_s must be finite and positive")
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError("observation_boundary_s must be finite and positive")
        return number

    @field_validator("maximum_ticks", mode="before")
    @classmethod
    def _maximum_ticks(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("maximum_ticks must be a positive strict integer")
        return value

    @model_validator(mode="after")
    def _semantic_contract(self) -> HistoricalStudyPlan:
        source_ids = [source.source_id for source in self.sources]
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise ValueError("sources must be nonempty with unique source IDs")
        source_id_set = set(source_ids)
        use_ids = [use.source_id for use in self.lineage.source_uses]
        if len(use_ids) != len(set(use_ids)) or set(use_ids) != source_id_set:
            raise ValueError(
                "source_uses must uniquely and completely reference declared sources",
            )
        usages = {source_use.usage for source_use in self.lineage.source_uses}
        expected_relationship = (
            SourceLineageRelationship.UNKNOWN
            if "unknown" in usages
            else (
                SourceLineageRelationship.REUSED
                if usages.intersection(
                    {"scenario_metadata_authoring", "scenario_calibration"},
                )
                else SourceLineageRelationship.INDEPENDENT
            )
        )
        if self.lineage.validation_source_relationship is not expected_relationship:
            raise ValueError(
                "validation_source_relationship contradicts the complete source uses",
            )

        all_metrics = self.gating_metrics + self.diagnostic_metrics
        if not self.gating_metrics:
            raise ValueError("gating_metrics must be nonempty")
        metric_ids = [metric.metric_id for metric in all_metrics]
        metric_names = [metric.name for metric in all_metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("metric IDs must be duplicate-free")
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("metric names must be duplicate-free")
        for metric in all_metrics:
            if not set(metric.source_ids) <= source_id_set:
                raise ValueError(
                    f"metric {metric.metric_id!r} references an unknown source",
                )
            if isinstance(metric.extractor, TimeToNaturalTerminalSecondsV1):
                conversion = metric.extractor.conversion
                source_start = conversion.offset
                source_boundary = self.observation_boundary_s * conversion.scale + conversion.offset
                reachable_minimum, reachable_maximum = sorted(
                    (source_start, source_boundary),
                )
                if not (reachable_minimum <= metric.source_range.minimum <= reachable_maximum):
                    raise ValueError(
                        f"duration metric {metric.metric_id!r} has no reachable "
                        "value at the study observation boundary",
                    )
            if isinstance(metric.extractor, TerminalWinnerIndicatorV1) and (
                metric.source_range.minimum < 0.0 or metric.source_range.maximum > 1.0
            ):
                raise ValueError(
                    f"winner metric {metric.metric_id!r} must remain within [0, 1]",
                )
        if all(metric.extractor.extractor_id == "terminal_winner_indicator.v1" for metric in self.gating_metrics):
            raise ValueError("winner-only gating is not historical outcome evidence")

        held_out_count = self.held_out_seed_interval.count
        if held_out_count > _MAX_HELD_OUT_RUNS:
            raise ValueError(
                f"held-out seed interval exceeds the maximum of {_MAX_HELD_OUT_RUNS} production runs",
            )
        for interval in self.lineage.training_seed_intervals + self.lineage.diagnostic_seed_intervals:
            overlap = self.held_out_seed_interval.first_overlap(interval)
            if overlap is not None:
                raise ValueError(
                    f"held-out seed interval overlaps prior seeds at {overlap}",
                )
        best_bound = exact_binomial_lower_bound(
            held_out_count,
            held_out_count,
            confidence=self.acceptance_policy.confidence,
        )
        if best_bound < self.acceptance_policy.minimum_joint_coverage:
            raise ValueError(
                "held-out sample cannot reach the declared joint coverage policy",
            )
        return self

    @property
    def held_out_seeds(self) -> tuple[int, ...]:
        return tuple(
            range(
                self.held_out_seed_interval.first,
                self.held_out_seed_interval.last + 1,
            ),
        )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self)

    @property
    def promotion_eligible(self) -> bool:
        return (
            self.lineage.validation_source_relationship is SourceLineageRelationship.INDEPENDENT
            and self.artifact_policy.predeclaration_revision is not None
            and self._predeclaration_receipt is not None
        )

    @property
    def predeclaration_receipt(self) -> PredeclarationReceipt | None:
        """Return repository verification evidence, never declaration alone."""
        return self._predeclaration_receipt


def validate_historical_runtime_scope(
    plan: HistoricalStudyPlan,
    config: CampaignScenarioConfig,
    *,
    data_root: Path,
) -> None:
    """Bind every extractor scope to the exact effective production catalog."""
    root = Path(data_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("data_root must identify a directory")
    unit_definitions = load_effective_unit_loader(
        root,
        config.era,
    ).definitions()
    sides = {side.side: side for side in config.sides}
    all_metrics = plan.gating_metrics + plan.diagnostic_metrics
    if len({metric.source_event_boundary for metric in all_metrics}) != 1:
        raise ValueError(
            "all study metrics must share one source event boundary",
        )
    for metric in all_metrics:
        extractor = metric.extractor
        scoped_components: tuple[Any, ...]
        if isinstance(
            extractor,
            (TerminalSideDestroyedCountV1, TerminalSideActiveCountV1),
        ):
            scoped_components = (extractor,)
        elif isinstance(extractor, TerminalWinnerIndicatorV1):
            if extractor.side not in sides:
                raise ValueError(
                    f"metric {metric.metric_id!r} names unknown side {extractor.side!r}",
                )
            continue
        elif isinstance(extractor, TerminalExchangeRatioV1):
            numerator_scope = {
                (extractor.numerator.side, unit_type) for unit_type in extractor.numerator.included_unit_types
            }
            denominator_scope = {
                (extractor.denominator.side, unit_type) for unit_type in extractor.denominator.included_unit_types
            }
            if numerator_scope.intersection(denominator_scope):
                raise ValueError(
                    f"metric {metric.metric_id!r} ratio scopes must be disjoint",
                )
            scoped_components = (
                extractor.numerator,
                extractor.denominator,
            )
        else:
            continue
        for component in scoped_components:
            side = sides.get(component.side)
            if side is None:
                raise ValueError(
                    f"metric {metric.metric_id!r} names unknown side {component.side!r}",
                )
            authored_types = tuple(
                dict.fromkeys(unit.unit_type for unit in side.units),
            )
            if not all(unit_type in authored_types for unit_type in component.included_unit_types):
                raise ValueError(
                    f"metric {metric.metric_id!r} names an unauthored unit type",
                )
            ordered_scope = tuple(
                unit_type for unit_type in authored_types if unit_type in component.included_unit_types
            )
            if ordered_scope != component.included_unit_types:
                raise ValueError(
                    f"metric {metric.metric_id!r} unit types must follow authored order",
                )
            scoped_definitions = []
            for unit_type in component.included_unit_types:
                definition = unit_definitions.get(unit_type)
                if definition is None:
                    raise ValueError(
                        f"metric {metric.metric_id!r} unit type {unit_type!r} has no effective definition",
                    )
                scoped_definitions.append(definition)
            scoped_count = sum(unit.count for unit in side.units if unit.unit_type in component.included_unit_types)
            if scoped_count <= 0:
                raise ValueError(
                    f"metric {metric.metric_id!r} has an empty authored unit scope",
                )
            if extractor.runtime_unit == "vehicle_count":
                vehicle_ground_types = {
                    "ARMOR",
                    "MECHANIZED_INFANTRY",
                    "MOTORIZED",
                    "ARTILLERY_SP",
                    "ROCKET_ARTILLERY",
                    "RECON",
                }
                for unit_type, definition in zip(
                    component.included_unit_types,
                    scoped_definitions,
                    strict=True,
                ):
                    if (
                        definition.domain != "ground"
                        or definition.ground_type not in vehicle_ground_types
                        or not any(item.category == "PROPULSION" for item in definition.equipment)
                    ):
                        raise ValueError(
                            f"metric {metric.metric_id!r} vehicle_count includes non-vehicle unit type {unit_type!r}",
                        )
            if isinstance(
                extractor,
                (TerminalSideDestroyedCountV1, TerminalSideActiveCountV1),
            ):
                bounds = (
                    metric.source_range.minimum,
                    metric.source_range.maximum,
                )
                if any(not bound.is_integer() for bound in bounds) or bounds[0] < 0.0 or bounds[1] > scoped_count:
                    raise ValueError(
                        f"metric {metric.metric_id!r} count range is outside its exact initial typed scope",
                    )

    cadence = config.tick_duration_seconds
    if cadence is None:
        if plan.maximum_ticks != 1 or plan.observation_boundary_s != config.tick_resolution.tactical_s:
            raise ValueError(
                "multi-resolution studies are limited to one exact tactical tick",
            )
        return
    exact_ticks = plan.observation_boundary_s / cadence
    if not exact_ticks.is_integer() or int(exact_ticks) != plan.maximum_ticks:
        raise ValueError(
            "observation boundary must align exactly with maximum_ticks and the uniform scenario cadence",
        )


def predeclaration_contract_sha256(plan: HistoricalStudyPlan) -> str:
    """Digest the immutable study contract independent of later binding metadata."""
    contract = plan.model_dump(mode="json", exclude_none=False)
    contract["artifact_policy"]["predeclaration_revision"] = None
    return canonical_sha256(contract)


class HistoricalStudyLoader:
    """Load and semantically bind a strict study to the current repository."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve(strict=True)

    def load(self, path: Path) -> HistoricalStudyPlan:
        """Load one plan and verify its exact source roster and cutoff."""
        require_no_symlink_path(path, field_name="historical study plan path")
        resolved_plan = path.resolve(strict=True)
        if not resolved_plan.is_relative_to(self._repository_root):
            raise ValueError("study plan must reside within the repository")
        plan = HistoricalStudyPlan.model_validate(
            load_unique_mapping(resolved_plan),
        )
        declared_plan = resolve_repository_path(
            self._repository_root,
            plan.plan_repository_path,
            field_name="plan_repository_path",
        ).resolve(strict=True)
        if declared_plan != resolved_plan:
            raise ValueError("plan_repository_path differs from the loaded study")
        scenario_path = resolve_repository_path(
            self._repository_root,
            plan.scenario_path,
            field_name="scenario_path",
        )
        data_root = resolve_repository_path(
            self._repository_root,
            f"{plan.data_root}/.validation-anchor",
            field_name="data_root",
            require_file=False,
        ).parent
        if not data_root.is_dir():
            raise ValueError("data_root must identify a repository directory")

        config = load_campaign_scenario_config(scenario_path)
        validate_historical_runtime_scope(
            plan,
            config,
            data_root=data_root,
        )
        if plan.artifact_policy.predeclaration_revision is not None:
            self._verify_predeclaration(plan, plan_path=resolved_plan)
        return plan

    def _verify_predeclaration(
        self,
        plan: HistoricalStudyPlan,
        *,
        plan_path: Path,
    ) -> None:
        revision = plan.artifact_policy.predeclaration_revision
        if revision is None:  # pragma: no cover - guarded by the caller.
            raise ValueError("predeclaration revision is missing")
        relative_plan = plan_path.relative_to(self._repository_root).as_posix()
        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "merge-base",
                    "--is-ancestor",
                    revision,
                    "HEAD",
                ],
                check=True,
                capture_output=True,
            )
            committed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._repository_root),
                    "show",
                    f"{revision}:{relative_plan}",
                ],
                check=True,
                capture_output=True,
            ).stdout.decode("utf-8")
        except (
            OSError,
            subprocess.CalledProcessError,
            UnicodeDecodeError,
        ) as exc:
            raise ValueError(
                "predeclaration_revision must identify an ancestor containing the plan",
            ) from exc

        from stochastic_warfare.core.strict_yaml import load_yaml_unique

        predeclared_raw = load_yaml_unique(io.StringIO(committed))
        if not isinstance(predeclared_raw, dict):
            raise ValueError("predeclared study must contain one YAML mapping")
        predeclared = HistoricalStudyPlan.model_validate(predeclared_raw)
        current_digest = predeclaration_contract_sha256(plan)
        committed_digest = predeclaration_contract_sha256(predeclared)
        if current_digest != committed_digest:
            raise ValueError("study contract differs from its predeclared revision")
        object.__setattr__(
            plan,
            "_predeclaration_receipt",
            PredeclarationReceipt(
                revision=revision,
                plan_repository_path=relative_plan,
                contract_sha256=current_digest,
            ),
        )
