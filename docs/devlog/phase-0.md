# Phase 0: Project Scaffolding

**Status**: Complete
**Date**: 2026-02-28

---

## Summary

Established the foundational infrastructure that every subsequent phase builds on: package structure, build system, core types, PRNG discipline, simulation clock, event bus, config/checkpoint system, coordinate transforms, and a minimal entity stub.

## What Was Built

### Package & Build (Step 1)
- `pyproject.toml` — PEP 621, setuptools backend, Python >=3.11
- Dependencies: numpy, scipy, pydantic, pyproj, pyyaml
- Dev deps: pytest, pytest-cov, matplotlib
- **Environment**: uv-managed venv (`.venv/`), not global install

### Core Types (Step 2) — `core/types.py`
- `Position` (ENU NamedTuple), `GeodeticPosition` (WGS-84 NamedTuple)
- `ModuleId` (str enum, 10 subsystems), `TickResolution` enum
- Semantic type aliases: `Meters`, `Seconds`, `Degrees`, `Radians`, `SimulationTime`
- Physical constants: speed of light, standard gravity, Earth mean radius, ISA lapse rate

### Logging (Step 3) — `core/logging.py`
- `get_logger(module_name)` → namespaced under `stochastic_warfare.*`
- `configure_logging()` — console + optional file handler, per-module level overrides
- Format: `[%(asctime)s] %(name)s %(levelname)s: %(message)s`

### RNG Manager (Step 4) — `core/rng.py` *(critical)*
- `RNGManager(master_seed)` — single source of all randomness
- `numpy.random.SeedSequence(master_seed).spawn(N)` → one `PCG64` Generator per `ModuleId`
- Full state capture/restore for checkpointing (`get_state()` / `set_state()`)
- `reset(seed)` for re-initialization
- No global instance — explicit passing

### Simulation Clock (Step 5) — `core/clock.py` *(critical)*
- Calendar-aware UTC datetime tracking
- Julian Date via Meeus Ch. 7 formula (verified against J2000.0 epoch)
- Calendar queries: `day_of_year`, `month`, `year`, `hour_utc`
- Variable tick resolution via `set_tick_duration()`
- State save/restore for checkpointing

### Event Bus (Step 6) — `core/events.py`
- Typed pub-sub: `subscribe(event_type, handler, priority)`
- Synchronous dispatch, priority ordering (lower = higher priority, stable sort)
- Inheritance support: subscribing to `Event` base receives all derived events
- `unsubscribe()`, `clear()`

### Config & Checkpoint (Step 7) — `core/config.py`, `core/checkpoint.py`
- YAML loading via pyyaml, validation via pydantic `BaseModel`
- `ScenarioConfig`: name, start_time (UTC-validated), duration, master_seed, tick_duration
- `CheckpointManager`: modules register state providers, creates/restores pickle-serialized snapshots
- Checkpoint format: `{version, clock, rng, modules}`

### Coordinates (Step 8) — `coordinates/transforms.py`, `coordinates/spatial.py`
- `ScenarioProjection(origin_lat, origin_lon)` — wraps pyproj for geodetic ↔ UTM ↔ ENU
- ENU = local tangent plane, origin maps to (0, 0, 0)
- Spatial: `distance()`, `distance_2d()`, `bearing()`, `point_at()`
- Round-trip tested at multiple global locations (< 1e-6 degree error)

### Entity Stub (Step 9) — `entities/base.py`
- Minimal `Entity` dataclass: `entity_id`, `position`
- `get_state()` / `set_state()` for checkpointing
- Deliberately skeletal — full hierarchy is Phase 2

## Design Decisions

1. **uv over pip** — Faster dependency resolution, proper venv isolation. All commands run via `source .venv/Scripts/activate`.
2. **ModuleId as str enum** — Allows use as both dict keys and human-readable serialization keys in checkpoint dicts.
3. **No global singletons** — RNGManager, EventBus, Clock are all explicitly instantiated and passed. Keeps testing clean and avoids hidden state.
4. **Pickle for checkpoints** — Simplest format that natively handles numpy bit_generator state dicts. Can be swapped later if needed (msgpack, etc.).
5. **Julian Date formula** — Used Meeus Ch. 7 (Gregorian calendar only). Validated against J2000.0 epoch (2451545.0). This feeds directly into the future astronomy/environment module.
6. **ENU via UTM offset** — Rather than a full ECEF→ENU rotation, we use UTM projection centered on origin. Accurate to ~1mm over battlefield scales, avoids complexity of geodetic math for the tangent plane.

## Deviations from Plan

- **Event bus `unsubscribe`**: Original used `is` identity check for handler removal. Changed to `==` equality because Python bound methods (e.g., `list.append`) create new objects on each access, so `is` comparison silently fails to remove them.

## Issues & Fixes

| Issue | Resolution |
|-------|-----------|
| `unsubscribe` silently failed for bound methods | Changed `h is not handler` → `h != handler` in list comprehension |
| pytest exit code 5 on empty test suite | Expected behavior — "no tests collected" is not an error |

## Open Questions

- **Checkpoint format longevity**: Pickle is fragile across numpy version upgrades. May need a more stable serialization for long-term save files. Not urgent for development.
- **Cross-UTM-zone coordinates**: `ScenarioProjection` currently uses a single UTM zone. Scenarios spanning zone boundaries will need handling (Phase 1+ when terrain loading is implemented).

## Test Coverage

97 tests total, all passing:
- 14 types, 9 logging, 10 RNG, 16 clock, 9 events, 7 config, 5 checkpoint, 9 transforms, 12 spatial, 4 entity base
- 2 integration tests (full lifecycle + determinism verification)

## Lessons Learned

- Bound method identity in Python is a recurring gotcha — always use `==` not `is` for callable comparison.
- uv is significantly faster than pip for installs (~3s vs ~15s for this dependency set).
