"""Phase 58b: Air combat routing tests.

Verifies that air combat engines are instantiated on SimulationContext
and that _route_air_engagement dispatches correctly by domain.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.battle import _route_air_engagement


def _make_unit(
    entity_id: str,
    domain: Domain,
    position: Position | None = None,
    training_level: float = 0.5,
) -> Unit:
    """Create a minimal unit for testing."""
    return Unit(
        entity_id=entity_id,
        position=position or Position(0, 0, 0),
        domain=domain,
        training_level=training_level,
    )


def _make_wpn_inst() -> SimpleNamespace:
    """Create a minimal weapon instance stub."""
    return SimpleNamespace(
        definition=SimpleNamespace(
            category="MISSILE_LAUNCHER",
            weapon_id="test_missile",
            rate_of_fire_rpm=1,
        ),
    )


class TestAirEnginesOnContext:
    """Air combat engines exist on SimulationContext."""

    def test_air_combat_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        # Verify the field exists (defaults to None)
        ctx = SimulationContext.__dataclass_fields__
        assert "air_combat_engine" in ctx

    def test_air_ground_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        ctx = SimulationContext.__dataclass_fields__
        assert "air_ground_engine" in ctx

    def test_air_defense_engine_field(self):
        from stochastic_warfare.simulation.scenario import SimulationContext
        ctx = SimulationContext.__dataclass_fields__
        assert "air_defense_engine" in ctx


class TestAirRoutingDispatch:
    """_route_air_engagement routes by domain combination."""

    def test_air_vs_air_routes_to_air_combat(self):
        """AIR vs AIR → air_combat_engine.resolve_air_engagement."""
        mock_result = SimpleNamespace(hit=True, effective_pk=0.7)
        mock_engine = MagicMock()
        mock_engine.resolve_air_engagement.return_value = mock_result

        ctx = SimpleNamespace(air_combat_engine=mock_engine)
        attacker = _make_unit("f16", Domain.AERIAL, Position(0, 0, 5000))
        target = _make_unit("mig29", Domain.AERIAL, Position(1000, 0, 5000))

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=1000, dt=1.0, timestamp=0.0,
        )
        assert handled
        assert status == UnitStatus.DESTROYED
        mock_engine.resolve_air_engagement.assert_called_once()

    def test_air_vs_ground_routes_to_air_ground(self):
        """AIR vs GROUND → air_ground_engine.execute_cas."""
        mock_result = SimpleNamespace(hit=True, aborted=False, effective_pk=0.5)
        mock_engine = MagicMock()
        mock_engine.execute_cas.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),  # present but shouldn't be used
            air_ground_engine=mock_engine,
            air_defense_engine=MagicMock(),
        )
        attacker = _make_unit("a10", Domain.AERIAL)
        target = _make_unit("tank1", Domain.GROUND)

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=500, dt=1.0, timestamp=0.0,
        )
        assert handled
        assert status == UnitStatus.DISABLED
        mock_engine.execute_cas.assert_called_once()

    def test_ground_vs_air_routes_to_air_defense(self):
        """GROUND vs AIR → air_defense_engine.fire_interceptor."""
        mock_result = SimpleNamespace(hit=True, effective_pk=0.6)
        mock_engine = MagicMock()
        mock_engine.fire_interceptor.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=mock_engine,
        )
        attacker = _make_unit("sa11", Domain.GROUND)
        target = _make_unit("f16", Domain.AERIAL)

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=20000, dt=1.0, timestamp=0.0,
        )
        assert handled
        assert status == UnitStatus.DESTROYED
        mock_engine.fire_interceptor.assert_called_once()

    def test_ground_vs_ground_not_handled(self):
        """GROUND vs GROUND → (False, None), falls through."""
        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=MagicMock(),
        )
        attacker = _make_unit("tank1", Domain.GROUND)
        target = _make_unit("tank2", Domain.GROUND)

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=1000, dt=1.0, timestamp=0.0,
        )
        assert not handled
        assert status is None

    def test_naval_vs_air_routes_to_air_defense(self):
        """NAVAL vs AIR → air_defense_engine."""
        mock_result = SimpleNamespace(hit=False)
        mock_engine = MagicMock()
        mock_engine.fire_interceptor.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=mock_engine,
        )
        attacker = _make_unit("ddg", Domain.NAVAL)
        target = _make_unit("mig29", Domain.AERIAL)

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=30000, dt=1.0, timestamp=0.0,
        )
        assert handled
        assert status is None  # miss

    def test_air_combat_engine_none_falls_through(self):
        """air_combat_engine=None → (False, None), graceful fallthrough."""
        ctx = SimpleNamespace(
            air_combat_engine=None,
            air_ground_engine=None,
            air_defense_engine=None,
        )
        attacker = _make_unit("f16", Domain.AERIAL)
        target = _make_unit("mig29", Domain.AERIAL)

        handled, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=1000, dt=1.0, timestamp=0.0,
        )
        assert not handled
        assert status is None

    def test_cannon_air_vs_air_falls_through(self):
        """Non-missile weapon (CANNON) for air-to-air falls through to direct fire."""
        cannon_wpn = SimpleNamespace(
            definition=SimpleNamespace(
                category="CANNON",
                weapon_id="m61_vulcan",
                rate_of_fire_rpm=6000,
            ),
        )
        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=MagicMock(),
        )
        attacker = _make_unit("f16", Domain.AERIAL)
        target = _make_unit("mig29", Domain.AERIAL)

        handled, status = _route_air_engagement(
            ctx, attacker, target, cannon_wpn,
            best_range=500, dt=1.0, timestamp=0.0,
        )
        assert not handled, "Cannon weapon should fall through to direct fire"

    def test_cannon_air_vs_ground_falls_through(self):
        """Non-bomb weapon (CANNON) for CAS falls through to direct fire."""
        cannon_wpn = SimpleNamespace(
            definition=SimpleNamespace(
                category="CANNON",
                weapon_id="gau8_avenger",
                rate_of_fire_rpm=3900,
            ),
        )
        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=MagicMock(),
        )
        attacker = _make_unit("a10", Domain.AERIAL)
        target = _make_unit("tank1", Domain.GROUND)

        handled, status = _route_air_engagement(
            ctx, attacker, target, cannon_wpn,
            best_range=500, dt=1.0, timestamp=0.0,
        )
        assert not handled, "Cannon CAS should fall through to direct fire"


class TestAirRoutingResults:
    """Result interpretation — hit/miss → status mapping."""

    def test_air_combat_hit_destroys(self):
        mock_result = SimpleNamespace(hit=True)
        mock_engine = MagicMock()
        mock_engine.resolve_air_engagement.return_value = mock_result

        ctx = SimpleNamespace(air_combat_engine=mock_engine)
        attacker = _make_unit("f16", Domain.AERIAL)
        target = _make_unit("mig29", Domain.AERIAL)

        _, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=5000, dt=1.0, timestamp=0.0,
        )
        assert status == UnitStatus.DESTROYED

    def test_air_combat_miss_no_damage(self):
        mock_result = SimpleNamespace(hit=False)
        mock_engine = MagicMock()
        mock_engine.resolve_air_engagement.return_value = mock_result

        ctx = SimpleNamespace(air_combat_engine=mock_engine)
        attacker = _make_unit("f16", Domain.AERIAL)
        target = _make_unit("mig29", Domain.AERIAL)

        _, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=5000, dt=1.0, timestamp=0.0,
        )
        assert status is None

    def test_cas_hit_disables(self):
        mock_result = SimpleNamespace(hit=True, aborted=False)
        mock_engine = MagicMock()
        mock_engine.execute_cas.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=mock_engine,
        )
        attacker = _make_unit("a10", Domain.AERIAL)
        target = _make_unit("tank1", Domain.GROUND)

        _, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=500, dt=1.0, timestamp=0.0,
        )
        assert status == UnitStatus.DISABLED

    def test_cas_aborted_no_damage(self):
        mock_result = SimpleNamespace(hit=False, aborted=True)
        mock_engine = MagicMock()
        mock_engine.execute_cas.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=mock_engine,
        )
        attacker = _make_unit("a10", Domain.AERIAL)
        target = _make_unit("tank1", Domain.GROUND)

        _, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=500, dt=1.0, timestamp=0.0,
        )
        assert status is None

    def test_intercept_hit_destroys(self):
        mock_result = SimpleNamespace(hit=True)
        mock_engine = MagicMock()
        mock_engine.fire_interceptor.return_value = mock_result

        ctx = SimpleNamespace(
            air_combat_engine=MagicMock(),
            air_ground_engine=MagicMock(),
            air_defense_engine=mock_engine,
        )
        attacker = _make_unit("sa11", Domain.GROUND)
        target = _make_unit("f16", Domain.AERIAL)

        _, status = _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=15000, dt=1.0, timestamp=0.0,
        )
        assert status == UnitStatus.DESTROYED

    def test_force_ratio_mod_scales_pk(self):
        """force_ratio_mod > 1 increases effective Pk."""
        mock_engine = MagicMock()
        mock_result = SimpleNamespace(hit=True)
        mock_engine.resolve_air_engagement.return_value = mock_result

        ctx = SimpleNamespace(air_combat_engine=mock_engine)
        attacker = _make_unit("f16", Domain.AERIAL)
        target = _make_unit("mig29", Domain.AERIAL)

        _route_air_engagement(
            ctx, attacker, target, _make_wpn_inst(),
            best_range=5000, dt=1.0, timestamp=0.0,
            force_ratio_mod=2.0,
        )
        # Check that missile_pk was scaled: min(1.0, 0.5 * 2.0) = 1.0
        call_kwargs = mock_engine.resolve_air_engagement.call_args
        assert call_kwargs.kwargs.get("missile_pk", call_kwargs[1].get("missile_pk", 0)) == pytest.approx(1.0)


class TestEnableAirRoutingFlag:
    """Air routing is gated by enable_air_routing in CalibrationSchema."""

    def test_default_is_disabled(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.enable_air_routing is False

    def test_enable_air_routing_accepted(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_air_routing=True)
        assert cal.enable_air_routing is True

    def test_battle_checks_flag(self):
        """battle.py checks enable_air_routing in the routing condition."""
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        assert "enable_air_routing" in text


class TestStructuralAirRouting:
    """Structural tests verifying source code wiring."""

    def test_scenario_creates_air_engines(self):
        """scenario.py mentions AirCombatEngine, AirGroundEngine, AirDefenseEngine."""
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "scenario.py"
        text = src.read_text(encoding="utf-8")
        assert "AirCombatEngine" in text
        assert "AirGroundEngine" in text
        assert "AirDefenseEngine" in text

    def test_battle_has_route_air_engagement(self):
        """battle.py has _route_air_engagement function."""
        src = Path(__file__).resolve().parents[2] / "stochastic_warfare" / "simulation" / "battle.py"
        text = src.read_text(encoding="utf-8")
        assert "_route_air_engagement" in text
