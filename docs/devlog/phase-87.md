# Phase 87: Expanded Numba JIT

**Block**: 9 (Performance at Scale)
**Status**: Complete
**Tests**: 40 (18 detection + 11 engagement + 11 morale)

## Overview

Extracts pure-math inner kernels from detection, combat, and morale hot paths into module-level functions decorated with `@optional_jit`. When Numba is installed, these compile to native machine code; without Numba, they run as plain Python with zero behavioral change. All kernels produce identical results to the original methods.

## What Was Built

### 87a: Detection SNR Kernels (`detection/detection.py`)

5 JIT-compilable kernel functions extracted from `DetectionEngine` static methods:

- **`_snr_visual_kernel`**: Beer-Lambert atmospheric extinction, pure scalar math
- **`_snr_thermal_kernel`**: IR atmospheric loss model, pure scalar math
- **`_snr_radar_kernel`**: Full radar range equation (Pt, Gt², λ², σ, R⁴), constants inlined
- **`_snr_acoustic_kernel`**: Signal excess (SE = SL - TL - NL + DI), sentinel `-1.0` for no TL override
- **`_detection_probability_kernel`**: Uses `math.erfc` (Numba-compatible) instead of `scipy.special.erfc`

Static methods now delegate to kernels: extract primitive params from sensor objects, call kernel, return result.

### 87b: Engagement Math Kernels

- **`_hit_probability_kernel`** (`combat/hit_probability.py`): 20-param pure-scalar function combining dispersion, crew skill, motion penalties, visibility, posture, uncertainty, terrain cover, elevation, condition floor, and clamping. `compute_phit` extracts primitives from weapon/config objects, calls kernel, then builds diagnostic `modifiers` dict separately.

- **`_penetration_kernel`** (`combat/damage.py`): DeMarre penetration with obliquity, ricochet check, range-dependent velocity decay, armor effectiveness. Returns `(penetrated, pen_mm, armor_eff_mm, margin_mm)` tuple. `compute_penetration` handles armor type enum lookup, then delegates.

### 87c: Morale Transition Kernels (`morale/state.py`)

- **`_transition_matrix_kernel`**: Discrete Markov transition matrix (5×5). All `MoraleConfig` fields passed as primitive floats. `leadership_present_f` as `1.0`/`0.0` (Numba cannot handle bool in all contexts). Uses manual `min`/`max` clamps instead of `np.clip` for Numba scalar compatibility.

- **`_continuous_transition_kernel`**: Continuous-time variant using `math.exp(-λ·dt)`. Same parameter pattern.

Both wired into `compute_transition_matrix` and `compute_continuous_transition_probs` — existing cache logic preserved.

## Key Design Decisions

1. **Extract-and-delegate pattern**: Kernels are pure-math module-level functions; existing methods remain as the public API, handling object access and result construction. Same pattern as `ballistics.py`.

2. **`math.erfc` over `scipy.special.erfc`**: Standard library `math.erfc` is supported by Numba nopython mode and produces identical results. Scipy import retained for `false_alarm_probability` and other consumers.

3. **Sentinel for None params**: `_snr_acoustic_kernel` uses `-1.0` for "no transmission loss override" since Numba cannot handle `None`. Wrapper converts `None` → `-1.0`.

4. **Manual clamps in kernels**: `max(lo, min(hi, v))` pattern instead of `np.clip` for scalar values — guaranteed float return in Numba.

5. **No new `enable_*` flags**: JIT is transparent — identical results, just faster when Numba is installed.

6. **Modifiers dict outside JIT path**: `compute_phit` builds the diagnostic `modifiers` dict in Python after the kernel call — dicts are not JIT-compatible.

7. **Batch morale deferred**: The batch morale kernel (processing all units on a side at once) requires SoA data layout from Phase 88. Scalar kernels still provide meaningful speedup per-call.

## Files Changed

### Modified Source (5)
- `stochastic_warfare/detection/detection.py` — 5 JIT kernels + delegation wiring
- `stochastic_warfare/combat/hit_probability.py` — 1 JIT kernel + delegation wiring
- `stochastic_warfare/combat/damage.py` — 1 JIT kernel + delegation wiring
- `stochastic_warfare/morale/state.py` — 2 JIT kernels + delegation wiring + `import math`

### New Test Files (3)
- `tests/unit/test_phase87_detection_jit.py` — 18 tests
- `tests/unit/test_phase87_engagement_jit.py` — 11 tests
- `tests/unit/test_phase87_morale_jit.py` — 11 tests

## Accepted Limitations

- **Batch detection sweep deferred**: Per-target loop in `fog_of_war.py` accesses Python objects; vectorization requires SoA data layer (Phase 88).
- **Batch morale update deferred**: Same dependency on SoA for array-based processing.
- **`@guvectorize` / `prange` parallelism deferred**: Phase 89 (per-side threading).
- **First-call JIT warmup**: ~100-500ms per function on first invocation with Numba; `cache=True` avoids this on subsequent process starts.
- **Constants inlined in radar kernel**: Module-level constants (`_FOUR_PI_CUBED`, etc.) not accessible in Numba nopython mode; values inlined in kernel body.
