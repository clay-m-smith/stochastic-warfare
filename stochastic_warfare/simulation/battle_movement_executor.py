"""Default deterministic movement executor used by ``BattleManager``."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from stochastic_warfare.simulation.battle import (
    Domain,
    LODReceipt,
    PerformanceReceiptDelta,
    Position,
    TacticalTargetingDecision,
    TargetingDisposition,
    Unit,
    UnitLodTier,
    UnitStatus,
    _NAVAL_POSTURE_SPEED_MULT,
    _POSTURE_SPEED_MULT,
    _movement_target,
    _should_hold_position,
    logger,
    nearest_enemy_weapon_standoff,
)
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleExecutorOwner,
    BattleIntervalView,
    BattleMovementRuntime,
    MovementExecutionRequest,
    ReadonlyValue,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MOVEMENT_EPSILON_M,
    MovementDecision,
    MovementHoldRevalidationOutcome,
    MovementReason,
    MovementStage,
    MovementTargetingMembership,
    resolve_movement_diagnostics_owner,
)
from stochastic_warfare.simulation.performance_flags import LODMovementReceipt


class DefaultBattleMovementExecutor:
    """Preserve candidate, movement-commit, and receipt ordering exactly."""

    def execute(
        self,
        owner: BattleExecutorOwner,
        request: MovementExecutionRequest,
    ) -> None:
        self._execute_movement(
            owner,
            request.runtime,
            request.units_by_side,
            request.active_enemies,
            request.dt_seconds,
            request.battle,
            request.behavior_rules,
            enemy_pos_arrays=request.enemy_position_arrays,
        )

    def _execute_movement(
        self,
        owner: BattleExecutorOwner,
        ctx: BattleMovementRuntime,
        units_by_side: Mapping[str, Sequence[Unit]],
        active_enemies: Mapping[str, Sequence[Unit]],
        dt: float,
        battle: BattleIntervalView | None = None,
        behavior_rules: Mapping[str, ReadonlyValue] | None = None,
        enemy_pos_arrays: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        """Execute movement for all active units."""
        diagnostics, diagnostic_tick = resolve_movement_diagnostics_owner(
            ctx,
            owner.movement_diagnostics,
            boundary="BattleManager",
        )

        cal_flat = ctx.cal_flat
        wave_interval = cal_flat.get("wave_interval_s", 300.0)
        battle_elapsed = battle.battle_elapsed_s if battle is not None else 0.0
        wave_assignments = battle.wave_assignments if battle is not None else {}
        _rules = behavior_rules or {}
        movement_decisions: list[MovementDecision] = []
        targeting_runtime = ctx.tactical_targeting
        battle_member_ids: frozenset[str] | None = None
        targeting_membership: MovementTargetingMembership | None = None
        if targeting_runtime is not None and battle is not None:
            interval = targeting_runtime.prepared_interval
            if interval is None:
                raise RuntimeError(
                    "Movement requires a prepared targeting interval",
                )
            try:
                membership_unit_ids = interval.battle_memberships[battle.battle_id]
                battle_member_ids = frozenset(membership_unit_ids)
                targeting_membership = MovementTargetingMembership(
                    battle_id=battle.battle_id,
                    unit_ids=membership_unit_ids,
                )
            except KeyError as exc:
                raise RuntimeError(
                    f"Battle {battle.battle_id!r} is absent from the prepared targeting interval",
                ) from exc
        movement_tier_counts = {
            UnitLodTier.ACTIVE: 0,
            UnitLodTier.NEARBY: 0,
            UnitLodTier.DISTANT: 0,
        }
        for side_units in units_by_side.values():
            for unit in side_units:
                if unit.status is not UnitStatus.ACTIVE or (
                    battle_member_ids is not None and unit.entity_id not in battle_member_ids
                ):
                    continue
                tier = UnitLodTier(owner.lod_tier(unit.entity_id))
                movement_tier_counts[tier] += 1
        owner.stage_performance_delta(
            PerformanceReceiptDelta(
                lod=LODReceipt(
                    movement=LODMovementReceipt(
                        active_processed=(movement_tier_counts[UnitLodTier.ACTIVE]),
                        nearby_processed=(movement_tier_counts[UnitLodTier.NEARBY]),
                        distant_processed=(movement_tier_counts[UnitLodTier.DISTANT]),
                    ),
                ),
            ),
        )
        movement_unit_index = {unit.entity_id: unit for side_units in units_by_side.values() for unit in side_units}
        hold_revalidations: dict[str, MovementHoldRevalidationOutcome] = {}

        def _resolve_hold_revalidation(
            unit: Unit,
            decision: TacticalTargetingDecision,
        ) -> MovementHoldRevalidationOutcome | None:
            if not decision.can_hold:
                return None
            existing = hold_revalidations.get(unit.entity_id)
            if existing is not None:
                return existing
            if decision.target_id is None:
                raise RuntimeError(
                    "A can-hold targeting decision lacks its target identity",
                )
            live_target = movement_unit_index.get(decision.target_id)
            if live_target is None or battle_member_ids is None or live_target.entity_id not in battle_member_ids:
                raise RuntimeError(
                    "A can-hold targeting decision is absent from its live movement battle topology",
                )
            live_distance_m = owner.targeting_distance(unit, live_target)
            live_disposition = (
                TargetingDisposition.SHOOTER_INACTIVE
                if unit.status is not UnitStatus.ACTIVE
                else owner.revalidate_tactical_engagement(
                    ctx,
                    unit,
                    live_target,
                    decision,
                    current_distance_m=live_distance_m,
                )[0]
            )
            hold_authorized = (
                live_disposition is TargetingDisposition.VALID_ENGAGEMENT_SOLUTION
                and live_distance_m <= decision.authorized_standoff_m
            )
            outcome = MovementHoldRevalidationOutcome(
                engine_tick=decision.engine_tick,
                battle_id=decision.battle_id,
                shooter_id=decision.shooter_id,
                target_id=decision.target_id,
                live_distance_m=live_distance_m,
                disposition=live_disposition,
                hold_authorized=hold_authorized,
            )
            hold_revalidations[unit.entity_id] = outcome
            return outcome

        def _observe(
            unit: Unit,
            reason: MovementReason,
            pre_position: Position,
            *,
            attempted_m: float = 0.0,
        ) -> None:
            targeting_decision = None
            hold_revalidation = None
            if targeting_runtime is not None and battle is not None:
                targeting_decision = targeting_runtime.decision_for(
                    engine_tick=int(ctx.clock.tick_count),
                    battle_id=battle.battle_id,
                    shooter_id=unit.entity_id,
                )
                if targeting_decision is None:
                    raise RuntimeError(
                        f"Tactical diagnostics are missing the published targeting decision for {unit.entity_id!r}",
                    )
                hold_revalidation = _resolve_hold_revalidation(
                    unit,
                    targeting_decision,
                )
                if reason is MovementReason.ENGINE_WEAPON_STANDOFF and (
                    hold_revalidation is None or not hold_revalidation.hold_authorized
                ):
                    raise RuntimeError(
                        "Automatic standoff movement requires an authorized live hold revalidation",
                    )
            movement_decisions.append(
                MovementDecision(
                    unit_id=unit.entity_id,
                    side=unit.side,
                    reason=reason,
                    attempted_m=attempted_m,
                    pre_position=pre_position,
                    post_position=unit.position,
                    targeting_decision=targeting_decision,
                    targeting_membership=(targeting_membership if targeting_decision is not None else None),
                    hold_revalidation=hold_revalidation,
                )
            )

        # Sides that should hold position (defensive doctrine)
        defensive_sides = set(cal_flat.get("defensive_sides", []))

        # Phase 70c: hoist movement-loop calibration lookups
        _mv_enable_sea_state = cal_flat.get("enable_sea_state_ops", False)
        _mv_enable_seasonal = cal_flat.get("enable_seasonal_effects", False)
        _mv_enable_obstacle = cal_flat.get("enable_obstacle_effects", False)
        _mv_enable_fire_zones = cal_flat.get("enable_fire_zones", False)
        _mv_enable_obscurants = cal_flat.get("enable_obscurants", False)
        _mv_enable_fuel = cal_flat.get("enable_fuel_consumption", False)
        _mv_enable_ice_crossing = cal_flat.get("enable_ice_crossing", False)
        _mv_enable_bridge = cal_flat.get("enable_bridge_capacity", False)

        # Phase 70c: hoist movement-loop engine references
        _mv_maint_eng = ctx.maintenance_engine
        _mv_seasons_eng = ctx.seasons_engine
        _mv_weather_eng = ctx.weather_engine
        _mv_trench_eng = ctx.trench_engine
        _mv_obs_eng = ctx.obscurants_engine
        _mv_inc_eng = ctx.incendiary_engine
        _mv_obstacle_mgr = ctx.obstacle_manager
        _mv_hydro = ctx.hydrography_manager
        _mv_infra = ctx.bridge_infrastructure
        _mv_movement_eng = ctx.movement_engine
        _mv_classif = ctx.classification

        # Phase 78b: weight defaults for bridge capacity enforcement
        _WEIGHT_DEFAULTS: dict[str, float] = {
            "m1a2_abrams": 62.0,
            "t72b": 41.0,
            "t90a": 46.5,
            "leopard_2a6": 62.3,
            "challenger_2": 62.5,
            "m2_bradley": 27.6,
            "bmp2": 14.3,
            "btr80": 13.6,
            "m113": 12.3,
            "stryker": 18.0,
        }

        for side, units in units_by_side.items():
            enemies = active_enemies.get(side, [])
            if battle_member_ids is not None:
                enemies = [enemy for enemy in enemies if enemy.entity_id in battle_member_ids]
            if not enemies:
                for u in units:
                    if battle_member_ids is not None and u.entity_id not in battle_member_ids:
                        continue
                    _observe(
                        u,
                        (MovementReason.NO_TARGET if u.status == UnitStatus.ACTIVE else MovementReason.INACTIVE),
                        u.position,
                    )
                continue
            # Phase 70a: pre-fetched numpy position array for vectorized helpers
            _epa = enemy_pos_arrays.get(side) if enemy_pos_arrays is not None else None
            if battle_member_ids is not None:
                _epa = None

            # If behavior_rules explicitly say hold_position, skip this side
            side_rules = _rules.get(side, {})
            if not isinstance(side_rules, Mapping):
                raise TypeError(f"behavior rule for side {side!r} must be a mapping")
            if side_rules.get("hold_position", False):
                for u in units:
                    if battle_member_ids is not None and u.entity_id not in battle_member_ids:
                        continue
                    _observe(
                        u,
                        (MovementReason.AUTHORED_HOLD if u.status == UnitStatus.ACTIVE else MovementReason.INACTIVE),
                        u.position,
                    )
                continue

            # Defensive sides don't advance
            if side in defensive_sides:
                for u in units:
                    if battle_member_ids is not None and u.entity_id not in battle_member_ids:
                        continue
                    _observe(
                        u,
                        (MovementReason.DEFENSIVE_HOLD if u.status == UnitStatus.ACTIVE else MovementReason.INACTIVE),
                        u.position,
                    )
                continue

            # Phase 70b: hoist formation sort — compute once per side, not per unit
            _sorted_active = sorted(
                [
                    ou
                    for ou in units
                    if (
                        ou.status == UnitStatus.ACTIVE
                        and (battle_member_ids is None or ou.entity_id in battle_member_ids)
                    )
                ],
                key=lambda ou: ou.entity_id,
            )
            _unit_formation_idx: dict[str, int] = {ou.entity_id: i for i, ou in enumerate(_sorted_active)}
            _n_sorted = len(_sorted_active)
            # Phase 70c: hoist side-specific formation spacing
            _spacing_side = cal_flat.get(
                f"{side}_formation_spacing_m",
                cal_flat.get("formation_spacing_m", 50.0),
            )

            for u in units:
                if battle_member_ids is not None and u.entity_id not in battle_member_ids:
                    continue
                pre_position = u.position
                if u.status != UnitStatus.ACTIVE:
                    _observe(u, MovementReason.INACTIVE, pre_position)
                    continue

                # Emplaced / air-defense units hold position
                if _should_hold_position(u):
                    _observe(
                        u,
                        MovementReason.EMPLACED_HOLD,
                        pre_position,
                    )
                    continue

                # Effective speed: use current speed (set by behavior_rules
                # or AI), fall back to max_speed for scenarios without rules
                effective_speed = u.speed if u.speed > 0 else u.max_speed
                if effective_speed <= 0:
                    _observe(
                        u,
                        MovementReason.RESOURCE_BLOCKED,
                        pre_position,
                    )
                    continue

                # Phase 50a: posture → movement speed multiplier
                posture_val = getattr(u, "posture", None)
                if posture_val is not None:
                    posture_int = int(posture_val)
                    if posture_int >= 3:  # DUG_IN or FORTIFIED
                        uid = u.entity_id
                        # Defensive sides stay dug in — no un-dig
                        if side not in defensive_sides:
                            if not owner.is_undigging(uid):
                                # First tick: start un-digging, skip movement
                                owner.begin_undigging(uid)
                                object.__setattr__(u, "posture", type(u.posture)(0))
                                _observe(
                                    u,
                                    MovementReason.DEFENSIVE_HOLD,
                                    pre_position,
                                )
                                continue
                            else:
                                # Second tick: cleared to move
                                owner.finish_undigging(uid)
                        else:
                            _observe(
                                u,
                                MovementReason.DEFENSIVE_HOLD,
                                pre_position,
                            )
                            continue  # Defensive side stays put
                    speed_mult = _POSTURE_SPEED_MULT.get(posture_int, 1.0)
                    effective_speed *= speed_mult
                    if effective_speed <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                # Phase 51b: naval posture → speed multiplier
                np_val = getattr(u, "naval_posture", None)
                if np_val is not None:
                    effective_speed *= _NAVAL_POSTURE_SPEED_MULT.get(int(np_val), 1.0)
                    if effective_speed <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                # Sea-state hull penalty is independent of the movement
                # vector.  Tidal projection is applied only after the current
                # unit's final target vector has been resolved below.
                if _mv_enable_sea_state:
                    _domain_61 = getattr(u, "domain", None)
                    if _domain_61 in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS):
                        _sse = ctx.sea_state_engine
                        if _sse is not None:
                            _sea = _sse.current
                            _bf = _sea.beaufort_scale
                            # Small craft speed penalty: −20% per Beaufort above 3
                            _disp = getattr(u, "displacement_tons", 0)
                            _is_small = _disp > 0 and _disp < 1000
                            if not _is_small:
                                _is_small = effective_speed > 0 and getattr(u, "max_speed", 0) < 15
                            if _is_small and _bf > 3:
                                _bf_pen = max(0.0, 1.0 - 0.2 * (_bf - 3))
                                effective_speed *= _bf_pen
                        if effective_speed <= 0:
                            _observe(
                                u,
                                MovementReason.RESOURCE_BLOCKED,
                                pre_position,
                            )
                            continue

                # Phase 56b: readiness-based movement speed penalty
                if _mv_maint_eng is not None:
                    try:
                        _rdns = _mv_maint_eng.get_unit_readiness(u.entity_id)
                        if _rdns < 1.0:
                            effective_speed *= max(0.3, _rdns)
                            if effective_speed <= 0:
                                _observe(
                                    u,
                                    MovementReason.RESOURCE_BLOCKED,
                                    pre_position,
                                )
                                continue
                    except KeyError:
                        pass
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "logistics.maintenance",
                            "get_unit_readiness",
                            exc,
                        ):
                            raise

                # Wave gating: check if this unit's wave has been released
                wave = wave_assignments.get(u.entity_id, 0)
                if wave == -1:
                    _observe(
                        u,
                        MovementReason.RESERVE_OR_UNRELEASED,
                        pre_position,
                    )
                    continue  # Reserve — never moves
                if wave > 0 and battle_elapsed < wave * wave_interval:
                    _observe(
                        u,
                        MovementReason.RESERVE_OR_UNRELEASED,
                        pre_position,
                    )
                    continue  # Wave not yet released

                # Phase 115: production automatic standoff consumes the exact
                # pre-movement composite decision.  The catalog-maximum helper
                # remains only for explicit legacy unit fixtures that do not
                # own the targeting runtime.
                if targeting_runtime is not None and battle is not None:
                    targeting_decision = targeting_runtime.decision_for(
                        engine_tick=int(ctx.clock.tick_count),
                        battle_id=battle.battle_id,
                        shooter_id=u.entity_id,
                    )
                    if targeting_decision is None:
                        raise RuntimeError(
                            f"Tactical movement is missing its published targeting decision for {u.entity_id!r}",
                        )
                    if targeting_decision.can_hold:
                        hold_revalidation = _resolve_hold_revalidation(
                            u,
                            targeting_decision,
                        )
                        if hold_revalidation is not None and hold_revalidation.hold_authorized:
                            _observe(
                                u,
                                MovementReason.ENGINE_WEAPON_STANDOFF,
                                pre_position,
                            )
                            continue
                else:
                    nearest_index, nearest_dist, standoff = nearest_enemy_weapon_standoff(
                        u,
                        ctx,
                        enemies,
                        enemy_pos_arr=_epa,
                    )
                    if nearest_index is None:
                        _observe(u, MovementReason.NO_TARGET, pre_position)
                        continue
                    if nearest_dist <= standoff:
                        _observe(
                            u,
                            MovementReason.ENGINE_WEAPON_STANDOFF,
                            pre_position,
                        )
                        continue

                # Blend centroid + nearest enemy for movement target,
                # then add a perpendicular offset to maintain formation
                # spacing and prevent centroid collapse.
                tx, ty = _movement_target(u.position, enemies, enemy_pos_arr=_epa)
                dx = tx - u.position.easting
                dy = ty - u.position.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < 1.0:
                    _observe(u, MovementReason.NO_TARGET, pre_position)
                    continue

                # Phase 70b: hoisted formation index — O(1) lookup per unit
                if _n_sorted > 1:
                    _idx = _unit_formation_idx.get(u.entity_id, 0)
                    # Lateral offset: center the formation around the advance
                    # axis so units stay evenly spaced perpendicular to the
                    # direction of movement.
                    _lat_offset = (_idx - (_n_sorted - 1) / 2.0) * _spacing_side
                    perp_x, perp_y = -dy / dist, dx / dist
                    tx += perp_x * _lat_offset
                    ty += perp_y * _lat_offset
                    # Recompute advance vector
                    dx = tx - u.position.easting
                    dy = ty - u.position.northing
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < 1.0:
                        _observe(u, MovementReason.NO_TARGET, pre_position)
                        continue

                if (
                    _mv_enable_sea_state
                    and getattr(u, "domain", None)
                    in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS)
                ):
                    _sse = ctx.sea_state_engine
                    if _sse is not None:
                        _sea = _sse.current
                        # Position uses (easting, northing), so atan2 receives
                        # (east, north) and zero radians denotes north.
                        _heading = math.atan2(dx, dy)
                        _tc_effect = _sea.tidal_current_speed * math.cos(
                            _sea.tidal_current_direction - _heading,
                        )
                        effective_speed = max(
                            0.0,
                            effective_speed + _tc_effect,
                        )
                        if effective_speed <= 0.0:
                            _observe(
                                u,
                                MovementReason.RESOURCE_BLOCKED,
                                pre_position,
                            )
                            continue

                # Phase 54b: trench movement factor (WW1)
                if _mv_trench_eng is not None and u.position is not None:
                    try:
                        mvt_factor = _mv_trench_eng.movement_factor_at(
                            u.position.easting,
                            u.position.northing,
                        )
                        if mvt_factor < 1.0:
                            effective_speed *= mvt_factor
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "terrain.trenches",
                            "movement_factor_at",
                            exc,
                        ):
                            raise
                        pass

                # Phase 59a: seasonal ground condition speed modifier
                if _mv_seasons_eng is not None and _mv_enable_seasonal:
                    _domain = getattr(u, "domain", None)
                    if _domain not in (Domain.NAVAL, Domain.AERIAL, Domain.SUBMARINE):
                        _sc = _mv_seasons_eng.current
                        _ms = getattr(u, "max_speed", 0)
                        if _ms > 15:  # wheeled
                            _mud_mult = max(0.1, 1.0 - _sc.mud_depth / 0.3)
                        elif _ms > 5:  # tracked
                            _mud_mult = max(0.3, 1.0 - _sc.mud_depth / 0.5)
                        else:  # foot
                            _mud_mult = max(0.4, 1.0 - _sc.mud_depth / 0.4)
                        _snow_mult = max(0.4, 1.0 - _sc.snow_depth / 0.5)
                        _traf_mult = _sc.ground_trafficability
                        effective_speed *= _mud_mult * _snow_mult * _traf_mult
                        if effective_speed <= 0:
                            _observe(
                                u,
                                MovementReason.RESOURCE_BLOCKED,
                                pre_position,
                            )
                            continue

                # Phase 59c: wind gust operational gates
                if _mv_weather_eng is not None and _mv_enable_seasonal:
                    _gust = getattr(_mv_weather_eng.current.wind, "gust", 0)
                    _domain = getattr(u, "domain", None)
                    if _domain == Domain.AERIAL:
                        _utype = str(getattr(u, "unit_type", ""))
                        if "HELO" in _utype.upper() or "HELICOPTER" in _utype.upper():
                            if _gust > 15.0:
                                _observe(
                                    u,
                                    MovementReason.RESOURCE_BLOCKED,
                                    pre_position,
                                )
                                continue
                    if _domain in (None, Domain.GROUND) and getattr(u, "max_speed", 0) <= 5.0:
                        if _gust > 25.0:
                            _observe(
                                u,
                                MovementReason.RESOURCE_BLOCKED,
                                pre_position,
                            )
                            continue

                # MOPP speed factor (Phase 25c)
                mopp_speed_factor = 1.0
                cbrn = ctx.cbrn_engine
                if cbrn is not None:
                    mopp_level = cbrn.get_mopp_level(u.entity_id)
                    if mopp_level > 0:
                        from stochastic_warfare.cbrn.protection import ProtectionEngine

                        mopp_speed_factor = ProtectionEngine.get_mopp_speed_factor(mopp_level)

                # Production targeting has already decided whether a hold is
                # authorized.  With no solution, force-closure movement has no
                # hidden ground-truth range floor.  The legacy fixture path
                # retains its historical overshoot guard.
                max_close = (
                    dist if targeting_runtime is not None and battle is not None else max(0.0, nearest_dist - standoff)
                )
                move_dist = min(effective_speed * dt * mopp_speed_factor, dist, max_close)
                if move_dist <= 0:
                    _observe(
                        u,
                        MovementReason.RESOURCE_BLOCKED,
                        pre_position,
                    )
                    continue

                # Phase 58e: fuel gate — vehicles with no fuel cannot move
                _fuel = getattr(u, "fuel_remaining", 1.0)
                _is_vehicle = getattr(u, "max_speed", 0) > 5.0
                if _fuel <= 0.0 and _is_vehicle:
                    _observe(
                        u,
                        MovementReason.RESOURCE_BLOCKED,
                        pre_position,
                    )
                    continue

                # Phase 59d: obstacle traversal speed reduction
                if _mv_enable_obstacle:
                    if _mv_obstacle_mgr is not None:
                        try:
                            _obstacles = _mv_obstacle_mgr.obstacles_at(u.position)
                            for _obs in _obstacles:
                                _tmult = getattr(_obs, "traversal_time_multiplier", 1.0)
                                if _tmult > 1.0:
                                    move_dist /= _tmult
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "terrain.obstacles",
                                "obstacles_at",
                                exc,
                            ):
                                raise
                            pass
                    if move_dist <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                # Phase 78a: ice crossing speed penalty + water cell gate
                if _mv_enable_ice_crossing and _mv_seasons_eng is not None:
                    _tent_ix = u.position.easting + (dx / dist) * move_dist
                    _tent_iy = u.position.northing + (dy / dist) * move_dist
                    _tent_pos_ice = Position(_tent_ix, _tent_iy)
                    if _mv_movement_eng is not None:
                        _ice_snap = _mv_seasons_eng.current
                        if _mv_movement_eng.is_on_ice(u.position, _ice_snap):
                            move_dist *= 0.5  # 50% speed on ice
                        # Block movement into unfrozen water
                        if _mv_classif is not None:
                            try:
                                from stochastic_warfare.terrain.classification import LandCover as _LC78

                                _tent_lc = _mv_classif.land_cover_at(_tent_pos_ice)
                                if _tent_lc == _LC78.WATER:
                                    if not _mv_movement_eng.is_on_ice(_tent_pos_ice, _ice_snap):
                                        _observe(
                                            u,
                                            MovementReason.RESOURCE_BLOCKED,
                                            pre_position,
                                        )
                                        continue
                            except (IndexError, ValueError) as exc:
                                if not owner.suppress_runtime_failure(
                                    "terrain.classification",
                                    "land_cover_at",
                                    exc,
                                ):
                                    raise
                                pass
                    if move_dist <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                # Phase 78b: bridge capacity + ford crossing
                if _mv_enable_bridge:
                    _tent_bx = u.position.easting + (dx / dist) * move_dist
                    _tent_by = u.position.northing + (dy / dist) * move_dist
                    _tent_bpos = Position(_tent_bx, _tent_by)
                    _u_weight = getattr(u, "weight_tons", 0.0) or _WEIGHT_DEFAULTS.get(u.unit_type, 0.0)
                    # Check bridge capacity
                    _blocked_bridge = False
                    if _mv_infra is not None and _u_weight > 0:
                        try:
                            _bridges = _mv_infra.bridges_near(_tent_bpos, 50.0)
                            for _br in _bridges:
                                if _u_weight > _br.capacity_tons:
                                    logger.debug(
                                        "Unit %s (%.1ft) blocked by bridge %s (%.1ft capacity)",
                                        u.entity_id,
                                        _u_weight,
                                        _br.bridge_id,
                                        _br.capacity_tons,
                                    )
                                    _blocked_bridge = True
                                    break
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "terrain.infrastructure",
                                "bridges_near",
                                exc,
                            ):
                                raise
                            pass
                    if _blocked_bridge:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue
                    # Ford crossing: allow at 30% speed
                    if _mv_hydro is not None:
                        try:
                            if _mv_hydro.is_in_water(_tent_bpos):
                                _fords = _mv_hydro.ford_points_near(_tent_bpos, 500.0)
                                if _fords:
                                    move_dist *= 0.3
                                else:
                                    # No ford — block unless ice allows
                                    if not (
                                        _mv_enable_ice_crossing
                                        and _mv_seasons_eng is not None
                                        and _mv_movement_eng is not None
                                        and _mv_movement_eng.is_on_ice(_tent_bpos, _mv_seasons_eng.current)
                                    ):
                                        _observe(
                                            u,
                                            MovementReason.RESOURCE_BLOCKED,
                                            pre_position,
                                        )
                                        continue
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "terrain.hydrography",
                                "resolve_ford_crossing",
                                exc,
                            ):
                                raise
                            pass
                    if move_dist <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                # Phase 60b: fire zones block movement
                if _mv_enable_fire_zones and _mv_inc_eng is not None:
                    _tent_nx = u.position.easting + (dx / dist) * move_dist
                    _tent_ny = u.position.northing + (dy / dist) * move_dist
                    if _mv_inc_eng.position_in_active_fire(
                        Position(_tent_nx, _tent_ny, u.position.altitude),
                    ):
                        move_dist = 0
                    if move_dist <= 0:
                        _observe(
                            u,
                            MovementReason.RESOURCE_BLOCKED,
                            pre_position,
                        )
                        continue

                nx = u.position.easting + (dx / dist) * move_dist
                ny = u.position.northing + (dy / dist) * move_dist
                proposed_position = Position(nx, ny, u.position.altitude)
                committed_position = owner.movement_committer(
                    u,
                    proposed_position,
                )
                if not isinstance(committed_position, Position):
                    raise TypeError(
                        "movement_committer must return a Position",
                    )
                object.__setattr__(u, "position", committed_position)

                # Phase 60b: vehicle movement dust trail on dry ground
                if _mv_obs_eng is not None and _mv_enable_obscurants:
                    _domain = getattr(u, "domain", None)
                    if _domain not in (Domain.NAVAL, Domain.AERIAL, Domain.SUBMARINE):
                        if _is_vehicle and move_dist > 5.0:
                            _is_dry = True
                            if _mv_seasons_eng is not None:
                                from stochastic_warfare.environment.seasons import GroundState

                                _is_dry = _mv_seasons_eng.current.ground_state == GroundState.DRY
                            if _is_dry:
                                try:
                                    _dust_r = 10.0 + effective_speed * 0.5
                                    _mv_obs_eng.add_dust(u.position, radius=_dust_r)
                                except Exception as exc:
                                    if not owner.suppress_runtime_failure(
                                        "environment.obscurants",
                                        "add_movement_dust",
                                        exc,
                                    ):
                                        raise
                                    pass

                # Phase 68a: consume fuel proportional to distance moved
                if _mv_enable_fuel and _is_vehicle and hasattr(u, "fuel_remaining"):
                    _domain_fuel = getattr(u, "domain", None)
                    _fuel_rate = getattr(u, "fuel_consumption_rate", None)
                    if _fuel_rate is None:
                        # Rates per meter of 0.0–1.0 fuel fraction.
                        # Ground: ~500km range → 0.000002/m.  Aerial: ~3000km → 0.0000003/m.
                        # Naval: ~10,000km → 0.0000001/m.
                        if _domain_fuel == Domain.AERIAL:
                            _fuel_rate = 0.0000003
                        elif _domain_fuel == Domain.NAVAL:
                            _fuel_rate = 0.0000001
                        else:
                            _fuel_rate = 0.000002  # ground default ~500km range
                    _new_fuel = max(0.0, u.fuel_remaining - move_dist * _fuel_rate)
                    object.__setattr__(u, "fuel_remaining", _new_fuel)
                    if _new_fuel <= 0.0:
                        object.__setattr__(u, "speed", 0.0)
                        logger.warning("Unit %s out of fuel — speed set to 0", u.entity_id)

                achieved_m = math.sqrt(
                    (u.position.easting - pre_position.easting) ** 2
                    + (u.position.northing - pre_position.northing) ** 2
                    + (u.position.altitude - pre_position.altitude) ** 2
                )
                if move_dist <= MOVEMENT_EPSILON_M:
                    movement_reason = MovementReason.RESOURCE_BLOCKED
                elif achieved_m <= MOVEMENT_EPSILON_M:
                    movement_reason = MovementReason.ZERO_PROGRESS
                else:
                    movement_reason = MovementReason.MOVED
                _observe(
                    u,
                    movement_reason,
                    pre_position,
                    attempted_m=(move_dist if move_dist > MOVEMENT_EPSILON_M else 0.0),
                )

        if diagnostics is not None:
            assert diagnostic_tick is not None
            diagnostics.record_batch(
                engine_tick=diagnostic_tick,
                stage=MovementStage.TACTICAL,
                battle_id=(battle.battle_id if battle is not None else ""),
                decisions=movement_decisions,
            )
