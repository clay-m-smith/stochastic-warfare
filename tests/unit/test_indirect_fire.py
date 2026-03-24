"""Tests for combat/indirect_fire.py."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import (
    FireMissionType,
    IndirectFireEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> IndirectFireEngine:
    rng = _rng(seed)
    bus = EventBus()
    bal = BallisticsEngine(rng)
    dmg = DamageEngine(bus, rng)
    return IndirectFireEngine(bal, dmg, bus, rng)


def _howitzer() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="m284", display_name="M284 155mm", category="HOWITZER",
        caliber_mm=155.0, muzzle_velocity_mps=684.0,
        max_range_m=30000.0, base_accuracy_mrad=0.4, cep_m=267.0,
        compatible_ammo=["m795_he"],
    )


def _he() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="m795_he", display_name="M795 HE", ammo_type="HE",
        mass_kg=46.7, diameter_mm=155.0, blast_radius_m=50.0,
        fragmentation_radius_m=150.0,
    )


def _guided() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="m982_excalibur", display_name="Excalibur", ammo_type="GUIDED",
        guidance="GPS", pk_at_reference=0.9, blast_radius_m=40.0,
    )


def _mlrs() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="m270", display_name="M270 MLRS", category="ROCKET_LAUNCHER",
        caliber_mm=227.0, max_range_m=45000.0, cep_m=300.0,
        compatible_ammo=["m26_mlrs_rocket", "m31_gmlrs"],
    )


def _unguided_rocket() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="m26_mlrs_rocket", display_name="M26 Rocket", ammo_type="ROCKET",
        guidance="INERTIAL", submunition_count=644,
    )


def _gmlrs() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="m31_gmlrs", display_name="GMLRS", ammo_type="GUIDED",
        guidance="GPS", pk_at_reference=0.95, blast_radius_m=50.0,
    )


class TestFireMission:
    def test_basic_fire_mission(self) -> None:
        e = _engine()
        result = e.fire_mission(
            "b1", Position(0, 0, 0), Position(0, 15000, 0),
            _howitzer(), _he(), FireMissionType.FIRE_FOR_EFFECT, 6,
        )
        assert result.rounds_fired == 6
        assert len(result.impacts) == 6
        assert result.suppression_achieved is True

    def test_impacts_scatter_around_target(self) -> None:
        e = _engine()
        target = Position(5000.0, 10000.0, 0.0)
        result = e.fire_mission(
            "b1", Position(0, 0, 0), target,
            _howitzer(), _he(), FireMissionType.FIRE_FOR_EFFECT, 20,
        )
        eastings = [ip.position.easting for ip in result.impacts]
        northings = [ip.position.northing for ip in result.impacts]
        # Should scatter around target
        assert min(eastings) < target.easting
        assert max(eastings) > target.easting
        mean_e = sum(eastings) / len(eastings)
        assert abs(mean_e - target.easting) < 200.0

    def test_guided_round_tighter_pattern(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        target = Position(5000.0, 10000.0, 0.0)

        unguided = e1.fire_mission(
            "b1", Position(0, 0, 0), target,
            _howitzer(), _he(), FireMissionType.FIRE_FOR_EFFECT, 20,
        )
        guided = e2.fire_mission(
            "b1", Position(0, 0, 0), target,
            _howitzer(), _guided(), FireMissionType.FIRE_FOR_EFFECT, 20,
        )

        def spread(result):
            es = [ip.position.easting - target.easting for ip in result.impacts]
            ns = [ip.position.northing - target.northing for ip in result.impacts]
            return sum(e**2 + n**2 for e, n in zip(es, ns)) / len(es)

        assert spread(guided) < spread(unguided)

    def test_ffe_tighter_than_adjust(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        target = Position(0, 15000, 0)

        adjust = e1.fire_mission(
            "b1", Position(0, 0, 0), target,
            _howitzer(), _he(), FireMissionType.ADJUST_FIRE, 20,
        )
        ffe = e2.fire_mission(
            "b1", Position(0, 0, 0), target,
            _howitzer(), _he(), FireMissionType.FIRE_FOR_EFFECT, 20,
        )

        def spread(result):
            es = [ip.position.easting - target.easting for ip in result.impacts]
            return sum(e**2 for e in es) / len(es)

        assert spread(ffe) < spread(adjust)

    def test_few_rounds_no_suppression(self) -> None:
        e = _engine()
        result = e.fire_mission(
            "b1", Position(0, 0, 0), Position(0, 15000, 0),
            _howitzer(), _he(), FireMissionType.ADJUST_FIRE, 2,
        )
        assert result.suppression_achieved is False

    def test_illumination_no_suppression(self) -> None:
        illum = AmmoDefinition(
            ammo_id="illum", display_name="Illum", ammo_type="ILLUMINATION",
            blast_radius_m=0.0,
        )
        e = _engine()
        result = e.fire_mission(
            "b1", Position(0, 0, 0), Position(0, 15000, 0),
            _howitzer(), illum, FireMissionType.ILLUMINATION, 4,
        )
        assert result.suppression_achieved is False


class TestRocketSalvo:
    def test_basic_salvo(self) -> None:
        e = _engine()
        result = e.rocket_salvo(
            "l1", Position(0, 0, 0), Position(0, 30000, 0),
            _mlrs(), _unguided_rocket(), 12,
        )
        assert result.rockets_fired == 12
        assert len(result.impacts) == 12

    def test_gmlrs_tight_pattern(self) -> None:
        e = _engine()
        target = Position(0, 40000, 0)
        result = e.rocket_salvo(
            "l1", Position(0, 0, 0), target,
            _mlrs(), _gmlrs(), 6,
        )
        # GMLRS should have very tight pattern (GPS guided)
        for ip in result.impacts:
            dist = math.sqrt(
                (ip.position.easting - target.easting) ** 2
                + (ip.position.northing - target.northing) ** 2
            )
            assert dist < 100.0  # Within 100m for GPS-guided


class TestCounterbattery:
    def test_counterbattery_solution(self) -> None:
        e = _engine()
        solution = e.compute_counterbattery_solution(
            incoming_direction_rad=0.0,  # from north
            estimated_range_m=20000.0,
        )
        # Should be approximately 20km north with some error
        assert abs(solution.northing - 20000.0) < 1000.0

    def test_counterbattery_has_error(self) -> None:
        results = []
        for seed in range(20):
            eng = _engine(seed)
            r = eng.compute_counterbattery_solution(0.0, 20000.0)
            results.append(r.northing)
        # Should not all be identical
        assert max(results) - min(results) > 10.0

    def test_deterministic_with_seed(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.compute_counterbattery_solution(1.0, 15000.0)
        r2 = e2.compute_counterbattery_solution(1.0, 15000.0)
        assert r1.easting == pytest.approx(r2.easting)


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.fire_mission("b1", Position(0, 0, 0), Position(0, 15000, 0),
                        _howitzer(), _he(), FireMissionType.FIRE_FOR_EFFECT, 2)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.compute_counterbattery_solution(0.0, 10000.0)
        r2 = e2.compute_counterbattery_solution(0.0, 10000.0)
        assert r1.easting == pytest.approx(r2.easting)
