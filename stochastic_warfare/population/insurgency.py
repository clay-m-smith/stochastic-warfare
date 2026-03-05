"""Insurgency engine --- radicalization pipeline and cell dynamics.

Phase 24e. Population-driven insurgency model with Markov radicalization
stages and cell-based operations.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class CellStatus(enum.IntEnum):
    """Insurgent cell operational status."""

    DORMANT = 0
    ACTIVE = 1
    DISCOVERED = 2
    DESTROYED = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RadicalizationState:
    """Radicalization state for a population region."""

    region_id: str
    sympathizer_fraction: float = 0.0
    supporter_fraction: float = 0.0
    cell_member_count: int = 0
    combatant_count: int = 0


@dataclass
class InsurgentCell:
    """An active or dormant insurgent cell."""

    cell_id: str
    region_id: str
    member_count: int
    status: CellStatus = CellStatus.DORMANT
    capabilities: list[str] = field(default_factory=list)
    concealment: float = 1.0
    operations_count: int = 0


@dataclass(frozen=True)
class CellOperationResult:
    """Result of an insurgent cell operation."""

    cell_id: str
    operation_type: str
    success: bool
    position: Position
    effects: dict[str, float]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class InsurgencyConfig(BaseModel):
    """Tuning parameters for insurgency dynamics."""

    # Radicalization rates (per hour)
    k_collateral: float = 0.005
    k_economic_baseline: float = 0.001
    k_family_casualty: float = 0.01

    # De-radicalization rates (per hour)
    k_economic_opportunity: float = 0.003
    k_governance_quality: float = 0.002
    k_military_protection: float = 0.002
    k_psyop: float = 0.001

    # Cell formation
    cell_formation_threshold: int = 5

    # Operations rates (per cell per hour)
    k_ied_emplacement: float = 0.01
    k_sabotage: float = 0.005
    k_ambush: float = 0.002

    # Discovery rates
    k_humint: float = 0.05
    k_sigint: float = 0.02
    k_pattern_analysis: float = 0.01

    # Transition rates (per hour)
    sympathizer_to_supporter_rate: float = 0.01
    supporter_to_cell_member_rate: float = 0.005

    # Concealment
    concealment_degradation_per_op: float = 0.05


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class InsurgencyEngine:
    """Radicalization pipeline and insurgent cell lifecycle manager.

    Models the population-to-insurgent pipeline as a multi-stage Markov
    process: NEUTRAL -> SYMPATHIZER -> SUPPORTER -> CELL MEMBER.
    Cell dynamics include formation, activation, operations, discovery,
    and destruction.

    Parameters
    ----------
    event_bus : EventBus
        For publishing insurgency events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : InsurgencyConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: InsurgencyConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or InsurgencyConfig()
        self._radicalization: dict[str, RadicalizationState] = {}
        self._cells: dict[str, InsurgentCell] = {}
        self._region_populations: dict[str, int] = {}

    # -- Region management --

    def register_region(
        self,
        region_id: str,
        population: int = 1000,
        initial_state: RadicalizationState | None = None,
    ) -> None:
        """Add a region to track with optional initial radicalization state."""
        if initial_state is not None:
            self._radicalization[region_id] = initial_state
        else:
            self._radicalization[region_id] = RadicalizationState(
                region_id=region_id
            )
        self._region_populations[region_id] = population
        logger.debug(
            "Registered insurgency region %s (pop=%d)", region_id, population
        )

    def get_radicalization(self, region_id: str) -> RadicalizationState:
        """Return the current radicalization state for a region."""
        return self._radicalization[region_id]

    # -- Radicalization pipeline --

    def update_radicalization(
        self,
        dt_hours: float,
        collateral_by_region: dict[str, float],
        military_presence_by_region: dict[str, float],
        economic_factor: float,
        aid_by_region: dict[str, float],
        psyop_by_region: dict[str, float],
        timestamp: datetime | None = None,
    ) -> dict[str, RadicalizationState]:
        """Advance the radicalization pipeline for all registered regions.

        Parameters
        ----------
        dt_hours : float
            Time step in hours.
        collateral_by_region : dict[str, float]
            Collateral damage intensity per region (0-1).
        military_presence_by_region : dict[str, float]
            Military protection level per region (0-1).
        economic_factor : float
            Global economic opportunity factor (0-1).
        aid_by_region : dict[str, float]
            Aid/governance quality per region (0-1).
        psyop_by_region : dict[str, float]
            PSYOP effectiveness per region (0-1).
        timestamp : datetime | None
            Simulation timestamp.

        Returns
        -------
        dict[str, RadicalizationState]
            Updated radicalization states keyed by region_id.
        """
        cfg = self._config
        result: dict[str, RadicalizationState] = {}

        for region_id, state in self._radicalization.items():
            collateral = collateral_by_region.get(region_id, 0.0)
            protection = military_presence_by_region.get(region_id, 0.0)
            aid = aid_by_region.get(region_id, 0.0)
            psyop = psyop_by_region.get(region_id, 0.0)
            population = self._region_populations.get(region_id, 1000)

            # --- Radicalization growth ---
            growth = dt_hours * (
                cfg.k_collateral * collateral
                + cfg.k_economic_baseline
                + cfg.k_family_casualty * collateral  # family casualties correlate
            )

            # --- De-radicalization ---
            decay = dt_hours * (
                cfg.k_economic_opportunity * economic_factor
                + cfg.k_governance_quality * aid
                + cfg.k_military_protection * protection
                + cfg.k_psyop * psyop
            )

            state.sympathizer_fraction += growth - decay
            state.sympathizer_fraction = max(0.0, min(1.0, state.sympathizer_fraction))

            # --- Sympathizer -> Supporter transition ---
            sym_to_sup = dt_hours * cfg.sympathizer_to_supporter_rate * state.sympathizer_fraction
            sym_to_sup = min(sym_to_sup, state.sympathizer_fraction)
            state.supporter_fraction += sym_to_sup
            state.sympathizer_fraction -= sym_to_sup

            # --- Supporter -> Cell member transition ---
            sup_to_cell = dt_hours * cfg.supporter_to_cell_member_rate * state.supporter_fraction
            sup_to_cell = min(sup_to_cell, state.supporter_fraction)
            new_members = int(sup_to_cell * population)
            state.cell_member_count += new_members
            state.supporter_fraction -= sup_to_cell

            # Clamp fractions
            state.sympathizer_fraction = max(0.0, min(1.0, state.sympathizer_fraction))
            state.supporter_fraction = max(0.0, min(1.0, state.supporter_fraction))

            result[region_id] = state

        logger.debug(
            "Updated radicalization for %d regions (dt=%.2fh)",
            len(result), dt_hours,
        )
        return result

    # -- Cell lifecycle --

    def check_cell_formation(
        self,
        region_id: str,
        timestamp: datetime | None = None,
    ) -> InsurgentCell | None:
        """Check if conditions are met to form a new insurgent cell.

        A cell forms when cell_member_count >= threshold and no existing
        ACTIVE or DORMANT cell exists in the region.

        Returns
        -------
        InsurgentCell | None
            Newly formed cell, or None if conditions not met.
        """
        state = self._radicalization.get(region_id)
        if state is None:
            return None

        if state.cell_member_count < self._config.cell_formation_threshold:
            return None

        # Check for existing non-destroyed cell in region
        for cell in self._cells.values():
            if (
                cell.region_id == region_id
                and cell.status in (CellStatus.DORMANT, CellStatus.ACTIVE)
            ):
                return None

        # Determine capabilities based on member count
        capabilities: list[str] = []
        if state.cell_member_count >= 5:
            capabilities.append("ied")
        if state.cell_member_count >= 8:
            capabilities.append("sabotage")
        if state.cell_member_count >= 12:
            capabilities.append("ambush")

        cell_id = str(uuid.uuid4())[:8]
        cell = InsurgentCell(
            cell_id=cell_id,
            region_id=region_id,
            member_count=state.cell_member_count,
            status=CellStatus.DORMANT,
            capabilities=list(capabilities),
            concealment=1.0,
            operations_count=0,
        )
        self._cells[cell_id] = cell

        logger.info(
            "Cell %s formed in region %s (members=%d, caps=%s)",
            cell_id, region_id, cell.member_count, capabilities,
        )
        return cell

    def activate_cell(
        self,
        cell_id: str,
        reason: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        """Activate a dormant cell.

        Only transitions DORMANT -> ACTIVE. Destroyed cells remain destroyed.
        """
        cell = self._cells.get(cell_id)
        if cell is None:
            return

        if cell.status == CellStatus.DESTROYED:
            logger.debug("Cannot activate destroyed cell %s", cell_id)
            return

        if cell.status == CellStatus.DORMANT:
            cell.status = CellStatus.ACTIVE
            logger.info(
                "Cell %s activated (reason=%s)", cell_id, reason
            )

    # -- Cell operations --

    def execute_cell_operations(
        self,
        dt_hours: float,
        high_traffic_positions: list[Position],
        military_targets: list[Position],
        timestamp: datetime | None = None,
    ) -> list[CellOperationResult]:
        """Execute operations for all active cells this tick.

        Parameters
        ----------
        dt_hours : float
            Time step in hours.
        high_traffic_positions : list[Position]
            Positions where IEDs can be emplaced.
        military_targets : list[Position]
            Positions of military targets for ambushes.
        timestamp : datetime | None
            Simulation timestamp.

        Returns
        -------
        list[CellOperationResult]
            Results of all cell operations this tick.
        """
        cfg = self._config
        results: list[CellOperationResult] = []

        for cell in list(self._cells.values()):
            if cell.status != CellStatus.ACTIVE:
                continue

            # IED emplacement
            if "ied" in cell.capabilities and len(high_traffic_positions) > 0:
                if self._rng.random() < cfg.k_ied_emplacement * dt_hours:
                    idx = self._rng.integers(0, len(high_traffic_positions))
                    pos = high_traffic_positions[idx]
                    success = bool(self._rng.random() < cell.concealment)
                    effects = {"ied_placed": 1.0} if success else {}
                    results.append(CellOperationResult(
                        cell_id=cell.cell_id,
                        operation_type="ied_emplacement",
                        success=success,
                        position=pos,
                        effects=effects,
                    ))
                    cell.concealment = max(
                        0.0, cell.concealment - cfg.concealment_degradation_per_op
                    )
                    cell.operations_count += 1

            # Sabotage
            if "sabotage" in cell.capabilities:
                if self._rng.random() < cfg.k_sabotage * dt_hours:
                    pos = Position(0.0, 0.0, 0.0)
                    if len(high_traffic_positions) > 0:
                        idx = self._rng.integers(0, len(high_traffic_positions))
                        pos = high_traffic_positions[idx]
                    success = bool(self._rng.random() < cell.concealment)
                    effects = {"infrastructure_damage": 0.3} if success else {}
                    results.append(CellOperationResult(
                        cell_id=cell.cell_id,
                        operation_type="sabotage",
                        success=success,
                        position=pos,
                        effects=effects,
                    ))
                    cell.concealment = max(
                        0.0, cell.concealment - cfg.concealment_degradation_per_op
                    )
                    cell.operations_count += 1

            # Ambush
            if "ambush" in cell.capabilities and len(military_targets) > 0:
                if self._rng.random() < cfg.k_ambush * dt_hours:
                    idx = self._rng.integers(0, len(military_targets))
                    pos = military_targets[idx]
                    success = bool(self._rng.random() < cell.concealment)
                    effects = {"ambush_casualties": 0.5} if success else {}
                    results.append(CellOperationResult(
                        cell_id=cell.cell_id,
                        operation_type="ambush",
                        success=success,
                        position=pos,
                        effects=effects,
                    ))
                    cell.concealment = max(
                        0.0, cell.concealment - cfg.concealment_degradation_per_op
                    )
                    cell.operations_count += 1

        logger.debug(
            "Cell operations: %d results from %d active cells",
            len(results),
            sum(1 for c in self._cells.values() if c.status == CellStatus.ACTIVE),
        )
        return results

    # -- Cell discovery & destruction --

    def attempt_cell_discovery(
        self,
        cell_id: str,
        discovery_source: str,
        quality: float,
        timestamp: datetime | None = None,
    ) -> bool:
        """Attempt to discover an insurgent cell.

        Parameters
        ----------
        cell_id : str
            Cell to attempt discovery on.
        discovery_source : str
            One of "humint", "sigint", "pattern_analysis".
        quality : float
            Intelligence quality factor (0-1).
        timestamp : datetime | None
            Simulation timestamp.

        Returns
        -------
        bool
            True if the cell was discovered.
        """
        cell = self._cells.get(cell_id)
        if cell is None:
            return False

        if cell.status in (CellStatus.DISCOVERED, CellStatus.DESTROYED):
            return False

        cfg = self._config
        source_rates = {
            "humint": cfg.k_humint,
            "sigint": cfg.k_sigint,
            "pattern_analysis": cfg.k_pattern_analysis,
        }
        source_rate = source_rates.get(discovery_source, 0.0)

        # Lower concealment = higher discovery probability
        p_discover = (1.0 - cell.concealment) * source_rate * quality
        p_discover = max(0.0, min(1.0, p_discover))

        if self._rng.random() < p_discover:
            cell.status = CellStatus.DISCOVERED
            logger.info(
                "Cell %s discovered via %s (quality=%.2f, concealment=%.2f)",
                cell_id, discovery_source, quality, cell.concealment,
            )
            return True

        return False

    def destroy_cell(
        self,
        cell_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Destroy an insurgent cell."""
        cell = self._cells.get(cell_id)
        if cell is None:
            return
        cell.status = CellStatus.DESTROYED
        logger.info("Cell %s destroyed", cell_id)

    # -- Queries --

    def get_active_cells(
        self,
        region_id: str | None = None,
    ) -> list[InsurgentCell]:
        """Return active cells, optionally filtered by region."""
        cells = [
            c for c in self._cells.values()
            if c.status == CellStatus.ACTIVE
        ]
        if region_id is not None:
            cells = [c for c in cells if c.region_id == region_id]
        return cells

    def get_cell(self, cell_id: str) -> InsurgentCell:
        """Return a cell by ID; raises ``KeyError`` if not found."""
        return self._cells[cell_id]

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize full engine state for checkpoint."""
        return {
            "radicalization": {
                rid: {
                    "region_id": s.region_id,
                    "sympathizer_fraction": s.sympathizer_fraction,
                    "supporter_fraction": s.supporter_fraction,
                    "cell_member_count": s.cell_member_count,
                    "combatant_count": s.combatant_count,
                }
                for rid, s in self._radicalization.items()
            },
            "cells": {
                cid: {
                    "cell_id": c.cell_id,
                    "region_id": c.region_id,
                    "member_count": c.member_count,
                    "status": int(c.status),
                    "capabilities": list(c.capabilities),
                    "concealment": c.concealment,
                    "operations_count": c.operations_count,
                }
                for cid, c in self._cells.items()
            },
            "region_populations": dict(self._region_populations),
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._radicalization.clear()
        for rid, rd in state["radicalization"].items():
            self._radicalization[rid] = RadicalizationState(
                region_id=rd["region_id"],
                sympathizer_fraction=rd["sympathizer_fraction"],
                supporter_fraction=rd["supporter_fraction"],
                cell_member_count=rd["cell_member_count"],
                combatant_count=rd.get("combatant_count", 0),
            )
        self._cells.clear()
        for cid, cd in state["cells"].items():
            self._cells[cid] = InsurgentCell(
                cell_id=cd["cell_id"],
                region_id=cd["region_id"],
                member_count=cd["member_count"],
                status=CellStatus(cd["status"]),
                capabilities=list(cd["capabilities"]),
                concealment=cd["concealment"],
                operations_count=cd.get("operations_count", 0),
            )
        self._region_populations = dict(state.get("region_populations", {}))
