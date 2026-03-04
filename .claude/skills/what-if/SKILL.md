# What-If Analysis

Quick parameter sensitivity analysis — answers "what if X were different?" questions.

## Trigger
Use when the user asks questions like:
- "What if we increased the hit probability?"
- "How sensitive is the outcome to force ratio?"
- "What happens if we change the target size modifier?"

## Process

### 1. Parse the Question
Identify from the user's question:
- **Parameter**: Which calibration override to sweep (e.g., `hit_probability_modifier`)
- **Range**: What values to test. If not specified, use sensible defaults:
  - Multipliers: [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
  - Counts: [2, 4, 6, 8, 10]
- **Scenario**: Which scenario to use (default: `test_campaign`)
- **Metrics**: Which outcomes to track

### 2. Run Sweep
Use `stochastic_warfare.tools.sensitivity`:
```python
from stochastic_warfare.tools.sensitivity import SweepConfig, run_sweep, plot_sweep

config = SweepConfig(
    scenario_path="data/scenarios/test_campaign/scenario.yaml",
    parameter_name="hit_probability_modifier",
    values=[0.5, 0.75, 1.0, 1.25, 1.5],
    metric_names=["blue_destroyed", "red_destroyed"],
    iterations_per_point=10,
    max_ticks=50,
)
result = run_sweep(config)
```

### 3. Analyze Results
For each sweep point, report:
- Mean and standard deviation of each metric
- Whether the relationship is linear, exponential, or threshold-based
- Key inflection points where behavior changes dramatically

### 4. Visualize
Generate a plot using `plot_sweep(result, metric="blue_destroyed")` and save it for the user.

### 5. Summarize
Provide a plain-language summary:
- "Increasing hit probability from 0.5x to 1.5x reduces red losses by X on average"
- "The effect is nonlinear — most of the change happens between 0.75x and 1.25x"
- "This parameter has [high/medium/low] sensitivity"

## Common Parameters
| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| `hit_probability_modifier` | Global hit probability scaling | 0.25–2.0 |
| `target_size_modifier` | Target size scaling | 0.25–2.0 |
| `force_ratio_modifier` | Force ratio assessment bias | 0.5–3.0 |
| `morale_modifier` | Morale transition rate scaling | 0.5–2.0 |

## Reference
- Module: `stochastic_warfare/tools/sensitivity.py`
- Calibration keys: defined per-scenario in `calibration_overrides` section
