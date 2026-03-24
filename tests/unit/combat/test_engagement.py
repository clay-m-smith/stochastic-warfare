"""Unit tests for EngagementEngine — kill chain orchestration and routing."""

from __future__ import annotations


import pytest

from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.engagement import (
    EngagementConfig,
    EngagementEngine,
    EngagementType,
)
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.suppression import SuppressionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _make_ap, _make_gun, _make_weapon_instance, _rng


def _make_engagement_engine(
    seed: int = 42,
    **cfg_kwargs,
) -> EngagementEngine:
    bus = EventBus()
    rng = _rng(seed)
    ballistics = BallisticsEngine(rng)
    damage = DamageEngine(bus, _rng(seed + 1))
    hit = HitProbabilityEngine(ballistics, _rng(seed + 2))
    suppression = SuppressionEngine(bus, _rng(seed + 3))
    fratricide = FratricideEngine(bus, _rng(seed + 4))
    config = EngagementConfig(**cfg_kwargs) if cfg_kwargs else None
    return EngagementEngine(
        hit_engine=hit,
        damage_engine=damage,
        suppression_engine=suppression,
        fratricide_engine=fratricide,
        event_bus=bus,
        rng=_rng(seed + 5),
        config=config,
    )


class TestCanEngage:
    def test_within_range(self):
        eng = _make_engagement_engine()
        weapon = _make_gun(max_range_m=3000.0)
        assert eng.can_engage(Position(0, 0, 0), Position(1000, 0, 0), weapon)

    def test_beyond_max_range(self):
        eng = _make_engagement_engine()
        weapon = _make_gun(max_range_m=3000.0)
        assert not eng.can_engage(Position(0, 0, 0), Position(5000, 0, 0), weapon)

    def test_below_min_range(self):
        eng = _make_engagement_engine()
        weapon = _make_gun(max_range_m=10000.0)
        weapon_dict = weapon.model_dump()
        weapon_dict["min_range_m"] = 3000.0
        from stochastic_warfare.combat.ammunition import WeaponDefinition
        sam = WeaponDefinition.model_validate(weapon_dict)
        assert not eng.can_engage(Position(0, 0, 0), Position(1000, 0, 0), sam)


class TestSelectTarget:
    def test_threat_priority(self):
        eng = _make_engagement_engine()
        weapon = _make_gun(max_range_m=5000.0)
        contacts = [
            {"contact_id": "low", "position": (1000, 0), "threat_level": 0.2, "value": 0.3},
            {"contact_id": "high", "position": (1000, 0), "threat_level": 0.9, "value": 0.8},
        ]
        selected = eng.select_target(contacts, weapon, Position(0, 0, 0))
        assert selected == "high"

    def test_no_valid_targets(self):
        eng = _make_engagement_engine()
        weapon = _make_gun(max_range_m=100.0)
        contacts = [
            {"contact_id": "far", "position": (5000, 0), "threat_level": 0.5, "value": 0.5},
        ]
        assert eng.select_target(contacts, weapon, Position(0, 0, 0)) is None


class TestExecuteEngagement:
    """Direct-fire kill chain execution."""

    def test_successful_engagement(self):
        eng = _make_engagement_engine(seed=42)
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.execute_engagement(
            attacker_id="blue_1",
            target_id="red_1",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=weapon,
            ammo_id="test_ap",
            ammo_def=ammo,
        )
        assert result.engaged
        assert result.hit_result is not None
        assert result.range_m == pytest.approx(1000.0)

    def test_out_of_range_aborts(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.execute_engagement(
            attacker_id="blue_1",
            target_id="red_1",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(10000, 0, 0),
            weapon=weapon,
            ammo_id="test_ap",
            ammo_def=ammo,
        )
        assert not result.engaged
        assert result.aborted_reason == "out_of_range"

    def test_no_ammo_aborts(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=0)
        ammo = _make_ap()
        result = eng.execute_engagement(
            attacker_id="blue_1",
            target_id="red_1",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(1000, 0, 0),
            weapon=weapon,
            ammo_id="test_ap",
            ammo_def=ammo,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_ammo"

    def test_terrain_cover_reduces_hit(self):
        """Terrain cover modifier flows through to hit probability."""
        eng = _make_engagement_engine(seed=100)
        weapon = _make_weapon_instance(rounds=100)
        ammo = _make_ap()
        # Run many engagements to check statistical hit rate
        hits_exposed = 0
        hits_covered = 0
        for i in range(50):
            w1 = _make_weapon_instance(rounds=10)
            r = eng.execute_engagement(
                attacker_id="b", target_id="r",
                shooter_pos=Position(0, 0, 0), target_pos=Position(500, 0, 0),
                weapon=w1, ammo_id="test_ap", ammo_def=ammo,
                terrain_cover=0.0,
            )
            if r.hit_result and r.hit_result.hit:
                hits_exposed += 1

        eng2 = _make_engagement_engine(seed=100)
        for i in range(50):
            w2 = _make_weapon_instance(rounds=10)
            r = eng2.execute_engagement(
                attacker_id="b", target_id="r",
                shooter_pos=Position(0, 0, 0), target_pos=Position(500, 0, 0),
                weapon=w2, ammo_id="test_ap", ammo_def=ammo,
                terrain_cover=0.7,
            )
            if r.hit_result and r.hit_result.hit:
                hits_covered += 1
        # With 70% cover, should have fewer hits
        assert hits_covered <= hits_exposed

    def test_fratricide_aborts_friendly(self):
        eng = _make_engagement_engine(fratricide_abort_threshold=0.05)
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.execute_engagement(
            attacker_id="blue_1",
            target_id="blue_2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(500, 0, 0),
            weapon=weapon,
            ammo_id="test_ap",
            ammo_def=ammo,
            target_is_friendly=True,
            identification_level="UNKNOWN",
            identification_confidence=0.1,
        )
        assert not result.engaged
        assert result.aborted_reason == "fratricide_risk"


class TestRouteEngagement:
    """Engagement type dispatching."""

    def test_direct_fire_routing(self):
        eng = _make_engagement_engine(seed=42)
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.route_engagement(
            EngagementType.DIRECT_FIRE,
            "blue_1", "red_1",
            Position(0, 0, 0), Position(1000, 0, 0),
            weapon, "test_ap", ammo,
        )
        assert result.engaged

    def test_coastal_defense_requires_missile_engine(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.route_engagement(
            EngagementType.COASTAL_DEFENSE,
            "blue_1", "red_1",
            Position(0, 0, 0), Position(5000, 0, 0),
            weapon, "test_ap", ammo,
            missile_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_missile_engine"

    def test_dew_laser_requires_dew_engine(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.route_engagement(
            EngagementType.DEW_LASER,
            "blue_1", "red_1",
            Position(0, 0, 0), Position(1000, 0, 0),
            weapon, "test_ap", ammo,
            dew_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_dew_engine"

    def test_dew_hpm_requires_dew_engine(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.route_engagement(
            EngagementType.DEW_HPM,
            "blue_1", "red_1",
            Position(0, 0, 0), Position(1000, 0, 0),
            weapon, "test_ap", ammo,
            dew_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_dew_engine"

    def test_air_launched_ashm_requires_missile_engine(self):
        eng = _make_engagement_engine()
        weapon = _make_weapon_instance(rounds=10)
        ammo = _make_ap()
        result = eng.route_engagement(
            EngagementType.AIR_LAUNCHED_ASHM,
            "blue_1", "red_1",
            Position(0, 0, 0), Position(5000, 0, 0),
            weapon, "test_ap", ammo,
            missile_engine=None,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_missile_engine"

    def test_state_roundtrip(self):
        eng = _make_engagement_engine(seed=55)
        state = eng.get_state()
        eng2 = _make_engagement_engine(seed=1)
        eng2.set_state(state)
        assert eng._rng.random() == eng2._rng.random()
