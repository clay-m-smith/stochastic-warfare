"""Suppression modeling — fire volume, decay, spreading, effects.

Suppression is caused by incoming fire volume and caliber, independent
of whether rounds hit.  It decays over time and can spread through
formations.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

# Constant suppression effects per level
_SUPPRESSION_EFFECTS: dict[int, dict[str, float]] = {
    0: {"accuracy_penalty": 0.0, "movement_speed_factor": 1.0, "morale_modifier": 0.0},
    1: {"accuracy_penalty": 0.1, "movement_speed_factor": 0.9, "morale_modifier": -0.05},
    2: {"accuracy_penalty": 0.25, "movement_speed_factor": 0.7, "morale_modifier": -0.15},
    3: {"accuracy_penalty": 0.5, "movement_speed_factor": 0.3, "morale_modifier": -0.30},
    4: {"accuracy_penalty": 0.8, "movement_speed_factor": 0.0, "morale_modifier": -0.50},
}


class SuppressionLevel(enum.IntEnum):
    """Graduated suppression state."""

    NONE = 0
    LIGHT = 1
    MODERATE = 2
    HEAVY = 3
    PINNED = 4


class SuppressionConfig(BaseModel):
    """Tunable parameters for suppression computation."""

    caliber_weight: float = 0.01  # suppression per mm of caliber per rpm
    volume_weight: float = 0.002  # suppression per round/min
    decay_rate: float = 0.1  # suppression decay per second
    spread_factor: float = 0.3  # fraction of suppression that spreads
    spread_max_distance_m: float = 50.0  # max distance for suppression spread
    light_threshold: float = 0.15
    moderate_threshold: float = 0.35
    heavy_threshold: float = 0.60
    pinned_threshold: float = 0.85


@dataclass
class SuppressionResult:
    """Result of applying suppression."""

    suppression_value: float  # 0.0–1.0
    level: SuppressionLevel
    effects: dict[str, float]  # accuracy_penalty, movement_factor, morale_mod


@dataclass
class UnitSuppressionState:
    """Per-unit suppression tracking."""

    value: float = 0.0  # 0.0–1.0 continuous suppression
    source_direction: float = 0.0  # radians from north

    def get_state(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source_direction": self.source_direction,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.value = state["value"]
        self.source_direction = state["source_direction"]


class SuppressionEngine:
    """Computes and manages suppression effects.

    Parameters
    ----------
    event_bus:
        For publishing suppression events.
    rng:
        PRNG generator for stochastic variation.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SuppressionConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SuppressionConfig()

    def _level_from_value(self, value: float) -> SuppressionLevel:
        """Map continuous suppression to discrete level."""
        cfg = self._config
        if value >= cfg.pinned_threshold:
            return SuppressionLevel.PINNED
        if value >= cfg.heavy_threshold:
            return SuppressionLevel.HEAVY
        if value >= cfg.moderate_threshold:
            return SuppressionLevel.MODERATE
        if value >= cfg.light_threshold:
            return SuppressionLevel.LIGHT
        return SuppressionLevel.NONE

    def apply_fire_volume(
        self,
        state: UnitSuppressionState,
        rounds_per_minute: float,
        caliber_mm: float,
        range_m: float,
        duration_s: float,
        source_direction: float = 0.0,
    ) -> SuppressionResult:
        """Apply incoming fire volume to a unit's suppression state.

        Parameters
        ----------
        state:
            Current suppression state (modified in-place).
        rounds_per_minute:
            Fire rate of incoming fire.
        caliber_mm:
            Caliber of incoming rounds in mm.
        range_m:
            Range of the firing unit (closer → more suppression).
        duration_s:
            Duration of the fire burst in seconds.
        source_direction:
            Direction of incoming fire in radians.
        """
        cfg = self._config

        # Base suppression from fire volume and caliber
        volume_effect = cfg.volume_weight * rounds_per_minute * (duration_s / 60.0)
        caliber_effect = cfg.caliber_weight * caliber_mm

        # Range factor: closer fire is more suppressive
        range_factor = max(0.2, 1.0 - range_m / 5000.0)

        # Stochastic variation
        noise = 1.0 + 0.1 * float(self._rng.standard_normal())
        noise = max(0.5, noise)

        suppression_delta = (volume_effect + caliber_effect) * range_factor * noise
        state.value = min(1.0, state.value + suppression_delta)
        state.source_direction = source_direction

        level = self._level_from_value(state.value)
        effects = self.compute_suppression_effect(level)

        return SuppressionResult(
            suppression_value=state.value,
            level=level,
            effects=effects,
        )

    def compute_suppression_effect(self, level: SuppressionLevel) -> dict[str, float]:
        """Return combat effects for a given suppression level."""
        return _SUPPRESSION_EFFECTS[int(level)]

    def update_suppression(
        self,
        state: UnitSuppressionState,
        dt: float,
    ) -> None:
        """Decay suppression over time.

        Parameters
        ----------
        state:
            Unit suppression state to update.
        dt:
            Time elapsed in seconds.
        """
        decay = self._config.decay_rate * dt
        state.value = max(0.0, state.value - decay)

    def spread_suppression(
        self,
        source_state: UnitSuppressionState,
        neighbor_states: list[tuple[UnitSuppressionState, float]],
    ) -> None:
        """Spread suppression to nearby units (convolution-like).

        Parameters
        ----------
        source_state:
            The suppressed unit.
        neighbor_states:
            List of (neighbor_state, distance_m) pairs.
        """
        cfg = self._config
        for neighbor, distance_m in neighbor_states:
            if distance_m > cfg.spread_max_distance_m:
                continue
            distance_factor = 1.0 - distance_m / cfg.spread_max_distance_m
            spread = source_state.value * cfg.spread_factor * distance_factor
            neighbor.value = min(1.0, neighbor.value + spread)

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
