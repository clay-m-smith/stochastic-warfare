"""Phase 71a: bug-fix tests — _sim_time_s ordering and missing launch_missile args."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.engagement import EngagementEngine, EngagementType
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# 71a-1: _sim_time_s used before assignment
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 71a-2: Missing launcher_id / missile_id in engagement.py
# ---------------------------------------------------------------------------


class TestLaunchMissileArgs:
    """Verify COASTAL_DEFENSE and AIR_LAUNCHED_ASHM pass required args."""

    def _launch_kwargs(self, engagement_type: EngagementType) -> dict:
        engine = EngagementEngine(
            hit_engine=MagicMock(),
            damage_engine=MagicMock(),
            suppression_engine=MagicMock(),
            fratricide_engine=MagicMock(),
            event_bus=EventBus(),
            rng=np.random.default_rng(71),
        )
        ammo_id = "phase71_missile"
        weapon = WeaponInstance(
            definition=WeaponDefinition(
                weapon_id="phase71_launcher",
                display_name="Phase 71 launcher",
                category="MISSILE_LAUNCHER",
                caliber_mm=150.0,
                max_range_m=10_000.0,
                rate_of_fire_rpm=6.0,
                magazine_capacity=5,
                compatible_ammo=[ammo_id],
            ),
            ammo_state=AmmoState(rounds_by_type={ammo_id: 5}),
        )
        ammo = AmmoDefinition(
            ammo_id=ammo_id,
            display_name="Phase 71 missile",
            ammo_type="MISSILE",
        )
        missile_engine = MagicMock()

        result = engine.route_engagement(
            engagement_type=engagement_type,
            attacker_id="phase71_attacker",
            target_id="phase71_target",
            attacker_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(1_000.0, 0.0, 0.0),
            weapon=weapon,
            ammo_id=ammo_id,
            ammo_def=ammo,
            missile_engine=missile_engine,
            current_time_s=71.0,
        )

        assert result.engaged is True
        missile_engine.launch_missile.assert_called_once()
        return missile_engine.launch_missile.call_args.kwargs

    def test_coastal_defense_has_launcher_id(self):
        """COASTAL_DEFENSE sends the actual attacker as launcher_id."""
        kwargs = self._launch_kwargs(EngagementType.COASTAL_DEFENSE)
        assert kwargs["launcher_id"] == "phase71_attacker"

    def test_coastal_defense_has_missile_id(self):
        """COASTAL_DEFENSE sends a route-specific missile identity."""
        kwargs = self._launch_kwargs(EngagementType.COASTAL_DEFENSE)
        assert kwargs["missile_id"] == "phase71_attacker_coastal_71"

    def test_air_launched_ashm_has_launcher_id(self):
        """AIR_LAUNCHED_ASHM sends the actual attacker as launcher_id."""
        kwargs = self._launch_kwargs(EngagementType.AIR_LAUNCHED_ASHM)
        assert kwargs["launcher_id"] == "phase71_attacker"

    def test_air_launched_ashm_has_missile_id(self):
        """AIR_LAUNCHED_ASHM sends a route-specific missile identity."""
        kwargs = self._launch_kwargs(EngagementType.AIR_LAUNCHED_ASHM)
        assert kwargs["missile_id"] == "phase71_attacker_ashm_71"

    def test_missile_handler_unchanged(self):
        """Generic MISSILE routing preserves both production identities."""
        kwargs = self._launch_kwargs(EngagementType.MISSILE)
        assert kwargs["launcher_id"] == "phase71_attacker"
        assert kwargs["missile_id"] == "phase71_attacker_missile_71"
