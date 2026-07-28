---
name: timeline
description: "Generate an evidence-grounded battle timeline or after-action report from recorded simulation events. Use for scenario narratives, event-sequence analysis, battle reports, or recorder exposure checks."
---

# Generate a Battle Timeline

Follow `CODEX.md`. Treat a narrative as a presentation of recorded evidence,
not as proof that unobserved behavior occurred.

## Run the Production Scenario

1. Select an explicit scenario path, deterministic seed, maximum tick count,
   and any requested side or event filters.
2. Inspect the current constructor signatures for `ScenarioLoader`,
   `SimulationEngine`, `EngineConfig`, `SimulationRecorder`, and
   `VictoryEvaluator` before building the run.
3. Load through `ScenarioLoader`, attach `SimulationRecorder` to the context's
   event bus, configure a bounded engine run, and use the scenario's actual
   victory contract where applicable.
4. Record the exact command, seed, tick bound, stop condition, and result.

Avoid an unbounded default run. If the scenario is expensive, use the smallest
bound that still exercises the requested narrative behavior and label the
result as partial.

## Build the Narrative

Pass `recorder.events` to
`stochastic_warfare.tools.narrative.generate_narrative`, then format the result
with `format_narrative` using `full`, `summary`, or `timeline` style.

Organize a longer report around actual simulation time or tick ranges:

- initial disposition and first recorded contacts;
- material engagements, decisions, morale transitions, and supply events;
- termination condition, final recorded disposition, and losses.

Event-bearing ticks may be sparse. Do not calculate opening, middle, and
conclusion percentages from the number of narrative entries.

## Preserve Evidentiary Accuracy

- State only facts supported by recorded events, snapshots, final state, or run
  results.
- Label causal explanations and military interpretation as inference.
- Do not invent commander intent, undetected movement, supply effects,
  casualties, or victory reasons.
- Do not treat the absence of a recorded event as proof that the underlying
  behavior did not happen.
- Identify formatter fallbacks and event types without dedicated narrative
  handling when they materially affect readability.

When changing narrative or recorder code, add behavioral tests for ordering,
filters, formatting, empty input, unknown event types, and deterministic
output. Verify recorder/API/UI exposure separately when it is part of the
requirement.
