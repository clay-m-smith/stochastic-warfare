# Post-Phase Scenario Evaluation

Run all scenarios through the simulation engine, compare results against the previous baseline, and report improvements and regressions.

## When to Use
Run after completing any development phase that modifies the battle loop, engagement resolution, victory evaluation, or scenario data. This is the primary tool for detecting unintended behavioral changes.

## Process

### 1. Run Evaluation
```bash
uv run python scripts/evaluate_scenarios.py --output scripts/evaluation_results_latest.json --no-details
```

### 2. Load Baseline
Find the most recent previous evaluation results file in `scripts/`:
- `evaluation_results_v4.json` (Phase 42 baseline)
- `evaluation_results_v3.json` (Phase 41 baseline)
- etc.

If no baseline exists, skip comparison and just report current results.

### 3. Compare Results
For each scenario, compare:
- **Winner**: Did the winning side change?
- **Victory condition**: Did the condition type change (e.g., force_destroyed → time_expired)?
- **Casualties**: Did total casualties change by ≥2?
- **Issues**: Did new diagnostic issues appear or existing ones resolve?

### 4. Classify Changes

**Positive changes** (historically more accurate):
- A wrong winner is now correct
- A draw resolved to the correct winner
- Casualty ratios moved closer to historical data
- Diagnostic issues resolved

**Concerning changes** (needs investigation):
- A correct winner flipped to wrong
- Scenarios stalling at max_ticks (previously resolved quickly)
- New diagnostic issues appeared (ZERO_CASUALTIES, ZERO_ENGAGEMENTS, NO_MOVEMENT)
- Casualty counts changed dramatically without explanation

**Neutral changes**:
- Small tick count variations
- Minor casualty count differences (±1)
- Same winner/condition with slightly different message

### 5. Report Format
Present a summary table:
```
| Scenario | Before Winner | After Winner | Before Cond | After Cond | Cas Delta | Assessment |
```

Then list:
- **Improvements**: Scenarios that became more accurate
- **Regressions**: Scenarios that became less accurate
- **Stalls**: Scenarios that hit max_ticks
- **Unchanged**: Count of scenarios with no significant changes

### 6. Save New Baseline
If results are acceptable, rename the output:
```bash
mv scripts/evaluation_results_latest.json scripts/evaluation_results_v{N+1}.json
```

### 7. Update Devlog
Add scenario evaluation results to the current phase devlog under a `## Scenario Evaluation` section.

## Historical Baselines
- v3: Pre-Phase 42 (after Phase 41)
- v4: Post-Phase 42
- Future versions increment from there

## Key Scenarios to Watch
These scenarios have known historical outcomes and are the best indicators of engine fidelity:
- **73 Easting** (1991): Blue (US) decisive win, ~4:1 exchange ratio
- **Golan Heights** (1973): Israeli defense, high Syrian casualties
- **Trafalgar** (1805): British decisive naval victory
- **Midway** (1942): USN victory, 4 IJN carriers sunk
- **Kursk** (1943): Soviet strategic victory
- **Normandy Bocage** (1944): US slow advance, high casualties
