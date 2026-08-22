"""Deterministic, transactional sensor-readiness cadence.

The scheduler owns attachment-level native and level-of-detail readiness.  A
complete reporting-side roster is staged for one global fog-of-war interval,
then committed only after every side has completed its observation work.
Staging is deliberately free of sensor and target behavior: an admitted sweep
consumes readiness even when target selection subsequently produces no targets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any


CADENCE_SCHEMA_VERSION = 2
_U64_MAX = (1 << 64) - 1


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8") from exc
    return value


def _require_u64(value: object, *, label: str) -> int:
    if type(value) is not int or not 0 <= value <= _U64_MAX:
        raise ValueError(f"{label} must be an unsigned 64-bit integer")
    return value


def _require_positive_period(value: object, *, label: str) -> int:
    period = _require_u64(value, label=label)
    if period == 0:
        raise ValueError(f"{label} must be positive")
    return period


def _require_bool(value: object, *, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _checked_add(left: int, right: int, *, label: str) -> int:
    result = left + right
    if result > _U64_MAX:
        raise ValueError(f"{label} exceeds the unsigned 64-bit bound")
    return result


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalObserverIdentity:
    """Exact reporting-side observer identity used by LOD promotions."""

    reporting_side: str
    observer_unit_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reporting_side",
            _require_identifier(
                self.reporting_side,
                label="observer reporting_side",
            ),
        )
        object.__setattr__(
            self,
            "observer_unit_id",
            _require_identifier(
                self.observer_unit_id,
                label="observer observer_unit_id",
            ),
        )

    def sort_key(self) -> tuple[bytes, bytes]:
        """Return the canonical UTF-8 byte order."""
        return (
            self.reporting_side.encode("utf-8"),
            self.observer_unit_id.encode("utf-8"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalAttachmentIdentity:
    """Complete identity of one runtime sensor attachment."""

    reporting_side: str
    observer_unit_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reporting_side",
            _require_identifier(
                self.reporting_side,
                label="attachment reporting_side",
            ),
        )
        object.__setattr__(
            self,
            "observer_unit_id",
            _require_identifier(
                self.observer_unit_id,
                label="attachment observer_unit_id",
            ),
        )
        object.__setattr__(
            self,
            "source_equipment_index",
            _require_u64(
                self.source_equipment_index,
                label="attachment source_equipment_index",
            ),
        )
        object.__setattr__(
            self,
            "sensor_id",
            _require_identifier(
                self.sensor_id,
                label="attachment sensor_id",
            ),
        )
        object.__setattr__(
            self,
            "modeled_role",
            _require_identifier(
                self.modeled_role,
                label="attachment modeled_role",
            ),
        )

    @property
    def observer(self) -> TacticalObserverIdentity:
        """Return the attachment's reporting-side observer identity."""
        return TacticalObserverIdentity(
            reporting_side=self.reporting_side,
            observer_unit_id=self.observer_unit_id,
        )

    def sort_key(self) -> tuple[bytes, bytes, int, bytes, bytes]:
        """Return the canonical complete-roster order."""
        return (
            self.reporting_side.encode("utf-8"),
            self.observer_unit_id.encode("utf-8"),
            self.source_equipment_index,
            self.sensor_id.encode("utf-8"),
            self.modeled_role.encode("utf-8"),
        )

    def get_state(self) -> dict[str, Any]:
        """Return the exact JSON-compatible identity state."""
        return {
            "reporting_side": self.reporting_side,
            "observer_unit_id": self.observer_unit_id,
            "source_equipment_index": self.source_equipment_index,
            "sensor_id": self.sensor_id,
            "modeled_role": self.modeled_role,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class _NativePhaseGroupKey:
    """Typed identity of one independent native-cadence phase group."""

    reporting_side: str
    sensor_id: str
    modeled_role: str
    native_period: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reporting_side",
            _require_identifier(
                self.reporting_side,
                label="native phase group reporting_side",
            ),
        )
        object.__setattr__(
            self,
            "sensor_id",
            _require_identifier(
                self.sensor_id,
                label="native phase group sensor_id",
            ),
        )
        object.__setattr__(
            self,
            "modeled_role",
            _require_identifier(
                self.modeled_role,
                label="native phase group modeled_role",
            ),
        )
        object.__setattr__(
            self,
            "native_period",
            _require_positive_period(
                self.native_period,
                label="native phase group native_period",
            ),
        )

    def sort_key(self) -> tuple[bytes, bytes, bytes, int]:
        return (
            self.reporting_side.encode("utf-8"),
            self.sensor_id.encode("utf-8"),
            self.modeled_role.encode("utf-8"),
            self.native_period,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalNativePhaseAssignment:
    """Immutable native-cadence phase assignment for one exact attachment."""

    identity: TacticalAttachmentIdentity
    native_period: int
    native_assignment_ordinal: int
    native_phase_residue: int

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise ValueError(
                "native phase assignment identity must be a TacticalAttachmentIdentity",
            )
        object.__setattr__(
            self,
            "native_period",
            _require_positive_period(
                self.native_period,
                label="native phase assignment native_period",
            ),
        )
        object.__setattr__(
            self,
            "native_assignment_ordinal",
            _require_u64(
                self.native_assignment_ordinal,
                label="native phase assignment ordinal",
            ),
        )
        object.__setattr__(
            self,
            "native_phase_residue",
            _require_u64(
                self.native_phase_residue,
                label="native phase assignment residue",
            ),
        )
        if self.native_phase_residue >= self.native_period:
            raise ValueError("native phase assignment residue must be below its period")
        if self.native_phase_residue != (self.native_assignment_ordinal % self.native_period):
            raise ValueError(
                "native phase assignment residue must equal ordinal modulo period",
            )

    @property
    def group(self) -> _NativePhaseGroupKey:
        return _NativePhaseGroupKey(
            reporting_side=self.identity.reporting_side,
            sensor_id=self.identity.sensor_id,
            modeled_role=self.identity.modeled_role,
            native_period=self.native_period,
        )

    def sort_key(
        self,
    ) -> tuple[tuple[bytes, bytes, bytes, int], int, tuple[bytes, bytes, int, bytes, bytes]]:
        return (
            self.group.sort_key(),
            self.native_assignment_ordinal,
            self.identity.sort_key(),
        )

    def get_state(self) -> dict[str, Any]:
        return {
            "identity": self.identity.get_state(),
            "native_period": self.native_period,
            "native_assignment_ordinal": self.native_assignment_ordinal,
            "native_phase_residue": self.native_phase_residue,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalCadenceAttachment:
    """One complete-roster cadence request for the current interval."""

    identity: TacticalAttachmentIdentity
    native_period: int
    lod_period: int
    operational: bool

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise ValueError(
                "cadence attachment identity must be a TacticalAttachmentIdentity",
            )
        object.__setattr__(
            self,
            "native_period",
            _require_positive_period(
                self.native_period,
                label="cadence native_period",
            ),
        )
        object.__setattr__(
            self,
            "lod_period",
            _require_positive_period(
                self.lod_period,
                label="cadence lod_period",
            ),
        )
        object.__setattr__(
            self,
            "operational",
            _require_bool(
                self.operational,
                label="cadence operational",
            ),
        )


class TacticalCadenceDisposition(str, Enum):
    """Exact attachment disposition for one staged interval."""

    ADMITTED = "admitted"
    OFFLINE = "offline"
    DEFERRED_NATIVE = "deferred_native"
    DEFERRED_LOD = "deferred_lod"
    DEFERRED_BOTH = "deferred_both"


class TacticalCadenceRecoveryAxis(str, Enum):
    """Readiness axis whose pending deferral was closed by an admission."""

    NATIVE = "native"
    LOD = "lod"


_RECOVERY_AXIS_ORDER = MappingProxyType(
    {
        TacticalCadenceRecoveryAxis.NATIVE: 0,
        TacticalCadenceRecoveryAxis.LOD: 1,
    },
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalCadenceRecovery:
    """One exact-identity recovery nested in its cadence decision."""

    axis: TacticalCadenceRecoveryAxis
    deferral_ordinal: int
    admission_ordinal: int
    deferral_period: int

    def __post_init__(self) -> None:
        if type(self.axis) is not TacticalCadenceRecoveryAxis:
            raise ValueError(
                "cadence recovery axis must be a TacticalCadenceRecoveryAxis",
            )
        object.__setattr__(
            self,
            "deferral_ordinal",
            _require_u64(
                self.deferral_ordinal,
                label="cadence recovery deferral_ordinal",
            ),
        )
        object.__setattr__(
            self,
            "admission_ordinal",
            _require_u64(
                self.admission_ordinal,
                label="cadence recovery admission_ordinal",
            ),
        )
        object.__setattr__(
            self,
            "deferral_period",
            _require_positive_period(
                self.deferral_period,
                label="cadence recovery deferral_period",
            ),
        )
        if self.deferral_ordinal >= self.admission_ordinal:
            raise ValueError(
                "cadence recovery deferral must precede its admission",
            )

    def sort_key(self) -> int:
        """Return the canonical native-before-LOD axis order."""
        return _RECOVERY_AXIS_ORDER[self.axis]

    def get_state(self) -> dict[str, Any]:
        """Return the exact JSON-compatible transient event state."""
        return {
            "axis": self.axis.value,
            "deferral_ordinal": self.deferral_ordinal,
            "admission_ordinal": self.admission_ordinal,
            "deferral_period": self.deferral_period,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalCadenceDecision:
    """Immutable admission instruction for one attachment sweep."""

    identity: TacticalAttachmentIdentity
    native_period: int
    native_assignment_ordinal: int
    native_phase_residue: int
    lod_period: int
    native_ready: bool
    lod_ready: bool
    operational: bool
    admitted: bool
    first_cycle: bool
    disposition: TacticalCadenceDisposition
    recoveries: tuple[TacticalCadenceRecovery, ...] = ()

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise ValueError(
                "cadence decision identity must be a TacticalAttachmentIdentity",
            )
        _require_positive_period(
            self.native_period,
            label="cadence decision native_period",
        )
        assignment_ordinal = _require_u64(
            self.native_assignment_ordinal,
            label="cadence decision native_assignment_ordinal",
        )
        phase_residue = _require_u64(
            self.native_phase_residue,
            label="cadence decision native_phase_residue",
        )
        if phase_residue >= self.native_period:
            raise ValueError("cadence decision native phase residue exceeds its period")
        if phase_residue != assignment_ordinal % self.native_period:
            raise ValueError("cadence decision native phase assignment is inconsistent")
        _require_positive_period(
            self.lod_period,
            label="cadence decision lod_period",
        )
        for name in (
            "native_ready",
            "lod_ready",
            "operational",
            "admitted",
            "first_cycle",
        ):
            _require_bool(getattr(self, name), label=f"cadence decision {name}")
        if not isinstance(self.disposition, TacticalCadenceDisposition):
            raise ValueError(
                "cadence decision disposition must be a TacticalCadenceDisposition",
            )
        expected = _disposition_for(
            operational=self.operational,
            native_ready=self.native_ready,
            lod_ready=self.lod_ready,
        )
        if self.disposition is not expected:
            raise ValueError("cadence decision disposition is inconsistent")
        if self.admitted is not (expected is TacticalCadenceDisposition.ADMITTED):
            raise ValueError("cadence decision admitted flag is inconsistent")
        if type(self.recoveries) is not tuple or any(
            type(recovery) is not TacticalCadenceRecovery
            for recovery in self.recoveries
        ):
            raise ValueError(
                "cadence decision recoveries must be a tuple of TacticalCadenceRecovery",
            )
        axes = tuple(recovery.axis for recovery in self.recoveries)
        canonical_axes = tuple(sorted(axes, key=_RECOVERY_AXIS_ORDER.__getitem__))
        if axes != canonical_axes or len(set(axes)) != len(axes):
            raise ValueError(
                "cadence decision recoveries must contain at most one event per axis in canonical order",
            )
        if self.recoveries and (
            not self.admitted or not self.operational or self.first_cycle
        ):
            raise ValueError(
                "cadence decision recoveries require a later operational admission",
            )
        for recovery in self.recoveries:
            if (
                recovery.axis is TacticalCadenceRecoveryAxis.NATIVE
                and recovery.deferral_period != self.native_period
            ):
                raise ValueError(
                    "native cadence recovery origin period must equal the decision native period",
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class TacticalCadenceAttachmentState:
    """Complete committed or staged readiness state for one attachment."""

    identity: TacticalAttachmentIdentity
    native_period: int
    native_assignment_ordinal: int
    native_phase_residue: int
    last_admission_ordinal: int | None
    native_next_due: int
    native_pending_ready: bool
    lod_next_due: int
    lod_pending_ready: bool
    current_lod_period: int
    native_deferrals: int = 0
    lod_deferrals: int = 0
    native_recovery_admissions: int = 0
    lod_recovery_admissions: int = 0
    native_pending_deferral_ordinal: int | None = None
    lod_pending_deferral_ordinal: int | None = None
    native_last_recovered_deferral_ordinal: int | None = None
    native_last_recovery_ordinal: int | None = None
    lod_last_recovered_deferral_ordinal: int | None = None
    lod_last_recovery_ordinal: int | None = None
    lod_pending_deferral_period: int | None = None
    lod_last_recovered_deferral_period: int | None = None

    def __post_init__(self) -> None:
        if type(self.identity) is not TacticalAttachmentIdentity:
            raise ValueError(
                "cadence state identity must be a TacticalAttachmentIdentity",
            )
        object.__setattr__(
            self,
            "native_period",
            _require_positive_period(
                self.native_period,
                label="cadence state native_period",
            ),
        )
        object.__setattr__(
            self,
            "native_assignment_ordinal",
            _require_u64(
                self.native_assignment_ordinal,
                label="cadence state native_assignment_ordinal",
            ),
        )
        object.__setattr__(
            self,
            "native_phase_residue",
            _require_u64(
                self.native_phase_residue,
                label="cadence state native_phase_residue",
            ),
        )
        if self.native_phase_residue >= self.native_period:
            raise ValueError("cadence state native phase residue exceeds its period")
        if self.native_phase_residue != (self.native_assignment_ordinal % self.native_period):
            raise ValueError("cadence state native phase assignment is inconsistent")
        if self.last_admission_ordinal is not None:
            object.__setattr__(
                self,
                "last_admission_ordinal",
                _require_u64(
                    self.last_admission_ordinal,
                    label="cadence state last_admission_ordinal",
                ),
            )
        object.__setattr__(
            self,
            "native_next_due",
            _require_u64(
                self.native_next_due,
                label="cadence state native_next_due",
            ),
        )
        object.__setattr__(
            self,
            "native_pending_ready",
            _require_bool(
                self.native_pending_ready,
                label="cadence state native_pending_ready",
            ),
        )
        object.__setattr__(
            self,
            "lod_next_due",
            _require_u64(
                self.lod_next_due,
                label="cadence state lod_next_due",
            ),
        )
        object.__setattr__(
            self,
            "lod_pending_ready",
            _require_bool(
                self.lod_pending_ready,
                label="cadence state lod_pending_ready",
            ),
        )
        object.__setattr__(
            self,
            "current_lod_period",
            _require_positive_period(
                self.current_lod_period,
                label="cadence state current_lod_period",
            ),
        )
        for name in (
            "native_deferrals",
            "lod_deferrals",
            "native_recovery_admissions",
            "lod_recovery_admissions",
        ):
            object.__setattr__(
                self,
                name,
                _require_u64(
                    getattr(self, name),
                    label=f"cadence state {name}",
                ),
            )
        for name in (
            "native_pending_deferral_ordinal",
            "lod_pending_deferral_ordinal",
            "native_last_recovered_deferral_ordinal",
            "native_last_recovery_ordinal",
            "lod_last_recovered_deferral_ordinal",
            "lod_last_recovery_ordinal",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    _require_u64(
                        value,
                        label=f"cadence state {name}",
                    ),
                )
        for name in (
            "lod_pending_deferral_period",
            "lod_last_recovered_deferral_period",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    _require_positive_period(
                        value,
                        label=f"cadence state {name}",
                    ),
                )
        self._validate_recovery_history(
            axis="native",
            deferrals=self.native_deferrals,
            recoveries=self.native_recovery_admissions,
            pending_deferral=self.native_pending_deferral_ordinal,
            last_recovered_deferral=(self.native_last_recovered_deferral_ordinal),
            last_recovery=self.native_last_recovery_ordinal,
        )
        self._validate_recovery_history(
            axis="LOD",
            deferrals=self.lod_deferrals,
            recoveries=self.lod_recovery_admissions,
            pending_deferral=self.lod_pending_deferral_ordinal,
            last_recovered_deferral=(self.lod_last_recovered_deferral_ordinal),
            last_recovery=self.lod_last_recovery_ordinal,
        )
        if (self.lod_pending_deferral_period is None) is not (self.lod_pending_deferral_ordinal is None):
            raise ValueError(
                "cadence state LOD pending deferral period and ordinal must coexist",
            )
        if (self.lod_last_recovered_deferral_period is None) is not (self.lod_recovery_admissions == 0):
            raise ValueError(
                "cadence state LOD last recovered period must exist exactly when recovery count is nonzero",
            )

    def _validate_recovery_history(
        self,
        *,
        axis: str,
        deferrals: int,
        recoveries: int,
        pending_deferral: int | None,
        last_recovered_deferral: int | None,
        last_recovery: int | None,
    ) -> None:
        if recoveries > deferrals:
            raise ValueError(
                f"cadence state {axis} recoveries cannot exceed deferrals",
            )
        if pending_deferral is not None and deferrals <= recoveries:
            raise ValueError(
                f"cadence state {axis} recovery pending requires an unrecovered deferral",
            )
        if pending_deferral is not None and self.last_admission_ordinal is None:
            raise ValueError(
                f"cadence state {axis} pending deferral requires a prior admission",
            )
        if (
            pending_deferral is not None
            and self.last_admission_ordinal is not None
            and pending_deferral <= self.last_admission_ordinal
        ):
            raise ValueError(
                f"cadence state {axis} pending deferral must follow the last admission",
            )
        if deferrals > 0 and recoveries == 0 and pending_deferral is None:
            raise ValueError(
                f"cadence state {axis} unrecovered history requires a pending deferral origin",
            )
        if (last_recovered_deferral is None) is not (recoveries == 0) or (
            (last_recovery is None) is not (recoveries == 0)
        ):
            raise ValueError(
                f"cadence state {axis} last recovery pair must exist exactly when recovery count is nonzero",
            )
        if (
            last_recovered_deferral is not None
            and last_recovery is not None
            and last_recovered_deferral >= last_recovery
        ):
            raise ValueError(
                f"cadence state {axis} recovered deferral must precede its recovery admission",
            )
        if pending_deferral is not None and last_recovery is not None and pending_deferral <= last_recovery:
            raise ValueError(
                f"cadence state {axis} pending deferral must follow the last recovery admission",
            )
        if last_recovery is not None and (
            self.last_admission_ordinal is None or last_recovery > self.last_admission_ordinal
        ):
            raise ValueError(
                f"cadence state {axis} last recovery cannot follow the last admission",
            )

    def get_state(self) -> dict[str, Any]:
        """Return the exact JSON-compatible attachment state."""
        return {
            "identity": self.identity.get_state(),
            "native_period": self.native_period,
            "native_assignment_ordinal": self.native_assignment_ordinal,
            "native_phase_residue": self.native_phase_residue,
            "last_admission_ordinal": self.last_admission_ordinal,
            "native_next_due": self.native_next_due,
            "native_pending_ready": self.native_pending_ready,
            "lod_next_due": self.lod_next_due,
            "lod_pending_ready": self.lod_pending_ready,
            "current_lod_period": self.current_lod_period,
            "native_deferrals": self.native_deferrals,
            "lod_deferrals": self.lod_deferrals,
            "native_recovery_admissions": self.native_recovery_admissions,
            "lod_recovery_admissions": self.lod_recovery_admissions,
            "native_pending_deferral_ordinal": self.native_pending_deferral_ordinal,
            "lod_pending_deferral_ordinal": self.lod_pending_deferral_ordinal,
            "native_last_recovered_deferral_ordinal": (self.native_last_recovered_deferral_ordinal),
            "native_last_recovery_ordinal": self.native_last_recovery_ordinal,
            "lod_last_recovered_deferral_ordinal": (self.lod_last_recovered_deferral_ordinal),
            "lod_last_recovery_ordinal": self.lod_last_recovery_ordinal,
            "lod_pending_deferral_period": self.lod_pending_deferral_period,
            "lod_last_recovered_deferral_period": (self.lod_last_recovered_deferral_period),
        }


@dataclass(frozen=True, slots=True)
class TacticalCadencePlan:
    """Owner-bound immutable complete-roster interval plan."""

    ordinal: int
    decisions: tuple[TacticalCadenceDecision, ...]
    witness_promoted_observers: tuple[TacticalObserverIdentity, ...]
    _staged_states: tuple[TacticalCadenceAttachmentState, ...]
    _staged_phase_assignments: tuple[TacticalNativePhaseAssignment, ...]
    _owner_token: object

    def __post_init__(self) -> None:
        _require_u64(self.ordinal, label="cadence plan ordinal")
        for decision in self.decisions:
            if type(decision) is not TacticalCadenceDecision:
                raise ValueError(
                    "cadence plan decisions must be TacticalCadenceDecision values",
                )
            if any(
                recovery.admission_ordinal != self.ordinal
                for recovery in decision.recoveries
            ):
                raise ValueError(
                    "cadence recovery admission ordinal must equal its plan ordinal",
                )

    @property
    def staged_states(self) -> tuple[TacticalCadenceAttachmentState, ...]:
        """Return the immutable staged complete-roster state."""
        return self._staged_states

    @property
    def phase_assignments(self) -> tuple[TacticalNativePhaseAssignment, ...]:
        """Return the complete staged registry, including retired identities."""
        return self._staged_phase_assignments

    def decision_for(
        self,
        identity: TacticalAttachmentIdentity,
    ) -> TacticalCadenceDecision:
        """Return the exact staged decision for one attachment."""
        for decision in self.decisions:
            if decision.identity == identity:
                return decision
        raise KeyError(identity)

    def state_for(
        self,
        identity: TacticalAttachmentIdentity,
    ) -> TacticalCadenceAttachmentState:
        """Return the exact staged next state for one attachment."""
        for state in self._staged_states:
            if state.identity == identity:
                return state
        raise KeyError(identity)


@dataclass(frozen=True, slots=True)
class TacticalCadenceCommitPlan:
    """Fully materialized cadence state ready for an outer atomic commit."""

    ordinal: int
    _states: Mapping[
        TacticalAttachmentIdentity,
        TacticalCadenceAttachmentState,
    ]
    _phase_assignments: Mapping[
        TacticalAttachmentIdentity,
        TacticalNativePhaseAssignment,
    ]
    _interval_plan: TacticalCadencePlan
    _owner_token: object
    _fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_states",
            MappingProxyType(dict(self._states)),
        )
        object.__setattr__(
            self,
            "_phase_assignments",
            MappingProxyType(dict(self._phase_assignments)),
        )


@dataclass(frozen=True, slots=True)
class TacticalCadenceRestorePlan:
    """Validated owner-bound cadence checkpoint publication."""

    schema_version: int
    committed_ordinal: int
    complete_from_tick_zero: bool
    attachment_states: tuple[TacticalCadenceAttachmentState, ...]
    phase_assignments: tuple[TacticalNativePhaseAssignment, ...]
    phase_assignments_sha256: str
    _owner_token: object
    _fingerprint: str


def _identity_from_state(value: object, *, label: str) -> TacticalAttachmentIdentity:
    keys = {
        "reporting_side",
        "observer_unit_id",
        "source_equipment_index",
        "sensor_id",
        "modeled_role",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has invalid key topology")
    return TacticalAttachmentIdentity(
        reporting_side=value["reporting_side"],
        observer_unit_id=value["observer_unit_id"],
        source_equipment_index=value["source_equipment_index"],
        sensor_id=value["sensor_id"],
        modeled_role=value["modeled_role"],
    )


def _phase_assignment_from_state(
    value: object,
    *,
    label: str,
) -> TacticalNativePhaseAssignment:
    keys = {
        "identity",
        "native_period",
        "native_assignment_ordinal",
        "native_phase_residue",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has invalid key topology")
    return TacticalNativePhaseAssignment(
        identity=_identity_from_state(value["identity"], label=f"{label} identity"),
        native_period=value["native_period"],
        native_assignment_ordinal=value["native_assignment_ordinal"],
        native_phase_residue=value["native_phase_residue"],
    )


def _attachment_state_from_state(
    value: object,
    *,
    label: str,
) -> TacticalCadenceAttachmentState:
    keys = {
        "identity",
        "native_period",
        "native_assignment_ordinal",
        "native_phase_residue",
        "last_admission_ordinal",
        "native_next_due",
        "native_pending_ready",
        "lod_next_due",
        "lod_pending_ready",
        "current_lod_period",
        "native_deferrals",
        "lod_deferrals",
        "native_recovery_admissions",
        "lod_recovery_admissions",
        "native_pending_deferral_ordinal",
        "lod_pending_deferral_ordinal",
        "native_last_recovered_deferral_ordinal",
        "native_last_recovery_ordinal",
        "lod_last_recovered_deferral_ordinal",
        "lod_last_recovery_ordinal",
        "lod_pending_deferral_period",
        "lod_last_recovered_deferral_period",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has invalid key topology")
    last_admission = value["last_admission_ordinal"]
    if last_admission is not None:
        last_admission = _require_u64(
            last_admission,
            label=f"{label} last_admission_ordinal",
        )
    optional_ordinals: dict[str, int | None] = {}
    for name in (
        "native_pending_deferral_ordinal",
        "lod_pending_deferral_ordinal",
        "native_last_recovered_deferral_ordinal",
        "native_last_recovery_ordinal",
        "lod_last_recovered_deferral_ordinal",
        "lod_last_recovery_ordinal",
    ):
        parsed = value[name]
        if parsed is not None:
            parsed = _require_u64(parsed, label=f"{label} {name}")
        optional_ordinals[name] = parsed
    optional_periods: dict[str, int | None] = {}
    for name in (
        "lod_pending_deferral_period",
        "lod_last_recovered_deferral_period",
    ):
        parsed = value[name]
        if parsed is not None:
            parsed = _require_positive_period(parsed, label=f"{label} {name}")
        optional_periods[name] = parsed
    return TacticalCadenceAttachmentState(
        identity=_identity_from_state(
            value["identity"],
            label=f"{label} identity",
        ),
        native_period=value["native_period"],
        native_assignment_ordinal=value["native_assignment_ordinal"],
        native_phase_residue=value["native_phase_residue"],
        last_admission_ordinal=last_admission,
        native_next_due=value["native_next_due"],
        native_pending_ready=value["native_pending_ready"],
        lod_next_due=value["lod_next_due"],
        lod_pending_ready=value["lod_pending_ready"],
        current_lod_period=value["current_lod_period"],
        native_deferrals=value["native_deferrals"],
        lod_deferrals=value["lod_deferrals"],
        native_recovery_admissions=value["native_recovery_admissions"],
        lod_recovery_admissions=value["lod_recovery_admissions"],
        **optional_ordinals,
        **optional_periods,
    )


def _disposition_for(
    *,
    operational: bool,
    native_ready: bool,
    lod_ready: bool,
) -> TacticalCadenceDisposition:
    if not operational:
        return TacticalCadenceDisposition.OFFLINE
    if native_ready and lod_ready:
        return TacticalCadenceDisposition.ADMITTED
    if not native_ready and not lod_ready:
        return TacticalCadenceDisposition.DEFERRED_BOTH
    if not native_ready:
        return TacticalCadenceDisposition.DEFERRED_NATIVE
    return TacticalCadenceDisposition.DEFERRED_LOD


def _stage_recovery_evidence(
    state: TacticalCadenceAttachmentState,
    *,
    disposition: TacticalCadenceDisposition,
    ordinal: int,
) -> tuple[
    TacticalCadenceAttachmentState,
    tuple[TacticalCadenceRecovery, ...],
]:
    """Stage per-identity deferral/recovery evidence for one disposition."""
    updates: dict[str, Any] = {}
    recoveries: list[TacticalCadenceRecovery] = []
    native_deferred = disposition in {
        TacticalCadenceDisposition.DEFERRED_NATIVE,
        TacticalCadenceDisposition.DEFERRED_BOTH,
    }
    lod_deferred = disposition in {
        TacticalCadenceDisposition.DEFERRED_LOD,
        TacticalCadenceDisposition.DEFERRED_BOTH,
    }
    if native_deferred:
        updates["native_deferrals"] = _checked_add(
            state.native_deferrals,
            1,
            label="native cadence deferrals",
        )
        if state.native_pending_deferral_ordinal is None:
            updates["native_pending_deferral_ordinal"] = ordinal
    if lod_deferred:
        updates["lod_deferrals"] = _checked_add(
            state.lod_deferrals,
            1,
            label="LOD cadence deferrals",
        )
        if state.lod_pending_deferral_ordinal is None:
            updates["lod_pending_deferral_ordinal"] = ordinal
            updates["lod_pending_deferral_period"] = state.current_lod_period
    if disposition is TacticalCadenceDisposition.ADMITTED:
        updates.update(
            {
                "last_admission_ordinal": ordinal,
                "native_pending_ready": False,
                "lod_pending_ready": False,
            },
        )
        if state.native_pending_deferral_ordinal is not None:
            recoveries.append(
                TacticalCadenceRecovery(
                    axis=TacticalCadenceRecoveryAxis.NATIVE,
                    deferral_ordinal=state.native_pending_deferral_ordinal,
                    admission_ordinal=ordinal,
                    deferral_period=state.native_period,
                ),
            )
            updates.update(
                {
                    "native_recovery_admissions": _checked_add(
                        state.native_recovery_admissions,
                        1,
                        label="native cadence recovery admissions",
                    ),
                    "native_last_recovered_deferral_ordinal": (state.native_pending_deferral_ordinal),
                    "native_last_recovery_ordinal": ordinal,
                    "native_pending_deferral_ordinal": None,
                },
            )
        if state.lod_pending_deferral_ordinal is not None:
            if state.lod_pending_deferral_period is None:  # pragma: no cover
                raise RuntimeError("LOD pending recovery lacks its origin period")
            recoveries.append(
                TacticalCadenceRecovery(
                    axis=TacticalCadenceRecoveryAxis.LOD,
                    deferral_ordinal=state.lod_pending_deferral_ordinal,
                    admission_ordinal=ordinal,
                    deferral_period=state.lod_pending_deferral_period,
                ),
            )
            updates.update(
                {
                    "lod_recovery_admissions": _checked_add(
                        state.lod_recovery_admissions,
                        1,
                        label="LOD cadence recovery admissions",
                    ),
                    "lod_last_recovered_deferral_ordinal": (state.lod_pending_deferral_ordinal),
                    "lod_last_recovery_ordinal": ordinal,
                    "lod_last_recovered_deferral_period": (state.lod_pending_deferral_period),
                    "lod_pending_deferral_ordinal": None,
                    "lod_pending_deferral_period": None,
                },
            )
    staged = state if not updates else replace(state, **updates)
    return staged, tuple(recoveries)


def _advance_deadline(*, deadline: int, period: int, ordinal: int, label: str) -> int:
    if ordinal < deadline:
        return deadline
    step_count = ((ordinal - deadline) // period) + 1
    advance = step_count * period
    return _checked_add(deadline, advance, label=label)


def _next_phase_deadline(
    *,
    ordinal: int,
    period: int,
    residue: int,
    label: str,
) -> int:
    """Return the least representable deadline after ordinal in one residue."""
    remainder = ordinal % period
    delta = (residue - remainder) % period
    if delta == 0:
        delta = period
    return _checked_add(ordinal, delta, label=label)


def _apply_lod_period_change(
    state: TacticalCadenceAttachmentState,
    *,
    new_period: int,
    ordinal: int,
) -> TacticalCadenceAttachmentState:
    old_period = state.current_lod_period
    if new_period == old_period:
        return state
    last_admission = ordinal if state.last_admission_ordinal is None else state.last_admission_ordinal
    admission_deadline = _checked_add(
        last_admission,
        new_period,
        label="LOD period-change admission deadline",
    )
    if new_period < old_period:
        next_interval = _checked_add(
            ordinal,
            1,
            label="LOD promotion interval",
        )
        next_due = min(
            state.lod_next_due,
            max(next_interval, admission_deadline),
        )
    else:
        next_due = max(state.lod_next_due, admission_deadline)
    return replace(
        state,
        lod_next_due=next_due,
        current_lod_period=new_period,
    )


def _decision_to_state(decision: TacticalCadenceDecision) -> dict[str, Any]:
    return {
        "identity": decision.identity.get_state(),
        "native_period": decision.native_period,
        "native_assignment_ordinal": decision.native_assignment_ordinal,
        "native_phase_residue": decision.native_phase_residue,
        "lod_period": decision.lod_period,
        "native_ready": decision.native_ready,
        "lod_ready": decision.lod_ready,
        "operational": decision.operational,
        "admitted": decision.admitted,
        "first_cycle": decision.first_cycle,
        "disposition": decision.disposition.value,
        "recoveries": [recovery.get_state() for recovery in decision.recoveries],
    }


def _observer_to_state(observer: TacticalObserverIdentity) -> dict[str, str]:
    return {
        "reporting_side": observer.reporting_side,
        "observer_unit_id": observer.observer_unit_id,
    }


def _canonical_sha256(value: dict[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _canonical_phase_assignments(
    assignments: Iterable[TacticalNativePhaseAssignment],
) -> tuple[TacticalNativePhaseAssignment, ...]:
    return tuple(sorted(assignments, key=TacticalNativePhaseAssignment.sort_key))


def _phase_assignments_sha256(
    assignments: Iterable[TacticalNativePhaseAssignment],
) -> str:
    canonical = _canonical_phase_assignments(assignments)
    return _canonical_sha256(
        {
            "native_phase_assignments": [assignment.get_state() for assignment in canonical],
        },
    )


def _validate_phase_assignment_registry(
    assignments: tuple[TacticalNativePhaseAssignment, ...],
) -> None:
    identities = tuple(assignment.identity for assignment in assignments)
    if len(set(identities)) != len(identities):
        raise ValueError("native phase registry contains duplicate identities")
    if assignments != _canonical_phase_assignments(assignments):
        raise ValueError("native phase registry is not in canonical order")

    ordinals_by_group: dict[_NativePhaseGroupKey, list[int]] = {}
    for assignment in assignments:
        ordinals_by_group.setdefault(assignment.group, []).append(
            assignment.native_assignment_ordinal,
        )
    for ordinals in ordinals_by_group.values():
        if ordinals != list(range(len(ordinals))):
            raise ValueError(
                "native phase registry group ordinals must be contiguous from zero",
            )


def _interval_plan_fingerprint(plan: TacticalCadencePlan) -> str:
    return _canonical_sha256(
        {
            "ordinal": plan.ordinal,
            "decisions": [_decision_to_state(decision) for decision in plan.decisions],
            "witness_promoted_observers": [
                _observer_to_state(observer) for observer in plan.witness_promoted_observers
            ],
            "staged_states": [state.get_state() for state in plan.staged_states],
            "staged_phase_assignments": [assignment.get_state() for assignment in plan.phase_assignments],
        }
    )


def _commit_plan_fingerprint(plan: TacticalCadenceCommitPlan) -> str:
    return _canonical_sha256(
        {
            "ordinal": plan.ordinal,
            "states": [
                state.get_state()
                for _, state in sorted(
                    plan._states.items(),
                    key=lambda item: item[0].sort_key(),
                )
            ],
            "phase_assignments": [
                assignment.get_state()
                for assignment in _canonical_phase_assignments(
                    plan._phase_assignments.values(),
                )
            ],
            "interval_plan": _interval_plan_fingerprint(plan._interval_plan),
        }
    )


def _restore_plan_fingerprint(plan: TacticalCadenceRestorePlan) -> str:
    return _canonical_sha256(
        {
            "schema_version": plan.schema_version,
            "committed_ordinal": plan.committed_ordinal,
            "complete_from_tick_zero": plan.complete_from_tick_zero,
            "attachments": [state.get_state() for state in plan.attachment_states],
            "native_phase_assignments": [assignment.get_state() for assignment in plan.phase_assignments],
            "native_phase_assignments_sha256": plan.phase_assignments_sha256,
        }
    )


class TacticalCadenceScheduler:
    """Own deterministic attachment readiness for committed FOW intervals."""

    _STATE_KEYS = frozenset(
        {
            "schema_version",
            "committed_ordinal",
            "complete_from_tick_zero",
            "attachments",
            "native_phase_assignments",
            "native_phase_assignments_sha256",
        }
    )

    def __init__(self, *, complete_from_tick_zero: bool = True) -> None:
        self._complete_from_tick_zero = _require_bool(
            complete_from_tick_zero,
            label="cadence complete_from_tick_zero",
        )
        self._committed_ordinal = 0
        self._states: Mapping[
            TacticalAttachmentIdentity,
            TacticalCadenceAttachmentState,
        ] = {}
        self._phase_assignments: Mapping[
            TacticalAttachmentIdentity,
            TacticalNativePhaseAssignment,
        ] = {}
        self._owner_token = object()
        self._active_plan: TacticalCadencePlan | None = None
        self._active_plan_fingerprint: str | None = None
        self._prepared_commit: TacticalCadenceCommitPlan | None = None
        self._poisoned = False

    @property
    def committed_ordinal(self) -> int:
        """Return the next all-side tactical interval ordinal."""
        return self._committed_ordinal

    @property
    def complete_from_tick_zero(self) -> bool:
        """Return whether cadence history begins at fresh runtime tick zero."""
        return self._complete_from_tick_zero

    @property
    def has_active_interval(self) -> bool:
        """Return whether a complete-roster transaction is active."""
        return self._active_plan is not None

    @property
    def poisoned(self) -> bool:
        """Return whether a failed transaction has poisoned this scheduler."""
        return self._poisoned

    @property
    def attachment_states(self) -> tuple[TacticalCadenceAttachmentState, ...]:
        """Return immutable committed attachment states in canonical order."""
        return tuple(self._states.values())

    @property
    def phase_assignments(self) -> tuple[TacticalNativePhaseAssignment, ...]:
        """Return all committed assignments, including retired identities."""
        return _canonical_phase_assignments(self._phase_assignments.values())

    def state_for(
        self,
        identity: TacticalAttachmentIdentity,
    ) -> TacticalCadenceAttachmentState:
        """Return one committed attachment state."""
        if type(identity) is not TacticalAttachmentIdentity:
            raise ValueError("identity must be a TacticalAttachmentIdentity")
        return self._states[identity]

    def _validate_checkpoint_boundary(self) -> None:
        if self._active_plan is not None:
            raise RuntimeError(
                "cadence checkpoint is unavailable during an active interval",
            )
        if self._poisoned:
            raise RuntimeError(
                "cadence checkpoint is unavailable after a poisoned interval",
            )

    def _validate_active_plan(self, plan: object) -> TacticalCadencePlan:
        if self._poisoned:
            raise RuntimeError("cadence scheduler is poisoned")
        if type(plan) is not TacticalCadencePlan:
            raise TypeError("plan must be a TacticalCadencePlan")
        if plan._owner_token is not self._owner_token:
            raise ValueError("cadence plan belongs to another scheduler")
        if self._active_plan is not plan:
            raise ValueError("cadence plan is stale or is not active")
        if self._active_plan_fingerprint is None or _interval_plan_fingerprint(plan) != self._active_plan_fingerprint:
            raise ValueError("cadence plan was mutated after staging")
        return plan

    def validate_interval_plan(self, plan: TacticalCadencePlan) -> None:
        """Preflight one owner-bound active interval without mutation."""
        self._validate_active_plan(plan)

    def stage_interval(
        self,
        complete_roster: Iterable[TacticalCadenceAttachment],
    ) -> TacticalCadencePlan:
        """Stage one complete all-side roster without mutating cadence state."""
        if self._poisoned:
            raise RuntimeError("cadence scheduler is poisoned")
        if self._active_plan is not None:
            raise RuntimeError("a cadence interval is already active")
        ordinal = self._committed_ordinal
        if ordinal == _U64_MAX:
            raise ValueError("cadence committed ordinal is exhausted")

        requests = tuple(complete_roster)
        if any(type(request) is not TacticalCadenceAttachment for request in requests):
            raise ValueError(
                "complete cadence roster contains an invalid attachment",
            )
        identities = tuple(request.identity for request in requests)
        if len(set(identities)) != len(identities):
            raise ValueError("complete cadence roster contains duplicate identities")
        requests = tuple(sorted(requests, key=lambda request: request.identity.sort_key()))

        staged_assignments = dict(self._phase_assignments)
        next_group_ordinal: dict[_NativePhaseGroupKey, int] = {}
        for assignment in self._phase_assignments.values():
            candidate = _checked_add(
                assignment.native_assignment_ordinal,
                1,
                label="native phase group assignment ordinal",
            )
            next_group_ordinal[assignment.group] = max(
                next_group_ordinal.get(assignment.group, 0),
                candidate,
            )
        for request in requests:
            assignment = staged_assignments.get(request.identity)
            if assignment is not None:
                if assignment.native_period != request.native_period:
                    raise ValueError(
                        "native cadence period changed for an assigned attachment",
                    )
                continue
            group = _NativePhaseGroupKey(
                reporting_side=request.identity.reporting_side,
                sensor_id=request.identity.sensor_id,
                modeled_role=request.identity.modeled_role,
                native_period=request.native_period,
            )
            assignment_ordinal = next_group_ordinal.get(group, 0)
            assignment = TacticalNativePhaseAssignment(
                identity=request.identity,
                native_period=request.native_period,
                native_assignment_ordinal=assignment_ordinal,
                native_phase_residue=assignment_ordinal % request.native_period,
            )
            staged_assignments[request.identity] = assignment
            next_group_ordinal[group] = _checked_add(
                assignment_ordinal,
                1,
                label="native phase group assignment ordinal",
            )

        decisions: list[TacticalCadenceDecision] = []
        staged_states: list[TacticalCadenceAttachmentState] = []
        for request in requests:
            assignment = staged_assignments[request.identity]
            existing = self._states.get(request.identity)
            first_cycle = existing is None
            if existing is None:
                state = TacticalCadenceAttachmentState(
                    identity=request.identity,
                    native_period=request.native_period,
                    native_assignment_ordinal=(assignment.native_assignment_ordinal),
                    native_phase_residue=assignment.native_phase_residue,
                    last_admission_ordinal=None,
                    native_next_due=_next_phase_deadline(
                        ordinal=ordinal,
                        period=request.native_period,
                        residue=assignment.native_phase_residue,
                        label="new attachment native deadline",
                    ),
                    native_pending_ready=True,
                    lod_next_due=_checked_add(
                        ordinal,
                        request.lod_period,
                        label="new attachment LOD deadline",
                    ),
                    lod_pending_ready=True,
                    current_lod_period=request.lod_period,
                )
            else:
                if existing.native_period != request.native_period:
                    raise ValueError(
                        "native cadence period changed for an existing attachment",
                    )
                if (
                    existing.native_assignment_ordinal != assignment.native_assignment_ordinal
                    or existing.native_phase_residue != assignment.native_phase_residue
                ):
                    raise RuntimeError(
                        "committed cadence state disagrees with its phase assignment",
                    )
                state = _apply_lod_period_change(
                    existing,
                    new_period=request.lod_period,
                    ordinal=ordinal,
                )
                native_pending = state.native_pending_ready
                native_next_due = state.native_next_due
                if ordinal >= native_next_due:
                    native_pending = True
                    native_next_due = _advance_deadline(
                        deadline=native_next_due,
                        period=state.native_period,
                        ordinal=ordinal,
                        label="native cadence deadline",
                    )
                lod_pending = state.lod_pending_ready
                lod_next_due = state.lod_next_due
                if ordinal >= lod_next_due:
                    lod_pending = True
                    lod_next_due = _advance_deadline(
                        deadline=lod_next_due,
                        period=state.current_lod_period,
                        ordinal=ordinal,
                        label="LOD cadence deadline",
                    )
                state = replace(
                    state,
                    native_next_due=native_next_due,
                    native_pending_ready=native_pending,
                    lod_next_due=lod_next_due,
                    lod_pending_ready=lod_pending,
                )

            native_ready = state.native_pending_ready
            lod_ready = state.lod_pending_ready
            disposition = _disposition_for(
                operational=request.operational,
                native_ready=native_ready,
                lod_ready=lod_ready,
            )
            admitted = disposition is TacticalCadenceDisposition.ADMITTED
            state, recoveries = _stage_recovery_evidence(
                state,
                disposition=disposition,
                ordinal=ordinal,
            )
            decision = TacticalCadenceDecision(
                identity=request.identity,
                native_period=request.native_period,
                native_assignment_ordinal=assignment.native_assignment_ordinal,
                native_phase_residue=assignment.native_phase_residue,
                lod_period=request.lod_period,
                native_ready=native_ready,
                lod_ready=lod_ready,
                operational=request.operational,
                admitted=admitted,
                first_cycle=first_cycle,
                disposition=disposition,
                recoveries=recoveries,
            )
            decisions.append(decision)
            staged_states.append(state)

        plan = TacticalCadencePlan(
            ordinal=ordinal,
            decisions=tuple(decisions),
            witness_promoted_observers=(),
            _staged_states=tuple(staged_states),
            _staged_phase_assignments=_canonical_phase_assignments(
                staged_assignments.values(),
            ),
            _owner_token=self._owner_token,
        )
        self._active_plan = plan
        self._active_plan_fingerprint = _interval_plan_fingerprint(plan)
        self._prepared_commit = None
        return plan

    def stage_witness_promotions(
        self,
        plan: TacticalCadencePlan,
        observers: Iterable[TacticalObserverIdentity],
    ) -> TacticalCadencePlan:
        """Stage period-one next-interval LOD promotion for live witnesses."""
        plan = self._validate_active_plan(plan)
        if self._prepared_commit is not None:
            raise RuntimeError("cadence interval commit was already prepared")
        raw_observers = tuple(observers)
        if any(type(observer) is not TacticalObserverIdentity for observer in raw_observers):
            raise ValueError("witness promotions contain an invalid observer")
        requested = frozenset(raw_observers)
        matched: set[TacticalObserverIdentity] = set()
        staged_states: list[TacticalCadenceAttachmentState] = []
        for state in plan.staged_states:
            observer = state.identity.observer
            if observer in requested:
                matched.add(observer)
                state = _apply_lod_period_change(
                    state,
                    new_period=1,
                    ordinal=plan.ordinal,
                )
            staged_states.append(state)
        missing = requested - matched
        if missing:
            missing_text = ", ".join(
                f"{observer.reporting_side}/{observer.observer_unit_id}"
                for observer in sorted(missing, key=TacticalObserverIdentity.sort_key)
            )
            raise ValueError(
                f"witness promotion references absent observers: {missing_text}",
            )
        promoted = tuple(
            sorted(
                set(plan.witness_promoted_observers) | requested,
                key=TacticalObserverIdentity.sort_key,
            )
        )
        updated = replace(
            plan,
            witness_promoted_observers=promoted,
            _staged_states=tuple(staged_states),
        )
        self._active_plan = updated
        self._active_plan_fingerprint = _interval_plan_fingerprint(updated)
        return updated

    def prepare_interval_commit(
        self,
        plan: TacticalCadencePlan,
    ) -> TacticalCadenceCommitPlan:
        """Materialize a cadence commit without changing live state."""
        plan = self._validate_active_plan(plan)
        if self._prepared_commit is not None:
            raise RuntimeError("cadence interval commit was already prepared")
        prepared = TacticalCadenceCommitPlan(
            ordinal=plan.ordinal + 1,
            _states={state.identity: state for state in plan.staged_states},
            _phase_assignments={assignment.identity: assignment for assignment in plan.phase_assignments},
            _interval_plan=plan,
            _owner_token=self._owner_token,
            _fingerprint="",
        )
        prepared = replace(
            prepared,
            _fingerprint=_commit_plan_fingerprint(prepared),
        )
        self._prepared_commit = prepared
        return prepared

    def validate_prepared_interval_commit(
        self,
        plan: TacticalCadenceCommitPlan,
    ) -> None:
        """Revalidate a commit-ready cadence plan without mutation."""
        if type(plan) is not TacticalCadenceCommitPlan:
            raise TypeError("plan must be a TacticalCadenceCommitPlan")
        self._validate_active_plan(plan._interval_plan)
        if plan._owner_token is not self._owner_token or self._prepared_commit is not plan:
            raise ValueError("cadence commit plan is foreign or stale")
        if _commit_plan_fingerprint(plan) != plan._fingerprint:
            raise ValueError("cadence commit plan was mutated after preparation")

    def _commit_prevalidated_interval(
        self,
        plan: TacticalCadenceCommitPlan,
    ) -> None:
        """Publish a prevalidated cadence plan using only bounded swaps."""
        self._states = plan._states
        self._phase_assignments = plan._phase_assignments
        self._committed_ordinal = plan.ordinal
        self._active_plan = None
        self._active_plan_fingerprint = None
        self._prepared_commit = None

    def commit_prepared_interval(
        self,
        plan: TacticalCadenceCommitPlan,
    ) -> None:
        """Validate and publish one standalone commit-ready cadence plan."""
        self.validate_prepared_interval_commit(plan)
        self._commit_prevalidated_interval(plan)

    def commit_interval(self, plan: TacticalCadencePlan) -> None:
        """Compatibility wrapper for standalone cadence publication."""
        self.commit_prepared_interval(self.prepare_interval_commit(plan))

    def abort_interval(self, plan: TacticalCadencePlan) -> None:
        """Discard staged cadence state and poison further evidence capture."""
        self._validate_active_plan(plan)
        self._active_plan = None
        self._active_plan_fingerprint = None
        self._prepared_commit = None
        self._poisoned = True

    def get_state(self) -> dict[str, Any]:
        """Return strict JSON-compatible committed cadence state."""
        self._validate_checkpoint_boundary()
        return {
            "schema_version": CADENCE_SCHEMA_VERSION,
            "committed_ordinal": self._committed_ordinal,
            "complete_from_tick_zero": self._complete_from_tick_zero,
            "attachments": [state.get_state() for state in self.attachment_states],
            "native_phase_assignments": [assignment.get_state() for assignment in self.phase_assignments],
            "native_phase_assignments_sha256": _phase_assignments_sha256(
                self.phase_assignments,
            ),
        }

    def stage_state(self, state: object) -> TacticalCadenceRestorePlan:
        """Validate cadence checkpoint state without mutating the scheduler."""
        self._validate_checkpoint_boundary()
        if not isinstance(state, dict) or set(state) != self._STATE_KEYS:
            raise ValueError("cadence state has invalid key topology")
        schema_version = _require_u64(
            state["schema_version"],
            label="cadence schema_version",
        )
        if schema_version != CADENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported cadence schema version {schema_version}",
            )
        committed_ordinal = _require_u64(
            state["committed_ordinal"],
            label="cadence committed_ordinal",
        )
        complete = _require_bool(
            state["complete_from_tick_zero"],
            label="cadence complete_from_tick_zero",
        )
        if not self._complete_from_tick_zero and complete:
            raise ValueError(
                "cadence completeness cannot be promoted after legacy restore",
            )
        raw_phase_assignments = state["native_phase_assignments"]
        if not isinstance(raw_phase_assignments, list):
            raise ValueError("native phase assignments must be a list")
        phase_assignments = tuple(
            _phase_assignment_from_state(
                raw,
                label=f"native phase assignments[{index}]",
            )
            for index, raw in enumerate(raw_phase_assignments)
        )
        _validate_phase_assignment_registry(phase_assignments)
        phase_assignments_sha256 = _require_sha256(
            state["native_phase_assignments_sha256"],
            label="native phase assignments SHA-256",
        )
        if phase_assignments_sha256 != _phase_assignments_sha256(
            phase_assignments,
        ):
            raise ValueError("native phase assignment registry digest mismatch")
        assignments_by_identity = {assignment.identity: assignment for assignment in phase_assignments}
        raw_attachments = state["attachments"]
        if not isinstance(raw_attachments, list):
            raise ValueError("cadence attachments must be a list")
        attachment_states = tuple(
            _attachment_state_from_state(
                raw,
                label=f"cadence attachments[{index}]",
            )
            for index, raw in enumerate(raw_attachments)
        )
        identities = tuple(item.identity for item in attachment_states)
        if len(set(identities)) != len(identities):
            raise ValueError("cadence state contains duplicate attachments")
        if identities != tuple(sorted(identities, key=TacticalAttachmentIdentity.sort_key)):
            raise ValueError("cadence attachments are not in canonical order")
        if committed_ordinal == 0 and (attachment_states or phase_assignments):
            raise ValueError(
                "cadence state cannot contain assignments before its first commit",
            )
        for item in attachment_states:
            assignment = assignments_by_identity.get(item.identity)
            if assignment is None:
                raise ValueError(
                    "active cadence attachment lacks a native phase assignment",
                )
            if (
                item.native_period != assignment.native_period
                or item.native_assignment_ordinal != assignment.native_assignment_ordinal
                or item.native_phase_residue != assignment.native_phase_residue
            ):
                raise ValueError(
                    "active cadence attachment disagrees with its native phase assignment",
                )
            if item.native_next_due < committed_ordinal:
                raise ValueError("native cadence deadline precedes committed ordinal")
            if item.native_next_due % item.native_period != item.native_phase_residue:
                raise ValueError("native cadence deadline has the wrong phase residue")
            if item.lod_next_due < committed_ordinal:
                raise ValueError("LOD cadence deadline precedes committed ordinal")
            if item.last_admission_ordinal is not None and item.last_admission_ordinal >= committed_ordinal:
                raise ValueError(
                    "cadence last admission must precede committed ordinal",
                )
            if item.last_admission_ordinal is not None and item.native_next_due <= item.last_admission_ordinal:
                raise ValueError(
                    "native cadence deadline must follow the last admission",
                )
            if item.last_admission_ordinal is None and (not item.native_pending_ready or not item.lod_pending_ready):
                raise ValueError(
                    "cadence state without an admission must retain readiness",
                )
            for axis, pending, recovered_deferral, recovery in (
                (
                    "native",
                    item.native_pending_deferral_ordinal,
                    item.native_last_recovered_deferral_ordinal,
                    item.native_last_recovery_ordinal,
                ),
                (
                    "LOD",
                    item.lod_pending_deferral_ordinal,
                    item.lod_last_recovered_deferral_ordinal,
                    item.lod_last_recovery_ordinal,
                ),
            ):
                if pending is not None and pending >= committed_ordinal:
                    raise ValueError(
                        f"cadence state {axis} pending deferral must precede the committed ordinal",
                    )
                if (
                    recovered_deferral is not None
                    and recovery is not None
                    and not (recovered_deferral < recovery < committed_ordinal)
                ):
                    raise ValueError(
                        f"cadence state {axis} recovery witness must satisfy deferral < admission < committed ordinal",
                    )
        plan = TacticalCadenceRestorePlan(
            schema_version=schema_version,
            committed_ordinal=committed_ordinal,
            complete_from_tick_zero=complete,
            attachment_states=attachment_states,
            phase_assignments=phase_assignments,
            phase_assignments_sha256=phase_assignments_sha256,
            _owner_token=self._owner_token,
            _fingerprint="",
        )
        return replace(plan, _fingerprint=_restore_plan_fingerprint(plan))

    def validate_restore_plan(self, plan: TacticalCadenceRestorePlan) -> None:
        """Preflight an owner-bound restore plan without publishing it."""
        self._validate_checkpoint_boundary()
        if type(plan) is not TacticalCadenceRestorePlan:
            raise TypeError("plan must be a TacticalCadenceRestorePlan")
        if plan._owner_token is not self._owner_token:
            raise ValueError("cadence restore plan belongs to another scheduler")
        expected_fingerprint = _restore_plan_fingerprint(
            replace(plan, _fingerprint=""),
        )
        if plan._fingerprint != expected_fingerprint:
            raise ValueError("cadence restore plan was mutated after staging")
        if not self._complete_from_tick_zero and plan.complete_from_tick_zero:
            raise ValueError(
                "cadence completeness cannot be promoted after legacy restore",
            )

    def commit_state(self, plan: TacticalCadenceRestorePlan) -> None:
        """Atomically publish one owner-bound validated restore plan."""
        self.validate_restore_plan(plan)
        self._states = {state.identity: state for state in plan.attachment_states}
        self._phase_assignments = {assignment.identity: assignment for assignment in plan.phase_assignments}
        self._committed_ordinal = plan.committed_ordinal
        self._complete_from_tick_zero = plan.complete_from_tick_zero

    def set_state(self, state: object) -> None:
        """Validate and atomically restore strict cadence checkpoint state."""
        self.commit_state(self.stage_state(state))


__all__ = [
    "CADENCE_SCHEMA_VERSION",
    "TacticalAttachmentIdentity",
    "TacticalCadenceAttachment",
    "TacticalCadenceAttachmentState",
    "TacticalCadenceDecision",
    "TacticalCadenceDisposition",
    "TacticalCadencePlan",
    "TacticalCadenceRecovery",
    "TacticalCadenceRecoveryAxis",
    "TacticalCadenceRestorePlan",
    "TacticalCadenceScheduler",
    "TacticalNativePhaseAssignment",
    "TacticalObserverIdentity",
]
