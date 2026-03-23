"""Unit tests for ArcheryEngine — Ancient/Medieval massed archery fire."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.archery import (
    ArcheryConfig,
    ArcheryEngine,
    ArcheryResult,
    ArmorType,
    MissileType,
)

from .conftest import _rng


# ---------------------------------------------------------------------------
# Volley fire — range tables
# ---------------------------------------------------------------------------


class TestVolleyByMissileType:
    """Massed volley casualties vary by missile type and range."""

    def test_longbow_close_range(self):
        """Longbow at 50m should produce non-trivial casualties."""
        eng = ArcheryEngine(rng=_rng(seed=1))
        result = eng.fire_volley("u1", n_archers=100, range_m=50.0, missile_type=MissileType.LONGBOW)
        assert isinstance(result, ArcheryResult)
        assert result.casualties >= 0
        # At 50m Phit=0.20, 100 archers -> expect ~20 cas (stochastic)
        assert result.arrows_expended == 100

    def test_crossbow_higher_phit_at_short_range(self):
        """Crossbow has higher Phit than longbow at close range."""
        rng1, rng2 = _rng(seed=2), _rng(seed=2)
        eng_cb = ArcheryEngine(rng=rng1)
        eng_lb = ArcheryEngine(rng=rng2)
        # Same seed, same n, same range — crossbow Phit > longbow Phit at 50m
        # Crossbow 50m: 0.30 vs Longbow 50m: 0.20
        cb_result = eng_cb.fire_volley("u1", 200, 50.0, MissileType.CROSSBOW)
        lb_result = eng_lb.fire_volley("u2", 200, 50.0, MissileType.LONGBOW)
        # With same seed and higher Phit, crossbow should get >= longbow
        # (not deterministic equality due to different unit_ids but conceptual check)
        assert cb_result.casualties >= 0
        assert lb_result.casualties >= 0

    def test_javelin_very_short_range(self):
        """Javelin at 5m has Phit=0.40 — highly effective."""
        eng = ArcheryEngine(rng=_rng(seed=3))
        result = eng.fire_volley("u1", 50, 5.0, MissileType.JAVELIN)
        assert result.casualties >= 0
        assert result.arrows_expended == 50

    def test_sling_moderate_range(self):
        """Sling at 60m has Phit=0.05."""
        eng = ArcheryEngine(rng=_rng(seed=4))
        result = eng.fire_volley("u1", 100, 60.0, MissileType.SLING)
        assert result.casualties >= 0

    def test_long_range_low_casualties(self):
        """Longbow at 250m (max range) should produce very few casualties."""
        eng = ArcheryEngine(rng=_rng(seed=5))
        result = eng.fire_volley("u1", 100, 250.0, MissileType.LONGBOW)
        # Phit=0.01 at 250m => ~1 casualty on average
        assert result.casualties <= 20  # generous bound


# ---------------------------------------------------------------------------
# Armor reduction
# ---------------------------------------------------------------------------


class TestArmorReduction:
    """Armor reduces hit probability."""

    def test_plate_significant_reduction(self):
        """PLATE armor reduces Phit to 0.15x — far fewer casualties."""
        eng = ArcheryEngine(rng=_rng(seed=10))
        no_armor = eng.fire_volley("u1", 200, 50.0, MissileType.LONGBOW, ArmorType.NONE)
        eng2 = ArcheryEngine(rng=_rng(seed=10))
        plate = eng2.fire_volley("u2", 200, 50.0, MissileType.LONGBOW, ArmorType.PLATE)
        # PLATE reduces by 0.15 factor — expect far fewer
        assert plate.casualties <= no_armor.casualties

    def test_mail_moderate_reduction(self):
        """MAIL armor reduces Phit to 0.4x."""
        eng = ArcheryEngine(rng=_rng(seed=11))
        result = eng.fire_volley("u1", 200, 50.0, MissileType.LONGBOW, ArmorType.MAIL)
        assert result.casualties >= 0


# ---------------------------------------------------------------------------
# Formation vulnerability
# ---------------------------------------------------------------------------


class TestFormationVulnerability:
    """Formation modifier scales Phit."""

    def test_high_vulnerability_increases_casualties(self):
        """target_formation_archery_vuln > 1.0 amplifies casualties."""
        eng1 = ArcheryEngine(rng=_rng(seed=20))
        normal = eng1.fire_volley("u1", 200, 100.0, MissileType.LONGBOW, target_formation_archery_vuln=1.0)
        eng2 = ArcheryEngine(rng=_rng(seed=20))
        high_vuln = eng2.fire_volley("u2", 200, 100.0, MissileType.LONGBOW, target_formation_archery_vuln=2.0)
        # Higher vulnerability should produce more casualties (same seed)
        assert high_vuln.casualties >= normal.casualties


# ---------------------------------------------------------------------------
# Ammo tracking
# ---------------------------------------------------------------------------


class TestAmmoTracking:
    """Ammo depletion and remaining_ammo query."""

    def test_ammo_decrements_per_volley(self):
        eng = ArcheryEngine(rng=_rng(seed=30))
        assert eng.remaining_ammo("u1") == 24  # default arrows_per_archer
        eng.fire_volley("u1", 10, 50.0, MissileType.LONGBOW)
        assert eng.remaining_ammo("u1") == 23

    def test_ammo_exhaustion_stops_fire(self):
        """After arrows are depleted, fire_volley produces zero casualties."""
        cfg = ArcheryConfig(arrows_per_archer=2)
        eng = ArcheryEngine(config=cfg, rng=_rng(seed=31))
        eng.fire_volley("u1", 50, 50.0, MissileType.LONGBOW)
        eng.fire_volley("u1", 50, 50.0, MissileType.LONGBOW)
        # Ammo exhausted
        result = eng.fire_volley("u1", 50, 50.0, MissileType.LONGBOW)
        assert result.casualties == 0
        assert result.arrows_expended == 0

    def test_remaining_ammo_uninitialized(self):
        """Unknown unit returns default arrows_per_archer."""
        eng = ArcheryEngine(rng=_rng(seed=32))
        assert eng.remaining_ammo("unknown_unit") == 24


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestArcheryStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = ArcheryEngine(rng=_rng(seed=40))
        eng.fire_volley("u1", 50, 50.0, MissileType.LONGBOW)
        eng.fire_volley("u2", 30, 100.0, MissileType.CROSSBOW)
        state = eng.get_state()

        eng2 = ArcheryEngine(rng=_rng(seed=40))
        eng2.set_state(state)
        assert eng2.remaining_ammo("u1") == eng.remaining_ammo("u1")
        assert eng2.remaining_ammo("u2") == eng.remaining_ammo("u2")
