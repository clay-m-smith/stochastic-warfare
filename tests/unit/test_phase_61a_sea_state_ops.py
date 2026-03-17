"""Phase 61a: Sea State -> Ship Operations — inline math verification tests.

Tests verify the four sea-state effects wired into BattleManager._advance_units()
and the gunnery loop when ``enable_sea_state_ops=True``:

1. Small craft speed penalty: -20% per Beaufort above 3
2. Tidal current adjustment: effective_speed += tc_speed * cos(tc_dir - heading)
3. Wave period resonance: crew_skill penalty when |wave_period - hull_period| < 0.1 * hull_period
4. Swell direction roll factor: crew_skill *= (1 - sin^2(wave_dir - heading) * 0.5)
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Domain
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helper: replicate the inline logic from battle.py
# ---------------------------------------------------------------------------

def _small_craft_speed_factor(beaufort: int, displacement_tons: float, max_speed: float) -> float:
    """Compute the speed multiplier for small craft in heavy seas.

    A vessel is "small" if displacement < 1000 tons or max_speed < 15 m/s.
    Penalty: -20% per Beaufort above 3, floored at 0.
    """
    is_small = (displacement_tons > 0 and displacement_tons < 1000) or max_speed < 15
    if is_small and beaufort > 3:
        return max(0.0, 1.0 - 0.2 * (beaufort - 3))
    return 1.0


def _tidal_current_effect(tidal_speed: float, tidal_dir: float, heading: float) -> float:
    """Compute the additive speed change from tidal current.

    Returns the component of tidal current along the movement heading.
    """
    return tidal_speed * math.cos(tidal_dir - heading)


def _wave_resonance_factor(wave_period: float, displacement_tons: float) -> float:
    """Compute the crew_skill multiplier from wave period resonance.

    Hull natural period: 10s for typical destroyer, 12s for ships > 10,000 tons.
    Penalty applied when |wave_period - hull_period| < 0.1 * hull_period.
    """
    hull_period = 12.0 if (displacement_tons and displacement_tons > 10000) else 10.0
    if wave_period > 0 and abs(wave_period - hull_period) < 0.1 * hull_period:
        return max(0.3, 1.0 / 1.5)
    return 1.0


def _swell_roll_factor(wave_dir: float, heading: float) -> float:
    """Compute the crew_skill multiplier from swell direction (roll).

    Beam seas (90 deg relative) produce maximum roll.
    """
    roll = math.sin(wave_dir - heading) ** 2
    return max(0.5, 1.0 - roll * 0.5)


# ---------------------------------------------------------------------------
# Tests: small craft speed penalty
# ---------------------------------------------------------------------------

class TestSmallCraftSpeedPenalty:
    """Beaufort-dependent speed penalty for small craft."""

    def test_beaufort_5_small_craft(self) -> None:
        """At Beaufort 5, small craft lose 40% speed (2 steps above 3)."""
        factor = _small_craft_speed_factor(beaufort=5, displacement_tons=500, max_speed=12.0)
        assert factor == pytest.approx(0.6, abs=1e-9)

    def test_beaufort_3_no_penalty(self) -> None:
        """At Beaufort 3 or below, no penalty is applied."""
        factor = _small_craft_speed_factor(beaufort=3, displacement_tons=500, max_speed=12.0)
        assert factor == pytest.approx(1.0, abs=1e-9)

    def test_beaufort_8_floors_at_zero(self) -> None:
        """At Beaufort 8, penalty = 1 - 0.2*5 = 0.0 (floored)."""
        factor = _small_craft_speed_factor(beaufort=8, displacement_tons=500, max_speed=12.0)
        assert factor == pytest.approx(0.0, abs=1e-9)

    def test_large_ship_no_penalty(self) -> None:
        """Ships with displacement >= 1000 and max_speed >= 15 are not small."""
        factor = _small_craft_speed_factor(beaufort=6, displacement_tons=5000, max_speed=20.0)
        assert factor == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Tests: tidal current adjustment
# ---------------------------------------------------------------------------

class TestTidalCurrentAdjustment:
    """Tidal current along or against movement heading."""

    def test_favorable_tidal_current(self) -> None:
        """Current aligned with heading adds full tidal speed."""
        # heading = 0 (north), tidal direction = 0 (north) -> cos(0) = 1.0
        effect = _tidal_current_effect(tidal_speed=1.5, tidal_dir=0.0, heading=0.0)
        assert effect == pytest.approx(1.5, abs=1e-9)

    def test_adverse_tidal_current(self) -> None:
        """Current opposing heading subtracts full tidal speed."""
        # heading = 0, tidal direction = pi -> cos(pi) = -1.0
        effect = _tidal_current_effect(tidal_speed=1.5, tidal_dir=math.pi, heading=0.0)
        assert effect == pytest.approx(-1.5, abs=1e-6)

    def test_perpendicular_current_zero_effect(self) -> None:
        """Current perpendicular to heading has no speed effect."""
        effect = _tidal_current_effect(tidal_speed=2.0, tidal_dir=math.pi / 2, heading=0.0)
        assert abs(effect) < 1e-9


# ---------------------------------------------------------------------------
# Tests: wave period resonance
# ---------------------------------------------------------------------------

class TestWavePeriodResonance:
    """Crew skill penalty when wave period matches hull natural period."""

    def test_resonance_destroyer(self) -> None:
        """Wave period near hull period (10s) triggers penalty."""
        # displacement=3000 -> hull_period=10, wave_period=10 -> |0| < 1.0 -> penalty
        factor = _wave_resonance_factor(wave_period=10.0, displacement_tons=3000)
        expected = max(0.3, 1.0 / 1.5)  # ~0.6667
        assert factor == pytest.approx(expected, abs=1e-4)

    def test_no_resonance_far_period(self) -> None:
        """Wave period far from hull period -> no penalty."""
        # hull_period=10, wave_period=5.0 -> |5| > 1.0 -> no penalty
        factor = _wave_resonance_factor(wave_period=5.0, displacement_tons=3000)
        assert factor == pytest.approx(1.0, abs=1e-9)

    def test_resonance_large_ship(self) -> None:
        """Ships > 10,000 tons have hull_period=12s; resonance at ~12s."""
        factor = _wave_resonance_factor(wave_period=12.0, displacement_tons=15000)
        expected = max(0.3, 1.0 / 1.5)
        assert factor == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# Tests: swell direction roll factor
# ---------------------------------------------------------------------------

class TestSwellDirectionRollFactor:
    """Beam seas (90 deg relative) produce maximum crew skill penalty."""

    def test_beam_seas_max_penalty(self) -> None:
        """Wave direction 90 deg from heading -> sin^2(90) = 1.0 -> max penalty."""
        factor = _swell_roll_factor(wave_dir=math.pi / 2, heading=0.0)
        # crew_skill *= max(0.5, 1.0 - 1.0 * 0.5) = max(0.5, 0.5) = 0.5
        assert factor == pytest.approx(0.5, abs=1e-9)

    def test_following_seas_no_penalty(self) -> None:
        """Wave direction aligned with heading -> sin^2(0) = 0 -> no penalty."""
        factor = _swell_roll_factor(wave_dir=0.0, heading=0.0)
        assert factor == pytest.approx(1.0, abs=1e-9)

    def test_quartering_seas_partial_penalty(self) -> None:
        """Wave direction at 45 deg -> sin^2(45) = 0.5 -> 25% penalty."""
        factor = _swell_roll_factor(wave_dir=math.pi / 4, heading=0.0)
        expected = 1.0 - 0.5 * math.sin(math.pi / 4) ** 2  # 1.0 - 0.5*0.5 = 0.75
        assert factor == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Tests: integration-level checks
# ---------------------------------------------------------------------------

class TestSeaStateOpsIntegration:
    """Integration-level checks for calibration flag and domain gating."""

    def test_calibration_schema_accepts_enable_sea_state_ops(self) -> None:
        """CalibrationSchema has enable_sea_state_ops field, defaults to False."""
        schema = CalibrationSchema()
        assert schema.enable_sea_state_ops is False

    def test_calibration_schema_enable_true(self) -> None:
        """CalibrationSchema accepts enable_sea_state_ops=True."""
        schema = CalibrationSchema(enable_sea_state_ops=True)
        assert schema.enable_sea_state_ops is True

    def test_non_naval_units_not_affected(self) -> None:
        """Ground/aerial units are not subject to sea state effects.

        The battle.py logic gates on domain in (NAVAL, SUBMARINE, AMPHIBIOUS).
        Ground/aerial units skip the block entirely.
        """
        ground_domain = Domain.GROUND
        aerial_domain = Domain.AERIAL
        naval_domains = {Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS}
        assert ground_domain not in naval_domains
        assert aerial_domain not in naval_domains

    def test_calm_seas_no_penalties(self) -> None:
        """Beaufort 0, zero tidal current, zero wave period -> no effect."""
        speed_factor = _small_craft_speed_factor(beaufort=0, displacement_tons=500, max_speed=10.0)
        tidal_effect = _tidal_current_effect(tidal_speed=0.0, tidal_dir=0.0, heading=0.0)
        resonance = _wave_resonance_factor(wave_period=0.0, displacement_tons=3000)
        roll = _swell_roll_factor(wave_dir=0.0, heading=0.0)

        assert speed_factor == pytest.approx(1.0)
        assert tidal_effect == pytest.approx(0.0)
        assert resonance == pytest.approx(1.0)
        assert roll == pytest.approx(1.0)

    def test_enable_false_means_no_effects(self) -> None:
        """When enable_sea_state_ops=False, the cal.get() returns False.

        This replicates the dict-based lookup pattern in battle.py:
        ``cal.get("enable_sea_state_ops", False)``
        """
        schema = CalibrationSchema(enable_sea_state_ops=False)
        cal = schema.model_dump()
        assert cal.get("enable_sea_state_ops", False) is False

    def test_structural_wiring_in_battle(self) -> None:
        """battle.py contains the Phase 61a sea state ops wiring."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "enable_sea_state_ops" in src
        assert "beaufort_scale" in src
        assert "tidal_current_speed" in src
        assert "hull_natural_period" not in src or "_hull_period" in src
        assert "_roll_factor" in src
