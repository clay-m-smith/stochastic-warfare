---
name: audit-determinism
description: Deep audit of PRNG discipline and simulation determinism in a module. Traces all stochastic paths to verify reproducibility. Use before finalizing any module that involves randomness.
allowed-tools: Read, Grep, Glob
---

# Determinism Auditor

You are performing a deep audit of simulation determinism in the Stochastic Warfare project. This goes beyond pattern-matching for convention violations — you are tracing the actual flow of randomness through the code to verify that replay fidelity is guaranteed.

## Target
$ARGUMENTS

If no target specified, audit the entire simulation core.

## Audit Checklist

### 1. PRNG Source Tracing
For every call that produces a random value:
- [ ] Identify the Generator instance used
- [ ] Trace it back to its creation — was it forked from the central RNG manager?
- [ ] Verify it uses the correct subsystem stream (combat RNG for combat, movement RNG for movement, etc.)
- [ ] Confirm no two subsystems share a Generator instance (cross-contamination)

### 2. Call Order Determinism
- [ ] Are random values consumed in the same order every run?
- [ ] Could conditional branches cause different numbers of RNG calls depending on state? (This shifts the sequence for all subsequent calls)
- [ ] Are collections iterated in deterministic order before drawing random values?
- [ ] Do any early-exit conditions skip RNG calls that would normally occur? (This shifts the sequence)

### 3. External Non-Determinism Sources
- [ ] No `time.time()`, `datetime.now()`, or wall-clock time in sim logic
- [ ] No `os.getpid()`, `id()`, or memory-address-dependent behavior
- [ ] No hash-based ordering (Python's `hash()` is randomized by default via PYTHONHASHSEED)
- [ ] No threading or multiprocessing in the simulation core (race conditions break determinism)
- [ ] No floating-point non-determinism from reordered operations (e.g., summing in different orders)

### 4. State Serialization Completeness
- [ ] Can the full PRNG state be captured via `generator.bit_generator.state`?
- [ ] Is ALL simulation state serializable for checkpointing?
- [ ] After restoring from checkpoint + PRNG state, does the simulation produce identical results?

### 5. Sequence Stability Under Code Changes
- [ ] If a new stochastic element is added to subsystem A, does it affect the random sequence in subsystem B? (It shouldn't, if streams are properly isolated)
- [ ] Are PRNG streams forked by name/key rather than by creation order? (Order-dependent forking is fragile)

## Output Format

```
DETERMINISM AUDIT: <module/file>
================================================

PRNG SOURCES FOUND:
  1. File:Line — Generator instance — Stream: <subsystem> — Status: OK/ISSUE
  ...

CALL ORDER ANALYSIS:
  [OK/ISSUE] Description of finding
  ...

EXTERNAL NON-DETERMINISM:
  [OK/ISSUE] Description of finding
  ...

SERIALIZATION:
  [OK/ISSUE] Description of finding
  ...

STREAM ISOLATION:
  [OK/ISSUE] Description of finding
  ...

VERDICT: DETERMINISTIC / NON-DETERMINISTIC / CONDITIONALLY DETERMINISTIC
  Summary of findings and required fixes.
```

## Important
- This audit must be thorough. A single missed non-determinism source silently breaks replay.
- When in doubt, flag it. False positives are better than missed issues.
- Consider edge cases: what happens with zero units? Empty collections? Maximum values?
