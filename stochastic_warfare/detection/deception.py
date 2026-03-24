"""Deception operations — decoys, camouflage, feints, false emissions.

Decoys generate false signatures that detection systems cannot distinguish
from real targets.  Camouflage modifies a unit's signature to reduce
detectability.  Effectiveness degrades over time.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.signatures import (
    EMSignature,
    SignatureProfile,
    VisualSignature,
    ThermalSignature,
    RadarSignature,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DeceptionType(enum.IntEnum):
    DECOY_VISUAL = 0
    DECOY_THERMAL = 1
    DECOY_RADAR = 2
    DECOY_ACOUSTIC = 3
    FEINT = 4
    FALSE_EMISSIONS = 5
    CAMOUFLAGE = 6


# ---------------------------------------------------------------------------
# Decoy
# ---------------------------------------------------------------------------


@dataclass
class Decoy:
    """A fake target that generates false signatures."""

    decoy_id: str
    position: Position
    deception_type: DeceptionType
    signature: SignatureProfile
    effectiveness: float = 1.0  # 0–1, degrades over time
    active: bool = True
    deploy_time: float = 0.0
    degradation_rate: float = 0.01  # per second

    def get_state(self) -> dict[str, Any]:
        return {
            "decoy_id": self.decoy_id,
            "position": tuple(self.position),
            "deception_type": int(self.deception_type),
            "effectiveness": self.effectiveness,
            "active": self.active,
            "deploy_time": self.deploy_time,
            "degradation_rate": self.degradation_rate,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.decoy_id = state["decoy_id"]
        self.position = Position(*state["position"])
        self.deception_type = DeceptionType(state["deception_type"])
        self.effectiveness = state["effectiveness"]
        self.active = state["active"]
        self.deploy_time = state["deploy_time"]
        self.degradation_rate = state["degradation_rate"]


# ---------------------------------------------------------------------------
# Deception engine
# ---------------------------------------------------------------------------


class DeceptionEngine:
    """Manages decoys, camouflage, and other deception operations.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._decoys: dict[str, Decoy] = {}
        self._decoy_counter: int = 0

    # ------------------------------------------------------------------
    # Decoy management
    # ------------------------------------------------------------------

    def deploy_decoy(
        self,
        position: Position,
        deception_type: DeceptionType,
        effectiveness: float = 1.0,
        signature: SignatureProfile | None = None,
        degradation_rate: float = 0.01,
    ) -> Decoy:
        """Deploy a new decoy at *position*."""
        self._decoy_counter += 1
        decoy_id = f"decoy-{self._decoy_counter:04d}"

        if signature is None:
            # Default decoy signature
            signature = SignatureProfile(
                profile_id=decoy_id,
                unit_type="decoy",
                visual=VisualSignature(cross_section_m2=5.0),
                thermal=ThermalSignature(heat_output_kw=200.0),
                radar=RadarSignature(rcs_frontal_m2=10.0, rcs_side_m2=10.0, rcs_rear_m2=10.0),
            )

        decoy = Decoy(
            decoy_id=decoy_id,
            position=position,
            deception_type=deception_type,
            signature=signature,
            effectiveness=effectiveness,
            degradation_rate=degradation_rate,
        )
        self._decoys[decoy_id] = decoy
        return decoy

    def update_decoys(self, dt: float) -> None:
        """Degrade all active decoys over time."""
        for decoy in self._decoys.values():
            if decoy.active:
                decoy.effectiveness -= decoy.degradation_rate * dt
                if decoy.effectiveness <= 0:
                    decoy.effectiveness = 0.0
                    decoy.active = False

    def active_decoys(self) -> list[Decoy]:
        """Return all currently active decoys."""
        return [d for d in self._decoys.values() if d.active]

    def remove_decoy(self, decoy_id: str) -> None:
        """Remove a decoy."""
        if decoy_id in self._decoys:
            del self._decoys[decoy_id]

    # ------------------------------------------------------------------
    # Camouflage
    # ------------------------------------------------------------------

    @staticmethod
    def camouflage_modifier(
        posture: int = 0,
        preparation_time_hours: float = 0.0,
        terrain_concealment: float = 0.0,
    ) -> float:
        """Return signature reduction factor (0.3–1.0) for camouflage.

        Depends on posture, time to prepare, and terrain concealment.
        """
        # Base modifier from posture (0=MOVING: 1.0, 4=FORTIFIED: 0.4)
        posture_mod = max(0.4, 1.0 - posture * 0.15)

        # Preparation time reduces signature (max benefit at 4+ hours)
        prep_mod = max(0.3, 1.0 - 0.15 * min(preparation_time_hours, 4.0))

        # Terrain concealment
        terrain_mod = 1.0 - terrain_concealment * 0.5

        return max(0.3, min(1.0, posture_mod * prep_mod * terrain_mod))

    # ------------------------------------------------------------------
    # False emission
    # ------------------------------------------------------------------

    def false_emission(
        self,
        position: Position,
        frequency_ghz: float,
        power_dbm: float,
    ) -> EMSignature:
        """Create a false EM emission to mislead ESM/SIGINT."""
        return EMSignature(
            emitting=True,
            power_dbm=power_dbm,
            frequency_ghz=frequency_ghz,
        )

    # ------------------------------------------------------------------
    # Feint assessment
    # ------------------------------------------------------------------

    @staticmethod
    def feint_assessment(
        unit_count: int,
        average_speed: float = 0.0,
        formation_coherence: float = 1.0,
    ) -> float:
        """How convincing is a force as a feint? 0–1 scale.

        Based on size, movement, and formation coherence.
        """
        # More units = more convincing
        size_score = min(1.0, unit_count / 10.0)
        # Movement makes it more convincing
        movement_score = min(1.0, average_speed / 5.0)
        # Formation coherence
        return min(1.0, (size_score * 0.4 + movement_score * 0.3 + formation_coherence * 0.3))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "decoys": {did: d.get_state() for did, d in sorted(self._decoys.items())},
            "decoy_counter": self._decoy_counter,
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._decoy_counter = state["decoy_counter"]
        self._rng.bit_generator.state = state["rng_state"]
        self._decoys = {}
        for did, ds in state["decoys"].items():
            decoy = Decoy(
                decoy_id="", position=Position(0, 0, 0),
                deception_type=DeceptionType.DECOY_VISUAL,
                signature=SignatureProfile(profile_id="", unit_type=""),
            )
            decoy.set_state(ds)
            self._decoys[did] = decoy
