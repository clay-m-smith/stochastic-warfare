"""Typed performance-flag classifications and observational receipts.

The models in this module are deliberately observational.  They describe work
that a production owner has already admitted or completed; they do not select
targets, schedule sensors, dispatch tasks, or consume randomness.

Receipt state is a closed, JSON-compatible topology.  Side-cycle and committed
execution receipts validate their accounting equations at construction and on
restore.  :class:`PerformanceReceiptDelta` is intentionally different: it is
an immutable transaction contribution and is not valid evidence until its
complete transaction has been reconciled by
:class:`PerformanceReceiptAccumulator`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from stochastic_warfare.core.performance_receipts import (
    DispatchReceipt,
    FOWCadenceReceipt,
    FOWCadenceRecoveryPeriodReceipt,
    FOWDetectionReceipt,
    FOWFusionReceipt,
    FOWIndexedRNGReceipt,
    FOWReceipt,
    FOWScanReceipt,
    FOWSelectionReceipt,
    FogOfWarCycleReceipt,
    LODDetectionReceipt,
    LODEngagementReceipt,
    LODMoraleReceipt,
    LODMovementReceipt,
    LODReceipt,
    NonNegativeInt,
    PerformanceReceiptDelta,
    PositiveInt,
    SoAReceipt,
    _StrictFrozenModel,
)


PERFORMANCE_RECEIPT_SCHEMA_VERSION = 2
DEFAULT_TACTICAL_INTERVAL_MICROSECONDS = 5_000_000
PERFORMANCE_SEMANTIC_EVIDENCE_PLAN_ID = "phase118-performance-semantics-v7"
PERFORMANCE_SEMANTIC_EVIDENCE_MANIFEST_SHA256 = (
    "bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86"
)
LOD_RUNTIME_COMPATIBILITY_DEFAULTS = MappingProxyType(
    {
        "lod_nearby_interval": 5,
        "lod_distant_interval": 20,
        "lod_hysteresis_ticks": 3,
    },
)


class GovernedPerformanceFlag(str, Enum):
    """The five controls governed by the Phase 118 semantic contract."""

    DETECTION_CULLING = "enable_detection_culling"
    SCAN_SCHEDULING = "enable_scan_scheduling"
    LOD = "enable_lod"
    SOA = "enable_soa"
    PARALLEL_DETECTION = "enable_parallel_detection"


class PerformanceFlagClassification(str, Enum):
    """Predeclared semantic classification of one governed flag."""

    SEMANTICS_PRESERVING_EXECUTION_OPTIMIZATION = "semantics_preserving_execution_optimization"
    MODEL_FIDELITY_APPROXIMATION = "model_fidelity_approximation"


class PerformanceFlagSupportDisposition(str, Enum):
    """Production support status established by retained semantic evidence."""

    SUPPORTED_EXACT_VALIDATED = "supported_exact_validated"
    UNSUPPORTED_FAILED_SEMANTIC_VALIDATION = (
        "unsupported_failed_semantic_validation"
    )


class RetainedSemanticVerdict(str, Enum):
    """Terminal per-flag verdict from the retained v7 evidence."""

    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class PerformanceFlagDefinition:
    """Immutable classification and contract summary for one flag."""

    flag: GovernedPerformanceFlag
    classification: PerformanceFlagClassification
    support_disposition: PerformanceFlagSupportDisposition
    retained_v7_verdict: RetainedSemanticVerdict
    required_meaning: str

    def __post_init__(self) -> None:
        if type(self.flag) is not GovernedPerformanceFlag:
            raise TypeError("performance flag must be GovernedPerformanceFlag")
        if type(self.classification) is not PerformanceFlagClassification:
            raise TypeError(
                "performance flag classification must be "
                "PerformanceFlagClassification",
            )
        if type(self.support_disposition) is not PerformanceFlagSupportDisposition:
            raise TypeError(
                "performance flag support_disposition must be "
                "PerformanceFlagSupportDisposition",
            )
        if type(self.retained_v7_verdict) is not RetainedSemanticVerdict:
            raise TypeError(
                "performance flag retained_v7_verdict must be "
                "RetainedSemanticVerdict",
            )
        if type(self.required_meaning) is not str or not self.required_meaning.strip():
            raise ValueError("performance flag required_meaning must be non-empty")
        if self.required_meaning != self.required_meaning.strip():
            raise ValueError("performance flag required_meaning must be trimmed")


PERFORMANCE_FLAG_ORDER: tuple[str, ...] = tuple(flag.value for flag in GovernedPerformanceFlag)


def _build_performance_flag_registry() -> MappingProxyType[str, PerformanceFlagDefinition]:
    definitions = {
        GovernedPerformanceFlag.DETECTION_CULLING.value: PerformanceFlagDefinition(
            flag=GovernedPerformanceFlag.DETECTION_CULLING,
            classification=(PerformanceFlagClassification.SEMANTICS_PRESERVING_EXECUTION_OPTIMIZATION),
            support_disposition=(
                PerformanceFlagSupportDisposition.SUPPORTED_EXACT_VALIDATED
            ),
            retained_v7_verdict=RetainedSemanticVerdict.PASS,
            required_meaning=(
                "Conservative target culling may omit only checks rejected before mutable scan state or RNG."
            ),
        ),
        GovernedPerformanceFlag.SCAN_SCHEDULING.value: PerformanceFlagDefinition(
            flag=GovernedPerformanceFlag.SCAN_SCHEDULING,
            classification=PerformanceFlagClassification.MODEL_FIDELITY_APPROXIMATION,
            support_disposition=(
                PerformanceFlagSupportDisposition.UNSUPPORTED_FAILED_SEMANTIC_VALIDATION
            ),
            retained_v7_verdict=RetainedSemanticVerdict.FAIL,
            required_meaning=("Authored sensor intervals intentionally omit off-interval detection opportunities."),
        ),
        GovernedPerformanceFlag.LOD.value: PerformanceFlagDefinition(
            flag=GovernedPerformanceFlag.LOD,
            classification=PerformanceFlagClassification.MODEL_FIDELITY_APPROXIMATION,
            support_disposition=(
                PerformanceFlagSupportDisposition.UNSUPPORTED_FAILED_SEMANTIC_VALIDATION
            ),
            retained_v7_verdict=RetainedSemanticVerdict.FAIL,
            required_meaning=(
                "LOD changes sensing cadence only; engagement, morale, movement, and damage remain full-rate."
            ),
        ),
        GovernedPerformanceFlag.SOA.value: PerformanceFlagDefinition(
            flag=GovernedPerformanceFlag.SOA,
            classification=(PerformanceFlagClassification.SEMANTICS_PRESERVING_EXECUTION_OPTIMIZATION),
            support_disposition=(
                PerformanceFlagSupportDisposition.SUPPORTED_EXACT_VALIDATED
            ),
            retained_v7_verdict=RetainedSemanticVerdict.PASS,
            required_meaning=(
                "Read-only array selection preserves authoritative state, target order, and admitted work."
            ),
        ),
        GovernedPerformanceFlag.PARALLEL_DETECTION.value: PerformanceFlagDefinition(
            flag=GovernedPerformanceFlag.PARALLEL_DETECTION,
            classification=(PerformanceFlagClassification.SEMANTICS_PRESERVING_EXECUTION_OPTIMIZATION),
            support_disposition=(
                PerformanceFlagSupportDisposition.SUPPORTED_EXACT_VALIDATED
            ),
            retained_v7_verdict=RetainedSemanticVerdict.PASS,
            required_meaning=("Only dispatch may differ; state, event order, RNG, and continuation remain identical."),
        ),
    }
    return MappingProxyType(definitions)


PERFORMANCE_FLAG_REGISTRY = _build_performance_flag_registry()

if tuple(PERFORMANCE_FLAG_REGISTRY) != PERFORMANCE_FLAG_ORDER:
    raise RuntimeError("performance flag registry is not in canonical order")
if len(PERFORMANCE_FLAG_REGISTRY) != len(GovernedPerformanceFlag):
    raise RuntimeError("performance flag registry is incomplete")


class EffectivePerformanceFlags(_StrictFrozenModel):
    """Exact effective values of every governed performance flag."""

    enable_detection_culling: bool
    enable_scan_scheduling: bool
    enable_lod: bool
    enable_soa: bool
    enable_parallel_detection: bool

    @classmethod
    def all_disabled(cls) -> EffectivePerformanceFlags:
        """Return the canonical all-disabled control configuration."""
        return cls(
            enable_detection_culling=False,
            enable_scan_scheduling=False,
            enable_lod=False,
            enable_soa=False,
            enable_parallel_detection=False,
        )

    def canonical_items(self) -> tuple[tuple[str, bool], ...]:
        """Return values in the immutable registry order."""
        return tuple((name, getattr(self, name)) for name in PERFORMANCE_FLAG_ORDER)


class _PerformanceConfigurationAccessor(Protocol):
    """Minimal typed view shared by calibration and runtime contexts."""

    def get(self, key: str, default: Any = None) -> Any:
        """Return one effective configuration value."""


class UnsupportedPerformanceConfigurationError(ValueError):
    """An enabled production configuration lacks accepted semantic support."""


def resolve_supported_runtime_performance_flags(
    configuration: EffectivePerformanceFlags | _PerformanceConfigurationAccessor,
) -> EffectivePerformanceFlags:
    """Resolve governed flags and reject unsupported production semantics.

    Historical receipts remain independently decodable through
    :class:`EffectivePerformanceFlags`; only this live-runtime boundary applies
    the retained v7 support disposition.
    """
    if type(configuration) is EffectivePerformanceFlags:
        flags = configuration
        nondefault_lod_fields: list[str] = []
    else:
        get_value = getattr(configuration, "get", None)
        if not callable(get_value):
            raise TypeError(
                "performance configuration must be EffectivePerformanceFlags "
                "or provide get(key, default)",
            )
        flags = EffectivePerformanceFlags(
            enable_detection_culling=get_value(
                "enable_detection_culling",
                True,
            ),
            enable_scan_scheduling=get_value(
                "enable_scan_scheduling",
                False,
            ),
            enable_lod=get_value("enable_lod", False),
            enable_soa=get_value("enable_soa", False),
            enable_parallel_detection=get_value(
                "enable_parallel_detection",
                False,
            ),
        )
        nondefault_lod_fields = []
        for field_name, expected in LOD_RUNTIME_COMPATIBILITY_DEFAULTS.items():
            value = get_value(field_name, expected)
            if type(value) is not int or value != expected:
                nondefault_lod_fields.append(
                    f"{field_name}={value!r} (expected {expected})",
                )

    unsupported_enabled = [
        field_name
        for field_name, enabled in flags.canonical_items()
        if enabled
        and PERFORMANCE_FLAG_REGISTRY[field_name].support_disposition
        is PerformanceFlagSupportDisposition.UNSUPPORTED_FAILED_SEMANTIC_VALIDATION
    ]
    if unsupported_enabled or nondefault_lod_fields:
        raise UnsupportedPerformanceConfigurationError(
            "unsupported production performance configuration after failed "
            "semantic validation: "
            f"enabled_flags={unsupported_enabled!r}; "
            f"nondefault_lod_fields={nondefault_lod_fields!r}",
        )
    return flags


def resolve_cross_bound_runtime_performance_flags(
    *,
    authored_configuration: EffectivePerformanceFlags | _PerformanceConfigurationAccessor,
    typed_calibration: EffectivePerformanceFlags | _PerformanceConfigurationAccessor,
    flat_calibration: EffectivePerformanceFlags | _PerformanceConfigurationAccessor,
) -> EffectivePerformanceFlags:
    """Resolve and cross-bind the three live calibration representations."""
    authored_flags = resolve_supported_runtime_performance_flags(
        authored_configuration,
    )
    typed_flags = resolve_supported_runtime_performance_flags(
        typed_calibration,
    )
    if authored_flags != typed_flags:
        raise RuntimeError(
            "Authored runtime configuration diverged from the typed "
            "performance calibration",
        )
    flat_flags = resolve_supported_runtime_performance_flags(
        flat_calibration,
    )
    if flat_flags != typed_flags:
        raise RuntimeError(
            "Flat performance calibration diverged from the typed runtime calibration",
        )
    return typed_flags


def validate_supported_runtime_performance_parameter_name(
    parameter_name: str,
) -> str:
    """Reject retired governed controls at sensitivity-analysis boundaries."""
    if type(parameter_name) is not str or not parameter_name or parameter_name != parameter_name.strip():
        raise ValueError(
            "performance parameter_name must be a non-empty trimmed string",
        )
    definition = PERFORMANCE_FLAG_REGISTRY.get(parameter_name)
    if (
        definition is not None
        and definition.support_disposition
        is PerformanceFlagSupportDisposition.UNSUPPORTED_FAILED_SEMANTIC_VALIDATION
    ) or parameter_name in LOD_RUNTIME_COMPATIBILITY_DEFAULTS:
        raise UnsupportedPerformanceConfigurationError(
            "unsupported production sensitivity parameter after failed "
            f"semantic validation: {parameter_name!r}",
        )
    return parameter_name


class PerformanceExecutionReceipt(_StrictFrozenModel):
    """Committed monotonic receipt with an exact persisted topology."""

    schema_version: Literal[2] = PERFORMANCE_RECEIPT_SCHEMA_VERSION
    complete_from_tick_zero: bool
    effective_flags: EffectivePerformanceFlags
    tactical_interval_microseconds: PositiveInt = DEFAULT_TACTICAL_INTERVAL_MICROSECONDS
    tactical_intervals: NonNegativeInt = 0
    tactical_duration_microseconds: NonNegativeInt = 0
    fow: FOWReceipt = Field(default_factory=FOWReceipt)
    dispatch: DispatchReceipt = Field(default_factory=DispatchReceipt)
    soa: SoAReceipt = Field(default_factory=SoAReceipt)
    lod: LODReceipt = Field(default_factory=LODReceipt)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version(cls, value: object) -> int:
        if type(value) is not int or value != PERFORMANCE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be the strict integer {PERFORMANCE_RECEIPT_SCHEMA_VERSION}",
            )
        return value

    @model_validator(mode="after")
    def _closed_topology(self) -> PerformanceExecutionReceipt:
        expected_duration = self.tactical_intervals * self.tactical_interval_microseconds
        if self.tactical_duration_microseconds != expected_duration:
            raise ValueError(
                "tactical_duration_microseconds must equal tactical_intervals times tactical_interval_microseconds",
            )
        dispatch_intervals = self.dispatch.sequential_intervals + self.dispatch.parallel_intervals
        if dispatch_intervals != self.tactical_intervals:
            raise ValueError(
                "dispatch intervals must partition tactical_intervals",
            )
        dispatched_side_cycles = self.dispatch.sequential_side_updates + self.dispatch.parallel_tasks_joined
        if dispatched_side_cycles != self.fow.side_cycles:
            raise ValueError(
                "sequential side updates plus joined parallel tasks must equal FOW side_cycles",
            )
        if self.lod.detection.admitted != self.fow.cadence.admitted:
            raise ValueError(
                "LOD tier admissions must equal cumulative cadence admissions",
            )
        if self.lod.detection.deferred != self.fow.cadence.deferred:
            raise ValueError(
                "LOD tier deferrals must equal cumulative cadence deferrals",
            )
        native_recoveries = sum(
            bucket.recovery_admissions
            for bucket in self.fow.cadence.native_recoveries_by_period
        )
        if native_recoveries > (
            self.fow.cadence.deferred_native
            + self.fow.cadence.deferred_both
        ):
            raise ValueError(
                "cumulative native cadence recoveries cannot exceed native deferrals",
            )
        lod_recoveries = sum(
            bucket.recovery_admissions
            for bucket in self.fow.cadence.lod_recoveries_by_period
        )
        if lod_recoveries > (
            self.fow.cadence.deferred_lod
            + self.fow.cadence.deferred_both
        ):
            raise ValueError(
                "cumulative LOD cadence recoveries cannot exceed LOD deferrals",
            )

        selection = self.fow.selection
        flags = self.effective_flags
        strtree_counts = (
            selection.strtree_builds,
            selection.strtree_queries,
            selection.strtree_admitted_targets,
            selection.strtree_pruned_targets,
        )
        soa_selection_counts = (
            selection.soa_vector_builds,
            selection.soa_vector_queries,
            selection.soa_vector_admitted_targets,
            selection.soa_vector_pruned_targets,
        )
        soa_snapshot_counts = (
            self.soa.pre_movement_builds,
            self.soa.pre_movement_enemy_position_projections,
            self.soa.post_movement_builds,
            self.soa.post_movement_enemy_position_projections,
        )
        parallel_counts = (
            self.dispatch.parallel_intervals,
            self.dispatch.parallel_tasks_submitted,
            self.dispatch.parallel_tasks_joined,
        )
        if not flags.enable_detection_culling and any(strtree_counts):
            raise ValueError(
                "STRtree receipt work requires enable_detection_culling",
            )
        if flags.enable_detection_culling and any(soa_selection_counts):
            raise ValueError(
                "SoA target selection is incompatible with enabled detection culling",
            )
        if not flags.enable_scan_scheduling and (
            self.fow.cadence.deferred_native != 0
            or self.fow.cadence.deferred_both != 0
            or self.fow.cadence.native_recoveries_by_period
        ):
            raise ValueError(
                "native cadence deferrals or recoveries require enable_scan_scheduling",
            )
        if not flags.enable_lod and (
            self.lod.nearby_classifications != 0
            or self.lod.distant_classifications != 0
            or self.lod.detection.nearby_attachments_admitted != 0
            or self.lod.detection.nearby_attachments_deferred != 0
            or self.lod.detection.distant_attachments_admitted != 0
            or self.lod.detection.distant_attachments_deferred != 0
            or self.fow.cadence.deferred_lod != 0
            or self.fow.cadence.deferred_both != 0
            or self.fow.cadence.lod_recoveries_by_period
            or self.lod.movement.nearby_processed != 0
            or self.lod.movement.distant_processed != 0
        ):
            raise ValueError(
                "non-ACTIVE LOD work or LOD deferral requires enable_lod",
            )
        if not flags.enable_soa and (any(soa_selection_counts) or any(soa_snapshot_counts)):
            raise ValueError("SoA receipt work requires enable_soa")
        if not flags.enable_parallel_detection and any(parallel_counts):
            raise ValueError(
                "parallel dispatch work requires enable_parallel_detection",
            )
        return self

    @classmethod
    def zero(
        cls,
        *,
        effective_flags: EffectivePerformanceFlags,
        tactical_interval_microseconds: int = DEFAULT_TACTICAL_INTERVAL_MICROSECONDS,
        complete_from_tick_zero: bool = True,
    ) -> PerformanceExecutionReceipt:
        """Construct a validated zero receipt for a fresh or legacy owner."""
        if type(effective_flags) is not EffectivePerformanceFlags:
            raise TypeError("effective_flags must be EffectivePerformanceFlags")
        if type(complete_from_tick_zero) is not bool:
            raise TypeError("complete_from_tick_zero must be a boolean")
        return cls(
            complete_from_tick_zero=complete_from_tick_zero,
            effective_flags=effective_flags,
            tactical_interval_microseconds=tactical_interval_microseconds,
        )

    def as_delta(self) -> PerformanceReceiptDelta:
        """Project committed counters into an immutable accumulation delta."""
        return PerformanceReceiptDelta(
            tactical_intervals=self.tactical_intervals,
            tactical_duration_microseconds=self.tactical_duration_microseconds,
            fow=self.fow,
            dispatch=self.dispatch,
            soa=self.soa,
            lod=self.lod,
        )

    @classmethod
    def from_delta(
        cls,
        delta: PerformanceReceiptDelta,
        *,
        effective_flags: EffectivePerformanceFlags,
        tactical_interval_microseconds: int,
        complete_from_tick_zero: bool,
    ) -> PerformanceExecutionReceipt:
        """Close and validate a complete transaction or cumulative delta."""
        if type(delta) is not PerformanceReceiptDelta:
            raise TypeError("delta must be PerformanceReceiptDelta")
        return cls(
            complete_from_tick_zero=complete_from_tick_zero,
            effective_flags=effective_flags,
            tactical_interval_microseconds=tactical_interval_microseconds,
            tactical_intervals=delta.tactical_intervals,
            tactical_duration_microseconds=delta.tactical_duration_microseconds,
            fow=delta.fow,
            dispatch=delta.dispatch,
            soa=delta.soa,
            lod=delta.lod,
        )


@dataclass(frozen=True, slots=True)
class PerformanceReceiptTransaction:
    """Opaque accumulator- and owner-bound transaction capability."""

    generation: int
    _accumulator_identity: object = field(repr=False, compare=False)
    _owner_identity: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PerformanceReceiptRestorePlan:
    """Validated, accumulator-bound atomic restore plan."""

    receipt: PerformanceExecutionReceipt
    _accumulator_identity: object = field(repr=False, compare=False)
    _owner_identity: object = field(repr=False, compare=False)


class PerformanceReceiptAccumulator:
    """Owner-bound monotonic accumulator with fail-closed transactions."""

    _STATE_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "complete_from_tick_zero",
            "effective_flags",
            "tactical_interval_microseconds",
            "tactical_intervals",
            "tactical_duration_microseconds",
            "fow",
            "dispatch",
            "soa",
            "lod",
        }
    )

    def __init__(
        self,
        *,
        owner: object,
        effective_flags: EffectivePerformanceFlags,
        tactical_interval_microseconds: int = DEFAULT_TACTICAL_INTERVAL_MICROSECONDS,
        complete_from_tick_zero: bool = True,
    ) -> None:
        if owner is None:
            raise TypeError("performance receipt accumulator owner cannot be None")
        if type(effective_flags) is not EffectivePerformanceFlags:
            raise TypeError("effective_flags must be EffectivePerformanceFlags")
        if type(complete_from_tick_zero) is not bool:
            raise TypeError("complete_from_tick_zero must be a boolean")
        self._owner = owner
        self._identity = object()
        self._receipt = PerformanceExecutionReceipt.zero(
            effective_flags=effective_flags,
            tactical_interval_microseconds=tactical_interval_microseconds,
            complete_from_tick_zero=complete_from_tick_zero,
        )
        self._active: PerformanceReceiptTransaction | None = None
        self._staged = PerformanceReceiptDelta()
        self._next_generation = 0
        self._poisoned = False
        self._poison_reason: str | None = None

    @property
    def effective_flags(self) -> EffectivePerformanceFlags:
        """Return the immutable effective-flag identity."""
        return self._receipt.effective_flags

    @property
    def tactical_interval_microseconds(self) -> int:
        """Return the immutable runtime tactical-cadence identity."""
        return self._receipt.tactical_interval_microseconds

    @property
    def transaction_active(self) -> bool:
        """Return whether a transaction is currently open."""
        return self._active is not None

    @property
    def poisoned(self) -> bool:
        """Return whether a failed production interval invalidated evidence."""
        return self._poisoned

    @property
    def poison_reason(self) -> str | None:
        """Return the bounded diagnostic reason for a poisoned accumulator."""
        return self._poison_reason

    def begin(self, owner: object) -> PerformanceReceiptTransaction:
        """Begin one production interval transaction."""
        self._require_owner(owner)
        self._require_healthy()
        if self._active is not None:
            raise RuntimeError("performance receipt transaction is already active")
        transaction = PerformanceReceiptTransaction(
            generation=self._next_generation,
            _accumulator_identity=self._identity,
            _owner_identity=owner,
        )
        self._next_generation += 1
        self._staged = PerformanceReceiptDelta()
        self._active = transaction
        return transaction

    def stage(
        self,
        owner: object,
        transaction: PerformanceReceiptTransaction,
        contribution: PerformanceReceiptDelta,
    ) -> None:
        """Stage a validated immutable contribution without publishing it."""
        self._require_transaction(owner, transaction)
        if type(contribution) is not PerformanceReceiptDelta:
            raise TypeError("contribution must be PerformanceReceiptDelta")
        self._staged = self._staged.plus(contribution)

    def stage_fow_cycle(
        self,
        owner: object,
        transaction: PerformanceReceiptTransaction,
        receipt: FogOfWarCycleReceipt,
    ) -> None:
        """Stage one already-reconciled reporting-side receipt."""
        self._require_transaction(owner, transaction)
        if type(receipt) is not FogOfWarCycleReceipt:
            raise TypeError("receipt must be FogOfWarCycleReceipt")
        self._staged = self._staged.plus(receipt.to_delta())

    def commit(
        self,
        owner: object,
        transaction: PerformanceReceiptTransaction,
    ) -> PerformanceExecutionReceipt:
        """Validate and atomically publish a complete transaction."""
        self._require_transaction(owner, transaction)
        try:
            cumulative = self._receipt.as_delta().plus(self._staged)
            committed = PerformanceExecutionReceipt.from_delta(
                cumulative,
                effective_flags=self.effective_flags,
                tactical_interval_microseconds=self.tactical_interval_microseconds,
                complete_from_tick_zero=self._receipt.complete_from_tick_zero,
            )
        except BaseException as exc:
            self._close_poisoned(
                reason=f"receipt reconciliation failed: {type(exc).__name__}",
            )
            raise

        self._receipt = committed
        self._staged = PerformanceReceiptDelta()
        self._active = None
        return committed

    def poison(
        self,
        owner: object,
        transaction: PerformanceReceiptTransaction,
        *,
        reason: str,
    ) -> None:
        """Permanently invalidate receipt evidence after an interval failure."""
        self._require_transaction(owner, transaction)
        if type(reason) is not str or not reason or reason != reason.strip():
            raise ValueError("poison reason must be a non-empty trimmed string")
        self._close_poisoned(reason=reason)

    def receipt(self, owner: object) -> PerformanceExecutionReceipt:
        """Return the immutable committed receipt when no transaction is open."""
        self._require_owner(owner)
        self._require_checkpointable()
        return self._receipt

    def mark_incomplete(self, owner: object) -> PerformanceExecutionReceipt:
        """Permanently clear tick-zero completeness for legacy continuation."""
        self._require_owner(owner)
        self._require_checkpointable()
        if not self._receipt.complete_from_tick_zero:
            return self._receipt
        self._receipt = PerformanceExecutionReceipt.from_delta(
            self._receipt.as_delta(),
            effective_flags=self.effective_flags,
            tactical_interval_microseconds=self.tactical_interval_microseconds,
            complete_from_tick_zero=False,
        )
        return self._receipt

    def get_state(self, owner: object) -> dict[str, Any]:
        """Return exact checkpoint state, rejecting active or poisoned work."""
        return self.receipt(owner).to_state()

    def checkpoint_state(self, owner: object) -> dict[str, Any]:
        """Alias for the checkpoint-facing state boundary."""
        return self.get_state(owner)

    def stage_state(
        self,
        owner: object,
        state: object,
    ) -> PerformanceReceiptRestorePlan:
        """Validate checkpoint state without mutating the accumulator."""
        self._require_owner(owner)
        self._require_checkpointable()
        candidate = PerformanceExecutionReceipt.from_state(state)
        resolve_supported_runtime_performance_flags(candidate.effective_flags)
        if candidate.effective_flags != self.effective_flags:
            raise ValueError(
                "performance receipt effective flags disagree with the runtime owner",
            )
        if candidate.tactical_interval_microseconds != self.tactical_interval_microseconds:
            raise ValueError(
                "performance receipt tactical cadence disagrees with the runtime owner",
            )
        if not self._receipt.complete_from_tick_zero and candidate.complete_from_tick_zero:
            raise ValueError(
                "performance receipt completeness cannot be promoted after legacy restore",
            )
        return PerformanceReceiptRestorePlan(
            receipt=candidate,
            _accumulator_identity=self._identity,
            _owner_identity=owner,
        )

    def commit_state(
        self,
        owner: object,
        plan: PerformanceReceiptRestorePlan,
    ) -> PerformanceExecutionReceipt:
        """Atomically commit a previously staged restore plan."""
        self._require_owner(owner)
        self._require_checkpointable()
        if type(plan) is not PerformanceReceiptRestorePlan:
            raise TypeError("plan must be PerformanceReceiptRestorePlan")
        if plan._accumulator_identity is not self._identity or plan._owner_identity is not owner:
            raise RuntimeError(
                "performance receipt restore plan belongs to another owner",
            )
        if plan.receipt.effective_flags != self.effective_flags:
            raise ValueError(
                "performance receipt restore flags changed after staging",
            )
        if plan.receipt.tactical_interval_microseconds != self.tactical_interval_microseconds:
            raise ValueError(
                "performance receipt tactical cadence changed after staging",
            )
        if not self._receipt.complete_from_tick_zero and plan.receipt.complete_from_tick_zero:
            raise ValueError(
                "performance receipt completeness cannot be promoted after legacy restore",
            )
        self._receipt = plan.receipt
        return self._receipt

    def set_state(
        self,
        owner: object,
        state: object,
    ) -> PerformanceExecutionReceipt:
        """Validate and atomically restore checkpoint state."""
        return self.commit_state(owner, self.stage_state(owner, state))

    def _require_owner(self, owner: object) -> None:
        if owner is not self._owner:
            raise RuntimeError("performance receipt accumulator owner mismatch")

    def _close_poisoned(self, *, reason: str) -> None:
        """Discard staged work and permanently close a failed transaction."""
        self._poisoned = True
        self._poison_reason = reason
        self._active = None
        self._staged = PerformanceReceiptDelta()

    def _require_healthy(self) -> None:
        if self._poisoned:
            raise RuntimeError(
                "performance receipt accumulator is poisoned"
                + (f": {self._poison_reason}" if self._poison_reason is not None else ""),
            )

    def _require_checkpointable(self) -> None:
        self._require_healthy()
        if self._active is not None:
            raise RuntimeError(
                "performance receipt state is unavailable during an active transaction",
            )

    def _require_transaction(
        self,
        owner: object,
        transaction: PerformanceReceiptTransaction,
    ) -> None:
        self._require_owner(owner)
        self._require_healthy()
        if type(transaction) is not PerformanceReceiptTransaction:
            raise TypeError("transaction must be PerformanceReceiptTransaction")
        if transaction._accumulator_identity is not self._identity or transaction._owner_identity is not owner:
            raise RuntimeError("performance receipt transaction owner mismatch")
        if transaction is not self._active:
            raise RuntimeError("performance receipt transaction is not active")


__all__ = [
    "DispatchReceipt",
    "DEFAULT_TACTICAL_INTERVAL_MICROSECONDS",
    "EffectivePerformanceFlags",
    "FOWCadenceReceipt",
    "FOWCadenceRecoveryPeriodReceipt",
    "FOWDetectionReceipt",
    "FOWFusionReceipt",
    "FOWIndexedRNGReceipt",
    "FOWReceipt",
    "FOWScanReceipt",
    "FOWSelectionReceipt",
    "FogOfWarCycleReceipt",
    "GovernedPerformanceFlag",
    "LODDetectionReceipt",
    "LODEngagementReceipt",
    "LODMoraleReceipt",
    "LODMovementReceipt",
    "LODReceipt",
    "LOD_RUNTIME_COMPATIBILITY_DEFAULTS",
    "PERFORMANCE_FLAG_ORDER",
    "PERFORMANCE_FLAG_REGISTRY",
    "PERFORMANCE_RECEIPT_SCHEMA_VERSION",
    "PERFORMANCE_SEMANTIC_EVIDENCE_MANIFEST_SHA256",
    "PERFORMANCE_SEMANTIC_EVIDENCE_PLAN_ID",
    "PerformanceExecutionReceipt",
    "PerformanceFlagClassification",
    "PerformanceFlagDefinition",
    "PerformanceFlagSupportDisposition",
    "PerformanceReceiptAccumulator",
    "PerformanceReceiptDelta",
    "PerformanceReceiptRestorePlan",
    "PerformanceReceiptTransaction",
    "RetainedSemanticVerdict",
    "SoAReceipt",
    "UnsupportedPerformanceConfigurationError",
    "resolve_cross_bound_runtime_performance_flags",
    "resolve_supported_runtime_performance_flags",
    "validate_supported_runtime_performance_parameter_name",
]
