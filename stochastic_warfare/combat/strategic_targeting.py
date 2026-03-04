"""Strategic targeting — target priority lists and effect chains.

Phase 12f-3. Generates target priority lists, applies strikes with
cascading infrastructure effects, runs BDA with overestimate bias,
and regenerates targets over time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class StrategicTarget:
    """A strategic target with health and repair dynamics."""

    target_id: str
    target_type: str  # "bridge", "factory", "airfield", "power_plant", "depot"
    position: Position
    infrastructure_id: str | None = None
    health: float = 1.0  # 0.0 = destroyed, 1.0 = operational
    repair_rate: float = 0.01  # health restored per hour


class TargetEffectChain(BaseModel):
    """Maps target types to operational effects."""

    target_type: str
    effect_type: str  # "supply_severed", "production_reduced", "sortie_reduced"
    effect_magnitude: float = 1.0
    """Magnitude of effect when target is fully destroyed."""


class StrategicTargetingConfig(BaseModel):
    """Strategic targeting configuration."""

    bda_overestimate_factor: float = 3.0
    """Historical tendency to overestimate BDA (lognormal bias)."""
    bda_noise_sigma: float = 0.5
    """Lognormal sigma for BDA assessment noise."""
    target_type_weights: dict[str, float] = {
        "bridge": 1.5,
        "factory": 2.0,
        "airfield": 1.8,
        "power_plant": 2.5,
        "depot": 1.2,
    }
    """Priority weights per target type for TPL generation."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class StrategicTargetingEngine:
    """Strategic targeting with priority lists and effect chains.

    Parameters
    ----------
    event_bus : EventBus
        For publishing events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : StrategicTargetingConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: StrategicTargetingConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or StrategicTargetingConfig()
        self._targets: dict[str, StrategicTarget] = {}
        self._effect_chains: list[TargetEffectChain] = []

    def register_target(self, target: StrategicTarget) -> None:
        """Register a strategic target."""
        self._targets[target.target_id] = target

    def register_effect_chain(self, chain: TargetEffectChain) -> None:
        """Register a target-effect chain."""
        self._effect_chains.append(chain)

    def get_target(self, target_id: str) -> StrategicTarget:
        """Return a target; raises ``KeyError`` if not found."""
        return self._targets[target_id]

    def generate_tpl(
        self,
        commander_priorities: dict[str, float] | None = None,
    ) -> list[tuple[str, float]]:
        """Generate a Target Priority List.

        Parameters
        ----------
        commander_priorities:
            Optional per-target-type priority overrides.

        Returns
        -------
        list[tuple[str, float]]
            List of (target_id, priority_score) sorted descending.
        """
        cfg = self._config
        weights = dict(cfg.target_type_weights)
        if commander_priorities:
            weights.update(commander_priorities)

        scored: list[tuple[str, float]] = []
        for target in self._targets.values():
            if target.health <= 0.0:
                continue  # already destroyed
            type_weight = weights.get(target.target_type, 1.0)
            # Priority inversely proportional to current health
            # (damaged targets need fewer resources to destroy)
            score = type_weight * (1.0 + (1.0 - target.health))
            scored.append((target.target_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def apply_strike(
        self,
        target_id: str,
        damage: float,
        infrastructure_manager: Any = None,
        supply_network: Any = None,
    ) -> list[dict]:
        """Apply a strike to a target and cascade effects.

        Parameters
        ----------
        target_id:
            Target to strike.
        damage:
            Damage amount (0-1).
        infrastructure_manager:
            Optional infrastructure manager for cascading damage.
        supply_network:
            Optional supply network for route severing on bridge destruction.

        Returns
        -------
        list[dict]
            Cascading effects triggered.
        """
        target = self._targets[target_id]
        old_health = target.health
        target.health = max(0.0, target.health - damage)
        effects: list[dict] = []

        logger.info(
            "Strike on %s (%s): health %.2f -> %.2f",
            target_id, target.target_type, old_health, target.health,
        )

        # Cascade to infrastructure
        if infrastructure_manager and target.infrastructure_id:
            if hasattr(infrastructure_manager, "damage"):
                infrastructure_manager.damage(target.infrastructure_id, damage)

        # Apply target-effect chains
        for chain in self._effect_chains:
            if chain.target_type == target.target_type:
                effect_amount = chain.effect_magnitude * (1.0 - target.health)
                effect = {
                    "target_id": target_id,
                    "effect_type": chain.effect_type,
                    "effect_amount": effect_amount,
                }
                effects.append(effect)

                # Special: bridge destruction severs supply routes
                if (chain.effect_type == "supply_severed"
                        and target.health <= 0.0
                        and supply_network
                        and target.infrastructure_id):
                    if hasattr(supply_network, "sever_route"):
                        affected = supply_network.sever_route(target.infrastructure_id)
                        effect["affected_units"] = affected

        return effects

    def run_bda_cycle(self, target_id: str) -> float:
        """Run a Battle Damage Assessment cycle.

        Returns assessed damage (0-1), with historical overestimate bias.
        The assessed value is drawn from a lognormal distribution centered
        on the true damage, biased upward.
        """
        cfg = self._config
        target = self._targets[target_id]
        true_damage = 1.0 - target.health

        if true_damage <= 0.0:
            return 0.0

        # Lognormal with upward bias
        log_true = math.log(max(true_damage, 0.01))
        log_assessed = log_true + math.log(cfg.bda_overestimate_factor) * 0.3
        assessed = math.exp(
            self._rng.normal(log_assessed, cfg.bda_noise_sigma)
        )
        return min(1.0, assessed)

    def update_regeneration(self, dt_hours: float) -> None:
        """Regenerate (repair) all damaged targets over time."""
        for target in self._targets.values():
            if 0.0 < target.health < 1.0:
                target.health = min(1.0, target.health + target.repair_rate * dt_hours)

    # -- State protocol --

    def get_state(self) -> dict:
        return {
            "targets": {
                tid: {
                    "target_id": t.target_id,
                    "target_type": t.target_type,
                    "position": list(t.position),
                    "infrastructure_id": t.infrastructure_id,
                    "health": t.health,
                    "repair_rate": t.repair_rate,
                }
                for tid, t in self._targets.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._targets.clear()
        for tid, td in state["targets"].items():
            self._targets[tid] = StrategicTarget(
                target_id=td["target_id"],
                target_type=td["target_type"],
                position=Position(*td["position"]),
                infrastructure_id=td.get("infrastructure_id"),
                health=td["health"],
                repair_rate=td.get("repair_rate", 0.01),
            )
