"""Default deterministic OODA executor used by ``BattleManager``."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

from stochastic_warfare.c2.ai.ooda import OODAPhase
from stochastic_warfare.simulation.battle import (
    ModuleId,
    Position,
    PropagationResult,
    _get_unit_position,
    logger,
)
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleExecutorOwner,
    BattleIntervalView,
    BattleOODARuntime,
    OODACompletionRequest,
    OODAIntervalRequest,
)


class DefaultBattleOODAExecutor:
    """Preserve global completion and deferred-decision ordering exactly."""

    def execute_interval(
        self,
        owner: BattleExecutorOwner,
        request: OODAIntervalRequest,
    ) -> None:
        self._execute_ooda_interval(
            owner,
            request.runtime,
            request.battles,
            request.dt_seconds,
        )

    def process_completions(
        self,
        owner: BattleExecutorOwner,
        request: OODACompletionRequest,
    ) -> None:
        self._process_ooda_completions(
            owner,
            request.runtime,
            request.completions,
            request.timestamp,
            battle=request.battle,
            battle_tick=request.battle_tick,
        )

    def _execute_ooda_interval(
        self,
        executor_owner: BattleExecutorOwner,
        ctx: BattleOODARuntime,
        battles: Sequence[BattleIntervalView],
        dt: float,
    ) -> None:
        """Advance and route OODA completions once per engine interval.

        OODA state is global to the simulation context, while tactical effects
        belong to one battle.  This coordinator therefore advances the global
        timer once, validates unique active-roster ownership, and then routes
        each completion to its owning battle without changing completion order.
        """
        ooda_engine = ctx.ooda_engine
        if ooda_engine is None:
            return

        active_battles = tuple(
            sorted(
                (battle for battle in battles if battle.active),
                key=lambda battle: battle.battle_id,
            ),
        )
        battle_owners: dict[str, BattleIntervalView] = {}
        commander_ids = set(ooda_engine.commander_ids)
        for battle in active_battles:
            for unit_id in sorted(battle.unit_ids & commander_ids):
                prior = battle_owners.get(unit_id)
                if prior is not None:
                    raise RuntimeError(
                        "OODA commander has duplicate active battle ownership: "
                        f"unit={unit_id!r}, battles="
                        f"{[prior.battle_id, battle.battle_id]!r}",
                    )
                battle_owners[unit_id] = battle

        executor_owner.validate_deferred_ooda_state()
        for unit_id, battle_id in executor_owner.deferred_ooda_owner_items():
            battle_owner = battle_owners.get(unit_id)
            if battle_owner is None or battle_owner.battle_id != battle_id:
                raise RuntimeError(
                    "Deferred OODA decision has no matching active battle owner: "
                    f"unit={unit_id!r}, expected_battle={battle_id!r}",
                )

        timestamp = ctx.clock.current_time
        newly_completed = ooda_engine.update(dt, ts=timestamp)
        # Preserve the OODA engine's insertion order for new completions.  Only
        # deferred retries use canonical identity order.
        completions = list(newly_completed)
        seen = set(newly_completed)
        for completion in ooda_engine.expired_phases():
            if completion not in seen:
                completions.append(completion)
                seen.add(completion)

        for completion in completions:
            unit_id, _ = completion
            battle_owner = battle_owners.get(unit_id)
            if battle_owner is None:
                # A registered commander outside active tactical combat keeps
                # its expired phase until it acquires an active battle owner.
                continue
            deferred_owner = executor_owner.deferred_ooda_owner(unit_id)
            if (
                deferred_owner is not None
                and deferred_owner != battle_owner.battle_id
            ):
                raise RuntimeError(
                    "Deferred OODA decision ownership changed before maturity: "
                    f"unit={unit_id!r}, expected_battle={deferred_owner!r}, "
                    f"actual_battle={battle_owner.battle_id!r}",
                )
            self._process_ooda_completions(
                executor_owner,
                ctx,
                [completion],
                timestamp,
                battle=battle_owner,
                battle_tick=battle_owner.ticks_executed + 1,
            )

    def _process_ooda_completions(
        self,
        owner: BattleExecutorOwner,
        ctx: BattleOODARuntime,
        completions: Sequence[tuple[str, OODAPhase]],
        timestamp: datetime,
        *,
        battle: BattleIntervalView | None = None,
        battle_tick: int | None = None,
    ) -> None:
        """Handle OODA phase completions — trigger assessment/decision.

        After processing each completion, advances the OODA loop to the
        next phase with tactical acceleration applied.
        """
        cal_flat = ctx.cal_flat

        # Tactical acceleration multiplier (< 1 = faster decisions in battle)
        tactical_mult = 1.0
        if ctx.ooda_engine is not None:
            tactical_mult = ctx.ooda_engine.tactical_acceleration
        effective_battle_tick = (
            battle_tick
            if battle_tick is not None
            else (battle.ticks_executed if battle is not None else 0)
        )

        for unit_id, completed_phase in completions:
            # Look up doctrinal school for this unit
            school = None
            if ctx.school_registry is not None:
                school = ctx.school_registry.get_for_unit(unit_id)

            if completed_phase == OODAPhase.OBSERVE:
                # Run situation assessment with real data
                if ctx.assessor is not None:
                    side = owner.find_unit_side(ctx, unit_id)
                    if side:
                        friendly = len(ctx.active_units(side))
                        # Phase 53a: Use fog-of-war detected count if enabled
                        _fow_enabled = cal_flat.get("enable_fog_of_war", False)
                        if _fow_enabled and ctx.fog_of_war is not None:
                            try:
                                _wv = ctx.fog_of_war.get_world_view(side)
                                enemies = len(_wv.contacts)
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "detection.fog_of_war",
                                    "get_world_view",
                                    exc,
                                ):
                                    raise
                                enemies = sum(len(ctx.active_units(s)) for s in ctx.side_names() if s != side)
                        else:
                            enemies = sum(len(ctx.active_units(s)) for s in ctx.side_names() if s != side)

                        # Real morale from state tracking
                        morale_level = owner.get_unit_morale_level(ctx, unit_id)

                        # Real supply from stockpile manager
                        supply_level = owner.get_unit_supply_level(ctx, unit_id)

                        # Get school weight overrides
                        weight_overrides = None
                        if school is not None:
                            weight_overrides = school.get_assessment_weight_overrides() or None
                        # Phase 53b: C2 effectiveness from comms state
                        c2_eff = owner.compute_c2_effectiveness(ctx, unit_id, side)
                        # Phase 69c: inflate enemy_power by active decoy count
                        _enemy_power_69c = float(enemies)
                        _fow_69c_obs = ctx.fog_of_war
                        if _fow_69c_obs is not None:
                            _cal_69c = ctx.cal_flat
                            if _cal_69c.get("enable_fog_of_war", False):
                                try:
                                    _active_decoys = _fow_69c_obs.get_active_decoys()
                                    _enemy_power_69c += sum(1.0 for d in _active_decoys if d.effectiveness > 0)
                                except (AttributeError, TypeError) as exc:
                                    if not owner.suppress_runtime_failure(
                                        "detection.fog_of_war",
                                        "get_active_decoys",
                                        exc,
                                    ):
                                        raise
                                    pass

                        assessment = ctx.assessor.assess(
                            unit_id=unit_id,
                            echelon=5,
                            friendly_units=friendly,
                            friendly_power=float(friendly),
                            morale_level=morale_level,
                            supply_level=supply_level,
                            c2_effectiveness=c2_eff,
                            contacts=enemies,
                            enemy_power=_enemy_power_69c,
                            ts=timestamp,
                            weight_overrides=weight_overrides,
                        )
                        # Cache assessment for DECIDE phase
                        owner.cache_assessment(unit_id, assessment)
            elif completed_phase == OODAPhase.DECIDE:
                _cal_c2 = ctx.cal_flat
                _planning_64 = ctx.planning_engine
                _result_68c: PropagationResult | None = None
                _resuming_deferred = False
                _deferred_owner = owner.deferred_ooda_owner(unit_id)
                if (
                    _deferred_owner is not None
                    and (
                        battle is None
                        or _deferred_owner != battle.battle_id
                    )
                ):
                    raise RuntimeError(
                        "Deferred OODA completion reached the wrong battle: "
                        f"unit={unit_id!r}, owner={_deferred_owner!r}, "
                        f"actual={getattr(battle, 'battle_id', None)!r}",
                    )
                _deferred = owner.deferred_decision(unit_id)
                _resuming_planning = (
                    _deferred_owner is not None and _deferred is None
                )
                if _resuming_planning and _planning_64 is None:
                    raise RuntimeError(
                        "Planning-deferred OODA state requires the planning engine",
                    )
                if _deferred is not None:
                    logical_time_s = float(ctx.clock.elapsed.total_seconds())
                    if logical_time_s < _deferred.due_elapsed_s:
                        logger.debug(
                            "Order pending for %s (%.1fs remaining)",
                            unit_id,
                            _deferred.due_elapsed_s - logical_time_s,
                        )
                        # Waiting is intentionally free of C2 checks, planning
                        # reads, RNG draws, and any other decision side effect.
                        continue
                    matured = owner.pop_deferred_decision(unit_id)
                    if matured is None:
                        raise RuntimeError(
                            "Deferred decision disappeared during maturity",
                        )
                    _result_68c = matured.propagation
                    _resuming_deferred = True
                    logger.debug("Order delay matured for %s", unit_id)

                if not _resuming_deferred:
                    # Phase 63d: C2 friction — skip a new DECIDE completion
                    # when comms are too degraded.  A matured decision already
                    # passed this gate before it was queued.
                    if (
                        not _resuming_planning
                        and _cal_c2 is not None
                        and _cal_c2.get("enable_c2_friction", False)
                    ):
                        _c2_side = owner.find_unit_side(ctx, unit_id)
                        if _c2_side:
                            _c2_eff = owner.compute_c2_effectiveness(ctx, unit_id, _c2_side)
                            _c2_min = _cal_c2.get("c2_min_effectiveness", 0.3)
                            if _c2_eff < _c2_min:
                                logger.debug(
                                    "C2 friction: unit %s DECIDE skipped (eff=%.2f < min=%.2f)",
                                    unit_id,
                                    _c2_eff,
                                    _c2_min,
                                )
                                owner.advance_ooda_completion(
                                    ctx,
                                    unit_id=unit_id,
                                    school=school,
                                    tactical_mult=tactical_mult,
                                    timestamp=timestamp,
                                )
                                continue

                    # Phase 64b: Planning delay for a new completion only.
                    if (
                        _planning_64 is not None
                        and _cal_c2 is not None
                        and _cal_c2.get("enable_c2_friction", False)
                    ):
                        from stochastic_warfare.c2.planning.process import (
                            PlanningPhase as _PP64,
                        )

                        _plan_status = _planning_64.get_planning_status(unit_id)
                        if _plan_status not in (_PP64.IDLE, _PP64.COMPLETE):
                            if battle is None:
                                raise RuntimeError(
                                    "Planning-deferred OODA requires an active battle owner",
                                )
                            owner.bind_deferred_ooda_owner(
                                unit_id=unit_id,
                                battle=battle,
                            )
                            logger.debug(
                                "Planning delay: unit %s in phase %s, DECIDE deferred",
                                unit_id,
                                _plan_status.name,
                            )
                            continue
                        if _plan_status == _PP64.IDLE:
                            if _resuming_planning:
                                raise RuntimeError(
                                    "Planning-deferred OODA state lost its planning process",
                                )
                            if battle is None:
                                raise RuntimeError(
                                    "Planning-deferred OODA requires an active battle owner",
                                )
                            from stochastic_warfare.c2.orders.types import (
                                Order as _Ord64b,
                                OrderPriority as _OP64b,
                                OrderType as _OT64b,
                            )

                            _plan_order = _Ord64b(
                                order_id=f"plan_{unit_id}_{timestamp}",
                                issuer_id=unit_id,
                                recipient_id=unit_id,
                                timestamp=timestamp,
                                order_type=_OT64b.FRAGO,
                                echelon_level=5,
                                priority=_OP64b.PRIORITY,
                                mission_type=0,
                            )
                            _plan_max = _cal_c2.get(
                                "planning_available_time_s",
                                7200.0,
                            )
                            _c2_plan_side2 = owner.find_unit_side(ctx, unit_id)
                            _c2_plan_eff2 = (
                                owner.compute_c2_effectiveness(
                                    ctx,
                                    unit_id,
                                    _c2_plan_side2,
                                )
                                if _c2_plan_side2
                                else 1.0
                            )
                            _avail_time = max(
                                60.0,
                                _plan_max * (1.0 - _c2_plan_eff2),
                            )
                            try:
                                _method = _planning_64.initiate_planning(
                                    unit_id,
                                    _plan_order,
                                    _avail_time,
                                    timestamp,
                                )
                            except Exception:
                                logger.exception(
                                    "Planning initiation failed for %s",
                                    unit_id,
                                )
                                raise
                            logger.debug(
                                "Initiated %s planning for %s",
                                _method.name,
                                unit_id,
                            )
                            owner.bind_deferred_ooda_owner(
                                unit_id=unit_id,
                                battle=battle,
                            )
                            continue

                    if ctx.decision_engine is not None:
                        _result_68c = owner.propagate_ooda_decision(
                            ctx,
                            unit_id=unit_id,
                            timestamp=timestamp,
                        )
                        if _result_68c is not None and not _result_68c.success:
                            logger.debug("Order propagation failed for %s", unit_id)
                            owner.advance_ooda_completion(
                                ctx,
                                unit_id=unit_id,
                                school=school,
                                tactical_mult=tactical_mult,
                                timestamp=timestamp,
                            )
                            continue
                        if _result_68c is not None and _result_68c.total_delay_s > 0.0:
                            if battle is None:
                                raise RuntimeError(
                                    "A deferred OODA decision requires an active battle owner",
                                )
                            queued = owner.queue_deferred_decision(
                                unit_id=unit_id,
                                battle=battle,
                                logical_time_s=float(
                                    ctx.clock.elapsed.total_seconds(),
                                ),
                                propagation=_result_68c,
                            )
                            logger.debug(
                                "Order delayed for %s until global time %.1fs",
                                unit_id,
                                queued.due_elapsed_s,
                            )
                            continue

                if _resuming_deferred and ctx.decision_engine is None:
                    raise RuntimeError(
                        "A matured OODA decision requires the decision engine",
                    )

                # Run decision engine with real assessment + personality
                if ctx.decision_engine is not None:
                    # Retrieve cached assessment from OBSERVE phase
                    assessment = owner.cached_assessment(unit_id)

                    # Get commander personality
                    personality = None
                    if ctx.commander_engine is not None:
                        personality = ctx.commander_engine.get_personality(unit_id)

                    # Build assessment summary from real data
                    assessment_summary = owner.build_assessment_summary(
                        ctx,
                        unit_id,
                        assessment,
                    )

                    # Get school decision adjustments
                    school_adjustments = None
                    if school is not None:
                        school_adjustments = school.get_decision_score_adjustments(
                            echelon=5,
                            assessment_summary=assessment_summary,
                        )
                        # Apply opponent modeling if enabled
                        if school.definition.opponent_modeling_enabled:
                            side = owner.find_unit_side(ctx, unit_id)
                            enemies = (
                                sum(len(ctx.active_units(s)) for s in ctx.side_names() if s != side) if side else 1
                            )
                            friendly = len(ctx.active_units(side)) if side else 1
                            opponent_prediction = school.predict_opponent_action(
                                own_assessment=assessment_summary,
                                opponent_power=float(enemies),
                                opponent_morale=assessment_summary.get("morale_level", 0.7),
                                own_power=float(friendly),
                            )
                            if opponent_prediction:
                                temp_scores = dict(school_adjustments)
                                adjusted = school.adjust_scores_for_opponent(
                                    temp_scores,
                                    opponent_prediction,
                                )
                                school_adjustments = adjusted

                    # Phase 69b: planning result injection — bias school_adjustments
                    if _planning_64 is not None and _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False):
                        _plan_result_69b = _planning_64.consume_result(unit_id)
                        if _plan_result_69b is not None and school_adjustments is not None:
                            _planning_bonus = 0.10
                            school_adjustments[_plan_result_69b] = (
                                school_adjustments.get(_plan_result_69b, 0.0) + _planning_bonus
                            )
                            logger.debug(
                                "Planning result '%s' injected for %s (+%.2f)",
                                _plan_result_69b,
                                unit_id,
                                _planning_bonus,
                            )

                    # Phase 68f: expire old stratagems before evaluating new ones
                    if ctx.stratagem_engine is not None and battle is not None:
                        _strat_dur = _cal_c2.get("stratagem_duration_ticks", 100) if _cal_c2 is not None else 100
                        _expired = ctx.stratagem_engine.expire_stratagems(
                            effective_battle_tick,
                            _strat_dur,
                        )
                        for _exp_id in _expired:
                            logger.debug(
                                "Stratagem %s expired at tick %d",
                                _exp_id,
                                effective_battle_tick,
                            )

                    # Phase 53c/64d: Evaluate + activate stratagem opportunities
                    # (before decide() so bonuses flow into school_adjustments)
                    if ctx.stratagem_engine is not None and assessment is not None:
                        side = owner.find_unit_side(ctx, unit_id)
                        if side:
                            unit_ids = [u.entity_id for u in ctx.active_units(side)]
                            experience = getattr(personality, "experience", 0.5) if personality else 0.5
                            affinity: dict[str, float] = {}
                            if school is not None:
                                affinity = school.get_stratagem_affinity()
                            _strat_activate = _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False)
                            conc_viable = False
                            dec_viable = False
                            try:
                                conc_viable, _ = ctx.stratagem_engine.evaluate_concentration_opportunity(
                                    assessment,
                                    unit_ids,
                                    echelon=5,
                                    experience=experience,
                                )
                                if conc_viable:
                                    logger.debug(
                                        "Concentration opportunity for %s (affinity=%.2f)",
                                        unit_id,
                                        affinity.get("CONCENTRATION", 0.5),
                                    )
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "c2.stratagem",
                                    "evaluate_concentration_opportunity",
                                    exc,
                                ):
                                    raise
                                pass
                            try:
                                dec_viable, _ = ctx.stratagem_engine.evaluate_deception_opportunity(
                                    assessment,
                                    unit_ids,
                                    echelon=5,
                                    experience=experience,
                                )
                                if dec_viable:
                                    logger.debug(
                                        "Deception opportunity for %s (affinity=%.2f)",
                                        unit_id,
                                        affinity.get("DECEPTION", 0.5),
                                    )
                            except Exception as exc:
                                if not owner.suppress_runtime_failure(
                                    "c2.stratagem",
                                    "evaluate_deception_opportunity",
                                    exc,
                                ):
                                    raise
                                pass

                            # Phase 64d: Activate stratagems when c2_friction enabled
                            if _strat_activate:
                                if conc_viable:
                                    _enemy_sides = [s for s in ctx.side_names() if s != side]
                                    _enemy_units_64 = []
                                    for _es in _enemy_sides:
                                        _enemy_units_64.extend(ctx.active_units(_es))
                                    if _enemy_units_64:
                                        _avg_e = sum(
                                            (getattr(e, "position", None) or Position(0, 0, 0)).easting
                                            for e in _enemy_units_64
                                        ) / len(_enemy_units_64)
                                        _avg_n = sum(
                                            (getattr(e, "position", None) or Position(0, 0, 0)).northing
                                            for e in _enemy_units_64
                                        ) / len(_enemy_units_64)
                                        _conc_point = Position(_avg_e, _avg_n, 0.0)
                                        _economy = unit_ids[-2:] if len(unit_ids) > 4 else []
                                        _conc_units = [u for u in unit_ids if u not in _economy]
                                        try:
                                            _plan = ctx.stratagem_engine.plan_concentration(
                                                _conc_units, _conc_point, _economy
                                            )
                                            ctx.stratagem_engine.activate_stratagem(
                                                unit_id,
                                                _plan,
                                                timestamp,
                                                tick=effective_battle_tick,
                                            )
                                            if school_adjustments is not None:
                                                _bonus = _cal_c2.get("stratagem_concentration_bonus", 0.08)
                                                school_adjustments["ATTACK"] = (
                                                    school_adjustments.get("ATTACK", 0.0) + _bonus
                                                )
                                        except Exception as exc:
                                            if not owner.suppress_runtime_failure(
                                                "c2.stratagem",
                                                "activate_concentration",
                                                exc,
                                            ):
                                                raise
                                            logger.debug(
                                                "Concentration activation failed for %s", unit_id, exc_info=True
                                            )
                                if dec_viable:
                                    _feint = unit_ids[:1]
                                    _main = unit_ids[1:]
                                    try:
                                        _plan = ctx.stratagem_engine.plan_deception(_feint, "enemy_front", _main)
                                        ctx.stratagem_engine.activate_stratagem(
                                            unit_id,
                                            _plan,
                                            timestamp,
                                            tick=effective_battle_tick,
                                        )
                                        if school_adjustments is not None:
                                            _bonus = _cal_c2.get("stratagem_deception_bonus", 0.10)
                                            school_adjustments["ATTACK"] = (
                                                school_adjustments.get("ATTACK", 0.0) + _bonus
                                            )
                                        # Phase 69c: deploy phantom decoys via FOW
                                        _fow_69c = ctx.fog_of_war
                                        if (
                                            _fow_69c is not None
                                            and _cal_c2 is not None
                                            and _cal_c2.get("enable_fog_of_war", False)
                                        ):
                                            _phantom_count = _cal_c2.get("deception_phantom_count", 3)
                                            _feint_pos_list = []
                                            for _fid in _feint:
                                                _fp = _get_unit_position(ctx, _fid)
                                                if _fp is not None:
                                                    _feint_pos_list.append(_fp)
                                            if _feint_pos_list:
                                                _dec_stream = (
                                                    ctx.rng_manager.get_stream(ModuleId.C2)
                                                    if ctx.rng_manager is not None
                                                    else None
                                                )
                                                for _pi in range(_phantom_count):
                                                    _base = _feint_pos_list[_pi % len(_feint_pos_list)]
                                                    _dist = 500.0 + 1000.0 * (
                                                        _dec_stream.random() if _dec_stream else 0.5
                                                    )
                                                    _ang = (
                                                        2
                                                        * math.pi
                                                        * (_dec_stream.random() if _dec_stream else 0.25 * _pi)
                                                    )
                                                    _dec_pos = Position(
                                                        _base.easting + math.cos(_ang) * _dist,
                                                        _base.northing + math.sin(_ang) * _dist,
                                                        _base.altitude,
                                                    )
                                                    _fow_69c.deploy_decoy(_dec_pos)
                                                logger.debug(
                                                    "Deception: %d phantoms deployed for %s", _phantom_count, unit_id
                                                )
                                    except Exception as exc:
                                        if not owner.suppress_runtime_failure(
                                            "c2.stratagem",
                                            "activate_deception",
                                            exc,
                                        ):
                                            raise
                                        logger.debug("Deception activation failed for %s", unit_id, exc_info=True)

                    # Phase 68d: apply misinterpretation effects before decide
                    # A matured record supplies its exact one-shot effect.  A
                    # zero-delay propagation can supply the effect directly.
                    _misinterp = (
                        _result_68c
                        if _result_68c is not None
                        and _result_68c.was_misinterpreted
                        else None
                    )
                    if _misinterp is not None and hasattr(_misinterp, "misinterpretation_type"):
                        _mistype = _misinterp.misinterpretation_type
                        if _mistype == "timing":
                            # The queue encoded this one-time extension when
                            # propagation first completed.
                            logger.debug(
                                "Timing misinterpretation matured for %s",
                                unit_id,
                            )
                        elif _mistype == "unit_designation":
                            # Wrong unit addressed — skip this decide cycle
                            logger.debug("Unit designation misinterpretation: %s skipped", unit_id)
                            owner.advance_ooda_completion(
                                ctx,
                                unit_id=unit_id,
                                school=school,
                                tactical_mult=tactical_mult,
                                timestamp=timestamp,
                            )
                            continue
                        elif _mistype == "objective" and school_adjustments is not None:
                            # Swap ATTACK ↔ DEFEND
                            _atk = school_adjustments.get("ATTACK", 0.0)
                            _def = school_adjustments.get("DEFEND", 0.0)
                            school_adjustments["ATTACK"] = _def
                            school_adjustments["DEFEND"] = _atk
                            logger.debug("Objective misinterpretation: %s ATTACK/DEFEND swapped", unit_id)
                        elif _mistype == "position":
                            # Offset movement target (handled post-decide via position perturbation)
                            _misinterp_radius = (_cal_c2 or {}).get("misinterpretation_radius_m", 500.0)
                            if ctx.rng_manager is not None:
                                _mis_stream = ctx.rng_manager.get_stream(ModuleId.C2)
                                _angle = _mis_stream.random() * 2 * math.pi
                                _offset_e = math.cos(_angle) * _misinterp_radius
                                _offset_n = math.sin(_angle) * _misinterp_radius
                                _upos = _get_unit_position(ctx, unit_id)
                                if _upos is not None:
                                    _new_pos = Position(
                                        _upos.easting + _offset_e,
                                        _upos.northing + _offset_n,
                                        _upos.altitude,
                                    )
                                    # Find unit and offset its position
                                    for _side_units_68d in ctx.units_by_side.values():
                                        for _u_68d in _side_units_68d:
                                            if _u_68d.entity_id == unit_id:
                                                object.__setattr__(_u_68d, "position", _new_pos)
                                                break
                                    logger.debug(
                                        "Position misinterpretation: %s offset by %.0fm", unit_id, _misinterp_radius
                                    )

                    ctx.decision_engine.decide(
                        unit_id=unit_id,
                        echelon=5,
                        assessment=assessment,
                        personality=personality,
                        doctrine=None,
                        ts=timestamp,
                        school_adjustments=school_adjustments,
                    )

            owner.advance_ooda_completion(
                ctx,
                unit_id=unit_id,
                school=school,
                tactical_mult=tactical_mult,
                timestamp=timestamp,
            )
