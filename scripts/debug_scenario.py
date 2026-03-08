"""Quick debug script for a single scenario."""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.entities.base import UnitStatus

scenario = sys.argv[1] if len(sys.argv) > 1 else "cannae"

# Find scenario
data_dir = Path(__file__).parent.parent / "data"
matches = list(data_dir.rglob(f"*{scenario}*/scenario.yaml"))
if not matches:
    print(f"No scenario matching '{scenario}'")
    sys.exit(1)
scenario_path = matches[0]
print(f"Loading: {scenario_path}")

loader = ScenarioLoader(data_dir)
ctx = loader.load(scenario_path, seed=42)

# Print forces
print("\n=== FORCES ===")
for side, units in ctx.units_by_side.items():
    print(f"\n  {side}: {len(units)} units")
    for u in units:
        pos = u.position
        print(f"    {u.entity_id} ({u.unit_type}) at ({pos.easting:.0f}, {pos.northing:.0f})")

# Print weapons
print("\n=== WEAPONS ===")
for eid, wpns in ctx.unit_weapons.items():
    for wi, ammos in wpns:
        cat = wi.definition.category
        ad = ammos[0] if ammos else None
        print(f"  {eid}: {wi.definition.weapon_id} cat={cat} "
              f"range={wi.definition.max_range_m}m min={wi.definition.min_range_m}m "
              f"mag={wi.definition.magazine_capacity} "
              f"ammo={ad.ammo_id if ad else 'NONE'} pen={ad.penetration_mm_rha if ad else 0}")

# Run simulation
recorder = SimulationRecorder(ctx.event_bus)
engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=50000), recorder=recorder)
print(f"\nStarting resolution: {engine.resolution}")

run_result = engine.run()
print(f"\n=== RESULT ===")
print(f"Ticks: {run_result.ticks_executed}")
print(f"Duration: {run_result.duration_s:.0f}s")
print(f"Victory: {run_result.victory_result}")

# Event analysis
event_types = Counter(e.event_type for e in recorder._events)
print(f"\n=== EVENT TYPES ===")
for et, count in event_types.most_common(20):
    print(f"  {et}: {count}")

# Look at engagement results
engagement_results = Counter()
weapon_usage = Counter()
for e in recorder._events:
    if e.event_type == 'EngagementEvent':
        engagement_results[e.data.get('result', 'unknown')] += 1
        weapon_usage[e.data.get('weapon_id', '?')] += 1
print(f"\n=== ENGAGEMENT RESULTS ===")
for r, c in engagement_results.most_common():
    print(f"  {r}: {c}")
print(f"\n=== WEAPON USAGE ===")
for w, c in weapon_usage.most_common():
    print(f"  {w}: {c}")

# Check damage events
print(f"\n=== DAMAGE EVENTS ===")
for e in recorder._events:
    if e.event_type == 'DamageEvent':
        print(f"  tick={e.tick} target={e.data.get('target_id', '?')} "
              f"damage={e.data.get('damage_amount', '?')} "
              f"type={e.data.get('damage_type', '?')}")

# Final unit status
print(f"\n=== FINAL STATUS ===")
for side, units in ctx.units_by_side.items():
    for u in units:
        print(f"  {u.entity_id}: {u.status.name}")
