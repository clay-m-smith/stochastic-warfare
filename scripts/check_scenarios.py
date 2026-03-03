"""Quick check that all scenario YAML files load correctly."""
from pathlib import Path
from stochastic_warfare.validation.historical_data import HistoricalDataLoader

loader = HistoricalDataLoader()
scenarios_dir = Path("data/scenarios")

for scenario_dir in sorted(scenarios_dir.iterdir()):
    if not scenario_dir.is_dir():
        continue
    scenario_file = scenario_dir / "scenario.yaml"
    if not scenario_file.exists():
        print(f"  SKIP {scenario_dir.name} (no scenario.yaml)")
        continue
    try:
        eng = loader.load(scenario_file)
        print(f"  OK {eng.name}")
        print(f"     Blue: {len(eng.blue_forces.units)} unit types, {eng.blue_forces.personnel_total} pers")
        print(f"     Red: {len(eng.red_forces.units)} unit types, {eng.red_forces.personnel_total} pers")
        print(f"     Outcomes: {len(eng.documented_outcomes)} metrics")
        print(f"     Terrain: {eng.terrain.terrain_type} {eng.terrain.width_m}x{eng.terrain.height_m}m")
    except Exception as e:
        print(f"  FAIL {scenario_dir.name}: {e}")

print("\nDone.")
