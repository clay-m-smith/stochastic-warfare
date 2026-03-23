"""Unit tests for IndirectFireEngine — fire missions, rockets, counterbattery, TOT."""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.indirect_fire import (
    FireMissionResult,
    FireMissionType,
    IndirectFireConfig,
    IndirectFireEngine,
    SalvoResult,
    TOTFirePlan,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _make_gun, _make_he, _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_indirect_engine(
    seed: int = 42,
    **cfg_kwargs,
) -> IndirectFireEngine:
    bus = EventBus()
    rng = _rng(seed)
    ballistics = BallisticsEngine(_rng(seed + 1))
    damage = DamageEngine(bus, _rng(seed + 2))
    config = IndirectFireConfig(**cfg_kwargs) if cfg_kwargs else None
    return IndirectFireEngine(ballistics, damage, bus, rng, config)


def _howitzer() -> tuple:
    """Return a (weapon, ammo) pair for a 155mm howitzer."""
    from stochastic_warfare.combat.ammunition import WeaponDefinition

    weapon = WeaponDefinition(
        weapon_id="m109_howitzer",
        display_name="M109 Howitzer",
        category="HOWITZER",
        caliber_mm=155.0,
        muzzle_velocity_mps=600.0,
        max_range_m=20_000.0,
        rate_of_fire_rpm=4.0,
        base_accuracy_mrad=1.5,
        cep_m=150.0,
        compatible_ammo=["m795_he"],
    )
    ammo = _make_he(
        ammo_id="m795_he",
        blast_radius_m=50.0,
        fragmentation_radius_m=100.0,
        explosive_fill_kg=6.6,
    )
    return weapon, ammo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdjustFireVsFFE:
    """FIRE_FOR_EFFECT should be tighter than ADJUST_FIRE."""

    def test_ffe_improves_accuracy(self):
        eng_adj = _make_indirect_engine(seed=100, ffe_cep_improvement=0.5)
        eng_ffe = _make_indirect_engine(seed=100, ffe_cep_improvement=0.5)
        weapon, ammo = _howitzer()

        fire_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(10_000.0, 0.0, 0.0)

        res_adj = eng_adj.fire_mission(
            "bty_1", fire_pos, target_pos, weapon, ammo,
            FireMissionType.ADJUST_FIRE, round_count=20,
        )
        res_ffe = eng_ffe.fire_mission(
            "bty_1", fire_pos, target_pos, weapon, ammo,
            FireMissionType.FIRE_FOR_EFFECT, round_count=20,
        )

        # Measure mean distance from target for each set of impacts
        def mean_error(impacts):
            errors = []
            for ip in impacts:
                de = ip.position.easting - target_pos.easting
                dn = ip.position.northing - target_pos.northing
                errors.append(math.sqrt(de * de + dn * dn))
            return sum(errors) / len(errors) if errors else 0.0

        assert mean_error(res_ffe.impacts) < mean_error(res_adj.impacts)

    def test_adjust_fire_round_count(self):
        eng = _make_indirect_engine(seed=101)
        weapon, ammo = _howitzer()
        res = eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(5000, 0, 0),
            weapon, ammo, FireMissionType.ADJUST_FIRE, round_count=6,
        )
        assert res.rounds_fired == 6
        assert len(res.impacts) == 6


class TestRocketDispersion:
    """Rocket salvos should have wider dispersion via multiplier."""

    def test_rocket_wider_than_tube(self):
        eng_tube = _make_indirect_engine(seed=200, rocket_dispersion_multiplier=3.0)
        eng_rocket = _make_indirect_engine(seed=200, rocket_dispersion_multiplier=3.0)
        weapon, ammo = _howitzer()

        fire_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(15_000.0, 0.0, 0.0)

        res_tube = eng_tube.fire_mission(
            "bty_1", fire_pos, target_pos, weapon, ammo,
            FireMissionType.FIRE_FOR_EFFECT, round_count=30,
        )
        res_rocket = eng_rocket.rocket_salvo(
            "mlrs_1", fire_pos, target_pos, weapon, ammo,
            rocket_count=30,
        )

        def spread(impacts):
            es = [ip.position.easting for ip in impacts]
            ns = [ip.position.northing for ip in impacts]
            return max(es) - min(es) + max(ns) - min(ns)

        assert spread(res_rocket.impacts) > spread(res_tube.impacts)


class TestGuidedTightening:
    """Guided ammo should produce much tighter impacts."""

    def test_guided_vs_unguided(self):
        from stochastic_warfare.combat.ammunition import AmmoDefinition

        eng_unguided = _make_indirect_engine(seed=300)
        eng_guided = _make_indirect_engine(seed=300)
        weapon = _make_gun(
            category="HOWITZER", muzzle_velocity_mps=600.0, max_range_m=30_000.0,
        )
        unguided = _make_he()
        guided = AmmoDefinition(
            ammo_id="excalibur",
            display_name="M982 Excalibur",
            ammo_type="HE",
            mass_kg=48.0,
            diameter_mm=155.0,
            blast_radius_m=50.0,
            fragmentation_radius_m=80.0,
            guidance="GPS_INS",
            pk_at_reference=0.9,
        )

        fire_pos = Position(0.0, 0.0, 0.0)
        target_pos = Position(20_000.0, 0.0, 0.0)

        res_unguided = eng_unguided.fire_mission(
            "bty_1", fire_pos, target_pos, weapon, unguided,
            FireMissionType.FIRE_FOR_EFFECT, round_count=20,
        )
        res_guided = eng_guided.fire_mission(
            "bty_1", fire_pos, target_pos, weapon, guided,
            FireMissionType.FIRE_FOR_EFFECT, round_count=20,
        )

        def mean_error(impacts):
            errors = []
            for ip in impacts:
                de = ip.position.easting - target_pos.easting
                dn = ip.position.northing - target_pos.northing
                errors.append(math.sqrt(de * de + dn * dn))
            return sum(errors) / len(errors) if errors else 0.0

        assert mean_error(res_guided.impacts) < mean_error(res_unguided.impacts)


class TestCounterbatterySolution:
    """Counterbattery back-trace should estimate enemy position with error."""

    def test_counterbattery_produces_position(self):
        eng = _make_indirect_engine(seed=400, counterbattery_error_m=200.0)
        direction_rad = math.radians(45.0)  # NE
        range_m = 15_000.0

        pos = eng.compute_counterbattery_solution(direction_rad, range_m)

        # Should be roughly at (15000*sin(45), 15000*cos(45)) + error
        expected_e = range_m * math.sin(direction_rad)
        expected_n = range_m * math.cos(direction_rad)

        # Allow for 3-sigma error (600m with 200m counterbattery_error_m)
        assert abs(pos.easting - expected_e) < 1000.0
        assert abs(pos.northing - expected_n) < 1000.0

    def test_counterbattery_deterministic(self):
        eng1 = _make_indirect_engine(seed=401)
        eng2 = _make_indirect_engine(seed=401)

        pos1 = eng1.compute_counterbattery_solution(math.radians(90.0), 10_000.0)
        pos2 = eng2.compute_counterbattery_solution(math.radians(90.0), 10_000.0)

        assert pos1.easting == pytest.approx(pos2.easting)
        assert pos1.northing == pytest.approx(pos2.northing)


class TestTOTPlan:
    """Time-on-target plan should compute fire times for simultaneous impact."""

    def test_tot_plan_basic(self):
        eng = _make_indirect_engine(seed=500)
        weapon, ammo = _howitzer()

        target = Position(10_000.0, 0.0, 0.0)
        batteries = {
            "bty_1": Position(0.0, 0.0, 0.0),
            "bty_2": Position(-5_000.0, 0.0, 0.0),
        }

        plan = eng.compute_tot_plan(target, batteries, weapon, ammo, 120.0)
        assert len(plan.batteries) == 2
        assert "bty_1" in plan.fire_times
        assert "bty_2" in plan.fire_times
        # Fire times should be less than desired impact time
        for bid in plan.batteries:
            assert plan.fire_times[bid] < 120.0


class TestSuppression:
    """HE fire missions with >= 3 rounds should achieve suppression."""

    def test_suppression_achieved(self):
        eng = _make_indirect_engine(seed=600)
        weapon, ammo = _howitzer()

        res = eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(5000, 0, 0),
            weapon, ammo, FireMissionType.IMMEDIATE_SUPPRESSION, round_count=6,
        )
        assert res.suppression_achieved is True

    def test_too_few_rounds_no_suppression(self):
        eng = _make_indirect_engine(seed=601)
        weapon, ammo = _howitzer()

        res = eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(5000, 0, 0),
            weapon, ammo, FireMissionType.ADJUST_FIRE, round_count=2,
        )
        assert res.suppression_achieved is False


class TestStateRoundtrip:
    """get_state / set_state should preserve PRNG state."""

    def test_state_roundtrip(self):
        eng = _make_indirect_engine(seed=700)
        weapon, ammo = _howitzer()

        # Advance RNG
        eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(8000, 0, 0),
            weapon, ammo, FireMissionType.ADJUST_FIRE, round_count=4,
        )
        state = eng.get_state()

        # Continue
        res_a = eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(8000, 0, 0),
            weapon, ammo, FireMissionType.FIRE_FOR_EFFECT, round_count=6,
        )

        # Restore and replay
        eng.set_state(state)
        res_b = eng.fire_mission(
            "bty_1", Position(0, 0, 0), Position(8000, 0, 0),
            weapon, ammo, FireMissionType.FIRE_FOR_EFFECT, round_count=6,
        )

        # Impact positions should be identical
        for ip_a, ip_b in zip(res_a.impacts, res_b.impacts):
            assert ip_a.position.easting == pytest.approx(ip_b.position.easting)
            assert ip_a.position.northing == pytest.approx(ip_b.position.northing)
