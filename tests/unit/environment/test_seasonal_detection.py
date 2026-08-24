"""Phase 59b: Seasons → Detection concealment.

Tests verify that vegetation_density adds concealment bonus in
forest/shrub terrain, capped at 1.0.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers — invoke _compute_terrain_modifiers with mock context
# ---------------------------------------------------------------------------


def _make_ctx(
    land_cover_name: str = "FOREST",
    base_cover: float = 0.3,
    base_concealment: float = 0.2,
) -> SimpleNamespace:
    """Create a minimal ctx with classification that returns given properties."""
    props = SimpleNamespace(
        cover=base_cover,
        concealment=base_concealment,
        land_cover=SimpleNamespace(name=land_cover_name),
    )
    classification = SimpleNamespace(
        properties_at=lambda pos: props,
    )
    return SimpleNamespace(
        classification=classification,
        heightmap=None,
        infrastructure_manager=None,
        obstacle_manager=None,
        trench_engine=None,
    )


def _call_terrain_mods(
    ctx: Any,
    seasonal_vegetation: float = 0.0,
) -> tuple[float, float, float]:
    """Call _compute_terrain_modifiers from BattleManager."""
    # Import here to avoid circular imports in test collection
    from stochastic_warfare.simulation.battle import BattleManager

    target = Position(100.0, 100.0, 0.0)
    attacker = Position(200.0, 200.0, 0.0)
    return BattleManager._compute_terrain_modifiers(
        ctx, target, attacker,
        seasonal_vegetation=seasonal_vegetation,
    )


class TestVegetationConcealmentBonus:
    def test_summer_forest(self) -> None:
        """Summer forest (vegetation_density=0.9): concealment +0.27."""
        ctx = _make_ctx("FOREST", base_concealment=0.2)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.9)
        assert conc == pytest.approx(0.2 + 0.9 * 0.3, abs=0.01)

    def test_winter_forest(self) -> None:
        """Winter forest (vegetation_density=0.2): concealment +0.06."""
        ctx = _make_ctx("FOREST", base_concealment=0.2)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.2)
        assert conc == pytest.approx(0.2 + 0.2 * 0.3, abs=0.01)

    def test_shrubland(self) -> None:
        """Shrubland with partial vegetation: proportional bonus."""
        ctx = _make_ctx("SHRUB", base_concealment=0.15)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.5)
        assert conc == pytest.approx(0.15 + 0.5 * 0.3, abs=0.01)

    def test_concealment_capped_at_one(self) -> None:
        """Concealment caps at 1.0 (base 0.9 + veg 0.9*0.3 = 1.17 → 1.0)."""
        ctx = _make_ctx("FOREST", base_concealment=0.9)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.9)
        assert conc == pytest.approx(1.0)


class TestNoVegetationBonus:
    def test_open_terrain(self) -> None:
        """Open terrain (no FOREST/SHRUB): no vegetation concealment."""
        ctx = _make_ctx("GRASSLAND", base_concealment=0.1)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.9)
        assert conc == pytest.approx(0.1)

    def test_desert_terrain(self) -> None:
        """Desert terrain: no vegetation concealment."""
        ctx = _make_ctx("BARE_DESERT", base_concealment=0.05)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.9)
        assert conc == pytest.approx(0.05)

    def test_seasons_engine_absent(self) -> None:
        """SeasonsEngine absent → seasonal_vegetation=0.0 → no bonus."""
        ctx = _make_ctx("FOREST", base_concealment=0.2)
        _, _, conc = _call_terrain_mods(ctx, seasonal_vegetation=0.0)
        assert conc == pytest.approx(0.2)

    def test_enable_seasonal_effects_false(self) -> None:
        """When disabled, caller passes 0.0 → no bonus."""
        cal = CalibrationSchema(enable_seasonal_effects=False)
        # The caller logic: if not enabled, _sv stays 0.0
        assert cal.get("enable_seasonal_effects", True) is False
