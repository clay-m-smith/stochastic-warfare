"""Phase 58b: Air combat routing tests.

Verifies that air combat engines are instantiated on SimulationContext
and that _route_air_engagement dispatches correctly by domain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from stochastic_warfare.combat.air_combat import AirCombatEngine, AirCombatMode
from stochastic_warfare.combat.events import AirEngagementEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.environment.weather import WindVector
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


class _RecordingAirCombatEngine(AirCombatEngine):
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus, np.random.Generator(np.random.PCG64(42)))
        self.calls: list[dict[str, object]] = []

    def resolve_air_engagement(self, *args: object, **kwargs: object):
        self.calls.append(dict(kwargs))
        return super().resolve_air_engagement(*args, **kwargs)


def _real_air_context(
    *,
    wind_speed_mps: float,
    wind_direction_rad: float,
    enabled: bool,
    density_kg_m3: float = 1.225,
    icing_risk: float = 0.0,
) -> tuple[SimpleNamespace, list[AirEngagementEvent]]:
    bus = EventBus()
    events: list[AirEngagementEvent] = []
    bus.subscribe(AirEngagementEvent, events.append)
    weather = SimpleNamespace(
        current=SimpleNamespace(
            wind=WindVector(wind_speed_mps, wind_direction_rad, wind_speed_mps),
        ),
        atmospheric_density=lambda _altitude_m: density_kg_m3,
    )
    engine = _RecordingAirCombatEngine(bus)
    return (
        SimpleNamespace(
            air_combat_engine=engine,
            event_bus=bus,
            weather_engine=weather,
            conditions_engine=SimpleNamespace(
                air=lambda: SimpleNamespace(icing_risk=icing_risk),
            ),
            cal_flat={
                "enable_air_combat_environment": enabled,
                "wind_bvr_missile_speed_mps": 1_000.0,
            },
        ),
        events,
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

    @pytest.mark.test_evidence("behavioral_oracle")
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

    @pytest.mark.test_evidence("behavioral_oracle")
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

    @pytest.mark.test_evidence("behavioral_oracle")
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


class TestAirCombatEnvironmentalRange:
    @pytest.mark.parametrize(
        ("target_northing_m", "wind_direction_rad", "expected_mode"),
        [
            pytest.param(85_000.0, 0.0, AirCombatMode.BVR, id="tailwind-extends"),
            pytest.param(75_000.0, np.pi, AirCombatMode.GUNS_ONLY, id="headwind-reduces"),
        ],
    )
    def test_enabled_wind_changes_bvr_eligibility_through_real_route(
        self,
        target_northing_m: float,
        wind_direction_rad: float,
        expected_mode: AirCombatMode,
    ) -> None:
        ctx, events = _real_air_context(
            wind_speed_mps=100.0,
            wind_direction_rad=wind_direction_rad,
            enabled=True,
        )
        attacker = _make_unit("f16", Domain.AERIAL, Position(0, 0, 10_000))
        target = _make_unit(
            "mig29",
            Domain.AERIAL,
            Position(0, target_northing_m, 10_000),
        )

        handled, _status = _route_air_engagement(
            ctx,
            attacker,
            target,
            _make_wpn_inst(),
            best_range=target_northing_m,
            dt=1.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert handled
        assert [event.engagement_type for event in events] == [expected_mode.name]

    def test_disabled_wind_preserves_geometric_bvr_eligibility(self) -> None:
        ctx, events = _real_air_context(
            wind_speed_mps=100.0,
            wind_direction_rad=0.0,
            enabled=False,
        )
        attacker = _make_unit("f16", Domain.AERIAL, Position(0, 0, 10_000))
        target = _make_unit("mig29", Domain.AERIAL, Position(0, 85_000, 10_000))

        handled, _status = _route_air_engagement(
            ctx,
            attacker,
            target,
            _make_wpn_inst(),
            best_range=85_000.0,
            dt=1.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert handled
        assert [event.engagement_type for event in events] == [
            AirCombatMode.GUNS_ONLY.name,
        ]

    def test_enabled_icing_and_density_reduce_real_routed_missile_pk(self) -> None:
        def routed_pk(*, enabled: bool, density: float, icing: float) -> float:
            ctx, _events = _real_air_context(
                wind_speed_mps=0.0,
                wind_direction_rad=0.0,
                enabled=enabled,
                density_kg_m3=density,
                icing_risk=icing,
            )
            handled, _status = _route_air_engagement(
                ctx,
                _make_unit("f16", Domain.AERIAL, Position(0, 0, 10_000)),
                _make_unit("mig29", Domain.AERIAL, Position(0, 50_000, 10_000)),
                _make_wpn_inst(),
                best_range=50_000.0,
                dt=1.0,
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            )
            assert handled
            assert len(ctx.air_combat_engine.calls) == 1
            return float(ctx.air_combat_engine.calls[0]["missile_pk"])

        adverse = routed_pk(enabled=True, density=0.9, icing=0.8)
        disabled = routed_pk(enabled=False, density=0.9, icing=0.8)
        clear_enabled = routed_pk(enabled=True, density=1.225, icing=0.0)

        assert adverse < disabled
        assert disabled == pytest.approx(clear_enabled)

    @pytest.mark.test_evidence("behavioral_oracle")
    @pytest.mark.parametrize(
        ("enabled", "guidance", "expected_calls"),
        [
            pytest.param(True, "none", 0, id="enabled-unguided-aborts"),
            pytest.param(True, "gps", 1, id="enabled-guided-proceeds"),
            pytest.param(False, "none", 1, id="disabled-unguided-proceeds"),
        ],
    )
    def test_low_cloud_ceiling_gates_only_enabled_unguided_cas(
        self,
        enabled: bool,
        guidance: str,
        expected_calls: int,
    ) -> None:
        air_ground = MagicMock()
        air_ground.execute_cas.return_value = SimpleNamespace(
            hit=False,
            aborted=False,
        )
        weapon = SimpleNamespace(
            definition=SimpleNamespace(
                category="BOMB",
                weapon_id="test-bomb",
                rate_of_fire_rpm=1,
                guidance_type=guidance,
            ),
        )
        ctx = SimpleNamespace(
            air_ground_engine=air_ground,
            cal_flat={
                "enable_air_combat_environment": enabled,
                "cloud_ceiling_min_attack_m": 500.0,
            },
            weather_engine=SimpleNamespace(
                current=SimpleNamespace(cloud_ceiling=300.0),
            ),
            conditions_engine=None,
        )

        handled, _status = _route_air_engagement(
            ctx,
            _make_unit("a10", Domain.AERIAL),
            _make_unit("target", Domain.GROUND),
            weapon,
            best_range=500.0,
            dt=1.0,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert handled
        assert air_ground.execute_cas.call_count == expected_calls


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

    @pytest.mark.test_evidence("behavioral_oracle")
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
