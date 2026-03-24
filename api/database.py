"""SQLite persistence layer via aiosqlite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    scenario_path TEXT NOT NULL,
    seed INTEGER NOT NULL,
    max_ticks INTEGER NOT NULL,
    config_overrides TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','completed','failed','cancelled')),
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    events_json TEXT,
    snapshots_json TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    scenario_path TEXT NOT NULL,
    num_iterations INTEGER NOT NULL,
    base_seed INTEGER NOT NULL,
    max_ticks INTEGER NOT NULL,
    completed_iterations INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','completed','failed','cancelled')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metrics_json TEXT,
    error_message TEXT
);
"""


class Database:
    """Async SQLite database wrapper for run/batch persistence."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open connection and create tables."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        # Enable WAL mode + busy timeout for concurrent access
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        # Migrate: add Phase 35 map data columns if missing
        for col in ("terrain_json", "frames_json"):
            try:
                await self._conn.execute(f"ALTER TABLE runs ADD COLUMN {col} TEXT")
                await self._conn.commit()
            except Exception as exc:
                logger.debug("Migration column %s: %s", col, exc)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized — call initialize() first")
        return self._conn

    # ── Run CRUD ─────────────────────────────────────────────────────

    async def create_run(
        self,
        run_id: str,
        scenario_name: str,
        scenario_path: str,
        seed: int,
        max_ticks: int,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        await self.conn.execute(
            """INSERT INTO runs (id, scenario_name, scenario_path, seed,
               max_ticks, config_overrides, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                run_id,
                scenario_name,
                scenario_path,
                seed,
                max_ticks,
                json.dumps(config_overrides or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self.conn.commit()

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        *,
        started_at: str | None = None,
        completed_at: str | None = None,
        result_json: str | None = None,
        events_json: str | None = None,
        snapshots_json: str | None = None,
        error_message: str | None = None,
        terrain_json: str | None = None,
        frames_json: str | None = None,
    ) -> None:
        fields = ["status = ?"]
        values: list[Any] = [status]
        if started_at is not None:
            fields.append("started_at = ?")
            values.append(started_at)
        if completed_at is not None:
            fields.append("completed_at = ?")
            values.append(completed_at)
        if result_json is not None:
            fields.append("result_json = ?")
            values.append(result_json)
        if events_json is not None:
            fields.append("events_json = ?")
            values.append(events_json)
        if snapshots_json is not None:
            fields.append("snapshots_json = ?")
            values.append(snapshots_json)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if terrain_json is not None:
            fields.append("terrain_json = ?")
            values.append(terrain_json)
        if frames_json is not None:
            fields.append("frames_json = ?")
            values.append(frames_json)
        values.append(run_id)
        await self.conn.execute(
            f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
        await self.conn.commit()

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        scenario: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM runs"
        conditions: list[str] = []
        params: list[Any] = []
        if scenario:
            conditions.append("scenario_name = ?")
            params.append(scenario)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await self.conn.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def delete_run(self, run_id: str) -> bool:
        cursor = await self.conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def count_runs(self) -> int:
        cursor = await self.conn.execute("SELECT COUNT(*) FROM runs")
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Batch CRUD ───────────────────────────────────────────────────

    async def create_batch(
        self,
        batch_id: str,
        scenario_name: str,
        scenario_path: str,
        num_iterations: int,
        base_seed: int,
        max_ticks: int,
    ) -> None:
        await self.conn.execute(
            """INSERT INTO batches (id, scenario_name, scenario_path,
               num_iterations, base_seed, max_ticks, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                batch_id,
                scenario_name,
                scenario_path,
                num_iterations,
                base_seed,
                max_ticks,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await self.conn.commit()

    async def update_batch(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        completed_iterations: int | None = None,
        completed_at: str | None = None,
        metrics_json: str | None = None,
        error_message: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if completed_iterations is not None:
            fields.append("completed_iterations = ?")
            values.append(completed_iterations)
        if completed_at is not None:
            fields.append("completed_at = ?")
            values.append(completed_at)
        if metrics_json is not None:
            fields.append("metrics_json = ?")
            values.append(metrics_json)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if not fields:
            return
        values.append(batch_id)
        await self.conn.execute(
            f"UPDATE batches SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
        await self.conn.commit()

    async def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
