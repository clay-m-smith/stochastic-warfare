# Auto-Calibration

Automatically tune calibration overrides to match historical engagement metrics.

## Trigger
Use when the user wants to:
- Calibrate a scenario to match historical outcomes
- Find the right parameter values for historical accuracy
- Tune hit probability, target size, or force modifiers

## Process

### 1. Identify Target Metrics
Ask the user for the historical metrics to match:
- **Exchange ratio**: e.g., 4.6:1 for Golan Heights
- **Casualties per side**: e.g., blue=10, red=46
- **Duration**: how long the engagement lasted
- **Other metrics**: territory control, morale outcomes

### 2. Identify Influential Parameters
Common calibration parameters and their primary effects:
| Parameter | Primary Effect |
|-----------|---------------|
| `hit_probability_modifier` | Overall lethality scaling |
| `target_size_modifier` | Defensive advantage (hull-down, concealment) |
| `force_ratio_modifier` | Assessment bias for attack/defense decisions |
| `morale_modifier` | Rate of morale degradation |

### 3. Sweep Each Parameter
For each parameter, run a sensitivity sweep to find the value range that produces results closest to the target:

```python
from stochastic_warfare.tools.sensitivity import SweepConfig, run_sweep

config = SweepConfig(
    scenario_path="data/scenarios/{name}/scenario.yaml",
    parameter_name="hit_probability_modifier",
    values=[0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
    metric_names=["exchange_ratio", "blue_destroyed", "red_destroyed"],
    iterations_per_point=10,
    max_ticks=200,
)
result = run_sweep(config)
```

### 4. Binary Search Refinement
Once the approximate range is found, use binary search to narrow down:
1. Find the two sweep points that bracket the target metric
2. Test the midpoint
3. Recurse until within 5% of target or 5 iterations

### 5. Multi-Parameter Calibration
If multiple parameters need tuning:
1. Start with the most influential parameter (usually `hit_probability_modifier`)
2. Fix it at the best value found
3. Move to the next parameter
4. Repeat until all parameters are calibrated
5. Do one final validation sweep with all parameters set

### 6. Validate
Run 20+ iterations with the final calibration and compare:
```python
from stochastic_warfare.tools.comparison import compare_distributions

# Compare simulation mean to historical value
# p-value indicates if the simulation is consistent with history
```

### 7. Output
Provide the final `calibration_overrides` block:
```yaml
calibration_overrides:
  hit_probability_modifier: 0.85
  target_size_modifier: 0.55
  force_ratio_modifier: 1.0
```

Report:
- Each parameter value and why it was chosen
- Final metric comparison (simulation mean vs historical)
- Confidence level (p-value from statistical test)
- Any remaining discrepancies and possible causes

## Reference
- Existing calibrations: see `data/scenarios/golan_heights/scenario.yaml`, `data/scenarios/73_easting/scenario.yaml`
- Known calibration values: Golan target_size_modifier=0.55 (hull-down positions)
- Modules: `stochastic_warfare/tools/sensitivity.py`, `stochastic_warfare/tools/comparison.py`
