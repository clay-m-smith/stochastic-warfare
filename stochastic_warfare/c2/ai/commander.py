"""Commander personality engine -- decision-making style and biases.

Commander profiles define individual traits (aggression, caution, flexibility,
initiative, experience) that modulate decision-making throughout the OODA cycle.
Profiles are loaded from YAML and assigned to units.  The engine applies
personality biases to OODA timing, option scoring, and risk thresholds.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.strict_yaml import load_yaml_unique

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CommanderPersonality(BaseModel):
    """A commander's personality profile loaded from YAML.

    All trait values are floats on [0.0, 1.0].
    """

    model_config = ConfigDict(extra="forbid")

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

    @field_validator("profile_id", mode="before")
    @classmethod
    def _valid_profile_id(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                "profile_id must be a non-empty trimmed string",
            )
        return value


class CommanderConfig(BaseModel):
    """Tuning parameters for the commander personality engine."""

    model_config = ConfigDict(extra="forbid")

    ooda_speed_base_mult: float = 1.0
    noise_sigma: float = 0.1
    risk_threshold_base: float = 0.3

    @field_validator(
        "ooda_speed_base_mult",
        "noise_sigma",
        "risk_threshold_base",
        mode="before",
    )
    @classmethod
    def _strict_finite_float(cls, value: Any, info: Any) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, float)
            or not math.isfinite(value)
        ):
            raise ValueError(
                f"{info.field_name} must be a finite strict float",
            )
        if info.field_name == "ooda_speed_base_mult" and value <= 0.0:
            raise ValueError("ooda_speed_base_mult must be greater than zero")
        if info.field_name == "noise_sigma" and value < 0.0:
            raise ValueError("noise_sigma must be non-negative")
        if (
            info.field_name == "risk_threshold_base"
            and not 0.0 <= value <= 1.0
        ):
            raise ValueError("risk_threshold_base must be in [0, 1]")
        return value


class CommanderScenarioConfig(CommanderConfig):
    """Strict scenario tuning and exact per-unit personality overrides."""

    assignments: dict[str, str] = Field(default_factory=dict)

    @field_validator("assignments", mode="before")
    @classmethod
    def _valid_assignments(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise ValueError("commander assignments must be a mapping")
        result: dict[str, str] = {}
        for unit_id, profile_id in value.items():
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or unit_id != unit_id.strip()
            ):
                raise ValueError(
                    "commander assignment unit IDs must be non-empty "
                    "trimmed strings",
                )
            if (
                not isinstance(profile_id, str)
                or not profile_id
                or profile_id != profile_id.strip()
            ):
                raise ValueError(
                    "commander assignment profile IDs must be non-empty "
                    "trimmed strings",
                )
            result[unit_id] = profile_id
        return result

    def engine_config(self) -> CommanderConfig:
        """Return the engine-owned tuning subset."""
        return CommanderConfig(
            ooda_speed_base_mult=self.ooda_speed_base_mult,
            noise_sigma=self.noise_sigma,
            risk_threshold_base=self.risk_threshold_base,
        )

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
        self._sources: dict[str, Path] = {}

    def load_definition(self, path: Path) -> CommanderPersonality:
        """Load a single commander profile YAML file."""
        defn = self._read_definition(path)
        existing = self._sources.get(defn.profile_id)
        if existing is not None:
            raise ValueError(
                f"Duplicate commander profile_id {defn.profile_id!r}: "
                f"{existing} and {path}",
            )
        self._definitions[defn.profile_id] = defn
        self._sources[defn.profile_id] = path
        return defn

    def load_all(self) -> None:
        """Load all ``*.yaml`` files in the data directory."""
        self.load_directories((self._data_dir,))

    def load_directories(self, directories: Sequence[Path]) -> None:
        """Atomically merge ordered catalogs while rejecting duplicate IDs."""
        staged_definitions = dict(self._definitions)
        staged_sources = dict(self._sources)
        for directory in directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.yaml")):
                definition = self._read_definition(path)
                existing = staged_sources.get(definition.profile_id)
                if existing is not None:
                    raise ValueError(
                        "Duplicate commander profile_id "
                        f"{definition.profile_id!r}: {existing} and {path}",
                    )
                staged_definitions[definition.profile_id] = definition
                staged_sources[definition.profile_id] = path
        self._definitions = staged_definitions
        self._sources = staged_sources

    @staticmethod
    def _read_definition(path: Path) -> CommanderPersonality:
        try:
            with open(path, encoding="utf-8") as profile_file:
                data = load_yaml_unique(profile_file)
            return CommanderPersonality.model_validate(data)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid commander profile {path}: {exc}",
            ) from exc

    def get_definition(self, profile_id: str) -> CommanderPersonality:
        """Return a loaded profile by its ``profile_id``."""
        try:
            return self._definitions[profile_id]
        except KeyError as exc:
            raise KeyError(
                f"Commander profile {profile_id!r} is not loaded",
            ) from exc

    def available_profiles(self) -> list[str]:
        """Return all loaded profile IDs."""
        return sorted(self._definitions.keys())

    def definitions(self) -> Mapping[str, CommanderPersonality]:
        """Return a read-only snapshot of the effective merged catalog."""
        return MappingProxyType(dict(self._definitions))


@dataclass(frozen=True)
class CommanderAssignmentPlan:
    """Validated deterministic assignment update."""

    assignments: tuple[tuple[str, str], ...]


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
        plan = self.prepare_assignments({unit_id: profile_id})
        self.commit_assignments(plan)
        logger.debug("Assigned profile %s to unit %s", profile_id, unit_id)

    def prepare_assignments(
        self,
        assignments: Mapping[str, str],
        *,
        expected_unit_ids: set[str] | None = None,
        require_complete: bool = False,
    ) -> CommanderAssignmentPlan:
        """Validate assignments without mutating engine state."""
        staged: list[tuple[str, str]] = []
        for unit_id, profile_id in sorted(assignments.items()):
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or unit_id != unit_id.strip()
            ):
                raise ValueError(
                    "Commander assignment unit IDs must be non-empty "
                    "trimmed strings",
                )
            if (
                not isinstance(profile_id, str)
                or not profile_id
                or profile_id != profile_id.strip()
            ):
                raise ValueError(
                    "Commander assignment profile IDs must be non-empty "
                    "trimmed strings",
                )
            if (
                expected_unit_ids is not None
                and unit_id not in expected_unit_ids
            ):
                raise ValueError(
                    f"Commander assignment references unknown unit {unit_id!r}",
                )
            self._loader.get_definition(profile_id)
            staged.append((unit_id, profile_id))
        if require_complete and expected_unit_ids is not None:
            assigned_ids = {unit_id for unit_id, _ in staged}
            if assigned_ids != expected_unit_ids:
                raise ValueError(
                    "Commander assignment topology must match the exact "
                    "runtime roster: "
                    f"missing={sorted(expected_unit_ids - assigned_ids)!r}, "
                    f"extra={sorted(assigned_ids - expected_unit_ids)!r}",
                )
        return CommanderAssignmentPlan(tuple(staged))

    def commit_assignments(
        self,
        plan: CommanderAssignmentPlan,
        *,
        replace: bool = False,
    ) -> None:
        """Commit a validated assignment plan."""
        assignments = {} if replace else dict(self._assignments)
        assignments.update(plan.assignments)
        self._assignments = assignments

    def assignments(self) -> Mapping[str, str]:
        """Return a read-only snapshot of current assignments."""
        return MappingProxyType(dict(self._assignments))

    def get_personality(self, unit_id: str) -> CommanderPersonality | None:
        """Return the personality for *unit_id*, or ``None`` if unassigned."""
        pid = self._assignments.get(unit_id)
        if pid is None:
            return None
        return self._loader.get_definition(pid)

    def get_profile_definition(
        self,
        profile_id: str,
    ) -> CommanderPersonality:
        """Return one definition from the engine's validated catalog."""
        return self._loader.get_definition(profile_id)

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

    def get_state(self) -> dict[str, Any]:
        """Serialize for checkpoint/restore."""
        return {
            "assignments": dict(sorted(self._assignments.items())),
        }

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_unit_ids: set[str] | None = None,
    ) -> CommanderAssignmentPlan:
        """Validate checkpoint state without mutating live assignments."""
        if set(state) != {"assignments"}:
            raise ValueError(
                "Commander checkpoint state must contain only assignments",
            )
        raw_assignments = state["assignments"]
        if not isinstance(raw_assignments, Mapping):
            raise ValueError(
                "Commander checkpoint assignments must be a mapping",
            )
        return self.prepare_assignments(
            raw_assignments,
            expected_unit_ids=expected_unit_ids,
            require_complete=expected_unit_ids is not None,
        )

    def commit_state(self, plan: CommanderAssignmentPlan) -> None:
        """Replace live assignment state with a validated checkpoint plan."""
        self.commit_assignments(plan, replace=True)

    def set_state(self, state: Mapping[str, Any]) -> None:
        """Restore independently validated checkpoint state."""
        self.commit_state(self.stage_state(state))
