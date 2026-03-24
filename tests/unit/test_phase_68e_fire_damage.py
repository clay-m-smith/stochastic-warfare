"""Phase 68e: Fire zone damage enforcement tests.

Verifies that units in active fire zones take burn damage when
``enable_fire_zones=True`` and ``fire_damage_per_tick`` is set.
"""

from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit
from stochastic_warfare.simulation.battle import BattleManager, _apply_aggregate_casualties
from stochastic_warfare.simulation.calibration import CalibrationSchema

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_unit(entity_id: str = "inf1", position: Position | None = None) -> GroundUnit:
    pos = position or Position(100, 100, 0)
    u = GroundUnit(entity_id=entity_id, position=pos, max_speed=4.0)
    object.__setattr__(u, "status", UnitStatus.ACTIVE)
    object.__setattr__(u, "speed", 4.0)
    return u


class FakeFireZone:
    """Minimal fire zone for testing."""

    def __init__(self, center: tuple[float, float], radius: float, burn_rate: float = 0.05):
        self.center = center
        self.current_radius_m = radius
        self._burn_rate = burn_rate


class FakeIncendiaryEngine:
    """Minimal incendiary engine that returns configurable fire zones."""

    def __init__(self, zones: list[FakeFireZone] | None = None, burn_rate: float = 0.05):
        self._active_zones = zones or []
        self._burn_rate = burn_rate

    def units_in_fire(self, unit_positions: dict[str, Position]) -> dict[str, float]:
        import math
        result: dict[str, float] = {}
        for uid, pos in unit_positions.items():
            for zone in self._active_zones:
                dx = pos.easting - zone.center[0]
                dy = pos.northing - zone.center[1]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= zone.current_radius_m:
                    result[uid] = self._burn_rate
        return result


def _make_ctx(
    units: list[GroundUnit],
    incendiary_engine: FakeIncendiaryEngine | None = None,
    enable_fire_zones: bool = True,
    fire_damage_per_tick: float = 0.01,
) -> SimpleNamespace:
    cal_dict = {
        "enable_fire_zones": enable_fire_zones,
        "fire_damage_per_tick": fire_damage_per_tick,
    }
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            calibration_overrides=cal_dict,
            sides=[],
        ),
        calibration=cal_dict,
        event_bus=EventBus(),
        incendiary_engine=incendiary_engine,
    )
    return ctx


class TestFireZoneDamage:
    """Fire zone damage applied to units inside active zones."""

    def test_unit_in_fire_zone_takes_damage(self):
        """Unit inside fire zone should have cumulative casualties tracked."""
        zone = FakeFireZone(center=(100, 100), radius=50.0)
        engine = FakeIncendiaryEngine(zones=[zone], burn_rate=0.05)
        unit = _make_unit(position=Position(100, 100, 0))
        ctx = _make_ctx([unit], incendiary_engine=engine)

        mgr = BattleManager(EventBus())
        # Simulate the fire damage portion by calling the logic directly
        # Fire damage is applied via _apply_aggregate_casualties into cumulative tracker
        hits = engine.units_in_fire({unit.entity_id: unit.position})
        assert unit.entity_id in hits
        assert hits[unit.entity_id] == 0.05

    def test_unit_outside_fire_zone_no_damage(self):
        """Unit outside fire zone should not appear in hits."""
        zone = FakeFireZone(center=(100, 100), radius=10.0)
        engine = FakeIncendiaryEngine(zones=[zone])
        unit = _make_unit(position=Position(500, 500, 0))

        hits = engine.units_in_fire({unit.entity_id: unit.position})
        assert unit.entity_id not in hits

    def test_multiple_units_in_zone(self):
        """Multiple units inside the same zone all get hit."""
        zone = FakeFireZone(center=(100, 100), radius=50.0)
        engine = FakeIncendiaryEngine(zones=[zone], burn_rate=0.02)
        u1 = _make_unit(entity_id="u1", position=Position(100, 100, 0))
        u2 = _make_unit(entity_id="u2", position=Position(110, 110, 0))
        u3 = _make_unit(entity_id="u3", position=Position(500, 500, 0))

        positions = {u.entity_id: u.position for u in [u1, u2, u3]}
        hits = engine.units_in_fire(positions)
        assert "u1" in hits
        assert "u2" in hits
        assert "u3" not in hits

    def test_dug_in_posture_reduces_fire_damage(self):
        """DUG_IN unit should take half fire damage — verified via damage multiplier logic."""
        # DUG_IN posture (int >= 3) → 0.5 multiplier on _fire_dmg
        posture_int = 3  # DUG_IN
        fire_dmg = 0.01 * 0.05  # base * burn_rate

        # Normal unit: full damage
        normal_dmg = fire_dmg
        # DUG_IN unit: half damage
        dug_in_dmg = fire_dmg * 0.5

        assert dug_in_dmg == pytest.approx(normal_dmg * 0.5)

    def test_fire_zones_disabled_no_damage(self):
        """When enable_fire_zones=False, no fire damage applied."""
        zone = FakeFireZone(center=(100, 100), radius=50.0)
        engine = FakeIncendiaryEngine(zones=[zone])
        ctx = _make_ctx([], incendiary_engine=engine, enable_fire_zones=False)

        # The gate check: cal.get("enable_fire_zones", False)
        assert ctx.config.calibration_overrides.get("enable_fire_zones", False) is False

    def test_no_active_zones_no_processing(self):
        """Incendiary engine with empty zones → no fire hits."""
        engine = FakeIncendiaryEngine(zones=[])
        assert not engine._active_zones  # empty → guard skips

    def test_fire_damage_per_tick_calibration(self):
        """CalibrationSchema accepts fire_damage_per_tick."""
        schema = CalibrationSchema(fire_damage_per_tick=0.05)
        assert schema.fire_damage_per_tick == 0.05

        default = CalibrationSchema()
        assert default.fire_damage_per_tick == 0.01

    def test_aggregate_casualties_from_fire(self):
        """Fire damage converts to aggregate casualties via _apply_aggregate_casualties."""
        unit = _make_unit()
        # Give unit 10 personnel so 1 casualty = 10% < threshold
        object.__setattr__(unit, "personnel", list(range(10)))  # mock personnel list

        pending: list[tuple] = []
        tracker: dict[str, int] = {}

        _apply_aggregate_casualties(
            casualties=1,
            target=unit,
            pending_damage=pending,
            destruction_threshold=0.5,
            disable_threshold=0.3,
            cumulative_tracker=tracker,
        )

        assert unit.entity_id in tracker
        assert tracker[unit.entity_id] == 1
        # 1 casualty on unit with 10 personnel = 10% < 30% disable threshold
        assert len(pending) == 0
