"""Phase 23c tests — Ancient & Medieval validation scenarios.

Tests for:
- Cannae scenario loading, era validation, terrain
- Agincourt scenario loading, longbow dominance
- Hastings scenario loading, combined arms
- CBRN correctly disabled for Ancient/Medieval era
- Engine extension integration (archery, melee, formations)
- Deterministic replay
- Backward compat (modern/ww2/ww1/napoleonic still load)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from tests.conftest import make_rng

DATA_DIR = Path("data")
AM_DIR = DATA_DIR / "eras" / "ancient_medieval"


# ---------------------------------------------------------------------------
# Scenario loading helpers
# ---------------------------------------------------------------------------


def _load_scenario_yaml(name: str) -> dict:
    path = AM_DIR / "scenarios" / name / "scenario.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_scenario_config(name: str):
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
    raw = _load_scenario_yaml(name)
    return CampaignScenarioConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Cannae — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestCannaeScenarioLoading:
    """Battle of Cannae scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("cannae")
        assert "Cannae" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("cannae")
        assert cfg.era == "ancient_medieval"

    def test_terrain_type(self) -> None:
        cfg = _load_scenario_config("cannae")
        assert cfg.terrain.terrain_type == "open_field"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("cannae")
        assert len(cfg.sides) == 2
        names = {s.side for s in cfg.sides}
        assert names == {"carthaginian", "roman"}

    def test_roman_has_legionaries(self) -> None:
        cfg = _load_scenario_config("cannae")
        roman = [s for s in cfg.sides if s.side == "roman"][0]
        legions = [u for u in roman.units if u.get("unit_type") == "roman_legionary_cohort"]
        assert len(legions) >= 1
        total = sum(u.get("count", 1) for u in legions)
        assert total >= 4

    def test_carthaginian_has_cavalry(self) -> None:
        cfg = _load_scenario_config("cannae")
        carth = [s for s in cfg.sides if s.side == "carthaginian"][0]
        cav = [u for u in carth.units if u.get("unit_type") == "mongol_horse_archer"]
        assert len(cav) >= 1
        total = sum(u.get("count", 1) for u in cav)
        assert total >= 2

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("cannae")
        assert len(raw["documented_outcomes"]) >= 2

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config("cannae")
        assert len(cfg.objectives) >= 2


# ---------------------------------------------------------------------------
# Agincourt — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestAgincourtScenarioLoading:
    """Battle of Agincourt scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("agincourt")
        assert "Agincourt" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("agincourt")
        assert cfg.era == "ancient_medieval"

    def test_terrain_type(self) -> None:
        cfg = _load_scenario_config("agincourt")
        assert cfg.terrain.terrain_type == "open_field"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("agincourt")
        names = {s.side for s in cfg.sides}
        assert names == {"english", "french"}

    def test_english_has_longbowmen(self) -> None:
        cfg = _load_scenario_config("agincourt")
        english = [s for s in cfg.sides if s.side == "english"][0]
        archers = [u for u in english.units if u.get("unit_type") == "english_longbowman"]
        assert len(archers) >= 1
        total = sum(u.get("count", 1) for u in archers)
        assert total >= 4

    def test_french_has_knights(self) -> None:
        cfg = _load_scenario_config("agincourt")
        french = [s for s in cfg.sides if s.side == "french"][0]
        knights = [u for u in french.units if u.get("unit_type") == "norman_knight_conroi"]
        assert len(knights) >= 1
        total = sum(u.get("count", 1) for u in knights)
        assert total >= 3

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("agincourt")
        outcomes = raw["documented_outcomes"]
        assert len(outcomes) >= 2
        names = {o["name"] for o in outcomes}
        assert "french_casualty_fraction" in names
        assert "english_casualty_fraction" in names


# ---------------------------------------------------------------------------
# Hastings — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestHastingsScenarioLoading:
    """Battle of Hastings scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("hastings")
        assert "Hastings" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("hastings")
        assert cfg.era == "ancient_medieval"

    def test_terrain_type_hilly(self) -> None:
        """Hastings uses hilly_defense (Senlac Hill)."""
        cfg = _load_scenario_config("hastings")
        assert cfg.terrain.terrain_type == "hilly_defense"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("hastings")
        names = {s.side for s in cfg.sides}
        assert names == {"saxon", "norman"}

    def test_saxon_shield_wall(self) -> None:
        cfg = _load_scenario_config("hastings")
        saxon = [s for s in cfg.sides if s.side == "saxon"][0]
        huscarls = [u for u in saxon.units if u.get("unit_type") == "viking_huscarl"]
        assert len(huscarls) >= 1
        total = sum(u.get("count", 1) for u in huscarls)
        assert total >= 3

    def test_norman_combined_arms(self) -> None:
        cfg = _load_scenario_config("hastings")
        norman = [s for s in cfg.sides if s.side == "norman"][0]
        unit_types = [u.get("unit_type") for u in norman.units]
        assert "norman_knight_conroi" in unit_types
        assert "english_longbowman" in unit_types or "viking_huscarl" in unit_types

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("hastings")
        assert len(raw["documented_outcomes"]) >= 2


# ---------------------------------------------------------------------------
# CBRN disabled for Ancient/Medieval era
# ---------------------------------------------------------------------------


class TestCBRNDisabledAncient:
    """CBRN is correctly disabled for Ancient/Medieval era."""

    def test_cbrn_in_disabled_modules(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ancient_medieval")
        assert "cbrn" in cfg.disabled_modules

    def test_all_modern_modules_disabled(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ancient_medieval")
        expected = {"ew", "space", "cbrn", "gps", "thermal_sights", "data_links", "pgm"}
        assert cfg.disabled_modules == expected


# ---------------------------------------------------------------------------
# Engine extension integration (Ancient/Medieval combat mechanics)
# ---------------------------------------------------------------------------


class TestAncientCombatMechanics:
    """Ancient/Medieval combat mechanics integration."""

    def test_longbow_volley_casualties(self) -> None:
        """100 longbowmen at 100m should produce significant casualties."""
        from stochastic_warfare.combat.archery import (
            ArcheryEngine, MissileType, ArmorType,
        )
        total_cas = 0
        runs = 100
        for seed in range(runs):
            eng = ArcheryEngine(rng=np.random.default_rng(seed))
            result = eng.fire_volley(
                "u1", 100, 100.0, MissileType.LONGBOW,
                ArmorType.NONE,
            )
            total_cas += result.casualties
        avg_cas = total_cas / runs
        # Phit at 100m = 0.12, 100 archers → ~12 casualties
        assert 3 <= avg_cas <= 25

    def test_plate_armor_reduces_archery(self) -> None:
        """Plate armor should significantly reduce archery casualties."""
        from stochastic_warfare.combat.archery import (
            ArcheryEngine, MissileType, ArmorType,
        )
        none_cas = 0
        plate_cas = 0
        runs = 200
        for seed in range(runs):
            eng = ArcheryEngine(rng=np.random.default_rng(seed))
            r1 = eng.fire_volley("u1", 100, 100.0, MissileType.LONGBOW, ArmorType.NONE)
            none_cas += r1.casualties
            eng2 = ArcheryEngine(rng=np.random.default_rng(seed + 10000))
            r2 = eng2.fire_volley("u2", 100, 100.0, MissileType.LONGBOW, ArmorType.PLATE)
            plate_cas += r2.casualties
        assert plate_cas < none_cas

    def test_testudo_blocks_archery(self) -> None:
        """TESTUDO formation should have very low archery vulnerability."""
        from stochastic_warfare.movement.formation_ancient import (
            AncientFormationEngine, AncientFormationType,
        )
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.TESTUDO)
        assert eng.archery_vulnerability("u1") == pytest.approx(0.1)

    def test_phalanx_flanking_vulnerability(self) -> None:
        """Phalanx is very vulnerable to flanking."""
        from stochastic_warfare.movement.formation_ancient import (
            AncientFormationEngine, AncientFormationType,
        )
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PHALANX)
        assert eng.flanking_vulnerability("u1") == pytest.approx(2.0)

    def test_pike_stops_cavalry(self) -> None:
        """Pike block should have very low cavalry vulnerability."""
        from stochastic_warfare.movement.formation_ancient import (
            AncientFormationEngine, AncientFormationType,
        )
        eng = AncientFormationEngine()
        eng.set_formation("u1", AncientFormationType.PIKE_BLOCK)
        assert eng.cavalry_vulnerability("u1") == pytest.approx(0.2)

    def test_reach_advantage_first_round(self) -> None:
        """Longer weapon should have advantage on first round."""
        from stochastic_warfare.combat.melee import MeleeEngine
        eng = MeleeEngine(rng=make_rng(42))
        # Pike (5m) vs gladius (1m) — pike has reach advantage
        advantage = eng.compute_reach_advantage(5.0, 1.0, round_number=1)
        assert advantage == pytest.approx(1.3)

    def test_flanking_doubles_casualties(self) -> None:
        """Flanked units should take much higher casualties."""
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        flanked_cas = 0
        unflanked_cas = 0
        runs = 100
        for seed in range(runs):
            eng = MeleeEngine(rng=np.random.default_rng(seed))
            r1 = eng.resolve_melee_round(
                100, 100, MeleeType.PIKE_PUSH,
                round_number=1, is_flanked=True,
            )
            flanked_cas += r1.defender_casualties
            eng2 = MeleeEngine(rng=np.random.default_rng(seed + 10000))
            r2 = eng2.resolve_melee_round(
                100, 100, MeleeType.PIKE_PUSH,
                round_number=1, is_flanked=False,
            )
            unflanked_cas += r2.defender_casualties
        assert flanked_cas > unflanked_cas

    def test_siege_breach_timeline(self) -> None:
        """2 trebuchets should breach walls in ~7 days."""
        from stochastic_warfare.combat.siege import SiegeEngine, SiegePhase
        eng = SiegeEngine(rng=make_rng(42))
        eng.begin_siege("s1", garrison_size=500, food_days=60, attacker_size=2000)
        for day in range(30):
            eng.advance_day("s1", n_trebuchets=2)
            if eng.get_phase("s1") == SiegePhase.BREACH:
                break
        assert eng.get_phase("s1") == SiegePhase.BREACH
        state = eng.get_siege_state("s1")
        # 2 trebuchets × 50 dmg/day = 100 dmg/day
        # Breach at 1000 × 0.3 = 300 HP remaining → 700 damage needed → 7 days
        assert state.days_elapsed <= 10

    def test_visual_signal_banner_range(self) -> None:
        """Banner signal should work within 1000m with LOS."""
        from stochastic_warfare.c2.visual_signals import VisualSignalEngine, SignalType
        eng = VisualSignalEngine(rng=make_rng(42))
        msg = eng.send_signal(
            SignalType.BANNER,
            (0.0, 0.0), (500.0, 0.0),
            has_los=True, sim_time_s=0.0,
        )
        assert msg is not None
        assert msg.received is True

    def test_visual_signal_banner_out_of_range(self) -> None:
        """Banner signal should fail beyond 1000m."""
        from stochastic_warfare.c2.visual_signals import VisualSignalEngine, SignalType
        eng = VisualSignalEngine(rng=make_rng(42))
        msg = eng.send_signal(
            SignalType.BANNER,
            (0.0, 0.0), (1500.0, 0.0),
            has_los=True, sim_time_s=0.0,
        )
        assert msg is None


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Deterministic replay of Ancient/Medieval engine operations."""

    def test_archery_deterministic(self) -> None:
        from stochastic_warfare.combat.archery import (
            ArcheryEngine, MissileType, ArmorType,
        )
        results = []
        for _ in range(2):
            eng = ArcheryEngine(rng=make_rng(42))
            result = eng.fire_volley(
                "u1", 100, 100.0, MissileType.LONGBOW, ArmorType.NONE,
            )
            results.append(result.casualties)
        assert results[0] == results[1]

    def test_melee_ancient_deterministic(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        results = []
        for _ in range(2):
            eng = MeleeEngine(rng=make_rng(42))
            result = eng.resolve_melee_round(
                200, 100, MeleeType.PIKE_PUSH,
                round_number=1, attacker_reach_m=4.0, defender_reach_m=1.5,
            )
            results.append(result.defender_casualties)
        assert results[0] == results[1]


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing eras still load correctly."""

    def test_modern_still_works(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("modern")
        assert cfg.era.value == "modern"
        assert len(cfg.disabled_modules) == 0

    def test_ww2_still_works(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww2")
        assert cfg.era.value == "ww2"

    def test_ww1_still_works(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert cfg.era.value == "ww1"

    def test_napoleonic_still_works(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert cfg.era.value == "napoleonic"

    def test_austerlitz_still_loads(self) -> None:
        path = DATA_DIR / "eras" / "napoleonic" / "scenarios" / "austerlitz" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["era"] == "napoleonic"

    def test_waterloo_still_loads(self) -> None:
        path = DATA_DIR / "eras" / "napoleonic" / "scenarios" / "waterloo" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["era"] == "napoleonic"
