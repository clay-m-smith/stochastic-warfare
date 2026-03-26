"""Structure-of-Arrays (SoA) data layer for hot-path unit data.

Phase 88: Provides contiguous NumPy arrays for positions, health, fuel,
morale, and operational status — enabling vectorized distance computation,
range checks, and batch kernel consumption.  Built as a read-mostly
snapshot at tick start; Unit objects remain the source of truth.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial.distance import cdist

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus

logger = get_logger(__name__)


class UnitArrays:
    """NumPy SoA for hot-path unit data.

    All arrays are indexed by a single flat unit index.  The mapping
    from flat index → ``entity_id`` is stored in ``unit_ids``.

    Attributes
    ----------
    positions : np.ndarray
        Shape ``(n, 2)`` float64 — easting, northing.
    health : np.ndarray
        Shape ``(n,)`` float64 — fraction of effective personnel.
    fuel : np.ndarray
        Shape ``(n,)`` float64 — ``fuel_remaining`` (0.0–1.0).
    morale_state : np.ndarray
        Shape ``(n,)`` int8 — ``MoraleState`` ordinal.
    side_indices : np.ndarray
        Shape ``(n,)`` int8 — integer encoding of side name.
    operational : np.ndarray
        Shape ``(n,)`` bool — ``status == ACTIVE``.
    max_range : np.ndarray
        Shape ``(n,)`` float64 — best weapon ``max_range_m``.
    unit_ids : list[str]
        Entity IDs in flat-index order.
    side_names : list[str]
        Ordered side name list (index → name).
    """

    __slots__ = (
        "positions",
        "health",
        "fuel",
        "morale_state",
        "side_indices",
        "operational",
        "max_range",
        "unit_ids",
        "side_names",
    )

    def __init__(
        self,
        positions: np.ndarray,
        health: np.ndarray,
        fuel: np.ndarray,
        morale_state: np.ndarray,
        side_indices: np.ndarray,
        operational: np.ndarray,
        max_range: np.ndarray,
        unit_ids: list[str],
        side_names: list[str],
    ) -> None:
        self.positions = positions
        self.health = health
        self.fuel = fuel
        self.morale_state = morale_state
        self.side_indices = side_indices
        self.operational = operational
        self.max_range = max_range
        self.unit_ids = unit_ids
        self.side_names = side_names

    @classmethod
    def from_units(
        cls,
        units_by_side: dict[str, list[Unit]],
        *,
        morale_states: dict[str, Any] | None = None,
        unit_weapons: dict[str, list[Any]] | None = None,
    ) -> UnitArrays:
        """Build SoA arrays from Unit objects.

        Parameters
        ----------
        units_by_side:
            Side name → list of Unit objects.
        morale_states:
            Optional entity_id → MoraleState int mapping (from ctx).
        unit_weapons:
            Optional entity_id → list of (weapon_inst, ammo_inst) tuples.
        """
        side_names = list(units_by_side.keys())
        side_map = {name: idx for idx, name in enumerate(side_names)}

        # Flatten all units with consistent ordering
        all_units: list[Unit] = []
        all_side_idx: list[int] = []
        for side_name, units in units_by_side.items():
            idx = side_map[side_name]
            for u in units:
                all_units.append(u)
                all_side_idx.append(idx)

        n = len(all_units)
        if n == 0:
            return cls(
                positions=np.empty((0, 2), dtype=np.float64),
                health=np.empty(0, dtype=np.float64),
                fuel=np.empty(0, dtype=np.float64),
                morale_state=np.empty(0, dtype=np.int8),
                side_indices=np.empty(0, dtype=np.int8),
                operational=np.empty(0, dtype=bool),
                max_range=np.empty(0, dtype=np.float64),
                unit_ids=[],
                side_names=side_names,
            )

        positions = np.empty((n, 2), dtype=np.float64)
        health = np.empty(n, dtype=np.float64)
        fuel = np.empty(n, dtype=np.float64)
        morale_arr = np.empty(n, dtype=np.int8)
        op = np.empty(n, dtype=bool)
        max_rng = np.empty(n, dtype=np.float64)
        unit_ids: list[str] = []

        morale_dict = morale_states or {}
        weapons_dict = unit_weapons or {}

        for i, u in enumerate(all_units):
            positions[i, 0] = u.position.easting
            positions[i, 1] = u.position.northing

            # Health: fraction of effective personnel
            if u.personnel:
                health[i] = sum(
                    1 for p in u.personnel if p.is_effective()
                ) / len(u.personnel)
            else:
                health[i] = 1.0

            fuel[i] = getattr(u, "fuel_remaining", 1.0)
            morale_arr[i] = int(morale_dict.get(u.entity_id, 0))
            op[i] = u.status == UnitStatus.ACTIVE

            # Max weapon range
            wpns = weapons_dict.get(u.entity_id, [])
            if wpns:
                max_rng[i] = max(
                    (getattr(getattr(w[0], "definition", w[0]), "max_range_m", 0.0)
                     for w in wpns),
                    default=0.0,
                )
            else:
                max_rng[i] = 0.0

            unit_ids.append(u.entity_id)

        return cls(
            positions=positions,
            health=health,
            fuel=fuel,
            morale_state=morale_arr,
            side_indices=np.array(all_side_idx, dtype=np.int8),
            operational=op,
            max_range=max_rng,
            unit_ids=unit_ids,
            side_names=side_names,
        )

    # -- Filtering -----------------------------------------------------------

    def side_mask(self, side: str) -> np.ndarray:
        """Return boolean mask for units belonging to *side*."""
        idx = self.side_names.index(side) if side in self.side_names else -1
        return self.side_indices == idx

    def enemy_mask(self, side: str) -> np.ndarray:
        """Return boolean mask for units NOT on *side* that are operational."""
        return (~self.side_mask(side)) & self.operational

    # -- Position helpers ----------------------------------------------------

    def get_enemy_positions(self, side: str) -> np.ndarray:
        """Return ``(m, 2)`` position array for operational enemies of *side*.

        Drop-in replacement for the position arrays built by
        ``BattleManager._build_enemy_data()``.
        """
        mask = self.enemy_mask(side)
        if not np.any(mask):
            return np.empty((0, 2), dtype=np.float64)
        return self.positions[mask]

    def get_side_positions(self, side: str) -> np.ndarray:
        """Return ``(m, 2)`` position array for all units on *side*."""
        mask = self.side_mask(side)
        return self.positions[mask]

    def get_active_enemy_indices(self, side: str) -> np.ndarray:
        """Return flat indices of operational enemies of *side*."""
        mask = self.enemy_mask(side)
        return np.where(mask)[0]

    # -- Distance computation ------------------------------------------------

    def distance_matrix(self, side_a: str, side_b: str) -> np.ndarray:
        """Compute pairwise distance matrix between two sides.

        Returns shape ``(n_a, n_b)`` float64 array using
        ``scipy.spatial.distance.cdist``.
        """
        pos_a = self.get_side_positions(side_a)
        pos_b = self.get_side_positions(side_b)
        if pos_a.shape[0] == 0 or pos_b.shape[0] == 0:
            return np.empty((pos_a.shape[0], pos_b.shape[0]), dtype=np.float64)
        return cdist(pos_a, pos_b, metric="euclidean")

    # -- Target position array for FOW --------------------------------------

    def target_positions_array(
        self,
        side: str,
    ) -> np.ndarray:
        """Return ``(m, 2)`` positions of all operational enemies.

        Identical to ``get_enemy_positions`` but named to clarify FOW
        usage — these are the *targets* that *side* is trying to detect.
        """
        return self.get_enemy_positions(side)

    # -- Sync back -----------------------------------------------------------

    def sync_positions_to_units(
        self,
        units_by_side: dict[str, list[Unit]],
    ) -> None:
        """Write SoA position array back to Unit objects.

        Iterates the same order as ``from_units`` — side order then unit
        order within each side.
        """
        i = 0
        for units in units_by_side.values():
            for u in units:
                if i < self.positions.shape[0]:
                    e = float(self.positions[i, 0])
                    n_ = float(self.positions[i, 1])
                    alt = u.position.altitude
                    object.__setattr__(u, "position", Position(e, n_, alt))
                i += 1

    @property
    def n(self) -> int:
        """Number of units in the arrays."""
        return self.positions.shape[0]
