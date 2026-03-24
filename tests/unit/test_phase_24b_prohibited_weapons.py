"""Phase 24b tests: prohibited weapons, incendiary/UXO effects, treaty compliance.

Tests cover:
- AmmoDefinition extension (new AmmoType values, treaty fields)
- Compliance check (engagement.check_prohibited_compliance)
- Incendiary damage engine (fire zones, expansion, burnout)
- UXO engine (field creation, encounter probability)
- ROE treaty compliance and political modulation
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    AmmoType,
)
from stochastic_warfare.combat.damage import (
    IncendiaryConfig,
    IncendiaryDamageEngine,
    UXOEngine,
)
from stochastic_warfare.combat.engagement import (
    check_prohibited_compliance,
)
from stochastic_warfare.c2.roe import (
    apply_political_roe_modulation,
    check_treaty_compliance,
)
from stochastic_warfare.core.types import Position

# Import shared fixtures
from tests.conftest import DEFAULT_SEED, make_rng

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "ammunition"


def _make_ammo(**overrides) -> AmmoDefinition:
    """Build an AmmoDefinition with sensible defaults, overridable."""
    defaults = dict(
        ammo_id="test_ammo",
        display_name="Test Ammo",
        ammo_type="HE",
        mass_kg=10.0,
        diameter_mm=155.0,
    )
    defaults.update(overrides)
    return AmmoDefinition(**defaults)


def _make_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    return make_rng(seed)


# ===========================================================================
# 1. AmmoDefinition extension (~10 tests)
# ===========================================================================


class TestAmmoTypeExtension:
    """New AmmoType enum values and AmmoDefinition treaty fields."""

    def test_cluster_type_exists(self):
        assert AmmoType.CLUSTER == 10

    def test_incendiary_weapon_type_exists(self):
        assert AmmoType.INCENDIARY_WEAPON == 11

    def test_anti_personnel_mine_type_exists(self):
        assert AmmoType.ANTI_PERSONNEL_MINE == 12

    def test_expanding_type_exists(self):
        assert AmmoType.EXPANDING == 13

    def test_default_treaty_fields(self):
        """Existing ammo without new fields preserves defaults."""
        ammo = _make_ammo()
        assert ammo.prohibited_under_treaties == []
        assert ammo.compliance_check is False
        assert ammo.uxo_rate == 0.0

    def test_treaty_fields_set(self):
        ammo = _make_ammo(
            prohibited_under_treaties=["CCM"],
            compliance_check=True,
            uxo_rate=0.05,
        )
        assert ammo.prohibited_under_treaties == ["CCM"]
        assert ammo.compliance_check is True
        assert ammo.uxo_rate == 0.05

    def test_parsed_ammo_type_cluster(self):
        ammo = _make_ammo(ammo_type="CLUSTER")
        assert ammo.parsed_ammo_type() == AmmoType.CLUSTER

    def test_parsed_ammo_type_incendiary(self):
        ammo = _make_ammo(ammo_type="INCENDIARY_WEAPON")
        assert ammo.parsed_ammo_type() == AmmoType.INCENDIARY_WEAPON

    def test_parsed_ammo_type_mine(self):
        ammo = _make_ammo(ammo_type="ANTI_PERSONNEL_MINE")
        assert ammo.parsed_ammo_type() == AmmoType.ANTI_PERSONNEL_MINE

    def test_parsed_ammo_type_expanding(self):
        ammo = _make_ammo(ammo_type="EXPANDING")
        assert ammo.parsed_ammo_type() == AmmoType.EXPANDING

    def test_yaml_loading_rockeye(self):
        """Load a prohibited ammo YAML and verify treaty fields."""
        loader = AmmoLoader(_DATA_DIR)
        path = _DATA_DIR / "prohibited" / "mk20_rockeye_cluster.yaml"
        defn = loader.load_definition(path)
        assert defn.ammo_id == "mk20_rockeye"
        assert defn.parsed_ammo_type() == AmmoType.CLUSTER
        assert "CCM" in defn.prohibited_under_treaties
        assert defn.compliance_check is True
        assert defn.uxo_rate == pytest.approx(0.05)
        assert defn.submunition_count == 247

    def test_yaml_loading_thermobaric_no_prohibition(self):
        """Thermobaric has no treaty restrictions."""
        loader = AmmoLoader(_DATA_DIR)
        path = _DATA_DIR / "prohibited" / "fae_thermobaric.yaml"
        defn = loader.load_definition(path)
        assert defn.ammo_id == "fae_thermobaric"
        assert defn.prohibited_under_treaties == []
        assert defn.compliance_check is False


# ===========================================================================
# 2. Compliance check (~15 tests)
# ===========================================================================


class TestComplianceCheck:
    """check_prohibited_compliance in engagement.py."""

    def test_authorized_when_no_compliance_check(self):
        ammo = _make_ammo(compliance_check=False)
        ok, reason = check_prohibited_compliance(ammo, None)
        assert ok is True
        assert reason == ""

    def test_authorized_when_no_escalation_engine(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM"],
        )
        ok, reason = check_prohibited_compliance(ammo, None)
        assert ok is True
        assert reason == "no_escalation_system"

    def test_authorized_at_correct_level_ccm(self):
        """CCM requires level 4; engine at 4 → authorized."""
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM"],
        )
        engine = SimpleNamespace(current_level=4)
        ok, reason = check_prohibited_compliance(ammo, engine)
        assert ok is True

    def test_rejected_below_required_level_ccm(self):
        """CCM requires level 4; engine at 3 → rejected."""
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM"],
        )
        engine = SimpleNamespace(current_level=3)
        ok, reason = check_prohibited_compliance(ammo, engine)
        assert ok is False
        assert "4" in reason
        assert "CCM" in reason

    def test_cwc_requires_level_5(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CWC"],
        )
        engine = SimpleNamespace(current_level=4)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is False

        engine5 = SimpleNamespace(current_level=5)
        ok5, _ = check_prohibited_compliance(ammo, engine5)
        assert ok5 is True

    def test_bwc_requires_level_6(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["BWC"],
        )
        engine = SimpleNamespace(current_level=5)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is False

        engine6 = SimpleNamespace(current_level=6)
        ok6, _ = check_prohibited_compliance(ammo, engine6)
        assert ok6 is True

    def test_ottawa_requires_level_4(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["Ottawa"],
        )
        engine = SimpleNamespace(current_level=3)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is False

        engine4 = SimpleNamespace(current_level=4)
        ok4, _ = check_prohibited_compliance(ammo, engine4)
        assert ok4 is True

    def test_protocol_iii_requires_level_3(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["Protocol III CCW"],
        )
        engine = SimpleNamespace(current_level=2)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is False

        engine3 = SimpleNamespace(current_level=3)
        ok3, _ = check_prohibited_compliance(ammo, engine3)
        assert ok3 is True

    def test_hague_requires_level_3(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["Hague"],
        )
        engine = SimpleNamespace(current_level=2)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is False

        engine3 = SimpleNamespace(current_level=3)
        ok3, _ = check_prohibited_compliance(ammo, engine3)
        assert ok3 is True

    def test_multiple_treaties_most_restrictive_wins(self):
        """If ammo is under CCM (4) and CWC (5), need level 5."""
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM", "CWC"],
        )
        engine4 = SimpleNamespace(current_level=4)
        ok4, _ = check_prohibited_compliance(ammo, engine4)
        assert ok4 is False  # CWC needs 5

        engine5 = SimpleNamespace(current_level=5)
        ok5, _ = check_prohibited_compliance(ammo, engine5)
        assert ok5 is True

    def test_high_level_authorizes_all(self):
        """Level 10 authorizes anything."""
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["BWC"],
        )
        engine = SimpleNamespace(current_level=10)
        ok, _ = check_prohibited_compliance(ammo, engine)
        assert ok is True

    def test_level_zero_rejects_all_compliance_checked(self):
        for treaty in ["CWC", "BWC", "CCM", "Ottawa", "Protocol III CCW", "Hague"]:
            ammo = _make_ammo(
                compliance_check=True,
                prohibited_under_treaties=[treaty],
            )
            engine = SimpleNamespace(current_level=0)
            ok, _ = check_prohibited_compliance(ammo, engine)
            assert ok is False, f"Level 0 should reject {treaty}"


# ===========================================================================
# 3. Incendiary damage engine (~15 tests)
# ===========================================================================


class TestIncendiaryDamageEngine:
    """IncendiaryDamageEngine fire zone lifecycle."""

    def test_fire_zone_creation(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        pos = Position(100.0, 200.0, 0.0)
        zone = engine.create_fire_zone(
            position=pos,
            radius_m=30.0,
            fuel_load=0.8,
            wind_speed_mps=5.0,
            wind_dir_rad=0.0,  # east
            duration_s=120.0,
            timestamp=0.0,
        )
        assert zone.zone_id == "fire_1"
        assert zone.center == pos
        assert zone.radius_m == 30.0
        assert zone.current_radius_m == 30.0
        assert zone.fuel_load == 0.8
        assert zone.duration_s == 120.0

    def test_fire_zone_wind_offset(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        zone = engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=20.0,
            fuel_load=1.0,
            wind_speed_mps=10.0,
            wind_dir_rad=math.pi / 2,  # north
            duration_s=60.0,
            timestamp=0.0,
        )
        # cos(pi/2) ~= 0, sin(pi/2) ~= 1
        assert zone.wind_offset_mps[0] == pytest.approx(0.0, abs=1e-9)
        assert zone.wind_offset_mps[1] == pytest.approx(10.0, abs=1e-9)

    def test_wind_driven_expansion(self):
        rng = _make_rng()
        config = IncendiaryConfig(expansion_factor=0.1, max_expansion_ratio=5.0)
        engine = IncendiaryDamageEngine(rng, config)
        zone = engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            fuel_load=1.0,
            wind_speed_mps=10.0,
            wind_dir_rad=0.0,
            duration_s=1000.0,
            timestamp=0.0,
        )
        initial_radius = zone.current_radius_m
        engine.update_fire_zones(10.0)  # 10s
        # expansion = 10.0 * 0.1 * 1.0 * 10.0 = 10.0
        expected = initial_radius + 10.0
        assert zone.current_radius_m == pytest.approx(expected)

    def test_expansion_capped_at_max_ratio(self):
        rng = _make_rng()
        config = IncendiaryConfig(expansion_factor=0.5, max_expansion_ratio=2.0)
        engine = IncendiaryDamageEngine(rng, config)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            fuel_load=1.0,
            wind_speed_mps=20.0,
            wind_dir_rad=0.0,
            duration_s=1000.0,
            timestamp=0.0,
        )
        # Huge expansion should be capped at 10 * 2.0 = 20.0
        active = engine.update_fire_zones(100.0)
        assert len(active) == 1
        assert active[0].current_radius_m == pytest.approx(20.0)

    def test_unit_damage_inside_fire_zone(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=50.0,
            fuel_load=0.5,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=100.0,
            timestamp=0.0,
        )
        damage_map = engine.units_in_fire({"u1": Position(10.0, 10.0)})
        assert "u1" in damage_map
        assert damage_map["u1"] == pytest.approx(0.02)

    def test_no_damage_outside_fire_zone(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            fuel_load=0.5,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=100.0,
            timestamp=0.0,
        )
        damage_map = engine.units_in_fire({"u1": Position(100.0, 100.0)})
        assert "u1" not in damage_map

    def test_burnout_creates_burned_zone(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        engine.create_fire_zone(
            position=Position(50.0, 50.0),
            radius_m=20.0,
            fuel_load=0.5,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=30.0,
            timestamp=0.0,
        )
        # Advance past duration
        active = engine.update_fire_zones(31.0)
        assert len(active) == 0
        burned = engine.get_burned_zones()
        assert len(burned) == 1
        assert burned[0].zone_id == "fire_1"
        assert burned[0].concealment_reduction == 0.5

    def test_burned_zone_preserves_radius(self):
        rng = _make_rng()
        config = IncendiaryConfig(expansion_factor=0.1, max_expansion_ratio=3.0)
        engine = IncendiaryDamageEngine(rng, config)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            fuel_load=1.0,
            wind_speed_mps=5.0,
            wind_dir_rad=0.0,
            duration_s=20.0,
            timestamp=0.0,
        )
        # Advance 10s to expand, then let it burn out
        engine.update_fire_zones(10.0)
        engine.update_fire_zones(11.0)  # goes past duration
        burned = engine.get_burned_zones()
        assert len(burned) == 1
        # Radius should be expanded, not original
        assert burned[0].radius_m > 10.0

    def test_multiple_fire_zones_independent(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            fuel_load=0.5,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=50.0,
            timestamp=0.0,
        )
        engine.create_fire_zone(
            position=Position(200.0, 200.0),
            radius_m=15.0,
            fuel_load=0.7,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=100.0,
            timestamp=0.0,
        )
        active = engine.update_fire_zones(60.0)
        # First zone should burn out, second stays
        assert len(active) == 1
        assert active[0].zone_id == "fire_2"

    def test_state_roundtrip(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        engine.create_fire_zone(
            position=Position(10.0, 20.0),
            radius_m=15.0,
            fuel_load=0.6,
            wind_speed_mps=3.0,
            wind_dir_rad=1.0,
            duration_s=60.0,
            timestamp=5.0,
        )
        engine.update_fire_zones(10.0)
        # Create a burned zone by burning out a quick one
        engine.create_fire_zone(
            position=Position(100.0, 100.0),
            radius_m=5.0,
            fuel_load=0.3,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=1.0,
            timestamp=0.0,
        )
        engine.update_fire_zones(2.0)

        state = engine.get_state()
        engine2 = IncendiaryDamageEngine(_make_rng())
        engine2.set_state(state)
        state2 = engine2.get_state()

        assert state["zone_counter"] == state2["zone_counter"]
        assert len(state["active_zones"]) == len(state2["active_zones"])
        assert len(state["burned_zones"]) == len(state2["burned_zones"])

    def test_no_expansion_without_wind(self):
        """Zero wind → zero expansion regardless of fuel load."""
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        zone = engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=20.0,
            fuel_load=1.0,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=1000.0,
            timestamp=0.0,
        )
        engine.update_fire_zones(100.0)
        assert zone.current_radius_m == pytest.approx(20.0)

    def test_custom_config(self):
        rng = _make_rng()
        config = IncendiaryConfig(burn_damage_per_second=0.05)
        engine = IncendiaryDamageEngine(rng, config)
        engine.create_fire_zone(
            position=Position(0.0, 0.0),
            radius_m=50.0,
            fuel_load=0.5,
            wind_speed_mps=0.0,
            wind_dir_rad=0.0,
            duration_s=100.0,
            timestamp=0.0,
        )
        damage_map = engine.units_in_fire({"u1": Position(5.0, 5.0)})
        assert damage_map["u1"] == pytest.approx(0.05)

    def test_zone_ids_increment(self):
        rng = _make_rng()
        engine = IncendiaryDamageEngine(rng)
        z1 = engine.create_fire_zone(
            Position(0, 0), 10, 0.5, 0, 0, 60, 0,
        )
        z2 = engine.create_fire_zone(
            Position(100, 100), 10, 0.5, 0, 0, 60, 0,
        )
        assert z1.zone_id == "fire_1"
        assert z2.zone_id == "fire_2"


# ===========================================================================
# 4. UXO engine (~10 tests)
# ===========================================================================


class TestUXOEngine:
    """UXOEngine field creation and encounter checks."""

    def test_field_creation_density(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        field = engine.create_uxo_field(
            position=Position(0.0, 0.0),
            radius_m=50.0,
            submunition_count=200,
            uxo_rate=0.05,
            timestamp=0.0,
        )
        assert field.field_id == "uxo_1"
        expected_density = (200 * 0.05) / (math.pi * 50.0 * 50.0)
        assert field.density == pytest.approx(expected_density)

    def test_encounter_within_field(self):
        """With high density, encounters should happen often."""
        # Create a dense field: density ~= 0.127 per m²
        rng = _make_rng(seed=99)
        engine = UXOEngine(rng)
        engine.create_uxo_field(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            submunition_count=10000,
            uxo_rate=0.4,
            timestamp=0.0,
        )
        # Run many checks from within the field
        encounters = sum(
            engine.check_uxo_encounter(Position(1.0, 1.0))
            for _ in range(100)
        )
        # Density = 10000*0.4/(pi*100) ≈ 12.7 — clamped effectively to ~1
        # Should encounter nearly every time
        assert encounters > 50

    def test_no_encounter_outside_field(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        engine.create_uxo_field(
            position=Position(0.0, 0.0),
            radius_m=10.0,
            submunition_count=100,
            uxo_rate=0.05,
            timestamp=0.0,
        )
        # Check from far away
        encounters = sum(
            engine.check_uxo_encounter(Position(1000.0, 1000.0))
            for _ in range(100)
        )
        assert encounters == 0

    def test_multiple_fields_tracked(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        f1 = engine.create_uxo_field(
            Position(0.0, 0.0), 20.0, 100, 0.05, 0.0,
        )
        f2 = engine.create_uxo_field(
            Position(500.0, 500.0), 30.0, 200, 0.10, 10.0,
        )
        fields = engine.get_fields()
        assert len(fields) == 2
        assert fields[0].field_id == "uxo_1"
        assert fields[1].field_id == "uxo_2"

    def test_state_roundtrip(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        engine.create_uxo_field(
            Position(10.0, 20.0), 25.0, 150, 0.08, 5.0,
        )
        engine.create_uxo_field(
            Position(300.0, 400.0), 40.0, 300, 0.04, 15.0,
        )

        state = engine.get_state()
        engine2 = UXOEngine(_make_rng())
        engine2.set_state(state)
        state2 = engine2.get_state()

        assert state["field_counter"] == state2["field_counter"]
        assert len(state["fields"]) == len(state2["fields"])
        for f1, f2 in zip(state["fields"], state2["fields"]):
            assert f1["field_id"] == f2["field_id"]
            assert f1["density"] == pytest.approx(f2["density"])

    def test_zero_uxo_rate_creates_zero_density(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        field = engine.create_uxo_field(
            Position(0.0, 0.0), 50.0, 200, 0.0, 0.0,
        )
        assert field.density == 0.0
        # Should never encounter
        assert not engine.check_uxo_encounter(Position(1.0, 1.0))

    def test_encounter_with_civilian_flag(self):
        """is_civilian flag does not change probability but is accepted."""
        rng = _make_rng(seed=123)
        engine = UXOEngine(rng)
        engine.create_uxo_field(
            Position(0.0, 0.0), 10.0, 5000, 0.5, 0.0,
        )
        # Just verify it doesn't error with is_civilian=True
        result = engine.check_uxo_encounter(Position(1.0, 1.0), is_civilian=True)
        assert isinstance(result, bool)

    def test_field_at_boundary(self):
        """Position exactly at radius boundary is within the field."""
        rng = _make_rng(seed=77)
        engine = UXOEngine(rng)
        engine.create_uxo_field(
            Position(0.0, 0.0), 100.0, 50000, 0.5, 0.0,
        )
        # Exactly at radius: distance = 100.0
        pos_at_boundary = Position(100.0, 0.0)
        # Should be within field (dist <= radius)
        encounters = sum(
            engine.check_uxo_encounter(pos_at_boundary)
            for _ in range(100)
        )
        # High density → should encounter at least once
        assert encounters > 0

    def test_field_ids_increment(self):
        rng = _make_rng()
        engine = UXOEngine(rng)
        f1 = engine.create_uxo_field(Position(0, 0), 10, 100, 0.05, 0.0)
        f2 = engine.create_uxo_field(Position(50, 50), 10, 100, 0.05, 0.0)
        f3 = engine.create_uxo_field(Position(100, 100), 10, 100, 0.05, 0.0)
        assert f1.field_id == "uxo_1"
        assert f2.field_id == "uxo_2"
        assert f3.field_id == "uxo_3"


# ===========================================================================
# 5. ROE treaty compliance + political modulation (~5 tests)
# ===========================================================================


class TestROETreatyCompliance:
    """check_treaty_compliance and apply_political_roe_modulation."""

    def test_no_compliance_check_always_passes(self):
        ammo = _make_ammo(compliance_check=False)
        ok, reason = check_treaty_compliance(ammo, 0)
        assert ok is True
        assert reason == ""

    def test_ccm_rejected_at_level_3(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM"],
        )
        ok, reason = check_treaty_compliance(ammo, 3)
        assert ok is False
        assert "CCM" in reason

    def test_ccm_authorized_at_level_4(self):
        ammo = _make_ammo(
            compliance_check=True,
            prohibited_under_treaties=["CCM"],
        )
        ok, _ = check_treaty_compliance(ammo, 4)
        assert ok is True

    def test_political_tightening(self):
        result = apply_political_roe_modulation(
            current_roe_level=2,
            effects=["FORCED_ROE_TIGHTENING"],
        )
        assert result == 1  # WEAPONS_FREE → WEAPONS_TIGHT

    def test_political_loosening(self):
        result = apply_political_roe_modulation(
            current_roe_level=0,
            effects=["ROE_LOOSENING_AUTHORIZED"],
        )
        assert result == 1  # WEAPONS_HOLD → WEAPONS_TIGHT

    def test_political_clamp_upper(self):
        result = apply_political_roe_modulation(
            current_roe_level=2,
            effects=["ROE_LOOSENING_AUTHORIZED"],
        )
        assert result == 2  # Already at max

    def test_political_clamp_lower(self):
        result = apply_political_roe_modulation(
            current_roe_level=0,
            effects=["FORCED_ROE_TIGHTENING"],
        )
        assert result == 0  # Already at min

    def test_political_multiple_effects(self):
        result = apply_political_roe_modulation(
            current_roe_level=1,
            effects=["FORCED_ROE_TIGHTENING", "FORCED_ROE_TIGHTENING"],
        )
        assert result == 0  # Clamped at 0

    def test_political_opposing_effects_cancel(self):
        result = apply_political_roe_modulation(
            current_roe_level=1,
            effects=["FORCED_ROE_TIGHTENING", "ROE_LOOSENING_AUTHORIZED"],
        )
        assert result == 1  # Net zero change

    def test_political_empty_effects(self):
        result = apply_political_roe_modulation(
            current_roe_level=1,
            effects=[],
        )
        assert result == 1
