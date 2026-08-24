"""Atomic battle checkpoint executor used by ``BattleManager``."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from stochastic_warfare.c2.ai.assessment import AssessmentRating
from stochastic_warfare.simulation.battle import (
    BattleContext,
    BattleStatePlan,
    PerformanceExecutionReceipt,
    PropagationResult,
    SituationAssessment,
    UnitLodTier,
    UnitSuppressionState,
    _DEFERRED_OODA_SCHEMA_VERSION,
)
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleCheckpointStageRequest,
    BattleExecutorOwner,
)


class DefaultBattleCheckpointExecutor:
    """Preserve checkpoint topology, validation, and atomic publication."""

    @staticmethod
    def _assessment_state(
        assessment: SituationAssessment,
    ) -> dict[str, Any]:
        if not isinstance(assessment, SituationAssessment):
            raise ValueError(
                "Battle assessment state must contain SituationAssessment instances",
            )
        force_ratio = assessment.force_ratio
        if isinstance(force_ratio, bool) or not isinstance(
            force_ratio,
            (int, float),
        ):
            raise ValueError(
                "Battle assessment force_ratio must be a non-negative number or positive infinity",
            )
        normalized_force_ratio = float(force_ratio)
        if math.isinf(normalized_force_ratio) and normalized_force_ratio > 0.0:
            force_ratio_state: float | None = None
        elif not math.isfinite(normalized_force_ratio) or normalized_force_ratio < 0.0:
            raise ValueError(
                "Battle assessment force_ratio must be a non-negative number or positive infinity",
            )
        else:
            force_ratio_state = normalized_force_ratio
        if force_ratio_state is None and assessment.force_ratio_rating is not AssessmentRating.VERY_FAVORABLE:
            raise ValueError(
                "Battle assessment unbounded force_ratio must have a VERY_FAVORABLE rating",
            )
        return {
            "unit_id": assessment.unit_id,
            "timestamp": assessment.timestamp.isoformat(),
            # ``None`` is the explicit finite-JSON representation of an
            # unbounded friendly/enemy ratio when enemy power is zero.
            "force_ratio": force_ratio_state,
            "force_ratio_rating": int(assessment.force_ratio_rating),
            "terrain_advantage": assessment.terrain_advantage,
            "terrain_rating": int(assessment.terrain_rating),
            "supply_level": assessment.supply_level,
            "supply_rating": int(assessment.supply_rating),
            "morale_level": assessment.morale_level,
            "morale_rating": int(assessment.morale_rating),
            "intel_quality": assessment.intel_quality,
            "intel_rating": int(assessment.intel_rating),
            "environmental_rating": int(
                assessment.environmental_rating,
            ),
            "c2_effectiveness": assessment.c2_effectiveness,
            "c2_rating": int(assessment.c2_rating),
            "overall_rating": int(assessment.overall_rating),
            "confidence": assessment.confidence,
            "opportunities": list(assessment.opportunities),
            "threats": list(assessment.threats),
        }

    @staticmethod
    def _propagation_state(
        result: PropagationResult,
    ) -> dict[str, Any]:
        if not isinstance(result, PropagationResult):
            raise ValueError(
                "Battle misinterpreted-order state must contain PropagationResult instances",
            )
        return {
            "success": result.success,
            "total_delay_s": result.total_delay_s,
            "was_misinterpreted": result.was_misinterpreted,
            "misinterpretation_type": result.misinterpretation_type,
            "comms_quality": result.comms_quality,
            "degraded": result.degraded,
        }

    def get_state(self, owner: BattleExecutorOwner) -> dict[str, Any]:
        """Capture battle manager state for checkpointing."""
        snapshot = owner.checkpoint_snapshot()
        if set(snapshot.pending_decisions) != set(snapshot.misinterpreted_orders):
            raise RuntimeError(
                "Current deferred-OODA state requires exactly one propagation "
                "record per pending decision",
            )
        if not set(snapshot.pending_decisions) <= set(snapshot.deferred_battle_ids):
            raise RuntimeError(
                "Current deferred-OODA state is missing battle ownership",
            )
        return {
            "deferred_ooda_schema": _DEFERRED_OODA_SCHEMA_VERSION,
            "battles": {
                bid: {
                    "battle_id": b.battle_id,
                    "start_tick": b.start_tick,
                    "start_time": b.start_time.isoformat(),
                    "involved_sides": list(b.involved_sides),
                    "active": b.active,
                    "ticks_executed": b.ticks_executed,
                    "unit_ids": sorted(b.unit_ids),
                    "wave_assignments": dict(
                        sorted(b.wave_assignments.items()),
                    ),
                    "battle_elapsed_s": b.battle_elapsed_s,
                }
                for bid, b in sorted(snapshot.battles.items())
            },
            "next_battle_id": snapshot.next_battle_id,
            "vls_launches": dict(sorted(snapshot.vls_launches.items())),
            "ammo_expended": dict(sorted(snapshot.ammo_expended.items())),
            "pending_decisions": dict(
                sorted(snapshot.pending_decisions.items()),
            ),
            "cached_assessments": {
                unit_id: self._assessment_state(assessment)
                for unit_id, assessment in sorted(
                    snapshot.cached_assessments.items(),
                )
            },
            "ticks_stationary": dict(
                sorted(snapshot.ticks_stationary.items()),
            ),
            "suppression_states": {uid: s.get_state() for uid, s in sorted(snapshot.suppression_states.items())},
            "cumulative_casualties": dict(
                sorted(snapshot.cumulative_casualties.items()),
            ),
            "undigging": dict(sorted(snapshot.undigging.items())),
            "concealment_scores": dict(
                sorted(snapshot.concealment_scores.items()),
            ),
            "env_casualty_accum": dict(
                sorted(snapshot.env_casualty_accum.items()),
            ),
            "misinterpreted_orders": {
                unit_id: self._propagation_state(result)
                for unit_id, result in sorted(
                    snapshot.misinterpreted_orders.items(),
                )
            },
            "lod_tiers": dict(sorted(snapshot.lod_tiers.items())),
            "lod_pending_tiers": dict(
                sorted(snapshot.lod_pending_tiers.items()),
            ),
            "lod_pending_counts": dict(
                sorted(snapshot.lod_pending_counts.items()),
            ),
            "lod_promoted": sorted(snapshot.lod_promoted),
            "fow_observer_unit_ids": sorted(
                snapshot.fow_observer_unit_ids,
            ),
            "performance_execution_receipt": (owner.checkpoint_performance_state()),
        }

    @staticmethod
    def _state_identifier(value: Any, *, field_name: str) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                f"Battle {field_name} must be a non-empty trimmed string",
            )
        return value

    @staticmethod
    def _state_int(
        value: Any,
        *,
        field_name: str,
        minimum: int = 0,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(
                f"Battle {field_name} must be a strict integer >= {minimum}",
            )
        return value

    @staticmethod
    def _state_float(
        value: Any,
        *,
        field_name: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(
                f"Battle {field_name} must be a finite number",
            )
        result = float(value)
        if minimum is not None and result < minimum:
            raise ValueError(
                f"Battle {field_name} must be >= {minimum}",
            )
        if maximum is not None and result > maximum:
            raise ValueError(
                f"Battle {field_name} must be <= {maximum}",
            )
        return result

    @classmethod
    def _stage_int_map(
        cls,
        raw: Any,
        *,
        field_name: str,
        minimum: int = 0,
    ) -> dict[str, int]:
        if not isinstance(raw, dict):
            raise ValueError(f"Battle {field_name} must be a mapping")
        return {
            cls._state_identifier(key, field_name=f"{field_name} key"): cls._state_int(
                value,
                field_name=f"{field_name}[{key!r}]",
                minimum=minimum,
            )
            for key, value in sorted(raw.items())
        }

    @classmethod
    def _stage_float_map(
        cls,
        raw: Any,
        *,
        field_name: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> dict[str, float]:
        if not isinstance(raw, dict):
            raise ValueError(f"Battle {field_name} must be a mapping")
        return {
            cls._state_identifier(key, field_name=f"{field_name} key"): cls._state_float(
                value,
                field_name=f"{field_name}[{key!r}]",
                minimum=minimum,
                maximum=maximum,
            )
            for key, value in sorted(raw.items())
        }

    @classmethod
    def _stage_assessment(
        cls,
        raw: Any,
        *,
        map_unit_id: str,
        checkpoint_time: datetime | None,
    ) -> SituationAssessment:
        expected_fields = {
            "unit_id",
            "timestamp",
            "force_ratio",
            "force_ratio_rating",
            "terrain_advantage",
            "terrain_rating",
            "supply_level",
            "supply_rating",
            "morale_level",
            "morale_rating",
            "intel_quality",
            "intel_rating",
            "environmental_rating",
            "c2_effectiveness",
            "c2_rating",
            "overall_rating",
            "confidence",
            "opportunities",
            "threats",
        }
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError(
                f"Battle assessment {map_unit_id!r} has invalid fields",
            )
        unit_id = cls._state_identifier(
            raw["unit_id"],
            field_name="assessment unit_id",
        )
        if unit_id != map_unit_id:
            raise ValueError(
                "Battle assessment map key disagrees with unit_id",
            )
        raw_timestamp = raw["timestamp"]
        if not isinstance(raw_timestamp, str) or not raw_timestamp:
            raise ValueError(
                "Battle assessment timestamp must be a non-empty ISO string",
            )
        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except ValueError as exc:
            raise ValueError(
                "Battle assessment timestamp is not valid ISO time",
            ) from exc
        if checkpoint_time is not None:
            try:
                after_checkpoint = timestamp > checkpoint_time
            except TypeError as exc:
                raise ValueError(
                    "Battle assessment and checkpoint timestamps have incompatible timezone awareness",
                ) from exc
            if after_checkpoint:
                raise ValueError(
                    "Battle assessment timestamp is after checkpoint time",
                )

        def rating(field_name: str) -> AssessmentRating:
            value = raw[field_name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Battle assessment {field_name} must be a strict integer",
                )
            try:
                return AssessmentRating(value)
            except ValueError as exc:
                raise ValueError(
                    f"Battle assessment {field_name} is unknown",
                ) from exc

        def strings(field_name: str) -> tuple[str, ...]:
            values = raw[field_name]
            if not isinstance(values, (list, tuple)):
                raise ValueError(
                    f"Battle assessment {field_name} must be a list",
                )
            result = tuple(
                cls._state_identifier(
                    value,
                    field_name=f"assessment {field_name}",
                )
                for value in values
            )
            if len(result) != len(set(result)):
                raise ValueError(
                    f"Battle assessment {field_name} must be unique",
                )
            return result

        force_ratio_rating = rating("force_ratio_rating")
        raw_force_ratio = raw["force_ratio"]
        if raw_force_ratio is None:
            if force_ratio_rating is not AssessmentRating.VERY_FAVORABLE:
                raise ValueError(
                    "Battle assessment unbounded force_ratio must have a VERY_FAVORABLE rating",
                )
            force_ratio = float("inf")
        else:
            force_ratio = cls._state_float(
                raw_force_ratio,
                field_name="assessment force_ratio",
                minimum=0.0,
            )

        return SituationAssessment(
            unit_id=unit_id,
            timestamp=timestamp,
            force_ratio=force_ratio,
            force_ratio_rating=force_ratio_rating,
            terrain_advantage=cls._state_float(
                raw["terrain_advantage"],
                field_name="assessment terrain_advantage",
            ),
            terrain_rating=rating("terrain_rating"),
            supply_level=cls._state_float(
                raw["supply_level"],
                field_name="assessment supply_level",
            ),
            supply_rating=rating("supply_rating"),
            morale_level=cls._state_float(
                raw["morale_level"],
                field_name="assessment morale_level",
            ),
            morale_rating=rating("morale_rating"),
            intel_quality=cls._state_float(
                raw["intel_quality"],
                field_name="assessment intel_quality",
                minimum=0.0,
                maximum=1.0,
            ),
            intel_rating=rating("intel_rating"),
            environmental_rating=rating("environmental_rating"),
            c2_effectiveness=cls._state_float(
                raw["c2_effectiveness"],
                field_name="assessment c2_effectiveness",
            ),
            c2_rating=rating("c2_rating"),
            overall_rating=rating("overall_rating"),
            confidence=cls._state_float(
                raw["confidence"],
                field_name="assessment confidence",
                minimum=0.0,
                maximum=1.0,
            ),
            opportunities=strings("opportunities"),
            threats=strings("threats"),
        )

    @classmethod
    def _stage_propagation_result(
        cls,
        raw: Any,
        *,
        unit_id: str,
    ) -> PropagationResult:
        expected_fields = {
            "success",
            "total_delay_s",
            "was_misinterpreted",
            "misinterpretation_type",
            "comms_quality",
            "degraded",
        }
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError(
                f"Battle misinterpreted order {unit_id!r} has invalid fields",
            )
        success = raw["success"]
        was_misinterpreted = raw["was_misinterpreted"]
        degraded = raw["degraded"]
        if not all(isinstance(value, bool) for value in (success, was_misinterpreted, degraded)):
            raise ValueError(
                "Battle propagation flags must be boolean",
            )
        if not success:
            raise ValueError(
                "Battle deferred-order state requires successful propagation",
            )
        raw_misinterpretation_type = raw["misinterpretation_type"]
        if was_misinterpreted:
            misinterpretation_type = cls._state_identifier(
                raw_misinterpretation_type,
                field_name="misinterpretation_type",
            )
            if misinterpretation_type not in {
                "position",
                "timing",
                "objective",
                "unit_designation",
            }:
                raise ValueError(
                    "Battle misinterpretation_type is unknown",
                )
        else:
            if raw_misinterpretation_type != "":
                raise ValueError(
                    "A correctly interpreted deferred order must have an empty effect type",
                )
            misinterpretation_type = ""
        return PropagationResult(
            success=success,
            total_delay_s=cls._state_float(
                raw["total_delay_s"],
                field_name="propagation total_delay_s",
                minimum=0.0,
            ),
            was_misinterpreted=was_misinterpreted,
            misinterpretation_type=misinterpretation_type,
            comms_quality=cls._state_float(
                raw["comms_quality"],
                field_name="propagation comms_quality",
                minimum=0.0,
                maximum=1.0,
            ),
            degraded=degraded,
        )

    def stage_state(
        self,
        owner: BattleExecutorOwner,
        request: BattleCheckpointStageRequest,
    ) -> BattleStatePlan:
        """Validate all tactical state before mutating the live manager."""
        # Validation intentionally receives a fresh mutable JSON-shaped copy;
        # injected executors can never mutate the caller's payload through the
        # immutable request view.
        state = request.detached_state()
        allow_legacy = request.allow_legacy
        expected_unit_ids = request.expected_unit_ids
        expected_sides = request.expected_sides
        required_assessment_ids = request.required_assessment_ids
        checkpoint_time = request.checkpoint_time
        checkpoint_elapsed_s = request.checkpoint_elapsed_s
        deferred_ooda_ids = request.deferred_ooda_ids
        if not isinstance(state, dict):
            raise ValueError("Battle checkpoint state must be a mapping")
        expected_keys = {
            "deferred_ooda_schema",
            "battles",
            "next_battle_id",
            "vls_launches",
            "ammo_expended",
            "pending_decisions",
            "cached_assessments",
            "ticks_stationary",
            "suppression_states",
            "cumulative_casualties",
            "undigging",
            "concealment_scores",
            "env_casualty_accum",
            "misinterpreted_orders",
            "lod_tiers",
            "lod_pending_tiers",
            "lod_pending_counts",
            "lod_promoted",
            "fow_observer_unit_ids",
            "performance_execution_receipt",
        }
        actual_keys = set(state)
        missing_keys = expected_keys - actual_keys
        invalid_missing = (
            set()
            if allow_legacy
            else missing_keys - {"deferred_ooda_schema"}
        )
        if actual_keys - expected_keys or invalid_missing:
            raise ValueError(
                "Battle checkpoint key topology is invalid: "
                f"missing={sorted(missing_keys)!r}, "
                f"extra={sorted(actual_keys - expected_keys)!r}",
            )
        has_deferred_schema = "deferred_ooda_schema" in state
        if has_deferred_schema:
            raw_deferred_schema = state["deferred_ooda_schema"]
            if (
                isinstance(raw_deferred_schema, bool)
                or not isinstance(raw_deferred_schema, int)
                or raw_deferred_schema != _DEFERRED_OODA_SCHEMA_VERSION
            ):
                raise ValueError(
                    "Battle deferred_ooda_schema is unsupported",
                )
        if checkpoint_elapsed_s is not None and (
            not math.isfinite(checkpoint_elapsed_s)
            or checkpoint_elapsed_s < 0.0
        ):
            raise ValueError(
                "Battle checkpoint elapsed time must be finite and non-negative",
            )

        raw_battles = state.get("battles", {})
        if not isinstance(raw_battles, dict):
            raise ValueError("Battle checkpoint battles must be a mapping")
        battle_fields = {
            "battle_id",
            "start_tick",
            "start_time",
            "involved_sides",
            "active",
            "ticks_executed",
            "unit_ids",
            "wave_assignments",
            "battle_elapsed_s",
        }
        battles: dict[str, BattleContext] = {}
        for battle_id, raw in sorted(raw_battles.items()):
            self._state_identifier(
                battle_id,
                field_name="battle map key",
            )
            if not isinstance(raw, dict) or (
                (not allow_legacy and set(raw) != battle_fields) or set(raw) - battle_fields
            ):
                raise ValueError(
                    f"Battle {battle_id!r} has invalid fields",
                )
            if raw.get("battle_id") != battle_id:
                raise ValueError(
                    "Battle map key disagrees with battle_id",
                )
            raw_start_time = raw.get("start_time")
            if not isinstance(raw_start_time, str) or not raw_start_time:
                raise ValueError("Battle start_time must be an ISO string")
            try:
                start_time = datetime.fromisoformat(raw_start_time)
            except ValueError as exc:
                raise ValueError(
                    f"Battle {battle_id!r} start_time is invalid",
                ) from exc
            raw_sides = raw.get("involved_sides")
            if not isinstance(raw_sides, list):
                raise ValueError("Battle involved_sides must be a list")
            involved_sides = [
                self._state_identifier(
                    side,
                    field_name="involved side",
                )
                for side in raw_sides
            ]
            if (
                len(involved_sides) < 2
                or len(involved_sides) != len(set(involved_sides))
                or (expected_sides is not None and not set(involved_sides) <= expected_sides)
            ):
                raise ValueError(
                    f"Battle {battle_id!r} has invalid side topology",
                )
            raw_unit_ids = raw.get("unit_ids", [])
            if not isinstance(raw_unit_ids, list):
                raise ValueError("Battle unit_ids must be a list")
            unit_ids = {
                self._state_identifier(
                    unit_id,
                    field_name="battle unit_id",
                )
                for unit_id in raw_unit_ids
            }
            if len(unit_ids) != len(raw_unit_ids) or (
                expected_unit_ids is not None and not unit_ids <= expected_unit_ids
            ):
                raise ValueError(
                    f"Battle {battle_id!r} has invalid unit topology",
                )
            wave_assignments = self._stage_int_map(
                raw.get("wave_assignments", {}),
                field_name="wave_assignments",
                minimum=-1,
            )
            if not set(wave_assignments) <= unit_ids:
                raise ValueError(
                    "Battle wave assignments reference units outside the battle",
                )
            active = raw.get("active")
            if not isinstance(active, bool):
                raise ValueError("Battle active must be boolean")
            battles[battle_id] = BattleContext(
                battle_id=battle_id,
                start_tick=self._state_int(
                    raw.get("start_tick"),
                    field_name="start_tick",
                ),
                start_time=start_time,
                involved_sides=involved_sides,
                active=active,
                ticks_executed=self._state_int(
                    raw.get("ticks_executed"),
                    field_name="ticks_executed",
                ),
                unit_ids=unit_ids,
                wave_assignments=wave_assignments,
                battle_elapsed_s=self._state_float(
                    raw.get("battle_elapsed_s", 0.0),
                    field_name="battle_elapsed_s",
                    minimum=0.0,
                ),
            )

        next_battle_id = self._state_int(
            state.get("next_battle_id", 0),
            field_name="next_battle_id",
        )
        allocated_ids: list[int] = []
        for battle_id in battles:
            suffix = battle_id.removeprefix("battle_")
            is_runtime_id = suffix.isascii() and suffix.isdecimal() and battle_id == f"battle_{int(suffix):04d}"
            if not is_runtime_id:
                if not allow_legacy:
                    raise ValueError(
                        "Current battle checkpoint IDs must use the runtime allocator format",
                    )
                continue
            allocated_ids.append(int(suffix))
        if allocated_ids and next_battle_id <= max(allocated_ids):
            raise ValueError(
                "Battle next_battle_id would collide with restored battle topology",
            )

        raw_assessments = state.get("cached_assessments", {})
        if not isinstance(raw_assessments, dict):
            raise ValueError(
                "Battle cached_assessments must be a mapping",
            )
        cached_assessments = {
            self._state_identifier(
                unit_id,
                field_name="assessment map key",
            ): self._stage_assessment(
                raw,
                map_unit_id=unit_id,
                checkpoint_time=checkpoint_time,
            )
            for unit_id, raw in sorted(raw_assessments.items())
        }
        if expected_unit_ids is not None and (not set(cached_assessments) <= expected_unit_ids):
            raise ValueError(
                "Battle assessment cache references unknown runtime units",
            )
        required = required_assessment_ids or set()
        if not required <= set(cached_assessments):
            raise ValueError(
                "Battle assessment cache is incomplete for OODA continuation: "
                f"missing={sorted(required - set(cached_assessments))!r}",
            )

        raw_suppression = state.get("suppression_states", {})
        if not isinstance(raw_suppression, dict):
            raise ValueError(
                "Battle suppression_states must be a mapping",
            )
        suppression_states: dict[str, UnitSuppressionState] = {}
        for unit_id, raw in sorted(raw_suppression.items()):
            unit_id = self._state_identifier(
                unit_id,
                field_name="suppression unit_id",
            )
            if not isinstance(raw, dict) or set(raw) != {"value", "source_direction"}:
                raise ValueError(
                    f"Battle suppression state {unit_id!r} is invalid",
                )
            suppression_states[unit_id] = UnitSuppressionState(
                value=self._state_float(
                    raw["value"],
                    field_name="suppression value",
                    minimum=0.0,
                    maximum=1.0,
                ),
                source_direction=self._state_float(
                    raw["source_direction"],
                    field_name="suppression source_direction",
                ),
            )

        raw_undigging = state.get("undigging", {})
        if not isinstance(raw_undigging, dict):
            raise ValueError("Battle undigging must be a mapping")
        undigging: dict[str, bool] = {}
        for unit_id, value in sorted(raw_undigging.items()):
            unit_id = self._state_identifier(
                unit_id,
                field_name="undigging unit_id",
            )
            if not isinstance(value, bool):
                raise ValueError("Battle undigging values must be boolean")
            undigging[unit_id] = value

        raw_misinterpreted = state.get("misinterpreted_orders", {})
        if not isinstance(raw_misinterpreted, dict):
            raise ValueError(
                "Battle misinterpreted_orders must be a mapping",
            )
        misinterpreted_orders = {
            self._state_identifier(
                unit_id,
                field_name="misinterpreted-order unit_id",
            ): self._stage_propagation_result(
                raw,
                unit_id=unit_id,
            )
            for unit_id, raw in sorted(raw_misinterpreted.items())
        }
        pending_decisions = self._stage_float_map(
            state.get("pending_decisions", {}),
            field_name="pending_decisions",
            minimum=0.0,
        )
        pending_ids = set(pending_decisions)
        propagation_ids = set(misinterpreted_orders)
        if has_deferred_schema and propagation_ids != pending_ids:
            raise ValueError(
                "Current deferred-OODA state requires exactly one propagation "
                "record per pending decision: "
                f"missing={sorted(pending_ids - propagation_ids)!r}, "
                f"extra={sorted(propagation_ids - pending_ids)!r}",
            )
        if not has_deferred_schema:
            if allow_legacy and pending_ids:
                raise ValueError(
                    "Versionless checkpoints cannot migrate pending OODA decisions",
                )
            if not propagation_ids <= pending_ids:
                raise ValueError(
                    "Markerless deferred-OODA propagation state references no "
                    "pending decision",
                )
            if pending_ids and checkpoint_elapsed_s is None:
                raise ValueError(
                    "Markerless pending OODA state requires global checkpoint "
                    "elapsed time for migration",
                )
            for unit_id in sorted(pending_ids - propagation_ids):
                misinterpreted_orders[unit_id] = PropagationResult(
                    success=True,
                    total_delay_s=0.0,
                    was_misinterpreted=False,
                    misinterpretation_type="",
                    comms_quality=1.0,
                    degraded=False,
                )

        if deferred_ooda_ids is None:
            deferred_ids = set(pending_ids)
        else:
            deferred_ids = {
                self._state_identifier(
                    unit_id,
                    field_name="deferred OODA unit_id",
                )
                for unit_id in deferred_ooda_ids
            }
            if not pending_ids <= deferred_ids:
                raise ValueError(
                    "Pending decisions require an expired DECIDE completion",
                )
            deferred_ids.update(pending_ids)

        deferred_battle_ids: dict[str, str] = {}
        for unit_id in sorted(deferred_ids):
            matching_battles = [
                battle.battle_id
                for battle in battles.values()
                if battle.active and unit_id in battle.unit_ids
            ]
            if len(matching_battles) != 1:
                raise ValueError(
                    "Deferred OODA decision must belong to exactly one active "
                    f"battle roster: unit={unit_id!r}, "
                    f"battles={matching_battles!r}",
                )
            deferred_battle_ids[unit_id] = matching_battles[0]

        if not has_deferred_schema:
            for unit_id in sorted(pending_ids):
                battle_owner = battles[deferred_battle_ids[unit_id]]
                legacy_due_s = pending_decisions[unit_id]
                propagation = misinterpreted_orders[unit_id]
                if (
                    propagation.was_misinterpreted
                    and propagation.misinterpretation_type == "timing"
                ):
                    legacy_due_s += propagation.total_delay_s
                if checkpoint_elapsed_s is None:
                    # Guarded above for non-empty pending state; keep the
                    # invariant local to the actual conversion as well.
                    raise ValueError(
                        "Markerless pending OODA state requires global checkpoint "
                        "elapsed time for migration",
                    )
                global_due_s = (
                    checkpoint_elapsed_s
                    + legacy_due_s
                    - battle_owner.battle_elapsed_s
                )
                if not math.isfinite(global_due_s) or global_due_s < 0.0:
                    raise ValueError(
                        "Migrated deferred-OODA global due time is invalid",
                    )
                pending_decisions[unit_id] = global_due_s

        raw_lod_promoted = state.get("lod_promoted", [])
        if not isinstance(raw_lod_promoted, list):
            raise ValueError("Battle lod_promoted must be a list")
        lod_promoted = {
            self._state_identifier(
                unit_id,
                field_name="lod_promoted unit_id",
            )
            for unit_id in raw_lod_promoted
        }
        if len(lod_promoted) != len(raw_lod_promoted):
            raise ValueError("Battle lod_promoted values must be unique")

        raw_fow_observers = state.get("fow_observer_unit_ids", [])
        if not isinstance(raw_fow_observers, list):
            raise ValueError("Battle fow_observer_unit_ids must be a list")
        fow_observer_unit_ids = frozenset(
            self._state_identifier(
                unit_id,
                field_name="fog-of-war observer unit_id",
            )
            for unit_id in raw_fow_observers
        )
        if len(fow_observer_unit_ids) != len(raw_fow_observers):
            raise ValueError(
                "Battle fow_observer_unit_ids values must be unique",
            )

        if allow_legacy:
            if has_deferred_schema:
                raise ValueError(
                    "Versionless battle state cannot contain a deferred-OODA schema marker",
                )
            if "performance_execution_receipt" in state:
                raise ValueError(
                    "Versionless battle state cannot contain a Phase 118 performance receipt",
                )
            if "fow_observer_unit_ids" in state:
                raise ValueError(
                    "Versionless battle state cannot contain a Phase 118 fog-of-war observer roster",
                )
            raw_performance_receipt = PerformanceExecutionReceipt.zero(
                effective_flags=(owner.performance_effective_flags),
                tactical_interval_microseconds=(owner.performance_tactical_interval_microseconds),
                complete_from_tick_zero=False,
            ).to_state()
        else:
            raw_performance_receipt = state["performance_execution_receipt"]
        performance_receipt_plan = owner.stage_performance_receipt_state(raw_performance_receipt)
        lod_tiers = self._stage_int_map(
            state.get("lod_tiers", {}),
            field_name="lod_tiers",
        )
        lod_pending_tiers = self._stage_int_map(
            state.get("lod_pending_tiers", {}),
            field_name="lod_pending_tiers",
        )
        lod_pending_counts = self._stage_int_map(
            state.get("lod_pending_counts", {}),
            field_name="lod_pending_counts",
            minimum=1,
        )
        valid_lod_values = {int(tier) for tier in UnitLodTier}
        if any(value not in valid_lod_values for value in lod_tiers.values()):
            raise ValueError("Battle lod_tiers contains an unknown tier")
        if any(value not in valid_lod_values for value in lod_pending_tiers.values()):
            raise ValueError(
                "Battle lod_pending_tiers contains an unknown tier",
            )
        if set(lod_pending_tiers) != set(lod_pending_counts):
            raise ValueError(
                "Battle LOD pending tier and count owners disagree",
            )
        if not set(lod_pending_tiers) <= set(lod_tiers):
            raise ValueError(
                "Battle LOD pending state references an unclassified unit",
            )
        if any(lod_pending_tiers[unit_id] <= lod_tiers[unit_id] for unit_id in lod_pending_tiers):
            raise ValueError(
                "Battle LOD pending state must describe a demotion",
            )
        if not lod_promoted <= set(lod_tiers):
            raise ValueError(
                "Battle lod_promoted references an unclassified unit",
            )
        if owner.performance_effective_flags.enable_lod and not fow_observer_unit_ids <= set(lod_tiers):
            raise ValueError(
                "Battle LOD-enabled observer roster contains an unclassified unit",
            )

        plan = BattleStatePlan(
            owner_id=owner.checkpoint_owner_id,
            battles=battles,
            next_battle_id=next_battle_id,
            vls_launches=self._stage_int_map(
                state.get("vls_launches", {}),
                field_name="vls_launches",
            ),
            ammo_expended=self._stage_int_map(
                state.get("ammo_expended", {}),
                field_name="ammo_expended",
            ),
            pending_decisions=pending_decisions,
            deferred_battle_ids=deferred_battle_ids,
            cached_assessments=cached_assessments,
            ticks_stationary=self._stage_int_map(
                state.get("ticks_stationary", {}),
                field_name="ticks_stationary",
            ),
            suppression_states=suppression_states,
            cumulative_casualties=self._stage_int_map(
                state.get("cumulative_casualties", {}),
                field_name="cumulative_casualties",
            ),
            undigging=undigging,
            concealment_scores=self._stage_float_map(
                state.get("concealment_scores", {}),
                field_name="concealment_scores",
                minimum=0.0,
            ),
            env_casualty_accum=self._stage_float_map(
                state.get("env_casualty_accum", {}),
                field_name="env_casualty_accum",
                minimum=0.0,
            ),
            misinterpreted_orders=misinterpreted_orders,
            lod_tiers=lod_tiers,
            lod_pending_tiers=lod_pending_tiers,
            lod_pending_counts=lod_pending_counts,
            lod_promoted=lod_promoted,
            fow_observer_unit_ids=fow_observer_unit_ids,
            performance_execution_receipt=performance_receipt_plan,
        )
        all_unit_maps = (
            plan.pending_decisions,
            plan.cached_assessments,
            plan.ticks_stationary,
            plan.suppression_states,
            plan.cumulative_casualties,
            plan.undigging,
            plan.concealment_scores,
            plan.env_casualty_accum,
            plan.misinterpreted_orders,
            plan.lod_tiers,
            plan.lod_pending_tiers,
            plan.lod_pending_counts,
        )
        if expected_unit_ids is not None and any(not set(mapping) <= expected_unit_ids for mapping in all_unit_maps):
            raise ValueError(
                "Battle unit-owned state references unknown runtime units",
            )
        if expected_unit_ids is not None and (not plan.lod_promoted <= expected_unit_ids):
            raise ValueError(
                "Battle lod_promoted references unknown runtime units",
            )
        if expected_unit_ids is not None and (not plan.fow_observer_unit_ids <= expected_unit_ids):
            raise ValueError(
                "Battle fog-of-war observer roster references unknown runtime units",
            )
        return plan

    def commit_state(
        self,
        owner: BattleExecutorOwner,
        plan: BattleStatePlan,
    ) -> None:
        owner.apply_checkpoint_plan(plan)

    def set_state(
        self,
        owner: BattleExecutorOwner,
        state: dict[str, Any],
        *,
        allow_legacy: bool = False,
    ) -> None:
        self.commit_state(
            owner,
            self.stage_state(
                owner,
                BattleCheckpointStageRequest(
                    state=state,
                    allow_legacy=allow_legacy,
                    expected_unit_ids=None,
                    expected_sides=None,
                    required_assessment_ids=None,
                    checkpoint_time=None,
                    checkpoint_elapsed_s=None,
                    deferred_ooda_ids=None,
                ),
            ),
        )
