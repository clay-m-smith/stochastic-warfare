"""Default deterministic engagement executor used by ``BattleManager``."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy as np
from shapely import STRtree
from shapely.geometry import Point

from stochastic_warfare.combat.engagement import EngagementType
from stochastic_warfare.combat.unconventional import (
    UnsupportedGuerrillaBlendError,
)
from stochastic_warfare.morale.state import _MORALE_EFFECTS
from stochastic_warfare.simulation.battle import (
    Domain,
    GroundUnitType,
    LODReceipt,
    ModuleId,
    MoraleState,
    PerformanceReceiptDelta,
    Position,
    SensorAttachment,
    SensorType,
    TacticalTargetingDecision,
    TargetingDisposition,
    Unit,
    UnitStatus,
    WeaponAttachment,
    WeaponCategory,
    WeaponModeledRole,
    _AIR_DELIVERY_ROLES,
    _DEFAULT_OBS_MODS,
    _EngagementIntent,
    _INDIRECT_FIRE_CATEGORIES,
    _INDIRECT_FIRE_ROLES,
    _MELEE_RANGE_M,
    _NAVAL_POSTURE_DETECT_MULT,
    _NAVAL_SUBSURFACE_ROLES,
    _ObserverModifiers,
    _WEATHER_BYPASS_TYPES,
    _apply_melee_result,
    _compute_crosswind_penalty,
    _compute_night_modifiers,
    _compute_rain_detection_factor,
    _compute_weather_pk_modifier,
    _consume_routed_ammunition,
    _get_formation_firepower,
    _infer_melee_type,
    _infer_missile_type,
    _route_air_engagement,
    _routed_shot_fired,
    _weapon_supports_domain,
    logger,
    saturating_range_power,
    saturating_range_product,
    weapon_role_uses_tactical_direct_engagement,
)
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleExecutorOwner,
    BattleEngagementRuntime,
    BattleIntervalView,
    EngagementExecutionRequest,
)
from stochastic_warfare.simulation.performance_flags import LODEngagementReceipt


_SONAR_SENSOR_TYPES = frozenset(
    {
        SensorType.ACTIVE_SONAR,
        SensorType.PASSIVE_SONAR,
        SensorType.PASSIVE_ACOUSTIC,
    },
)
_SURFACE_DUCT_POSITIVE_MULTIPLIER = 3.0
_CONVERGENCE_ZONE_POSITIVE_MULTIPLIER = 2.0
_MAX_POSITIVE_ACOUSTIC_LAYER_MULTIPLIER = (
    _SURFACE_DUCT_POSITIVE_MULTIPLIER
    * _CONVERGENCE_ZONE_POSITIVE_MULTIPLIER
)


class DefaultBattleEngagementExecutor:
    """Preserve engagement candidate, RNG, event, and damage order exactly."""

    def execute(
        self,
        owner: BattleExecutorOwner,
        request: EngagementExecutionRequest,
    ) -> list[tuple[Unit, UnitStatus, str]]:
        return self._execute_engagements(
            owner,
            request.runtime,
            request.units_by_side,
            request.active_enemies,
            request.enemy_position_arrays,
            request.dt_seconds,
            request.timestamp,
            _unit_index=request.unit_index,
            battle=request.battle,
        )

    def _execute_engagements(
        self,
        owner: BattleExecutorOwner,
        ctx: BattleEngagementRuntime,
        units_by_side: Mapping[str, Sequence[Unit]],
        active_enemies: Mapping[str, Sequence[Unit]],
        enemy_pos_arrays: Mapping[str, np.ndarray],
        dt: float,
        timestamp: datetime,
        _unit_index: Mapping[str, Unit] | None = None,
        battle: BattleIntervalView | None = None,
    ) -> list[tuple[Unit, UnitStatus, str]]:
        """Run detection + engagement for all units. Returns deferred damage."""
        pending_damage: list[tuple[Unit, UnitStatus, str]] = []
        cal_flat = ctx.cal_flat
        config_view = owner.config_view
        targeting_runtime = ctx.tactical_targeting
        targeting_member_ids: frozenset[str] | None = None
        if targeting_runtime is not None and battle is not None:
            interval = targeting_runtime.prepared_interval
            if interval is None:
                raise RuntimeError(
                    "Engagement requires a prepared targeting interval",
                )
            try:
                targeting_member_ids = frozenset(
                    interval.battle_memberships[battle.battle_id],
                )
            except KeyError as exc:
                raise RuntimeError(
                    f"Battle {battle.battle_id!r} is absent from the prepared targeting interval",
                ) from exc
        visibility_m = owner.targeting_visibility_bound(
            ctx,
            calibration=cal_flat,
        )
        hit_prob_mod = cal_flat.get("hit_probability_modifier", 1.0)
        # Per-side target_size_modifier: look up target_size_modifier_{side}, fall back to uniform
        target_size_mod_default = cal_flat.get("target_size_modifier", 1.0)
        # Phase 41a: force channeling
        max_engagers = cal_flat.get("max_engagers_per_side", 0)
        # Phase 41c: target selection mode
        target_selection_mode = cal_flat.get("target_selection_mode", "threat_scored")

        # Phase 44a/52b: Weather combat effects (computed once per tick)
        weather_pk_modifier = 1.0
        wind_e = 0.0
        wind_n = 0.0
        precipitation_rate_mmhr = 0.0
        weather_engine = ctx.weather_engine
        if weather_engine is not None:
            try:
                conditions = weather_engine.current
                # Precipitation Pk penalty
                weather_pk_modifier = _compute_weather_pk_modifier(
                    int(conditions.state),
                )
                # Phase 52b: extract wind for crosswind penalty
                wind = conditions.wind
                wind_e = -wind.speed * math.sin(wind.direction)
                wind_n = -wind.speed * math.cos(wind.direction)
                # Phase 52b: extract precipitation for radar attenuation
                precipitation_rate_mmhr = conditions.precipitation_rate
            except Exception as exc:
                if not owner.suppress_runtime_failure(
                    "environment.weather",
                    "read_engagement_conditions",
                    exc,
                ):
                    raise
                pass

        # Phase 52a: Night combat effects — continuous twilight gradation
        night_visual_modifier = 1.0
        night_thermal_modifier = 1.0
        tod_engine = ctx.time_of_day_engine
        lat = ctx.config.latitude
        lon = ctx.config.longitude
        if tod_engine is not None:
            try:
                illum = tod_engine.illumination_at(lat, lon)
                _thermal_floor = cal_flat.get("night_thermal_floor", 0.8)
                night_visual_modifier, night_thermal_modifier = _compute_night_modifiers(illum, _thermal_floor)
            except Exception as exc:
                if not owner.suppress_runtime_failure(
                    "environment.time_of_day",
                    "illumination_at",
                    exc,
                ):
                    raise
                pass

        # Phase 60c: physics-based thermal ΔT model (computed once per tick)
        thermal_dt_contrast = 1.0
        if cal_flat.get("enable_thermal_crossover", False) and tod_engine is not None:
            try:
                _therm = tod_engine.thermal_environment(lat, lon)
                # Base contrast from solar-elevation model, scaled by scenario
                # calibration (thermal_contrast > 1 = superior thermal sights,
                # e.g. M1A1 in desert night).
                _cal_tc = cal_flat.get("thermal_contrast", 1.0)
                thermal_dt_contrast = min(1.0, _therm.thermal_contrast * _cal_tc)
                if _therm.crossover_in_hours < 0.5:
                    thermal_dt_contrast *= max(0.1, _therm.crossover_in_hours / 0.5)
            except Exception as exc:
                if not owner.suppress_runtime_failure(
                    "environment.time_of_day",
                    "thermal_environment",
                    exc,
                ):
                    raise
                pass

        # Phase 44a: Sea state effects (computed once per tick)
        sea_dispersion_modifier = 1.0
        _sea_wave_period = 0.0
        _sea_wave_dir = 0.0
        _sea_beaufort = 0
        sea_state_engine = ctx.sea_state_engine
        if sea_state_engine is not None:
            try:
                sea = sea_state_engine.current
                _sea_beaufort = sea.beaufort_scale
                _sea_wave_period = sea.wave_period
                _sea_wave_dir = sea.tidal_current_direction  # swell direction
                if sea.beaufort_scale > 4:
                    sea_dispersion_modifier = 1.0 + 0.2 * (sea.beaufort_scale - 4)
            except Exception as exc:
                if not owner.suppress_runtime_failure(
                    "environment.sea_state",
                    "read_engagement_conditions",
                    exc,
                ):
                    raise
                pass

        # Phase 42a: ROE engine and hold-fire discipline
        roe_engine = ctx.roe_engine
        roe_level_str = cal_flat.get("roe_level", None)
        if roe_engine is not None and roe_level_str is not None:
            from stochastic_warfare.c2.roe import RoeLevel

            try:
                roe_engine.configure_default_level(
                    RoeLevel[roe_level_str.upper()],
                )
            except (KeyError, AttributeError) as exc:
                if not owner.suppress_runtime_failure(
                    "c2.rules_of_engagement",
                    "configure_default_level",
                    exc,
                ):
                    raise
                pass
        behavior_rules = ctx.config.behavior_rules

        if ctx.engagement_engine is None:
            return pending_damage

        # Phase 70c/86a: hoist calibration lookups into local variables
        _enable_seasonal = cal_flat.get("enable_seasonal_effects", False)
        _enable_em_prop = cal_flat.get("enable_em_propagation", False)
        _enable_nvg = cal_flat.get("enable_nvg_detection", False)
        _enable_thermal_xo = cal_flat.get("enable_thermal_crossover", False)
        _enable_obscurants = cal_flat.get("enable_obscurants", False)
        _enable_acoustic = cal_flat.get("enable_acoustic_layers", False)
        _enable_human_factors = cal_flat.get("enable_human_factors", False)
        _enable_air_combat_env = cal_flat.get("enable_air_combat_environment", False)
        _enable_unconventional = cal_flat.get("enable_unconventional_warfare", False)
        _enable_ammo_gate = cal_flat.get("enable_ammo_gate", False)
        _enable_fire_zones = cal_flat.get("enable_fire_zones", False)
        _enable_missile_routing = cal_flat.get("enable_missile_routing", False)
        _enable_air_routing = cal_flat.get("enable_air_routing", False)
        _enable_sea_state_ops = cal_flat.get("enable_sea_state_ops", False)
        _enable_equip_stress = cal_flat.get("enable_equipment_stress", False)
        _observation_decay = cal_flat.get("observation_decay_rate", 0.05)
        _rain_atten_factor = cal_flat.get("rain_attenuation_factor", 1.0)
        _stealth_penalty = cal_flat.get("stealth_detection_penalty", 0.0)
        _sigint_bonus = cal_flat.get("sigint_detection_bonus", 0.0)
        _eng_conceal_thresh = cal_flat.get("engagement_concealment_threshold", 0.5)
        _dest_thresh = cal_flat.get(
            "destruction_threshold",
            config_view.destruction_threshold,
        )
        _dis_thresh = cal_flat.get(
            "disable_threshold",
            config_view.disable_threshold,
        )
        _sam_supp = cal_flat.get("sam_suppression_modifier", 0.0)
        _wind_accuracy_scale = cal_flat.get("wind_accuracy_penalty_scale", 0.03)
        _jammer_mult = cal_flat.get("jammer_coverage_mult", 1.0)
        _dew_disable_thresh = cal_flat.get("dew_disable_threshold", 0.5)
        _night_thermal_floor = cal_flat.get("night_thermal_floor", 0.8)

        # Phase 70c: hoist engine references (each getattr is O(1) but ~95 per tick)
        _weather_eng = ctx.weather_engine
        _tod_eng = ctx.time_of_day_engine
        _sea_eng = ctx.sea_state_engine
        _cbrn_eng = ctx.cbrn_engine
        _obs_eng = ctx.obscurants_engine
        _ua_eng = ctx.underwater_acoustics_engine
        _ew_eng = ctx.ew_engine
        _eccm_eng = ctx.eccm_engine
        _det_eng = ctx.detection_engine
        _space_eng = ctx.space_engine
        _seasons_eng = ctx.seasons_engine
        _maint_eng = ctx.maintenance_engine
        _inc_eng = ctx.incendiary_engine
        _conditions_eng = ctx.conditions_engine
        _conditions_facade = ctx.conditions_facade
        _gas_eng = ctx.gas_warfare_engine
        _uw_eng = ctx.unconventional_engine
        _pop_eng = ctx.population_engine
        _sup_eng = ctx.suppression_engine
        # Phase 84c: Build per-side enemy STRtrees for engagement culling
        _eng_trees: dict[str, STRtree | None] = {}
        for _et_side in units_by_side:
            _et_pos = enemy_pos_arrays.get(_et_side)
            if _et_pos is not None and _et_pos.shape[0] > 0:
                _et_pts = [Point(_et_pos[i, 0], _et_pos[i, 1]) for i in range(_et_pos.shape[0])]
                _eng_trees[_et_side] = STRtree(_et_pts)
            else:
                _eng_trees[_et_side] = None

        # Phase 86b: Batch per-observer modifiers — compute once per unit,
        # reuse across all targets/weapons.
        _observer_mods: dict[str, _ObserverModifiers] = {}
        _obs_alt_thresh = cal_flat.get("altitude_sickness_threshold_m", 2500.0)
        _obs_alt_rate = cal_flat.get("altitude_sickness_rate", 0.03)
        _obs_fov_full = cal_flat.get("mopp_fov_reduction_4", 0.7)
        _obs_rl_full = cal_flat.get("mopp_reload_factor_4", 1.5)
        for _obs_units in units_by_side.values():
            for _obs_u in _obs_units:
                if _obs_u.status != UnitStatus.ACTIVE:
                    continue
                _obs_uid = _obs_u.entity_id
                # MOPP
                _obs_mopp_det = 1.0
                _obs_mopp_fat = 1.0
                _obs_mopp_lvl = 0
                if _cbrn_eng is not None:
                    try:
                        _s, _obs_mopp_det, _obs_mopp_fat = _cbrn_eng.get_mopp_effects(_obs_uid)
                        _obs_mopp_lvl = _cbrn_eng.get_mopp_level(_obs_uid)
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "cbrn.protection",
                            "get_mopp_effects",
                            exc,
                        ):
                            raise
                        pass
                _obs_mopp_fov = 1.0
                _obs_mopp_rl = 1.0
                if _obs_mopp_lvl > 0 and _enable_human_factors:
                    _fov_sc = _obs_mopp_lvl / 4.0
                    _obs_mopp_fov = 1.0 - _fov_sc * (1.0 - _obs_fov_full)
                    _obs_mopp_rl = 1.0 + _fov_sc * (_obs_rl_full - 1.0)
                # Altitude
                _obs_alt_f = 1.0
                if _enable_human_factors:
                    _obs_alt = getattr(_obs_u.position, "altitude", 0.0) or 0.0
                    if _obs_alt > _obs_alt_thresh:
                        _obs_alt_f = max(
                            0.5,
                            1.0 - _obs_alt_rate * (_obs_alt - _obs_alt_thresh) / 100.0,
                        )
                        if getattr(_obs_u, "acclimatized", False):
                            _obs_alt_f = 1.0 - (1.0 - _obs_alt_f) * 0.5
                # Readiness
                _obs_rdns = 1.0
                if _maint_eng is not None:
                    try:
                        _obs_rdns = _maint_eng.get_unit_readiness(_obs_uid)
                    except KeyError:
                        pass
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "logistics.maintenance",
                            "get_unit_readiness",
                            exc,
                        ):
                            raise
                _observer_mods[_obs_uid] = _ObserverModifiers(
                    mopp_detection=_obs_mopp_det,
                    mopp_fov_mod=_obs_mopp_fov,
                    mopp_fatigue=_obs_mopp_fat,
                    mopp_reload_mod=_obs_mopp_rl,
                    mopp_level=_obs_mopp_lvl,
                    altitude_factor=_obs_alt_f,
                    readiness=_obs_rdns,
                )

        attacker_cycles_processed = 0

        for side_name, side_units in units_by_side.items():
            side_enemies = active_enemies.get(side_name, [])
            side_pos_arr = enemy_pos_arrays.get(
                side_name,
                np.empty((0, 2)),
            )
            side_engagements = 0

            for attacker in side_units:
                enemies = side_enemies
                pos_arr = side_pos_arr
                if attacker.status != UnitStatus.ACTIVE:
                    continue

                # Phase 41a: force channeling — limit engagers per side
                if max_engagers > 0 and side_engagements >= max_engagers:
                    break
                attacker_cycles_processed += 1

                # Phase 50b: air posture gate — GROUNDED/RETURNING skip
                air_posture = getattr(attacker, "air_posture", None)
                if air_posture is not None and int(air_posture) in (0, 3):
                    continue

                # Phase 51b: naval posture gate — ANCHORED skip
                naval_posture = getattr(attacker, "naval_posture", None)
                if naval_posture is not None and int(naval_posture) == 0:
                    continue

                # Phase 40f: morale gate — routed/surrendered units don't fire
                attacker_morale = ctx.morale_states.get(attacker.entity_id)
                if attacker_morale is not None:
                    ms = (
                        MoraleState(int(attacker_morale))
                        if not isinstance(attacker_morale, MoraleState)
                        else attacker_morale
                    )
                    if ms in (MoraleState.ROUTED, MoraleState.SURRENDERED):
                        continue

                # Phase 66b: data link range gates UAV engagement
                if _enable_unconventional:
                    _dlr = getattr(attacker, "data_link_range", None)
                    if _dlr is not None and _dlr > 0:
                        # Phase 70b: O(1) parent lookup via _unit_index
                        _cmd_pos_dlr = None
                        _cmd_id_dlr = getattr(attacker, "parent_id", None)
                        if _cmd_id_dlr:
                            _parent_dlr = _unit_index.get(_cmd_id_dlr)
                            if _parent_dlr is not None:
                                _cmd_pos_dlr = getattr(_parent_dlr, "position", None)
                        if _cmd_pos_dlr is not None:
                            _dx_dlr = attacker.position.easting - _cmd_pos_dlr.easting
                            _dy_dlr = attacker.position.northing - _cmd_pos_dlr.northing
                            if math.sqrt(_dx_dlr * _dx_dlr + _dy_dlr * _dy_dlr) > _dlr:
                                logger.debug("UAV %s beyond data link range (%.0fm)", attacker.entity_id, _dlr)
                                continue  # skip engagement

                weapons = ctx.unit_weapons.get(attacker.entity_id, [])
                if not weapons:
                    continue
                targeting_decision = None
                routed_only_targeting = False
                if targeting_runtime is not None and battle is not None:
                    if not all(isinstance(attachment, WeaponAttachment) for attachment in weapons):
                        raise RuntimeError(
                            f"Production targeting requires typed weapon attachments for {attacker.entity_id!r}",
                        )
                    typed_weapons = tuple(weapons)
                    direct_attachments = tuple(
                        attachment
                        for attachment in typed_weapons
                        if weapon_role_uses_tactical_direct_engagement(
                            attachment.modeled_role,
                        )
                    )
                    routed_attachments = tuple(
                        attachment
                        for attachment in typed_weapons
                        if not weapon_role_uses_tactical_direct_engagement(
                            attachment.modeled_role,
                        )
                    )
                    staged_intents: list[_EngagementIntent] = []
                    staged_direct_revalidation: TargetingDisposition | None = None
                    staged_direct_decision: TacticalTargetingDecision | None = None
                    if (
                        direct_attachments
                        and targeting_member_ids is not None
                        and attacker.entity_id in targeting_member_ids
                    ):
                        staged_direct_decision = targeting_runtime.decision_for(
                            engine_tick=int(ctx.clock.tick_count),
                            battle_id=battle.battle_id,
                            shooter_id=attacker.entity_id,
                        )
                        if staged_direct_decision is None:
                            raise RuntimeError(
                                "Direct engagement is missing its published "
                                f"targeting decision for {attacker.entity_id!r}",
                            )
                        if staged_direct_decision.can_engage:
                            unit_lookup = _unit_index or {
                                unit.entity_id: unit for units in units_by_side.values() for unit in units
                            }
                            direct_target = (
                                unit_lookup.get(staged_direct_decision.target_id)
                                if staged_direct_decision.target_id in targeting_member_ids
                                else None
                            )
                            if direct_target is None:
                                staged_direct_revalidation = TargetingDisposition.TARGET_NOT_IN_BATTLE
                            else:
                                direct_distance_m = owner.targeting_distance(
                                    attacker,
                                    direct_target,
                                )
                                staged_direct_revalidation, _ = owner.revalidate_tactical_engagement(
                                    ctx,
                                    attacker,
                                    direct_target,
                                    staged_direct_decision,
                                    current_distance_m=direct_distance_m,
                                )
                                if staged_direct_revalidation is (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION):
                                    direct_intent = owner.stage_engagement_intent(
                                        runtime=ctx,
                                        attacker=attacker,
                                        target=direct_target,
                                        attachments=direct_attachments,
                                        enable_ammo_gate=_enable_ammo_gate,
                                        targeting_decision=(staged_direct_decision),
                                    )
                                    if direct_intent is not None:
                                        staged_intents.append(direct_intent)

                    routed_intent = owner.stage_routed_intent(
                        runtime=ctx,
                        attacker=attacker,
                        enemies=enemies,
                        attachments=routed_attachments,
                        visibility_m=visibility_m,
                        target_selection_mode=target_selection_mode,
                        enable_ammo_gate=_enable_ammo_gate,
                        air_routing_enabled=_enable_air_routing,
                    )
                    if routed_intent is not None:
                        staged_intents.append(routed_intent)
                    committed_intent = owner.arbitrate_engagement_intents(
                        staged_intents,
                        target_selection_mode=target_selection_mode,
                    )
                    if (
                        staged_direct_decision is not None
                        and staged_direct_revalidation is not None
                        and (committed_intent is None or committed_intent.targeting_decision is None)
                    ):
                        owner.publish_tactical_revalidation(
                            targeting_runtime,
                            staged_direct_decision,
                            staged_direct_revalidation,
                        )
                    if committed_intent is None:
                        continue

                    targeting_decision = committed_intent.targeting_decision
                    routed_only_targeting = targeting_decision is None
                    # The arbitration boundary commits exactly one attachment
                    # and target before downstream RNG, ammunition, or events.
                    # The established owner pipeline below receives only that
                    # immutable winner and therefore cannot double-act.
                    weapons = [committed_intent.attachment]
                    enemies = [committed_intent.target]
                    pos_arr = np.asarray(
                        [
                            [
                                committed_intent.target.position.easting,
                                committed_intent.target.position.northing,
                            ]
                        ],
                        dtype=np.float64,
                    )

                if pos_arr.shape[0] == 0:
                    if targeting_decision is not None:
                        target_exists = _unit_index is not None and targeting_decision.target_id in _unit_index
                        owner.publish_tactical_revalidation(
                            targeting_runtime,
                            targeting_decision,
                            (
                                TargetingDisposition.TARGET_INACTIVE
                                if target_exists
                                else TargetingDisposition.TARGET_NOT_IN_BATTLE
                            ),
                        )
                    continue

                # Target selection (vectorized distance computation)
                att_pos = np.array([attacker.position.easting, attacker.position.northing])
                diffs = pos_arr - att_pos
                dists = np.sqrt(np.sum(diffs * diffs, axis=1))

                # Phase 84c/109: spatially cull first, then apply semantic
                # availability and detection filters only to candidates that
                # at least one live weapon could reach.
                # The interval runtime filters to declared battle membership.
                # The side-wide STRtree was built before that filter, so its
                # indexes are not valid for the filtered enemy sequence.
                _eng_tree = None if targeting_member_ids is not None else _eng_trees.get(side_name)
                _max_wpn_range = max(
                    (weapon_instance.definition.max_range_m for weapon_instance, _ in weapons),
                    default=0.0,
                )
                if targeting_decision is not None:
                    _range_candidate_idxs = [
                        enemy_index
                        for enemy_index, enemy in enumerate(enemies)
                        if enemy.entity_id == targeting_decision.target_id
                    ]
                elif _max_wpn_range <= 0.0:
                    _range_candidate_idxs = list(range(len(enemies)))
                elif _eng_tree is not None:
                    _range_candidate_idxs = sorted(
                        _eng_tree.query(
                            Point(
                                attacker.position.easting,
                                attacker.position.northing,
                            ).buffer(_max_wpn_range),
                        )
                    )
                else:
                    _range_candidate_idxs = [
                        enemy_index
                        for enemy_index in range(len(enemies))
                        if float(dists[enemy_index]) <= _max_wpn_range
                    ]
                if not _range_candidate_idxs:
                    if targeting_decision is not None:
                        target_exists = _unit_index is not None and targeting_decision.target_id in _unit_index
                        owner.publish_tactical_revalidation(
                            targeting_runtime,
                            targeting_decision,
                            (
                                TargetingDisposition.TARGET_INACTIVE
                                if target_exists
                                else TargetingDisposition.TARGET_NOT_IN_BATTLE
                            ),
                        )
                    continue

                # Phase 109: mapping-owned weapon domains are a production
                # eligibility contract, not merely post-selection metadata.
                # Exclude targets no live attachment can ever engage before
                # closest/threat selection so an incompatible target cannot
                # starve a valid one.
                _domain_compatible_idxs: list[int] = []
                sensors = ctx.unit_sensors.get(attacker.entity_id, [])
                selected_sensing_attachment: SensorAttachment | None = None
                if targeting_decision is not None:
                    sensing_index = targeting_decision.sensing_sensor_source_equipment_index
                    sensing_id = targeting_decision.sensing_sensor_id
                    if sensing_index is None:
                        sensors = []
                    else:
                        exact_sensing = tuple(
                            attachment
                            for attachment in ctx.unit_sensor_attachments.get(
                                attacker.entity_id,
                                (),
                            )
                            if (
                                attachment.source_equipment_index == sensing_index
                                and attachment.sensor_id == sensing_id
                                and attachment.modeled_role is targeting_decision.sensing_sensor_modeled_role
                            )
                        )
                        if len(exact_sensing) == 1:
                            selected_sensing_attachment = exact_sensing[0]
                            sensors = [selected_sensing_attachment.sensor]
                        else:
                            sensors = []
                for enemy_index in _range_candidate_idxs:
                    enemy = enemies[enemy_index]
                    enemy_distance = float(dists[enemy_index])
                    if targeting_decision is not None:
                        _domain_compatible_idxs.append(enemy_index)
                        continue
                    usable_weapon = any(
                        (
                            _weapon_supports_domain(
                                weapon_instance.definition,
                                enemy.domain,
                            )
                            and (
                                weapon_instance.definition.max_range_m <= 0.0
                                or enemy_distance <= weapon_instance.definition.max_range_m
                            )
                            and any(weapon_instance.can_fire(ammo.ammo_id) for ammo in ammo_definitions)
                        )
                        for weapon_instance, ammo_definitions in weapons
                    )
                    if not usable_weapon:
                        continue
                    baseline_visible = enemy.domain is not Domain.SUBMARINE and enemy_distance <= visibility_m
                    sensor_detectable = any(
                        (
                            sensor.operational
                            and sensor.sensor_type is not SensorType.ESM
                            and sensor.supports_target_domain(enemy.domain)
                            and enemy_distance
                            <= (
                                float(sensor.effective_range)
                                * _MAX_POSITIVE_ACOUSTIC_LAYER_MULTIPLIER
                                if (
                                    _enable_acoustic
                                    and _ua_eng is not None
                                    and sensor.sensor_type
                                    in _SONAR_SENSOR_TYPES
                                )
                                else float(sensor.effective_range)
                            )
                        )
                        for sensor in sensors
                    )
                    if baseline_visible or sensor_detectable:
                        _domain_compatible_idxs.append(enemy_index)
                if not _domain_compatible_idxs:
                    continue

                # Phase 41c: threat-based or closest target selection
                if targeting_decision is not None:
                    best_idx = _domain_compatible_idxs[0]
                elif target_selection_mode in {"closest", "nearest"}:
                    best_idx = min(
                        _domain_compatible_idxs,
                        key=lambda enemy_index: (
                            float(dists[enemy_index]),
                            enemy_index,
                        ),
                    )
                else:
                    _cand_idxs = _domain_compatible_idxs
                    best_score = -1.0
                    best_idx = _cand_idxs[0]
                    for ei in _cand_idxs:
                        score = owner.score_target(
                            attacker,
                            enemies[ei],
                            float(dists[ei]),
                            weapons,
                            ctx,
                        )
                        if score > best_score:
                            best_score = score
                            best_idx = ei

                best_range = float(dists[best_idx])
                best_target = enemies[best_idx]
                live_targeting_range = (
                    owner.targeting_distance(attacker, best_target) if targeting_decision is not None else best_range
                )
                if targeting_decision is not None:
                    revalidation, _exact_weapon = owner.revalidate_tactical_engagement(
                        ctx,
                        attacker,
                        best_target,
                        targeting_decision,
                        current_distance_m=live_targeting_range,
                    )
                    owner.publish_tactical_revalidation(
                        targeting_runtime,
                        targeting_decision,
                        revalidation,
                    )
                    if revalidation is not (TargetingDisposition.VALID_ENGAGEMENT_SOLUTION):
                        continue

                # Phase 41a: terrain modifiers
                # Phase 59b: pass seasonal vegetation for concealment bonus
                _sv = 0.0
                if _seasons_eng is not None and _enable_seasonal:
                    _sv = _seasons_eng.current.vegetation_density
                terrain_cover, elevation_mod, concealment = owner.compute_terrain_modifiers(
                    ctx,
                    best_target.position,
                    attacker.position,
                    seasonal_vegetation=_sv,
                )

                # Detection check
                baseline_visual_range = 0.0 if best_target.domain is Domain.SUBMARINE else visibility_m
                eligible_sensors = [
                    sensor
                    for sensor in sensors
                    if (
                        sensor.operational
                        # ESM is meaningful only when DetectionEngine resolves
                        # an electromagnetic-emission signature. The
                        # non-FOW range gate has no such target state, so it
                        # must not turn a passive receiver into omniscient
                        # generic detection.
                        and sensor.sensor_type is not SensorType.ESM
                        and sensor.supports_target_domain(best_target.domain)
                    )
                ]
                best_sensor = None
                weather_independent = False

                # Phase 50c: continuous concealment — persistent per-target.
                # Phase 115 production targeting advances this mutable value
                # once in prepare_tactical_interval.  Legacy direct fixtures
                # retain their per-attacker update until they adopt the
                # runtime-owned interval boundary.
                tid = best_target.entity_id
                terrain_concealment = concealment
                if targeting_runtime is not None and battle is not None:
                    effective_concealment = owner.concealment_score(
                        tid,
                        terrain_concealment,
                    )
                else:
                    effective_concealment = owner.update_legacy_concealment(
                        tid,
                        terrain_concealment=terrain_concealment,
                        target_is_moving=best_target.speed > 0.5,
                        observation_decay=_observation_decay,
                    )

                # Resolve visual and sensor modalities independently. A
                # shorter thermal/NVG catalog envelope must be allowed to
                # beat night-degraded eyesight, but never beyond that
                # mapping-owned envelope.
                _opacity_visual = 0.0
                _opacity_thermal = 0.0
                _opacity_radar = 0.0
                if _obs_eng is not None and _enable_obscurants:
                    try:
                        _opacity = _obs_eng.opacity_at(best_target.position)
                        _opacity_visual = _opacity.visual
                        _opacity_thermal = _opacity.thermal
                        _opacity_radar = _opacity.radar
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "environment.obscurants",
                            "opacity_at",
                            exc,
                        ):
                            raise
                        pass

                _visual_concealment = max(
                    0.0,
                    1.0 - effective_concealment,
                )
                _nonvisual_concealment = max(
                    0.0,
                    1.0 - effective_concealment * 0.3,
                )
                detection_range = (
                    baseline_visual_range * _visual_concealment * night_visual_modifier * (1.0 - _opacity_visual)
                )
                _nvg_visual_modifier = night_visual_modifier
                if _enable_nvg and night_visual_modifier < 1.0 and tod_engine is not None:
                    try:
                        _nvg_eff = tod_engine.nvg_effectiveness(lat, lon)
                        _nvg_recovery = _nvg_eff * 0.5
                        _nvg_visual_modifier = night_visual_modifier + _nvg_recovery * (1.0 - night_visual_modifier)
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "environment.time_of_day",
                            "nvg_effectiveness",
                            exc,
                        ):
                            raise
                        pass

                for sensor in eligible_sensors:
                    sensor_type = sensor.sensor_type
                    sensor_range = float(sensor.effective_range)
                    if sensor_type is SensorType.VISUAL:
                        sensor_range = (
                            min(sensor_range, visibility_m)
                            * _visual_concealment
                            * night_visual_modifier
                            * (1.0 - _opacity_visual)
                        )
                    elif sensor_type is SensorType.NVG:
                        sensor_range = (
                            sensor_range * _visual_concealment * _nvg_visual_modifier * (1.0 - _opacity_visual)
                        )
                    elif sensor_type is SensorType.THERMAL:
                        if _enable_thermal_xo:
                            thermal_factor = thermal_dt_contrast
                            if thermal_factor < 0.5 and getattr(best_target, "speed", 0) > 1.0:
                                thermal_factor = max(thermal_factor, 0.5)
                        else:
                            thermal_factor = night_thermal_modifier
                        sensor_range *= _nonvisual_concealment * thermal_factor * (1.0 - _opacity_thermal)
                    elif sensor_type is SensorType.RADAR:
                        sensor_range *= _nonvisual_concealment * (1.0 - _opacity_radar)
                        # Phase 61c: radar horizon gate + EM ducting.
                        if _enable_em_prop and _conditions_eng is not None:
                            try:
                                _att_domain = getattr(attacker, "domain", None)
                                if _att_domain is Domain.AERIAL:
                                    _ant_h = max(
                                        10.0,
                                        attacker.position.altitude,
                                    )
                                elif _att_domain in (
                                    Domain.NAVAL,
                                    Domain.SUBMARINE,
                                ):
                                    _ant_h = 30.0
                                else:
                                    _ant_h = 10.0
                                _tgt_alt = best_target.position.altitude
                                _total_hz = _conditions_eng.radar_horizon(_ant_h) + _conditions_eng.radar_horizon(
                                    max(0.0, _tgt_alt),
                                )
                                if best_range > _total_hz and _tgt_alt < 500.0:
                                    sensor_range = 0.0
                                from stochastic_warfare.environment.electromagnetic import (
                                    FrequencyBand,
                                )

                                _prop = _conditions_eng.propagation(
                                    FrequencyBand.SHF,
                                    best_range / 1000.0,
                                )
                                if _prop.ducting_possible and _att_domain in (
                                    Domain.NAVAL,
                                    Domain.SUBMARINE,
                                ):
                                    sensor_range *= min(
                                        2.0,
                                        _conditions_eng.effective_earth_radius_factor() / (4.0 / 3.0),
                                    )
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "environment.electromagnetic",
                                    "resolve_radar_propagation",
                                    exc,
                                ):
                                    raise
                                pass
                        if precipitation_rate_mmhr > 0.0:
                            sensor_range = saturating_range_product(
                                sensor_range,
                                saturating_range_power(
                                    _compute_rain_detection_factor(
                                        precipitation_rate_mmhr,
                                        sensor_range / 1000.0,
                                    ),
                                    _rain_atten_factor,
                                ),
                            )
                        if _enable_air_combat_env and _conditions_facade is not None:
                            try:
                                _icing = _conditions_facade.air(
                                    attacker.position,
                                    float(attacker.position.altitude or 0.0),
                                    lat,
                                    lon,
                                ).icing_risk
                                if _icing > 0.5:
                                    _ice_db = cal_flat.get(
                                        "icing_radar_penalty_db",
                                        3.0,
                                    )
                                    sensor_range *= 10.0 ** (-_ice_db / 40.0)
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "environment.conditions",
                                    "read_air_icing",
                                    exc,
                                ):
                                    raise
                                pass
                    elif sensor_type in _SONAR_SENSOR_TYPES and _enable_acoustic and _ua_eng is not None:
                        try:
                            _ac = _ua_eng.conditions
                            _obs_depth = getattr(attacker, "depth", 0.0)
                            _tgt_depth = getattr(best_target, "depth", 0.0)
                            _layer_mod = 1.0
                            if (
                                _ac.thermocline_depth
                                and _tgt_depth > _ac.thermocline_depth
                                and _obs_depth <= _ac.thermocline_depth
                            ):
                                _layer_mod *= 0.1
                            if _ac.surface_duct_depth:
                                if _obs_depth < _ac.surface_duct_depth and _tgt_depth < _ac.surface_duct_depth:
                                    _layer_mod *= (
                                        _SURFACE_DUCT_POSITIVE_MULTIPLIER
                                    )
                                elif _obs_depth < _ac.surface_duct_depth and _tgt_depth > _ac.surface_duct_depth:
                                    _layer_mod *= 0.06
                            _cz_ranges = _ua_eng.convergence_zone_ranges(
                                _obs_depth,
                            )
                            _in_cz = any(abs(best_range - cz_range) < 5_000.0 for cz_range in _cz_ranges)
                            if _cz_ranges and best_range > 30_000.0 and not _in_cz:
                                _layer_mod *= 0.05
                            elif _in_cz:
                                _layer_mod *= (
                                    _CONVERGENCE_ZONE_POSITIVE_MULTIPLIER
                                )
                            sensor_range *= _layer_mod
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "environment.underwater_acoustics",
                                "resolve_sensor_conditions",
                                exc,
                            ):
                                raise
                            pass

                    if sensor_range > detection_range:
                        detection_range = sensor_range
                        best_sensor = sensor

                selected_sensor_type = getattr(
                    best_sensor,
                    "sensor_type",
                    None,
                )
                weather_independent = (
                    selected_sensor_type in _WEATHER_BYPASS_TYPES
                    or selected_sensor_type in _SONAR_SENSOR_TYPES
                )

                # Phase 86b: MOPP + altitude modifiers from pre-computed batch
                _obs = _observer_mods.get(attacker.entity_id, _DEFAULT_OBS_MODS)
                detection_range *= _obs.mopp_detection
                detection_range *= _obs.mopp_fov_mod
                detection_range *= _obs.altitude_factor
                _mopp_level_62 = _obs.mopp_level

                # Phase 55c-1: WW1 gas warfare MOPP — query gas mask protection
                _gas_protection = 0.0
                if _gas_eng is not None:
                    try:
                        _mopp, _gas_protection = _gas_eng.get_effective_mopp_level(
                            best_target.entity_id,
                            time_since_alert_s=ctx.clock.elapsed.total_seconds(),
                        )
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "cbrn.gas",
                            "get_effective_mopp_level",
                            exc,
                        ):
                            raise
                        pass

                # Phase 56e: naval posture modifies target detectability
                _tnp = getattr(best_target, "naval_posture", None)
                if _tnp is not None:
                    detection_range *= _NAVAL_POSTURE_DETECT_MULT.get(int(_tnp), 1.0)

                if targeting_decision is not None:
                    # Acquisition already has one immutable source.  Preserve
                    # its exact modality for downstream effectiveness instead
                    # of allowing the legacy visual/sensor competition above
                    # to reconstruct a different winning path after movement.
                    best_sensor = (
                        selected_sensing_attachment.sensor if selected_sensing_attachment is not None else None
                    )
                    selected_sensor_type = getattr(
                        best_sensor,
                        "sensor_type",
                        None,
                    )
                    weather_independent = (
                    selected_sensor_type in _WEATHER_BYPASS_TYPES
                    or selected_sensor_type in _SONAR_SENSOR_TYPES
                    )
                    detection_range = targeting_decision.sensing_range_m

                if targeting_decision is None and best_range > detection_range:
                    continue

                # Phase 41d: detection quality modulates engagement effectiveness
                detection_quality_mod = 1.0
                if _det_eng is not None and eligible_sensors:
                    best_snr = -100.0
                    for sensor in eligible_sensors:
                        if best_range > getattr(sensor, "effective_range", 0.0):
                            continue
                        if sensor.sensor_type not in {
                            SensorType.VISUAL,
                            SensorType.NVG,
                        }:
                            # This fast battle gate has no target signature
                            # from which to compute radar, thermal, acoustic,
                            # or electromagnetic SNR. Keep its neutral quality
                            # factor instead of applying the visual equation
                            # to an unrelated interface.
                            continue
                        try:
                            snr = _det_eng.compute_snr_visual(
                                sensor,
                                1.0,
                                best_range,
                                visibility_m=visibility_m,
                            )
                            if snr > best_snr:
                                best_snr = snr
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "detection.sensors",
                                "compute_visual_snr",
                                exc,
                            ):
                                raise
                            pass
                    if best_snr > -100.0:
                        # SNR excess → quality mod (linear scale)
                        snr_linear = 10.0 ** (best_snr / 20.0)
                        detection_quality_mod = min(1.0, max(0.3, snr_linear / 10.0))

                # Phase 44b: EW jamming degrades radar detection. Thermal and
                # acoustic modalities may also bypass visual weather, but
                # they do not expose a radar carrier for this interface.
                if _ew_eng is not None and selected_sensor_type is SensorType.RADAR:
                    try:
                        snr_penalty_db = _ew_eng.compute_radar_snr_penalty(
                            sensor_pos=attacker.position,
                            sensor_freq_ghz=getattr(
                                best_sensor,
                                "frequency_ghz",
                                10.0,
                            )
                            if best_sensor is not None
                            else 10.0,
                            sensor_power_dbm=getattr(
                                best_sensor,
                                "power_dbm",
                                70.0,
                            )
                            if best_sensor is not None
                            else 70.0,
                            sensor_gain_dbi=getattr(
                                best_sensor,
                                "antenna_gain_dbi",
                                30.0,
                            )
                            if best_sensor is not None
                            else 30.0,
                            sensor_bw_ghz=getattr(
                                best_sensor,
                                "bandwidth_ghz",
                                0.1,
                            )
                            if best_sensor is not None
                            else 0.1,
                            target_range_m=best_range,
                        )
                        if snr_penalty_db > 0:
                            # Phase 65c: ECCM reduces jamming effectiveness
                            if _eccm_eng is not None:
                                _eccm_suite = _eccm_eng.get_suite_for_unit(
                                    attacker.entity_id,
                                )
                                if _eccm_suite is not None and _eccm_suite.active:
                                    _eccm_reduction = _eccm_eng.compute_jam_reduction(
                                        _eccm_suite,
                                        jammer_freq_ghz=getattr(
                                            best_sensor,
                                            "frequency_ghz",
                                            10.0,
                                        )
                                        if best_sensor is not None
                                        else 10.0,
                                        jammer_bw_ghz=getattr(
                                            best_sensor,
                                            "bandwidth_ghz",
                                            0.1,
                                        )
                                        if best_sensor is not None
                                        else 0.1,
                                        js_ratio_db=snr_penalty_db,
                                    )
                                    snr_penalty_db = max(
                                        0.0,
                                        snr_penalty_db - _eccm_reduction,
                                    )
                            # Phase 48: jammer_coverage_mult scales EW effect
                            ew_factor = max(
                                0.1,
                                1.0 - (snr_penalty_db * _jammer_mult) / 40.0,
                            )
                            detection_quality_mod *= ew_factor
                    except Exception as exc:
                        if not owner.suppress_runtime_failure(
                            "electronic_warfare",
                            "compute_radar_snr_penalty",
                            exc,
                        ):
                            raise
                        pass

                # Phase 48: stealth_detection_penalty — reduce detection
                # quality for stealth-configured targets
                if _stealth_penalty > 0:
                    target_rcs = getattr(best_target, "radar_cross_section_m2", None)
                    if target_rcs is not None and target_rcs < 1.0:
                        detection_quality_mod *= max(0.1, 1.0 - _stealth_penalty)

                # Phase 48: sigint_detection_bonus — boost detection for
                # SIGINT-capable sensors
                if _sigint_bonus > 0 and eligible_sensors:
                    for sensor in eligible_sensors:
                        if getattr(sensor, "sensor_type", None) == SensorType.ESM:
                            detection_quality_mod = min(
                                1.0,
                                detection_quality_mod * (1.0 + _sigint_bonus),
                            )
                            break

                vis_mod = (
                    1.0 if weather_independent else (min(visibility_m / best_range, 1.0) if best_range > 0 else 1.0)
                )
                vis_mod = vis_mod * detection_quality_mod

                # Phase 60a: obscurant Pk reduction follows the modality that
                # actually supplied the winning detection envelope.
                if selected_sensor_type is SensorType.THERMAL:
                    vis_mod *= 1.0 - _opacity_thermal
                elif selected_sensor_type is SensorType.RADAR:
                    vis_mod *= 1.0 - _opacity_radar
                elif selected_sensor_type not in _SONAR_SENSOR_TYPES:
                    vis_mod *= 1.0 - _opacity_visual

                # Phase 42a: ROE gate
                if roe_engine is not None:
                    from stochastic_warfare.c2.roe import TargetCategory

                    id_confidence = detection_quality_mod
                    authorized, _reason = roe_engine.check_engagement_authorized(
                        shooter_id=attacker.entity_id,
                        target_id=best_target.entity_id,
                        target_category=TargetCategory.MILITARY_COMBATANT,
                        id_confidence=id_confidence,
                        target_position=best_target.position,
                    )
                    if not authorized:
                        continue

                # Phase 50c: concealment engagement threshold
                if effective_concealment > _eng_conceal_thresh:
                    continue

                # Select best weapon for current range — prefer ranged weapons
                # at distance, melee weapons at close range.  Skip weapons
                # that are out of ammo or out of range.
                selected_wpn = None
                selected_ammo_def = None
                selected_ammo_id = None
                selected_attachment: WeaponAttachment | None = None
                best_wpn_score = -1.0
                for attachment in weapons:
                    if targeting_decision is not None:
                        if not isinstance(attachment, WeaponAttachment):
                            raise RuntimeError(
                                f"Production targeting requires typed weapon attachments for {attacker.entity_id!r}",
                            )
                        if (
                            attachment.source_equipment_index != targeting_decision.weapon_source_equipment_index
                            or attachment.weapon.weapon_id != targeting_decision.weapon_id
                            or attachment.modeled_role is not targeting_decision.weapon_modeled_role
                        ):
                            continue
                    if (
                        isinstance(attachment, WeaponAttachment)
                        and ctx.indirect_fire_engine is not None
                        and ctx.indirect_fire_engine.is_attachment_reserved(
                            attacker.entity_id,
                            attachment.source_equipment_index,
                            attachment.weapon.weapon_id,
                        )
                    ):
                        continue
                    if isinstance(attachment, WeaponAttachment):
                        wpn_inst = attachment.weapon
                        ammo_defs = attachment.ammunition
                    else:
                        # Compatibility for older direct unit fixtures. The
                        # production context publishes WeaponAttachment only.
                        wpn_inst, ammo_defs = attachment
                    excluded_ammo_ids: set[str] = set()
                    if _enable_ammo_gate:
                        _mag_cap = getattr(
                            wpn_inst.definition,
                            "magazine_capacity",
                            0,
                        )
                        if _mag_cap > 0:
                            _legacy_ammo_key = f"{attacker.entity_id}:{wpn_inst.definition.weapon_id}"
                            for candidate in ammo_defs:
                                _ammo_key = f"{_legacy_ammo_key}:{candidate.ammo_id}"
                                _rounds_fired = owner.ammunition_expenditure(
                                    _ammo_key,
                                    fallback_key=_legacy_ammo_key,
                                )
                                if _rounds_fired >= _mag_cap:
                                    excluded_ammo_ids.add(
                                        candidate.ammo_id,
                                    )
                    if isinstance(attachment, WeaponAttachment):
                        if targeting_decision is not None:
                            ammo_def = next(
                                (
                                    candidate
                                    for candidate in attachment.ammunition
                                    if (
                                        candidate.ammo_id == targeting_decision.ammunition_id
                                        and candidate.ammo_id not in excluded_ammo_ids
                                        and attachment.weapon.can_fire(
                                            candidate.ammo_id,
                                        )
                                    )
                                ),
                                None,
                            )
                        else:
                            ammo_def = attachment.first_fireable_ammunition(
                                excluded_ammo_ids=excluded_ammo_ids,
                            )
                    else:
                        ammo_def = next(
                            (
                                candidate
                                for candidate in ammo_defs
                                if (
                                    candidate.ammo_id not in excluded_ammo_ids
                                    and wpn_inst.can_fire(
                                        candidate.ammo_id,
                                    )
                                )
                            ),
                            None,
                        )
                    if ammo_def is None:
                        continue
                    ammo_id = ammo_def.ammo_id
                    max_r = wpn_inst.definition.max_range_m
                    if max_r > 0 and best_range > max_r:
                        continue
                    # Phase 40d: domain filtering
                    if not _weapon_supports_domain(
                        wpn_inst.definition,
                        best_target.domain,
                    ):
                        continue
                    # Phase 40c: deployed weapons can't fire while moving
                    if attacker.speed > 0.5 and wpn_inst.definition.requires_deployed:
                        continue
                    _typed_indirect_owner = (
                        isinstance(attachment, WeaponAttachment) and attachment.modeled_role in _INDIRECT_FIRE_ROLES
                    )
                    # Phase 54f: weapon traverse arc constraint
                    # traverse_deg 0 or 360 = no constraint (platform-aimed)
                    # Phase 100 gap 4: aircraft can maneuver to face target;
                    # exempt AERIAL platforms from fixed-forward traverse like
                    # Phase 99 did for seeker FOV.  Also exempt dismounted
                    # infantry (they rotate bodily like Javelin/Stinger crews).
                    _traverse = getattr(wpn_inst.definition, "traverse_deg", 360.0)
                    if not _typed_indirect_owner and isinstance(_traverse, (int, float)) and 0 < _traverse < 360.0:
                        _att_domain_tv = getattr(attacker, "domain", None)
                        _att_ground_tv = getattr(attacker, "ground_type", None)
                        _traverse_exempt = (
                            _att_domain_tv == Domain.AERIAL or _att_ground_tv == GroundUnitType.LIGHT_INFANTRY
                        )
                        if not _traverse_exempt:
                            _att_heading = getattr(attacker, "heading", 0.0) or 0.0
                            _tgt_bearing = math.atan2(
                                best_target.position.easting - attacker.position.easting,
                                best_target.position.northing - attacker.position.northing,
                            )
                            _bearing_diff = abs(_tgt_bearing - _att_heading)
                            if _bearing_diff > math.pi:
                                _bearing_diff = 2 * math.pi - _bearing_diff
                            if _bearing_diff > math.radians(_traverse / 2):
                                continue  # target outside weapon traverse arc
                    # Phase 54f: weapon elevation constraint — only for
                    # weapons with explicitly set (non-default) elevation arcs
                    _elev_min = getattr(wpn_inst.definition, "elevation_min_deg", -5.0)
                    _elev_max = getattr(wpn_inst.definition, "elevation_max_deg", 85.0)
                    if (
                        not _typed_indirect_owner
                        and best_range > 0
                        # A missile launcher's rail/canister elevation defines
                        # its launch attitude, not a direct line-of-sight firing
                        # arc.  The guided flight path resolves downstream.
                        and wpn_inst.definition.parsed_category() != WeaponCategory.MISSILE_LAUNCHER
                        and isinstance(_elev_min, (int, float))
                        and isinstance(_elev_max, (int, float))
                        and (_elev_min != -5.0 or _elev_max != 85.0)
                    ):
                        _alt_diff = getattr(best_target.position, "altitude", 0.0) - getattr(
                            attacker.position, "altitude", 0.0
                        )
                        _elev_deg = math.degrees(math.atan2(_alt_diff, best_range))
                        if _elev_deg < _elev_min or _elev_deg > _elev_max:
                            continue  # target outside weapon elevation arc
                    # Phase 55c-2: seeker FOV constraint — guided munitions
                    # must acquire target within seeker cone.
                    # Phase 67: aircraft can turn to face targets before firing.
                    # Phase 99: dismounted infantry (shoulder/tripod-fired guided
                    # weapons — Javelin, Stinger, Kornet teams) can rotate to
                    # acquire; the constraint applies to fixed/turret-mounted
                    # launchers only.
                    _seeker_fov = getattr(ammo_def, "seeker_fov_deg", 0.0)
                    if not _typed_indirect_owner and isinstance(_seeker_fov, (int, float)) and _seeker_fov > 0:
                        _att_domain_sk = getattr(attacker, "domain", None)
                        _att_ground_sk = getattr(attacker, "ground_type", None)
                        _seeker_exempt = (
                            _att_domain_sk == Domain.AERIAL or _att_ground_sk == GroundUnitType.LIGHT_INFANTRY
                        )
                        if not _seeker_exempt:
                            _launch_bearing = math.atan2(
                                best_target.position.easting - attacker.position.easting,
                                best_target.position.northing - attacker.position.northing,
                            )
                            _att_heading_sk = getattr(attacker, "heading", 0.0) or 0.0
                            _seeker_diff = abs(_launch_bearing - _att_heading_sk)
                            if _seeker_diff > math.pi:
                                _seeker_diff = 2 * math.pi - _seeker_diff
                            if _seeker_diff > math.radians(_seeker_fov / 2):
                                continue  # target outside seeker acquisition cone
                    # Score: prefer weapon whose max range best fits current
                    # distance.  Ranged weapons score higher when target is
                    # far; melee weapons score higher when target is very
                    # close (ratio > 1 means "within comfortable range").
                    if max_r > 0:
                        ratio = max_r / max(best_range, 1.0)
                        # Ideal ratio is ~1.5 (target well within range)
                        score = min(ratio, 3.0)
                    else:
                        score = 0.1  # fallback for weapons with 0 range
                    if score > best_wpn_score:
                        best_wpn_score = score
                        selected_wpn = wpn_inst
                        selected_ammo_def = ammo_def
                        selected_ammo_id = ammo_id
                        selected_attachment = attachment if isinstance(attachment, WeaponAttachment) else None

                if selected_wpn is None:
                    continue

                # Phase 42a: hold-fire — defensive units wait for effective range
                side_rules = behavior_rules.get(side_name, {})
                if isinstance(side_rules, Mapping) and side_rules.get("hold_fire_until_effective_range", False):
                    best_eff_range = max(
                        (w[0].definition.get_effective_range() for w in weapons if w[0].definition.max_range_m > 0),
                        default=0.0,
                    )
                    if best_eff_range > 0 and best_range > best_eff_range:
                        continue  # Hold fire — target not yet in effective range

                wpn_inst = selected_wpn
                ammo_def = selected_ammo_def
                ammo_id = selected_ammo_id
                runtime_system_multiplier = (
                    selected_attachment.runtime_system_multiplier if selected_attachment is not None else 1
                )

                target_armor = getattr(best_target, "armor_front", 0.0)

                # Phase 40f: morale accuracy modifier
                morale_accuracy_mod = 1.0
                if attacker_morale is not None:
                    ms = (
                        MoraleState(int(attacker_morale))
                        if not isinstance(attacker_morale, MoraleState)
                        else attacker_morale
                    )
                    effects = _MORALE_EFFECTS.get(ms, {})
                    morale_accuracy_mod = effects.get("accuracy_mult", 1.0)

                # Phase 41b: per-unit training_level modulates crew skill
                base_skill = ctx.config.side_experience_levels.get(
                    side_name,
                    0.5,
                )
                unit_training = getattr(attacker, "training_level", 0.5)
                effective_skill = base_skill * (0.5 + 0.5 * unit_training)
                # Per-side hit probability modifier (Phase 48)
                side_hit_prob = cal_flat.get(
                    f"hit_probability_modifier_{side_name}",
                    hit_prob_mod,
                )
                # Phase 48: force_ratio_modifier — Dupuy CEV (Combat
                # Effectiveness Value).  Captures training, doctrine,
                # weapon superiority, and C2 quality as a single scalar.
                # Values >1 = more effective than raw numbers suggest.
                force_ratio_mod = cal_flat.get(
                    f"{side_name}_force_ratio_modifier",
                    1.0,
                )
                crew_skill = (
                    effective_skill * side_hit_prob * morale_accuracy_mod * weather_pk_modifier * force_ratio_mod
                )

                # Phase 52b: crosswind accuracy penalty
                if wind_e != 0.0 or wind_n != 0.0:
                    _wind_scale = _wind_accuracy_scale
                    crew_skill *= _compute_crosswind_penalty(
                        wind_e,
                        wind_n,
                        attacker.position.easting,
                        attacker.position.northing,
                        best_target.position.easting,
                        best_target.position.northing,
                        _wind_scale,
                    )

                # Phase 86b: MOPP + altitude + readiness from batched modifiers
                if _obs.mopp_fatigue > 1.0:
                    crew_skill /= _obs.mopp_fatigue
                if _obs.mopp_reload_mod > 1.0:
                    crew_skill /= _obs.mopp_reload_mod
                crew_skill *= _obs.altitude_factor
                if _obs.readiness < 0.3:
                    continue  # Too degraded to engage
                crew_skill *= max(0.5, _obs.readiness)

                # Phase 59d: equipment temperature stress → weapon jam
                if _enable_equip_stress:
                    _wx59d = ctx.weather_engine
                    if _wx59d is not None:
                        _temp59d = _wx59d.current.temperature
                        _wpn_equip = getattr(wpn_inst, "equipment", None)
                        if _wpn_equip is not None:
                            from stochastic_warfare.entities.equipment import EquipmentManager

                            _stress = EquipmentManager.environment_stress(
                                _wpn_equip,
                                _temp59d,
                            )
                            if _stress > 0:
                                if ctx.rng_manager is not None:
                                    _jam_stream = ctx.rng_manager.get_stream(
                                        ModuleId.COMBAT,
                                    )
                                    if _jam_stream.random() < min(0.5, _stress * 0.1):
                                        continue  # weapon jam from temperature stress

                # Phase 50e: compute weapon category early for fire-on-move exemption
                _early_wpn_cat = getattr(
                    wpn_inst.definition,
                    "category",
                    "",
                ).upper()

                # Phase 48a: fire-on-move accuracy penalty (non-deployed)
                # Phase 50e: exempt indirect fire categories (D7 fix)
                if (
                    attacker.speed > 0.5
                    and not wpn_inst.definition.requires_deployed
                    and _early_wpn_cat not in _INDIRECT_FIRE_CATEGORIES
                    and (selected_attachment is None or selected_attachment.modeled_role not in _INDIRECT_FIRE_ROLES)
                ):
                    _max_spd = getattr(attacker, "max_speed_mps", 20.0) or 20.0
                    _speed_frac = min(1.0, attacker.speed / max(1.0, _max_spd))
                    crew_skill *= 1.0 - _speed_frac * 0.5  # Up to 50% penalty

                # Phase 48: sam_suppression_modifier — SEAD degrades AD
                # unit effectiveness (SAM crews forced to shut down radar)
                if _sam_supp > 0:
                    _wpn_cat = getattr(wpn_inst.definition, "category", "").upper()
                    if _wpn_cat in ("SAM", "AAA", "MISSILE_LAUNCHER"):
                        att_type = getattr(attacker, "unit_type_id", "")
                        if any(k in att_type.lower() for k in ("sa-", "sam", "s-300", "buk", "patriot")):
                            crew_skill *= max(0.1, 1.0 - _sam_supp)

                # Per-side target_size_modifier: use target's side
                target_side = owner.find_unit_side(ctx, best_target.entity_id)
                target_size_mod = cal_flat.get(
                    f"target_size_modifier_{target_side}",
                    target_size_mod_default,
                )

                # Phase 44a: Sea state degrades naval target accuracy
                if best_target.domain in (Domain.NAVAL, Domain.SUBMARINE):
                    target_size_mod /= sea_dispersion_modifier

                # Phase 61a: wave period resonance + swell direction → gunnery
                if _enable_sea_state_ops:
                    if attacker.domain in (Domain.NAVAL, Domain.SUBMARINE) or best_target.domain in (
                        Domain.NAVAL,
                        Domain.SUBMARINE,
                    ):
                        # Wave period resonance: hull natural period ~8–12s
                        _hull_period = 10.0  # typical destroyer
                        _disp_a = getattr(attacker, "displacement_tons", 0)
                        if _disp_a and _disp_a > 10000:
                            _hull_period = 12.0  # larger ships
                        if _sea_wave_period > 0 and abs(_sea_wave_period - _hull_period) < 0.1 * _hull_period:
                            crew_skill *= max(0.3, 1.0 / 1.5)  # resonance penalty
                        # Swell direction: beam seas = max roll
                        _att_heading = 0.0
                        _dx_sw = best_target.position.easting - attacker.position.easting
                        _dy_sw = best_target.position.northing - attacker.position.northing
                        _dist_sw = math.sqrt(_dx_sw * _dx_sw + _dy_sw * _dy_sw)
                        if _dist_sw > 0:
                            _att_heading = math.atan2(_dx_sw, _dy_sw)
                        _roll_factor = math.sin(_sea_wave_dir - _att_heading) ** 2
                        crew_skill *= max(0.5, 1.0 - _roll_factor * 0.5)

                # Current time for fire rate limiting
                current_time_s = ctx.clock.elapsed.total_seconds()

                # Phase 44b: GPS accuracy affects guided weapon Pk
                gps_cep_factor = 1.0
                if _space_eng is not None:
                    gps_eng = getattr(_space_eng, "gps_engine", None)
                    if gps_eng is not None:
                        try:
                            guidance = getattr(
                                ammo_def,
                                "guidance_type",
                                "none",
                            )
                            if guidance in ("gps", "gps_ins"):
                                gps_state = gps_eng.compute_gps_accuracy(
                                    side_name,
                                    current_time_s,
                                )
                                gps_cep_factor = gps_eng.compute_cep_factor(
                                    gps_state.position_accuracy_m,
                                    guidance,
                                )
                        except Exception as exc:
                            if not owner.suppress_runtime_failure(
                                "space.gps",
                                "compute_guidance_cep_factor",
                                exc,
                            ):
                                raise
                            pass
                # Apply GPS degradation
                if gps_cep_factor > 1.0:
                    crew_skill /= gps_cep_factor

                # Phase 66a: human shield — reduce crew_skill when civilian
                # population near target (proxy for ROE constraint)
                _civ_density_66 = 0.0
                if _enable_unconventional and _uw_eng is not None:
                    if _pop_eng is not None:
                        _tgt_pos_66 = getattr(best_target, "position", None)
                        if _tgt_pos_66 is not None:
                            _civ_density_66 = getattr(
                                _pop_eng,
                                "get_density_at",
                                lambda p: 0.0,
                            )(_tgt_pos_66)
                    if _civ_density_66 > 0:
                        _shield_val = _uw_eng.evaluate_human_shield(
                            best_target.position,
                            _civ_density_66,
                        )
                        _pk_red = cal_flat.get("human_shield_pk_reduction", 0.5) * _shield_val
                        crew_skill *= max(0.1, 1.0 - _pk_red)

                # Record the live-state delta only after an engine actually
                # fires. Pre-routing intent is not ammunition expenditure.
                _ammo_before_routing = wpn_inst.ammo_state.available(ammo_id)

                # ── Phase 43: domain-specific engagement routing ──────
                routed_aggregate = False
                wpn_cat_str = getattr(
                    wpn_inst.definition,
                    "category",
                    "",
                ).upper()
                selected_modeled_role = selected_attachment.modeled_role if selected_attachment is not None else None
                dest_thresh = _dest_thresh
                dis_thresh = _dis_thresh

                # Phase 43c: naval domain routing (all eras, highest priority)
                if (
                    not routed_aggregate
                    and best_target.domain is not Domain.AERIAL
                    and (
                        selected_modeled_role in _NAVAL_SUBSURFACE_ROLES
                        or attacker.domain in (Domain.NAVAL, Domain.SUBMARINE)
                        or best_target.domain in (Domain.NAVAL, Domain.SUBMARINE)
                    )
                ):
                    handled, naval_status = owner.route_naval_engagement(
                        ctx,
                        attacker,
                        best_target,
                        wpn_inst,
                        best_range,
                        dt,
                        timestamp,
                        force_ratio_modifier=force_ratio_mod,
                        ammunition=ammo_def,
                        current_time_s=current_time_s,
                        runtime_system_multiplier=runtime_system_multiplier,
                        modeled_role=selected_modeled_role,
                    )
                    if handled:
                        if naval_status is not None:
                            pending_damage.append((best_target, naval_status, wpn_inst.definition.weapon_id))
                        if _routed_shot_fired(
                            wpn_inst,
                            ammo_id,
                            _ammo_before_routing,
                        ):
                            side_engagements += 1
                        routed_aggregate = True

                # Phase 58b: air domain routing (opt-in via enable_air_routing)
                if (
                    not routed_aggregate
                    and _enable_air_routing
                    and (
                        selected_modeled_role in _AIR_DELIVERY_ROLES
                        or attacker.domain == Domain.AERIAL
                        or best_target.domain == Domain.AERIAL
                    )
                ):
                    handled, air_status = _route_air_engagement(
                        ctx,
                        attacker,
                        best_target,
                        wpn_inst,
                        best_range,
                        dt,
                        timestamp,
                        force_ratio_mod=force_ratio_mod,
                        ammo_def=ammo_def,
                        current_time_s=current_time_s,
                        modeled_role=selected_modeled_role,
                        failure_handler=owner.suppress_runtime_failure,
                    )
                    if handled:
                        if air_status is not None:
                            pending_damage.append((best_target, air_status, wpn_inst.definition.weapon_id))
                        routed_shot_fired = _routed_shot_fired(
                            wpn_inst,
                            ammo_id,
                            _ammo_before_routing,
                        )
                        if routed_shot_fired:
                            side_engagements += 1
                        routed_aggregate = True
                        # Phase 69a: record sortie consumption
                        _ato_69a = ctx.ato_engine
                        if routed_shot_fired and attacker.domain is Domain.AERIAL and _ato_69a is not None:
                            _sim_time_69a = ctx.clock.elapsed.total_seconds()
                            _ato_69a.record_sortie(attacker.entity_id, _sim_time_69a)

                # Phase 43a: era-aware aggregate model routing
                # Phase 47: aggregate effectiveness modifier — terrain cover
                # reduces effective casualties, elevation advantage boosts them,
                # and crew_skill (morale × training × weather × CBRN × readiness)
                # scales aggregate lethality the same way it scales direct-fire Pk.
                _terrain_cas_mult = max(0.1, (1.0 - terrain_cover) * elevation_mod)
                _agg_skill = min(1.0, max(0.1, crew_skill))
                _agg_modifier = _terrain_cas_mult * _agg_skill

                if not routed_aggregate and selected_modeled_role not in _INDIRECT_FIRE_ROLES:
                    era = ctx.era_runtime_contract.era.value

                    if era == "napoleonic":
                        if wpn_cat_str in ("RIFLE", "CANNON", "ARTILLERY") and best_range > _MELEE_RANGE_M:
                            vf = ctx.volley_fire_engine
                            if vf is not None:
                                n_muskets = max(1, len(attacker.personnel))
                                formation_frac = _get_formation_firepower(
                                    ctx,
                                    attacker,
                                    failure_handler=owner.suppress_runtime_failure,
                                )
                                is_rifle = "rifle" in wpn_inst.definition.weapon_id.lower()
                                vr = vf.fire_volley(
                                    n_muskets=n_muskets,
                                    range_m=best_range,
                                    is_rifle=is_rifle,
                                    formation_firepower_fraction=formation_frac,
                                )
                                owner.apply_aggregate_casualties(
                                    int(vr.casualties * _agg_modifier),
                                    best_target,
                                    pending_damage,
                                    dest_thresh,
                                    dis_thresh,
                                    event_bus=ctx.event_bus,
                                    attacker=attacker,
                                    weapon=wpn_inst,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                # Suppression from volley fire
                                owner.apply_aggregate_suppression(
                                    ctx,
                                    best_target,
                                    wpn_inst,
                                    best_range,
                                    dt,
                                )
                        if not routed_aggregate and (wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M):
                            # Phase 54c: cavalry charge state machine
                            cavalry_eng = ctx.cavalry_engine
                            unit_type_lower = getattr(
                                attacker,
                                "unit_type",
                                "",
                            ).lower()
                            is_cavalry = any(
                                kw in unit_type_lower for kw in ("cavalry", "hussar", "dragoon", "lancer", "cuirassier")
                            )
                            if cavalry_eng is not None and is_cavalry:
                                charge_id = f"{attacker.entity_id}_vs_{best_target.entity_id}"
                                try:
                                    if not cavalry_eng.has_charge(charge_id):
                                        cavalry_eng.initiate_charge(
                                            charge_id,
                                            attacker.entity_id,
                                            best_target.entity_id,
                                            distance_m=best_range,
                                        )
                                    phase = cavalry_eng.update_charge(
                                        charge_id,
                                        dt,
                                    )
                                    logger.debug(
                                        "Cavalry charge %s phase: %s",
                                        charge_id,
                                        phase,
                                    )
                                    routed_aggregate = True
                                    side_engagements += 1
                                except Exception as exc:
                                    if not owner.suppress_runtime_failure(
                                        "combat.cavalry",
                                        "resolve_charge",
                                        exc,
                                    ):
                                        raise
                                    logger.debug(
                                        "Cavalry charge failed for %s",
                                        charge_id,
                                        exc_info=True,
                                    )

                            if not routed_aggregate:
                                me = ctx.melee_engine
                                if me is not None:
                                    mr = me.resolve_melee_round(
                                        attacker_strength=max(1, len(attacker.personnel)),
                                        defender_strength=max(1, len(best_target.personnel)),
                                        melee_type=_infer_melee_type(attacker, wpn_inst),
                                    )
                                    _apply_melee_result(
                                        mr,
                                        attacker,
                                        best_target,
                                        pending_damage,
                                        ctx.morale_runtime,
                                        dest_thresh,
                                        dis_thresh,
                                        event_bus=ctx.event_bus,
                                        wpn_inst=wpn_inst,
                                        timestamp=timestamp,
                                        current_time_s=current_time_s,
                                    )
                                    side_engagements += 1
                                    routed_aggregate = True

                    elif era == "ancient_medieval":
                        # Phase 54d: ancient formation modifiers
                        af_eng = ctx.formation_ancient_engine
                        if wpn_cat_str == "RIFLE" and best_range > _MELEE_RANGE_M:
                            ae = ctx.archery_engine
                            if ae is not None:
                                n_archers = max(1, len(attacker.personnel))
                                ar = ae.fire_volley(
                                    unit_id=attacker.entity_id,
                                    n_archers=n_archers,
                                    range_m=best_range,
                                    missile_type=_infer_missile_type(wpn_inst),
                                )
                                # Phase 54d: archery vulnerability from formation
                                arch_vuln = 1.0
                                if af_eng is not None:
                                    try:
                                        arch_vuln = af_eng.archery_vulnerability(
                                            best_target.entity_id,
                                        )
                                    except Exception as exc:
                                        if not owner.suppress_runtime_failure(
                                            "combat.ancient_formation",
                                            "archery_vulnerability",
                                            exc,
                                        ):
                                            raise
                                        pass
                                owner.apply_aggregate_casualties(
                                    int(ar.casualties * _agg_modifier * arch_vuln),
                                    best_target,
                                    pending_damage,
                                    dest_thresh,
                                    dis_thresh,
                                    event_bus=ctx.event_bus,
                                    attacker=attacker,
                                    weapon=wpn_inst,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                owner.apply_aggregate_suppression(
                                    ctx,
                                    best_target,
                                    wpn_inst,
                                    best_range,
                                    dt,
                                )
                        if not routed_aggregate and (wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M):
                            me = ctx.melee_engine
                            if me is not None:
                                # Phase 54d: formation melee/defense modifiers
                                melee_power_mod = 1.0
                                defense_mod_val = 1.0
                                if af_eng is not None:
                                    try:
                                        melee_power_mod = af_eng.melee_power(
                                            attacker.entity_id,
                                        )
                                    except Exception as exc:
                                        if not owner.suppress_runtime_failure(
                                            "combat.ancient_formation",
                                            "melee_power",
                                            exc,
                                        ):
                                            raise
                                        pass
                                    try:
                                        defense_mod_val = af_eng.defense_mod(
                                            best_target.entity_id,
                                        )
                                    except Exception as exc:
                                        if not owner.suppress_runtime_failure(
                                            "combat.ancient_formation",
                                            "defense_modifier",
                                            exc,
                                        ):
                                            raise
                                        pass
                                mr = me.resolve_melee_round(
                                    attacker_strength=int(max(1, len(attacker.personnel)) * melee_power_mod),
                                    defender_strength=int(max(1, len(best_target.personnel)) * defense_mod_val),
                                    melee_type=_infer_melee_type(attacker, wpn_inst),
                                )
                                _apply_melee_result(
                                    mr,
                                    attacker,
                                    best_target,
                                    pending_damage,
                                    ctx.morale_runtime,
                                    dest_thresh,
                                    dis_thresh,
                                    event_bus=ctx.event_bus,
                                    wpn_inst=wpn_inst,
                                    timestamp=timestamp,
                                    current_time_s=current_time_s,
                                )
                                side_engagements += 1
                                routed_aggregate = True

                    elif era == "ww1":
                        # Phase 55c-1: gas warfare protection modifier
                        # If ammo is gas-related, defender's gas mask reduces casualties
                        _gas_cas_mod = 1.0
                        _ammo_id_lower = (ammo_def.ammo_id if ammo_def else "").lower()
                        if _gas_protection > 0 and any(
                            kw in _ammo_id_lower for kw in ("gas", "chlorine", "phosgene", "mustard")
                        ):
                            _gas_floor = cal_flat.get("gas_casualty_floor", 0.1)
                            _gas_scale = cal_flat.get("gas_protection_scaling", 0.8)
                            _gas_cas_mod = max(_gas_floor, 1.0 - _gas_protection * _gas_scale)

                        # Phase 54b: barrage zone suppression on defender
                        barrage_eng = ctx.barrage_engine
                        if barrage_eng is not None and best_target is not None:
                            try:
                                bz = barrage_eng.get_barrage_zone_at(
                                    best_target.position.easting,
                                    best_target.position.northing,
                                )
                                if bz is not None:
                                    b_effects = barrage_eng.compute_effects(
                                        best_target.position.easting,
                                        best_target.position.northing,
                                        in_dugout=(
                                            getattr(best_target, "posture", None) is not None
                                            and int(getattr(best_target, "posture", 0)) >= 3
                                        ),
                                    )
                                    b_supp = b_effects.get("suppression_p", 0.0)
                                    if b_supp > 0:
                                        logger.debug(
                                            "Barrage suppression on %s: %.2f",
                                            best_target.entity_id,
                                            b_supp,
                                        )
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "combat.barrage",
                                    "compute_target_effects",
                                    exc,
                                ):
                                    raise
                                pass

                        if wpn_cat_str in ("RIFLE", "MACHINE_GUN", "LIGHT_MG", "CANNON"):
                            vf = ctx.volley_fire_engine
                            if vf is not None:
                                n_rifles = max(1, len(attacker.personnel))
                                vr = vf.fire_volley(
                                    n_muskets=n_rifles,
                                    range_m=best_range,
                                    is_rifle=True,
                                    formation_firepower_fraction=1.0,
                                )
                                owner.apply_aggregate_casualties(
                                    int(vr.casualties * _agg_modifier * _gas_cas_mod),
                                    best_target,
                                    pending_damage,
                                    dest_thresh,
                                    dis_thresh,
                                    event_bus=ctx.event_bus,
                                    attacker=attacker,
                                    weapon=wpn_inst,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                owner.apply_aggregate_suppression(
                                    ctx,
                                    best_target,
                                    wpn_inst,
                                    best_range,
                                    dt,
                                )
                        if not routed_aggregate and (wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M):
                            me = ctx.melee_engine
                            if me is not None:
                                mr = me.resolve_melee_round(
                                    attacker_strength=max(1, len(attacker.personnel)),
                                    defender_strength=max(1, len(best_target.personnel)),
                                    melee_type=_infer_melee_type(attacker, wpn_inst),
                                )
                                _apply_melee_result(
                                    mr,
                                    attacker,
                                    best_target,
                                    pending_damage,
                                    ctx.morale_runtime,
                                    dest_thresh,
                                    dis_thresh,
                                    event_bus=ctx.event_bus,
                                    wpn_inst=wpn_inst,
                                    timestamp=timestamp,
                                    current_time_s=current_time_s,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                    # era == "modern" or "ww2" → no aggregate routing

                # Phase 43b: indirect fire routing (all eras)
                if not routed_aggregate and (
                    selected_modeled_role in _INDIRECT_FIRE_ROLES
                    or (selected_modeled_role is None and wpn_cat_str in _INDIRECT_FIRE_CATEGORIES)
                ):
                    ife = ctx.indirect_fire_engine
                    if ife is not None:
                        min_range = getattr(wpn_inst.definition, "min_range_m", 0.0)
                        if best_range >= min_range:
                            from stochastic_warfare.combat.indirect_fire import (
                                FireMissionType,
                            )

                            round_count = max(
                                1,
                                int(wpn_inst.definition.rate_of_fire_rpm * dt / 60),
                            )
                            rounds_fired = _consume_routed_ammunition(
                                ctx,
                                attacker,
                                wpn_inst,
                                ammo_def,
                                quantity=round_count,
                                timestamp=timestamp,
                                current_time_s=current_time_s,
                                cooldown_multiplier=(runtime_system_multiplier),
                            )
                            if rounds_fired <= 0:
                                continue
                            if selected_modeled_role is (WeaponModeledRole.ROCKET_ARTILLERY):
                                fm_result = ife.rocket_salvo(
                                    launcher_id=attacker.entity_id,
                                    fire_pos=attacker.position,
                                    target_pos=best_target.position,
                                    weapon=wpn_inst.definition,
                                    ammo=ammo_def,
                                    rocket_count=rounds_fired,
                                    timestamp=timestamp,
                                )
                            else:
                                fm_result = ife.fire_mission(
                                    battery_id=attacker.entity_id,
                                    fire_pos=attacker.position,
                                    target_pos=best_target.position,
                                    weapon=wpn_inst.definition,
                                    ammo=ammo_def,
                                    mission_type=(FireMissionType.FIRE_FOR_EFFECT),
                                    round_count=rounds_fired,
                                    timestamp=timestamp,
                                )
                            if fm_result.impacts:
                                _ifire_radius = (
                                    getattr(
                                        ammo_def,
                                        "blast_radius_m",
                                        0.0,
                                    )
                                    or 50.0
                                )
                                owner.apply_indirect_fire_result(
                                    fm_result,
                                    best_target,
                                    pending_damage,
                                    dest_thresh,
                                    dis_thresh,
                                    _agg_modifier,
                                    lethal_radius_m=_ifire_radius,
                                    weapon_id=wpn_inst.definition.weapon_id,
                                )
                                # Phase 60a: artillery impact dust
                                if _obs_eng is not None and _enable_obscurants:
                                    try:
                                        _blast_r = getattr(ammo_def, "blast_radius_m", 20.0) or 20.0
                                        _obs_eng.add_dust(best_target.position, radius=_blast_r)
                                    except Exception as exc:
                                        if not owner.suppress_runtime_failure(
                                            "environment.obscurants",
                                            "add_impact_dust",
                                            exc,
                                        ):
                                            raise
                                        pass
                            side_engagements += 1
                            routed_aggregate = True
                            owner.apply_aggregate_suppression(
                                ctx,
                                best_target,
                                wpn_inst,
                                best_range,
                                dt,
                            )

                # ── Standard direct-fire path (modern, WW2, fallback) ─────
                if not routed_aggregate and routed_only_targeting:
                    continue
                if not routed_aggregate:
                    # Determine engagement type — DEW weapons route through
                    # Beer-Lambert / HPM models instead of ballistic physics
                    engagement_type = EngagementType.DIRECT_FIRE
                    try:
                        if wpn_inst.definition.parsed_category() == WeaponCategory.DIRECTED_ENERGY:
                            if wpn_inst.definition.beam_power_kw > 0:
                                engagement_type = EngagementType.DEW_LASER
                            else:
                                engagement_type = EngagementType.DEW_HPM
                    except (KeyError, ValueError):
                        pass

                    # Phase 63d: MISSILE type inference for guided missile launchers
                    if engagement_type == EngagementType.DIRECT_FIRE and _enable_missile_routing:
                        try:
                            if wpn_inst.definition.parsed_category() == WeaponCategory.MISSILE_LAUNCHER:
                                from stochastic_warfare.combat.ammunition import GuidanceType

                                _g = ammo_def.parsed_guidance()
                                if _g != GuidanceType.NONE:
                                    engagement_type = EngagementType.MISSILE
                        except (KeyError, ValueError, AttributeError):
                            pass

                    # Phase 54f: terminal maneuver hit probability bonus
                    if getattr(ammo_def, "terminal_maneuver", False) is True:
                        crew_skill *= 1.05

                    # Phase 40b: extract target posture
                    target_posture_val = getattr(best_target, "posture", None)
                    target_posture_str = target_posture_val.name if target_posture_val is not None else "MOVING"

                    # Phase 61c: extract humidity/precipitation for DEW
                    _dew_humidity = 0.5
                    _dew_precip = 0.0
                    if _enable_em_prop:
                        if _weather_eng is not None:
                            try:
                                _wc = _weather_eng.current
                                _dew_humidity = getattr(_wc, "humidity", 0.5)
                                _dew_precip = getattr(_wc, "precipitation_rate", 0.0)
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "environment.weather",
                                    "read_dew_conditions",
                                    exc,
                                ):
                                    raise
                                pass

                    result = ctx.engagement_engine.route_engagement(
                        engagement_type=engagement_type,
                        attacker_id=attacker.entity_id,
                        target_id=best_target.entity_id,
                        attacker_pos=attacker.position,
                        target_pos=best_target.position,
                        weapon=wpn_inst,
                        ammo_id=ammo_id,
                        ammo_def=ammo_def,
                        missile_engine=ctx.missile_engine,
                        dew_engine=ctx.dew_engine,
                        crew_skill=crew_skill,
                        target_size_m2=8.5 * target_size_mod,
                        target_armor_mm=target_armor,
                        shooter_speed_mps=attacker.speed,
                        target_posture=target_posture_str,
                        visibility=vis_mod,
                        timestamp=timestamp,
                        current_time_s=current_time_s,
                        terrain_cover=terrain_cover,
                        elevation_mod=elevation_mod,
                        humidity=_dew_humidity,
                        precipitation_rate=_dew_precip,
                    )

                    # Phase 40e: apply fire volume to target suppression
                    if result.engaged:
                        side_engagements += 1
                        if _sup_eng is not None:
                            tid = best_target.entity_id
                            _sup_eng.apply_fire_volume(
                                state=owner.suppression_state(tid),
                                rounds_per_minute=(wpn_inst.definition.rate_of_fire_rpm),
                                caliber_mm=wpn_inst.definition.caliber_mm,
                                range_m=best_range,
                                duration_s=dt,
                            )

                    if result.engaged and result.hit_result and result.hit_result.hit:
                        _df_wpn_id = wpn_inst.definition.weapon_id
                        if engagement_type in (EngagementType.DEW_LASER, EngagementType.DEW_HPM):
                            # Phase 51c: DEW disable path — threshold-based
                            dew_pk = result.hit_result.p_hit if hasattr(result.hit_result, "p_hit") else 0.5
                            dew_thresh = _dew_disable_thresh
                            if dew_pk >= dew_thresh:
                                pending_damage.append((best_target, UnitStatus.DESTROYED, _df_wpn_id))
                            else:
                                pending_damage.append((best_target, UnitStatus.DISABLED, _df_wpn_id))
                        elif result.damage_result and result.damage_result.damage_fraction > 0:
                            if result.damage_result.damage_fraction >= dest_thresh:
                                pending_damage.append((best_target, UnitStatus.DESTROYED, _df_wpn_id))
                            elif result.damage_result.damage_fraction >= dis_thresh:
                                pending_damage.append((best_target, UnitStatus.DISABLED, _df_wpn_id))

                            # Phase 58c: extract damage detail (logged;
                            # behavioral application deferred to calibration)
                            _dmg = result.damage_result
                            if _dmg.casualties:
                                logger.debug(
                                    "%d casualties on %s",
                                    len(_dmg.casualties),
                                    best_target.entity_id,
                                )
                            if _dmg.systems_damaged:
                                logger.debug(
                                    "%d systems_damaged on %s",
                                    len(_dmg.systems_damaged),
                                    best_target.entity_id,
                                )
                            # Phase 101: INCENDIARY_WEAPON ammo always starts a fire
                            # on hit (WP, thermobaric, napalm). Force fire_started
                            # so the existing fire-zone branch runs — honest WP
                            # "shake and bake" semantics.
                            try:
                                from stochastic_warfare.combat.ammunition import AmmoType as _AT

                                if ammo_def is not None and ammo_def.parsed_ammo_type() == _AT.INCENDIARY_WEAPON:
                                    object.__setattr__(_dmg, "fire_started", True)
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "combat.ammunition",
                                    "classify_incendiary_ammunition",
                                    exc,
                                ):
                                    raise
                                pass

                            if _dmg.fire_started:
                                logger.debug(
                                    "Fire started at %s from hit on %s",
                                    best_target.position,
                                    best_target.entity_id,
                                )
                                # Phase 60b: create fire zone on combustible terrain
                                if _enable_fire_zones:
                                    _classif = ctx.classification
                                    if _inc_eng is not None:
                                        try:
                                            _combustibility = 0.5
                                            if _classif is not None:
                                                _tp = _classif.properties_at(best_target.position)
                                                _combustibility = _tp.combustibility
                                            if _combustibility > 0.3:
                                                _ws, _wd = 0.0, 0.0
                                                if _weather_eng is not None:
                                                    _ws = _weather_eng.current.wind.speed
                                                    _wd = _weather_eng.current.wind.direction
                                                _inc_eng.create_fire_zone(
                                                    position=best_target.position,
                                                    radius_m=20.0 * _combustibility,
                                                    fuel_load=_combustibility,
                                                    wind_speed_mps=_ws,
                                                    wind_dir_rad=_wd,
                                                    duration_s=1800.0 * _combustibility,
                                                    timestamp=ctx.clock.elapsed.total_seconds(),
                                                )
                                                # Cross-engine: fire produces smoke
                                                if _obs_eng is not None:
                                                    _obs_eng.deploy_smoke(
                                                        best_target.position,
                                                        radius=_inc_eng.smoke_obscurant_radius_m,
                                                    )
                                        except Exception as exc:
                                            if not owner.suppress_runtime_failure(
                                                "combat.incendiary",
                                                "create_fire_zone",
                                                exc,
                                            ):
                                                raise
                                            logger.debug("Fire zone creation failed", exc_info=True)

                if _enable_ammo_gate:
                    _ammo_consumed = _ammo_before_routing - wpn_inst.ammo_state.available(ammo_id)
                    if _ammo_consumed > 0:
                        _legacy_ammo_key_trk = f"{attacker.entity_id}:{wpn_inst.definition.weapon_id}"
                        _ammo_key_trk = f"{_legacy_ammo_key_trk}:{ammo_id}"
                        owner.record_ammunition_expenditure(
                            _ammo_key_trk,
                            _ammo_consumed,
                            fallback_key=_legacy_ammo_key_trk,
                        )

        # Phase 66a/68g: guerrilla disengage + retreat movement
        if _enable_unconventional:
            if _uw_eng is not None:
                _retreat_dist = cal_flat.get("retreat_distance_m", 2000.0)
                for _guer_side, _su_guer in units_by_side.items():
                    _guer_enemies = active_enemies.get(_guer_side, [])
                    for _u_guer in _su_guer:
                        if _u_guer.status != UnitStatus.ACTIVE:
                            continue
                        _att_type_guer = getattr(_u_guer, "unit_type", "").lower()
                        if not any(kw in _att_type_guer for kw in ("insurgent", "militia", "guerrilla")):
                            continue
                        # Compute casualty fraction from cumulative tracking
                        _cas_key = _u_guer.entity_id
                        _total_pers = len(_u_guer.personnel) if _u_guer.personnel else 4
                        _cum = owner.cumulative_casualties(_cas_key)
                        _cas_frac = _cum / max(1, _total_pers + _cum)
                        # Apply the calibrated threshold to this decision only.
                        _guer_thresh = cal_flat.get("guerrilla_disengage_threshold", 0.3)
                        _in_pop = False
                        if _pop_eng is not None:
                            _gp = getattr(_u_guer, "position", None)
                            if _gp is not None:
                                _gd = getattr(_pop_eng, "get_density_at", lambda p: 0.0)(_gp)
                                _in_pop = _gd > 0
                        _disengage, _blend = _uw_eng.evaluate_guerrilla_disengage(
                            _u_guer.entity_id,
                            _cas_frac,
                            _in_pop,
                            disengage_threshold=_guer_thresh,
                        )
                        if _disengage:
                            if _blend > 0:
                                raise UnsupportedGuerrillaBlendError(
                                    "Populated-area guerrilla blending is "
                                    "unsupported until REM-032 provides a "
                                    "non-morale concealment owner",
                                )
                            logger.debug(
                                "Guerrilla %s disengaging (blend=%.2f)",
                                _u_guer.entity_id,
                                _blend,
                            )
                            # Phase 68g: move unit away from nearest enemy
                            _gp = getattr(_u_guer, "position", None)
                            if _gp is not None and _guer_enemies:
                                # Find nearest enemy direction
                                _ne_dist = float("inf")
                                _ne_dx, _ne_dy = 0.0, 0.0
                                for _ge in _guer_enemies:
                                    _gdx = _ge.position.easting - _gp.easting
                                    _gdy = _ge.position.northing - _gp.northing
                                    _gd2 = _gdx * _gdx + _gdy * _gdy
                                    if _gd2 < _ne_dist:
                                        _ne_dist = _gd2
                                        _ne_dx, _ne_dy = _gdx, _gdy
                                _ne_dist_m = math.sqrt(_ne_dist) if _ne_dist > 0 else 1.0
                                # Retreat vector: opposite of enemy direction
                                _rx = -_ne_dx / _ne_dist_m * _retreat_dist
                                _ry = -_ne_dy / _ne_dist_m * _retreat_dist
                                _new_pos = Position(
                                    _gp.easting + _rx,
                                    _gp.northing + _ry,
                                    _gp.altitude,
                                )
                                object.__setattr__(_u_guer, "position", _new_pos)
                                logger.debug(
                                    "Guerrilla %s retreated %.0fm to (%s)",
                                    _u_guer.entity_id,
                                    _retreat_dist,
                                    _new_pos,
                                )
        owner.stage_performance_delta(
            PerformanceReceiptDelta(
                lod=LODReceipt(
                    engagement=LODEngagementReceipt(
                        attacker_cycles_processed=(attacker_cycles_processed),
                    ),
                ),
            ),
        )
        return pending_damage
