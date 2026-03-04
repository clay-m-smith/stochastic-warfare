"""Population disposition dynamics — influence engine.

Phase 12e-5. Markov chain driving civilian disposition transitions
based on collateral damage, aid, and PSYOP events.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.population.civilians import (
    CivilianDisposition,
    CivilianManager,
)
from stochastic_warfare.population.events import DispositionChangeEvent

logger = get_logger(__name__)


class InfluenceConfig(BaseModel):
    """Influence engine configuration."""

    collateral_hostility_rate: float = 0.01
    """Rate of disposition shift toward HOSTILE per casualty per hour."""
    aid_friendliness_rate: float = 0.005
    """Rate of disposition shift toward FRIENDLY per aid event per hour."""
    psyop_rate: float = 0.002
    """Base rate of PSYOP-driven disposition change per hour."""
    natural_decay_rate: float = 0.001
    """Rate of disposition drift back toward NEUTRAL per hour."""


class InfluenceEngine:
    """Drive civilian disposition transitions via influence factors.

    Parameters
    ----------
    civilian_manager : CivilianManager
        Source of region data.
    event_bus : EventBus
        For publishing disposition change events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : InfluenceConfig | None
        Configuration.
    """

    def __init__(
        self,
        civilian_manager: CivilianManager,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: InfluenceConfig | None = None,
    ) -> None:
        self._civilians = civilian_manager
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or InfluenceConfig()

    def update(
        self,
        dt_hours: float,
        collateral_events: dict[str, int] | None = None,
        aid_events: dict[str, int] | None = None,
        psyop_events: dict[str, float] | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, str]:
        """Advance disposition dynamics for all regions.

        Parameters
        ----------
        dt_hours:
            Time step in hours.
        collateral_events:
            Region ID → new civilian casualties this step.
        aid_events:
            Region ID → aid delivery count this step.
        psyop_events:
            Region ID → PSYOP effectiveness (0-1) this step.
        timestamp:
            Simulation timestamp.

        Returns
        -------
        dict[str, str]
            Region ID → new disposition name for regions that changed.
        """
        ts = timestamp or datetime.now(tz=timezone.utc)
        cfg = self._config
        collateral = collateral_events or {}
        aid = aid_events or {}
        psyop = psyop_events or {}
        changes: dict[str, str] = {}

        for region in self._civilians.all_regions():
            rid = region.region_id
            old_disp = region.disposition

            # Compute influence scores
            hostile_pressure = collateral.get(rid, 0) * cfg.collateral_hostility_rate * dt_hours
            friendly_pressure = aid.get(rid, 0) * cfg.aid_friendliness_rate * dt_hours
            psyop_effect = psyop.get(rid, 0.0) * cfg.psyop_rate * dt_hours

            # Net disposition shift: positive = toward friendly, negative = toward hostile
            net_shift = friendly_pressure + psyop_effect - hostile_pressure

            # Natural decay toward neutral
            if old_disp == CivilianDisposition.FRIENDLY:
                net_shift -= cfg.natural_decay_rate * dt_hours
            elif old_disp == CivilianDisposition.HOSTILE:
                net_shift += cfg.natural_decay_rate * dt_hours

            # Stochastic transition check
            if net_shift > 0 and self._rng.random() < min(1.0, abs(net_shift)):
                # Shift toward friendly
                if old_disp == CivilianDisposition.HOSTILE:
                    new_disp = CivilianDisposition.NEUTRAL
                elif old_disp == CivilianDisposition.NEUTRAL:
                    new_disp = CivilianDisposition.FRIENDLY
                elif old_disp == CivilianDisposition.MIXED:
                    new_disp = CivilianDisposition.NEUTRAL
                else:
                    new_disp = old_disp  # already FRIENDLY
            elif net_shift < 0 and self._rng.random() < min(1.0, abs(net_shift)):
                # Shift toward hostile
                if old_disp == CivilianDisposition.FRIENDLY:
                    new_disp = CivilianDisposition.NEUTRAL
                elif old_disp == CivilianDisposition.NEUTRAL:
                    new_disp = CivilianDisposition.HOSTILE
                elif old_disp == CivilianDisposition.MIXED:
                    new_disp = CivilianDisposition.NEUTRAL
                else:
                    new_disp = old_disp  # already HOSTILE
            else:
                new_disp = old_disp

            if new_disp != old_disp:
                region.disposition = new_disp
                changes[rid] = new_disp.name
                self._event_bus.publish(DispositionChangeEvent(
                    timestamp=ts,
                    source=ModuleId.POPULATION,
                    region_id=rid,
                    old_disposition=old_disp.name,
                    new_disposition=new_disp.name,
                ))
                logger.debug(
                    "Region %s disposition: %s -> %s",
                    rid, old_disp.name, new_disp.name,
                )

        return changes
