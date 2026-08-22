"""Immutable performance-work receipts shared across simulation layers.

These models are observational data boundaries.  Detection constructs the
fog-of-war cycle receipts, while the simulation layer aggregates and persists
them.  Keeping the immutable DTOs in ``core`` preserves the repository's
one-way dependency direction without giving either layer ownership of the
other's behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _require_exact_state_topology(
    provided: object,
    canonical: object,
    *,
    path: str = "",
) -> None:
    """Reject omitted fields anywhere in a persisted receipt topology."""
    if isinstance(canonical, dict):
        if not isinstance(provided, Mapping):
            raise ValueError(f"receipt state {path or '/'} must be a mapping")
        provided_keys = set(provided)
        canonical_keys = set(canonical)
        if provided_keys != canonical_keys:
            missing = sorted(canonical_keys - provided_keys, key=str)
            extra = sorted(provided_keys - canonical_keys, key=str)
            raise ValueError(
                f"receipt state {path or '/'} has inexact topology; missing={missing}, extra={extra}",
            )
        for key in canonical:
            _require_exact_state_topology(
                provided[key],
                canonical[key],
                path=f"{path}/{key}",
            )
    elif isinstance(canonical, list):
        if (
            not isinstance(provided, Sequence)
            or isinstance(provided, (str, bytes, bytearray))
            or len(provided) != len(canonical)
        ):
            raise ValueError(f"receipt state {path or '/'} has inexact sequence topology")
        for index, item in enumerate(canonical):
            _require_exact_state_topology(
                provided[index],
                item,
                path=f"{path}/{index}",
            )


class _StrictFrozenModel(BaseModel):
    """Frozen, closed Pydantic model with strict input semantics."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )

    def to_state(self) -> dict[str, Any]:
        """Return the exact JSON-compatible public state topology."""
        return self.model_dump(mode="json")

    @classmethod
    def from_state(cls, state: object) -> Self:
        """Strictly validate an exact public state topology."""
        validated = cls.model_validate(state)
        _require_exact_state_topology(state, validated.to_state())
        return validated


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class _IntegerReceipt(_StrictFrozenModel):
    """Base for a receipt node containing only non-negative integers."""

    def plus(self, other: Self) -> Self:
        """Return the fieldwise sum of two receipt nodes of the same type."""
        if type(other) is not type(self):
            raise TypeError(f"cannot add {type(other).__name__} to {type(self).__name__}")
        model_type = type(self)
        return model_type.model_validate(
            {name: getattr(self, name) + getattr(other, name) for name in model_type.model_fields}
        )


class FOWSelectionReceipt(_IntegerReceipt):
    """Target-selection work, retaining target units throughout."""

    strtree_builds: NonNegativeInt = 0
    strtree_queries: NonNegativeInt = 0
    strtree_admitted_targets: NonNegativeInt = 0
    strtree_pruned_targets: NonNegativeInt = 0
    soa_vector_builds: NonNegativeInt = 0
    soa_vector_queries: NonNegativeInt = 0
    soa_vector_admitted_targets: NonNegativeInt = 0
    soa_vector_pruned_targets: NonNegativeInt = 0
    brute_force_cycles: NonNegativeInt = 0
    brute_force_admitted_targets: NonNegativeInt = 0

    @property
    def selector_cycles(self) -> int:
        """Number of observer-level selector cycles."""
        return self.strtree_queries + self.soa_vector_queries + self.brute_force_cycles

    @property
    def admitted_targets(self) -> int:
        """Number of target candidates admitted by all selectors."""
        return self.strtree_admitted_targets + self.soa_vector_admitted_targets + self.brute_force_admitted_targets

    @property
    def pruned_targets(self) -> int:
        """Number of target candidates pruned by exact optimization routes."""
        return self.strtree_pruned_targets + self.soa_vector_pruned_targets


class FOWScanReceipt(_IntegerReceipt):
    """Detection-API work and attachment scheduling skips."""

    operational_sensor_target_opportunities: NonNegativeInt = 0
    scheduled_attachment_skips: NonNegativeInt = 0


class FOWCadenceRecoveryPeriodReceipt(_StrictFrozenModel):
    """Recoveries sharing one exact deferral-origin cadence period."""

    deferral_period: PositiveInt
    recovery_admissions: PositiveInt
    recovery_admissions_with_indexed_work: NonNegativeInt = 0
    indexed_detection_blocks: NonNegativeInt = 0

    @model_validator(mode="after")
    def _reconcile_material_work(self) -> FOWCadenceRecoveryPeriodReceipt:
        if self.recovery_admissions_with_indexed_work > self.recovery_admissions:
            raise ValueError(
                "recovery admissions with indexed work cannot exceed recovery admissions",
            )
        if self.indexed_detection_blocks < self.recovery_admissions_with_indexed_work:
            raise ValueError(
                "indexed detection blocks cannot be fewer than recovery admissions with indexed work",
            )
        if (self.recovery_admissions_with_indexed_work == 0) is not (
            self.indexed_detection_blocks == 0
        ):
            raise ValueError(
                "indexed recovery admissions and detection blocks must be zero together",
            )
        return self

    def plus(
        self,
        other: FOWCadenceRecoveryPeriodReceipt,
    ) -> FOWCadenceRecoveryPeriodReceipt:
        """Return the sum of two buckets with the same origin period."""
        if type(other) is not FOWCadenceRecoveryPeriodReceipt:
            raise TypeError(
                "FOWCadenceRecoveryPeriodReceipt can only be added to its own type",
            )
        if other.deferral_period != self.deferral_period:
            raise ValueError("cadence recovery periods must match before addition")
        return FOWCadenceRecoveryPeriodReceipt(
            deferral_period=self.deferral_period,
            recovery_admissions=(self.recovery_admissions + other.recovery_admissions),
            recovery_admissions_with_indexed_work=(
                self.recovery_admissions_with_indexed_work
                + other.recovery_admissions_with_indexed_work
            ),
            indexed_detection_blocks=(
                self.indexed_detection_blocks + other.indexed_detection_blocks
            ),
        )


def _plus_recovery_periods(
    left: tuple[FOWCadenceRecoveryPeriodReceipt, ...],
    right: tuple[FOWCadenceRecoveryPeriodReceipt, ...],
) -> tuple[FOWCadenceRecoveryPeriodReceipt, ...]:
    """Key and add canonical recovery-period buckets."""
    combined = {bucket.deferral_period: bucket for bucket in left}
    for bucket in right:
        existing = combined.get(bucket.deferral_period)
        combined[bucket.deferral_period] = (
            bucket if existing is None else existing.plus(bucket)
        )
    return tuple(combined[period] for period in sorted(combined))


class FOWCadenceReceipt(_StrictFrozenModel):
    """Attachment-level cadence accounting."""

    attachment_cycles: NonNegativeInt = 0
    operational_attachment_cycles: NonNegativeInt = 0
    native_ready: NonNegativeInt = 0
    lod_ready: NonNegativeInt = 0
    admitted: NonNegativeInt = 0
    deferred_native: NonNegativeInt = 0
    deferred_lod: NonNegativeInt = 0
    deferred_both: NonNegativeInt = 0
    offline: NonNegativeInt = 0
    native_recoveries_by_period: tuple[
        FOWCadenceRecoveryPeriodReceipt,
        ...,
    ] = ()
    lod_recoveries_by_period: tuple[
        FOWCadenceRecoveryPeriodReceipt,
        ...,
    ] = ()

    @field_validator(
        "native_recoveries_by_period",
        "lod_recoveries_by_period",
        mode="before",
    )
    @classmethod
    def _recovery_period_sequence(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        if type(value) is not tuple:
            raise ValueError("cadence recovery period buckets must be a tuple or state list")
        return value

    @model_validator(mode="after")
    def _reconcile_attachment_partitions(self) -> FOWCadenceReceipt:
        if self.attachment_cycles != self.operational_attachment_cycles + self.offline:
            raise ValueError(
                "attachment_cycles must equal operational_attachment_cycles plus offline",
            )
        operational_partition = self.admitted + self.deferred_native + self.deferred_lod + self.deferred_both
        if self.operational_attachment_cycles != operational_partition:
            raise ValueError(
                "operational attachment cycles do not reconcile with cadence dispositions",
            )
        if self.native_ready > self.attachment_cycles:
            raise ValueError("native_ready cannot exceed attachment_cycles")
        if self.lod_ready > self.attachment_cycles:
            raise ValueError("lod_ready cannot exceed attachment_cycles")
        for label, buckets in (
            ("native", self.native_recoveries_by_period),
            ("LOD", self.lod_recoveries_by_period),
        ):
            periods = tuple(bucket.deferral_period for bucket in buckets)
            if periods != tuple(sorted(set(periods))):
                raise ValueError(
                    f"{label} cadence recovery periods must be unique and strictly increasing",
                )
            if sum(bucket.recovery_admissions for bucket in buckets) > self.admitted:
                raise ValueError(
                    f"{label} cadence recoveries cannot exceed admitted attachments",
                )
        return self

    @property
    def deferred(self) -> int:
        """Operational attachment cycles deferred by either readiness gate."""
        return self.deferred_native + self.deferred_lod + self.deferred_both

    def plus(self, other: FOWCadenceReceipt) -> FOWCadenceReceipt:
        """Return counts plus keyed canonical recovery-period sums."""
        if type(other) is not FOWCadenceReceipt:
            raise TypeError("FOWCadenceReceipt can only be added to FOWCadenceReceipt")
        return FOWCadenceReceipt(
            attachment_cycles=self.attachment_cycles + other.attachment_cycles,
            operational_attachment_cycles=(
                self.operational_attachment_cycles
                + other.operational_attachment_cycles
            ),
            native_ready=self.native_ready + other.native_ready,
            lod_ready=self.lod_ready + other.lod_ready,
            admitted=self.admitted + other.admitted,
            deferred_native=self.deferred_native + other.deferred_native,
            deferred_lod=self.deferred_lod + other.deferred_lod,
            deferred_both=self.deferred_both + other.deferred_both,
            offline=self.offline + other.offline,
            native_recoveries_by_period=_plus_recovery_periods(
                self.native_recoveries_by_period,
                other.native_recoveries_by_period,
            ),
            lod_recoveries_by_period=_plus_recovery_periods(
                self.lod_recoveries_by_period,
                other.lod_recoveries_by_period,
            ),
        )


class FOWDetectionReceipt(_IntegerReceipt):
    """Detection boundary decision-stage accounting."""

    api_calls: NonNegativeInt = 0
    pre_rng_unsupported_domain_rejections: NonNegativeInt = 0
    pre_rng_above_max_range_rejections: NonNegativeInt = 0
    pre_rng_below_min_range_rejections: NonNegativeInt = 0
    pre_rng_outside_fov_rejections: NonNegativeInt = 0
    pre_rng_los_rejections: NonNegativeInt = 0
    pre_rng_no_emission_rejections: NonNegativeInt = 0
    stochastic_draws: NonNegativeInt = 0
    successes: NonNegativeInt = 0
    published_witnesses: NonNegativeInt = 0

    @property
    def pre_rng_rejections(self) -> int:
        """Total calls rejected before an indexed decision block."""
        return (
            self.pre_rng_unsupported_domain_rejections
            + self.pre_rng_above_max_range_rejections
            + self.pre_rng_below_min_range_rejections
            + self.pre_rng_outside_fov_rejections
            + self.pre_rng_los_rejections
            + self.pre_rng_no_emission_rejections
        )

    @model_validator(mode="after")
    def _reconcile_decision_stages(self) -> FOWDetectionReceipt:
        if self.api_calls != self.pre_rng_rejections + self.stochastic_draws:
            raise ValueError(
                "detection api_calls must equal pre-RNG rejections plus stochastic draws",
            )
        if self.successes > self.stochastic_draws:
            raise ValueError("detection successes cannot exceed stochastic draws")
        if self.published_witnesses > self.successes:
            raise ValueError("published witnesses cannot exceed detection successes")
        return self


class FOWFusionReceipt(_IntegerReceipt):
    """Elapsed-time estimator and fusion disposition accounting."""

    position_measurement_candidates: NonNegativeInt = 0
    position_measurement_groups: NonNegativeInt = 0
    correlated_candidates_elided: NonNegativeInt = 0
    predictions: NonNegativeInt = 0
    predicted_microseconds: NonNegativeInt = 0
    creations: NonNegativeInt = 0
    updates: NonNegativeInt = 0
    replacements: NonNegativeInt = 0

    @model_validator(mode="after")
    def _reconcile_elapsed_predictions(self) -> FOWFusionReceipt:
        if (self.predictions == 0) != (self.predicted_microseconds == 0):
            raise ValueError(
                "fusion prediction count and elapsed microseconds must be zero together",
            )
        if self.position_measurement_candidates != (
            self.position_measurement_groups
            + self.correlated_candidates_elided
        ):
            raise ValueError(
                "fusion candidates must equal groups plus correlated candidates elided",
            )
        if self.position_measurement_groups != (
            self.creations + self.updates + self.replacements
        ):
            raise ValueError(
                "fusion groups must equal creations plus updates plus replacements",
            )
        if self.predictions > self.position_measurement_groups:
            raise ValueError("fusion predictions cannot exceed measurement groups")
        return self


class FOWIndexedRNGReceipt(_IntegerReceipt):
    """Indexed Philox decision and transcript accounting."""

    blocks: NonNegativeInt = 0
    detection_lanes: NonNegativeInt = 0
    identification_lanes: NonNegativeInt = 0
    transcript_entries: NonNegativeInt = 0


class LODDetectionReceipt(_IntegerReceipt):
    """Attachment dispositions partitioned by the observer's LOD tier."""

    active_attachments_admitted: NonNegativeInt = 0
    active_attachments_deferred: NonNegativeInt = 0
    nearby_attachments_admitted: NonNegativeInt = 0
    nearby_attachments_deferred: NonNegativeInt = 0
    distant_attachments_admitted: NonNegativeInt = 0
    distant_attachments_deferred: NonNegativeInt = 0

    @property
    def admitted(self) -> int:
        """Attachment admissions across all three tiers."""
        return self.active_attachments_admitted + self.nearby_attachments_admitted + self.distant_attachments_admitted

    @property
    def deferred(self) -> int:
        """Attachment deferrals across all three tiers."""
        return self.active_attachments_deferred + self.nearby_attachments_deferred + self.distant_attachments_deferred


class FOWReceipt(_StrictFrozenModel):
    """Cumulative FOW counts in the exact persisted topology."""

    side_cycles: NonNegativeInt = 0
    observers: NonNegativeInt = 0
    targets: NonNegativeInt = 0
    sensors: NonNegativeInt = 0
    target_opportunities: NonNegativeInt = 0
    selection: FOWSelectionReceipt = Field(default_factory=FOWSelectionReceipt)
    scan: FOWScanReceipt = Field(default_factory=FOWScanReceipt)
    cadence: FOWCadenceReceipt = Field(default_factory=FOWCadenceReceipt)
    detection: FOWDetectionReceipt = Field(default_factory=FOWDetectionReceipt)
    fusion: FOWFusionReceipt = Field(default_factory=FOWFusionReceipt)
    indexed_rng: FOWIndexedRNGReceipt = Field(default_factory=FOWIndexedRNGReceipt)

    @model_validator(mode="after")
    def _closed_topology(self) -> FOWReceipt:
        _validate_fow_topology(
            observers=self.observers,
            sensors=self.sensors,
            target_opportunities=self.target_opportunities,
            selection=self.selection,
            scan=self.scan,
            cadence=self.cadence,
            detection=self.detection,
            fusion=self.fusion,
            indexed_rng=self.indexed_rng,
        )
        return self

    def plus(self, other: FOWReceipt) -> FOWReceipt:
        """Return the exact fieldwise aggregate of two FOW receipts."""
        if type(other) is not FOWReceipt:
            raise TypeError("FOWReceipt can only be added to FOWReceipt")
        return FOWReceipt(
            side_cycles=self.side_cycles + other.side_cycles,
            observers=self.observers + other.observers,
            targets=self.targets + other.targets,
            sensors=self.sensors + other.sensors,
            target_opportunities=(self.target_opportunities + other.target_opportunities),
            selection=self.selection.plus(other.selection),
            scan=self.scan.plus(other.scan),
            cadence=self.cadence.plus(other.cadence),
            detection=self.detection.plus(other.detection),
            fusion=self.fusion.plus(other.fusion),
            indexed_rng=self.indexed_rng.plus(other.indexed_rng),
        )


class DispatchReceipt(_IntegerReceipt):
    """Sequential and threaded side-dispatch work."""

    sequential_intervals: NonNegativeInt = 0
    sequential_side_updates: NonNegativeInt = 0
    parallel_intervals: NonNegativeInt = 0
    parallel_tasks_submitted: NonNegativeInt = 0
    parallel_tasks_joined: NonNegativeInt = 0

    @model_validator(mode="after")
    def _joined_tasks_reconcile(self) -> DispatchReceipt:
        if self.parallel_tasks_submitted != self.parallel_tasks_joined:
            raise ValueError("parallel tasks submitted and joined must be equal")
        return self


class SoAReceipt(_IntegerReceipt):
    """Read-only structure-of-arrays snapshot and projection work."""

    pre_movement_builds: NonNegativeInt = 0
    pre_movement_enemy_position_projections: NonNegativeInt = 0
    post_movement_builds: NonNegativeInt = 0
    post_movement_enemy_position_projections: NonNegativeInt = 0


class LODEngagementReceipt(_IntegerReceipt):
    """Full-rate engagement work while LOD is governed."""

    attacker_cycles_processed: NonNegativeInt = 0
    deferred: NonNegativeInt = 0

    @model_validator(mode="after")
    def _never_deferred(self) -> LODEngagementReceipt:
        if self.deferred != 0:
            raise ValueError("LOD may not defer engagement work")
        return self


class LODMoraleReceipt(_IntegerReceipt):
    """Full-rate morale work while LOD is governed."""

    unit_cycles_processed: NonNegativeInt = 0
    deferred: NonNegativeInt = 0

    @model_validator(mode="after")
    def _never_deferred(self) -> LODMoraleReceipt:
        if self.deferred != 0:
            raise ValueError("LOD may not defer morale work")
        return self


class LODMovementReceipt(_IntegerReceipt):
    """Full-rate movement work classified by LOD tier."""

    active_processed: NonNegativeInt = 0
    nearby_processed: NonNegativeInt = 0
    distant_processed: NonNegativeInt = 0
    deferred: NonNegativeInt = 0

    @model_validator(mode="after")
    def _never_deferred(self) -> LODMovementReceipt:
        if self.deferred != 0:
            raise ValueError("LOD may not defer movement work")
        return self


class LODReceipt(_StrictFrozenModel):
    """LOD classifications, sensing dispositions, and full-rate consumers."""

    active_classifications: NonNegativeInt = 0
    nearby_classifications: NonNegativeInt = 0
    distant_classifications: NonNegativeInt = 0
    detection: LODDetectionReceipt = Field(default_factory=LODDetectionReceipt)
    engagement: LODEngagementReceipt = Field(default_factory=LODEngagementReceipt)
    morale: LODMoraleReceipt = Field(default_factory=LODMoraleReceipt)
    movement: LODMovementReceipt = Field(default_factory=LODMovementReceipt)

    def plus(self, other: LODReceipt) -> LODReceipt:
        """Return the exact fieldwise aggregate of two LOD receipts."""
        if type(other) is not LODReceipt:
            raise TypeError("LODReceipt can only be added to LODReceipt")
        return LODReceipt(
            active_classifications=(self.active_classifications + other.active_classifications),
            nearby_classifications=(self.nearby_classifications + other.nearby_classifications),
            distant_classifications=(self.distant_classifications + other.distant_classifications),
            detection=self.detection.plus(other.detection),
            engagement=self.engagement.plus(other.engagement),
            morale=self.morale.plus(other.morale),
            movement=self.movement.plus(other.movement),
        )


class FogOfWarCycleReceipt(_StrictFrozenModel):
    """One immutable, fully reconciled reporting-side FOW cycle."""

    reporting_side: str
    engine_tick: NonNegativeInt
    observers: NonNegativeInt = 0
    targets: NonNegativeInt = 0
    sensors: NonNegativeInt = 0
    target_opportunities: NonNegativeInt = 0
    selection: FOWSelectionReceipt = Field(default_factory=FOWSelectionReceipt)
    scan: FOWScanReceipt = Field(default_factory=FOWScanReceipt)
    cadence: FOWCadenceReceipt = Field(default_factory=FOWCadenceReceipt)
    detection: FOWDetectionReceipt = Field(default_factory=FOWDetectionReceipt)
    fusion: FOWFusionReceipt = Field(default_factory=FOWFusionReceipt)
    indexed_rng: FOWIndexedRNGReceipt = Field(default_factory=FOWIndexedRNGReceipt)
    lod_detection: LODDetectionReceipt = Field(default_factory=LODDetectionReceipt)

    @field_validator("reporting_side", mode="before")
    @classmethod
    def _reporting_side(cls, value: object) -> str:
        if type(value) is not str or not value or value != value.strip():
            raise ValueError("reporting_side must be a non-empty trimmed string")
        return value

    @model_validator(mode="after")
    def _closed_topology(self) -> FogOfWarCycleReceipt:
        _validate_fow_topology(
            observers=self.observers,
            sensors=self.sensors,
            target_opportunities=self.target_opportunities,
            selection=self.selection,
            scan=self.scan,
            cadence=self.cadence,
            detection=self.detection,
            fusion=self.fusion,
            indexed_rng=self.indexed_rng,
        )
        if self.target_opportunities != self.observers * self.targets:
            raise ValueError(
                "target_opportunities must equal observers times targets",
            )
        if self.lod_detection.admitted != self.cadence.admitted:
            raise ValueError("LOD tier admissions must equal cadence admissions")
        if self.lod_detection.deferred != self.cadence.deferred:
            raise ValueError("LOD tier deferrals must equal cadence deferrals")
        return self

    def to_fow_receipt(self) -> FOWReceipt:
        """Project this side cycle into the cumulative FOW topology."""
        return FOWReceipt(
            side_cycles=1,
            observers=self.observers,
            targets=self.targets,
            sensors=self.sensors,
            target_opportunities=self.target_opportunities,
            selection=self.selection,
            scan=self.scan,
            cadence=self.cadence,
            detection=self.detection,
            fusion=self.fusion,
            indexed_rng=self.indexed_rng,
        )

    def to_delta(self) -> PerformanceReceiptDelta:
        """Return a transaction-only contribution for this side cycle."""
        return PerformanceReceiptDelta(
            fow=self.to_fow_receipt(),
            lod=LODReceipt(detection=self.lod_detection),
        )


def _validate_fow_topology(
    *,
    observers: int,
    sensors: int,
    target_opportunities: int,
    selection: FOWSelectionReceipt,
    scan: FOWScanReceipt,
    cadence: FOWCadenceReceipt,
    detection: FOWDetectionReceipt,
    fusion: FOWFusionReceipt,
    indexed_rng: FOWIndexedRNGReceipt,
) -> None:
    """Validate the exact target-, attachment-, call-, and RNG-unit equations."""
    if selection.selector_cycles != observers:
        raise ValueError("each observer must name exactly one target-selection route")
    if selection.admitted_targets + selection.pruned_targets != target_opportunities:
        raise ValueError(
            "selector admitted and pruned target counts must equal target_opportunities",
        )
    if sensors != cadence.attachment_cycles:
        raise ValueError("sensor count must equal cadence attachment_cycles")
    if scan.scheduled_attachment_skips != cadence.deferred:
        raise ValueError(
            "scheduled attachment skips must equal cadence attachment deferrals",
        )
    if scan.operational_sensor_target_opportunities != detection.api_calls:
        raise ValueError(
            "operational sensor-target opportunities must equal detection api_calls",
        )
    if detection.stochastic_draws != indexed_rng.blocks:
        raise ValueError("stochastic draws must equal indexed RNG blocks")
    if indexed_rng.blocks != indexed_rng.detection_lanes:
        raise ValueError("indexed RNG blocks must equal detection lanes")
    if indexed_rng.blocks != indexed_rng.transcript_entries:
        raise ValueError("indexed RNG blocks must equal transcript entries")
    if indexed_rng.identification_lanes > detection.successes:
        raise ValueError("identification lanes cannot exceed detection successes")
    if fusion.position_measurement_candidates != detection.successes:
        raise ValueError(
            "fusion position-measurement candidates must equal detection successes",
        )
    for label, buckets in (
        ("native", cadence.native_recoveries_by_period),
        ("LOD", cadence.lod_recoveries_by_period),
    ):
        recovery_blocks = sum(
            bucket.indexed_detection_blocks for bucket in buckets
        )
        if recovery_blocks > indexed_rng.blocks:
            raise ValueError(
                f"{label} cadence recovery blocks cannot exceed indexed RNG blocks",
            )


class PerformanceReceiptDelta(_StrictFrozenModel):
    """Immutable partial contribution to one owner transaction.

    A delta can be incomplete across owners (for example, side-cycle work may
    be staged before its dispatch counters).  It is therefore never serialized
    as execution evidence.  Commit builds and validates the closed execution
    receipt before publishing any mutation.
    """

    tactical_intervals: NonNegativeInt = 0
    tactical_duration_microseconds: NonNegativeInt = 0
    fow: FOWReceipt = Field(default_factory=FOWReceipt)
    dispatch: DispatchReceipt = Field(default_factory=DispatchReceipt)
    soa: SoAReceipt = Field(default_factory=SoAReceipt)
    lod: LODReceipt = Field(default_factory=LODReceipt)

    def plus(self, other: PerformanceReceiptDelta) -> PerformanceReceiptDelta:
        """Return the fieldwise sum of two transaction contributions."""
        if type(other) is not PerformanceReceiptDelta:
            raise TypeError(
                "PerformanceReceiptDelta can only be added to PerformanceReceiptDelta",
            )
        return PerformanceReceiptDelta(
            tactical_intervals=self.tactical_intervals + other.tactical_intervals,
            tactical_duration_microseconds=(self.tactical_duration_microseconds + other.tactical_duration_microseconds),
            fow=self.fow.plus(other.fow),
            dispatch=self.dispatch.plus(other.dispatch),
            soa=self.soa.plus(other.soa),
            lod=self.lod.plus(other.lod),
        )


__all__ = [
    "DispatchReceipt",
    "FOWCadenceReceipt",
    "FOWCadenceRecoveryPeriodReceipt",
    "FOWDetectionReceipt",
    "FOWFusionReceipt",
    "FOWIndexedRNGReceipt",
    "FOWReceipt",
    "FOWScanReceipt",
    "FOWSelectionReceipt",
    "FogOfWarCycleReceipt",
    "LODDetectionReceipt",
    "LODEngagementReceipt",
    "LODMoraleReceipt",
    "LODMovementReceipt",
    "LODReceipt",
    "PerformanceReceiptDelta",
    "SoAReceipt",
]
