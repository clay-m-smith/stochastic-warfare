"""WW1 gas warfare — delivery adapter wrapping the CBRN pipeline.

Handles WW1-specific gas delivery mechanics (cylinder release, artillery
shells, Livens projectors) and gas mask → MOPP level mapping.  All
dispersal, contamination, and casualty effects are delegated to the
existing :mod:`cbrn` pipeline.
"""

from __future__ import annotations

import enum
import math
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GasDeliveryMethod(enum.IntEnum):
    """WW1 gas delivery methods."""

    CYLINDER_RELEASE = 0
    ARTILLERY_SHELL = 1
    PROJECTOR = 2


class GasMaskType(enum.IntEnum):
    """WW1 gas protection types, mapped to MOPP levels."""

    NONE = 0          # No protection → MOPP 0
    IMPROVISED_CLOTH = 1   # Wet cloth → MOPP 1
    PH_HELMET = 2     # Phenate-hexamine hood → MOPP 2
    SMALL_BOX_RESPIRATOR = 3  # SBR → MOPP 3


# Mapping from WW1 gas mask type to MOPP level
_MASK_TO_MOPP: dict[GasMaskType, int] = {
    GasMaskType.NONE: 0,
    GasMaskType.IMPROVISED_CLOTH: 1,
    GasMaskType.PH_HELMET: 2,
    GasMaskType.SMALL_BOX_RESPIRATOR: 3,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class GasWarfareConfig(BaseModel):
    """Configuration for WW1 gas warfare delivery."""

    cylinder_release_duration_s: float = 300.0
    """Duration of a cylinder release (continuous cloud generation)."""

    cylinder_mass_per_m_front_kg: float = 20.0
    """Mass of agent released per metre of front."""

    min_wind_speed_mps: float = 1.0
    """Minimum wind speed for cylinder release (too calm = settles locally)."""

    max_wind_speed_mps: float = 6.0
    """Maximum wind speed for cylinder release (too fast = disperses)."""

    shell_gas_mass_kg: float = 1.5
    """Mass of agent per gas shell."""

    projector_gas_mass_kg: float = 14.0
    """Mass of agent per Livens projector drum."""

    mask_don_time_s: float = 10.0
    """Time to don gas mask (units are unprotected during this interval)."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GasWarfareEngine:
    """WW1 gas warfare delivery engine.

    Wraps the CBRN pipeline with WW1-specific delivery methods.

    Parameters
    ----------
    config:
        Gas warfare configuration.
    cbrn_engine:
        The main CBRN engine for ``release_agent()`` calls.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: GasWarfareConfig | None = None,
        cbrn_engine: Any = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or GasWarfareConfig()
        self._cbrn = cbrn_engine
        self._rng = rng or np.random.default_rng(42)
        self._unit_masks: dict[str, GasMaskType] = {}
        self._release_ids: list[str] = []

    def check_wind_favorable(
        self,
        wind_speed_mps: float,
        wind_dir_deg: float,
        target_bearing_deg: float,
    ) -> bool:
        """Check if wind conditions are favorable for cylinder release.

        Wind must be within speed limits and blowing roughly toward
        the target (within 60 degrees).

        Parameters
        ----------
        wind_speed_mps:
            Wind speed in m/s.
        wind_dir_deg:
            Wind direction (meteorological: direction wind blows FROM).
        target_bearing_deg:
            Bearing from release point to target.

        Returns
        -------
        True if conditions favor gas release.
        """
        cfg = self._config
        if wind_speed_mps < cfg.min_wind_speed_mps:
            return False
        if wind_speed_mps > cfg.max_wind_speed_mps:
            return False

        # Wind blows FROM wind_dir, so gas goes in wind_dir + 180
        gas_travel_dir = (wind_dir_deg + 180.0) % 360.0
        diff = abs(gas_travel_dir - target_bearing_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        return diff <= 60.0

    def execute_cylinder_release(
        self,
        agent_id: str,
        front_start: tuple[float, float],
        front_end: tuple[float, float],
        wind_speed_mps: float = 2.0,
        num_release_points: int = 5,
        timestamp: Any = None,
    ) -> list[str]:
        """Execute a cylinder gas release along a front.

        Creates multiple puffs along the front line via the CBRN engine.

        Parameters
        ----------
        agent_id:
            CBRN agent identifier (e.g. ``"chlorine"``).
        front_start, front_end:
            (easting, northing) endpoints of the release front.
        wind_speed_mps:
            Wind speed for dispersal.
        num_release_points:
            Number of release points along the front.
        timestamp:
            Optional timestamp for event publishing.

        Returns
        -------
        List of puff IDs created.
        """
        if self._cbrn is None:
            logger.warning("No CBRN engine — cylinder release skipped")
            return []

        cfg = self._config
        front_length = math.sqrt(
            (front_end[0] - front_start[0]) ** 2
            + (front_end[1] - front_start[1]) ** 2
        )
        total_mass = front_length * cfg.cylinder_mass_per_m_front_kg
        mass_per_point = total_mass / max(num_release_points, 1)

        puff_ids: list[str] = []
        for i in range(num_release_points):
            t = (i + 0.5) / max(num_release_points, 1)
            e = front_start[0] + t * (front_end[0] - front_start[0])
            n = front_start[1] + t * (front_end[1] - front_start[1])
            pos = Position(e, n, 0.0)
            pid = self._cbrn.release_agent(
                agent_id=agent_id,
                position=pos,
                quantity_kg=mass_per_point,
                delivery_method="cylinder",
                timestamp=timestamp,
            )
            puff_ids.append(pid)

        self._release_ids.extend(puff_ids)
        logger.info(
            "Cylinder release: %s, %.0fm front, %.0fkg total, %d puffs",
            agent_id, front_length, total_mass, len(puff_ids),
        )
        return puff_ids

    def execute_gas_bombardment(
        self,
        agent_id: str,
        target_easting: float,
        target_northing: float,
        num_shells: int,
        spread_m: float = 100.0,
        timestamp: Any = None,
    ) -> list[str]:
        """Execute a gas shell bombardment.

        Each shell creates a puff at a randomised position around the target.

        Parameters
        ----------
        agent_id:
            CBRN agent identifier.
        target_easting, target_northing:
            Target centre position.
        num_shells:
            Number of gas shells fired.
        spread_m:
            1-sigma spread around target centre.
        timestamp:
            Optional timestamp.

        Returns
        -------
        List of puff IDs created.
        """
        if self._cbrn is None:
            logger.warning("No CBRN engine — gas bombardment skipped")
            return []

        cfg = self._config
        puff_ids: list[str] = []
        for _ in range(num_shells):
            e = target_easting + self._rng.normal(0, spread_m)
            n = target_northing + self._rng.normal(0, spread_m)
            pos = Position(e, n, 0.0)
            pid = self._cbrn.release_agent(
                agent_id=agent_id,
                position=pos,
                quantity_kg=cfg.shell_gas_mass_kg,
                delivery_method="shell",
                timestamp=timestamp,
            )
            puff_ids.append(pid)

        self._release_ids.extend(puff_ids)
        logger.info(
            "Gas bombardment: %s, %d shells at (%.0f, %.0f)",
            agent_id, num_shells, target_easting, target_northing,
        )
        return puff_ids

    def execute_projector_salvo(
        self,
        agent_id: str,
        target_easting: float,
        target_northing: float,
        num_projectors: int,
        spread_m: float = 50.0,
        timestamp: Any = None,
    ) -> list[str]:
        """Execute a Livens projector salvo.

        Parameters
        ----------
        agent_id:
            CBRN agent identifier.
        target_easting, target_northing:
            Target centre position.
        num_projectors:
            Number of projector drums fired.
        spread_m:
            1-sigma spread.
        timestamp:
            Optional timestamp.

        Returns
        -------
        List of puff IDs created.
        """
        if self._cbrn is None:
            logger.warning("No CBRN engine — projector salvo skipped")
            return []

        cfg = self._config
        puff_ids: list[str] = []
        for _ in range(num_projectors):
            e = target_easting + self._rng.normal(0, spread_m)
            n = target_northing + self._rng.normal(0, spread_m)
            pos = Position(e, n, 0.0)
            pid = self._cbrn.release_agent(
                agent_id=agent_id,
                position=pos,
                quantity_kg=cfg.projector_gas_mass_kg,
                delivery_method="projector",
                timestamp=timestamp,
            )
            puff_ids.append(pid)

        self._release_ids.extend(puff_ids)
        logger.info(
            "Projector salvo: %s, %d drums at (%.0f, %.0f)",
            agent_id, num_projectors, target_easting, target_northing,
        )
        return puff_ids

    def set_unit_gas_mask(self, unit_id: str, mask_type: GasMaskType) -> int:
        """Set a unit's gas mask type.

        Returns the corresponding MOPP level.
        """
        self._unit_masks[unit_id] = mask_type
        return _MASK_TO_MOPP[mask_type]

    def get_unit_mopp_level(self, unit_id: str) -> int:
        """Get the MOPP level for a unit based on its gas mask."""
        mask = self._unit_masks.get(unit_id, GasMaskType.NONE)
        return _MASK_TO_MOPP[mask]

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "unit_masks": {
                uid: int(mask) for uid, mask in self._unit_masks.items()
            },
            "release_ids": list(self._release_ids),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._unit_masks = {
            uid: GasMaskType(v)
            for uid, v in state.get("unit_masks", {}).items()
        }
        self._release_ids = state.get("release_ids", [])
