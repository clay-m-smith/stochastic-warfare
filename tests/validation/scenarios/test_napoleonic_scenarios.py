"""Phase 22c tests — Napoleonic validation scenarios.

Tests for:
- Austerlitz scenario loading, era validation, terrain
- Waterloo scenario loading, infantry/cavalry balance
- CBRN correctly disabled for Napoleonic era
- Engine extension integration (volley fire, melee, formations, cavalry)
- Deterministic replay
- Backward compat (modern/ww2/ww1 still load)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from tests.conftest import make_rng

DATA_DIR = Path("data")
NAP_DIR = DATA_DIR / "eras" / "napoleonic"


# ---------------------------------------------------------------------------
# Scenario loading helpers
# ---------------------------------------------------------------------------


def _load_scenario_yaml(name: str) -> dict:
    path = NAP_DIR / "scenarios" / name / "scenario.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_scenario_config(name: str):
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
    raw = _load_scenario_yaml(name)
    return CampaignScenarioConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Austerlitz — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestAusterlitzScenarioLoading:
    """Austerlitz scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("austerlitz")
        assert "Austerlitz" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        assert cfg.era == "napoleonic"

    def test_terrain_type(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        assert cfg.terrain.terrain_type == "hilly_defense"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        assert len(cfg.sides) == 2
        names = {s.side for s in cfg.sides}
        assert names == {"french", "coalition"}

    def test_french_has_old_guard(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        french = [s for s in cfg.sides if s.side == "french"][0]
        guard_entries = [u for u in french.units if u.get("unit_type") == "french_old_guard"]
        assert len(guard_entries) > 0

    def test_french_has_cavalry(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        french = [s for s in cfg.sides if s.side == "french"][0]
        cav_entries = [u for u in french.units if u.get("unit_type") == "cuirassier_squadron"]
        assert len(cav_entries) > 0

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("austerlitz")
        assert len(raw["documented_outcomes"]) >= 2

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config("austerlitz")
        assert len(cfg.objectives) >= 3

    def test_era_config_correct(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "cbrn" in cfg.disabled_modules
        assert "ew" in cfg.disabled_modules


# ---------------------------------------------------------------------------
# Waterloo — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestWaterlooScenarioLoading:
    """Waterloo scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("waterloo")
        assert "Waterloo" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("waterloo")
        assert cfg.era == "napoleonic"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("waterloo")
        names = {s.side for s in cfg.sides}
        assert names == {"french", "british"}

    def test_french_has_cuirassiers(self) -> None:
        cfg = _load_scenario_config("waterloo")
        french = [s for s in cfg.sides if s.side == "french"][0]
        cav = [u for u in french.units if u.get("unit_type") == "cuirassier_squadron"]
        assert len(cav) > 0

    def test_british_has_rifles(self) -> None:
        cfg = _load_scenario_config("waterloo")
        british = [s for s in cfg.sides if s.side == "british"][0]
        rifles = [u for u in british.units if u.get("unit_type") == "british_rifle_company"]
        assert len(rifles) > 0

    def test_french_has_lancers(self) -> None:
        cfg = _load_scenario_config("waterloo")
        french = [s for s in cfg.sides if s.side == "french"][0]
        lancers = [u for u in french.units if u.get("unit_type") == "lancer_squadron"]
        assert len(lancers) > 0

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("waterloo")
        assert len(raw["documented_outcomes"]) >= 2

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config("waterloo")
        assert len(cfg.objectives) >= 3


# ---------------------------------------------------------------------------
# CBRN disabled for Napoleonic era
# ---------------------------------------------------------------------------


class TestCBRNDisabled:
    """CBRN is correctly disabled for Napoleonic era."""

    def test_cbrn_in_disabled_modules(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("napoleonic")
        assert "cbrn" in cfg.disabled_modules

    def test_ww1_cbrn_enabled(self) -> None:
        """WW1 keeps CBRN (gas warfare)."""
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "cbrn" not in cfg.disabled_modules


# ---------------------------------------------------------------------------
# Engine extension integration (Napoleonic combat mechanics)
# ---------------------------------------------------------------------------


class TestNapoleonicCombatMechanics:
    """Napoleonic combat mechanics integration."""

    def test_musket_volley_casualties_realistic(self) -> None:
        """500 muskets at 100m should produce ~25 casualties (2-5%)."""
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        total_cas = 0
        runs = 100
        for seed in range(runs):
            eng = VolleyFireEngine(rng=make_rng(seed))
            result = eng.fire_volley(500, 100.0)
            total_cas += result.casualties
        avg_cas = total_cas / runs
        # 2-5% of 500 = 10-25 (plan says ~25 hits, Phit=0.05 at 100m)
        assert 10 <= avg_cas <= 40

    def test_cavalry_breaks_infantry_not_square(self) -> None:
        """Cavalry should break infantry in LINE more than SQUARE."""
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType

        line_breaks = 0
        square_breaks = 0
        for seed in range(100):
            eng = MeleeEngine(rng=make_rng(seed))
            # LINE: cavalry vulnerability = 1.0
            d_breaks_line, _ = eng.check_pre_contact_morale(
                0.7, 0.5, MeleeType.CAVALRY_CHARGE, 1.0,
            )
            if d_breaks_line:
                line_breaks += 1
            # SQUARE: cavalry vulnerability = 0.1
            d_breaks_sq, _ = eng.check_pre_contact_morale(
                0.7, 0.5, MeleeType.CAVALRY_CHARGE, 0.1,
            )
            if d_breaks_sq:
                square_breaks += 1
        # Line should break more often (deterministic thresholds)
        assert line_breaks >= square_breaks

    def test_square_stops_cavalry(self) -> None:
        """Square formation should be nearly immune to cavalry."""
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine, NapoleonicFormationType,
        )
        eng = NapoleonicFormationEngine()
        eng.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert eng.cavalry_vulnerability("u1") == pytest.approx(0.1)

    def test_square_vulnerable_to_artillery(self) -> None:
        """Square is the most vulnerable to artillery."""
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine, NapoleonicFormationType,
        )
        eng = NapoleonicFormationEngine()
        eng.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert eng.artillery_vulnerability("u1") == pytest.approx(2.0)

    def test_courier_hour_scale_delays(self) -> None:
        """10km courier should take ~30 min."""
        from stochastic_warfare.c2.courier import CourierEngine, CourierType
        eng = CourierEngine(rng=np.random.default_rng(0))
        time = eng.compute_travel_time(10000.0, CourierType.MOUNTED_ADC, "open")
        assert 1500.0 < time < 2500.0  # ~33 min

    def test_formation_changes_take_minutes(self) -> None:
        """Formation transitions take 30-120 seconds."""
        from stochastic_warfare.movement.formation_napoleonic import (
            NapoleonicFormationEngine, NapoleonicFormationType,
        )
        eng = NapoleonicFormationEngine()
        eng.set_formation("u1", NapoleonicFormationType.LINE)
        time_s = eng.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        assert 30.0 <= time_s <= 120.0


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Deterministic replay of Napoleonic engine operations."""

    def test_volley_deterministic(self) -> None:
        from stochastic_warfare.combat.volley_fire import VolleyFireEngine
        results = []
        for _ in range(2):
            eng = VolleyFireEngine(rng=make_rng(42))
            result = eng.fire_volley(500, 100.0)
            results.append(result.casualties)
        assert results[0] == results[1]

    def test_melee_deterministic(self) -> None:
        from stochastic_warfare.combat.melee import MeleeEngine, MeleeType
        results = []
        for _ in range(2):
            eng = MeleeEngine(rng=make_rng(42))
            result = eng.resolve_melee_round(120, 75, MeleeType.CAVALRY_CHARGE, 1.0)
            results.append(result.defender_casualties)
        assert results[0] == results[1]

    def test_foraging_deterministic(self) -> None:
        from stochastic_warfare.logistics.foraging import (
            ForagingEngine, TerrainProductivity,
        )
        results = []
        for _ in range(2):
            eng = ForagingEngine(rng=make_rng(42))
            eng.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
            result = eng.forage("z1", 10000, "summer")
            results.append((result.rations_supplied, result.ambush_occurred))
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
        assert "cbrn" not in cfg.disabled_modules

    def test_somme_still_loads(self) -> None:
        path = DATA_DIR / "eras" / "ww1" / "scenarios" / "somme_july1" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["era"] == "ww1"

    def test_cambrai_still_loads(self) -> None:
        path = DATA_DIR / "eras" / "ww1" / "scenarios" / "cambrai" / "scenario.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert raw["era"] == "ww1"
