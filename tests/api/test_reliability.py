"""Tests for reliability improvements — WAL, busy timeout, cache, shutdown."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
import pytest_asyncio

from api.database import Database
from api.run_manager import RunManager

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


# ── Database hardening ────────────────────────────────────────────────────


async def test_wal_mode_enabled():
    """File-backed DB should have WAL journal mode."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        db = Database(tmp.name)
        await db.initialize()
        cursor = await db.conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"
        await db.close()
    finally:
        os.unlink(tmp.name)
        # WAL creates companion files
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except FileNotFoundError:
                pass


async def test_busy_timeout_set():
    """File-backed DB should have busy_timeout=5000."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        db = Database(tmp.name)
        await db.initialize()
        cursor = await db.conn.execute("PRAGMA busy_timeout")
        row = await cursor.fetchone()
        assert row[0] == 5000
        await db.close()
    finally:
        os.unlink(tmp.name)
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except FileNotFoundError:
                pass


async def test_double_init_no_error():
    """Calling initialize() twice on same DB should not raise."""
    db = Database(":memory:")
    await db.initialize()
    await db.initialize()  # Should not raise
    await db.close()


async def test_conn_raises_before_init():
    """Accessing .conn before initialize() should raise RuntimeError."""
    db = Database(":memory:")
    with pytest.raises(RuntimeError, match="Database not initialized"):
        _ = db.conn


# ── Scan cache ────────────────────────────────────────────────────────────


async def test_scenario_cache_same_object():
    """Two scan_scenarios() calls should return the same list object."""
    from pathlib import Path
    from api.scenarios import invalidate_cache, scan_scenarios

    invalidate_cache()
    data_dir = Path("data")
    result1 = scan_scenarios(data_dir)
    result2 = scan_scenarios(data_dir)
    assert result1 is result2


async def test_scenario_cache_invalidates():
    """Cache should invalidate when invalidate_cache() is called."""
    from pathlib import Path
    from api.scenarios import invalidate_cache, scan_scenarios

    invalidate_cache()
    data_dir = Path("data")
    result1 = scan_scenarios(data_dir)
    invalidate_cache()
    result2 = scan_scenarios(data_dir)
    assert result1 is not result2


async def test_unit_cache_same_object():
    """Two scan_units() calls should return the same list object."""
    from pathlib import Path
    from api.scenarios import invalidate_cache, scan_units

    invalidate_cache()
    data_dir = Path("data")
    result1 = scan_units(data_dir)
    result2 = scan_units(data_dir)
    assert result1 is result2


# ── Shutdown ──────────────────────────────────────────────────────────────


async def test_shutdown_cancels_tasks():
    """shutdown() should cancel all running tasks."""
    db = Database(":memory:")
    await db.initialize()
    mgr = RunManager(db, data_dir="data", max_concurrent=4)

    # Create a mock long-running task
    async def slow_task():
        await asyncio.sleep(60)

    task = asyncio.create_task(slow_task())
    mgr._tasks["fake_run"] = task
    mgr._cancel_flags["fake_run"] = False

    await mgr.shutdown(timeout=1.0)
    assert task.cancelled() or task.done()
    await db.close()
