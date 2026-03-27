#!/usr/bin/env python
"""Overnight scenario evaluation — runs every scenario and reports diagnostics.

Captures: movement, engagements, casualties, resolution switches, weapon fires,
final positions, and potential bugs (no movement, stalled units, zero engagements).

Usage:
    uv run python scripts/evaluate_scenarios.py
    uv run python scripts/evaluate_scenarios.py --scenario bekaa_valley_1982
    uv run python scripts/evaluate_scenarios.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class UnitDiagnostics:
    entity_id: str
    side: str
    unit_type: str
    status: str
    start_pos: tuple[float, float]
    end_pos: tuple[float, float]
    distance_moved: float
    weapons_count: int
    best_weapon_range: float


@dataclass
class ScenarioResult:
    scenario_name: str
    scenario_path: str
    success: bool = True
    error: str = ""
    duration_wall_s: float = 0.0

    # Simulation outcome
    ticks_executed: int = 0
    sim_duration_s: float = 0.0
    victory_side: str = ""
    victory_condition: str = ""
    victory_message: str = ""

    # Force counts
    sides: dict[str, int] = field(default_factory=dict)
    initial_total: int = 0
    final_active: dict[str, int] = field(default_factory=dict)
    final_destroyed: dict[str, int] = field(default_factory=dict)
    total_casualties: int = 0

    # Movement diagnostics
    units_that_moved: int = 0
    units_that_didnt_move: int = 0
    avg_distance_moved: float = 0.0
    max_distance_moved: float = 0.0
    min_distance_moved_active: float = 0.0  # among active units

    # Engagement diagnostics
    total_events: int = 0
    engagement_events: int = 0
    damage_events: int = 0
    destruction_events: int = 0
    morale_events: int = 0
    weapon_fire_events: int = 0

    # Resolution tracking
    started_tactical: bool = False
    reached_tactical: bool = False

    # Position clustering (detect centroid collapse)
    final_position_spread: dict[str, float] = field(default_factory=dict)

    # Flags / potential issues
    issues: list[str] = field(default_factory=list)

    # Per-unit detail (optional)
    unit_details: list[dict] = field(default_factory=list)


def run_scenario(scenario_path: Path, data_dir: Path, verbose: bool = False, seed: int = 42) -> ScenarioResult:
    """Run a single scenario and collect diagnostics."""
    from stochastic_warfare.simulation.scenario import ScenarioLoader
    from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
    from stochastic_warfare.simulation.recorder import SimulationRecorder
    from stochastic_warfare.simulation.victory import VictoryEvaluator
    from stochastic_warfare.entities.base import UnitStatus

    result = ScenarioResult(
        scenario_name=scenario_path.parent.name,
        scenario_path=str(scenario_path),
    )

    start_time = time.time()

    try:
        # Load scenario
        loader = ScenarioLoader(data_dir)
        ctx = loader.load(scenario_path, seed=seed)

        # Record initial positions
        initial_positions: dict[str, tuple[float, float]] = {}
        initial_counts: dict[str, int] = {}
        for side, units in ctx.units_by_side.items():
            initial_counts[side] = len(units)
            for u in units:
                initial_positions[u.entity_id] = (
                    u.position.easting, u.position.northing
                )
        result.sides = initial_counts
        result.initial_total = sum(initial_counts.values())

        # Record weapon info per unit
        unit_weapons_info: dict[str, tuple[int, float]] = {}
        for eid, wpn_list in ctx.unit_weapons.items():
            count = len(wpn_list)
            best_range = 0.0
            for wpn_inst, _ammo in wpn_list:
                r = wpn_inst.definition.max_range_m
                if r > best_range:
                    best_range = r
            unit_weapons_info[eid] = (count, best_range)

        # Set up recorder and victory evaluator
        recorder = SimulationRecorder(ctx.event_bus)

        # Build victory evaluator from scenario config
        victory_eval = None
        cfg = ctx.config
        if hasattr(cfg, 'victory_conditions') and cfg.victory_conditions:
            from stochastic_warfare.simulation.victory import (
                VictoryEvaluator, ObjectiveState,
            )
            from stochastic_warfare.core.types import Position
            objectives = []
            if hasattr(cfg, 'objectives') and cfg.objectives:
                for obj in cfg.objectives:
                    pos = obj.position if hasattr(obj, 'position') else [0, 0]
                    objectives.append(ObjectiveState(
                        objective_id=obj.objective_id,
                        position=Position(
                            easting=pos[0] if len(pos) > 0 else 0,
                            northing=pos[1] if len(pos) > 1 else 0,
                        ),
                        radius_m=obj.radius_m,
                    ))
            # VictoryConditionConfig from scenario module is compatible
            victory_eval = VictoryEvaluator(
                objectives=objectives,
                conditions=cfg.victory_conditions,
                event_bus=ctx.event_bus,
                max_duration_s=cfg.duration_hours * 3600.0,
            )

        # Set up engine
        engine_config = EngineConfig(max_ticks=20000, snapshot_interval_ticks=0)
        engine = SimulationEngine(
            ctx,
            config=engine_config,
            victory_evaluator=victory_eval,
            recorder=recorder,
        )

        # Record starting resolution
        result.started_tactical = str(engine.resolution) != "TickResolution.STRATEGIC"

        # Set up reinforcements if any
        if hasattr(cfg, 'reinforcements') and cfg.reinforcements:
            engine.campaign_manager.set_reinforcements(cfg.reinforcements)

        # Run
        run_result = engine.run()

        result.ticks_executed = run_result.ticks_executed
        result.sim_duration_s = run_result.duration_s
        if run_result.victory_result:
            result.victory_side = run_result.victory_result.winning_side
            result.victory_condition = run_result.victory_result.condition_type
            result.victory_message = run_result.victory_result.message

        # Track if tactical resolution was reached
        result.reached_tactical = result.started_tactical or any(
            e.event_type in ('BattleStartedEvent', 'EngagementEvent')
            for e in recorder._events
        )

        # Analyze events
        result.total_events = len(recorder._events)
        for e in recorder._events:
            et = e.event_type
            if 'Engagement' in et or 'Battle' in et:
                result.engagement_events += 1
            # Phase 91: count combat_damage destructions as engagements for
            # aggregate models (melee, archery, volley fire) that don't publish
            # EngagementEvent but do apply damage directly.
            if 'Destroy' in et:
                _cause = (e.data or {}).get('cause', '') if hasattr(e, 'data') else ''
                if _cause == 'combat_damage':
                    result.engagement_events += 1
            if 'Damage' in et or 'Hit' in et:
                result.damage_events += 1
            if 'Destroy' in et or 'Killed' in et or 'Sunk' in et or 'Downed' in et:
                result.destruction_events += 1
            if 'Morale' in et:
                result.morale_events += 1
            if 'Fire' in et or 'Shot' in et or 'Launch' in et or 'Volley' in et or 'Engagement' in et:
                result.weapon_fire_events += 1

        # Analyze final unit states
        total_casualties = 0
        units_moved = 0
        units_not_moved = 0
        distances = []
        active_distances = []

        unit_details = []
        side_positions: dict[str, list[tuple[float, float]]] = {}

        for side, units in ctx.units_by_side.items():
            active_count = 0
            destroyed_count = 0
            if side not in side_positions:
                side_positions[side] = []

            for u in units:
                status_str = u.status.name if hasattr(u.status, 'name') else str(u.status)
                end_pos = (u.position.easting, u.position.northing)
                start = initial_positions.get(u.entity_id, end_pos)
                dist = math.sqrt(
                    (end_pos[0] - start[0])**2 + (end_pos[1] - start[1])**2
                )

                wpn_count, best_range = unit_weapons_info.get(
                    u.entity_id, (0, 0.0)
                )

                detail = UnitDiagnostics(
                    entity_id=u.entity_id,
                    side=side,
                    unit_type=u.unit_type,
                    status=status_str,
                    start_pos=start,
                    end_pos=end_pos,
                    distance_moved=round(dist, 1),
                    weapons_count=wpn_count,
                    best_weapon_range=best_range,
                )
                unit_details.append(asdict(detail))

                if u.status == UnitStatus.ACTIVE:
                    active_count += 1
                    side_positions[side].append(end_pos)
                    if dist > 1.0:
                        active_distances.append(dist)
                else:
                    destroyed_count += 1
                    total_casualties += 1

                if dist > 1.0:
                    units_moved += 1
                    distances.append(dist)
                else:
                    units_not_moved += 1

            result.final_active[side] = active_count
            result.final_destroyed[side] = destroyed_count

        result.total_casualties = total_casualties
        result.units_that_moved = units_moved
        result.units_that_didnt_move = units_not_moved

        if distances:
            result.avg_distance_moved = round(sum(distances) / len(distances), 1)
            result.max_distance_moved = round(max(distances), 1)
        if active_distances:
            result.min_distance_moved_active = round(min(active_distances), 1)

        # Position spread (standard deviation of positions per side)
        for side, positions in side_positions.items():
            if len(positions) > 1:
                cx = sum(p[0] for p in positions) / len(positions)
                cy = sum(p[1] for p in positions) / len(positions)
                var = sum(
                    (p[0] - cx)**2 + (p[1] - cy)**2 for p in positions
                ) / len(positions)
                result.final_position_spread[side] = round(math.sqrt(var), 1)
            elif len(positions) == 1:
                result.final_position_spread[side] = 0.0

        result.unit_details = unit_details

        # Detect issues
        if result.total_casualties == 0 and result.ticks_executed > 10:
            # Skip CBRN / ISR scenarios where zero casualties is expected
            non_combat = ('cbrn_chemical', 'space_isr')
            if not any(tag in result.scenario_name for tag in non_combat):
                result.issues.append("ZERO_CASUALTIES")
        if result.engagement_events == 0 and result.ticks_executed > 10 and result.total_casualties == 0:
            # Only flag if there are truly no engagements AND no casualties.
            # Aggregate models (volley fire, archery) produce casualties without
            # EngagementEvent events.
            result.issues.append("ZERO_ENGAGEMENTS")
        if result.units_that_moved == 0 and result.initial_total > 0:
            result.issues.append("NO_MOVEMENT")
        if result.damage_events == 0 and result.engagement_events > 0 and result.total_casualties == 0:
            result.issues.append("ENGAGEMENTS_BUT_NO_DAMAGE")

        # Check for centroid collapse (all active units within 50m)
        # Skip if side lost >50% — survivors naturally cluster after collapse
        for side, spread in result.final_position_spread.items():
            active = result.final_active.get(side, 0)
            total = result.sides.get(side, 0)
            if total > 0 and (total - active) / total > 0.5:
                continue  # side lost majority — clustering is expected
            if spread < 50 and active > 2:
                result.issues.append(f"CENTROID_COLLAPSE_{side}")

        # Check for stuck units (active, have weapons, didn't move much)
        # Exclude defensive-side units — they are supposed to hold position
        _def_sides = set()
        _cal_ov = getattr(cfg, 'calibration_overrides', None)
        if isinstance(_cal_ov, dict):
            _def_sides = set(_cal_ov.get('defensive_sides', []))
        elif _cal_ov is not None:
            _def_sides = set(getattr(_cal_ov, 'defensive_sides', None) or [])
        stuck_count = 0
        non_defensive_total = 0
        for d in unit_details:
            if d['side'] in _def_sides:
                continue  # defensive units hold position by design
            non_defensive_total += 1
            if (d['status'] == 'ACTIVE'
                    and d['distance_moved'] < 10
                    and d['weapons_count'] > 0
                    and d['best_weapon_range'] > 0):
                stuck_count += 1
        if stuck_count > non_defensive_total * 0.5 and non_defensive_total > 4:
            result.issues.append(f"MANY_STUCK_UNITS({stuck_count}/{non_defensive_total})")

    except Exception as exc:
        result.success = False
        result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        result.issues.append("LOAD_OR_RUN_ERROR")

    result.duration_wall_s = round(time.time() - start_time, 2)
    return result


def find_all_scenarios(data_dir: Path) -> list[Path]:
    """Find all scenario.yaml files."""
    scenarios = []
    for p in sorted(data_dir.rglob("scenario.yaml")):
        # Skip test_campaign_* scenarios (internal test fixtures)
        if 'test_campaign' in p.parent.name:
            continue
        # Skip benchmark scenarios (Phase 90 — too large for evaluator timeout)
        if p.parent.name.startswith('benchmark_'):
            continue
        scenarios.append(p)
    return scenarios


def print_summary(results: list[ScenarioResult]) -> None:
    """Print a human-readable summary table."""
    # Header
    print("\n" + "=" * 120)
    print(f"{'SCENARIO EVALUATION REPORT':^120}")
    print("=" * 120)

    # Summary table
    print(f"\n{'Scenario':<35} {'Status':<8} {'Ticks':>6} {'Casualties':>10} "
          f"{'Engagements':>11} {'Moved':>6} {'Stuck':>6} {'Issues'}")
    print("-" * 120)

    issue_scenarios = []
    ok_scenarios = []

    for r in results:
        if not r.success:
            status = "ERROR"
        elif r.issues:
            status = "WARN"
        else:
            status = "OK"

        moved_str = f"{r.units_that_moved}/{r.initial_total}"
        stuck_str = f"{r.units_that_didnt_move}/{r.initial_total}"

        issues_str = ", ".join(r.issues) if r.issues else ""
        if not r.success:
            # Truncate error for table
            issues_str = r.error.split('\n')[0][:50]

        print(f"{r.scenario_name:<35} {status:<8} {r.ticks_executed:>6} "
              f"{r.total_casualties:>10} {r.engagement_events:>11} "
              f"{moved_str:>6} {stuck_str:>6} {issues_str}")

        if r.issues or not r.success:
            issue_scenarios.append(r)
        else:
            ok_scenarios.append(r)

    # Issue details
    if issue_scenarios:
        print(f"\n{'=' * 120}")
        print("DETAILED ISSUE REPORTS")
        print("=" * 120)

        for r in issue_scenarios:
            print(f"\n--- {r.scenario_name} ---")
            if not r.success:
                print(f"  ERROR: {r.error[:500]}")
                continue

            print(f"  Issues: {', '.join(r.issues)}")
            print(f"  Victory: {r.victory_condition} — {r.victory_message}")
            print(f"  Duration: {r.sim_duration_s:.0f}s sim, {r.duration_wall_s:.1f}s wall")
            print(f"  Forces: {r.sides}")
            print(f"  Final active: {r.final_active}")
            print(f"  Final destroyed: {r.final_destroyed}")
            print(f"  Events: total={r.total_events}, engage={r.engagement_events}, "
                  f"damage={r.damage_events}, destroy={r.destruction_events}")
            print(f"  Movement: moved={r.units_that_moved}, stuck={r.units_that_didnt_move}, "
                  f"avg_dist={r.avg_distance_moved:.0f}m, max_dist={r.max_distance_moved:.0f}m")
            print(f"  Position spread: {r.final_position_spread}")
            print(f"  Started tactical: {r.started_tactical}, "
                  f"Reached tactical: {r.reached_tactical}")

            # Show stuck units
            stuck = [d for d in r.unit_details
                     if d['status'] == 'ACTIVE' and d['distance_moved'] < 10]
            if stuck and len(stuck) <= 20:
                print("  Stuck active units:")
                for d in stuck:
                    print(f"    {d['entity_id']} ({d['unit_type']}, {d['side']}) "
                          f"pos=({d['end_pos'][0]:.0f}, {d['end_pos'][1]:.0f}) "
                          f"weapons={d['weapons_count']} "
                          f"best_range={d['best_weapon_range']:.0f}m")

    # Summary
    print(f"\n{'=' * 120}")
    print(f"TOTALS: {len(results)} scenarios — "
          f"{len(ok_scenarios)} OK, "
          f"{len(issue_scenarios)} with issues")
    print("  Issues breakdown:")
    from collections import Counter
    all_issues = []
    for r in results:
        all_issues.extend(r.issues)
    for issue, count in Counter(all_issues).most_common():
        print(f"    {issue}: {count}")
    print("=" * 120)


def main():
    parser = argparse.ArgumentParser(description="Evaluate all scenarios")
    parser.add_argument("--scenario", type=str, help="Run only this scenario (directory name)")
    parser.add_argument("--output", type=str, help="Save results to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Show per-unit details")
    parser.add_argument("--no-details", action="store_true",
                        help="Omit per-unit details from JSON output")
    parser.add_argument("--seed", type=int, default=42,
                        help="PRNG seed (default: 42)")
    args = parser.parse_args()

    data_dir = project_root / "data"
    all_scenarios = find_all_scenarios(data_dir)

    if args.scenario:
        all_scenarios = [s for s in all_scenarios if args.scenario in s.parent.name]
        if not all_scenarios:
            print(f"No scenarios matching '{args.scenario}'")
            sys.exit(1)

    print(f"Found {len(all_scenarios)} scenarios to evaluate")
    print(f"Scenarios: {[s.parent.name for s in all_scenarios]}\n")

    results: list[ScenarioResult] = []
    for i, scenario_path in enumerate(all_scenarios, 1):
        name = scenario_path.parent.name
        print(f"[{i}/{len(all_scenarios)}] Running {name}...", end=" ", flush=True)
        r = run_scenario(scenario_path, data_dir, verbose=args.verbose, seed=args.seed)
        status = "OK" if r.success and not r.issues else (
            "ERROR" if not r.success else f"WARN({','.join(r.issues)})"
        )
        print(f"{status} ({r.ticks_executed} ticks, {r.total_casualties} casualties, "
              f"{r.duration_wall_s:.1f}s)")
        results.append(r)

    print_summary(results)

    if args.output:
        out_data = []
        for r in results:
            d = asdict(r)
            if args.no_details:
                d.pop('unit_details', None)
            out_data.append(d)
        with open(args.output, 'w') as f:
            json.dump(out_data, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
