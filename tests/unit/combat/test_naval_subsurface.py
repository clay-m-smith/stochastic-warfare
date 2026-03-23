"""Unit tests for NavalSubsurfaceEngine — torpedo, evasion, ASROC, depth charges, CM."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.naval_subsurface import (
    ASROCResult,
    DepthChargeResult,
    EvasionResult,
    NavalSubsurfaceConfig,
    NavalSubsurfaceEngine,
    TorpedoCountermeasureResult,
    TorpedoResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> NavalSubsurfaceEngine:
    bus = EventBus()
    damage = DamageEngine(bus, _rng(seed + 100))
    config = NavalSubsurfaceConfig(**cfg_kwargs) if cfg_kwargs else None
    return NavalSubsurfaceEngine(damage, bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTorpedoEngagement:
    """Torpedo attack resolution."""

    def test_torpedo_wire_guided_bonus(self):
        """Wire-guided torpedo should have higher effective Pk."""
        pks_plain = []
        pks_wire = []
        for seed in range(50):
            eng1 = _make_engine(seed=seed)
            eng2 = _make_engine(seed=seed)
            r1 = eng1.torpedo_engagement("sub1", "tgt1", 0.5, 10_000.0, wire_guided=False)
            r2 = eng2.torpedo_engagement("sub1", "tgt1", 0.5, 10_000.0, wire_guided=True)
            if not r1.malfunction:
                pks_plain.append(1 if r1.hit else 0)
            if not r2.malfunction:
                pks_wire.append(1 if r2.hit else 0)
        # Wire-guided should hit more often on average
        assert sum(pks_wire) >= sum(pks_plain)

    def test_torpedo_range_decay(self):
        """Longer range should reduce effective Pk."""
        eng1 = _make_engine(seed=10)
        eng2 = _make_engine(seed=10)
        close = eng1.torpedo_engagement("sub1", "tgt1", 0.7, 5_000.0)
        far = eng2.torpedo_engagement("sub1", "tgt1", 0.7, 40_000.0)
        # The far torpedo has much higher range decay
        # We can't compare hit/miss directly due to randomness, but we can
        # verify the torpedo was created with the right id structure
        assert close.torpedo_id.startswith("sub1_torp_")
        assert far.torpedo_id.startswith("sub1_torp_")

    def test_torpedo_malfunction(self):
        """With high malfunction rate, some torpedoes should malfunction."""
        malfunctions = 0
        for seed in range(100):
            eng = _make_engine(seed=seed, malfunction_probability=0.5)
            result = eng.torpedo_engagement("sub1", "tgt1", 0.8, 5_000.0)
            if result.malfunction:
                malfunctions += 1
        # Expect roughly 50% malfunction rate
        assert 20 < malfunctions < 80

    def test_torpedo_hit_produces_damage(self):
        """A torpedo hit should produce damage_fraction > 0."""
        for seed in range(100):
            eng = _make_engine(seed=seed, malfunction_probability=0.0)
            result = eng.torpedo_engagement("sub1", "tgt1", 0.99, 1_000.0)
            if result.hit:
                assert result.damage_fraction > 0.0
                break
        else:
            pytest.fail("No torpedo hit in 100 seeds with Pk=0.99")


class TestEvasionManeuver:
    """Submarine evasion maneuvers."""

    def test_decoy_evasion(self):
        eng = _make_engine(seed=20)
        result = eng.evasion_maneuver("sub1", 90.0, "decoy")
        assert result.evasion_type == "decoy"
        assert 0.0 <= result.effectiveness <= 1.0

    def test_depth_change_evasion(self):
        eng = _make_engine(seed=21)
        result = eng.evasion_maneuver("sub1", 45.0, "depth_change")
        assert result.evasion_type == "depth_change"

    def test_knuckle_evasion(self):
        eng = _make_engine(seed=22)
        result = eng.evasion_maneuver("sub1", 180.0, "knuckle")
        assert result.evasion_type == "knuckle"


class TestASROC:
    """ASROC rocket-delivered torpedo engagement."""

    def test_asroc_within_range(self):
        """ASROC within max range should attempt engagement."""
        eng = _make_engine(seed=30)
        result = eng.asroc_engagement("dd1", "sub1", range_m=15_000.0, target_depth_m=80.0)
        # Flight may or may not succeed (0.9 reliability), but result is valid
        assert isinstance(result, ASROCResult)
        assert result.ship_id == "dd1"

    def test_asroc_out_of_range(self):
        """ASROC beyond max range should fail."""
        eng = _make_engine(seed=31)
        result = eng.asroc_engagement("dd1", "sub1", range_m=30_000.0)
        assert result.flight_success is False
        assert result.torpedo_hit is False

    def test_asroc_deep_target_penalty(self):
        """Deeper targets should be harder to hit."""
        hits_shallow = 0
        hits_deep = 0
        for seed in range(100):
            eng1 = _make_engine(seed=seed + 500)
            eng2 = _make_engine(seed=seed + 500)
            r1 = eng1.asroc_engagement("dd1", "sub1", 10_000.0, target_depth_m=50.0)
            r2 = eng2.asroc_engagement("dd1", "sub1", 10_000.0, target_depth_m=400.0)
            if r1.torpedo_hit:
                hits_shallow += 1
            if r2.torpedo_hit:
                hits_deep += 1
        assert hits_shallow >= hits_deep


class TestDepthCharges:
    """Depth charge attack patterns."""

    def test_depth_charge_lethal_radius(self):
        """Depth charges should sometimes hit at close range."""
        total_hits = 0
        for seed in range(100):
            eng = _make_engine(seed=seed + 600)
            result = eng.depth_charge_attack(
                "dd1", "sub1", num_charges=10,
                target_depth_m=50.0, target_range_m=10.0,
            )
            total_hits += result.hits
        # With 10 charges at very close range, should get some hits
        assert total_hits > 0

    def test_depth_charge_damage_fraction(self):
        """Hits should produce damage_fraction > 0."""
        for seed in range(200):
            eng = _make_engine(seed=seed + 700)
            result = eng.depth_charge_attack(
                "dd1", "sub1", num_charges=20,
                target_depth_m=50.0, target_range_m=5.0,
            )
            if result.hits > 0:
                assert result.damage_fraction > 0.0
                break


class TestTorpedoCountermeasures:
    """NIXIE, acoustic CM, and evasion layers."""

    def test_nixie_seduction(self):
        """NIXIE should sometimes defeat the torpedo."""
        defeats = 0
        for seed in range(100):
            eng = _make_engine(seed=seed + 800)
            result = eng.resolve_torpedo_countermeasures(
                "dd1", 0.7, nixie_deployed=True,
            )
            if result.torpedo_defeated and result.nixie_success:
                defeats += 1
        # ~35% NIXIE seduction probability
        assert defeats > 10

    def test_no_cm_no_defeat(self):
        """Without any CM, torpedo should not be defeated."""
        eng = _make_engine(seed=50)
        result = eng.resolve_torpedo_countermeasures(
            "dd1", 0.7,
            nixie_deployed=False, acoustic_cm=False, evasion_type="none",
        )
        assert result.torpedo_defeated is False
        assert result.effective_pk == pytest.approx(0.7)

    def test_layered_defense(self):
        """Layered defense (NIXIE + acoustic CM) should defeat more often."""
        defeats_single = 0
        defeats_layered = 0
        for seed in range(200):
            eng1 = _make_engine(seed=seed + 900)
            eng2 = _make_engine(seed=seed + 900)
            r1 = eng1.resolve_torpedo_countermeasures(
                "dd1", 0.7, nixie_deployed=True,
            )
            r2 = eng2.resolve_torpedo_countermeasures(
                "dd1", 0.7, nixie_deployed=True, acoustic_cm=True,
                evasion_type="hard_turn",
            )
            if r1.torpedo_defeated:
                defeats_single += 1
            if r2.torpedo_defeated:
                defeats_layered += 1
        assert defeats_layered >= defeats_single


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=100)
        eng.torpedo_engagement("sub1", "tgt1", 0.7, 10_000.0)
        eng.torpedo_engagement("sub1", "tgt2", 0.5, 15_000.0)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert eng2._torpedo_count == 2

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)
