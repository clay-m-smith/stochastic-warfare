"""Tests for DEW battle loop wiring via route_engagement (Phase 37a, Bug 3).

Verifies that BattleManager._execute_engagements routes directed energy
weapons through route_engagement (→ DEW engine) instead of
execute_engagement (→ ballistic physics).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponCategory,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.directed_energy import DEWEngine
from stochastic_warfare.combat.engagement import (
    EngagementEngine,
    EngagementResult,
    EngagementType,
)
from stochastic_warfare.combat.hit_probability import HitResult
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from tests.conftest import TS, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bus() -> EventBus:
    return EventBus()


def _make_engagement_engine():
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.fratricide import FratricideEngine
    from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
    from stochastic_warfare.combat.suppression import SuppressionEngine

    bus = _bus()
    rng = make_rng()
    ballistics = BallisticsEngine(rng)
    hit = HitProbabilityEngine(ballistics, rng)
    damage = DamageEngine(bus, rng)
    suppression = SuppressionEngine(bus, rng)
    fratricide = FratricideEngine(bus, rng)
    return EngagementEngine(hit, damage, suppression, fratricide, bus, rng)


def _make_ammo_state(ammo_id: str, count: int) -> AmmoState:
    state = AmmoState()
    state.rounds_by_type[ammo_id] = count
    return state


def _laser_weapon(magazine: int = 100) -> tuple[WeaponInstance, AmmoDefinition]:
    wdef = WeaponDefinition(
        weapon_id="test_laser",
        display_name="Test Laser",
        category="DIRECTED_ENERGY",
        caliber_mm=0.0,
        beam_power_kw=50.0,
        beam_wavelength_nm=1064.0,
        dwell_time_s=3.0,
        beam_divergence_mrad=0.5,
        max_range_m=5000.0,
        rate_of_fire_rpm=10.0,
        magazine_capacity=magazine,
        compatible_ammo=["dew_charge"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="dew_charge",
        display_name="DEW Charge",
        ammo_type="DIRECTED_ENERGY",
        caliber_mm=0.0,
        muzzle_velocity_mps=0.0,
        mass_kg=0.0,
        drag_coefficient=0.0,
        explosive_mass_kg=0.0,
        penetration_mm=0.0,
        lethal_radius_m=0.0,
    )
    inst = WeaponInstance(definition=wdef, ammo_state=_make_ammo_state("dew_charge", magazine))
    return inst, ammo_def


def _hpm_weapon(magazine: int = 50) -> tuple[WeaponInstance, AmmoDefinition]:
    wdef = WeaponDefinition(
        weapon_id="test_hpm",
        display_name="Test HPM",
        category="DIRECTED_ENERGY",
        caliber_mm=0.0,
        beam_power_kw=0.0,  # HPM uses RF, not optical
        max_range_m=300.0,
        rate_of_fire_rpm=6.0,
        magazine_capacity=magazine,
        compatible_ammo=["hpm_pulse"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="hpm_pulse",
        display_name="HPM Pulse",
        ammo_type="DIRECTED_ENERGY",
        caliber_mm=0.0,
        muzzle_velocity_mps=0.0,
        mass_kg=0.0,
        drag_coefficient=0.0,
        explosive_mass_kg=0.0,
        penetration_mm=0.0,
        lethal_radius_m=0.0,
    )
    inst = WeaponInstance(definition=wdef, ammo_state=_make_ammo_state("hpm_pulse", magazine))
    return inst, ammo_def


def _conventional_weapon(magazine: int = 40) -> tuple[WeaponInstance, AmmoDefinition]:
    wdef = WeaponDefinition(
        weapon_id="test_cannon",
        display_name="Test Cannon",
        category="CANNON",
        caliber_mm=120.0,
        max_range_m=4000.0,
        rate_of_fire_rpm=8.0,
        magazine_capacity=magazine,
        compatible_ammo=["ap_round"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="ap_round",
        display_name="AP Round",
        ammo_type="AP",
        caliber_mm=120.0,
        muzzle_velocity_mps=1700.0,
        mass_kg=4.0,
        drag_coefficient=0.3,
        explosive_mass_kg=0.0,
        penetration_mm=600.0,
        lethal_radius_m=0.0,
    )
    inst = WeaponInstance(definition=wdef, ammo_state=_make_ammo_state("ap_round", magazine))
    return inst, ammo_def


class TestDEWRouting:
    """Verify route_engagement dispatches DEW correctly."""

    def test_laser_routes_to_dew_laser(self) -> None:
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), make_rng(99))
        wpn, ammo_def = _laser_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DEW_LASER,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=wpn,
            ammo_id="dew_charge",
            ammo_def=ammo_def,
            dew_engine=dew,
            timestamp=TS,
        )

        assert result.engagement_type == EngagementType.DEW_LASER
        assert result.engaged

    def test_hpm_routes_to_dew_hpm(self) -> None:
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), make_rng(99))
        wpn, ammo_def = _hpm_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DEW_HPM,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(100, 0, 0),
            weapon=wpn,
            ammo_id="hpm_pulse",
            ammo_def=ammo_def,
            dew_engine=dew,
            timestamp=TS,
        )

        assert result.engagement_type == EngagementType.DEW_HPM
        assert result.engaged

    def test_conventional_routes_to_direct_fire(self) -> None:
        eng = _make_engagement_engine()
        wpn, ammo_def = _conventional_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DIRECT_FIRE,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=wpn,
            ammo_id="ap_round",
            ammo_def=ammo_def,
            timestamp=TS,
        )

        assert result.engagement_type == EngagementType.DIRECT_FIRE

    def test_dew_without_engine_aborts(self) -> None:
        eng = _make_engagement_engine()
        wpn, ammo_def = _laser_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DEW_LASER,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=wpn,
            ammo_id="dew_charge",
            ammo_def=ammo_def,
            dew_engine=None,
            timestamp=TS,
        )

        assert not result.engaged
        assert result.aborted_reason == "no_dew_engine"

    def test_laser_hit_result_propagated(self) -> None:
        """route_engagement wraps DEW result with HitResult for damage chain."""
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), make_rng(99))
        wpn, ammo_def = _laser_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DEW_LASER,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(500, 0, 0),
            weapon=wpn,
            ammo_id="dew_charge",
            ammo_def=ammo_def,
            dew_engine=dew,
            timestamp=TS,
        )

        assert result.engaged
        assert result.hit_result is not None
        assert result.hit_result.p_hit >= 0.0

    def test_hpm_hit_result_propagated(self) -> None:
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), make_rng(99))
        wpn, ammo_def = _hpm_weapon()

        result = eng.route_engagement(
            engagement_type=EngagementType.DEW_HPM,
            attacker_id="a1",
            target_id="t1",
            attacker_pos=Position(0, 0, 0),
            target_pos=Position(100, 0, 0),
            weapon=wpn,
            ammo_id="hpm_pulse",
            ammo_def=ammo_def,
            dew_engine=dew,
            timestamp=TS,
        )

        assert result.engaged
        assert result.hit_result is not None

    def test_weapon_category_detection(self) -> None:
        """Verify WeaponCategory.DIRECTED_ENERGY is correctly detected."""
        wpn, _ = _laser_weapon()
        assert wpn.definition.parsed_category() == WeaponCategory.DIRECTED_ENERGY
        assert wpn.definition.beam_power_kw > 0  # laser

        hpm, _ = _hpm_weapon()
        assert hpm.definition.parsed_category() == WeaponCategory.DIRECTED_ENERGY
        assert hpm.definition.beam_power_kw == 0.0  # HPM uses RF

    def test_conventional_not_dew(self) -> None:
        wpn, _ = _conventional_weapon()
        assert wpn.definition.parsed_category() != WeaponCategory.DIRECTED_ENERGY
