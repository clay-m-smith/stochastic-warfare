"""Grid-based contamination manager.

Tracks per-cell, per-agent airborne concentration and persistent ground deposit.
Grid convention matches :class:`Heightmap` — ``grid[0,0]`` = SW corner, row
increases northward, col increases eastward.  Agent grids are allocated lazily
(only when agent first released) to avoid memory waste.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.cbrn.events import (
    ContaminationClearedEvent,
    ContaminationDetectedEvent,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ContaminationConfig(BaseModel):
    """Configuration for the contamination manager."""

    enable_cbrn: bool = False
    decay_check_interval_s: float = 60.0
    min_concentration_mg_m3: float = 0.001
    max_agents_tracked: int = 8


# ---------------------------------------------------------------------------
# Contamination manager
# ---------------------------------------------------------------------------


class ContaminationManager:
    """Manages per-cell contamination grids for multiple CBRN agents."""

    def __init__(
        self,
        grid_shape: tuple[int, int],
        cell_size_m: float,
        origin_easting: float,
        origin_northing: float,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: ContaminationConfig | None = None,
    ) -> None:
        self._rows, self._cols = grid_shape
        self._cell_size = cell_size_m
        self._origin_e = origin_easting
        self._origin_n = origin_northing
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or ContaminationConfig()

        # Lazy per-agent grids: agent_id -> 2D numpy array
        self._airborne: dict[str, np.ndarray] = {}
        self._ground: dict[str, np.ndarray] = {}

        # Track which cells were previously contaminated (for cleared events)
        self._was_contaminated: dict[str, set[tuple[int, int]]] = {}

    # ── Grid helpers ──────────────────────────────────────────────────

    def enu_to_grid(self, pos: Position) -> tuple[int, int]:
        """Convert ENU position to grid (row, col).  Clamps to grid bounds."""
        col = int((pos.easting - self._origin_e) / self._cell_size)
        row = int((pos.northing - self._origin_n) / self._cell_size)
        row = max(0, min(row, self._rows - 1))
        col = max(0, min(col, self._cols - 1))
        return row, col

    def _ensure_grid(self, agent_id: str) -> None:
        """Lazily allocate grids for an agent."""
        if agent_id not in self._airborne:
            self._airborne[agent_id] = np.zeros(
                (self._rows, self._cols), dtype=np.float64
            )
            self._ground[agent_id] = np.zeros(
                (self._rows, self._cols), dtype=np.float64
            )
            self._was_contaminated[agent_id] = set()

    # ── Add contamination ─────────────────────────────────────────────

    def add_contamination(
        self, agent_id: str, row: int, col: int, concentration_mg_m3: float
    ) -> None:
        """Add airborne contamination to a specific cell."""
        self._ensure_grid(agent_id)
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._airborne[agent_id][row, col] += concentration_mg_m3

    def add_ground_deposit(
        self, agent_id: str, row: int, col: int, deposit_mg_m2: float
    ) -> None:
        """Add ground contamination deposit to a specific cell."""
        self._ensure_grid(agent_id)
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._ground[agent_id][row, col] += deposit_mg_m2

    # ── Query ─────────────────────────────────────────────────────────

    def concentration_at(self, agent_id: str, row: int, col: int) -> float:
        """Return airborne concentration (mg/m³) at a cell for one agent."""
        grid = self._airborne.get(agent_id)
        if grid is None:
            return 0.0
        if 0 <= row < self._rows and 0 <= col < self._cols:
            return float(grid[row, col])
        return 0.0

    def ground_deposit_at(self, agent_id: str, row: int, col: int) -> float:
        """Return ground deposit (mg/m²) at a cell for one agent."""
        grid = self._ground.get(agent_id)
        if grid is None:
            return 0.0
        if 0 <= row < self._rows and 0 <= col < self._cols:
            return float(grid[row, col])
        return 0.0

    def total_concentration_at_pos(self, pos: Position) -> dict[str, float]:
        """Return dict of agent_id -> concentration at a position."""
        row, col = self.enu_to_grid(pos)
        result: dict[str, float] = {}
        for agent_id, grid in self._airborne.items():
            c = float(grid[row, col])
            if c > self._config.min_concentration_mg_m3:
                result[agent_id] = c
        return result

    def is_contaminated(self, pos: Position) -> bool:
        """Check if a position has any contamination above threshold."""
        row, col = self.enu_to_grid(pos)
        for grid in self._airborne.values():
            if grid[row, col] > self._config.min_concentration_mg_m3:
                return True
        return False

    def contaminated_cells(self, agent_id: str) -> list[tuple[int, int]]:
        """Return list of (row, col) cells with above-threshold contamination."""
        grid = self._airborne.get(agent_id)
        if grid is None:
            return []
        mask = grid > self._config.min_concentration_mg_m3
        rows, cols = np.where(mask)
        return list(zip(rows.tolist(), cols.tolist()))

    # ── Decay & environmental effects ─────────────────────────────────

    def apply_decay(
        self,
        agent_id: str,
        agent_defn: Any,
        dt_s: float,
        temperature_c: float = 20.0,
        wind_speed_m_s: float = 2.0,
        precipitation_rate_mm_hr: float = 0.0,
        soil_type: str = "default",
    ) -> None:
        """Apply time-based decay, evaporation, rain washout, and soil absorption.

        Parameters
        ----------
        agent_defn:
            AgentDefinition with persistence_hours, evaporation_rate_per_c,
            rain_washout_rate, soil_absorption fields.
        """
        grid = self._airborne.get(agent_id)
        if grid is None:
            return

        dt_hr = dt_s / 3600.0

        # 1. Exponential half-life decay
        persistence_hours = getattr(agent_defn, "persistence_hours", 1.0)
        if persistence_hours > 0:
            half_life = persistence_hours
            decay_factor = 0.5 ** (dt_hr / half_life)
            grid *= decay_factor

        # 2. Temperature-dependent evaporation
        evap_rate = getattr(agent_defn, "evaporation_rate_per_c", 0.01)
        temp_excess = max(0.0, temperature_c - 15.0)
        evap_factor = 1.0 - evap_rate * temp_excess * dt_hr
        evap_factor = max(0.0, evap_factor)
        grid *= evap_factor

        # 3. Rain washout
        washout_rate = getattr(agent_defn, "rain_washout_rate", 0.1)
        if precipitation_rate_mm_hr > 0:
            washout_factor = 1.0 - washout_rate * precipitation_rate_mm_hr * dt_hr
            washout_factor = max(0.0, washout_factor)
            grid *= washout_factor

        # 4. Soil absorption (airborne → ground)
        absorption_map = getattr(agent_defn, "soil_absorption", {})
        abs_rate = absorption_map.get(soil_type, 0.0)
        if abs_rate > 0 and agent_id in self._ground:
            transfer = grid * abs_rate * dt_hr
            self._ground[agent_id] += transfer
            grid -= transfer
            np.clip(grid, 0.0, None, out=grid)

        # Zero out below threshold
        grid[grid < self._config.min_concentration_mg_m3] = 0.0

    def update(
        self,
        dt_s: float,
        dispersal_engine: Any = None,
        weather_conditions: Any = None,
        classification: Any = None,
        heightmap: Any = None,
        time_of_day: Any = None,
        agent_registry: Any = None,
        timestamp: Any = None,
    ) -> None:
        """Full update cycle: decay all agents, emit detection/cleared events."""
        temp_c = 20.0
        wind_speed = 2.0
        precip = 0.0

        if weather_conditions is not None:
            temp_c = getattr(weather_conditions, "temperature_c", 20.0)
            wind_speed = getattr(weather_conditions, "wind_speed_m_s", 2.0)
            precip = getattr(weather_conditions, "precipitation_rate_mm_hr", 0.0)

        for agent_id in list(self._airborne.keys()):
            agent_defn = None
            if agent_registry is not None:
                agent_defn = agent_registry.get(agent_id)
            if agent_defn is not None:
                self.apply_decay(agent_id, agent_defn, dt_s, temp_c, wind_speed, precip)

            # Emit detection events for newly contaminated cells
            if timestamp is not None:
                self._emit_contamination_events(agent_id, timestamp)

    def _emit_contamination_events(self, agent_id: str, timestamp: Any) -> None:
        """Emit detection/cleared events for state changes."""
        grid = self._airborne.get(agent_id)
        if grid is None:
            return

        threshold = self._config.min_concentration_mg_m3
        currently_contaminated: set[tuple[int, int]] = set()
        mask = grid > threshold
        rows, cols = np.where(mask)
        for r, c in zip(rows.tolist(), cols.tolist()):
            currently_contaminated.add((r, c))

        previously = self._was_contaminated.get(agent_id, set())

        # New contamination
        for r, c in currently_contaminated - previously:
            self._event_bus.publish(ContaminationDetectedEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                cell_row=r,
                cell_col=c,
                agent_id=agent_id,
                concentration_mg_m3=float(grid[r, c]),
            ))

        # Cleared contamination
        for r, c in previously - currently_contaminated:
            self._event_bus.publish(ContaminationClearedEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                cell_row=r,
                cell_col=c,
                agent_id=agent_id,
            ))

        self._was_contaminated[agent_id] = currently_contaminated

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "grid_shape": (self._rows, self._cols),
            "cell_size": self._cell_size,
            "origin_e": self._origin_e,
            "origin_n": self._origin_n,
            "airborne": {},
            "ground": {},
        }
        for aid, grid in self._airborne.items():
            state["airborne"][aid] = grid.tolist()
        for aid, grid in self._ground.items():
            state["ground"][aid] = grid.tolist()
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        self._airborne.clear()
        self._ground.clear()
        for aid, data in state.get("airborne", {}).items():
            self._airborne[aid] = np.array(data, dtype=np.float64)
        for aid, data in state.get("ground", {}).items():
            self._ground[aid] = np.array(data, dtype=np.float64)
