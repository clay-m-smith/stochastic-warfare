"""Probit dose-response model for CBRN casualties.

Accumulates per-unit dosage over time and evaluates casualty probability
using the probit model: ``Y = a + b·ln(D)``, ``P(effect) = Φ(Y - 5)``
where Φ is the standard normal CDF.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel
from scipy.special import ndtr

from stochastic_warfare.cbrn.events import CBRNCasualtyEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Dosage records
# ---------------------------------------------------------------------------


@dataclass
class DosageRecord:
    """Per-unit cumulative dosage tracking."""

    unit_id: str
    agent_dosages: dict[str, float] = field(default_factory=dict)  # agent_id -> Ct
    radiation_dose_gy: float = 0.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CasualtyConfig(BaseModel):
    """Configuration for the CBRN casualty engine."""

    exposure_check_interval_s: float = 10.0
    min_dosage_for_check: float = 0.1


# ---------------------------------------------------------------------------
# Casualty engine
# ---------------------------------------------------------------------------


class CBRNCasualtyEngine:
    """Evaluates CBRN casualties via probit dose-response model."""

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: CasualtyConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or CasualtyConfig()
        self._dosages: dict[str, DosageRecord] = {}

    def _get_record(self, unit_id: str) -> DosageRecord:
        if unit_id not in self._dosages:
            self._dosages[unit_id] = DosageRecord(unit_id=unit_id)
        return self._dosages[unit_id]

    def accumulate_dosage(
        self,
        unit_id: str,
        agent_id: str,
        concentration_mg_m3: float,
        exposure_time_s: float,
        protection_factor: float = 0.0,
    ) -> float:
        """Accumulate chemical dosage Ct (mg·min/m³) for a unit.

        Parameters
        ----------
        protection_factor:
            0-1, fraction of exposure blocked by MOPP gear.

        Returns the new cumulative dosage.
        """
        rec = self._get_record(unit_id)
        # Ct = concentration × time_in_minutes × (1 - protection)
        effective_conc = concentration_mg_m3 * (1.0 - protection_factor)
        ct = effective_conc * (exposure_time_s / 60.0)
        rec.agent_dosages[agent_id] = rec.agent_dosages.get(agent_id, 0.0) + ct
        return rec.agent_dosages[agent_id]

    def accumulate_radiation(
        self,
        unit_id: str,
        dose_rate_gy_per_s: float,
        exposure_time_s: float,
        protection_factor: float = 0.0,
    ) -> float:
        """Accumulate radiation dose (Gy) for a unit.

        Returns the new cumulative dose.
        """
        rec = self._get_record(unit_id)
        effective_rate = dose_rate_gy_per_s * (1.0 - protection_factor)
        rec.radiation_dose_gy += effective_rate * exposure_time_s
        return rec.radiation_dose_gy

    @staticmethod
    def probit_probability(dosage: float, probit_a: float, probit_b: float) -> float:
        """Compute probability of effect from probit model.

        ``Y = a + b·ln(D)``, ``P = Φ(Y - 5)`` where Φ is standard normal CDF.
        """
        if dosage <= 0:
            return 0.0
        y = probit_a + probit_b * math.log(max(dosage, 1e-20))
        # P = Φ(Y - 5) using scipy ndtr
        return float(ndtr(y - 5.0))

    def assess_casualties(
        self,
        unit_id: str,
        agent_defn: Any,
        personnel_count: int,
        timestamp: Any = None,
    ) -> tuple[int, int]:
        """Assess incapacitated and lethal casualties for a unit.

        Returns (incapacitated, lethal) counts.
        """
        rec = self._get_record(unit_id)
        agent_id = getattr(agent_defn, "agent_id", "unknown")
        dosage = rec.agent_dosages.get(agent_id, 0.0)

        if dosage < self._config.min_dosage_for_check:
            return 0, 0

        probit_a = getattr(agent_defn, "probit_a", -14.0)
        probit_b = getattr(agent_defn, "probit_b", 1.0)

        # Lethality probability (from LCt50 probit)
        p_lethal = self.probit_probability(dosage, probit_a, probit_b)

        # Incapacitation at lower threshold (use ICt50 if available)
        ict50 = getattr(agent_defn, "ict50_mg_min_m3", 0.0)
        lct50 = getattr(agent_defn, "lct50_mg_min_m3", 0.0)
        if ict50 > 0 and lct50 > 0:
            # Shift probit for incapacitation: adjust intercept for ICt50
            ratio = math.log(ict50 / max(lct50, 1e-20))
            incap_a = probit_a - probit_b * ratio
            p_incap = self.probit_probability(dosage, incap_a, probit_b)
        else:
            p_incap = min(1.0, p_lethal * 2.0)

        # Stochastic casualties
        lethal = 0
        incapacitated = 0
        for _ in range(personnel_count):
            roll = self._rng.random()
            if roll < p_lethal:
                lethal += 1
            elif roll < p_incap:
                incapacitated += 1

        if (lethal > 0 or incapacitated > 0) and timestamp is not None:
            self._event_bus.publish(CBRNCasualtyEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                unit_id=unit_id,
                agent_id=agent_id,
                casualties_incapacitated=incapacitated,
                casualties_lethal=lethal,
                dosage_ct=dosage,
            ))

        return incapacitated, lethal

    @staticmethod
    def get_triage_priority(dosage_fraction: float) -> int:
        """Map dosage fraction (dosage/LCt50) to triage priority.

        Returns 1=IMMEDIATE, 2=DELAYED, 3=MINIMAL, 4=EXPECTANT.
        """
        if dosage_fraction >= 2.0:
            return 4  # EXPECTANT
        elif dosage_fraction >= 1.0:
            return 1  # IMMEDIATE
        elif dosage_fraction >= 0.5:
            return 2  # DELAYED
        else:
            return 3  # MINIMAL

    def get_dosage(self, unit_id: str, agent_id: str) -> float:
        """Get current cumulative dosage for a unit and agent."""
        rec = self._dosages.get(unit_id)
        if rec is None:
            return 0.0
        return rec.agent_dosages.get(agent_id, 0.0)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "dosages": {
                uid: {
                    "agent_dosages": dict(rec.agent_dosages),
                    "radiation_dose_gy": rec.radiation_dose_gy,
                }
                for uid, rec in self._dosages.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._dosages.clear()
        for uid, data in state.get("dosages", {}).items():
            rec = DosageRecord(unit_id=uid)
            rec.agent_dosages = data.get("agent_dosages", {})
            rec.radiation_dose_gy = data.get("radiation_dose_gy", 0.0)
            self._dosages[uid] = rec
