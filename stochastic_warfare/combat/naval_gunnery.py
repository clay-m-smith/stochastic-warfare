"""WW2 naval gunnery — bracket firing, fire control, and hit probability.

Models pre-guided-munition naval surface engagements where guns converge
on target via successive bracketing salvos.  Distinct from
:mod:`combat.naval_surface` (modern missile salvo exchange) and
:mod:`combat.naval_gunfire_support` (shore bombardment).

Physics
-------
* Initial bracket ~400 m around target.
* Each salvo adjusts the bracket by ``correction_factor * error``.
* Mechanical fire control (quality 0.5-0.7) converges faster than
  visual spotting (0.3-0.5).
* Once bracket < straddle width, hit probability rises significantly.
* Per-shell hit probability uses 2-D Gaussian dispersion (range x deflection).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NavalGunneryConfig(BaseModel):
    """Configuration for WW2-era naval gunnery.

    Sources:
    - Bracket convergence: Campbell, "Naval Weapons of World War Two" (1985),
      Ch. 1 — typical initial bracket 400m, correction 30-50% per salvo.
    - Hit probabilities: Friedman, "Naval Firepower" (2008), Ch. 4 — straddle
      Pk ~3-8% per shell for 14-16" guns at 15-20 kyd.
    - Dispersion: Jurens, "The Evolution of Battleship Gunnery in the US Navy,
      1920-1945", Warship International (1991) — 5 mrad range, 2 mrad deflection.
    """

    initial_bracket_m: float = 400.0
    """Initial bracket width in meters around the estimated target range."""

    straddle_width_m: float = 100.0
    """Bracket width at which a straddle is considered achieved."""

    spotting_correction_factor: float = 0.4
    """Correction factor per salvo for visual spotting (0.3-0.5)."""

    fire_control_accuracy: float = 0.5
    """Fire control quality (0.3 = visual only, 0.5-0.7 = mechanical FC)."""

    range_dispersion_mrad: float = 5.0
    """1-sigma range dispersion in milliradians."""

    deflection_dispersion_mrad: float = 2.0
    """1-sigma deflection (cross-range) dispersion in milliradians."""

    base_hit_probability_at_straddle: float = 0.05
    """Per-shell hit probability when at straddle range and conditions."""


# ---------------------------------------------------------------------------
# Bracket state
# ---------------------------------------------------------------------------


@dataclass
class BracketState:
    """Tracks the current bracket for one firing ship against one target."""

    target_id: str
    bracket_width_m: float = 400.0
    salvos_fired: int = 0
    straddle_achieved: bool = False
    range_error_m: float = 0.0
    """Current estimated range error (positive = over, negative = short)."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NavalGunneryEngine:
    """WW2 naval gunnery fire control engine.

    Parameters
    ----------
    config:
        Gunnery configuration.
    rng:
        Numpy random generator for stochastic dispersion.
    """

    def __init__(
        self,
        config: NavalGunneryConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or NavalGunneryConfig()
        self._rng = rng
        self._brackets: dict[tuple[str, str], BracketState] = {}

    def get_bracket(self, firer_id: str, target_id: str) -> BracketState:
        """Get or create bracket state for a firer-target pair."""
        key = (firer_id, target_id)
        if key not in self._brackets:
            self._brackets[key] = BracketState(
                target_id=target_id,
                bracket_width_m=self._config.initial_bracket_m,
                range_error_m=self._config.initial_bracket_m * (self._rng.random() - 0.5),
            )
        return self._brackets[key]

    def update_bracket(
        self,
        firer_id: str,
        target_id: str,
        fire_control_quality: float | None = None,
    ) -> BracketState:
        """Update bracket after a salvo observation.

        Parameters
        ----------
        firer_id:
            Identifier of the firing ship.
        target_id:
            Identifier of the target.
        fire_control_quality:
            Override for fire control accuracy (0.3-0.7).

        Returns
        -------
        Updated bracket state.
        """
        bracket = self.get_bracket(firer_id, target_id)
        bracket.salvos_fired += 1

        fcq = fire_control_quality or self._config.fire_control_accuracy
        correction = self._config.spotting_correction_factor + (fcq - 0.5) * 0.4

        # Correct range error — apply correction with some noise
        noise = self._rng.normal(0, 0.1)
        bracket.range_error_m *= (1.0 - correction + noise)

        # Shrink bracket
        shrink = correction * 0.5
        bracket.bracket_width_m *= (1.0 - shrink)
        bracket.bracket_width_m = max(bracket.bracket_width_m, 10.0)

        if bracket.bracket_width_m <= self._config.straddle_width_m:
            bracket.straddle_achieved = True

        return bracket

    def compute_hit_probability(
        self,
        range_m: float,
        target_length_m: float,
        target_beam_m: float,
        bracket: BracketState,
        num_guns: int = 1,
    ) -> float:
        """Compute per-salvo hit probability.

        Parameters
        ----------
        range_m:
            Range to target in meters.
        target_length_m:
            Target ship length in meters.
        target_beam_m:
            Target ship beam (width) in meters.
        bracket:
            Current bracket state.
        num_guns:
            Number of guns firing in the salvo.

        Returns
        -------
        Probability that at least one shell hits (0.0 - 1.0).
        """
        if range_m <= 0:
            return 0.0

        # Dispersion at range (1-sigma in meters)
        sigma_range = range_m * self._config.range_dispersion_mrad / 1000.0
        sigma_defl = range_m * self._config.deflection_dispersion_mrad / 1000.0

        # Per-shell hit probability using 2D Gaussian overlap
        # Probability of landing within target rectangle
        if sigma_range <= 0 or sigma_defl <= 0:
            return 0.0

        # Range offset from bracket error
        offset_range = abs(bracket.range_error_m)

        # Probability in range dimension
        p_range = (
            _norm_cdf((target_length_m / 2 - offset_range) / sigma_range)
            - _norm_cdf((-target_length_m / 2 - offset_range) / sigma_range)
        )

        # Probability in deflection dimension (centered)
        p_defl = 2.0 * _norm_cdf(target_beam_m / (2.0 * sigma_defl)) - 1.0

        p_hit_per_shell = max(0.0, p_range * p_defl)

        # Straddle bonus
        if bracket.straddle_achieved:
            p_hit_per_shell = max(p_hit_per_shell, self._config.base_hit_probability_at_straddle)

        # At least one hit from num_guns shells
        p_miss_all = (1.0 - p_hit_per_shell) ** num_guns
        return 1.0 - p_miss_all

    def fire_salvo(
        self,
        firer_id: str,
        target_id: str,
        range_m: float,
        target_length_m: float,
        target_beam_m: float,
        num_guns: int,
        fire_control_quality: float | None = None,
    ) -> dict[str, Any]:
        """Fire a salvo and return results.

        Combines bracket update and hit probability computation.

        Returns
        -------
        dict with keys: ``hits``, ``hit_probability``, ``bracket``.
        """
        bracket = self.update_bracket(firer_id, target_id, fire_control_quality)

        p_hit = self.compute_hit_probability(
            range_m, target_length_m, target_beam_m, bracket, num_guns,
        )

        # Determine actual hits per shell
        hits = 0
        for _ in range(num_guns):
            p_shell = p_hit / num_guns if num_guns > 0 else 0
            # Use individual per-shell probability
            p_shell = min(1.0, max(0.0, p_hit))
            # Bernoulli per shell using per-shell base probability
            sigma_range = range_m * self._config.range_dispersion_mrad / 1000.0
            sigma_defl = range_m * self._config.deflection_dispersion_mrad / 1000.0
            if sigma_range > 0 and sigma_defl > 0:
                offset = abs(bracket.range_error_m)
                p_r = (
                    _norm_cdf((target_length_m / 2 - offset) / sigma_range)
                    - _norm_cdf((-target_length_m / 2 - offset) / sigma_range)
                )
                p_d = 2.0 * _norm_cdf(target_beam_m / (2.0 * sigma_defl)) - 1.0
                p_per = max(0.0, p_r * p_d)
                if bracket.straddle_achieved:
                    p_per = max(p_per, self._config.base_hit_probability_at_straddle)
            else:
                p_per = 0.0
            if self._rng.random() < p_per:
                hits += 1

        return {
            "hits": hits,
            "hit_probability": p_hit,
            "bracket": bracket,
            "salvos_fired": bracket.salvos_fired,
            "straddle_achieved": bracket.straddle_achieved,
        }

    def reset(self, firer_id: str | None = None) -> None:
        """Reset bracket state.  If *firer_id* given, only for that ship."""
        if firer_id is None:
            self._brackets.clear()
        else:
            to_remove = [k for k in self._brackets if k[0] == firer_id]
            for k in to_remove:
                del self._brackets[k]

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "brackets": {
                f"{k[0]}:{k[1]}": {
                    "target_id": v.target_id,
                    "bracket_width_m": v.bracket_width_m,
                    "salvos_fired": v.salvos_fired,
                    "straddle_achieved": v.straddle_achieved,
                    "range_error_m": v.range_error_m,
                }
                for k, v in self._brackets.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._brackets.clear()
        for key_str, bdata in state.get("brackets", {}).items():
            parts = key_str.split(":", 1)
            if len(parts) == 2:
                self._brackets[(parts[0], parts[1])] = BracketState(**bdata)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))
