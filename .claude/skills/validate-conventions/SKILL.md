---
name: validate-conventions
description: Review Python code against Stochastic Warfare project conventions. Checks for PRNG discipline, deterministic iteration, coordinate system usage, logging, and type hints. Use after writing or modifying simulation core code.
allowed-tools: Read, Grep, Glob
---

# Convention Validator

You are reviewing code in the Stochastic Warfare project for compliance with project conventions. These conventions exist to ensure simulation determinism, reproducibility, and code quality.

## Target
$ARGUMENTS

If no specific file or directory is given, scan the entire simulation core (`src/` or the main package directory).

## Convention Rules (CHECK ALL)

### 1. PRNG Discipline (CRITICAL)
- **VIOLATION**: Any use of `import random`, `random.random()`, `random.choice()`, `random.randint()`, `random.uniform()`, `random.gauss()`, or any `random` module function
- **REQUIRED**: All randomness must flow through seeded `numpy.random.Generator` instances
- **VIOLATION**: Using `numpy.random.seed()` or the legacy `numpy.random.RandomState` global functions (e.g., `np.random.random()`, `np.random.randn()`)
- **REQUIRED**: Explicit `numpy.random.Generator` via `numpy.random.default_rng(seed)` or forked from the central RNG manager
- **CHECK**: Each subsystem should use its own dedicated PRNG stream, not share generators across subsystems

### 2. Deterministic Iteration (CRITICAL)
- **VIOLATION**: Iterating over `set()` objects where iteration order affects simulation logic
- **VIOLATION**: Relying on `dict` iteration order for simulation-critical sequences (acceptable for display/logging)
- **REQUIRED**: Use sorted collections, ordered data structures, or explicit ordering when iteration order matters
- **CHECK**: Look for `for x in some_set` or `for k, v in some_dict.items()` in simulation-critical paths

### 3. Coordinate System
- **VIOLATION**: Using lat/lon (geodetic) coordinates in simulation math (distance calculations, movement, range checks)
- **REQUIRED**: All simulation math in ENU/UTM (meters). Geodetic only at import/export/display boundaries
- **CHECK**: Look for variables named `lat`, `lon`, `latitude`, `longitude` in simulation core — these should only appear in conversion functions

### 4. Logging
- **VIOLATION**: Bare `print()` calls in simulation core code
- **REQUIRED**: Use the project logging framework (`logging` module or project-specific logger)
- **EXCEPTION**: `print()` is acceptable in CLI entry points, scripts, and test utilities

### 5. Type Hints
- **CHECK**: All public API functions (not prefixed with `_`) should have type hints for parameters and return values
- **ADVISORY**: Missing type hints are a warning, not a blocking violation

### 6. No Timing-Dependent Behavior
- **VIOLATION**: Using `time.time()`, `datetime.now()`, or wall-clock time in simulation logic
- **REQUIRED**: All time in the simulation is simulation time (tick count, sim clock), never wall-clock
- **EXCEPTION**: Performance profiling, logging timestamps, and non-simulation utility code

## Output Format

For each file checked, report:
```
FILE: path/to/file.py
  [CRITICAL] Line XX: description of violation — suggested fix
  [WARNING]  Line XX: description of concern — suggested fix
  [OK] No violations found
```

Provide a summary at the end:
- Total files checked
- Critical violations (must fix)
- Warnings (should fix)
- Files clean
