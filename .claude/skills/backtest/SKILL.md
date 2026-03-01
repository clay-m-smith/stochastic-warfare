---
name: backtest
description: Structure a validation comparison between simulation output and historical engagement data. Use when verifying simulation fidelity against real-world outcomes.
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch, Bash
context: fork
agent: general-purpose
---

# Historical Backtest Structuring Skill

You are structuring a backtest for the Stochastic Warfare simulation — comparing simulation output against historical military data to validate model fidelity.

## Task
$ARGUMENTS

## Research Source Constraints
All historical data must come from validated sources (see docs/skills-and-hooks.md for full tier definitions):
- Tier 1: Official military histories, government reports, doctrine publications
- Tier 2: Peer-reviewed academic publications
- Tier 3: Established military reference publishers
- EXCLUDED: Blogs, forums, unsourced claims, gaming wikis

## Backtest Report Structure

### 1. Historical Engagement Summary
- What happened: forces involved, terrain, weather, timeline, outcome
- Sources: full citations for all historical data used
- Key quantitative data: force sizes, casualties, distances, durations, ammunition expenditure

### 2. Scenario Configuration
- How to set up this engagement in the simulation
- Unit compositions (map to YAML unit definitions)
- Terrain and map requirements
- Initial dispositions and objectives
- Intelligence state for each side

### 3. Metrics to Compare
For each metric, specify:
- **Metric name** (e.g., "total casualties, Blue force")
- **Historical value** with source and confidence level
- **How to extract from simulation** (which output field/log)
- **Acceptable tolerance** and rationale for that tolerance
- **What divergence would indicate** (model deficiency vs. historical uncertainty)

### 4. Common Metrics Checklist
Consider these where data is available:
- [ ] Casualty rates (KIA, WIA) by side
- [ ] Equipment losses by type
- [ ] Engagement duration
- [ ] Territorial outcome (ground gained/lost)
- [ ] Ammunition expenditure rates
- [ ] Movement rates vs. planned rates
- [ ] Force ratio vs. exchange ratio (Lanchester validation)

### 5. Known Limitations
- What aspects of the historical engagement the simulation cannot yet model
- What historical data is uncertain or contested
- What simplifications are being made and their expected impact

### 6. Multiple Runs
- Since the simulation is stochastic, specify number of Monte Carlo runs
- Define statistical measures: mean, std dev, confidence intervals
- Historical outcome should fall within the expected distribution — if not, investigate why

## Important
- Be honest about data quality — flag uncertain historical figures
- A failed backtest is valuable information, not a failure. It identifies where the model needs refinement.
- Document everything needed to reproduce the backtest from scratch
