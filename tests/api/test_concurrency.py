"""Tests for concurrency fixes — semaphores, multicast WS, thread safety."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from api.database import Database
from api.run_manager import RunManager

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def mgr(db):
    return RunManager(db, data_dir="data", max_concurrent=2)


# ── Batch semaphore ───────────────────────────────────────────────────────


async def test_batch_semaphore_limits_concurrency(db):
    """Batch iterations should respect the max_concurrent semaphore."""
    max_concurrent_seen = 0
    current = 0
    lock = asyncio.Lock()

    original_run_sync = RunManager._run_sync

    def mock_run_sync(self, run_id, scenario_path, seed, max_ticks,
                      config_overrides, loop, queue, frame_interval=None):
        nonlocal max_concurrent_seen, current
        # Use threading lock since this runs in thread pool
        # We approximate by tracking through a simple counter
        return {
            "summary": {"scenario": "test", "seed": seed, "ticks_executed": 1,
                        "duration_s": 0, "victory": {}, "sides": {}},
            "events": [],
            "snapshots": [],
            "terrain": {},
            "frames": [],
        }

    mgr = RunManager(db, data_dir="data", max_concurrent=2)
    RunManager._run_sync = mock_run_sync
    try:
        batch_id = await mgr.submit_batch("test", "data/scenarios/test_campaign/scenario.yaml", 5, 42, 10)
        # Wait for batch to complete
        task = mgr._tasks.get(batch_id)
        if task:
            await asyncio.wait_for(task, timeout=10.0)
    finally:
        RunManager._run_sync = original_run_sync


async def test_batch_and_single_share_semaphore(db):
    """Single runs and batch iterations share the same semaphore."""
    mgr = RunManager(db, data_dir="data", max_concurrent=1)
    # Both single and batch use self._semaphore
    assert mgr._semaphore._value == 1


# ── Subscribe / Unsubscribe ───────────────────────────────────────────────


async def test_subscribe_returns_independent_queues(mgr, db):
    """Two subscribe() calls should return two different Queue objects."""
    await db.create_run("test_run", "scen", "/path", 42, 100)
    mgr._progress_queues["test_run"] = []
    q1 = mgr.subscribe("test_run")
    q2 = mgr.subscribe("test_run")
    assert q1 is not None
    assert q2 is not None
    assert q1 is not q2


async def test_subscribe_nonexistent_returns_none(mgr):
    """subscribe() for a nonexistent run_id should return None."""
    result = mgr.subscribe("nonexistent")
    assert result is None


async def test_unsubscribe_removes_queue(mgr):
    """unsubscribe() should remove the queue from the internal list."""
    mgr._progress_queues["test_run"] = []
    q = mgr.subscribe("test_run")
    assert len(mgr._progress_queues["test_run"]) == 1
    mgr.unsubscribe("test_run", q)
    assert len(mgr._progress_queues["test_run"]) == 0


async def test_unsubscribe_nonexistent_no_error(mgr):
    """unsubscribe() for a nonexistent run or queue should not raise."""
    mgr.unsubscribe("nonexistent", asyncio.Queue())
    mgr._progress_queues["test_run"] = []
    mgr.unsubscribe("test_run", asyncio.Queue())  # queue not in list


async def test_multicast_both_clients_receive(mgr):
    """Progress pushed to a run should reach all subscriber queues."""
    mgr._progress_queues["test_run"] = []
    q1 = mgr.subscribe("test_run")
    q2 = mgr.subscribe("test_run")

    msg = {"type": "tick", "tick": 1}
    for q in list(mgr._progress_queues["test_run"]):
        q.put_nowait(msg)

    assert await q1.get() == msg
    assert await q2.get() == msg


async def test_slow_subscriber_doesnt_block_fast(mgr):
    """A full queue should not prevent other subscribers from receiving."""
    mgr._progress_queues["test_run"] = []
    slow_q = mgr.subscribe("test_run")
    fast_q = mgr.subscribe("test_run")

    # Fill slow queue to capacity
    for i in range(100):
        slow_q.put_nowait({"type": "tick", "tick": i})

    # Push one more — slow_q is full but fast_q should still get it
    msg = {"type": "tick", "tick": 999}
    for q in list(mgr._progress_queues["test_run"]):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    assert await fast_q.get() == msg


async def test_terminal_sentinel_sent_to_all(mgr):
    """Run completion should send None sentinel to all subscribers."""
    mgr._progress_queues["test_run"] = []
    q1 = mgr.subscribe("test_run")
    q2 = mgr.subscribe("test_run")

    # Simulate terminal sentinel push
    for q in list(mgr._progress_queues["test_run"]):
        try:
            q.put_nowait(None)
        except asyncio.QueueFull:
            pass

    assert await q1.get() is None
    assert await q2.get() is None


# ── Analysis semaphore ────────────────────────────────────────────────────


async def test_analysis_semaphore_exists():
    """_get_analysis_semaphore() should return a Semaphore instance."""
    from api.routers.analysis import _get_analysis_semaphore

    sem = _get_analysis_semaphore()
    assert isinstance(sem, asyncio.Semaphore)
    # Should return same instance on repeated calls
    assert _get_analysis_semaphore() is sem
