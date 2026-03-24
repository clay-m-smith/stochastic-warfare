"""Negotiated war termination -- ceasefire and capitulation logic.

Phase 24f.  Evaluates mutual willingness to negotiate and triggers
ceasefire when both sides cross threshold during stalemate.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class WarTerminationConfig(BaseModel):
    """Configuration for war termination negotiation logic."""

    ceasefire_threshold: float = 0.7
    """Willingness threshold at which a side will accept ceasefire."""

    armistice_delay_hours: float = 48.0
    """Hours between ceasefire activation and formal armistice."""

    min_stalemate_for_negotiation_hours: float = 72.0
    """Minimum stalemate duration (hours) before negotiations can begin."""

    capitulation_threshold: float = 0.95
    """Threshold for unilateral capitulation (desperation + political)."""

    territory_weight: float = 0.4
    """Weight of territory loss in willingness computation."""

    force_correlation_weight: float = 0.3
    """Weight of unfavourable force correlation trend."""

    political_weight: float = 0.3
    """Weight of political pressure in willingness computation."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class WarTerminationEngine:
    """Evaluate negotiation willingness and trigger ceasefire/capitulation.

    Parameters
    ----------
    event_bus : EventBus
        EventBus for publishing termination events.
    config : WarTerminationConfig | None
        Configuration.  Defaults are used when ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: WarTerminationConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or WarTerminationConfig()
        self._willingness: dict[str, float] = {}
        self._ceasefire_active: bool = False
        self._ceasefire_time: datetime | None = None

    # -- Public API ---------------------------------------------------------

    def evaluate_negotiation_willingness(
        self,
        side: str,
        territory_control_fraction: float,
        territory_objective_fraction: float,
        force_correlation_trend: float,
        domestic_pressure: float,
        international_pressure: float,
        coalition_pressure: float,
    ) -> float:
        """Compute willingness to negotiate in [0, 1].

        Parameters
        ----------
        side : str
            Side identifier.
        territory_control_fraction : float
            Fraction of map territory currently controlled [0, 1].
        territory_objective_fraction : float
            Fraction of objectives currently held [0, 1].
        force_correlation_trend : float
            Favourable force trend [0, 1] -- 1.0 means winning decisively.
        domestic_pressure : float
            Domestic political pressure [0, 1].
        international_pressure : float
            International political pressure [0, 1].
        coalition_pressure : float
            Coalition fracture pressure [0, 1].

        Returns
        -------
        float
            Negotiation willingness clamped to [0, 1].
        """
        cfg = self._config

        willingness = (
            cfg.territory_weight * (1.0 - territory_objective_fraction)
            + cfg.force_correlation_weight * (1.0 - force_correlation_trend)
            + cfg.political_weight * max(
                domestic_pressure,
                international_pressure,
                coalition_pressure,
            )
        )
        willingness = min(1.0, max(0.0, willingness))
        self._willingness[side] = willingness

        logger.debug(
            "WarTermination willingness[%s]: terr=%.3f force=%.3f pol=%.3f => %.3f",
            side,
            1.0 - territory_objective_fraction,
            1.0 - force_correlation_trend,
            max(domestic_pressure, international_pressure, coalition_pressure),
            willingness,
        )
        return willingness

    def check_ceasefire(
        self,
        willingness_by_side: dict[str, float],
        stalemate_duration_hours: float,
        timestamp: datetime,
    ) -> bool:
        """Check whether all sides are willing to accept a ceasefire.

        Parameters
        ----------
        willingness_by_side : dict[str, float]
            Negotiation willingness per side [0, 1].
        stalemate_duration_hours : float
            Duration of stalemate in hours.
        timestamp : datetime
            Current simulation time.

        Returns
        -------
        bool
            ``True`` if ceasefire is triggered.
        """
        cfg = self._config

        if stalemate_duration_hours < cfg.min_stalemate_for_negotiation_hours:
            return False

        all_willing = all(
            w >= cfg.ceasefire_threshold
            for w in willingness_by_side.values()
        )

        if all_willing:
            self._ceasefire_active = True
            self._ceasefire_time = timestamp
            logger.info(
                "Ceasefire activated at %s (stalemate=%.1fh, willingness=%s)",
                timestamp,
                stalemate_duration_hours,
                {s: f"{w:.3f}" for s, w in willingness_by_side.items()},
            )
            return True

        return False

    def check_capitulation(
        self,
        side: str,
        desperation: float,
        political_pressure: float,
        timestamp: datetime,
    ) -> bool:
        """Check if a side capitulates unilaterally.

        Parameters
        ----------
        side : str
            Side identifier.
        desperation : float
            Desperation index [0, 1].
        political_pressure : float
            Combined political pressure [0, 1].
        timestamp : datetime
            Current simulation time.

        Returns
        -------
        bool
            ``True`` if capitulation threshold is exceeded.
        """
        combined = desperation + political_pressure
        if combined > self._config.capitulation_threshold:
            logger.info(
                "Capitulation[%s]: desperation=%.3f + political=%.3f = %.3f > %.3f",
                side,
                desperation,
                political_pressure,
                combined,
                self._config.capitulation_threshold,
            )
            return True
        return False

    def activate_ceasefire(self, timestamp: datetime) -> None:
        """Force-activate ceasefire at *timestamp*."""
        self._ceasefire_active = True
        self._ceasefire_time = timestamp
        logger.info("Ceasefire force-activated at %s", timestamp)

    def is_ceasefire_active(self) -> bool:
        """Return whether a ceasefire is currently active."""
        return self._ceasefire_active

    def get_willingness(self, side: str) -> float:
        """Return stored willingness for *side* (0.0 if not set)."""
        return self._willingness.get(side, 0.0)

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Capture war termination state for checkpointing."""
        return {
            "willingness": dict(self._willingness),
            "ceasefire_active": self._ceasefire_active,
            "ceasefire_time": (
                self._ceasefire_time.isoformat()
                if self._ceasefire_time is not None
                else None
            ),
        }

    def set_state(self, state: dict) -> None:
        """Restore war termination state from checkpoint."""
        self._willingness = dict(state.get("willingness", {}))
        self._ceasefire_active = state.get("ceasefire_active", False)
        ct = state.get("ceasefire_time")
        if ct is not None:
            self._ceasefire_time = datetime.fromisoformat(ct)
        else:
            self._ceasefire_time = None
