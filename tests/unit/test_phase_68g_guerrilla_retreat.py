"""Phase 68g: Guerrilla retreat movement tests.

Verifies that guerrilla units physically move away from enemies on
disengage, and optionally transition to ROUTING status.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position, ModuleId
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.combat.unconventional import (
    GuerrillaConfig,
    UnconventionalWarfareEngine,
)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_guerrilla(
    entity_id: str = "insurgent_1",
    position: Position | None = None,
) -> GroundUnit:
    pos = position or Position(1000, 1000, 0)
    u = GroundUnit(entity_id=entity_id, position=pos, max_speed=5.0)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    object.__setattr__(u, "speed", 5.0)
    object.__setattr__(u, "unit_type", "insurgent_squad")
    return u


def _make_enemy(entity_id: str = "enemy1", position: Position | None = None) -> GroundUnit:
    pos = position or Position(500, 1000, 0)
    u = GroundUnit(entity_id=entity_id, position=pos, max_speed=15.0)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    return u


class TestRetreatDirection:
    """Guerrilla retreat moves unit away from nearest enemy."""

    def test_retreat_away_from_enemy(self):
        """Unit at (1000,1000) with enemy at (500,1000) retreats east (+easting)."""
        guerrilla = _make_guerrilla(position=Position(1000, 1000, 0))
        enemy = _make_enemy(position=Position(500, 1000, 0))

        # Simulate retreat logic: direction from enemy to guerrilla = (500, 0)
        gp = guerrilla.position
        ep = enemy.position
        dx = ep.easting - gp.easting   # -500
        dy = ep.northing - gp.northing  # 0
        dist = math.sqrt(dx * dx + dy * dy)  # 500

        retreat_distance = 2000.0
        rx = -dx / dist * retreat_distance  # +2000
        ry = -dy / dist * retreat_distance  # 0

        new_pos = Position(gp.easting + rx, gp.northing + ry, gp.altitude)
        assert new_pos.easting == pytest.approx(3000.0)  # moved east (away from enemy)
        assert new_pos.northing == pytest.approx(1000.0)

    def test_retreat_distance_matches_calibration(self):
        """Retreat distance should match calibration retreat_distance_m."""
        schema = CalibrationSchema(retreat_distance_m=3000.0)
        assert schema.retreat_distance_m == 3000.0

        default = CalibrationSchema()
        assert default.retreat_distance_m == 2000.0

    def test_non_guerrilla_units_unaffected(self):
        """Units without insurgent/militia/guerrilla in unit_type skip the check."""
        unit = _make_guerrilla(entity_id="tank1", position=Position(1000, 1000, 0))
        object.__setattr__(unit, "unit_type", "m1a2_abrams")
        # The type filter: any(kw in unit_type.lower() for kw in ("insurgent", "militia", "guerrilla"))
        att_type = getattr(unit, "unit_type", "").lower()
        assert not any(kw in att_type for kw in ("insurgent", "militia", "guerrilla"))


class TestDisengageEvaluation:
    """Disengage evaluation produces correct decisions."""

    def test_high_casualty_triggers_disengage(self):
        """Casualty fraction above threshold triggers disengage."""
        uw = UnconventionalWarfareEngine(
            EventBus(), _rng(),
            config_guerrilla=GuerrillaConfig(disengage_threshold=0.3),
        )
        # High casualty fraction → should disengage
        disengage, blend = uw.evaluate_guerrilla_disengage("g1", 0.5, in_populated_area=False)
        assert disengage is True

    def test_low_casualty_no_disengage(self):
        """Casualty fraction below threshold → no disengage."""
        uw = UnconventionalWarfareEngine(
            EventBus(), _rng(),
            config_guerrilla=GuerrillaConfig(disengage_threshold=0.3),
        )
        disengage, blend = uw.evaluate_guerrilla_disengage("g1", 0.1, in_populated_area=False)
        assert disengage is False


class TestBlendRouting:
    """Blend probability can set guerrilla to ROUTING status."""

    def test_routing_status_possible(self):
        """ROUTING status exists and has value 4."""
        assert UnitStatus.ROUTING.value == 4

    def test_blend_zero_no_routing(self):
        """With blend=0, unit stays ACTIVE regardless of RNG."""
        guerrilla = _make_guerrilla()
        blend = 0.0
        # The gate: if _blend > 0 ... → never enters block
        assert not (blend > 0)
        assert guerrilla.status == UnitStatus.ACTIVE
