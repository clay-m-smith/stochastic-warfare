# Phase 76: API Robustness

**Status**: Complete
**Block**: 8 (Consequence Enforcement & Scenario Expansion)
**Tests**: 25 new (3 test files)

## Summary

Phase 76 addresses Block 8 exit criteria #7 (API schemas current) and #8 (API concurrency bugs fixed). It fixes 6 critical/high concurrency bugs, adds graceful shutdown, WAL mode, filesystem scan caching, request body limits, and health probe endpoints.

## What Was Built

### 76a: Concurrency Fixes

- **Batch semaphore**: `_execute_batch()` now acquires `self._semaphore` before each `run_in_executor` call, respecting the `max_concurrent` limit
- **Analysis semaphore**: Lazily-initialized `asyncio.Semaphore(2)` wraps `/analysis/compare` and `/analysis/sweep` endpoints
- **Per-client WebSocket multicast**: `_progress_queues` changed from `dict[str, Queue]` to `dict[str, list[Queue]]`. New `subscribe()`/`unsubscribe()` API replaces `get_progress_queue()`. All progress pushes iterate subscriber list. `QueueFull` on one subscriber doesn't block others.
- **Tempfile to thread pool**: `tempfile.mkdtemp()` in `/runs/from-config` now runs via `asyncio.to_thread()`

### 76b: Graceful Shutdown & Reliability

- **Graceful shutdown**: `RunManager.shutdown()` method sets all cancel flags, waits with timeout, cancels remaining tasks. Called from ASGI lifespan cleanup.
- **Database hardening**: WAL mode + `busy_timeout=5000` PRAGMAs in `initialize()`. Migration errors logged (not silently swallowed). `assert` replaced with `RuntimeError` in `.conn` property.
- **Scan caching**: `_ScanCache` class in `api/scenarios.py` with mtime-based invalidation. `scan_scenarios()` and `scan_units()` now cache results until directory mtime changes. `invalidate_cache()` for tests.

### 76c: Request Safety

- **Schema validation**: `Field(ge=1, le=1_000_000)` on `max_ticks` across all request schemas. `Field(ge=1, le=1_000)` on `num_iterations` (batch), `Field(ge=1, le=500)` on `num_iterations` (compare/sweep). `Field(max_length=50)` on sweep `values`. `_check_dict_depth()` validator on `config_overrides` and inline `config` (max depth 5, max 200 keys per level). `ConfigDict(str_max_length=100_000)` on all request schemas.
- **Health endpoints**: `/health/live` (instant 200, no external checks) and `/health/ready` (DB connectivity + cached scenario/unit counts). Existing `/health` preserved (now fast due to scan caching).
- **New response models**: `HealthLiveResponse`, `HealthReadyResponse`

## Files Modified

| File | Changes |
|------|---------|
| `api/schemas.py` | `ConfigDict`, `Field` constraints, `_check_dict_depth()` validator, `HealthLiveResponse`/`HealthReadyResponse` models |
| `api/database.py` | WAL mode, `busy_timeout=5000`, migration error logging, `assert` replaced with `RuntimeError` |
| `api/scenarios.py` | `_ScanCache` class, `invalidate_cache()`, cached `scan_scenarios()`/`scan_units()` |
| `api/run_manager.py` | Multicast queues (`subscribe()`/`unsubscribe()`), batch semaphore enforcement, `shutdown()` method |
| `api/routers/runs.py` | `subscribe()`/`unsubscribe()` in WebSocket handlers, `asyncio.to_thread()` for tempfile |
| `api/routers/analysis.py` | Analysis concurrency semaphore |
| `api/routers/meta.py` | `/health/live` + `/health/ready` endpoints |
| `api/main.py` | Graceful shutdown in lifespan cleanup |

## New Test Files

| File | Tests |
|------|-------|
| `tests/api/test_concurrency.py` | 11 |
| `tests/api/test_reliability.py` | 8 |
| `tests/api/test_request_safety.py` | 6 |
| **Total** | **25** |

## Design Decisions

1. **Multicast uses list of queues per run_id**: Simpler than a pub/sub pattern — no external dependencies, straightforward iteration over subscriber list. Each subscriber gets an independent queue.

2. **Analysis semaphore is independent from RunManager semaphore**: Analysis endpoints use a different thread pool and have different resource characteristics — separate rate limiting is appropriate.

3. **WAL mode safe on :memory: databases**: Returns `"memory"` with no side effects, so the test suite (which uses in-memory SQLite) is unaffected.

4. **No signal handlers needed**: uvicorn's ASGI lifespan handles SIGTERM/SIGINT cross-platform. The `shutdown()` method hooks into the lifespan cleanup phase.

5. **Scan cache uses directory mtime, not individual file mtimes**: A single `os.stat()` call per directory is fast and sufficient — any file add/remove/rename changes the directory's mtime. Good enough for invalidation without scanning individual files.

## Postmortem

### Scope
**On target.** All 3 substeps (concurrency, reliability, request safety) delivered. 25 tests cover the key behavioral changes.

### Integration
**Fully wired.** All concurrency fixes are in existing API paths — no new modules. WebSocket multicast is backward-compatible (single client still works). Health endpoints added to existing router. Scan caching is transparent to all callers.

### Quality
- Concurrency tests validate semaphore limits and multicast isolation
- Reliability tests verify WAL mode, shutdown behavior, and cache invalidation
- Request safety tests exercise field constraints and depth validation
- No behavioral changes to simulation engine — purely API layer

### Deficits
**0 new deficits.** API-layer changes only, no simulation engine impact.

### Performance
- Scan caching eliminates redundant filesystem walks on `/health` and scenario listing endpoints
- WAL mode improves concurrent read performance under write load
- 25 new tests run in <1s. No regression suite performance impact.
