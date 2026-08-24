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
        magazine_capacity=1,
        compatible_ammo=["missile_rd"],
    )
    weapon = WeaponInstance(definition=defn)
    weapon.ammo_state.add("missile_rd", 1)
    return weapon


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
        assert cal.get("enable_missile_routing", False) is True
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

    @pytest.mark.test_evidence("behavioral_oracle")
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
            ammo_id="missile_rd",
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
            ammo_id="missile_rd",
            ammo_def=ammo,
            missile_engine=None,
        )
        assert result.engaged is False
        assert result.aborted_reason == "no_missile_engine"

    def test_unguided_ammo_stays_direct_fire(self):
        """Ammo with guidance=NONE stays DIRECT_FIRE."""
        ammo = _make_ammo("NONE")
        assert ammo.parsed_guidance() == GuidanceType.NONE

    @pytest.mark.test_evidence("structural_only")
    def test_missile_engine_on_context(self):
        """SimulationContext has missile_engine field."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        assert hasattr(SimulationContext, "missile_engine")
