"""Fidelity-scoped exposure of immutable tactical targeting snapshots.

The simulation owns targeting decisions and fog-of-war tracks.  This module
only snapshots their latest committed state; it never performs acquisition,
target selection, or fire-control resolution.  Exact consumers receive the
full decision evidence.  A side-scoped projection receives only its own
shooters plus opaque public tracks from that side's current world view.  The
scope selects payload fidelity; caller authentication and authorization remain
the responsibility of the API boundary that invokes this module.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from stochastic_warfare.detection.estimation import TrackStatus
from stochastic_warfare.detection.identification import ContactLevel
from stochastic_warfare.detection.intel_fusion import validate_fow_track_id
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    TacticalEngagementRevalidationOutcome,
    TacticalTargetingDecision,
    TacticalTargetingRuntime,
    TargetingDisposition,
    targeting_disposition_is_targetless,
    targeting_disposition_is_valid_engagement,
    targeting_decision_from_state,
    targeting_decision_to_state,
    targeting_revalidation_outcome_from_state,
    targeting_revalidation_outcome_to_state,
)


class TargetingExposureScope(str, Enum):
    """Payload-fidelity scope attached to targeting/replay evidence."""

    PRIVILEGED_ENGINE = "PRIVILEGED_ENGINE"
    SIDE_FOW = "SIDE_FOW"


TARGETING_EXPOSURE_SCHEMA_VERSION = 118
_TARGETING_EXPOSURE_SCHEMA_KEY = "targeting_exposure_schema_version"
_PAIRED_TARGETING_ROOT_KEYS = frozenset(
    {
        "tick",
        "units",
        "scope",
        "targeting",
        "targeting_outcomes",
        "side_fow_available",
        "side_fow",
        "side_fow_associations",
    },
)
_VERSIONED_TARGETING_ROOT_KEYS = _PAIRED_TARGETING_ROOT_KEYS | {
    _TARGETING_EXPOSURE_SCHEMA_KEY,
    "fog_of_war_enabled",
}
_PAIRED_TARGETING_MARKER_KEYS = frozenset(
    {
        "fog_of_war_enabled",
        "scope",
        "side_fow_available",
        "side_fow",
        "side_fow_associations",
    },
)


class PublicTrackStatus(str, Enum):
    """Stable string-valued public projection of ``TrackStatus``."""

    TENTATIVE = TrackStatus.TENTATIVE.name
    CONFIRMED = TrackStatus.CONFIRMED.name
    COASTING = TrackStatus.COASTING.name
    STALE = TrackStatus.STALE.name
    LOST = TrackStatus.LOST.name


class PublicIdentificationLevel(str, Enum):
    """Stable string-valued public projection of ``ContactLevel``."""

    UNKNOWN = ContactLevel.UNKNOWN.name
    DETECTED = ContactLevel.DETECTED.name
    CLASSIFIED = ContactLevel.CLASSIFIED.name
    IDENTIFIED = ContactLevel.IDENTIFIED.name


def _identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def _optional_identifier(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, label=label)


def _finite_number(
    value: object,
    *,
    label: str,
    non_negative: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or (non_negative and float(value) < 0.0)
    ):
        qualifier = "finite and non-negative" if non_negative else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return float(value)


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _strict_bool(value: object, *, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _side_local_ordinals(
    decisions: Collection[TacticalTargetingDecision],
    *,
    viewer_side: str,
) -> dict[tuple[int, str, str], int]:
    """Return canonical per-battle ordinals without opposing-side cardinality."""
    side = _identifier(viewer_side, label="viewer_side")
    by_battle: dict[str, list[TacticalTargetingDecision]] = {}
    for decision in decisions:
        if decision.shooter_side == side:
            by_battle.setdefault(decision.battle_id, []).append(decision)
    ordinals: dict[tuple[int, str, str], int] = {}
    for battle_id in sorted(by_battle):
        for ordinal, decision in enumerate(
            sorted(
                by_battle[battle_id],
                key=lambda item: item.shooter_id,
            ),
        ):
            ordinals[decision.key] = ordinal
    return ordinals


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicTrackExposure:
    """Public fields for one opaque track in a side-owned world view."""

    track_id: str
    reporting_side: str
    easting_m: float
    northing_m: float
    velocity_east_mps: float
    velocity_north_mps: float
    position_uncertainty_m: float
    status: PublicTrackStatus
    identification_level: PublicIdentificationLevel
    domain_estimate: str | None
    type_estimate: str | None
    specific_estimate: str | None
    confidence: float
    first_detected_time_s: float
    last_sensor_contact_time_s: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "track_id",
            validate_fow_track_id(self.track_id, "track_id"),
        )
        _identifier(self.reporting_side, label="reporting_side")
        try:
            object.__setattr__(self, "status", PublicTrackStatus(self.status))
        except (TypeError, ValueError) as exc:
            raise ValueError("track status is not a TrackStatus name") from exc
        try:
            object.__setattr__(
                self,
                "identification_level",
                PublicIdentificationLevel(self.identification_level),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "identification_level is not a ContactLevel name",
            ) from exc
        for field_name in (
            "easting_m",
            "northing_m",
            "velocity_east_mps",
            "velocity_north_mps",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_number(getattr(self, field_name), label=field_name),
            )
        for field_name in (
            "position_uncertainty_m",
            "first_detected_time_s",
            "last_sensor_contact_time_s",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_number(
                    getattr(self, field_name),
                    label=field_name,
                    non_negative=True,
                ),
            )
        confidence = _finite_number(
            self.confidence,
            label="confidence",
            non_negative=True,
        )
        if confidence > 1.0:
            raise ValueError("confidence must be at most 1.0")
        object.__setattr__(self, "confidence", confidence)
        for field_name in (
            "domain_estimate",
            "type_estimate",
            "specific_estimate",
        ):
            _optional_identifier(getattr(self, field_name), label=field_name)
        if self.last_sensor_contact_time_s < self.first_detected_time_s:
            raise ValueError(
                "last_sensor_contact_time_s cannot precede first detection",
            )

    @classmethod
    def from_contact(
        cls,
        contact: object,
        *,
        reporting_side: str,
    ) -> PublicTrackExposure:
        """Snapshot public track fields without retaining target identity."""
        side = _identifier(reporting_side, label="reporting_side")
        track = getattr(contact, "track", None)
        if track is None:
            raise ValueError("fog-of-war contact is missing its track")
        track_side = _identifier(
            getattr(track, "side", None),
            label="track reporting side",
        )
        if track_side != side:
            raise ValueError("fog-of-war track belongs to another side")
        state = getattr(track, "state", None)
        if state is None:
            raise ValueError("fog-of-war track is missing public state")
        position = getattr(state, "position", None)
        velocity = getattr(state, "velocity", None)
        if position is None or len(position) != 2:
            raise ValueError("fog-of-war track position must contain two values")
        if velocity is None or len(velocity) != 2:
            raise ValueError("fog-of-war track velocity must contain two values")
        contact_info = getattr(contact, "contact_info", None)
        if contact_info is None:
            raise ValueError("fog-of-war contact is missing identification state")
        status = getattr(track, "status", None)
        status_name = getattr(status, "name", None)
        level = getattr(contact_info, "level", None)
        level_name = getattr(level, "name", None)
        return cls(
            track_id=getattr(track, "track_id", None),
            reporting_side=side,
            easting_m=position[0],
            northing_m=position[1],
            velocity_east_mps=velocity[0],
            velocity_north_mps=velocity[1],
            position_uncertainty_m=getattr(
                track,
                "position_uncertainty",
                None,
            ),
            status=status_name,
            identification_level=level_name,
            domain_estimate=getattr(contact_info, "domain_estimate", None),
            type_estimate=getattr(contact_info, "type_estimate", None),
            specific_estimate=getattr(
                contact_info,
                "specific_estimate",
                None,
            ),
            confidence=getattr(contact_info, "confidence", None),
            first_detected_time_s=getattr(
                contact,
                "first_detected_time",
                None,
            ),
            last_sensor_contact_time_s=getattr(
                contact,
                "last_sensor_contact_time",
                None,
            ),
        )

    def to_wire(self) -> dict[str, Any]:
        """Return JSON-compatible public track fields."""
        return {
            "track_id": self.track_id,
            "reporting_side": self.reporting_side,
            "easting_m": self.easting_m,
            "northing_m": self.northing_m,
            "velocity_east_mps": self.velocity_east_mps,
            "velocity_north_mps": self.velocity_north_mps,
            "position_uncertainty_m": self.position_uncertainty_m,
            "status": self.status.value,
            "identification_level": self.identification_level.value,
            "domain_estimate": self.domain_estimate,
            "type_estimate": self.type_estimate,
            "specific_estimate": self.specific_estimate,
            "confidence": self.confidence,
            "first_detected_time_s": self.first_detected_time_s,
            "last_sensor_contact_time_s": self.last_sensor_contact_time_s,
        }

    @classmethod
    def from_wire(cls, value: object) -> PublicTrackExposure:
        """Validate a stored public track snapshot."""
        if not isinstance(value, dict):
            raise ValueError("public track exposure must be a mapping")
        expected = {
            "track_id",
            "reporting_side",
            "easting_m",
            "northing_m",
            "velocity_east_mps",
            "velocity_north_mps",
            "position_uncertainty_m",
            "status",
            "identification_level",
            "domain_estimate",
            "type_estimate",
            "specific_estimate",
            "confidence",
            "first_detected_time_s",
            "last_sensor_contact_time_s",
        }
        if set(value) != expected:
            raise ValueError("public track exposure has invalid key topology")
        return cls(**value)


@dataclass(frozen=True, slots=True, kw_only=True)
class SideFowTargetingDecisionExposure:
    """Targeting result safe for the decision shooter's own side."""

    engine_tick: int
    logical_time_s: float
    battle_id: str
    ordinal: int
    shooter_id: str
    viewer_side: str
    target_track_id: str | None
    disposition: TargetingDisposition
    contact_source: ContactSource
    contact_time_s: float | None
    authorized_standoff_m: float
    hold_authorized: bool
    engagement_solution_valid: bool
    sensing_aware_standoff_enabled: bool
    fog_of_war_enabled: bool
    consumable: bool

    def __post_init__(self) -> None:
        _non_negative_int(self.engine_tick, label="engine_tick")
        _non_negative_int(self.ordinal, label="ordinal")
        object.__setattr__(
            self,
            "logical_time_s",
            _finite_number(
                self.logical_time_s,
                label="logical_time_s",
                non_negative=True,
            ),
        )
        _identifier(self.battle_id, label="battle_id")
        _identifier(self.shooter_id, label="shooter_id")
        _identifier(self.viewer_side, label="viewer_side")
        if self.target_track_id is not None:
            object.__setattr__(
                self,
                "target_track_id",
                validate_fow_track_id(
                    self.target_track_id,
                    "target_track_id",
                ),
            )
        if not isinstance(self.disposition, TargetingDisposition):
            raise ValueError("disposition must be a TargetingDisposition")
        if not isinstance(self.contact_source, ContactSource):
            raise ValueError("contact_source must be a ContactSource")
        if self.contact_time_s is not None:
            object.__setattr__(
                self,
                "contact_time_s",
                _finite_number(
                    self.contact_time_s,
                    label="contact_time_s",
                    non_negative=True,
                ),
            )
        object.__setattr__(
            self,
            "authorized_standoff_m",
            _finite_number(
                self.authorized_standoff_m,
                label="authorized_standoff_m",
                non_negative=True,
            ),
        )
        for field_name in (
            "hold_authorized",
            "engagement_solution_valid",
            "sensing_aware_standoff_enabled",
            "fog_of_war_enabled",
            "consumable",
        ):
            _strict_bool(getattr(self, field_name), label=field_name)
        if not self.fog_of_war_enabled:
            raise ValueError("SIDE_FOW decisions require fog of war")
        if self.target_track_id is None:
            if self.contact_source is not ContactSource.NONE or self.contact_time_s is not None:
                raise ValueError(
                    "a targetless SIDE_FOW decision cannot carry contact evidence",
                )
        elif (
            self.contact_source
            not in {
                ContactSource.FOW_OBSERVER_WITNESS,
                ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
            }
            or self.contact_time_s != self.logical_time_s
        ):
            raise ValueError(
                "a targeted SIDE_FOW decision requires same-interval FOW authority",
            )
        valid_solution = targeting_disposition_is_valid_engagement(
            self.disposition,
        )
        if self.engagement_solution_valid is not valid_solution:
            raise ValueError(
                "SIDE_FOW disposition and engagement_solution_valid disagree",
            )
        targetless = targeting_disposition_is_targetless(self.disposition)
        if targetless is not (self.target_track_id is None):
            raise ValueError(
                "SIDE_FOW disposition and target-track presence disagree",
            )
        if not self.engagement_solution_valid:
            if self.authorized_standoff_m != 0.0 or self.hold_authorized:
                raise ValueError(
                    "an invalid SIDE_FOW solution cannot authorize standoff",
                )
        if self.hold_authorized:
            if self.disposition is not (TargetingDisposition.VALID_STANDOFF_HOLD):
                raise ValueError(
                    "SIDE_FOW hold requires VALID_STANDOFF_HOLD",
                )
        elif self.disposition is TargetingDisposition.VALID_STANDOFF_HOLD:
            raise ValueError(
                "SIDE_FOW VALID_STANDOFF_HOLD requires an authorized hold",
            )

    @classmethod
    def from_decision(
        cls,
        decision: TacticalTargetingDecision,
        *,
        viewer_side: str,
        target_track_id: str | None,
        side_local_ordinal: int,
    ) -> SideFowTargetingDecisionExposure:
        """Remove target and attachment identity from one exact decision."""
        if not isinstance(decision, TacticalTargetingDecision):
            raise ValueError("decision must be TacticalTargetingDecision")
        side = _identifier(viewer_side, label="viewer_side")
        if decision.shooter_side != side:
            raise ValueError("SIDE_FOW decision belongs to another side")
        if decision.target_id is None:
            if target_track_id is not None:
                raise ValueError("targetless decision cannot reference a track")
        elif target_track_id is None:
            raise ValueError("targeted SIDE_FOW decision requires a public track")
        elif (
            decision.contact_source
            is ContactSource.FOW_OBSERVER_TRACK_SUPPORT
            and (
                decision.observer_track_support is None
                or decision.observer_track_support.fusion_track_id
                != target_track_id
            )
        ):
            raise ValueError(
                "observer track support disagrees with the public target track",
            )
        ordinal = _non_negative_int(
            side_local_ordinal,
            label="side_local_ordinal",
        )
        return cls(
            engine_tick=decision.engine_tick,
            logical_time_s=decision.logical_time_s,
            battle_id=decision.battle_id,
            ordinal=ordinal,
            shooter_id=decision.shooter_id,
            viewer_side=side,
            target_track_id=target_track_id,
            disposition=decision.disposition,
            contact_source=decision.contact_source,
            contact_time_s=decision.contact_time_s,
            authorized_standoff_m=decision.authorized_standoff_m,
            hold_authorized=decision.hold_authorized,
            engagement_solution_valid=decision.engagement_solution_valid,
            sensing_aware_standoff_enabled=(decision.sensing_aware_standoff_enabled),
            fog_of_war_enabled=decision.fog_of_war_enabled,
            consumable=decision.consumable,
        )

    def to_wire(self) -> dict[str, Any]:
        """Return the bounded side-safe wire representation."""
        return {
            "engine_tick": self.engine_tick,
            "logical_time_s": self.logical_time_s,
            "battle_id": self.battle_id,
            "ordinal": self.ordinal,
            "shooter_id": self.shooter_id,
            "viewer_side": self.viewer_side,
            "target_track_id": self.target_track_id,
            "disposition": self.disposition.value,
            "contact_source": self.contact_source.value,
            "contact_time_s": self.contact_time_s,
            "authorized_standoff_m": self.authorized_standoff_m,
            "hold_authorized": self.hold_authorized,
            "engagement_solution_valid": self.engagement_solution_valid,
            "sensing_aware_standoff_enabled": (self.sensing_aware_standoff_enabled),
            "fog_of_war_enabled": self.fog_of_war_enabled,
            "consumable": self.consumable,
        }

    @classmethod
    def from_wire(
        cls,
        value: object,
    ) -> SideFowTargetingDecisionExposure:
        """Validate a stored side-safe targeting result."""
        if not isinstance(value, dict):
            raise ValueError("SIDE_FOW targeting decision must be a mapping")
        expected = {
            "engine_tick",
            "logical_time_s",
            "battle_id",
            "ordinal",
            "shooter_id",
            "viewer_side",
            "target_track_id",
            "disposition",
            "contact_source",
            "contact_time_s",
            "authorized_standoff_m",
            "hold_authorized",
            "engagement_solution_valid",
            "sensing_aware_standoff_enabled",
            "fog_of_war_enabled",
            "consumable",
        }
        if set(value) != expected:
            raise ValueError("SIDE_FOW decision has invalid key topology")
        try:
            disposition = TargetingDisposition(value["disposition"])
            contact_source = ContactSource(value["contact_source"])
        except (TypeError, ValueError) as exc:
            raise ValueError("SIDE_FOW decision has an unknown enum") from exc
        return cls(
            **{
                **value,
                "disposition": disposition,
                "contact_source": contact_source,
            },
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SideFowEngagementRevalidationExposure:
    """Post-movement outcome safe for the decision shooter's own side."""

    engine_tick: int
    logical_time_s: float
    battle_id: str
    shooter_id: str
    viewer_side: str
    target_track_id: str
    disposition: TargetingDisposition
    revalidation_passed: bool
    fog_of_war_enabled: bool
    consumable: bool

    def __post_init__(self) -> None:
        _non_negative_int(self.engine_tick, label="engine_tick")
        object.__setattr__(
            self,
            "logical_time_s",
            _finite_number(
                self.logical_time_s,
                label="logical_time_s",
                non_negative=True,
            ),
        )
        _identifier(self.battle_id, label="battle_id")
        _identifier(self.shooter_id, label="shooter_id")
        _identifier(self.viewer_side, label="viewer_side")
        object.__setattr__(
            self,
            "target_track_id",
            validate_fow_track_id(
                self.target_track_id,
                "target_track_id",
            ),
        )
        if not isinstance(self.disposition, TargetingDisposition):
            raise ValueError("disposition must be a TargetingDisposition")
        for field_name in (
            "revalidation_passed",
            "fog_of_war_enabled",
            "consumable",
        ):
            _strict_bool(getattr(self, field_name), label=field_name)
        if not self.fog_of_war_enabled:
            raise ValueError("SIDE_FOW revalidation requires fog of war")
        if self.revalidation_passed:
            if self.disposition is not (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION):
                raise ValueError(
                    "a passed SIDE_FOW revalidation must expose VALID_ENGAGEMENT_SOLUTION",
                )
        elif targeting_disposition_is_valid_engagement(self.disposition):
            raise ValueError(
                "a failed SIDE_FOW revalidation requires a rejection disposition",
            )

    @classmethod
    def from_outcome(
        cls,
        outcome: TacticalEngagementRevalidationOutcome,
        *,
        decision: TacticalTargetingDecision,
        viewer_side: str,
        target_track_id: str,
    ) -> SideFowEngagementRevalidationExposure:
        """Remove exact target/weapon identity from one ledger outcome."""
        if not isinstance(outcome, TacticalEngagementRevalidationOutcome):
            raise ValueError(
                "outcome must be TacticalEngagementRevalidationOutcome",
            )
        if not isinstance(decision, TacticalTargetingDecision):
            raise ValueError("decision must be TacticalTargetingDecision")
        side = _identifier(viewer_side, label="viewer_side")
        if decision.shooter_side != side or outcome.key != decision.key:
            raise ValueError("SIDE_FOW revalidation belongs to another decision")
        if (
            not decision.engagement_solution_valid
            or outcome.logical_time_s != decision.logical_time_s
            or outcome.fog_of_war_enabled is not decision.fog_of_war_enabled
            or outcome.consumable is not decision.consumable
            or outcome.target_id != decision.target_id
            or outcome.weapon_id != decision.weapon_id
            or outcome.weapon_source_equipment_index != decision.weapon_source_equipment_index
            or outcome.weapon_modeled_role is not decision.weapon_modeled_role
            or outcome.ammunition_id != decision.ammunition_id
        ):
            raise ValueError("revalidation identity disagrees with decision")
        return cls(
            engine_tick=outcome.engine_tick,
            logical_time_s=outcome.logical_time_s,
            battle_id=outcome.battle_id,
            shooter_id=outcome.shooter_id,
            viewer_side=side,
            target_track_id=target_track_id,
            disposition=outcome.disposition,
            revalidation_passed=outcome.revalidation_passed,
            fog_of_war_enabled=outcome.fog_of_war_enabled,
            consumable=outcome.consumable,
        )

    def to_wire(self) -> dict[str, Any]:
        """Return the identity-bounded public outcome."""
        return {
            "engine_tick": self.engine_tick,
            "logical_time_s": self.logical_time_s,
            "battle_id": self.battle_id,
            "shooter_id": self.shooter_id,
            "viewer_side": self.viewer_side,
            "target_track_id": self.target_track_id,
            "disposition": self.disposition.value,
            "revalidation_passed": self.revalidation_passed,
            "fog_of_war_enabled": self.fog_of_war_enabled,
            "consumable": self.consumable,
        }

    @classmethod
    def from_wire(
        cls,
        value: object,
    ) -> SideFowEngagementRevalidationExposure:
        """Validate a stored identity-bounded public outcome."""
        if not isinstance(value, dict):
            raise ValueError("SIDE_FOW revalidation must be a mapping")
        expected = {
            "engine_tick",
            "logical_time_s",
            "battle_id",
            "shooter_id",
            "viewer_side",
            "target_track_id",
            "disposition",
            "revalidation_passed",
            "fog_of_war_enabled",
            "consumable",
        }
        if set(value) != expected:
            raise ValueError("SIDE_FOW revalidation has invalid key topology")
        try:
            disposition = TargetingDisposition(value["disposition"])
        except (TypeError, ValueError) as exc:
            raise ValueError("SIDE_FOW revalidation has an unknown enum") from exc
        return cls(**{**value, "disposition": disposition})


@dataclass(frozen=True, slots=True)
class PrivilegedTargetingExposure:
    """Exact latest decision evidence for engine/evaluator consumers."""

    engine_tick: int
    decisions: tuple[TacticalTargetingDecision, ...]

    def __post_init__(self) -> None:
        _non_negative_int(self.engine_tick, label="engine_tick")
        if not isinstance(self.decisions, tuple):
            raise ValueError("privileged decisions must be an immutable tuple")
        expected = tuple(sorted(self.decisions, key=lambda item: item.key))
        if self.decisions != expected:
            raise ValueError("privileged decisions are not in canonical key order")
        keys = tuple(decision.key for decision in self.decisions)
        if len(keys) != len(set(keys)):
            raise ValueError("privileged exposure contains duplicate decision keys")
        if any(decision.engine_tick != self.engine_tick for decision in self.decisions):
            raise ValueError("privileged exposure contains a cross-tick decision")
        if self.decisions:
            interval_reference = self.decisions[0]
            if any(
                decision.logical_time_s != interval_reference.logical_time_s
                or decision.fog_of_war_enabled is not interval_reference.fog_of_war_enabled
                for decision in self.decisions
            ):
                raise ValueError(
                    "privileged exposure contains an incoherent targeting interval",
                )
        decisions_by_battle: dict[str, list[TacticalTargetingDecision]] = {}
        for decision in self.decisions:
            decisions_by_battle.setdefault(decision.battle_id, []).append(decision)
        for battle_decisions in decisions_by_battle.values():
            canonical_picture = sorted(
                battle_decisions,
                key=lambda decision: (
                    decision.shooter_side,
                    decision.shooter_id,
                ),
            )
            if any(decision.ordinal != ordinal for ordinal, decision in enumerate(canonical_picture)):
                raise ValueError(
                    "privileged exposure contains a noncanonical picture ordinal",
                )

    def to_wire(self) -> list[dict[str, Any]]:
        """Return lossless exact decision evidence."""
        return [targeting_decision_to_state(item) for item in self.decisions]

    @classmethod
    def from_wire(
        cls,
        *,
        engine_tick: int,
        value: object,
    ) -> PrivilegedTargetingExposure:
        """Validate stored privileged evidence without recomputing it."""
        if not isinstance(value, list):
            raise ValueError("privileged targeting exposure must be a list")
        if any(not isinstance(item, dict) for item in value):
            raise ValueError(
                "privileged targeting exposure decisions must be mappings",
            )
        support_key_presence = {
            "observer_track_support" in item for item in value
        }
        if len(support_key_presence) > 1:
            raise ValueError(
                "privileged targeting exposure mixes pre-118 and current decision topology",
            )
        legacy_topology = support_key_presence == {False}
        return cls(
            engine_tick=engine_tick,
            decisions=tuple(
                _targeting_decision_from_stored_exposure(
                    item,
                    legacy_topology=legacy_topology,
                )
                for item in value
            ),
        )


def _targeting_decision_from_stored_exposure(
    value: dict[str, Any],
    *,
    legacy_topology: bool,
) -> TacticalTargetingDecision:
    """Decode current or exact pre-118 stored-frame decision topology.

    Replay frames persisted before Phase 118 have the current decision shape
    minus the required nullable ``observer_track_support`` key.  Normalize only
    that one historical topology at the storage boundary; the shared strict
    decoder still rejects every other omission, addition, or semantic mismatch.
    Checkpoint and live runtime decoding therefore remain format-118 strict.
    """
    if legacy_topology:
        value = {**value, "observer_track_support": None}
    return targeting_decision_from_state(value)


@dataclass(frozen=True, slots=True)
class PrivilegedEngagementRevalidationExposure:
    """Exact latest post-movement outcomes for privileged consumers."""

    engine_tick: int
    outcomes: tuple[TacticalEngagementRevalidationOutcome, ...]

    def __post_init__(self) -> None:
        _non_negative_int(self.engine_tick, label="engine_tick")
        if not isinstance(self.outcomes, tuple):
            raise ValueError("privileged outcomes must be an immutable tuple")
        expected = tuple(sorted(self.outcomes, key=lambda item: item.key))
        if self.outcomes != expected:
            raise ValueError("privileged outcomes are not in canonical key order")
        keys = tuple(outcome.key for outcome in self.outcomes)
        if len(keys) != len(set(keys)):
            raise ValueError("privileged exposure contains duplicate outcomes")
        if any(outcome.engine_tick != self.engine_tick for outcome in self.outcomes):
            raise ValueError("privileged exposure contains a cross-tick outcome")

    def to_wire(self) -> list[dict[str, Any]]:
        """Return lossless exact outcome evidence."""
        return [targeting_revalidation_outcome_to_state(outcome) for outcome in self.outcomes]

    @classmethod
    def from_wire(
        cls,
        *,
        engine_tick: int,
        value: object,
    ) -> PrivilegedEngagementRevalidationExposure:
        """Validate stored exact outcomes without recomputation."""
        if not isinstance(value, list):
            raise ValueError("privileged targeting outcomes must be a list")
        return cls(
            engine_tick=engine_tick,
            outcomes=tuple(targeting_revalidation_outcome_from_state(item) for item in value),
        )


@dataclass(frozen=True, slots=True)
class SideFowTargetingExposure:
    """One side's complete bounded targeting/track snapshot."""

    engine_tick: int
    viewer_side: str
    tracks: tuple[PublicTrackExposure, ...]
    decisions: tuple[SideFowTargetingDecisionExposure, ...]
    engagement_revalidations: tuple[
        SideFowEngagementRevalidationExposure,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        _non_negative_int(self.engine_tick, label="engine_tick")
        _identifier(self.viewer_side, label="viewer_side")
        if (
            not isinstance(self.tracks, tuple)
            or not isinstance(self.decisions, tuple)
            or not isinstance(self.engagement_revalidations, tuple)
        ):
            raise ValueError("SIDE_FOW exposure collections must be tuples")
        if self.tracks != tuple(sorted(self.tracks, key=lambda item: item.track_id)):
            raise ValueError("SIDE_FOW tracks are not canonical")
        track_ids = tuple(track.track_id for track in self.tracks)
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("SIDE_FOW exposure contains duplicate tracks")
        expected_decisions = tuple(
            sorted(
                self.decisions,
                key=lambda item: (item.engine_tick, item.battle_id, item.shooter_id),
            )
        )
        if self.decisions != expected_decisions:
            raise ValueError("SIDE_FOW decisions are not canonical")
        decision_keys = tuple((item.engine_tick, item.battle_id, item.shooter_id) for item in self.decisions)
        if len(decision_keys) != len(set(decision_keys)):
            raise ValueError("SIDE_FOW exposure contains duplicate decisions")
        expected_outcomes = tuple(
            sorted(
                self.engagement_revalidations,
                key=lambda item: (item.engine_tick, item.battle_id, item.shooter_id),
            )
        )
        if self.engagement_revalidations != expected_outcomes:
            raise ValueError("SIDE_FOW revalidations are not canonical")
        outcome_keys = tuple(
            (item.engine_tick, item.battle_id, item.shooter_id) for item in self.engagement_revalidations
        )
        if len(outcome_keys) != len(set(outcome_keys)):
            raise ValueError("SIDE_FOW exposure contains duplicate revalidations")
        known_decisions = set(decision_keys)
        decision_by_key = {(item.engine_tick, item.battle_id, item.shooter_id): item for item in self.decisions}
        known_tracks = set(track_ids)
        for track in self.tracks:
            if track.reporting_side != self.viewer_side:
                raise ValueError("SIDE_FOW exposure contains another side's track")
        for decision in self.decisions:
            if decision.engine_tick != self.engine_tick:
                raise ValueError("SIDE_FOW exposure contains a cross-tick decision")
            if decision.viewer_side != self.viewer_side:
                raise ValueError("SIDE_FOW exposure contains another side")
            if decision.target_track_id is not None and decision.target_track_id not in known_tracks:
                raise ValueError("SIDE_FOW decision references an absent track")
        if self.decisions:
            interval_logical_time_s = self.decisions[0].logical_time_s
            if any(decision.logical_time_s != interval_logical_time_s for decision in self.decisions):
                raise ValueError(
                    "SIDE_FOW exposure contains an incoherent targeting interval",
                )
        decisions_by_battle: dict[
            str,
            list[SideFowTargetingDecisionExposure],
        ] = {}
        for decision in self.decisions:
            decisions_by_battle.setdefault(decision.battle_id, []).append(decision)
        for battle_decisions in decisions_by_battle.values():
            canonical = sorted(
                battle_decisions,
                key=lambda decision: decision.shooter_id,
            )
            ordinals = [decision.ordinal for decision in canonical]
            if ordinals != list(range(len(canonical))):
                raise ValueError(
                    "SIDE_FOW picture ordinals are not canonical side-local ordinals",
                )
        for outcome in self.engagement_revalidations:
            outcome_key = (
                outcome.engine_tick,
                outcome.battle_id,
                outcome.shooter_id,
            )
            if outcome.engine_tick != self.engine_tick:
                raise ValueError("SIDE_FOW exposure contains a cross-tick outcome")
            if outcome.viewer_side != self.viewer_side:
                raise ValueError("SIDE_FOW exposure contains another side's outcome")
            if outcome_key not in known_decisions:
                raise ValueError("SIDE_FOW outcome lacks its targeting decision")
            if outcome.target_track_id not in known_tracks:
                raise ValueError("SIDE_FOW outcome references an absent track")
            decision = decision_by_key[outcome_key]
            if (
                outcome.logical_time_s != decision.logical_time_s
                or outcome.target_track_id != decision.target_track_id
                or outcome.fog_of_war_enabled is not decision.fog_of_war_enabled
                or outcome.consumable is not decision.consumable
            ):
                raise ValueError(
                    "SIDE_FOW outcome association disagrees with its decision",
                )
            if not decision.engagement_solution_valid:
                raise ValueError(
                    "SIDE_FOW revalidation requires a valid targeting solution",
                )

    def to_wire(self) -> dict[str, Any]:
        """Return a JSON-compatible side-safe snapshot."""
        return {
            "scope": TargetingExposureScope.SIDE_FOW.value,
            "viewer_side": self.viewer_side,
            "tracks": [track.to_wire() for track in self.tracks],
            "targeting": [decision.to_wire() for decision in self.decisions],
            "targeting_outcomes": [outcome.to_wire() for outcome in self.engagement_revalidations],
        }

    @classmethod
    def from_wire(
        cls,
        *,
        engine_tick: int,
        value: object,
    ) -> SideFowTargetingExposure:
        """Validate one stored SIDE_FOW snapshot."""
        if not isinstance(value, dict) or set(value) != {
            "scope",
            "viewer_side",
            "tracks",
            "targeting",
            "targeting_outcomes",
            "units",
        }:
            raise ValueError("SIDE_FOW snapshot has invalid key topology")
        if value["scope"] != TargetingExposureScope.SIDE_FOW.value:
            raise ValueError("SIDE_FOW snapshot has the wrong scope")
        if (
            not isinstance(value["tracks"], list)
            or not isinstance(
                value["targeting"],
                list,
            )
            or not isinstance(value["targeting_outcomes"], list)
        ):
            raise ValueError("SIDE_FOW track/targeting snapshots must be lists")
        return cls(
            engine_tick=engine_tick,
            viewer_side=value["viewer_side"],
            tracks=tuple(PublicTrackExposure.from_wire(item) for item in value["tracks"]),
            decisions=tuple(SideFowTargetingDecisionExposure.from_wire(item) for item in value["targeting"]),
            engagement_revalidations=tuple(
                SideFowEngagementRevalidationExposure.from_wire(item) for item in value["targeting_outcomes"]
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PrivilegedFowTrackAssociation:
    """Root-only binding between exact target identity and an opaque track."""

    reporting_side: str
    target_id: str
    track_id: str

    def __post_init__(self) -> None:
        _identifier(self.reporting_side, label="association reporting_side")
        _identifier(self.target_id, label="association target_id")
        object.__setattr__(
            self,
            "track_id",
            validate_fow_track_id(
                self.track_id,
                "association track_id",
            ),
        )

    @property
    def key(self) -> tuple[str, str]:
        """Return the canonical side/target identity."""
        return (self.reporting_side, self.target_id)


@dataclass(frozen=True, slots=True)
class TargetingExposureBundle:
    """Privileged snapshot plus optional precomputed side-safe projections."""

    privileged: PrivilegedTargetingExposure
    privileged_engagement_revalidations: PrivilegedEngagementRevalidationExposure
    side_fow_available: bool
    sides: tuple[SideFowTargetingExposure, ...]
    privileged_fow_associations: tuple[
        PrivilegedFowTrackAssociation,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        _strict_bool(self.side_fow_available, label="side_fow_available")
        if not isinstance(self.sides, tuple):
            raise ValueError("side exposures must be an immutable tuple")
        if not isinstance(self.privileged_fow_associations, tuple):
            raise ValueError(
                "privileged FOW associations must be an immutable tuple",
            )
        if self.sides != tuple(sorted(self.sides, key=lambda item: item.viewer_side)):
            raise ValueError("side exposures are not canonical")
        side_names = tuple(item.viewer_side for item in self.sides)
        if len(side_names) != len(set(side_names)):
            raise ValueError("targeting exposure contains duplicate sides")
        if not self.side_fow_available and self.sides:
            raise ValueError("disabled SIDE_FOW exposure cannot contain side views")
        expected_associations = tuple(
            sorted(
                self.privileged_fow_associations,
                key=lambda item: item.key,
            ),
        )
        if self.privileged_fow_associations != expected_associations:
            raise ValueError("privileged FOW associations are not canonical")
        association_keys = tuple(association.key for association in self.privileged_fow_associations)
        if len(association_keys) != len(set(association_keys)):
            raise ValueError("privileged FOW associations contain duplicate targets")
        association_track_keys = tuple(
            (association.reporting_side, association.track_id) for association in self.privileged_fow_associations
        )
        if len(association_track_keys) != len(set(association_track_keys)):
            raise ValueError("privileged FOW associations contain duplicate tracks")
        if not self.side_fow_available and self.privileged_fow_associations:
            raise ValueError(
                "disabled SIDE_FOW exposure cannot contain associations",
            )
        if any(association.reporting_side not in side_names for association in self.privileged_fow_associations):
            raise ValueError("privileged FOW association has no side view")
        if any(side.engine_tick != self.privileged.engine_tick for side in self.sides):
            raise ValueError("targeting exposure contains a cross-tick side view")
        if self.privileged_engagement_revalidations.engine_tick != self.privileged.engine_tick:
            raise ValueError("targeting exposure contains cross-tick outcomes")
        decision_by_key = {decision.key: decision for decision in self.privileged.decisions}
        for outcome in self.privileged_engagement_revalidations.outcomes:
            decision = decision_by_key.get(outcome.key)
            if decision is None:
                raise ValueError("targeting outcome lacks its exact decision")
            if (
                not decision.engagement_solution_valid
                or outcome.logical_time_s != decision.logical_time_s
                or outcome.fog_of_war_enabled is not decision.fog_of_war_enabled
                or outcome.consumable is not decision.consumable
                or outcome.target_id != decision.target_id
                or outcome.weapon_id != decision.weapon_id
                or outcome.weapon_source_equipment_index != decision.weapon_source_equipment_index
                or outcome.weapon_modeled_role is not decision.weapon_modeled_role
                or outcome.ammunition_id != decision.ammunition_id
            ):
                raise ValueError("targeting outcome identity disagrees with decision")

        associations_by_side: dict[
            str,
            dict[str, PrivilegedFowTrackAssociation],
        ] = {side: {} for side in side_names}
        for association in self.privileged_fow_associations:
            associations_by_side[association.reporting_side][association.target_id] = association
        privileged_decisions_by_key = {decision.key: decision for decision in self.privileged.decisions}
        privileged_outcomes_by_key = {
            outcome.key: outcome for outcome in self.privileged_engagement_revalidations.outcomes
        }
        for side in self.sides:
            associations = associations_by_side[side.viewer_side]
            associated_track_ids = {association.track_id for association in associations.values()}
            exposed_track_ids = {track.track_id for track in side.tracks}
            if associated_track_ids != exposed_track_ids:
                raise ValueError(
                    "privileged FOW associations do not exactly match side tracks",
                )

            side_decisions_by_key = {
                (decision.engine_tick, decision.battle_id, decision.shooter_id): decision for decision in side.decisions
            }
            local_ordinals = _side_local_ordinals(
                self.privileged.decisions,
                viewer_side=side.viewer_side,
            )
            expected_decision_keys = set(local_ordinals)
            if set(side_decisions_by_key) != expected_decision_keys:
                raise ValueError(
                    "SIDE_FOW decisions do not exactly match privileged decisions",
                )
            for key, public_decision in side_decisions_by_key.items():
                exact_decision = privileged_decisions_by_key[key]
                association = None if exact_decision.target_id is None else associations.get(exact_decision.target_id)
                expected_track_id = None if association is None else association.track_id
                if public_decision.target_track_id != expected_track_id:
                    raise ValueError(
                        "SIDE_FOW decision track association disagrees with its privileged target",
                    )
                expected_public_decision = (
                    SideFowTargetingDecisionExposure.from_decision(
                        exact_decision,
                        viewer_side=side.viewer_side,
                        target_track_id=expected_track_id,
                        side_local_ordinal=local_ordinals[key],
                    )
                )
                if public_decision != expected_public_decision:
                    raise ValueError(
                        "SIDE_FOW decision semantic projection disagrees with privileged evidence",
                    )

            side_outcomes_by_key = {
                (outcome.engine_tick, outcome.battle_id, outcome.shooter_id): outcome
                for outcome in side.engagement_revalidations
            }
            expected_outcome_keys = {
                outcome.key
                for outcome in self.privileged_engagement_revalidations.outcomes
                if privileged_decisions_by_key[outcome.key].shooter_side == side.viewer_side
            }
            if set(side_outcomes_by_key) != expected_outcome_keys:
                raise ValueError(
                    "SIDE_FOW outcomes do not exactly match privileged outcomes",
                )
            for key, public_outcome in side_outcomes_by_key.items():
                exact_outcome = privileged_outcomes_by_key[key]
                association = associations.get(exact_outcome.target_id)
                if association is None or public_outcome.target_track_id != association.track_id:
                    raise ValueError(
                        "SIDE_FOW outcome track association disagrees with its privileged target",
                    )
                expected_public_outcome = (
                    SideFowEngagementRevalidationExposure.from_outcome(
                        exact_outcome,
                        decision=privileged_decisions_by_key[key],
                        viewer_side=side.viewer_side,
                        target_track_id=association.track_id,
                    )
                )
                if public_outcome != expected_public_outcome:
                    raise ValueError(
                        "SIDE_FOW outcome semantic projection disagrees with privileged evidence",
                    )

    def to_wire(
        self,
        *,
        unit_frames: Collection[Mapping[str, Any]],
        fog_of_war_enabled: bool,
    ) -> dict[str, Any]:
        """Return storage payloads with side unit frames filtered up front."""
        declared_fow_enabled = _strict_bool(
            fog_of_war_enabled,
            label="fog_of_war_enabled",
        )
        if declared_fow_enabled is not self.side_fow_available:
            raise ValueError(
                "frame FOW mode disagrees with SIDE_FOW availability",
            )
        if any(
            decision.fog_of_war_enabled is not declared_fow_enabled
            for decision in self.privileged.decisions
        ):
            raise ValueError(
                "frame FOW mode disagrees with the targeting interval",
            )
        root_unit_frames = tuple(unit_frames)
        validate_privileged_targeting_roster(
            exposure=self,
            authoritative_unit_frames=root_unit_frames,
        )
        side_payloads: dict[str, dict[str, Any]] = {}
        for side in self.sides:
            payload = side.to_wire()
            side_unit_frames = filter_side_unit_frames(
                root_unit_frames,
                viewer_side=side.viewer_side,
            )
            validate_side_fow_targeting_roster(
                exposure=side,
                authoritative_unit_frames=root_unit_frames,
                side_unit_frames=side_unit_frames,
            )
            payload["units"] = [dict(item) for item in side_unit_frames]
            side_payloads[side.viewer_side] = payload
        association_payloads = {
            side.viewer_side: {
                association.target_id: association.track_id
                for association in self.privileged_fow_associations
                if association.reporting_side == side.viewer_side
            }
            for side in self.sides
        }
        return {
            _TARGETING_EXPOSURE_SCHEMA_KEY: (
                TARGETING_EXPOSURE_SCHEMA_VERSION
            ),
            # This runtime-mode declaration is intentionally distinct from
            # the materialized side-view availability below.  Their exact
            # agreement makes an empty FOW interval fail closed if its side
            # envelope is downgraded or removed in storage.
            "fog_of_war_enabled": declared_fow_enabled,
            "scope": TargetingExposureScope.PRIVILEGED_ENGINE.value,
            "targeting": self.privileged.to_wire(),
            "targeting_outcomes": (self.privileged_engagement_revalidations.to_wire()),
            "side_fow_available": self.side_fow_available,
            "side_fow": side_payloads,
            # This exact target-to-opaque-track binding stays at the
            # privileged storage root.  SIDE_FOW payloads and public schemas
            # never receive ground-truth target identity.
            "side_fow_associations": association_payloads,
        }


def filter_side_unit_frames(
    unit_frames: Collection[Mapping[str, Any]],
    *,
    viewer_side: str,
) -> tuple[Mapping[str, Any], ...]:
    """Return immutable copies of only a side's own ground-truth unit frames."""
    side = _identifier(viewer_side, label="viewer_side")
    filtered: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    for item in unit_frames:
        if not isinstance(item, Mapping):
            raise ValueError("unit frame must be a mapping")
        item_side = _identifier(item.get("side"), label="unit frame side")
        unit_id = _identifier(
            item.get("id", item.get("unit_id")),
            label="unit frame ID",
        )
        if unit_id in seen_ids:
            raise ValueError("unit frames contain a duplicate unit ID")
        seen_ids.add(unit_id)
        if item_side == side:
            filtered.append(MappingProxyType(dict(item)))
    return tuple(
        sorted(
            filtered,
            key=lambda item: str(item.get("id", item.get("unit_id", ""))),
        )
    )


def _unit_frame_roster(
    unit_frames: object,
    *,
    label: str,
) -> tuple[dict[str, tuple[str, dict[str, Any]]], tuple[str, ...]]:
    """Validate unit-frame identity and return exact entries plus input order."""
    if not isinstance(unit_frames, Collection) or isinstance(unit_frames, (str, bytes, Mapping)):
        raise ValueError(f"{label} must be a unit-frame collection")
    roster: dict[str, tuple[str, dict[str, Any]]] = {}
    ordered_ids: list[str] = []
    for item in unit_frames:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} contains a non-mapping unit frame")
        compact_id = item.get("id")
        legacy_id = item.get("unit_id")
        if compact_id is not None and legacy_id is not None and compact_id != legacy_id:
            raise ValueError(f"{label} contains conflicting unit IDs")
        unit_id = _identifier(
            compact_id if compact_id is not None else legacy_id,
            label=f"{label} unit ID",
        )
        side = _identifier(item.get("side"), label=f"{label} unit side")
        if unit_id in roster:
            raise ValueError(f"{label} contains a duplicate unit ID")
        roster[unit_id] = (side, dict(item))
        ordered_ids.append(unit_id)
    return roster, tuple(ordered_ids)


def validate_privileged_targeting_roster(
    *,
    exposure: TargetingExposureBundle,
    authoritative_unit_frames: object,
) -> None:
    """Bind exact targeting identities to the authoritative ROOT unit roster."""
    if not isinstance(exposure, TargetingExposureBundle):
        raise ValueError("exposure must be a TargetingExposureBundle")
    roster, _ = _unit_frame_roster(
        authoritative_unit_frames,
        label="authoritative ROOT snapshot",
    )
    if exposure.side_fow_available:
        root_sides = {side for side, _ in roster.values()}
        exposure_sides = {side.viewer_side for side in exposure.sides}
        if exposure_sides != root_sides:
            raise ValueError(
                "SIDE_FOW snapshot sides must exactly match the ROOT roster sides",
            )
    for decision in exposure.privileged.decisions:
        shooter = roster.get(decision.shooter_id)
        if shooter is None:
            raise ValueError(
                "privileged targeting shooter is absent from the ROOT roster",
            )
        if shooter[0] != decision.shooter_side:
            raise ValueError(
                "privileged targeting shooter side disagrees with the ROOT roster",
            )
        if decision.target_id is None:
            continue
        target = roster.get(decision.target_id)
        if target is None:
            raise ValueError(
                "privileged targeting target is absent from the ROOT roster",
            )
        if target[0] != decision.target_side:
            raise ValueError(
                "privileged targeting target side disagrees with the ROOT roster",
            )
    for outcome in exposure.privileged_engagement_revalidations.outcomes:
        if outcome.shooter_id not in roster:
            raise ValueError(
                "privileged targeting outcome shooter is absent from the ROOT roster",
            )
        if outcome.target_id not in roster:
            raise ValueError(
                "privileged targeting outcome target is absent from the ROOT roster",
            )
    for association in exposure.privileged_fow_associations:
        target = roster.get(association.target_id)
        # Sensor-only contacts such as decoys need not be unit frames.  When
        # the association does name a roster unit, however, it cannot bind a
        # side's public track to that same side's ground-truth unit.
        if target is not None and target[0] == association.reporting_side:
            raise ValueError(
                "privileged FOW association cannot bind a viewer-side target",
            )


def validate_side_fow_targeting_roster(
    *,
    exposure: SideFowTargetingExposure,
    authoritative_unit_frames: object,
    side_unit_frames: object,
) -> None:
    """Bind a bounded projection to ROOT identities without trusting its labels."""
    if not isinstance(exposure, SideFowTargetingExposure):
        raise ValueError("exposure must be a SideFowTargetingExposure")
    root, _ = _unit_frame_roster(
        authoritative_unit_frames,
        label="authoritative ROOT snapshot",
    )
    side_roster, side_order = _unit_frame_roster(
        side_unit_frames,
        label="SIDE_FOW unit snapshot",
    )
    expected_ids = tuple(sorted(unit_id for unit_id, (side, _) in root.items() if side == exposure.viewer_side))
    if side_order != expected_ids or set(side_roster) != set(expected_ids):
        raise ValueError(
            "SIDE_FOW unit snapshot does not match the viewer's ROOT roster",
        )
    for unit_id in expected_ids:
        if side_roster[unit_id] != root[unit_id]:
            raise ValueError(
                "SIDE_FOW unit snapshot disagrees with its ROOT unit frame",
            )
    root_ids = frozenset(root)
    if any(track.track_id in root_ids for track in exposure.tracks):
        raise ValueError(
            "SIDE_FOW track IDs must be opaque from every ROOT unit ID",
        )
    viewer_unit_ids = frozenset(expected_ids)
    if any(decision.shooter_id not in viewer_unit_ids for decision in exposure.decisions):
        raise ValueError(
            "SIDE_FOW targeting shooter is not a viewer-side ROOT unit",
        )
    if any(outcome.shooter_id not in viewer_unit_ids for outcome in exposure.engagement_revalidations):
        raise ValueError(
            "SIDE_FOW targeting outcome shooter is not a viewer-side ROOT unit",
        )


@dataclass(frozen=True, slots=True)
class DecodedSideFowTargetingExposure:
    """Validated stored side projection and its already scoped unit frames."""

    exposure: SideFowTargetingExposure
    unit_frames: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class DecodedStoredTargetingExposure:
    """One atomically validated stored root bundle and scoped unit snapshots."""

    bundle: TargetingExposureBundle
    root_unit_frames: tuple[Mapping[str, Any], ...]
    side_unit_frames: Mapping[
        str,
        tuple[Mapping[str, Any], ...],
    ]

    def for_side(
        self,
        viewer_side: str,
    ) -> DecodedSideFowTargetingExposure:
        """Return one bounded view from the already validated root bundle."""
        requested_side = _identifier(viewer_side, label="viewer_side")
        if not self.bundle.side_fow_available:
            raise ValueError(
                "legacy or non-FOW frame is explicitly privileged-only",
            )
        exposure = next(
            (
                side
                for side in self.bundle.sides
                if side.viewer_side == requested_side
            ),
            None,
        )
        unit_frames = self.side_unit_frames.get(requested_side)
        if exposure is None or unit_frames is None:
            raise ValueError("requested side has no stored SIDE_FOW snapshot")
        return DecodedSideFowTargetingExposure(
            exposure=exposure,
            unit_frames=unit_frames,
        )


def _copied_unit_frames(
    value: object,
    *,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    """Validate and defensively copy one stored unit-frame list."""
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    frames: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} contains a non-mapping frame")
        frames.append(dict(item))
    return tuple(frames)


def decode_stored_targeting_exposure(
    *,
    engine_tick: int,
    stored_frame: object,
) -> DecodedStoredTargetingExposure:
    """Decode and cross-bind one complete stored targeting frame.

    The privileged root remains the sole owner of exact target identity.  All
    stored side projections are decoded together so neither response scope can
    bypass decision/outcome, target-to-track association, or roster validation.
    """
    tick = _non_negative_int(engine_tick, label="engine_tick")
    if not isinstance(stored_frame, dict):
        raise ValueError("stored targeting frame must be a mapping")

    schema_declared = _TARGETING_EXPOSURE_SCHEMA_KEY in stored_frame
    paired_marker_declared = any(
        key in stored_frame for key in _PAIRED_TARGETING_MARKER_KEYS
    )
    if schema_declared:
        raw_schema_version = stored_frame[_TARGETING_EXPOSURE_SCHEMA_KEY]
        if (
            type(raw_schema_version) is not int
            or raw_schema_version != TARGETING_EXPOSURE_SCHEMA_VERSION
        ):
            raise ValueError(
                "targeting exposure schema version must be the strict integer 118",
            )
        if not _VERSIONED_TARGETING_ROOT_KEYS <= set(stored_frame):
            raise ValueError(
                "versioned targeting exposure requires the complete root envelope",
            )
        stored_format = "versioned"
    elif "fog_of_war_enabled" in stored_frame:
        raise ValueError(
            "unversioned targeting exposure contains a current-only FOW mode",
        )
    elif paired_marker_declared:
        if not _PAIRED_TARGETING_ROOT_KEYS <= set(stored_frame):
            raise ValueError(
                "unversioned paired targeting exposure requires the complete root envelope",
            )
        stored_format = "paired_legacy"
    else:
        stored_format = "privileged_legacy"

    if stored_format != "privileged_legacy":
        stored_tick = _non_negative_int(
            stored_frame["tick"],
            label="stored targeting frame tick",
        )
        if stored_tick != tick:
            raise ValueError(
                "stored targeting frame tick disagrees with its owner",
            )
    stored_scope = stored_frame.get(
        "scope",
        TargetingExposureScope.PRIVILEGED_ENGINE.value,
    )
    if stored_scope != TargetingExposureScope.PRIVILEGED_ENGINE.value:
        raise ValueError("stored targeting frame has the wrong root scope")

    raw_targeting = stored_frame.get("targeting", [])
    if (
        stored_format == "privileged_legacy"
        and isinstance(raw_targeting, list)
        and not raw_targeting
    ):
        raise ValueError(
            "unversioned empty targeting exposure is unsupported",
        )
    privileged = PrivilegedTargetingExposure.from_wire(
        engine_tick=tick,
        value=raw_targeting,
    )
    current_decision_topology = bool(raw_targeting) and (
        "observer_track_support" in raw_targeting[0]
    )
    if stored_format == "versioned" and raw_targeting and not current_decision_topology:
        raise ValueError(
            "versioned targeting exposure requires current decision topology",
        )
    if stored_format != "versioned" and current_decision_topology:
        raise ValueError(
            "stored current decision topology requires the format-118 root envelope",
        )
    privileged_outcomes = PrivilegedEngagementRevalidationExposure.from_wire(
        engine_tick=tick,
        value=stored_frame.get("targeting_outcomes", []),
    )
    root_unit_frames = _copied_unit_frames(
        stored_frame.get("units", []),
        label="stored privileged units",
    )
    root_only_bundle = TargetingExposureBundle(
        privileged=privileged,
        privileged_engagement_revalidations=privileged_outcomes,
        side_fow_available=False,
        sides=(),
    )
    validate_privileged_targeting_roster(
        exposure=root_only_bundle,
        authoritative_unit_frames=root_unit_frames,
    )

    availability_declared = "side_fow_available" in stored_frame
    raw_available = stored_frame.get("side_fow_available", False)
    if type(raw_available) is not bool:
        raise ValueError("stored SIDE_FOW availability must be a boolean")
    if stored_format == "versioned":
        raw_fow_enabled = stored_frame["fog_of_war_enabled"]
        if type(raw_fow_enabled) is not bool:
            raise ValueError(
                "stored targeting FOW mode must be a boolean",
            )
        if raw_fow_enabled is not raw_available:
            raise ValueError(
                "stored targeting FOW mode disagrees with SIDE_FOW availability",
            )
        if any(
            decision.fog_of_war_enabled is not raw_fow_enabled
            for decision in privileged.decisions
        ):
            raise ValueError(
                "stored targeting FOW mode disagrees with the targeting interval",
            )
    if not raw_available:
        raw_side_views = stored_frame.get("side_fow", {})
        raw_associations = stored_frame.get("side_fow_associations", {})
        if (
            not isinstance(raw_side_views, dict)
            or not isinstance(raw_associations, dict)
            or raw_side_views
            or raw_associations
        ):
            raise ValueError(
                "stored privileged-only frame must contain empty SIDE_FOW envelopes",
            )
        if not availability_declared and current_decision_topology:
            raise ValueError(
                "stored current decision topology requires SIDE_FOW availability",
            )
        if any(
            decision.observer_track_support is not None
            for decision in privileged.decisions
        ):
            raise ValueError(
                "stored observer track support lacks exact SIDE_FOW associations",
            )
        if availability_declared and any(
            decision.fog_of_war_enabled for decision in privileged.decisions
        ):
            raise ValueError(
                "stored explicit privileged-only frame cannot contain FOW decisions",
            )
        return DecodedStoredTargetingExposure(
            bundle=root_only_bundle,
            root_unit_frames=root_unit_frames,
            side_unit_frames=MappingProxyType({}),
        )

    # A SIDE_FOW-capable frame was introduced with an explicit root scope; do
    # not let omission of that field masquerade as an older privileged frame.
    if stored_frame.get("scope") != TargetingExposureScope.PRIVILEGED_ENGINE.value:
        raise ValueError("stored targeting frame has the wrong root scope")
    raw_side_views = stored_frame.get("side_fow")
    if not isinstance(raw_side_views, dict):
        raise ValueError("stored SIDE_FOW snapshots must be a mapping")
    raw_associations = stored_frame.get("side_fow_associations")
    if not isinstance(raw_associations, dict):
        raise ValueError(
            "stored SIDE_FOW snapshot lacks privileged track associations",
        )
    if set(raw_associations) != set(raw_side_views):
        raise ValueError(
            "stored SIDE_FOW association sides disagree with side snapshots",
        )
    side_names = tuple(
        sorted(
            _identifier(raw_side, label="stored SIDE_FOW side key")
            for raw_side in raw_side_views
        ),
    )
    root_roster, _ = _unit_frame_roster(
        root_unit_frames,
        label="authoritative ROOT snapshot",
    )
    root_sides = {side for side, _ in root_roster.values()}
    if set(side_names) != root_sides:
        raise ValueError(
            "stored SIDE_FOW snapshot sides must exactly match the ROOT roster sides",
        )
    support_sides = {
        decision.shooter_side
        for decision in privileged.decisions
        if decision.observer_track_support is not None
    }
    if not support_sides <= set(side_names):
        raise ValueError(
            "stored observer track support lacks its SIDE_FOW snapshot",
        )

    side_exposures: list[SideFowTargetingExposure] = []
    unit_frames_by_side: dict[str, tuple[Mapping[str, Any], ...]] = {}
    associations: list[PrivilegedFowTrackAssociation] = []
    for side in side_names:
        public = SideFowTargetingExposure.from_wire(
            engine_tick=tick,
            value=raw_side_views[side],
        )
        if public.viewer_side != side:
            raise ValueError(
                "stored SIDE_FOW snapshot viewer side disagrees with requested side",
            )
        unit_frames_by_side[side] = _copied_unit_frames(
            raw_side_views[side].get("units"),
            label="SIDE_FOW unit snapshot",
        )
        raw_side_associations = raw_associations[side]
        if not isinstance(raw_side_associations, dict):
            raise ValueError(
                "stored privileged FOW associations must be a mapping",
            )
        canonical_side_associations = tuple(
            sorted(
                (
                    _identifier(
                        raw_target_id,
                        label="stored privileged FOW target ID",
                    ),
                    raw_track_id,
                )
                for raw_target_id, raw_track_id in (
                    raw_side_associations.items()
                )
            ),
        )
        for target_id, raw_track_id in canonical_side_associations:
            associations.append(
                PrivilegedFowTrackAssociation(
                    reporting_side=side,
                    target_id=target_id,
                    track_id=raw_track_id,
                ),
            )
        side_exposures.append(public)

    bundle = TargetingExposureBundle(
        privileged=privileged,
        privileged_engagement_revalidations=privileged_outcomes,
        side_fow_available=True,
        sides=tuple(side_exposures),
        privileged_fow_associations=tuple(associations),
    )
    validate_privileged_targeting_roster(
        exposure=bundle,
        authoritative_unit_frames=root_unit_frames,
    )
    for public in bundle.sides:
        validate_side_fow_targeting_roster(
            exposure=public,
            authoritative_unit_frames=root_unit_frames,
            side_unit_frames=unit_frames_by_side[public.viewer_side],
        )

    return DecodedStoredTargetingExposure(
        bundle=bundle,
        root_unit_frames=root_unit_frames,
        side_unit_frames=MappingProxyType(unit_frames_by_side),
    )


def decode_stored_side_fow_targeting_exposure(
    *,
    engine_tick: int,
    viewer_side: str,
    stored_frame: object,
) -> DecodedSideFowTargetingExposure:
    """Decode one side from an atomically validated stored root bundle."""
    return decode_stored_targeting_exposure(
        engine_tick=engine_tick,
        stored_frame=stored_frame,
    ).for_side(
        viewer_side,
    )


def capture_targeting_exposure(
    *,
    engine_tick: int,
    runtime: TacticalTargetingRuntime,
    fog_of_war: object | None,
    fog_of_war_enabled: bool,
    viewer_sides: Collection[str],
) -> TargetingExposureBundle:
    """Snapshot current decisions and side views without recomputation.

    Only pictures from ``engine_tick`` are exposed.  Older bounded runtime
    history remains checkpoint evidence but cannot leak into a newer frame.
    """
    tick = _non_negative_int(engine_tick, label="engine_tick")
    fow_enabled = _strict_bool(
        fog_of_war_enabled,
        label="fog_of_war_enabled",
    )
    requested_sides = tuple(
        _identifier(side, label="viewer side") for side in viewer_sides
    )
    if len(requested_sides) != len(set(requested_sides)):
        raise ValueError("viewer sides must be duplicate-free")
    sides = tuple(sorted(requested_sides))
    decisions: tuple[TacticalTargetingDecision, ...] = ()
    outcomes: tuple[TacticalEngagementRevalidationOutcome, ...] = ()
    if not isinstance(runtime, TacticalTargetingRuntime):
        raise ValueError("runtime must be a TacticalTargetingRuntime")
    registered_unit_ids = frozenset(runtime.registered_unit_sides)
    registered_sides = tuple(sorted(set(runtime.registered_unit_sides.values())))
    if fow_enabled and sides != registered_sides:
        raise ValueError(
            "SIDE_FOW viewer sides must exactly match targeting registration",
        )
    decisions = tuple(
        sorted(
            (
                decision
                for picture in runtime.latest_pictures()
                if picture.engine_tick == tick
                for decision in picture.decisions
            ),
            key=lambda item: item.key,
        )
    )
    outcomes = tuple(outcome for outcome in runtime.latest_engagement_revalidations() if outcome.engine_tick == tick)
    if any(
        decision.fog_of_war_enabled is not fow_enabled
        for decision in decisions
    ):
        raise ValueError(
            "frame FOW enablement disagrees with the committed targeting interval",
        )
    privileged = PrivilegedTargetingExposure(
        engine_tick=tick,
        decisions=decisions,
    )
    privileged_outcomes = PrivilegedEngagementRevalidationExposure(
        engine_tick=tick,
        outcomes=outcomes,
    )
    if not fow_enabled:
        return TargetingExposureBundle(
            privileged=privileged,
            privileged_engagement_revalidations=privileged_outcomes,
            side_fow_available=False,
            sides=(),
        )
    if fog_of_war is None:
        raise ValueError("SIDE_FOW exposure requires a FogOfWarManager")
    peek_world_view = getattr(fog_of_war, "peek_world_view", None)
    if not callable(peek_world_view):
        raise ValueError("fog-of-war owner has no non-mutating world-view boundary")

    decision_by_key = {decision.key: decision for decision in decisions}
    side_exposures: list[SideFowTargetingExposure] = []
    privileged_fow_associations: list[PrivilegedFowTrackAssociation] = []
    for side in sides:
        world_view = peek_world_view(side)
        if world_view is None:
            contacts: Mapping[str, object] = MappingProxyType({})
        else:
            if getattr(world_view, "side", None) != side:
                raise ValueError("fog-of-war world view belongs to another side")
            contacts = getattr(world_view, "contacts", None)
            if not isinstance(contacts, Mapping):
                raise ValueError("fog-of-war contacts must be a mapping")
        public_by_target: dict[str, PublicTrackExposure] = {}
        for target_id, contact in sorted(contacts.items()):
            target_key = _identifier(target_id, label="contact target key")
            public_by_target[target_key] = PublicTrackExposure.from_contact(
                contact,
                reporting_side=side,
            )
            if (
                public_by_target[target_key].track_id == target_key
                or public_by_target[target_key].track_id in registered_unit_ids
            ):
                raise ValueError(
                    "SIDE_FOW track ID must be opaque from ground-truth unit IDs",
                )
        tracks = tuple(
            sorted(
                public_by_target.values(),
                key=lambda item: item.track_id,
            )
        )
        privileged_fow_associations.extend(
            PrivilegedFowTrackAssociation(
                reporting_side=side,
                target_id=target_id,
                track_id=public_track.track_id,
            )
            for target_id, public_track in sorted(public_by_target.items())
        )
        public_decisions: list[SideFowTargetingDecisionExposure] = []
        local_ordinals = _side_local_ordinals(
            decisions,
            viewer_side=side,
        )
        for decision in decisions:
            if decision.shooter_side != side:
                continue
            if not decision.fog_of_war_enabled:
                raise ValueError(
                    "SIDE_FOW snapshot cannot include a non-FOW decision",
                )
            public_track = None if decision.target_id is None else public_by_target.get(decision.target_id)
            if decision.target_id is not None and public_track is None:
                raise ValueError(
                    "targeting decision target is absent from the side world view",
                )
            public_decisions.append(
                SideFowTargetingDecisionExposure.from_decision(
                    decision,
                    viewer_side=side,
                    target_track_id=(None if public_track is None else public_track.track_id),
                    side_local_ordinal=local_ordinals[decision.key],
                ),
            )
        public_outcomes: list[SideFowEngagementRevalidationExposure] = []
        for outcome in outcomes:
            decision = decision_by_key.get(outcome.key)
            if decision is None:
                raise ValueError("targeting outcome lacks its exact decision")
            if decision.shooter_side != side:
                continue
            public_track = public_by_target.get(outcome.target_id)
            if public_track is None:
                raise ValueError(
                    "targeting outcome target is absent from the side world view",
                )
            public_outcomes.append(
                SideFowEngagementRevalidationExposure.from_outcome(
                    outcome,
                    decision=decision,
                    viewer_side=side,
                    target_track_id=public_track.track_id,
                ),
            )
        side_exposures.append(
            SideFowTargetingExposure(
                engine_tick=tick,
                viewer_side=side,
                tracks=tracks,
                decisions=tuple(
                    sorted(
                        public_decisions,
                        key=lambda item: (
                            item.engine_tick,
                            item.battle_id,
                            item.shooter_id,
                        ),
                    )
                ),
                engagement_revalidations=tuple(
                    sorted(
                        public_outcomes,
                        key=lambda item: (
                            item.engine_tick,
                            item.battle_id,
                            item.shooter_id,
                        ),
                    )
                ),
            )
        )
    return TargetingExposureBundle(
        privileged=privileged,
        privileged_engagement_revalidations=privileged_outcomes,
        side_fow_available=True,
        sides=tuple(side_exposures),
        privileged_fow_associations=tuple(privileged_fow_associations),
    )


__all__ = [
    "DecodedSideFowTargetingExposure",
    "DecodedStoredTargetingExposure",
    "PrivilegedEngagementRevalidationExposure",
    "PrivilegedFowTrackAssociation",
    "PrivilegedTargetingExposure",
    "PublicIdentificationLevel",
    "PublicTrackExposure",
    "PublicTrackStatus",
    "SideFowEngagementRevalidationExposure",
    "SideFowTargetingDecisionExposure",
    "TARGETING_EXPOSURE_SCHEMA_VERSION",
    "SideFowTargetingExposure",
    "TargetingExposureBundle",
    "TargetingExposureScope",
    "capture_targeting_exposure",
    "decode_stored_side_fow_targeting_exposure",
    "decode_stored_targeting_exposure",
    "filter_side_unit_frames",
    "validate_privileged_targeting_roster",
    "validate_side_fow_targeting_roster",
]
