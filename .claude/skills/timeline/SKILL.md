# Battle Timeline / Narrative

Run a scenario and generate a human-readable narrative of the battle.

## Trigger
Use when the user wants to:
- See what happens in a scenario run as a story
- Generate a battle report or after-action review
- Understand the sequence of events in a simulation

## Process

### 1. Select Scenario
Ask the user which scenario to run, or use the one they've been working with.

### 2. Run Simulation
```python
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.victory import VictoryEvaluator
```
Run with recorder enabled and appropriate max_ticks.

### 3. Generate Narrative
Use `stochastic_warfare.tools.narrative`:
```python
from stochastic_warfare.tools.narrative import generate_narrative, format_narrative

ticks = generate_narrative(
    recorder.events,
    side_filter=None,        # or "blue"/"red"
    event_types=None,        # or ["EngagementEvent", "MoraleStateChangeEvent"]
    max_ticks=None,
)
```

### 4. Structure as Report
Present the narrative in three phases:

#### Opening (first 10% of ticks)
- Initial contact and detection events
- First engagement decisions
- Force dispositions

#### Main Battle (middle 80% of ticks)
- Key engagements and their outcomes
- Morale shifts and their causes
- Commander decisions and order flow
- Supply state changes

#### Conclusion (final 10% of ticks)
- Victory conditions met
- Final force disposition
- Casualties and losses

### 5. Output Styles
Offer the user a choice:
- **Full** (`style="full"`): Every tick with all entries
- **Summary** (`style="summary"`): Only significant events (engagements, damage, morale changes, victories)
- **Timeline** (`style="timeline"`): Compact one-line-per-event format

```python
text = format_narrative(ticks, style="summary")
```

## Reference
- Module: `stochastic_warfare/tools/narrative.py`
- Event types with formatters: EngagementEvent, HitEvent, DamageEvent, DetectionEvent, MoraleStateChangeEvent, RoutEvent, SurrenderEvent, OrderIssuedEvent, DecisionMadeEvent, VictoryDeclaredEvent, OODAPhaseChangeEvent, and more
