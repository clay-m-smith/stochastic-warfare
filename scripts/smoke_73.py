"""Smoke test for 73 Easting scenario calibration."""
from pathlib import Path
from collections import Counter

from stochastic_warfare.validation.historical_data import HistoricalDataLoader
from stochastic_warfare.validation.scenario_runner import ScenarioRunner, ScenarioRunnerConfig
from stochastic_warfare.validation.metrics import EngagementMetrics

loader = HistoricalDataLoader()
eng = loader.load(Path("data/scenarios/73_easting/scenario.yaml"))
config = ScenarioRunnerConfig(master_seed=42, max_ticks=500, data_dir="data")
runner = ScenarioRunner(config)
result = runner.run(eng)

print(f"Ticks: {result.ticks_executed}")
print(f"Duration: {result.duration_simulated_s:.0f}s ({result.duration_simulated_s/60:.1f} min)")
print(f"Terminated by: {result.terminated_by}")
print(f"Events: {len(result.event_log)}")

metrics = EngagementMetrics.extract_all(result)
for k, v in sorted(metrics.items()):
    print(f"  {k}: {v}")

blue_status = Counter(u.status for u in result.units_final if u.side == "blue")
red_status = Counter(u.status for u in result.units_final if u.side == "red")
print(f"Blue status: {dict(blue_status)}")
print(f"Red status: {dict(red_status)}")
