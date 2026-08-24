"""Deterministic production runtime for configured direct-ascent ASAT actions.

The engine owns mutable strategic-ASAT asset, order, and debris state.  Scenario
loading supplies an already validated immutable topology; callers cannot
incrementally register weapons or directly fire while supplying their own
ownership data.

The supported kinetic probability is the Rayleigh radial-error CDF::

    Pk = 1 - exp(-0.5 * (lethal_radius / guidance_sigma) ** 2)

Kinetic debris remains a deliberately coarse Poisson abstraction.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.runtime_failure import (
    RuntimeFailureHandler,
    RuntimeFailurePolicyBinding,
)
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATType,
    ASATWeaponDefinition,
    SpaceConfig,
)
from stochastic_warfare.space.constellations import ConstellationManager
from stochastic_warfare.space.events import ASATEngagementEvent, DebrisCascadeEvent
from stochastic_warfare.space.orbits import R_EARTH

logger = get_logger(__name__)

_MAX_DEBRIS_COUNT = 2**63 - 1


@dataclass
class DebrisCloud:
    """Mutable orbital-debris state for one altitude band."""

    altitude_band_km: float
    debris_count: int
    age_s: float = 0.0


@dataclass
class _ASATAssetState:
    """Runtime inventory and cooldown for one configured ASAT asset."""

    config: ASATAssetConfig
    rounds_remaining: int
    ready_at_s: float = 0.0


class ASATEngine:
    """Execute predeclared direct-ascent ASAT orders exactly once."""

    _STATE_KEYS = frozenset({
        "configuration_fingerprint",
        "assets",
        "pending_order_ids",
        "completed_orders",
        "debris_clouds",
    })
    _RESULT_KEYS = frozenset({
        "order_id",
        "asset_id",
        "weapon_id",
        "attacker_side",
        "target_satellite_id",
        "target_constellation_id",
        "scheduled_time_s",
        "execution_time_s",
        "launched",
        "hit",
        "pk",
        "outcome",
        "reason",
        "debris_generated",
        "rounds_remaining",
        "previous_constellation_count",
        "new_constellation_count",
    })
    _REJECTION_REASONS = frozenset({
        "asset_depleted",
        "asset_reloading",
        "target_inactive",
        "target_out_of_range",
    })

    def __init__(
        self,
        constellation_manager: ConstellationManager,
        config: SpaceConfig,
        event_bus: EventBus,
        rng: np.random.Generator,
        clock: Any = None,
        *,
        weapon_definitions: Mapping[str, ASATWeaponDefinition] | None = None,
        assets: Sequence[ASATAssetConfig] = (),
        orders: Sequence[ASATOrderConfig] = (),
        configuration_fingerprint: str | None = None,
    ) -> None:
        self._cm = constellation_manager
        self._config = config
        self._event_bus = event_bus
        self._rng = rng
        self._clock = clock
        self._runtime_failure_handler: RuntimeFailurePolicyBinding | None = None

        definitions = dict(weapon_definitions or {})
        asset_configs = tuple(assets)
        order_configs = tuple(orders)
        self._validate_topology(definitions, asset_configs, order_configs)

        self._weapon_definitions = definitions
        self._assets = {
            asset.asset_id: _ASATAssetState(
                config=asset,
                rounds_remaining=asset.rounds_available,
            )
            for asset in asset_configs
        }
        self._orders = order_configs
        self._order_by_id = {order.order_id: order for order in order_configs}
        self._order_declaration_index = {
            order.order_id: index for index, order in enumerate(order_configs)
        }
        self._pending_order_ids = {order.order_id for order in order_configs}
        self._completed_orders: dict[str, dict[str, Any]] = {}
        self._debris_clouds: list[DebrisCloud] = []

        if configuration_fingerprint is None:
            self._configuration_fingerprint = self._compute_fingerprint()
        elif (
            not isinstance(configuration_fingerprint, str)
            or len(configuration_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in configuration_fingerprint)
        ):
            raise ValueError(
                "configuration_fingerprint must be a lowercase SHA-256 hex digest",
            )
        else:
            self._configuration_fingerprint = configuration_fingerprint

    def bind_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Bind the production strict/degraded failure-policy owner."""
        binding = RuntimeFailurePolicyBinding(handler)
        existing = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if existing is not None and existing != handler:
            raise RuntimeError(
                "ASATEngine already has a different runtime failure-policy "
                "owner",
            )
        self._runtime_failure_handler = binding

    def validate_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Reject failure-policy owner drift after runtime construction."""
        bound = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if bound != handler:
            raise RuntimeError(
                "ASATEngine runtime failure-policy binding changed",
            )

    def _validate_topology(
        self,
        definitions: Mapping[str, ASATWeaponDefinition],
        assets: Sequence[ASATAssetConfig],
        orders: Sequence[ASATOrderConfig],
    ) -> None:
        """Defensively validate the complete immutable runtime topology."""
        if tuple(self._config.asat_assets) != tuple(assets):
            raise ValueError(
                "ASAT constructor assets do not match SpaceConfig topology",
            )
        if tuple(self._config.asat_orders) != tuple(orders):
            raise ValueError(
                "ASAT constructor orders do not match SpaceConfig topology",
            )
        for key, definition in definitions.items():
            if key != definition.weapon_id:
                raise ValueError(
                    f"ASAT weapon mapping key {key!r} does not match "
                    f"weapon_id {definition.weapon_id!r}",
                )

        asset_by_id: dict[str, ASATAssetConfig] = {}
        for asset in assets:
            if asset.asset_id in asset_by_id:
                raise ValueError(f"duplicate ASAT asset_id: {asset.asset_id!r}")
            weapon = definitions.get(asset.weapon_id)
            if weapon is None:
                raise ValueError(
                    f"ASAT asset {asset.asset_id!r} references unknown weapon "
                    f"{asset.weapon_id!r}",
                )
            if weapon.asat_type != ASATType.DIRECT_ASCENT_KKV:
                raise ValueError(
                    f"ASAT asset {asset.asset_id!r} uses unsupported production "
                    f"type {weapon.asat_type.name}",
                )
            asset_by_id[asset.asset_id] = asset

        seen_orders: set[str] = set()
        for order in orders:
            if order.order_id in seen_orders:
                raise ValueError(f"duplicate ASAT order_id: {order.order_id!r}")
            seen_orders.add(order.order_id)
            asset = asset_by_id.get(order.asset_id)
            if asset is None:
                raise ValueError(
                    f"ASAT order {order.order_id!r} references unknown asset "
                    f"{order.asset_id!r}",
                )
            target = self._cm.get_satellite(order.target_satellite_id)
            if target is None:
                raise ValueError(
                    f"ASAT order {order.order_id!r} references unknown satellite "
                    f"{order.target_satellite_id!r}",
                )
            if target.side == asset.side:
                raise ValueError(
                    f"ASAT order {order.order_id!r} targets friendly satellite "
                    f"{order.target_satellite_id!r}",
                )

        referenced_weapon_ids = {asset.weapon_id for asset in assets}
        if set(definitions) != referenced_weapon_ids:
            raise ValueError(
                "ASAT weapon definitions do not exactly match configured assets",
            )

    def _compute_fingerprint(self) -> str:
        """Build a canonical fallback fingerprint for component construction."""
        payload = {
            "space_config": self._config.model_dump(mode="json"),
            "weapon_definitions": {
                weapon_id: definition.model_dump(mode="json")
                for weapon_id, definition in sorted(self._weapon_definitions.items())
            },
            "assets": [
                state.config.model_dump(mode="json")
                for state in self._assets.values()
            ],
            "orders": [order.model_dump(mode="json") for order in self._orders],
            "satellites": [
                {
                    "satellite_id": satellite.satellite_id,
                    "constellation_id": satellite.constellation_id,
                    "side": satellite.side,
                    "elements": satellite.elements.model_dump(mode="json"),
                }
                for satellite in sorted(
                    self._cm.all_satellites(),
                    key=lambda item: item.satellite_id,
                )
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _timestamp(self) -> datetime:
        """Return the injected logical clock time or a deterministic fallback."""
        if self._clock is not None:
            return self._clock.current_time
        return datetime(2024, 1, 1, tzinfo=timezone.utc)

    @staticmethod
    def _satellite_altitude_km(target: Any) -> float:
        """Compute current orbital altitude from the target's osculating state."""
        elements = target.elements
        anomaly_rad = math.radians(target.current_true_anomaly_deg)
        radius_m = (
            elements.semi_major_axis_m
            * (1.0 - elements.eccentricity**2)
            / (1.0 + elements.eccentricity * math.cos(anomaly_rad))
        )
        return (radius_m - R_EARTH) / 1000.0

    @staticmethod
    def _compute_kinetic_pk(
        weapon: ASATWeaponDefinition,
        target_altitude_km: float | None = None,
    ) -> float:
        """Return the Rayleigh radial-error CDF at the lethal radius.

        ``target_altitude_km`` remains accepted for source compatibility with
        historical component tests; altitude is a launch-validity constraint,
        not a factor in this declared probability equation.
        """
        del target_altitude_km
        ratio = weapon.lethal_radius_m / weapon.guidance_sigma_m
        if not math.isfinite(ratio) or ratio >= 40.0:
            return 1.0
        return -math.expm1(-0.5 * ratio * ratio)

    def execute_due_orders(
        self,
        sim_time_s: float,
        timestamp: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Execute each newly due configured order in canonical order.

        Disabled ASAT execution is an intentional no-op: orders remain pending
        and neither asset state nor the injected RNG is touched.
        """
        if not self._config.enable_asat:
            return []
        sim_time_s = self._validated_finite_number(
            sim_time_s,
            "sim_time_s",
            minimum=0.0,
        )

        due_orders = sorted(
            (
                order
                for order in self._orders
                if (
                    order.order_id in self._pending_order_ids
                    and order.execute_at_s <= sim_time_s
                )
            ),
            key=lambda order: (
                order.execute_at_s,
                self._order_declaration_index[order.order_id],
            ),
        )
        event_timestamp = timestamp if timestamp is not None else self._timestamp()
        return [
            self._execute_order(order, sim_time_s, event_timestamp)
            for order in due_orders
        ]

    def _execute_order(
        self,
        order: ASATOrderConfig,
        sim_time_s: float,
        timestamp: datetime,
    ) -> dict[str, Any]:
        """Commit one due order and publish its observable result."""
        asset = self._assets[order.asset_id]
        weapon = self._weapon_definitions[asset.config.weapon_id]
        target = self._cm.get_satellite(order.target_satellite_id)
        if target is None:
            raise RuntimeError(
                f"validated ASAT target disappeared: {order.target_satellite_id!r}",
            )

        previous_count = self._cm.active_count(target.constellation_id)
        reason = ""
        if asset.rounds_remaining <= 0:
            reason = "asset_depleted"
        elif sim_time_s < asset.ready_at_s:
            reason = "asset_reloading"
        elif not target.is_active:
            reason = "target_inactive"
        else:
            altitude_km = self._satellite_altitude_km(target)
            if not (
                weapon.min_altitude_km
                <= altitude_km
                <= weapon.max_altitude_km
            ):
                reason = "target_out_of_range"

        if reason:
            result = self._build_result(
                order=order,
                asset=asset,
                target=target,
                sim_time_s=sim_time_s,
                launched=False,
                hit=False,
                pk=0.0,
                outcome="rejected",
                reason=reason,
                debris_generated=0,
                previous_count=previous_count,
                new_count=previous_count,
            )
            self._complete_and_publish(order.order_id, result, timestamp, ())
            return copy.deepcopy(result)

        pk = self._compute_kinetic_pk(weapon)
        hit = float(self._rng.random()) < pk
        debris_generated = 0
        altitude_km = 0.0
        if hit:
            # Complete every potentially failing stochastic calculation before
            # committing inventory, cooldown, satellite, or order state.
            debris_generated = int(
                self._rng.poisson(self._config.debris_fragment_mean),
            )
            altitude_km = self._satellite_altitude_km(target)

        asset.rounds_remaining -= 1
        asset.ready_at_s = sim_time_s + weapon.reload_time_s
        observer_failures: list[Exception] = []

        if hit:
            observer_failures.extend(
                self._cm.deactivate_satellite(
                    target.satellite_id,
                    cause="asat_kinetic",
                    timestamp=timestamp,
                ),
            )
            self._debris_clouds.append(
                DebrisCloud(altitude_km, debris_generated),
            )

        new_count = self._cm.active_count(target.constellation_id)
        result = self._build_result(
            order=order,
            asset=asset,
            target=target,
            sim_time_s=sim_time_s,
            launched=True,
            hit=hit,
            pk=pk,
            outcome="hit" if hit else "miss",
            reason="",
            debris_generated=debris_generated,
            previous_count=previous_count,
            new_count=new_count,
        )
        self._complete_and_publish(
            order.order_id,
            result,
            timestamp,
            observer_failures,
        )
        return copy.deepcopy(result)

    @staticmethod
    def _build_result(
        *,
        order: ASATOrderConfig,
        asset: _ASATAssetState,
        target: Any,
        sim_time_s: float,
        launched: bool,
        hit: bool,
        pk: float,
        outcome: str,
        reason: str,
        debris_generated: int,
        previous_count: int,
        new_count: int,
    ) -> dict[str, Any]:
        """Create the JSON-safe canonical result/event payload."""
        return {
            "order_id": order.order_id,
            "asset_id": asset.config.asset_id,
            "weapon_id": asset.config.weapon_id,
            "attacker_side": asset.config.side,
            "target_satellite_id": target.satellite_id,
            "target_constellation_id": target.constellation_id,
            "scheduled_time_s": float(order.execute_at_s),
            "execution_time_s": float(sim_time_s),
            "launched": launched,
            "hit": hit,
            "pk": float(pk),
            "outcome": outcome,
            "reason": reason,
            "debris_generated": debris_generated,
            "rounds_remaining": asset.rounds_remaining,
            "previous_constellation_count": previous_count,
            "new_constellation_count": new_count,
        }

    def _complete_and_publish(
        self,
        order_id: str,
        result: dict[str, Any],
        timestamp: datetime,
        prior_failures: Sequence[Exception],
    ) -> None:
        """Commit order completion, then notify every observer without rollback."""
        self._pending_order_ids.remove(order_id)
        self._completed_orders[order_id] = copy.deepcopy(result)
        event = ASATEngagementEvent(
            timestamp=timestamp,
            source=ModuleId.SPACE,
            **result,
        )
        failures = [*prior_failures, *self._event_bus.publish_collecting(event)]
        self._handle_observer_failures(
            f"order {order_id}",
            failures,
        )

    def update_debris(
        self,
        dt_s: float,
        sim_time_s: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Age existing debris and resolve deterministic-band cascade checks."""
        dt_s = self._validated_finite_number(
            dt_s,
            "dt_s",
            minimum=0.0,
        )
        sim_time_s = self._validated_finite_number(
            sim_time_s,
            "sim_time_s",
            minimum=0.0,
        )

        for cloud in self._debris_clouds:
            cloud.age_s += dt_s

        total_debris_by_band: dict[float, int] = {}
        for cloud in self._debris_clouds:
            band_km = round(cloud.altitude_band_km / 100.0) * 100.0
            total_debris_by_band[band_km] = (
                total_debris_by_band.get(band_km, 0) + cloud.debris_count
            )

        event_timestamp = timestamp if timestamp is not None else self._timestamp()
        for band_km, count in sorted(total_debris_by_band.items()):
            collision_probability = min(
                float(min(count, _MAX_DEBRIS_COUNT))
                * self._config.debris_collision_prob_per_orbit,
                0.1,
            )
            if collision_probability <= 0.01:
                continue

            cascade_event = DebrisCascadeEvent(
                timestamp=event_timestamp,
                source=ModuleId.SPACE,
                altitude_band_km=band_km,
                debris_count=count,
                collision_probability_per_orbit=collision_probability,
            )
            self._handle_observer_failures(
                "debris cascade risk event",
                self._event_bus.publish_collecting(cascade_event),
            )

            if float(self._rng.random()) >= collision_probability:
                continue

            eligible = sorted(
                (
                    satellite
                    for satellite in self._cm.all_satellites()
                    if (
                        satellite.is_active
                        and abs(
                            self._satellite_altitude_km(satellite) - band_km
                        ) < 100.0
                    )
                ),
                key=lambda satellite: satellite.satellite_id,
            )
            if not eligible:
                continue

            target = eligible[0]
            observer_failures = self._cm.deactivate_satellite(
                target.satellite_id,
                cause="debris",
                timestamp=event_timestamp,
            )
            new_debris = int(
                self._rng.poisson(self._config.debris_fragment_mean * 0.5),
            )
            self._debris_clouds.append(
                DebrisCloud(
                    self._satellite_altitude_km(target),
                    new_debris,
                ),
            )
            self._handle_observer_failures(
                f"debris degradation of {target.satellite_id}",
                observer_failures,
            )
            logger.info(
                "Debris cascade destroyed %s at %.0f km",
                target.satellite_id,
                self._satellite_altitude_km(target),
            )

    def _handle_observer_failures(
        self,
        context: str,
        failures: Sequence[Exception],
    ) -> None:
        for failure in failures:
            logger.error(
                "ASAT observer failed after committed %s: %s",
                context,
                failure,
                exc_info=(
                    type(failure),
                    failure,
                    failure.__traceback__,
                ),
            )
            binding = getattr(
                self,
                "_runtime_failure_handler",
                None,
            )
            handler = (
                binding.resolve()
                if binding is not None
                else None
            )
            if handler is None or not handler(
                "space.asat",
                "publish_committed_event",
                failure,
            ):
                raise failure

    def update(
        self,
        dt_s: float,
        sim_time_s: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Update pre-existing debris state without executing queued orders."""
        self.update_debris(dt_s, sim_time_s, timestamp)

    def get_state(self) -> dict[str, Any]:
        """Return all mutable ASAT state plus its immutable-topology fingerprint."""
        return {
            "configuration_fingerprint": self._configuration_fingerprint,
            "assets": {
                asset_id: {
                    "weapon_id": asset.config.weapon_id,
                    "side": asset.config.side,
                    "rounds_initial": asset.config.rounds_available,
                    "rounds_remaining": asset.rounds_remaining,
                    "ready_at_s": asset.ready_at_s,
                }
                for asset_id, asset in self._assets.items()
            },
            "pending_order_ids": [
                order.order_id
                for order in self._orders
                if order.order_id in self._pending_order_ids
            ],
            "completed_orders": copy.deepcopy(self._completed_orders),
            "debris_clouds": [
                {
                    "altitude_band_km": cloud.altitude_band_km,
                    "debris_count": cloud.debris_count,
                    "age_s": cloud.age_s,
                }
                for cloud in self._debris_clouds
            ],
        }

    def validate_state(
        self,
        state: dict[str, Any],
        *,
        expected_elapsed_s: float | None = None,
        expected_tick_count: int | None = None,
    ) -> dict[str, Any]:
        """Validate and normalize a checkpoint without mutating live state."""
        if not isinstance(state, dict):
            raise TypeError("ASAT state must be a dictionary")
        if set(state) != self._STATE_KEYS:
            missing = sorted(self._STATE_KEYS - set(state))
            extra = sorted(set(state) - self._STATE_KEYS)
            raise ValueError(
                f"invalid ASAT state keys; missing={missing}, extra={extra}",
            )
        if state["configuration_fingerprint"] != self._configuration_fingerprint:
            raise ValueError("ASAT configuration fingerprint mismatch")

        staged_assets = self._validate_asset_state(state["assets"])
        staged_pending, staged_completed = self._validate_order_state(
            state["pending_order_ids"],
            state["completed_orders"],
            staged_assets,
        )
        if expected_tick_count is not None:
            if (
                isinstance(expected_tick_count, bool)
                or not isinstance(expected_tick_count, int)
                or expected_tick_count < 0
            ):
                raise ValueError(
                    "expected ASAT checkpoint tick count must be a "
                    "non-negative integer",
                )
            if expected_tick_count == 0 and staged_completed:
                raise ValueError(
                    "ASAT orders cannot be completed before the first "
                    "simulation tick",
                )
        if expected_elapsed_s is not None:
            elapsed = self._validated_finite_number(
                expected_elapsed_s,
                "expected ASAT checkpoint elapsed time",
                minimum=0.0,
            )
            future_completed = [
                order_id
                for order_id, result in staged_completed.items()
                if result["execution_time_s"] > elapsed
            ]
            if future_completed:
                raise ValueError(
                    "ASAT completed orders execute after the checkpoint clock: "
                    f"{future_completed!r}",
                )
            overdue_pending = [
                order_id
                for order_id in staged_pending
                if (
                    self._config.enable_asat
                    and elapsed > 0.0
                    and self._order_by_id[order_id].execute_at_s <= elapsed
                )
            ]
            if overdue_pending:
                raise ValueError(
                    "ASAT pending orders are already due at the checkpoint "
                    f"clock: {overdue_pending!r}",
                )
        staged_clouds = self._validate_debris_state(state["debris_clouds"])
        hit_results = [
            result
            for result in staged_completed.values()
            if result["hit"]
        ]
        if (
            len(staged_clouds) < len(hit_results)
            or sum(cloud["debris_count"] for cloud in staged_clouds)
            < sum(result["debris_generated"] for result in hit_results)
        ):
            raise ValueError(
                "ASAT debris clouds do not preserve completed hit debris",
            )
        if not self._config.enable_asat:
            disabled_assets_are_pristine = all(
                asset["rounds_remaining"] == asset["rounds_initial"]
                and asset["ready_at_s"] == 0.0
                for asset in staged_assets.values()
            )
            expected_pending = [
                order.order_id
                for order in self._orders
            ]
            if (
                staged_completed
                or staged_pending != expected_pending
                or not disabled_assets_are_pristine
                or staged_clouds
            ):
                raise ValueError(
                    "ASAT-disabled checkpoint must preserve pristine assets, "
                    "all pending orders, no completed orders, and no debris",
                )
        return {
            "configuration_fingerprint": self._configuration_fingerprint,
            "assets": staged_assets,
            "pending_order_ids": staged_pending,
            "completed_orders": staged_completed,
            "debris_clouds": staged_clouds,
        }

    def _validate_asset_state(
        self,
        assets_state: Any,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(assets_state, dict):
            raise TypeError("ASAT assets state must be a dictionary")
        if set(assets_state) != set(self._assets):
            raise ValueError("ASAT checkpoint asset topology mismatch")

        staged: dict[str, dict[str, Any]] = {}
        expected_keys = {
            "weapon_id",
            "side",
            "rounds_initial",
            "rounds_remaining",
            "ready_at_s",
        }
        for asset_id, live in self._assets.items():
            raw = assets_state[asset_id]
            if not isinstance(raw, dict) or set(raw) != expected_keys:
                raise ValueError(f"invalid state for ASAT asset {asset_id!r}")
            if (
                raw["weapon_id"] != live.config.weapon_id
                or raw["side"] != live.config.side
                or raw["rounds_initial"] != live.config.rounds_available
            ):
                raise ValueError(
                    f"ASAT checkpoint topology mismatch for asset {asset_id!r}",
                )
            remaining = raw["rounds_remaining"]
            if (
                isinstance(remaining, bool)
                or not isinstance(remaining, int)
                or not 0 <= remaining <= live.config.rounds_available
            ):
                raise ValueError(
                    f"invalid rounds_remaining for ASAT asset {asset_id!r}",
                )
            try:
                ready_at = self._validated_finite_number(
                    raw["ready_at_s"],
                    f"ASAT asset {asset_id!r} ready_at_s",
                    minimum=0.0,
                )
            except ValueError as exc:
                raise ValueError(
                    f"invalid ready_at_s for ASAT asset {asset_id!r}",
                ) from exc
            staged[asset_id] = {
                "weapon_id": live.config.weapon_id,
                "side": live.config.side,
                "rounds_initial": live.config.rounds_available,
                "rounds_remaining": remaining,
                "ready_at_s": ready_at,
            }
        return staged

    def _validate_order_state(
        self,
        pending_state: Any,
        completed_state: Any,
        staged_assets: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        if not isinstance(pending_state, list) or not all(
            isinstance(order_id, str) for order_id in pending_state
        ):
            raise TypeError("pending_order_ids must be a list of strings")
        if len(pending_state) != len(set(pending_state)):
            raise ValueError("pending_order_ids contains duplicates")
        if not isinstance(completed_state, dict):
            raise TypeError("completed_orders must be a dictionary")

        pending_ids = set(pending_state)
        completed_ids = set(completed_state)
        configured_ids = set(self._order_by_id)
        if pending_ids & completed_ids:
            raise ValueError("ASAT order cannot be pending and completed")
        if pending_ids | completed_ids != configured_ids:
            raise ValueError("ASAT checkpoint order topology mismatch")

        canonical_pending = [
            order.order_id
            for order in self._orders
            if order.order_id in pending_ids
        ]
        if pending_state != canonical_pending:
            raise ValueError("pending_order_ids is not in canonical order")

        canonical_completed_ids = sorted(
            completed_ids,
            key=lambda order_id: (
                self._order_by_id[order_id].execute_at_s,
                self._order_declaration_index[order_id],
            ),
        )
        if list(completed_state) != canonical_completed_ids:
            raise ValueError("completed_orders is not in canonical order")

        staged_completed: dict[str, dict[str, Any]] = {}
        last_remaining_by_asset: dict[str, int] = {}
        last_ready_at_by_asset: dict[str, float] = {}
        last_execution_time_s = 0.0
        for order_id in canonical_completed_ids:
            result = self._validate_completed_result(
                order_id,
                completed_state[order_id],
            )
            previous_remaining = last_remaining_by_asset.get(
                result["asset_id"],
                self._assets[result["asset_id"]].config.rounds_available,
            )
            previous_ready_at = last_ready_at_by_asset.get(
                result["asset_id"],
                0.0,
            )
            execution_time_s = result["execution_time_s"]
            if execution_time_s < last_execution_time_s:
                raise ValueError(
                    "ASAT completed order execution times are not canonical",
                )
            last_execution_time_s = execution_time_s

            if result["launched"]:
                if (
                    previous_remaining <= 0
                    or execution_time_s < previous_ready_at
                ):
                    raise ValueError(
                        f"ASAT launch preconditions are impossible for order "
                        f"{order_id!r}",
                    )
            elif result["reason"] == "asset_depleted":
                if previous_remaining != 0:
                    raise ValueError(
                        f"ASAT asset_depleted result is impossible for order "
                        f"{order_id!r}",
                    )
            elif result["reason"] == "asset_reloading":
                if (
                    previous_remaining <= 0
                    or execution_time_s >= previous_ready_at
                ):
                    raise ValueError(
                        f"ASAT asset_reloading result is impossible for order "
                        f"{order_id!r}",
                    )
            elif (
                previous_remaining <= 0
                or execution_time_s < previous_ready_at
            ):
                raise ValueError(
                    f"ASAT rejection precedence is impossible for order "
                    f"{order_id!r}",
                )

            expected_remaining = (
                previous_remaining - 1
                if result["launched"]
                else previous_remaining
            )
            if result["rounds_remaining"] != expected_remaining:
                raise ValueError(
                    f"inconsistent rounds result for ASAT order {order_id!r}",
                )
            last_remaining_by_asset[result["asset_id"]] = expected_remaining
            if result["launched"]:
                asset = self._assets[result["asset_id"]].config
                weapon = self._weapon_definitions[asset.weapon_id]
                last_ready_at_by_asset[result["asset_id"]] = (
                    execution_time_s + weapon.reload_time_s
                )
            staged_completed[order_id] = result

        for asset_id, current in staged_assets.items():
            expected = last_remaining_by_asset.get(
                asset_id,
                self._assets[asset_id].config.rounds_available,
            )
            if current["rounds_remaining"] != expected:
                raise ValueError(
                    f"ASAT asset {asset_id!r} inventory disagrees with completed orders",
                )
            expected_ready_at = last_ready_at_by_asset.get(asset_id, 0.0)
            if current["ready_at_s"] != expected_ready_at:
                raise ValueError(
                    f"ASAT asset {asset_id!r} cooldown disagrees with completed orders",
                )
        return canonical_pending, staged_completed

    def _validate_completed_result(
        self,
        order_id: str,
        raw: Any,
    ) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != self._RESULT_KEYS:
            raise ValueError(f"invalid completed result for ASAT order {order_id!r}")
        order = self._order_by_id[order_id]
        asset = self._assets[order.asset_id].config
        target = self._cm.get_satellite(order.target_satellite_id)
        if target is None:
            raise ValueError(
                f"configured ASAT target missing during restore: "
                f"{order.target_satellite_id!r}",
            )
        expected_static = {
            "order_id": order_id,
            "asset_id": order.asset_id,
            "weapon_id": asset.weapon_id,
            "attacker_side": asset.side,
            "target_satellite_id": order.target_satellite_id,
            "target_constellation_id": target.constellation_id,
            "scheduled_time_s": float(order.execute_at_s),
        }
        if any(raw.get(key) != value for key, value in expected_static.items()):
            raise ValueError(
                f"ASAT completed result topology mismatch for order {order_id!r}",
            )

        launched = raw["launched"]
        hit = raw["hit"]
        if type(launched) is not bool or type(hit) is not bool:
            raise ValueError(
                f"invalid launch/hit flags for ASAT order {order_id!r}",
            )
        outcome = raw["outcome"]
        reason = raw["reason"]
        if launched:
            if reason != "" or outcome != ("hit" if hit else "miss"):
                raise ValueError(
                    f"incoherent launched result for ASAT order {order_id!r}",
                )
        elif (
            hit
            or outcome != "rejected"
            or reason not in self._REJECTION_REASONS
        ):
            raise ValueError(
                f"incoherent rejected result for ASAT order {order_id!r}",
            )

        execution_time = self._validated_finite_number(
            raw["execution_time_s"],
            f"execution_time_s for order {order_id!r}",
            minimum=order.execute_at_s,
        )
        pk = self._validated_finite_number(
            raw["pk"],
            f"pk for order {order_id!r}",
            minimum=0.0,
            maximum=1.0,
        )
        if (not launched and pk != 0.0) or (
            launched
            and not math.isclose(
                pk,
                self._compute_kinetic_pk(
                    self._weapon_definitions[asset.weapon_id],
                ),
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            raise ValueError(f"invalid pk for ASAT order {order_id!r}")

        integer_fields = (
            "debris_generated",
            "rounds_remaining",
            "previous_constellation_count",
            "new_constellation_count",
        )
        integers: dict[str, int] = {}
        for field in integer_fields:
            value = raw[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"invalid {field} for ASAT order {order_id!r}",
                )
            if field == "debris_generated" and value > _MAX_DEBRIS_COUNT:
                raise ValueError(
                    f"invalid {field} for ASAT order {order_id!r}",
                )
            integers[field] = value
        if (not hit and integers["debris_generated"] != 0) or (
            hit
            and integers["new_constellation_count"]
            != integers["previous_constellation_count"] - 1
        ) or (
            not hit
            and integers["new_constellation_count"]
            != integers["previous_constellation_count"]
        ):
            raise ValueError(
                f"incoherent outcome counts for ASAT order {order_id!r}",
            )
        if integers["rounds_remaining"] > asset.rounds_available:
            raise ValueError(
                f"invalid rounds_remaining for ASAT order {order_id!r}",
            )

        return {
            **expected_static,
            "execution_time_s": execution_time,
            "launched": launched,
            "hit": hit,
            "pk": pk,
            "outcome": outcome,
            "reason": reason,
            **integers,
        }

    @staticmethod
    def _validated_finite_number(
        value: Any,
        label: str,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be finite")
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"{label} must be finite") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} must be finite")
        if number < minimum or (maximum is not None and number > maximum):
            raise ValueError(f"{label} is outside its valid range")
        return number

    def _validate_debris_state(self, debris_state: Any) -> list[dict[str, Any]]:
        if not isinstance(debris_state, list):
            raise TypeError("debris_clouds must be a list")
        staged: list[dict[str, Any]] = []
        expected_keys = {"altitude_band_km", "debris_count", "age_s"}
        for index, raw in enumerate(debris_state):
            if not isinstance(raw, dict) or set(raw) != expected_keys:
                raise ValueError(f"invalid debris cloud state at index {index}")
            altitude = self._validated_finite_number(
                raw["altitude_band_km"],
                f"debris altitude at index {index}",
                minimum=0.0,
            )
            age = self._validated_finite_number(
                raw["age_s"],
                f"debris age at index {index}",
                minimum=0.0,
            )
            count = raw["debris_count"]
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 0 <= count <= _MAX_DEBRIS_COUNT
            ):
                raise ValueError(
                    f"invalid debris count at index {index}",
                )
            staged.append({
                "altitude_band_km": altitude,
                "debris_count": count,
                "age_s": age,
            })
        return staged

    def set_state(self, state: dict[str, Any]) -> None:
        """Atomically restore a previously validated ASAT checkpoint."""
        staged = self.validate_state(state)
        for asset_id, raw in staged["assets"].items():
            self._assets[asset_id].rounds_remaining = raw["rounds_remaining"]
            self._assets[asset_id].ready_at_s = raw["ready_at_s"]
        self._pending_order_ids = set(staged["pending_order_ids"])
        self._completed_orders = copy.deepcopy(staged["completed_orders"])
        self._debris_clouds = [
            DebrisCloud(
                altitude_band_km=raw["altitude_band_km"],
                debris_count=raw["debris_count"],
                age_s=raw["age_s"],
            )
            for raw in staged["debris_clouds"]
        ]


__all__ = [
    "ASATEngine",
    "ASATType",
    "ASATWeaponDefinition",
    "DebrisCloud",
]
