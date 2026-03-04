# A/B Configuration Comparison

Run two scenario configurations and statistically compare their outcomes.

## Trigger
Use when the user wants to:
- Compare two different configurations of the same scenario
- Determine if a parameter change has a statistically significant effect
- Evaluate the impact of calibration overrides

## Process

### 1. Identify Configurations
Determine what the user wants to compare:
- **Same scenario, different overrides**: e.g., hit_probability_modifier=0.8 vs 1.2
- **Different scenarios**: two scenario YAML files
- **Before/after a code change**: run same config, compare results

Ask for:
- Scenario path
- Override dict for config A
- Override dict for config B
- Labels for A and B
- Number of iterations (recommend 20+ for statistical significance)
- Metrics to compare

### 2. Run Comparison
Use `stochastic_warfare.tools.comparison`:
```python
from stochastic_warfare.tools.comparison import ComparisonConfig, run_comparison, format_comparison

config = ComparisonConfig(
    scenario_path="data/scenarios/test_campaign/scenario.yaml",
    overrides_a={"hit_probability_modifier": 0.8},
    overrides_b={"hit_probability_modifier": 1.2},
    label_a="Low Hit Prob",
    label_b="High Hit Prob",
    num_iterations=20,
    metric_names=["blue_destroyed", "red_destroyed", "exchange_ratio"],
)
result = run_comparison(config)
print(format_comparison(result))
```

### 3. Interpret Results
For each metric, explain:
- **p-value < 0.05**: Statistically significant difference. The parameter change has a measurable effect.
- **p-value > 0.05**: No significant difference detected. Either the effect is too small or more iterations are needed.
- **Effect size**: How large the practical difference is (|r| > 0.5 = large, > 0.3 = medium, > 0.1 = small)

### 4. Military Context
Relate findings back to military concepts:
- Hit probability changes → lethality of weapons systems
- Force ratio changes → Lanchester attrition dynamics
- Morale effects → Clausewitzian friction

## Reference
- Module: `stochastic_warfare/tools/comparison.py`
- Available metrics: `blue_destroyed`, `red_destroyed`, `blue_active`, `red_active`, `exchange_ratio`, `ticks_executed`
