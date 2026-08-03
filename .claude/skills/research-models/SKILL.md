---
name: research-models
description: "Research defensible mathematical, stochastic, signal-processing, optimization, and numerical models for Stochastic Warfare. Use when selecting, replacing, or parameterizing an equation, distribution, estimator, random process, or quantitative algorithm; do not use for routine refactors that leave the model contract unchanged."
---

# Quantitative Model Research

Read `CODEX.md`, the relevant specification, current implementation, phase
material, and remediation entry. Research the model that the production path
needs, not an isolated mathematical curiosity.

## Frame the Decision

1. State the observable phenomenon, inputs, outputs, scale, units, and required
   fidelity.
2. Identify the current model and the precise deficiency or open design choice.
3. Define required stochastic, numerical, runtime, and deterministic-replay
   properties.
4. Establish how candidate models could be parameterized and falsified.

## Source Discipline

Classify every material source:

### Tier 1 — Primary or Authoritative

- Original papers, established textbooks, standards, and government technical
  reports
- FFRDC analytical publications with inspectable evidence and methods

### Tier 2 — Academic or Peer-Reviewed

- Peer-reviewed signal-processing, probability, control, applied-mathematics,
  operations-research, and defense-modeling publications
- Established academic-press monographs

### Tier 3 — Implementation Reference

- Official NumPy, SciPy, or other library documentation for implementation
  behavior only
- Cited open-source implementations as supplementary implementation evidence

Treat arXiv material as a preprint unless publication is verified. Treat search
indexes as discovery tools. Do not select a model from Tier 3 material alone, or
from tutorials, forum answers, or implementations without a traceable
mathematical source.

## Evaluate Each Candidate

Record:

- formulation, equations, variable definitions, units, and dimensional checks;
- assumptions, independence claims, stationarity, boundary conditions, and
  failure modes;
- parameter ranges, estimation data, identifiability, and correlations;
- stochastic distribution and integration with project RNG streams;
- numerical stability, precision, conditioning, clipping, and edge behavior;
- computational complexity and expected hot-path cost;
- calibration risk and sensitivity to inputs;
- validation oracle, negative controls, and Monte Carlo design;
- alternatives and why they are preferable or inferior for this use.

For signal-processing models, define signal, noise, detection threshold, false
alarm behavior, and ROC implications. For state estimators, define process and
measurement models and covariance assumptions. For optimization, define the
objective, constraints, convergence behavior, and infeasible cases.

## Recommend and Hand Off

Recommend a model only when its assumptions match the simulated phenomenon.
State:

- the selected formulation and source;
- implementation-ready equations and units;
- required configuration fields and validation;
- deterministic RNG and iteration requirements;
- expected test cases, sensitivity analysis, and performance checks;
- assumptions that must be documented;
- remaining evidence gaps.

If implementation follows, trace it through the completion evidence matrix in
`CODEX.md`. A correct derivation, import, or isolated function call does not
prove production wiring or outcome effect.
