"""Commander personality engine -- decision-making style and biases.

Commander profiles define individual traits (aggression, caution, flexibility,
initiative, experience) that modulate decision-making throughout the OODA cycle.
Profiles are loaded from YAML and assigned to units.  The engine applies
personality biases to OODA timing, option scoring, and risk thresholds.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CommanderPersonality(BaseModel):
    """A commander's personality profile loaded from YAML.

    All trait values are floats on [0.0, 1.0].
    """

    profile_id: str
    display_name: str
    description: str
    aggression: float = Field(ge=0.0, le=1.0)
    caution: float = Field(ge=0.0, le=1.0)
    flexibility: float = Field(ge=0.0, le=1.0)
    initiative: float = Field(ge=0.0, le=1.0)
    experience: float = Field(ge=0.0, le=1.0)
    preferred_doctrine: str | None = None
    school_id: str | None = None
    stress_tolerance: float = Field(default=0.5, ge=0.0, le=1.0)
    decision_speed: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_acceptance: float = Field(default=0.5, ge=0.0, le=1.0)
    doctrine_violation_tolerance: float = Field(default=0.2, ge=0.0, le=1.0)
    collateral_tolerance: float = Field(default=0.3, ge=0.0, le=1.0)
    escalation_awareness: float = Field(default=0.5, ge=0.0, le=1.0)


class CommanderConfig(BaseModel):
    """Tuning parameters for the commander personality engine."""

    ooda_speed_base_mult: float = 1.0
    noise_sigma: float = 0.1
    risk_threshold_base: float = 0.3


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


class CommanderProfileLoader:
    """Load commander personality profiles from YAML files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = (
                Path(__file__).resolve().parents[3] / "data" / "commander_profiles"
            )
        self._data_dir = data_dir
        self._definitions: dict[str, CommanderPersonality] = {}

    def load_definition(self, path: Path) -> CommanderPersonality:
        """Load a single commander profile YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = CommanderPersonality.model_validate(data)
        self._definitions[defn.profile_id] = defn
        return defn

    def load_all(self) -> None:
        """Load all ``*.yaml`` files in the data directory."""
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)

    def get_definition(self, profile_id: str) -> CommanderPersonality:
        """Return a loaded profile by its ``profile_id``."""
        return self._definitions[profile_id]

    def available_profiles(self) -> list[str]:
        """Return all loaded profile IDs."""
        return sorted(self._definitions.keys())


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CommanderEngine:
    """Applies commander personality biases to AI decision-making.

    Parameters
    ----------
    loader : CommanderProfileLoader
        Pre-loaded profile definitions.
    rng : numpy.random.Generator
        Deterministic PRNG stream (``ModuleId.C2``).
    config : CommanderConfig | None
        Tuning parameters.  Uses defaults when ``None``.
    """

    def __init__(
        self,
        loader: CommanderProfileLoader,
        rng: np.random.Generator,
        config: CommanderConfig | None = None,
    ) -> None:
        self._loader = loader
        self._rng = rng
        self._config = config or CommanderConfig()
        # unit_id -> profile_id mapping
        self._assignments: dict[str, str] = {}

    # -- Assignment ---------------------------------------------------------

    def assign_personality(self, unit_id: str, profile_id: str) -> None:
        """Assign a loaded personality profile to a unit.

        Raises ``KeyError`` if *profile_id* has not been loaded.
        """
        # Validate that the profile exists in the loader
        self._loader.get_definition(profile_id)
        self._assignments[unit_id] = profile_id
        logger.debug("Assigned profile %s to unit %s", profile_id, unit_id)

    def get_personality(self, unit_id: str) -> CommanderPersonality | None:
        """Return the personality for *unit_id*, or ``None`` if unassigned."""
        pid = self._assignments.get(unit_id)
        if pid is None:
            return None
        return self._loader.get_definition(pid)

    # -- OODA speed ---------------------------------------------------------

    def get_ooda_speed_multiplier(self, unit_id: str) -> float:
        """Return the OODA cycle speed multiplier for *unit_id*.

        Formula::

            base_mult / (0.5 + 0.5 * (decision_speed + experience * 0.3))

        Faster ``decision_speed`` and higher ``experience`` produce a lower
        multiplier, meaning faster OODA cycling.  Typical range ~0.6--2.0.

        Returns ``config.ooda_speed_base_mult`` (1.0) for unassigned units.
        """
        p = self.get_personality(unit_id)
        if p is None:
            return self._config.ooda_speed_base_mult
        denominator = 0.5 + 0.5 * (p.decision_speed + p.experience * 0.3)
        return self._config.ooda_speed_base_mult / denominator

    # -- Decision noise -----------------------------------------------------

    def apply_decision_noise(
        self,
        unit_id: str,
        scores: dict[str, float],
    ) -> dict[str, float]:
        """Add Gaussian noise to option scores based on personality.

        Noise standard deviation is ``config.noise_sigma * (1.0 - experience)``.
        Higher experience yields less noise (more consistent decisions).

        Returns a **new** dict with noised scores; the input is not modified.
        For unassigned units, returns a copy of the input unchanged.
        """
        p = self.get_personality(unit_id)
        if p is None:
            return dict(scores)
        sigma = self._config.noise_sigma * (1.0 - p.experience)
        noised: dict[str, float] = {}
        for key in sorted(scores):
            noise = float(self._rng.normal(0.0, sigma)) if sigma > 0.0 else 0.0
            noised[key] = scores[key] + noise
        return noised

    # -- Risk threshold -----------------------------------------------------

    def get_risk_threshold(self, unit_id: str, base: float = 0.3) -> float:
        """Return the risk acceptance threshold for *unit_id*.

        Formula::

            base * (1.0 + caution - aggression)

        Higher caution raises the threshold (commander rejects risky options
        more readily).  Higher aggression lowers it (commander accepts risk).

        Returns *base* for unassigned units.
        """
        p = self.get_personality(unit_id)
        if p is None:
            return base
        return base * (1.0 + p.caution - p.aggression)

    # -- Doctrine preference ------------------------------------------------

    def get_preferred_doctrine(self, unit_id: str) -> str | None:
        """Return the preferred doctrine ID, or ``None``."""
        p = self.get_personality(unit_id)
        if p is None:
            return None
        return p.preferred_doctrine

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "assignments": dict(self._assignments),
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._assignments = dict(state["assignments"])
