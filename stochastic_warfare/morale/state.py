"""Markov-chain morale state machine.

Models unit morale as a 5-state Markov chain with transition probabilities
driven by casualty rate, suppression, leadership, cohesion, and force ratio.
SURRENDERED is an absorbing state.
"""

from __future__ import annotations

import enum
import math

import numpy as np
from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.numba_utils import optional_jit


# ---------------------------------------------------------------------------
# JIT-compiled morale kernels (Phase 87c)
# ---------------------------------------------------------------------------

_N_MORALE_STATES = 5


@optional_jit
def _transition_matrix_kernel(
    casualty_rate: float,
    suppression_level: float,
    leadership_present_f: float,
    cohesion: float,
    force_ratio: float,
    cbrn_stress: float,
    base_degrade_rate: float,
    casualty_weight: float,
    suppression_weight: float,
    force_ratio_weight: float,
    base_recover_rate: float,
    leadership_weight: float,
    cohesion_weight: float,
) -> np.ndarray:
    """Pure-math discrete morale transition matrix (JIT-compilable).

    Returns a 5x5 row-stochastic matrix.
    ``leadership_present_f`` is 1.0 if leader present, 0.0 otherwise.
    """
    n = _N_MORALE_STATES
    matrix = np.zeros((n, n), dtype=np.float64)

    # Degradation pressure
    degrade = base_degrade_rate
    degrade += casualty_weight * casualty_rate
    degrade += suppression_weight * suppression_level
    if force_ratio < 1.0:
        degrade += force_ratio_weight * (1.0 - force_ratio)
    degrade += cbrn_stress
    if degrade < 0.0:
        degrade = 0.0
    if degrade > 0.8:
        degrade = 0.8

    # Recovery pressure
    recover = base_recover_rate
    if leadership_present_f > 0.5:
        recover += leadership_weight
    recover += cohesion_weight * cohesion
    if force_ratio > 1.0:
        bonus = force_ratio - 1.0
        if bonus > 1.0:
            bonus = 1.0
        recover += force_ratio_weight * bonus * 0.5
    if recover < 0.0:
        recover = 0.0
    if recover > 0.8:
        recover = 0.8

    for i in range(n):
        if i == n - 1:
            # SURRENDERED — absorbing state
            matrix[i, i] = 1.0
            continue

        p_down = degrade * (1.0 + 0.2 * i)
        if p_down > 0.9:
            p_down = 0.9

        p_up = recover * max(0.1, 1.0 - 0.3 * i) if i > 0 else 0.0

        total_trans = p_down + p_up
        if total_trans > 0.95:
            scale = 0.95 / total_trans
            p_down *= scale
            p_up *= scale

        if i < n - 1:
            matrix[i, i + 1] = p_down
        if i > 0:
            matrix[i, i - 1] = p_up
        matrix[i, i] = 1.0 - p_down - p_up

    return matrix


@optional_jit
def _continuous_transition_kernel(
    casualty_rate: float,
    suppression_level: float,
    leadership_present_f: float,
    cohesion: float,
    force_ratio: float,
    dt: float,
    base_degrade_rate: float,
    casualty_weight: float,
    suppression_weight: float,
    force_ratio_weight: float,
    base_recover_rate: float,
    leadership_weight: float,
    cohesion_weight: float,
) -> np.ndarray:
    """Pure-math continuous-time morale transition matrix (JIT-compilable).

    Uses P(transition) = 1 - exp(-lambda * dt).
    Returns a 5x5 row-stochastic matrix.
    """
    n = _N_MORALE_STATES
    matrix = np.zeros((n, n), dtype=np.float64)

    # Degradation rate
    degrade_rate = base_degrade_rate
    degrade_rate += casualty_weight * casualty_rate
    degrade_rate += suppression_weight * suppression_level
    if force_ratio < 1.0:
        degrade_rate += force_ratio_weight * (1.0 - force_ratio)
    if degrade_rate > 2.0:
        degrade_rate = 2.0

    # Recovery rate
    recover_rate = base_recover_rate
    if leadership_present_f > 0.5:
        recover_rate += leadership_weight
    recover_rate += cohesion_weight * cohesion
    if force_ratio > 1.0:
        bonus = force_ratio - 1.0
        if bonus > 1.0:
            bonus = 1.0
        recover_rate += force_ratio_weight * bonus * 0.5
    if recover_rate > 2.0:
        recover_rate = 2.0

    for i in range(n):
        if i == n - 1:
            matrix[i, i] = 1.0
            continue

        lambda_down = degrade_rate * (1.0 + 0.2 * i)
        lambda_up = recover_rate * max(0.1, 1.0 - 0.3 * i) if i > 0 else 0.0

        p_down = 1.0 - math.exp(-lambda_down * dt)
        p_up = 1.0 - math.exp(-lambda_up * dt)

        total_trans = p_down + p_up
        if total_trans > 0.95:
            scale = 0.95 / total_trans
            p_down *= scale
            p_up *= scale

        if i < n - 1:
            matrix[i, i + 1] = p_down
        if i > 0:
            matrix[i, i - 1] = p_up
        matrix[i, i] = 1.0 - p_down - p_up

    return matrix

# ---------------------------------------------------------------------------
# Morale state enum
# ---------------------------------------------------------------------------


class MoraleState(enum.IntEnum):
    """Discrete morale levels from best to worst."""

    STEADY = 0
    SHAKEN = 1
    BROKEN = 2
    ROUTED = 3
    SURRENDERED = 4


class MoraleTransitionCause(enum.StrEnum):
    """Typed production causes for semantic morale transitions."""

    STOCHASTIC = "stochastic"
    RALLY = "rally"
    MELEE_ROUT = "melee_rout"
    ROUT_CASCADE = "rout_cascade"


def validate_morale_state_name(value: str) -> str:
    """Validate and return one exact, case-sensitive morale state name."""
    if value not in MoraleState.__members__:
        allowed = ", ".join(MoraleState.__members__)
        raise ValueError(
            f"morale_initial must be one of {allowed}; got {value!r}",
        )
    return value


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class MoraleConfig(BaseModel):
    """Configurable parameters for morale state transitions.

    Sources:
    - Dupuy, "Attrition" (1990): casualties 2–3× more impactful than
      suppression on unit effectiveness; force ratio contributes ~0.5 weight.
    - Marshall, "Men Against Fire" (1947): ~15–25% degrade in first hour
      under fire; leadership presence improves recovery 20–40%.
    - Shils & Janowitz, "Cohesion and Disintegration in the Wehrmacht"
      (1948): primary group cohesion as dominant morale factor → 0.4 weight.
    - Rowland, "The Stress of Battle" (2006): base degrade ~5%/check,
      recovery ~10%/check under favorable conditions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_degrade_rate: float = 0.05
    """Base probability of degrading one step per check."""

    base_recover_rate: float = 0.10
    """Base probability of recovering one step per check."""

    casualty_weight: float = 2.0
    """Multiplier on casualty_rate contribution to degradation.
    Dupuy: casualties 2–3× more impactful than suppression."""

    suppression_weight: float = 1.5
    """Multiplier on suppression_level contribution to degradation."""

    leadership_weight: float = 0.3
    """Recovery bonus when leadership is present.
    Marshall: leadership improves recovery 20–40%."""

    cohesion_weight: float = 0.4
    """Recovery bonus from unit cohesion.
    Shils & Janowitz: primary group cohesion is the dominant morale factor."""

    force_ratio_weight: float = 0.5
    """Degrade bonus when outnumbered (force_ratio < 1)."""

    transition_cooldown_s: float = 30.0
    """Minimum seconds between morale state transitions."""

    use_continuous_time: bool = False
    """When True, interpret rates as continuous-time Markov chain rates
    and scale by dt, making transitions tick-rate-independent."""


# ---------------------------------------------------------------------------
# Morale state machine
# ---------------------------------------------------------------------------

# Effects multipliers per morale state: accuracy, speed, initiative.
# Source: Dupuy, "Understanding War" (1987), Ch. 3 — combat effectiveness
# degrades non-linearly with morale: SHAKEN ~70%, BROKEN ~30%, ROUTED ~10%.
# Initiative loss is steeper (Rowland: units under extreme stress lose
# offensive capability before defensive).
_MORALE_EFFECTS: dict[MoraleState, dict[str, float]] = {
    MoraleState.STEADY: {"accuracy_mult": 1.0, "speed_mult": 1.0, "initiative_mult": 1.0},
    MoraleState.SHAKEN: {"accuracy_mult": 0.7, "speed_mult": 0.7, "initiative_mult": 0.6},
    MoraleState.BROKEN: {"accuracy_mult": 0.3, "speed_mult": 0.3, "initiative_mult": 0.2},
    MoraleState.ROUTED: {"accuracy_mult": 0.1, "speed_mult": 0.1, "initiative_mult": 0.0},
    MoraleState.SURRENDERED: {"accuracy_mult": 0.0, "speed_mult": 0.0, "initiative_mult": 0.0},
}


class MoraleStateMachine:
    """Stateless Markov-chain morale transition selector.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator``.
    config:
        Morale configuration parameters.

    The machine owns no per-unit semantic state, events, or checkpoint data.
    Its only mutable data is a non-semantic transition-matrix cache.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: MoraleConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or MoraleConfig()
        # Last-result cache for compute_transition_matrix (same-side units
        # share identical parameters within a tick)
        self._cached_matrix_key: tuple[float, ...] | None = None
        self._cached_matrix: np.ndarray | None = None

    @property
    def rng(self) -> np.random.Generator:
        """Return the injected authoritative MORALE generator."""
        return self._rng

    @property
    def config(self) -> MoraleConfig:
        """Return the validated immutable-by-convention configuration."""
        return self._config

    def compute_transition_matrix(
        self,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        cbrn_stress: float = 0.0,
    ) -> np.ndarray:
        """Build a 5x5 morale transition matrix.

        Parameters
        ----------
        casualty_rate:
            Fraction of casualties (0.0–1.0).
        suppression_level:
            Level of suppression (0.0–1.0).
        leadership_present:
            Whether a leader is present with the unit.
        cohesion:
            Unit cohesion factor (0.0–1.0).
        force_ratio:
            Friendly-to-enemy force ratio (>1 = advantage).
        cbrn_stress:
            Additional degradation pressure from CBRN environment (0.0–1.0).

        Returns
        -------
        np.ndarray
            5x5 row-stochastic transition matrix.
        """
        cfg = self._config
        key = (casualty_rate, suppression_level, float(leadership_present), cohesion, force_ratio, cbrn_stress)
        if self._cached_matrix_key == key and self._cached_matrix is not None:
            return self._cached_matrix

        matrix = _transition_matrix_kernel(
            casualty_rate, suppression_level, float(leadership_present),
            cohesion, force_ratio, cbrn_stress,
            cfg.base_degrade_rate, cfg.casualty_weight, cfg.suppression_weight,
            cfg.force_ratio_weight, cfg.base_recover_rate,
            cfg.leadership_weight, cfg.cohesion_weight,
        )

        self._cached_matrix_key = key
        self._cached_matrix = matrix
        return matrix

    def compute_continuous_transition_probs(
        self,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        dt: float,
    ) -> np.ndarray:
        """Build a 5x5 transition matrix using continuous-time rates.

        Uses ``P(transition) = 1 - exp(-λ·dt)`` so that transitions are
        tick-rate-independent.  With ``dt=1.0`` and moderate rates, this
        closely approximates the discrete matrix but scales properly for
        any tick duration.

        Parameters
        ----------
        casualty_rate, suppression_level, leadership_present, cohesion, force_ratio:
            Same semantics as :meth:`compute_transition_matrix`.
        dt:
            Time step duration in seconds.

        Returns
        -------
        np.ndarray
            5x5 row-stochastic transition matrix.
        """
        cfg = self._config
        return _continuous_transition_kernel(
            casualty_rate, suppression_level, float(leadership_present),
            cohesion, force_ratio, dt,
            cfg.base_degrade_rate, cfg.casualty_weight, cfg.suppression_weight,
            cfg.force_ratio_weight, cfg.base_recover_rate,
            cfg.leadership_weight, cfg.cohesion_weight,
        )

    def select_transition(
        self,
        current_state: MoraleState,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        *,
        dt: float,
        cbrn_stress: float = 0.0,
    ) -> MoraleState:
        """Consume one draw and select one adjacent stochastic state."""
        if not isinstance(current_state, MoraleState):
            raise TypeError("current_state must be a MoraleState")
        if (
            isinstance(dt, bool)
            or not isinstance(dt, (int, float))
            or not math.isfinite(float(dt))
            or float(dt) <= 0.0
        ):
            raise ValueError("dt must be a finite positive number")

        if self._config.use_continuous_time:
            matrix = self.compute_continuous_transition_probs(
                casualty_rate, suppression_level, leadership_present,
                cohesion, force_ratio, float(dt),
            )
        else:
            matrix = self.compute_transition_matrix(
                casualty_rate, suppression_level, leadership_present, cohesion, force_ratio,
                cbrn_stress=cbrn_stress,
            )

        row = matrix[int(current_state)]
        roll = self._rng.random()

        cumulative = 0.0
        new_state = current_state
        for j in range(len(MoraleState)):
            cumulative += row[j]
            if roll < cumulative:
                new_state = MoraleState(j)
                break
        return new_state

    @staticmethod
    def apply_morale_effects(state: MoraleState) -> dict[str, float]:
        """Return effectiveness multipliers for the given morale state."""
        return _MORALE_EFFECTS[state]
