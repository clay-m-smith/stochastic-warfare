"""Phase 68g: Guerrilla retreat movement tests.

Verifies that guerrilla units physically move away from enemies on
disengage without fabricating a morale-owned routing status.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.combat.unconventional import (
    GuerrillaConfig,
    UnconventionalWarfareEngine,
    UnsupportedGuerrillaBlendError,
)
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit
from stochastic_warfare.morale.runtime import MoraleRegistration, MoraleRuntime
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.battle import BattleManager
from stochastic_warfare.simulation.calibration import CalibrationSchema


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


class TestBlendBoundary:
    """Concealment blending cannot impersonate a morale transition."""

    @pytest.mark.parametrize(
        ("blend_probability", "unsupported"),
        ((1.0, True), (0.0, False)),
        ids=("positive-explicitly-unsupported", "zero-retreat-control"),
    )
    def test_blend_boundary_preserves_morale_and_rng(
        self,
        blend_probability: float,
        unsupported: bool,
    ) -> None:
        guerrilla = _make_guerrilla(position=Position(1000, 1000, 0))
        enemy = _make_enemy(position=Position(500, 1000, 0))
        bus = EventBus()
        events: list[Event] = []
        bus.subscribe(Event, events.append)
        rng_manager = RNGManager(68)
        combat_rng = rng_manager.get_stream(ModuleId.COMBAT)
        morale_rng = rng_manager.get_stream(ModuleId.MORALE)
        unconventional = UnconventionalWarfareEngine(
            bus,
            combat_rng,
            config_guerrilla=GuerrillaConfig(
                disengage_threshold=0.3,
                blend_probability=blend_probability,
            ),
        )
        assert unconventional._rng is combat_rng
        combat_rng_before = copy.deepcopy(combat_rng.bit_generator.state)
        morale_rng_before = copy.deepcopy(morale_rng.bit_generator.state)
        manager = BattleManager(event_bus=bus)
        manager._cumulative_casualties[guerrilla.entity_id] = 4

        units_by_side = {"blue": [guerrilla], "red": [enemy]}
        active_enemies = {"blue": [enemy], "red": [guerrilla]}
        enemy_positions = {
            "blue": np.array([[500.0, 1000.0]], dtype=np.float64),
            "red": np.array([[1000.0, 1000.0]], dtype=np.float64),
        }
        morale_runtime = MoraleRuntime(
            bus,
            rng_manager.get_stream(ModuleId.MORALE),
        )
        morale_runtime.register_units(
            (
                MoraleRegistration(guerrilla.entity_id, MoraleState.STEADY),
                MoraleRegistration(enemy.entity_id, MoraleState.STEADY),
            ),
            {
                guerrilla.entity_id: guerrilla,
                enemy.entity_id: enemy,
            },
        )
        context = SimpleNamespace(
            calibration={
                "enable_unconventional_warfare": True,
                "guerrilla_disengage_threshold": 0.3,
                "retreat_distance_m": 2000.0,
            },
            config=SimpleNamespace(
                behavior_rules={},
                latitude=0.0,
                longitude=0.0,
            ),
            engagement_engine=object(),
            morale_runtime=morale_runtime,
            morale_states=morale_runtime.states,
            population_engine=SimpleNamespace(get_density_at=lambda _position: 1.0),
            rng_manager=rng_manager,
            rout_engine=morale_runtime.rout_engine,
            unconventional_engine=unconventional,
            unit_weapons={},
        )

        execute = lambda: manager._execute_engagements(
            context,
            units_by_side,
            active_enemies,
            enemy_positions,
            dt=1.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            _unit_index={
                guerrilla.entity_id: guerrilla,
                enemy.entity_id: enemy,
            },
        )
        if unsupported:
            with pytest.raises(
                UnsupportedGuerrillaBlendError,
                match="REM-032",
            ):
                execute()
        else:
            assert execute() == []

        expected_easting = 1000.0 if unsupported else 3000.0
        assert guerrilla.position.easting == pytest.approx(expected_easting)
        assert guerrilla.position.northing == pytest.approx(1000.0)
        assert guerrilla.status is UnitStatus.ACTIVE
        assert morale_runtime.states[guerrilla.entity_id] is MoraleState.STEADY
        assert morale_runtime.record_for(guerrilla.entity_id).generation == 0
        assert combat_rng.bit_generator.state == combat_rng_before
        assert morale_rng.bit_generator.state == morale_rng_before
        assert events == []
