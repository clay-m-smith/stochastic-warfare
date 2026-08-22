"""Immutable observer-owned track support for native radar deferrals.

The records in this module deliberately contain only scalar identity, cadence,
and estimator state.  They do not retain live units, tracks, positions, random
generators, or current target truth.  A support owner may therefore stage and
checkpoint them without creating hidden aliases into mutable simulation state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from stochastic_warfare.detection.cadence import TacticalAttachmentIdentity
from stochastic_warfare.detection.estimation import (
    constant_velocity_projection_matrices,
)
from stochastic_warfare.detection.sensor_roles import SensorModeledRole
from stochastic_warfare.detection.sensors import SensorType

_U64_MAX = (1 << 64) - 1
_SYMMETRY_RTOL = 1e-12
_SYMMETRY_ATOL = 1e-9
_PSD_RELATIVE_TOLERANCE = 1e-10


OBSERVER_TRACK_SUPPORT_RADAR_ROLES = frozenset(
    {
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        SensorModeledRole.FIRE_CONTROL_RADAR,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
        SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
    }
)


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


def _require_finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{label} must be a finite number")
    return normalized


def _require_non_negative_number(value: object, *, label: str) -> float:
    normalized = _require_finite_number(value, label=label)
    if normalized < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return normalized


def _require_vector(
    value: object,
    *,
    size: int,
    label: str,
) -> tuple[float, ...]:
    if type(value) is not tuple or len(value) != size:
        raise ValueError(f"{label} must be an immutable {size}-element tuple")
    return tuple(_require_finite_number(component, label=f"{label}[{index}]") for index, component in enumerate(value))


def _require_covariance(value: object, *, label: str) -> tuple[tuple[float, ...], ...]:
    if type(value) is not tuple or len(value) != 4:
        raise ValueError(f"{label} must be an immutable 4x4 tuple")
    rows = tuple(_require_vector(row, size=4, label=f"{label}[{index}]") for index, row in enumerate(value))
    covariance = np.asarray(rows, dtype=np.float64)
    if np.any(np.diag(covariance) < 0.0):
        raise ValueError(f"{label} has a negative diagonal")
    if not np.allclose(
        covariance,
        covariance.T,
        rtol=_SYMMETRY_RTOL,
        atol=_SYMMETRY_ATOL,
    ):
        raise ValueError(f"{label} must be symmetric")
    covariance = (covariance + covariance.T) * 0.5
    eigenvalues = np.linalg.eigvalsh(covariance)
    eigen_tolerance = -_PSD_RELATIVE_TOLERANCE * max(
        1.0,
        float(np.max(np.abs(covariance))),
    )
    if float(np.min(eigenvalues)) < eigen_tolerance:
        raise ValueError(f"{label} must be positive semidefinite")
    return tuple(tuple(float(component) for component in row) for row in covariance)


def _modeled_role(identity: ObserverTrackSupportIdentity) -> SensorModeledRole:
    try:
        return SensorModeledRole(identity.attachment_identity.modeled_role)
    except ValueError as exc:
        raise ValueError(
            "observer track support modeled role is not a SensorModeledRole",
        ) from exc


def observer_track_support_role_is_supported(
    *,
    sensor_type: SensorType,
    modeled_role: SensorModeledRole,
) -> bool:
    """Return the closed Phase 118 radar-support policy decision."""
    if not isinstance(sensor_type, SensorType):
        raise ValueError("observer track support sensor_type must be a SensorType")
    if not isinstance(modeled_role, SensorModeledRole):
        raise ValueError(
            "observer track support modeled_role must be a SensorModeledRole",
        )
    return sensor_type is SensorType.RADAR and modeled_role in OBSERVER_TRACK_SUPPORT_RADAR_ROLES


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserverTrackSupportIdentity:
    """Stable identity of one observer attachment supporting one target."""

    attachment_identity: TacticalAttachmentIdentity
    target_id: str

    def __post_init__(self) -> None:
        if type(self.attachment_identity) is not TacticalAttachmentIdentity:
            raise ValueError(
                "observer track support attachment_identity must be a TacticalAttachmentIdentity",
            )
        object.__setattr__(
            self,
            "target_id",
            _require_identifier(
                self.target_id,
                label="observer track support target_id",
            ),
        )

    @property
    def key(self) -> tuple[str, str, int, str, str, str]:
        """Return the complete non-overwriting support-map key."""
        attachment = self.attachment_identity
        return (
            attachment.reporting_side,
            attachment.observer_unit_id,
            attachment.source_equipment_index,
            attachment.sensor_id,
            attachment.modeled_role,
            self.target_id,
        )

    def sort_key(self) -> tuple[bytes, bytes, int, bytes, bytes, bytes]:
        """Return canonical UTF-8 identity order for checkpoint state."""
        return (
            *self.attachment_identity.sort_key(),
            self.target_id.encode("utf-8"),
        )

    def get_state(self) -> dict[str, Any]:
        """Return strict JSON-compatible identity state."""
        return _identity_to_state(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class _ObserverTrackSupportRecord:
    """Shared immutable estimator and chronology fields."""

    identity: ObserverTrackSupportIdentity
    fusion_track_id: str
    sensor_type: SensorType
    observation_ordinal: int
    observation_time_s: float
    native_period: int
    native_phase_residue: int
    native_due_ordinal: int
    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]
    covariance: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ]

    def __post_init__(self) -> None:
        if type(self.identity) is not ObserverTrackSupportIdentity:
            raise ValueError(
                "observer track support identity must be an ObserverTrackSupportIdentity",
            )
        object.__setattr__(
            self,
            "fusion_track_id",
            _require_identifier(
                self.fusion_track_id,
                label="observer track support fusion_track_id",
            ),
        )
        if not isinstance(self.sensor_type, SensorType):
            raise ValueError(
                "observer track support sensor_type must be a SensorType",
            )
        modeled_role = _modeled_role(self.identity)
        if not observer_track_support_role_is_supported(
            sensor_type=self.sensor_type,
            modeled_role=modeled_role,
        ):
            raise ValueError(
                "observer track support requires one of the seven supported radar roles",
            )

        observation_ordinal = _require_u64(
            self.observation_ordinal,
            label="observer track support observation_ordinal",
        )
        object.__setattr__(self, "observation_ordinal", observation_ordinal)
        object.__setattr__(
            self,
            "observation_time_s",
            _require_non_negative_number(
                self.observation_time_s,
                label="observer track support observation_time_s",
            ),
        )
        native_period = _require_u64(
            self.native_period,
            label="observer track support native_period",
        )
        if native_period == 0:
            raise ValueError("observer track support native_period must be positive")
        object.__setattr__(self, "native_period", native_period)
        native_phase_residue = _require_u64(
            self.native_phase_residue,
            label="observer track support native_phase_residue",
        )
        if native_phase_residue >= native_period:
            raise ValueError(
                "observer track support native_phase_residue must be below native_period",
            )
        object.__setattr__(
            self,
            "native_phase_residue",
            native_phase_residue,
        )
        native_due_ordinal = _require_u64(
            self.native_due_ordinal,
            label="observer track support native_due_ordinal",
        )
        phase_delta = (native_phase_residue - (observation_ordinal % native_period)) % native_period
        if phase_delta == 0:
            phase_delta = native_period
        expected_due = observation_ordinal + phase_delta
        if expected_due > _U64_MAX or native_due_ordinal != expected_due:
            raise ValueError(
                "observer track support native_due_ordinal must be the exact next native deadline",
            )
        object.__setattr__(self, "native_due_ordinal", native_due_ordinal)
        position = _require_vector(
            self.position_m,
            size=2,
            label="observer track support position_m",
        )
        velocity = _require_vector(
            self.velocity_mps,
            size=2,
            label="observer track support velocity_mps",
        )
        covariance = _require_covariance(
            self.covariance,
            label="observer track support covariance",
        )
        object.__setattr__(self, "position_m", position)
        object.__setattr__(self, "velocity_mps", velocity)
        object.__setattr__(self, "covariance", covariance)

    @property
    def position_uncertainty_m(self) -> float:
        """Return RMS horizontal position uncertainty from covariance."""
        return math.sqrt(self.covariance[0][0] + self.covariance[1][1])

    def estimated_range_m(
        self,
        *,
        observer_easting_m: float,
        observer_northing_m: float,
    ) -> float:
        """Return range to the local estimate, never current target truth."""
        observer_easting = _require_finite_number(
            observer_easting_m,
            label="observer easting",
        )
        observer_northing = _require_finite_number(
            observer_northing_m,
            label="observer northing",
        )
        return math.hypot(
            self.position_m[0] - observer_easting,
            self.position_m[1] - observer_northing,
        )

    def is_within_limits(
        self,
        *,
        observer_easting_m: float,
        observer_northing_m: float,
        reach_m: float,
        max_position_uncertainty_m: float,
    ) -> bool:
        """Return whether uncertainty is bounded and reach is conservative."""
        reach = _require_non_negative_number(reach_m, label="observer support reach_m")
        max_uncertainty = _require_non_negative_number(
            max_position_uncertainty_m,
            label="observer support max_position_uncertainty_m",
        )
        uncertainty = self.position_uncertainty_m
        estimated_range = self.estimated_range_m(
            observer_easting_m=observer_easting_m,
            observer_northing_m=observer_northing_m,
        )
        return uncertainty < max_uncertainty and estimated_range + uncertainty <= reach


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserverTrackSupportState(_ObserverTrackSupportRecord):
    """A successful attachment measurement retained until native readiness."""

    def project(
        self,
        *,
        projection_ordinal: int,
        projection_time_s: float,
        process_noise_std_mps2: float,
    ) -> ObserverTrackSupportEvidence:
        """Project a deferred support record deterministically without RNG."""
        ordinal = _require_u64(
            projection_ordinal,
            label="observer track support projection_ordinal",
        )
        if not self.observation_ordinal < ordinal < self.native_due_ordinal:
            raise ValueError(
                "observer track support projection ordinal must be after observation and before native due",
            )
        projection_time = _require_non_negative_number(
            projection_time_s,
            label="observer track support projection_time_s",
        )
        if projection_time < self.observation_time_s:
            raise ValueError("observer track support projection time cannot move backwards")
        process_noise = _require_non_negative_number(
            process_noise_std_mps2,
            label="observer track support process_noise_std_mps2",
        )

        elapsed_s = projection_time - self.observation_time_s
        transition, process_covariance = constant_velocity_projection_matrices(
            elapsed_s,
            process_noise,
        )
        state = np.asarray((*self.position_m, *self.velocity_mps), dtype=np.float64)
        covariance = np.asarray(self.covariance, dtype=np.float64)
        projected_state = transition @ state
        projected_covariance = transition @ covariance @ transition.T + process_covariance
        projected_covariance = (projected_covariance + projected_covariance.T) * 0.5
        if not np.all(np.isfinite(projected_state)) or not np.all(
            np.isfinite(projected_covariance),
        ):
            raise ValueError("observer track support projection must remain finite")

        return ObserverTrackSupportEvidence(
            identity=self.identity,
            fusion_track_id=self.fusion_track_id,
            sensor_type=self.sensor_type,
            observation_ordinal=self.observation_ordinal,
            observation_time_s=self.observation_time_s,
            native_period=self.native_period,
            native_phase_residue=self.native_phase_residue,
            native_due_ordinal=self.native_due_ordinal,
            projection_ordinal=ordinal,
            projection_time_s=projection_time,
            position_m=(
                float(projected_state[0]),
                float(projected_state[1]),
            ),
            velocity_mps=(
                float(projected_state[2]),
                float(projected_state[3]),
            ),
            covariance=tuple(tuple(float(component) for component in row) for row in projected_covariance),
        )

    def get_state(self) -> dict[str, Any]:
        """Return strict JSON-compatible support state."""
        return observer_track_support_state_to_state(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class ObserverTrackSupportEvidence(_ObserverTrackSupportRecord):
    """Decision-bound deterministic projection of one support record."""

    projection_ordinal: int
    projection_time_s: float

    def __post_init__(self) -> None:
        _ObserverTrackSupportRecord.__post_init__(self)
        projection_ordinal = _require_u64(
            self.projection_ordinal,
            label="observer track support projection_ordinal",
        )
        if not self.observation_ordinal < projection_ordinal < self.native_due_ordinal:
            raise ValueError(
                "observer track support projection ordinal must be after observation and before native due",
            )
        object.__setattr__(self, "projection_ordinal", projection_ordinal)
        projection_time = _require_non_negative_number(
            self.projection_time_s,
            label="observer track support projection_time_s",
        )
        if projection_time < self.observation_time_s:
            raise ValueError("observer track support projection time cannot move backwards")
        object.__setattr__(self, "projection_time_s", projection_time)

    def get_state(self) -> dict[str, Any]:
        """Return strict JSON-compatible decision evidence state."""
        return observer_track_support_evidence_to_state(self)


_IDENTITY_KEYS = frozenset(
    {
        "reporting_side",
        "observer_unit_id",
        "source_equipment_index",
        "sensor_id",
        "modeled_role",
        "target_id",
    }
)
_RECORD_KEYS = frozenset(
    {
        "identity",
        "fusion_track_id",
        "sensor_type",
        "observation_ordinal",
        "observation_time_s",
        "native_period",
        "native_phase_residue",
        "native_due_ordinal",
        "position_m",
        "velocity_mps",
        "covariance",
    }
)
_EVIDENCE_KEYS = _RECORD_KEYS | {"projection_ordinal", "projection_time_s"}


def _identity_to_state(identity: ObserverTrackSupportIdentity) -> dict[str, Any]:
    attachment = identity.attachment_identity
    return {
        "reporting_side": attachment.reporting_side,
        "observer_unit_id": attachment.observer_unit_id,
        "source_equipment_index": attachment.source_equipment_index,
        "sensor_id": attachment.sensor_id,
        "modeled_role": attachment.modeled_role,
        "target_id": identity.target_id,
    }


def _identity_from_state(value: object, *, label: str) -> ObserverTrackSupportIdentity:
    if not isinstance(value, dict) or set(value) != _IDENTITY_KEYS:
        raise ValueError(f"{label} has invalid key topology")
    return ObserverTrackSupportIdentity(
        attachment_identity=TacticalAttachmentIdentity(
            reporting_side=value["reporting_side"],
            observer_unit_id=value["observer_unit_id"],
            source_equipment_index=value["source_equipment_index"],
            sensor_id=value["sensor_id"],
            modeled_role=value["modeled_role"],
        ),
        target_id=value["target_id"],
    )


def _sensor_type_from_state(value: object, *, label: str) -> SensorType:
    if type(value) is not str:
        raise ValueError(f"{label} must name a SensorType")
    try:
        return SensorType[value]
    except KeyError as exc:
        raise ValueError(f"{label} must name a SensorType") from exc


def _tuple_from_state(value: object, *, size: int, label: str) -> tuple[object, ...]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must be a {size}-element list")
    return tuple(value)


def _covariance_from_state(value: object, *, label: str) -> tuple[tuple[object, ...], ...]:
    rows = _tuple_from_state(value, size=4, label=label)
    return tuple(_tuple_from_state(row, size=4, label=f"{label}[{index}]") for index, row in enumerate(rows))


def _record_to_state(record: _ObserverTrackSupportRecord) -> dict[str, Any]:
    return {
        "identity": _identity_to_state(record.identity),
        "fusion_track_id": record.fusion_track_id,
        "sensor_type": record.sensor_type.name,
        "observation_ordinal": record.observation_ordinal,
        "observation_time_s": record.observation_time_s,
        "native_period": record.native_period,
        "native_phase_residue": record.native_phase_residue,
        "native_due_ordinal": record.native_due_ordinal,
        "position_m": list(record.position_m),
        "velocity_mps": list(record.velocity_mps),
        "covariance": [list(row) for row in record.covariance],
    }


def _record_kwargs_from_state(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    return {
        "identity": _identity_from_state(value["identity"], label=f"{label}.identity"),
        "fusion_track_id": value["fusion_track_id"],
        "sensor_type": _sensor_type_from_state(
            value["sensor_type"],
            label=f"{label}.sensor_type",
        ),
        "observation_ordinal": value["observation_ordinal"],
        "observation_time_s": value["observation_time_s"],
        "native_period": value["native_period"],
        "native_phase_residue": value["native_phase_residue"],
        "native_due_ordinal": value["native_due_ordinal"],
        "position_m": _tuple_from_state(
            value["position_m"],
            size=2,
            label=f"{label}.position_m",
        ),
        "velocity_mps": _tuple_from_state(
            value["velocity_mps"],
            size=2,
            label=f"{label}.velocity_mps",
        ),
        "covariance": _covariance_from_state(
            value["covariance"],
            label=f"{label}.covariance",
        ),
    }


def observer_track_support_state_to_state(
    support: ObserverTrackSupportState,
) -> dict[str, Any]:
    """Return strict JSON-compatible state for one retained support."""
    if type(support) is not ObserverTrackSupportState:
        raise ValueError("support must be an ObserverTrackSupportState")
    return _record_to_state(support)


def observer_track_support_state_from_state(
    state: object,
) -> ObserverTrackSupportState:
    """Validate and restore one retained support record."""
    if not isinstance(state, dict) or set(state) != _RECORD_KEYS:
        raise ValueError("observer track support state has invalid key topology")
    return ObserverTrackSupportState(
        **_record_kwargs_from_state(
            state,
            label="observer track support state",
        ),
    )


def observer_track_support_evidence_to_state(
    evidence: ObserverTrackSupportEvidence,
) -> dict[str, Any]:
    """Return strict JSON-compatible state for decision support evidence."""
    if type(evidence) is not ObserverTrackSupportEvidence:
        raise ValueError("evidence must be an ObserverTrackSupportEvidence")
    state = _record_to_state(evidence)
    state.update(
        {
            "projection_ordinal": evidence.projection_ordinal,
            "projection_time_s": evidence.projection_time_s,
        }
    )
    return state


def observer_track_support_evidence_from_state(
    state: object,
) -> ObserverTrackSupportEvidence:
    """Validate and restore one decision-bound support projection."""
    if not isinstance(state, dict) or set(state) != _EVIDENCE_KEYS:
        raise ValueError("observer track support evidence has invalid key topology")
    return ObserverTrackSupportEvidence(
        **_record_kwargs_from_state(
            state,
            label="observer track support evidence",
        ),
        projection_ordinal=state["projection_ordinal"],
        projection_time_s=state["projection_time_s"],
    )


__all__ = [
    "OBSERVER_TRACK_SUPPORT_RADAR_ROLES",
    "ObserverTrackSupportEvidence",
    "ObserverTrackSupportIdentity",
    "ObserverTrackSupportState",
    "observer_track_support_evidence_from_state",
    "observer_track_support_evidence_to_state",
    "observer_track_support_role_is_supported",
    "observer_track_support_state_from_state",
    "observer_track_support_state_to_state",
]
