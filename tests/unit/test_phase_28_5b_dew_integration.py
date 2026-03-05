"""Phase 28.5b — DEW integration tests.

Tests engagement routing, AD unit type extension, scenario wiring,
and enum extensions for directed energy weapons.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)

from stochastic_warfare.combat.directed_energy import DEWConfig, DEWEngine
from stochastic_warfare.combat.engagement import EngagementType
from stochastic_warfare.entities.unit_classes.air_defense import ADUnitType, AirDefenseUnit
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from tests.conftest import TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _bus() -> EventBus:
    return EventBus()


def _make_engagement_engine():
    """Minimal EngagementEngine for routing tests."""
    from stochastic_warfare.combat.engagement import EngagementConfig, EngagementEngine
    from stochastic_warfare.combat.ballistics import BallisticsEngine
    from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
    from stochastic_warfare.combat.damage import DamageEngine
    from stochastic_warfare.combat.suppression import SuppressionEngine
    from stochastic_warfare.combat.fratricide import FratricideEngine

    bus = _bus()
    rng = _rng()
    ballistics = BallisticsEngine(rng)
    hit = HitProbabilityEngine(ballistics, rng)
    damage = DamageEngine(bus, rng)
    suppression = SuppressionEngine(bus, rng)
    fratricide = FratricideEngine(bus, rng)
    return EngagementEngine(hit, damage, suppression, fratricide, bus, rng)


def _laser_weapon(magazine: int = 100):
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
        mass_kg=0.0,
    )
    ammo_state = AmmoState(rounds_by_type={"dew_charge": magazine})
    weapon = WeaponInstance(wdef, ammo_state)
    return weapon, "dew_charge", ammo_def


def _hpm_weapon(magazine: int = 50):
    wdef = WeaponDefinition(
        weapon_id="test_hpm",
        display_name="Test HPM",
        category="DIRECTED_ENERGY",
        caliber_mm=0.0,
        max_range_m=1000.0,
        rate_of_fire_rpm=5.0,
        magazine_capacity=magazine,
        compatible_ammo=["hpm_pulse"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="hpm_pulse",
        display_name="HPM Pulse",
        ammo_type="DIRECTED_ENERGY",
        mass_kg=0.0,
    )
    ammo_state = AmmoState(rounds_by_type={"hpm_pulse": magazine})
    weapon = WeaponInstance(wdef, ammo_state)
    return weapon, "hpm_pulse", ammo_def


# ===========================================================================
# Engagement Router
# ===========================================================================


class TestEngagementRouterDEW:
    def test_dew_laser_no_engine_aborted(self) -> None:
        eng = _make_engagement_engine()
        weapon, ammo_id, ammo_def = _laser_weapon()

        result = eng.route_engagement(
            EngagementType.DEW_LASER,
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            dew_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_dew_engine"

    def test_dew_hpm_no_engine_aborted(self) -> None:
        eng = _make_engagement_engine()
        weapon, ammo_id, ammo_def = _hpm_weapon()

        result = eng.route_engagement(
            EngagementType.DEW_HPM,
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(300, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            dew_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_dew_engine"

    def test_dew_laser_with_engine(self) -> None:
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), _rng(0))
        weapon, ammo_id, ammo_def = _laser_weapon()

        result = eng.route_engagement(
            EngagementType.DEW_LASER,
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            dew_engine=dew,
        )
        assert result.engaged
        assert result.engagement_type == EngagementType.DEW_LASER

    def test_dew_hpm_with_engine(self) -> None:
        eng = _make_engagement_engine()
        dew = DEWEngine(_bus(), _rng(0))
        weapon, ammo_id, ammo_def = _hpm_weapon()

        result = eng.route_engagement(
            EngagementType.DEW_HPM,
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(300, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            dew_engine=dew,
        )
        assert result.engaged
        assert result.engagement_type == EngagementType.DEW_HPM

    def test_direct_fire_still_works(self) -> None:
        eng = _make_engagement_engine()
        wdef = WeaponDefinition(
            weapon_id="m1_gun",
            display_name="M1 Gun",
            category="CANNON",
            caliber_mm=120.0,
            max_range_m=4000.0,
            rate_of_fire_rpm=6.0,
            compatible_ammo=["ap_round"],
        )
        ammo_def = AmmoDefinition(
            ammo_id="ap_round",
            display_name="AP",
            ammo_type="AP",
            mass_kg=5.0,
            penetration_mm_rha=500.0,
        )
        weapon = WeaponInstance(wdef, AmmoState(rounds_by_type={"ap_round": 40}))

        result = eng.route_engagement(
            EngagementType.DIRECT_FIRE,
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(2000, 0, 0),
            weapon=weapon, ammo_id="ap_round", ammo_def=ammo_def,
        )
        assert result.engaged

    def test_unknown_type_aborted(self) -> None:
        eng = _make_engagement_engine()
        weapon, ammo_id, ammo_def = _laser_weapon()

        # Use a value beyond the enum
        result = eng.route_engagement(
            999,  # type: ignore[arg-type]
            attacker_id="a", target_id="b",
            attacker_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
        )
        assert not result.engaged
        assert result.aborted_reason == "unknown_engagement_type"

    def test_engagement_type_enum_values(self) -> None:
        assert EngagementType.DEW_LASER == 12
        assert EngagementType.DEW_HPM == 13

    def test_existing_types_unaffected(self) -> None:
        assert EngagementType.DIRECT_FIRE == 0
        assert EngagementType.MISSILE == 2
        assert EngagementType.ATGM_VS_ROTARY == 11


# ===========================================================================
# AD Unit Type
# ===========================================================================


class TestADUnitTypeDEW:
    def test_dew_enum_value(self) -> None:
        assert ADUnitType.DEW == 8

    def test_dew_unit_creation(self) -> None:
        unit = AirDefenseUnit(
            entity_id="dew_1",
            position=Position(0, 0, 0),
            ad_type=ADUnitType.DEW,
        )
        assert unit.ad_type == ADUnitType.DEW

    def test_existing_types_unaffected(self) -> None:
        assert ADUnitType.SAM_LONG == 0
        assert ADUnitType.CIWS == 5
        assert ADUnitType.RADAR_FIRE_CONTROL == 7


# ===========================================================================
# Scenario Wiring
# ===========================================================================


class TestScenarioWiring:
    def test_ctx_dew_engine_default_none(self) -> None:
        from stochastic_warfare.simulation.scenario import SimulationContext, CampaignScenarioConfig
        # Verify the field exists and defaults to None
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(SimulationContext)}
        assert "dew_engine" in fields
        assert fields["dew_engine"].default is None

    def test_config_accepts_dew_config(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
        assert "dew_config" in CampaignScenarioConfig.model_fields

    def test_config_dew_config_null(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-06-15",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000, "cell_size_m": 10},
            sides=[
                {"side": "red", "units": []},
                {"side": "blue", "units": []},
            ],
            dew_config=None,
        )
        assert cfg.dew_config is None

    def test_config_dew_config_empty_dict(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-06-15",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000, "cell_size_m": 10},
            sides=[
                {"side": "red", "units": []},
                {"side": "blue", "units": []},
            ],
            dew_config={},
        )
        assert cfg.dew_config == {}

    def test_config_dew_config_custom(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-06-15",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000, "cell_size_m": 10},
            sides=[
                {"side": "red", "units": []},
                {"side": "blue", "units": []},
            ],
            dew_config={"base_extinction_per_km": 0.3},
        )
        assert cfg.dew_config["base_extinction_per_km"] == 0.3

    def test_dew_engine_state_roundtrip(self) -> None:
        bus = _bus()
        rng = _rng()
        dew = DEWEngine(bus, rng)
        state = dew.get_state()
        assert "rng_state" in state

        dew2 = DEWEngine(bus, _rng(99))
        dew2.set_state(state)
        # Verify same RNG state produces same output
        v1 = dew._rng.random()
        v2 = dew2._rng.random()
        assert v1 == v2


# Enum extension tests in test_phase_28_5a_dew_physics.py (TestEnumExtensions)
