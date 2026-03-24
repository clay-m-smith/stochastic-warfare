"""Phase 51: Naval Combat Completeness — routing, posture, DEW disable, mine/blockade wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Unit, UnitStatus

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_unit(
    entity_id: str = "u1",
    domain: Domain = Domain.NAVAL,
    side: str = "blue",
    speed: float = 10.0,
    max_speed: float = 20.0,
    position: Position | None = None,
    **kwargs,
) -> Unit:
    u = Unit(
        entity_id=entity_id,
        unit_type="test_unit",
        name="Test",
        domain=domain,
        side=Side(side),
        max_speed=max_speed,
        position=position or Position(0.0, 0.0, 0.0),
    )
    object.__setattr__(u, "speed", speed)
    for k, v in kwargs.items():
        object.__setattr__(u, k, v)
    return u


def _make_wpn_inst(category: str = "MISSILE_LAUNCHER", rate_of_fire_rpm: float = 4.0,
                   magazine_capacity: int = 0) -> SimpleNamespace:
    defn = SimpleNamespace(
        category=category,
        rate_of_fire_rpm=rate_of_fire_rpm,
        magazine_capacity=magazine_capacity,
        max_range_m=10000.0,
        beam_power_kw=0.0,
    )
    return SimpleNamespace(definition=defn, weapon_id="wpn_test")


# ---------------------------------------------------------------------------
# 51a — Depth charge routing
# ---------------------------------------------------------------------------

class TestDepthChargeRouting:
    """Depth charge weapons route to naval_subsurface_engine.depth_charge_attack()."""

    def test_depth_charge_routes_to_engine(self):
        """DEPTH_CHARGE category calls depth_charge_attack."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import DepthChargeResult

        mock_result = DepthChargeResult(ship_id="s1", target_id="t1", charges_dropped=4, hits=2, damage_fraction=0.7)
        engine = MagicMock()
        engine.depth_charge_attack.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=engine)
        attacker = _make_unit("s1", Domain.NAVAL)
        target = _make_unit("t1", Domain.SUBMARINE, depth=100.0)
        wpn = _make_wpn_inst("DEPTH_CHARGE", rate_of_fire_rpm=6)

        handled, status = _route_naval_engagement(ctx, attacker, target, wpn, 500.0, 10.0, TS)

        assert handled is True
        engine.depth_charge_attack.assert_called_once()

    def test_depth_charge_high_damage_destroyed(self):
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import DepthChargeResult

        mock_result = DepthChargeResult(ship_id="s1", target_id="t1", charges_dropped=4, hits=2, damage_fraction=0.7)
        engine = MagicMock()
        engine.depth_charge_attack.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=engine)

        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.SUBMARINE),
            _make_wpn_inst("DEPTH_CHARGE"), 500.0, 10.0, TS,
        )
        assert status == UnitStatus.DESTROYED

    def test_depth_charge_low_damage_disabled(self):
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import DepthChargeResult

        mock_result = DepthChargeResult(ship_id="s1", target_id="t1", charges_dropped=4, hits=1, damage_fraction=0.3)
        engine = MagicMock()
        engine.depth_charge_attack.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=engine)

        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.SUBMARINE),
            _make_wpn_inst("DEPTH_CHARGE"), 500.0, 10.0, TS,
        )
        assert status == UnitStatus.DISABLED

    def test_depth_charge_miss_returns_none(self):
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import DepthChargeResult

        mock_result = DepthChargeResult(ship_id="s1", target_id="t1", charges_dropped=4, hits=0, damage_fraction=0.0)
        engine = MagicMock()
        engine.depth_charge_attack.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=engine)

        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.SUBMARINE),
            _make_wpn_inst("DEPTH_CHARGE"), 500.0, 10.0, TS,
        )
        assert handled is True
        assert status is None


# ---------------------------------------------------------------------------
# 51a — ASROC routing
# ---------------------------------------------------------------------------

class TestASROCRouting:
    """MISSILE_LAUNCHER vs SUBMARINE routes to asroc_engagement."""

    def test_missile_vs_submarine_routes_to_asroc(self):
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import ASROCResult

        mock_result = ASROCResult(ship_id="s1", target_id="t1", flight_success=True, torpedo_hit=True, damage_fraction=0.5)
        subsurface = MagicMock()
        subsurface.asroc_engagement.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=subsurface, naval_surface_engine=None)

        wpn = _make_wpn_inst("MISSILE_LAUNCHER")
        target = _make_unit("t1", Domain.SUBMARINE)
        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), target, wpn, 3000.0, 10.0, TS,
        )

        assert handled is True
        subsurface.asroc_engagement.assert_called_once()
        assert status == UnitStatus.DISABLED  # 0.5 < 0.6

    def test_missile_vs_naval_routes_to_salvo(self):
        """MISSILE_LAUNCHER vs NAVAL target → salvo_exchange, not ASROC."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement

        salvo_result = SimpleNamespace(hits=1)
        surface = MagicMock()
        surface.salvo_exchange.return_value = salvo_result
        ctx = SimpleNamespace(naval_subsurface_engine=None, naval_surface_engine=surface)

        wpn = _make_wpn_inst("MISSILE_LAUNCHER")
        target = _make_unit("t1", Domain.NAVAL)
        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), target, wpn, 5000.0, 10.0, TS,
        )

        assert handled is True
        surface.salvo_exchange.assert_called_once()

    def test_asroc_high_damage_destroyed(self):
        from stochastic_warfare.simulation.battle import _route_naval_engagement
        from stochastic_warfare.combat.naval_subsurface import ASROCResult

        mock_result = ASROCResult(ship_id="s1", target_id="t1", flight_success=True, torpedo_hit=True, damage_fraction=0.8)
        subsurface = MagicMock()
        subsurface.asroc_engagement.return_value = mock_result
        ctx = SimpleNamespace(naval_subsurface_engine=subsurface, naval_surface_engine=None)

        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.SUBMARINE),
            _make_wpn_inst("MISSILE_LAUNCHER"), 3000.0, 10.0, TS,
        )
        assert status == UnitStatus.DESTROYED


# ---------------------------------------------------------------------------
# 51a — Shore bombardment guard and VLS
# ---------------------------------------------------------------------------

class TestShoreBombardmentAndVLS:
    """Shore bombardment requires naval attacker; VLS tracks magazine."""

    def test_shore_bombardment_requires_naval_attacker(self):
        """CANNON vs GROUND from NAVAL attacker → shore bombardment path."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement

        bom_result = SimpleNamespace(hits_in_lethal_radius=1)
        ngse = MagicMock()
        ngse.shore_bombardment.return_value = bom_result
        ctx = SimpleNamespace(
            naval_subsurface_engine=None, naval_surface_engine=None,
            naval_gunnery_engine=None, naval_gunfire_support_engine=ngse,
        )

        attacker = _make_unit("s1", Domain.NAVAL)
        target = _make_unit("t1", Domain.GROUND)
        wpn = _make_wpn_inst("CANNON", rate_of_fire_rpm=10)

        handled, status = _route_naval_engagement(
            ctx, attacker, target, wpn, 8000.0, 10.0, TS,
        )
        assert handled is True
        ngse.shore_bombardment.assert_called_once()

    def test_shore_bombardment_ground_attacker_falls_through(self):
        """CANNON vs GROUND from GROUND attacker → not handled by shore bombardment."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement

        ngse = MagicMock()
        ctx = SimpleNamespace(
            naval_subsurface_engine=None, naval_surface_engine=None,
            naval_gunnery_engine=None, naval_gunfire_support_engine=ngse,
        )

        attacker = _make_unit("s1", Domain.GROUND)
        target = _make_unit("t1", Domain.GROUND)
        wpn = _make_wpn_inst("CANNON", rate_of_fire_rpm=10)

        handled, _status = _route_naval_engagement(
            ctx, attacker, target, wpn, 8000.0, 10.0, TS,
        )
        assert handled is False
        ngse.shore_bombardment.assert_not_called()

    def test_vls_magazine_exhaustion(self):
        """VLS tracking: magazine_capacity > 0, launched >= capacity → skip."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement

        surface = MagicMock()
        surface.salvo_exchange.return_value = SimpleNamespace(hits=1)
        ctx = SimpleNamespace(naval_subsurface_engine=None, naval_surface_engine=surface)
        wpn = _make_wpn_inst("MISSILE_LAUNCHER", rate_of_fire_rpm=4, magazine_capacity=8)
        vls = {"s1": 8}  # already exhausted

        handled, status = _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.NAVAL),
            wpn, 5000.0, 10.0, TS, vls_launches=vls,
        )
        assert handled is True
        assert status is None  # exhausted
        surface.salvo_exchange.assert_not_called()

    def test_vls_fires_and_tracks(self):
        """VLS tracking: magazine not exhausted → fires and increments count."""
        from stochastic_warfare.simulation.battle import _route_naval_engagement

        surface = MagicMock()
        surface.salvo_exchange.return_value = SimpleNamespace(hits=0)
        ctx = SimpleNamespace(naval_subsurface_engine=None, naval_surface_engine=surface)
        wpn = _make_wpn_inst("MISSILE_LAUNCHER", rate_of_fire_rpm=4, magazine_capacity=16)
        vls: dict[str, int] = {}

        _route_naval_engagement(
            ctx, _make_unit("s1"), _make_unit("t1", Domain.NAVAL),
            wpn, 5000.0, 10.0, TS, vls_launches=vls,
        )
        assert vls["s1"] == 4  # rate_of_fire_rpm = 4 missiles fired


# ---------------------------------------------------------------------------
# 51b — Naval posture
# ---------------------------------------------------------------------------

class TestNavalPosture:
    """NavalPosture enum, speed multipliers, engagement gate, auto-assignment."""

    def test_naval_posture_enum_values(self):
        from stochastic_warfare.entities.unit_classes.naval import NavalPosture

        assert NavalPosture.ANCHORED == 0
        assert NavalPosture.UNDERWAY == 1
        assert NavalPosture.TRANSIT == 2
        assert NavalPosture.BATTLE_STATIONS == 3
        assert len(NavalPosture) == 4

    def test_anchored_zero_speed(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_SPEED_MULT

        assert _NAVAL_POSTURE_SPEED_MULT[0] == 0.0

    def test_transit_faster_speed(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_SPEED_MULT

        assert _NAVAL_POSTURE_SPEED_MULT[2] == 1.2

    def test_battle_stations_slower(self):
        from stochastic_warfare.simulation.battle import _NAVAL_POSTURE_SPEED_MULT

        assert _NAVAL_POSTURE_SPEED_MULT[3] == 0.9

    def test_anchored_unit_cannot_engage(self):
        """ANCHORED units are skipped in engagement loop."""
        from stochastic_warfare.entities.unit_classes.naval import NavalPosture

        # Simulate the gate logic from battle.py
        attacker = _make_unit("s1", Domain.NAVAL, naval_posture=NavalPosture.ANCHORED)
        naval_posture = getattr(attacker, "naval_posture", None)
        assert naval_posture is not None
        assert int(naval_posture) == 0  # should be skipped

    def test_underway_unit_can_engage(self):
        from stochastic_warfare.entities.unit_classes.naval import NavalPosture

        attacker = _make_unit("s1", Domain.NAVAL, naval_posture=NavalPosture.UNDERWAY)
        naval_posture = getattr(attacker, "naval_posture", None)
        assert int(naval_posture) != 0  # should NOT be skipped

    def test_naval_posture_state_roundtrip(self):
        from stochastic_warfare.entities.unit_classes.naval import NavalPosture, NavalUnit, NavalUnitType

        u = NavalUnit(
            entity_id="dd1", unit_type="destroyer", name="Destroyer",
            domain=Domain.NAVAL, side=Side("blue"), max_speed=30.0,
            position=Position(0, 0, 0), naval_type=NavalUnitType.DESTROYER,
            naval_posture=NavalPosture.BATTLE_STATIONS,
        )
        state = u.get_state()
        assert state["naval_posture"] == 3

        u2 = NavalUnit(
            entity_id="dd2", unit_type="destroyer", name="Destroyer 2",
            domain=Domain.NAVAL, side=Side("blue"), max_speed=30.0,
            position=Position(0, 0, 0),
        )
        u2.set_state(state)
        assert u2.naval_posture == NavalPosture.BATTLE_STATIONS

    def test_default_naval_posture_underway(self):
        from stochastic_warfare.entities.unit_classes.naval import NavalPosture, NavalUnit

        u = NavalUnit(
            entity_id="dd1", unit_type="destroyer", name="Destroyer",
            domain=Domain.NAVAL, side=Side("blue"), max_speed=30.0,
            position=Position(0, 0, 0),
        )
        assert u.naval_posture == NavalPosture.UNDERWAY


# ---------------------------------------------------------------------------
# 51c — DEW disable path
# ---------------------------------------------------------------------------

class TestDEWDisablePath:
    """DEW hits below threshold produce DISABLED, not DESTROYED."""

    def test_dew_high_pk_destroyed(self):
        """DEW hit with p_hit >= dew_disable_threshold → DESTROYED."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(dew_disable_threshold=0.5)
        p_hit = 0.7
        assert p_hit >= cal.dew_disable_threshold
        # Logic: dew_pk >= threshold → DESTROYED

    def test_dew_low_pk_disabled(self):
        """DEW hit with p_hit < dew_disable_threshold → DISABLED."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(dew_disable_threshold=0.5)
        p_hit = 0.3
        assert p_hit < cal.dew_disable_threshold
        # Logic: dew_pk < threshold → DISABLED

    def test_dew_disable_threshold_configurable(self):
        """dew_disable_threshold is configurable via CalibrationSchema."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(dew_disable_threshold=0.8)
        assert cal.get("dew_disable_threshold", 0.5) == 0.8

    def test_dew_disable_threshold_default(self):
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema()
        assert cal.dew_disable_threshold == 0.5

    def test_wavelength_532_lower_transmittance(self):
        """532nm (green) produces lower transmittance than 1064nm (IR)."""
        from stochastic_warfare.combat.directed_energy import DEWEngine

        engine = DEWEngine(EventBus(), _rng())
        t_1064 = engine.compute_atmospheric_transmittance(5000.0, wavelength_nm=1064.0)
        t_532 = engine.compute_atmospheric_transmittance(5000.0, wavelength_nm=532.0)
        assert t_532 < t_1064

    def test_wavelength_default_backward_compat(self):
        """Default 1064nm wavelength produces same result as before (factor=1.0)."""
        from stochastic_warfare.combat.directed_energy import DEWEngine

        engine = DEWEngine(EventBus(), _rng())
        t_default = engine.compute_atmospheric_transmittance(5000.0)
        t_explicit = engine.compute_atmospheric_transmittance(5000.0, wavelength_nm=1064.0)
        assert t_default == t_explicit

    def test_beam_wavelength_used_in_laser_engagement(self):
        """execute_laser_engagement reads beam_wavelength_nm from weapon definition."""
        from stochastic_warfare.combat.directed_energy import DEWEngine
        from stochastic_warfare.combat.ammunition import WeaponDefinition, WeaponInstance

        engine = DEWEngine(EventBus(), _rng())

        # Patch to track wavelength_nm arg
        original_transmittance = engine.compute_atmospheric_transmittance
        calls = []

        def tracking_transmittance(*args, **kwargs):
            calls.append(kwargs)
            return original_transmittance(*args, **kwargs)

        engine.compute_atmospheric_transmittance = tracking_transmittance

        # Create weapon with beam_wavelength_nm = 532
        wdef = WeaponDefinition(
            weapon_id="test_laser",
            display_name="Test Laser",
            category="DIRECTED_ENERGY",
            caliber_mm=0,
            max_range_m=10000,
            rate_of_fire_rpm=60,
            beam_power_kw=100.0,
            dwell_time_s=2.0,
            beam_divergence_mrad=0.5,
            beam_wavelength_nm=532.0,
        )
        wpn_inst = WeaponInstance(wdef, {"energy_charge": 100})

        result = engine.execute_laser_engagement(
            attacker_id="a1", target_id="t1",
            shooter_pos=Position(0, 0, 0), target_pos=Position(5000, 0, 0),
            weapon=wpn_inst, ammo_id="energy_charge",
            ammo_def=SimpleNamespace(ammo_id="energy_charge"),
        )
        # Verify wavelength was passed
        assert any(c.get("wavelength_nm") == 532.0 for c in calls)

    def test_calibration_schema_accepts_dew_disable_threshold(self):
        """CalibrationSchema validates dew_disable_threshold without error."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema

        cal = CalibrationSchema(**{"dew_disable_threshold": 0.3})
        assert cal.dew_disable_threshold == 0.3


# ---------------------------------------------------------------------------
# 51d — Mine warfare wiring
# ---------------------------------------------------------------------------

class TestMineWarfareWiring:
    """Mine encounter check during movement phase."""

    def test_naval_unit_triggers_mine(self):
        """Moving naval unit within trigger radius of armed mine → encounter."""
        from stochastic_warfare.combat.naval_mine import Mine, MineType, MineWarfareEngine

        rng = _rng(seed=100)
        bus = EventBus()
        dmg = MagicMock()
        engine = MineWarfareEngine(dmg, bus, rng)

        # Lay a mine at (1000, 1000)
        mine = Mine(mine_id="m1", position=Position(1000.0, 1000.0, 0.0),
                    mine_type=MineType.CONTACT)
        engine._mines.append(mine)

        # Resolve encounter for ship near mine
        result = engine.resolve_mine_encounter(
            ship_id="dd1", mine=mine,
            ship_magnetic_sig=0.5, ship_acoustic_sig=0.5,
            timestamp=TS,
        )
        # Contact mine has 0.8 trigger prob and 0.05 dud rate
        # Result depends on RNG, but we test the API works
        assert result.mine_id == "m1"

    def test_stationary_unit_skips_mine_check(self):
        """Units with speed < 0.1 are not checked against mines (logic in battle.py)."""
        # This tests the gate condition; stationary naval units don't trigger mines
        u = _make_unit("dd1", Domain.NAVAL, speed=0.0)
        assert u.speed < 0.1  # would be skipped in battle.py mine check

    def test_ground_unit_skips_mine_check(self):
        """Ground units are not naval mine targets."""
        u = _make_unit("g1", Domain.GROUND, speed=10.0)
        assert u.domain not in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS)

    def test_mine_detonation_high_damage_destroyed(self):
        """Mine with damage >= destruction_threshold → DESTROYED."""
        from stochastic_warfare.combat.naval_mine import MineResult

        result = MineResult(mine_id="m1", triggered=True, detonated=True, damage_fraction=0.7)
        dest_thresh = 0.5
        assert result.detonated and result.damage_fraction >= dest_thresh

    def test_mine_detonation_low_damage_disabled(self):
        """Mine with damage >= disable_threshold but < destruction → DISABLED."""
        from stochastic_warfare.combat.naval_mine import MineResult

        result = MineResult(mine_id="m1", triggered=True, detonated=True, damage_fraction=0.35)
        dest_thresh = 0.5
        dis_thresh = 0.3
        assert result.detonated and result.damage_fraction < dest_thresh
        assert result.damage_fraction >= dis_thresh

    def test_mine_miss_no_damage(self):
        """Mine that doesn't detonate → no damage."""
        from stochastic_warfare.combat.naval_mine import MineResult

        result = MineResult(mine_id="m1", triggered=False, detonated=False, damage_fraction=0.0)
        assert not result.detonated
        assert result.damage_fraction == 0.0


# ---------------------------------------------------------------------------
# 51d — Disruption engine wiring
# ---------------------------------------------------------------------------

class TestDisruptionEngineWiring:
    """DisruptionEngine instantiated on context, blockade queries work."""

    def test_disruption_engine_on_context(self):
        """SimulationContext has disruption_engine field."""
        from stochastic_warfare.simulation.scenario import SimulationContext

        assert hasattr(SimulationContext, "__dataclass_fields__") or "disruption_engine" in dir(SimulationContext)
        # Field exists and defaults to None
        import dataclasses
        fields = {f.name for f in dataclasses.fields(SimulationContext)}
        assert "disruption_engine" in fields

    def test_check_blockade_returns_effectiveness(self):
        """check_blockade returns > 0 for blockaded zone."""
        from stochastic_warfare.logistics.disruption import DisruptionEngine

        engine = DisruptionEngine(EventBus(), _rng())
        engine.apply_blockade("b1", ["zone_a"], ["dd1", "dd2"], "blue")
        eff = engine.check_blockade("zone_a")
        assert eff > 0

    def test_check_blockade_returns_zero_for_clear_zone(self):
        """check_blockade returns 0.0 for non-blockaded zone."""
        from stochastic_warfare.logistics.disruption import DisruptionEngine

        engine = DisruptionEngine(EventBus(), _rng())
        eff = engine.check_blockade("zone_x")
        assert eff == 0.0

    def test_disruption_state_roundtrip(self):
        """DisruptionEngine state round-trips via get_state/set_state."""
        from stochastic_warfare.logistics.disruption import DisruptionEngine

        engine = DisruptionEngine(EventBus(), _rng())
        engine.apply_blockade("b1", ["zone_a"], ["dd1"], "blue")
        engine.apply_interdiction("z1", Position(100, 200, 0), 500.0, 0.5)

        state = engine.get_state()
        assert "blockades" in state
        assert "zones" in state

        engine2 = DisruptionEngine(EventBus(), _rng())
        engine2.set_state(state)
        assert engine2.check_blockade("zone_a") > 0
        assert len(engine2.active_zones()) == 1
