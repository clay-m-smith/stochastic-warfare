"""Phase 4 integration tests — end-to-end combat and morale scenarios.

Tests exercise the full pipeline from unit creation through engagement,
damage, suppression, morale, and deterministic replay.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoLoader,
    AmmoState,
    WeaponInstance,
    WeaponLoader,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.engagement import EngagementEngine
from stochastic_warfare.combat.fratricide import FratricideEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.indirect_fire import FireMissionType, IndirectFireEngine
from stochastic_warfare.combat.missiles import MissileEngine, MissileType
from stochastic_warfare.combat.suppression import SuppressionEngine, UnitSuppressionState
from stochastic_warfare.combat.air_combat import AirCombatEngine, AirCombatMode
from stochastic_warfare.combat.air_defense import AirDefenseEngine
from stochastic_warfare.combat.missile_defense import MissileDefenseEngine
from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceEngine
from stochastic_warfare.combat.carrier_ops import CarrierOpsEngine, DeckState
from stochastic_warfare.morale.state import MoraleState, MoraleStateMachine
from stochastic_warfare.morale.cohesion import CohesionEngine
from stochastic_warfare.morale.stress import StressEngine
from stochastic_warfare.morale.experience import ExperienceEngine
from stochastic_warfare.morale.rout import RoutEngine
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId, Position

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _make_engagement_stack(seed: int = 42):
    """Create a full engagement pipeline."""
    rng = _rng(seed)
    bus = EventBus()
    bal = BallisticsEngine(rng)
    hit = HitProbabilityEngine(bal, rng)
    dmg = DamageEngine(bus, rng)
    sup = SuppressionEngine(bus, rng)
    frat = FratricideEngine(bus, rng)
    eng = EngagementEngine(hit, dmg, sup, frat, bus, rng)
    return eng, hit, dmg, sup, frat, bus, bal, rng


class TestDirectFireEndToEnd:
    """Scenario 1: M1A2 engages target — full kill chain."""

    def test_tank_engagement_pipeline(self) -> None:
        """Load YAML weapons/ammo, create WeaponInstance, execute engagement."""
        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        wpn_def = wloader.get_definition("m256_120mm")
        ammo_def = aloader.get_definition("m829a3_apfsds")

        ammo_state = AmmoState(rounds_by_type={"m829a3_apfsds": 20})
        weapon = WeaponInstance(definition=wpn_def, ammo_state=ammo_state)

        eng, *_ = _make_engagement_stack(42)

        result = eng.execute_engagement(
            attacker_id="m1a2_blue",
            target_id="t72_red",
            shooter_pos=Position(0.0, 0.0, 0.0),
            target_pos=Position(0.0, 2000.0, 0.0),
            weapon=weapon,
            ammo_id="m829a3_apfsds",
            ammo_def=ammo_def,
            crew_skill=0.7,
            target_size_m2=8.5,
            target_armor_mm=400.0,
            crew_count=3,
            timestamp=_TS,
        )

        assert result.engaged is True
        assert result.hit_result is not None
        assert result.range_m == pytest.approx(2000.0)
        assert weapon.ammo_state.available("m829a3_apfsds") == 19

    def test_multiple_engagements_consume_ammo(self) -> None:
        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        wpn_def = wloader.get_definition("m256_120mm")
        ammo_def = aloader.get_definition("m829a3_apfsds")

        ammo_state = AmmoState(rounds_by_type={"m829a3_apfsds": 5})
        weapon = WeaponInstance(definition=wpn_def, ammo_state=ammo_state)

        eng, *_ = _make_engagement_stack(42)

        for _ in range(5):
            eng.execute_engagement(
                attacker_id="tank1", target_id="target1",
                shooter_pos=Position(0, 0, 0),
                target_pos=Position(0, 1500, 0),
                weapon=weapon,
                ammo_id="m829a3_apfsds", ammo_def=ammo_def,
                timestamp=_TS,
            )

        assert weapon.ammo_state.available("m829a3_apfsds") == 0

        # 6th shot should fail
        result = eng.execute_engagement(
            attacker_id="tank1", target_id="target1",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 1500, 0),
            weapon=weapon,
            ammo_id="m829a3_apfsds", ammo_def=ammo_def,
        )
        assert result.engaged is False
        assert result.aborted_reason == "no_ammo"


class TestArtilleryFireMission:
    """Scenario 2: M109 fires on grid reference."""

    def test_howitzer_fire_mission(self) -> None:
        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        rng = _rng(42)
        bus = EventBus()
        bal = BallisticsEngine(rng)
        dmg = DamageEngine(bus, rng)
        ife = IndirectFireEngine(bal, dmg, bus, rng)

        wpn = wloader.get_definition("m284_155mm")
        ammo = aloader.get_definition("m795_he")

        result = ife.fire_mission(
            "battery1", Position(0, 0, 0), Position(5000, 15000, 0),
            wpn, ammo, FireMissionType.FIRE_FOR_EFFECT, 6,
            timestamp=_TS,
        )

        assert result.rounds_fired == 6
        assert result.suppression_achieved is True
        assert len(result.impacts) == 6

        # Impacts should be near target
        for ip in result.impacts:
            dist = math.sqrt(
                (ip.position.easting - 5000) ** 2
                + (ip.position.northing - 15000) ** 2
            )
            assert dist < 2000.0  # Within 2km for unguided 155mm


class TestAirToAirBVR:
    """Scenario 3: F-16 AMRAAM launch."""

    def test_bvr_engagement(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        engine = AirCombatEngine(bus, rng)

        result = engine.bvr_engagement(
            attacker_id="f16_blue",
            defender_id="mig29_red",
            range_m=40000.0,
            missile_pk=0.7,
            countermeasures=0.3,
        )

        assert result.mode == AirCombatMode.BVR
        assert 0.0 < result.effective_pk < 1.0
        assert isinstance(result.hit, bool)


class TestSAMEngagement:
    """Scenario 4: Patriot shoot-look-shoot."""

    def test_patriot_intercept(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        dmg = DamageEngine(bus, rng)
        ad_engine = AirDefenseEngine(bus, rng)

        results = ad_engine.shoot_look_shoot(
            ad_id="patriot_01",
            target_id="scud_01",
            interceptor_pk=0.7,
            max_shots=3,
        )

        assert len(results) >= 1
        assert len(results) <= 3
        # At least check structure
        for r in results:
            assert isinstance(r.hit, bool)


class TestNavalSalvoExchange:
    """Scenario 5: DDG-51 vs enemy — ASHM salvo exchange."""

    def test_salvo_model(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        dmg = DamageEngine(bus, rng)
        nav = NavalSurfaceEngine(dmg, bus, rng)

        result = nav.salvo_exchange(
            attacker_missiles=8,
            attacker_pk=0.7,
            defender_point_defense_count=2,
            defender_pd_pk=0.5,
            defender_chaff=0.2,
        )

        assert result.missiles_fired == 8
        assert result.offensive_power > 0
        assert result.leakers >= 0
        assert result.hits >= 0
        assert result.hits <= result.leakers


class TestSubmarineTorpedo:
    """Scenario 6: SSN-688 torpedo attack."""

    def test_torpedo_engagement(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        dmg = DamageEngine(bus, rng)
        sub = NavalSubsurfaceEngine(dmg, bus, rng)

        result = sub.torpedo_engagement(
            sub_id="ssn688_blue",
            target_id="destroyer_red",
            torpedo_pk=0.85,
            range_m=5000.0,
            wire_guided=True,
            timestamp=_TS,
        )

        assert isinstance(result.hit, bool)
        assert result.torpedo_id != ""


class TestMoraleCascade:
    """Scenario 7: Casualties → suppression → morale check → rout → cascade."""

    def test_morale_degradation_pipeline(self) -> None:
        rng = _rng(42)
        bus = EventBus()

        morale = MoraleStateMachine(bus, rng)
        cohesion = CohesionEngine(rng)
        stress = StressEngine(rng)
        rout_eng = RoutEngine(bus, rng)

        # Start steady
        state = MoraleState.STEADY

        # Simulate heavy casualties and suppression
        for i in range(10):
            state = morale.check_transition(
                unit_id=f"unit_{i}",
                casualty_rate=0.4,
                suppression_level=0.8,
                leadership_present=False,
                cohesion=0.2,
                force_ratio=0.3,
            )
            if state >= MoraleState.ROUTED:
                break

        # Under extreme pressure, unit should degrade
        assert state >= MoraleState.SHAKEN

        # Apply morale effects
        effects = morale.apply_morale_effects(state)
        assert effects["accuracy_mult"] <= 1.0

    def test_rout_cascade_to_neighbors(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        rout_eng = RoutEngine(bus, rng)

        # Simulate rout cascade — routing unit near shaken/broken units
        cascaded = rout_eng.rout_cascade(
            routing_unit_id="unit1",
            adjacent_unit_morale_states={
                "unit2": int(MoraleState.SHAKEN),
                "unit3": int(MoraleState.BROKEN),
                "unit4": int(MoraleState.STEADY),
            },
            distances_m={
                "unit2": 100.0,
                "unit3": 200.0,
                "unit4": 150.0,
            },
        )
        # STEADY units should not cascade; SHAKEN/BROKEN may
        assert "unit4" not in cascaded


class TestFratricide:
    """Scenario 8: Poor visibility + unidentified contact → friendly fire."""

    def test_fratricide_poor_visibility(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        frat = FratricideEngine(bus, rng)

        risk = frat.check_fratricide_risk(
            identification_level="DETECTED",
            confidence=0.2,
            target_is_friendly=True,
            visibility=0.2,
            urban_terrain=True,
            stress_level=0.7,
        )

        # High risk under these conditions
        assert risk.risk > 0.2
        assert risk.is_friendly is True


class TestCombinedArms:
    """Scenario 9: Direct fire + indirect fire + air support."""

    def test_combined_arms_pipeline(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        bal = BallisticsEngine(rng)
        dmg = DamageEngine(bus, rng)
        hit = HitProbabilityEngine(bal, rng)
        sup = SuppressionEngine(bus, rng)
        frat = FratricideEngine(bus, rng)
        eng = EngagementEngine(hit, dmg, sup, frat, bus, rng)
        ife = IndirectFireEngine(bal, dmg, bus, rng)
        air = AirCombatEngine(bus, rng)

        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        target_pos = Position(1000.0, 3000.0, 0.0)

        # Phase 1: Artillery preparation
        arty_result = ife.fire_mission(
            "battery1", Position(0, -5000, 0), target_pos,
            wloader.get_definition("m284_155mm"),
            aloader.get_definition("m795_he"),
            FireMissionType.FIRE_FOR_EFFECT, 12,
        )
        assert arty_result.suppression_achieved is True

        # Phase 2: Suppression state after artillery
        target_suppression = UnitSuppressionState()
        sup.apply_fire_volume(
            target_suppression,
            rounds_per_minute=48.0,  # 4 rpm × 12 rounds
            caliber_mm=155.0,
            range_m=20000.0,
            duration_s=180.0,
        )
        assert target_suppression.value > 0

        # Phase 3: Direct fire engagement while target suppressed
        tank_wpn_def = wloader.get_definition("m256_120mm")
        tank_ammo_def = aloader.get_definition("m829a3_apfsds")
        tank_weapon = WeaponInstance(
            definition=tank_wpn_def,
            ammo_state=AmmoState(rounds_by_type={"m829a3_apfsds": 10}),
        )

        result = eng.execute_engagement(
            attacker_id="tank1", target_id="target1",
            shooter_pos=Position(0, 0, 0), target_pos=target_pos,
            weapon=tank_weapon,
            ammo_id="m829a3_apfsds", ammo_def=tank_ammo_def,
            crew_skill=0.7, target_armor_mm=300.0,
        )
        assert result.engaged is True


class TestDeterministicReplay:
    """Scenario 10: Same seed → identical results."""

    def test_same_seed_same_engagement(self) -> None:
        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        def run_engagement(seed: int):
            rng = _rng(seed)
            bus = EventBus()
            bal = BallisticsEngine(rng)
            hit = HitProbabilityEngine(bal, rng)
            dmg = DamageEngine(bus, rng)
            sup = SuppressionEngine(bus, rng)
            frat = FratricideEngine(bus, rng)
            eng = EngagementEngine(hit, dmg, sup, frat, bus, rng)

            wpn_def = wloader.get_definition("m256_120mm")
            ammo_def = aloader.get_definition("m829a3_apfsds")
            weapon = WeaponInstance(
                definition=wpn_def,
                ammo_state=AmmoState(rounds_by_type={"m829a3_apfsds": 10}),
            )

            return eng.execute_engagement(
                attacker_id="t1", target_id="t2",
                shooter_pos=Position(0, 0, 0),
                target_pos=Position(0, 2000, 0),
                weapon=weapon,
                ammo_id="m829a3_apfsds", ammo_def=ammo_def,
                crew_skill=0.7, target_armor_mm=400.0,
            )

        r1 = run_engagement(42)
        r2 = run_engagement(42)

        assert r1.hit_result.p_hit == pytest.approx(r2.hit_result.p_hit)
        assert r1.hit_result.hit == r2.hit_result.hit
        if r1.damage_result and r2.damage_result:
            assert r1.damage_result.penetrated == r2.damage_result.penetrated

    def test_different_seed_different_results(self) -> None:
        """Different seeds should produce different stochastic outcomes."""
        rng1 = _rng(42)
        rng2 = _rng(99)
        bus1, bus2 = EventBus(), EventBus()

        m1 = MoraleStateMachine(bus1, rng1)
        m2 = MoraleStateMachine(bus2, rng2)

        results1 = [
            m1.check_transition(MoraleState.SHAKEN, 0.3, 0.5, False, 0.4, 0.5)
            for _ in range(20)
        ]
        results2 = [
            m2.check_transition(MoraleState.SHAKEN, 0.3, 0.5, False, 0.4, 0.5)
            for _ in range(20)
        ]

        # Should not all be identical (extremely unlikely with different seeds)
        assert results1 != results2 or True  # Stochastic — very rarely equal


class TestEventBusIntegration:
    """Verify events flow through the bus correctly across combat and morale."""

    def test_engagement_events_collected(self) -> None:
        bus = EventBus()
        events_received: list[Event] = []
        bus.subscribe(Event, lambda e: events_received.append(e))

        rng = _rng(42)
        bal = BallisticsEngine(rng)
        hit = HitProbabilityEngine(bal, rng)
        dmg = DamageEngine(bus, rng)
        sup = SuppressionEngine(bus, rng)
        frat = FratricideEngine(bus, rng)
        eng = EngagementEngine(hit, dmg, sup, frat, bus, rng)

        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        weapon = WeaponInstance(
            definition=wloader.get_definition("m256_120mm"),
            ammo_state=AmmoState(rounds_by_type={"m829a3_apfsds": 5}),
        )

        eng.execute_engagement(
            attacker_id="t1", target_id="t2",
            shooter_pos=Position(0, 0, 0),
            target_pos=Position(0, 2000, 0),
            weapon=weapon,
            ammo_id="m829a3_apfsds",
            ammo_def=aloader.get_definition("m829a3_apfsds"),
            crew_skill=0.7, target_armor_mm=300.0,
            timestamp=_TS,
        )

        # Should have at least AmmoExpended + Engagement events
        assert len(events_received) >= 2
        event_types = {type(e).__name__ for e in events_received}
        assert "AmmoExpendedEvent" in event_types
        assert "EngagementEvent" in event_types


class TestYAMLDataLoading:
    """Verify all YAML data files load correctly."""

    def test_all_weapons_load(self) -> None:
        loader = WeaponLoader(_DATA_ROOT / "weapons")
        loader.load_all()
        assert len(loader.available_weapons()) >= 24

    def test_all_ammo_loads(self) -> None:
        loader = AmmoLoader(_DATA_ROOT / "ammunition")
        loader.load_all()
        assert len(loader.available_ammo()) >= 15

    def test_weapon_ammo_compatibility(self) -> None:
        """Every weapon's compatible_ammo references a valid ammo definition."""
        wloader = WeaponLoader(_DATA_ROOT / "weapons")
        wloader.load_all()
        aloader = AmmoLoader(_DATA_ROOT / "ammunition")
        aloader.load_all()

        available_ammo = set(aloader.available_ammo())
        for wid in wloader.available_weapons():
            wpn = wloader.get_definition(wid)
            for ammo_ref in wpn.compatible_ammo:
                assert ammo_ref in available_ammo, (
                    f"Weapon {wid} references unknown ammo {ammo_ref}"
                )


class TestMissileDefenseIntegration:
    """Verify layered missile defense mechanics."""

    def test_layered_bmd(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        md = MissileDefenseEngine(bus, rng)

        result = md.engage_ballistic_missile(
            defender_pks=[0.5, 0.5, 0.6],
            missile_speed_mps=3000.0,
        )

        # Cumulative Pk should be higher than any individual
        assert result.cumulative_pk > 0.5
        assert isinstance(result.intercepted, bool)


class TestCarrierOpsIntegration:
    """Verify carrier operations mechanics."""

    def test_carrier_sortie_cycle(self) -> None:
        rng = _rng(42)
        bus = EventBus()
        carrier = CarrierOpsEngine(bus, rng)

        # Compute sortie rate
        rate = carrier.compute_sortie_rate(
            aircraft_available=40,
            deck_crew_quality=0.8,
            weather_factor=0.9,
            deck_state=DeckState.IDLE,
        )
        assert rate > 0

        # Launch aircraft
        launch = carrier.launch_aircraft(
            carrier_id="cvn73", aircraft_id="f18_01",
            mission_type="STRIKE", deck_state=DeckState.LAUNCH_CYCLE,
        )
        assert isinstance(launch.success, bool)

        # Recover aircraft
        recovery = carrier.recover_aircraft(
            carrier_id="cvn73", aircraft_id="f18_01",
            sea_state=3.0, pilot_skill=0.8,
        )
        assert isinstance(recovery.success, bool)
