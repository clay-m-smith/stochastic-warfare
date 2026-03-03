"""Quick smoke test: run 73 Easting scenario once."""
from pathlib import Path
from stochastic_warfare.validation.historical_data import HistoricalDataLoader
from stochastic_warfare.validation.scenario_runner import ScenarioRunner, ScenarioRunnerConfig
from stochastic_warfare.validation.metrics import EngagementMetrics
from stochastic_warfare.entities.loader import UnitLoader

# Debug: check UnitLoader
data_dir = Path("data")
ul = UnitLoader(data_dir / "units")
ul.load_all()
print(f"Available unit types: {ul.available_types()}")
print(f"m3a2_bradley in loader: {'m3a2_bradley' in ul.available_types()}")
print(f"bmp1 in loader: {'bmp1' in ul.available_types()}")

loader = HistoricalDataLoader()
eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))

config = ScenarioRunnerConfig(master_seed=42, max_ticks=500, data_dir="data")
runner = ScenarioRunner(config)

print("\nRunning scenario...")
result = runner.run(eng)

print(f"Ticks: {result.ticks_executed}")
print(f"Duration: {result.duration_simulated_s}s")
print(f"Terminated by: {result.terminated_by}")
print(f"Events: {len(result.event_log)}")
print(f"Units final: {len(result.units_final)}")
for u in result.units_final[:5]:
    print(f"  {u.entity_id}: {u.status} morale={u.morale_state}")

metrics = EngagementMetrics.extract_all(result)
for k, v in sorted(metrics.items()):
    print(f"  {k}: {v}")
