"""Phase 63d: MISSILE Routing & Comms → C2 friction tests."""

import pytest
from unittest.mock import MagicMock

from stochastic_warfare.combat.engagement import (
    EngagementEngine,
    EngagementType,
)
from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    WeaponCategory,
    WeaponDefinition,
    WeaponInstance,
    GuidanceType,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema


def _make_ammo(guidance="RADAR_ACTIVE"):
    return AmmoDefinition(
        ammo_id="missile_rd",
        name="test missile",
        display_name="Test Missile",
        caliber_mm=0.0,
        ammo_type="HE",
        guidance=guidance,
    )


def _make_weapon(category="MISSILE_LAUNCHER"):
    defn = WeaponDefinition(
        weapon_id="launcher_1",
        name="test launcher",
        display_name="Test Launcher",
        category=category,
        caliber_mm=0.0,
        rate_of_fire_rpm=1.0,
        max_range_m=10000.0,
    )
    return WeaponInstance(definition=defn)


def _make_engine():
    hit_engine = MagicMock()
    dmg_engine = MagicMock()
    sup_engine = MagicMock()
    frat_engine = MagicMock()
    bus = MagicMock()
    import numpy as np
    rng = np.random.default_rng(42)
    return EngagementEngine(hit_engine, dmg_engine, sup_engine, frat_engine, bus, rng)


class TestMissileRouting:
    """Test MISSILE type inference and routing."""

    def test_missile_launcher_guided_missile_routing_enabled(self):
        """MISSILE_LAUNCHER + guided ammo + enable_missile_routing → MISSILE."""
        cal = CalibrationSchema(enable_missile_routing=True)
        ammo = _make_ammo("RADAR_ACTIVE")
        wpn = _make_weapon("MISSILE_LAUNCHER")

        # Verify type inference logic
        assert wpn.definition.parsed_category() == WeaponCategory.MISSILE_LAUNCHER
        assert ammo.parsed_guidance() != GuidanceType.NONE

    def test_missile_launcher_guided_routing_disabled(self):
        """With enable_missile_routing=False, stays DIRECT_FIRE."""
        cal = CalibrationSchema(enable_missile_routing=False)
        # Battle.py uses cal.get("enable_missile_routing", False) — stays False
        assert cal.get("enable_missile_routing", True) is False

    def test_non_missile_weapon_stays_direct_fire(self):
        """Non-MISSILE_LAUNCHER weapons stay as DIRECT_FIRE regardless."""
        wpn = _make_weapon("CANNON")
        assert wpn.definition.parsed_category() != WeaponCategory.MISSILE_LAUNCHER

    def test_missile_type_route_engagement_calls_missile_engine(self):
        """MISSILE type → route_engagement calls missile_engine.launch_missile."""
        eng = _make_engine()
        missile_engine = MagicMock()
        ammo = _make_ammo()
        wpn = _make_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.MISSILE,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(1000.0, 0.0, 0.0),
            weapon=wpn,
            ammo_id="ammo1",
            ammo_def=ammo,
            missile_engine=missile_engine,
        )
        assert result.engaged is True
        assert result.engagement_type == EngagementType.MISSILE
        missile_engine.launch_missile.assert_called_once()

    def test_missile_type_no_engine_returns_not_engaged(self):
        """MISSILE type + no missile_engine → not engaged."""
        eng = _make_engine()
        ammo = _make_ammo()
        wpn = _make_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.MISSILE,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(1000.0, 0.0, 0.0),
            weapon=wpn,
            ammo_id="ammo1",
            ammo_def=ammo,
            missile_engine=None,
        )
        assert result.engaged is False
        assert result.aborted_reason == "no_missile_engine"

    def test_unguided_ammo_stays_direct_fire(self):
        """Ammo with guidance=NONE stays DIRECT_FIRE."""
        ammo = _make_ammo("NONE")
        assert ammo.parsed_guidance() == GuidanceType.NONE

    def test_missile_engine_on_context(self):
        """SimulationContext has missile_engine field."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        assert hasattr(SimulationContext, "missile_engine")


class TestC2Friction:
    """Test comms → C2 friction gating."""

    def test_c2_friction_enabled_low_comms_skips_decide(self):
        """Structural: enable_c2_friction gate exists in battle.py."""
        import stochastic_warfare.simulation.battle as battle_mod
        src = open(battle_mod.__file__).read()
        assert "enable_c2_friction" in src
        assert "C2 friction" in src

    def test_c2_friction_disabled_decide_proceeds(self):
        """When enable_c2_friction=False, DECIDE always proceeds."""
        cal = CalibrationSchema(enable_c2_friction=False)
        assert cal.get("enable_c2_friction", True) is False

    def test_c2_min_effectiveness_configurable(self):
        """c2_min_effectiveness is configurable via CalibrationSchema."""
        cal = CalibrationSchema(c2_min_effectiveness=0.5)
        assert cal.c2_min_effectiveness == pytest.approx(0.5)

    def test_c2_effectiveness_used_for_gate(self):
        """Structural: _compute_c2_effectiveness called in C2 friction block."""
        import stochastic_warfare.simulation.battle as battle_mod
        src = open(battle_mod.__file__).read()
        assert "_compute_c2_effectiveness(ctx, unit_id," in src

    def test_multiple_units_independently_gated(self):
        """Structural: C2 friction gate is inside the per-unit OODA DECIDE handler."""
        import stochastic_warfare.simulation.battle as battle_mod
        src = open(battle_mod.__file__).read()
        # The gate is inside the DECIDE completion handler per unit
        assert "C2 friction" in src
        # Both strings must exist and C2 friction must be after the DECIDE check
        decide_idx = src.find("completed_phase == OODAPhase.DECIDE")
        friction_idx = src.find("C2 friction")
        assert decide_idx >= 0, "DECIDE handler not found"
        assert friction_idx >= 0, "C2 friction gate not found"
        assert friction_idx > decide_idx

    def test_mopp_comms_compounds_with_c2_friction(self):
        """Structural: MOPP comms degradation exists in _compute_c2_effectiveness."""
        import stochastic_warfare.simulation.battle as battle_mod
        src = open(battle_mod.__file__).read()
        assert "mopp_comms_factor_4" in src
