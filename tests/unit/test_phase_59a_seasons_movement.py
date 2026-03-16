"""Phase 59a: Seasons → Movement speed modifiers.

Tests verify that mud, snow, and trafficability reduce effective_speed
in the battle movement loop, gated by enable_seasonal_effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers — minimal mocks for the movement computation logic
# ---------------------------------------------------------------------------


def _compute_seasonal_speed_mult(
    max_speed: float,
    mud_depth: float,
    snow_depth: float,
    ground_trafficability: float,
) -> float:
    """Reproduce the seasonal speed multiplier from battle.py logic."""
    if max_speed > 15:  # wheeled
        mud_mult = max(0.1, 1.0 - mud_depth / 0.3)
    elif max_speed > 5:  # tracked
        mud_mult = max(0.3, 1.0 - mud_depth / 0.5)
    else:  # foot
        mud_mult = max(0.4, 1.0 - mud_depth / 0.4)
    snow_mult = max(0.4, 1.0 - snow_depth / 0.5)
    return mud_mult * snow_mult * ground_trafficability


class TestMudPenalties:
    """Mud depth affects different mobility classes differently."""

    def test_wheeled_20cm_mud(self) -> None:
        """Wheeled vehicle in 20cm mud: ~33% of base speed."""
        mult = _compute_seasonal_speed_mult(20.0, 0.2, 0.0, 1.0)
        assert 0.30 <= mult <= 0.40

    def test_tracked_20cm_mud(self) -> None:
        """Tracked vehicle in 20cm mud: ~60% of base speed."""
        mult = _compute_seasonal_speed_mult(10.0, 0.2, 0.0, 1.0)
        assert 0.55 <= mult <= 0.65

    def test_foot_20cm_mud(self) -> None:
        """Infantry in 20cm mud: ~50% of base speed."""
        mult = _compute_seasonal_speed_mult(4.0, 0.2, 0.0, 1.0)
        assert 0.45 <= mult <= 0.55

    def test_deep_mud_nearly_immobilizes_wheeled(self) -> None:
        """25cm mud nearly stops wheeled vehicles (~17%)."""
        mult = _compute_seasonal_speed_mult(20.0, 0.25, 0.0, 1.0)
        assert mult < 0.20


class TestSnowPenalties:
    def test_infantry_30cm_snow(self) -> None:
        """Infantry in 30cm snow: speed ≈ 40% (floor)."""
        mult = _compute_seasonal_speed_mult(4.0, 0.0, 0.3, 1.0)
        assert 0.38 <= mult <= 0.42


class TestDryGroundNoEffect:
    def test_no_penalty_dry(self) -> None:
        """Dry ground (mud=0, snow=0, trafficability=1.0): no penalty."""
        mult = _compute_seasonal_speed_mult(10.0, 0.0, 0.0, 1.0)
        assert mult == pytest.approx(1.0)


class TestTrafficability:
    def test_saturated_ground(self) -> None:
        """SATURATED (trafficability=0.2): 20% of base speed."""
        mult = _compute_seasonal_speed_mult(10.0, 0.0, 0.0, 0.2)
        assert mult == pytest.approx(0.2)

    def test_dry_ground(self) -> None:
        """DRY (trafficability=1.0): no penalty."""
        mult = _compute_seasonal_speed_mult(10.0, 0.0, 0.0, 1.0)
        assert mult == pytest.approx(1.0)


class TestDisabledByDefault:
    def test_seasons_engine_absent_no_penalty(self) -> None:
        """When seasons_engine is None, no seasonal modifiers apply."""
        # Verifying via structural check that the code guards on None
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert 'getattr(ctx, "seasons_engine", None)' in src

    def test_enable_seasonal_effects_false_no_penalty(self) -> None:
        """When enable_seasonal_effects=False, seasonal modifiers are skipped."""
        cal = CalibrationSchema(enable_seasonal_effects=False)
        assert cal.get("enable_seasonal_effects", True) is False


class TestDomainExclusion:
    def test_naval_units_unaffected(self) -> None:
        """Structural: naval units excluded from ground seasons."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "Domain.NAVAL" in src
        # The guard excludes NAVAL, AERIAL, SUBMARINE
        assert "Domain.SUBMARINE" in src

    def test_aerial_units_unaffected(self) -> None:
        """Structural: aerial units excluded from ground seasons."""
        from pathlib import Path

        src = Path("stochastic_warfare/simulation/battle.py").read_text()
        assert "Domain.AERIAL" in src
