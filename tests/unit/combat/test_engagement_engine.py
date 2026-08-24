"""Tests for combat/engagement.py — orchestrator kill chain."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.engagement import (
    EngagementEngine,
    EngagementType,
)
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.suppression import SuppressionEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _weapon_def() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="gun", display_name="Gun", category="CANNON",
        caliber_mm=120.0, muzzle_velocity_mps=1750.0,
        base_accuracy_mrad=0.2, max_range_m=4000.0,
        min_range_m=50.0, compatible_ammo=["ap"],
    )


def _ammo_def() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="ap", display_name="AP", ammo_type="AP",
        mass_kg=8.9, diameter_mm=120.0, drag_coefficient=0.15,
        penetration_mm_rha=750.0, penetration_reference_range_m=2000.0,
    )


def _weapon_instance(rounds: int = 10) -> WeaponInstance:
    return WeaponInstance(
        definition=_weapon_def(),
        ammo_state=AmmoState(rounds_by_type={"ap": rounds}),
    )


def _engine(seed: int = 42) -> EngagementEngine:
    rng = _rng(seed)
    bus = EventBus()
    bal = BallisticsEngine(rng)
    hit = HitProbabilityEngine(bal, rng)
    dmg = DamageEngine(bus, rng)
    sup = SuppressionEngine(bus, rng)
    frat = FratricideEngine(bus, rng)
    return EngagementEngine(hit, dmg, sup, frat, bus, rng)


class TestCanEngage:
    def test_in_range(self) -> None:
        e = _engine()
        assert e.can_engage(
            Position(0, 0, 0), Position(0, 2000, 0), _weapon_def(),
        ) is True

    def test_out_of_range(self) -> None:
        e = _engine()
        assert e.can_engage(
            Position(0, 0, 0), Position(0, 5000, 0), _weapon_def(),
        ) is False

    def test_too_close(self) -> None:
        e = _engine()
        assert e.can_engage(
            Position(0, 0, 0), Position(0, 20, 0), _weapon_def(),
        ) is False


class TestSelectTarget:
    def test_selects_highest_threat(self) -> None:
        e = _engine()
        contacts = [
            {"contact_id": "c1", "position": (0, 1000, 0), "threat_level": 0.3, "value": 0.5},
            {"contact_id": "c2", "position": (0, 1500, 0), "threat_level": 0.9, "value": 0.5},
            {"contact_id": "c3", "position": (0, 2000, 0), "threat_level": 0.5, "value": 0.5},
        ]
        target = e.select_target(contacts, _weapon_def(), Position(0, 0, 0))
        assert target == "c2"

    def test_filters_out_of_range(self) -> None:
        e = _engine()
        contacts = [
            {"contact_id": "c1", "position": (0, 10000, 0), "threat_level": 0.9, "value": 0.9},
        ]
        target = e.select_target(contacts, _weapon_def(), Position(0, 0, 0))
        assert target is None

    def test_empty_contacts_returns_none(self) -> None:
        e = _engine()
        target = e.select_target([], _weapon_def(), Position(0, 0, 0))
        assert target is None

    def test_prefers_high_value(self) -> None:
        e = _engine()
        contacts = [
            {"contact_id": "c1", "position": (0, 1000, 0), "threat_level": 0.5, "value": 0.2},
            {"contact_id": "c2", "position": (0, 1000, 0), "threat_level": 0.5, "value": 0.9},
        ]
        target = e.select_target(contacts, _weapon_def(), Position(0, 0, 0))
        assert target == "c2"


class TestExecuteEngagement:
    def test_successful_engagement(self) -> None:
        e = _engine(42)
        result = e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
            crew_skill=0.8, target_armor_mm=200.0,
        )
        assert result.engaged is True
        assert result.hit_result is not None
        assert result.ammo_id == "ap"

    def test_out_of_range_aborted(self) -> None:
        e = _engine()
        result = e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 5000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
        )
        assert result.engaged is False
        assert result.aborted_reason == "out_of_range"

    def test_no_ammo_aborted(self) -> None:
        e = _engine()
        result = e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(rounds=0),
            ammo_id="ap", ammo_def=_ammo_def(),
        )
        assert result.engaged is False
        assert result.aborted_reason == "no_ammo"

    def test_fratricide_high_risk_aborted(self) -> None:
        e = _engine()
        result = e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
            identification_level="UNKNOWN",
            identification_confidence=0.0,
            target_is_friendly=True,
        )
        assert result.engaged is False
        assert result.aborted_reason == "fratricide_risk"

    def test_ammo_consumed_on_fire(self) -> None:
        e = _engine()
        wi = _weapon_instance(rounds=5)
        e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=wi,
            ammo_id="ap", ammo_def=_ammo_def(),
        )
        assert wi.ammo_state.available("ap") == 4

    def test_hit_produces_damage(self) -> None:
        # Run many trials to get at least one hit
        for seed in range(100):
            e = _engine(seed)
            result = e.execute_engagement(
                attacker_id="u1", target_id="u2",
                shooter_pos=Position(0, 0, 0),
                target_pos=Position(0, 1000, 0),
                weapon=_weapon_instance(),
                ammo_id="ap", ammo_def=_ammo_def(),
                crew_skill=0.9, target_armor_mm=200.0,
            )
            if result.hit_result and result.hit_result.hit:
                assert result.damage_result is not None
                break
        else:
            pytest.fail("No hits in 100 trials at close range")

    def test_deterministic_with_same_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)

        r1 = e1.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
        )
        r2 = e2.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
        )
        assert r1.hit_result.p_hit == pytest.approx(r2.hit_result.p_hit)
        assert r1.hit_result.hit == r2.hit_result.hit

    def test_events_published(self) -> None:
        from datetime import datetime, timezone
        bus = EventBus()
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        rng = _rng(42)
        bal = BallisticsEngine(rng)
        hit = HitProbabilityEngine(bal, rng)
        dmg = DamageEngine(bus, rng)
        sup = SuppressionEngine(bus, rng)
        frat = FratricideEngine(bus, rng)
        e = EngagementEngine(hit, dmg, sup, frat, bus, rng)

        e.execute_engagement(
            attacker_id="u1", target_id="u2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=_weapon_instance(),
            ammo_id="ap", ammo_def=_ammo_def(),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        # Should have at least AmmoExpended + Engagement events
        assert len(received) >= 2


class TestEngagementType:
    def test_enum_values(self) -> None:
        assert EngagementType.DIRECT_FIRE == 0
        assert EngagementType.MINE == 8
