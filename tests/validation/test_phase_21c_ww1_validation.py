"""Phase 21c tests — WW1 validation scenarios.

Tests for:
- Somme Day 1 scenario loading, era validation, trench warfare terrain
- Cambrai scenario loading, tank integration
- Engine extension integration (trenches, barrage, gas)
- Deterministic replay
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from tests.conftest import make_rng

DATA_DIR = Path("data")
WW1_DIR = DATA_DIR / "eras" / "ww1"


# ---------------------------------------------------------------------------
# Scenario loading helpers
# ---------------------------------------------------------------------------


def _load_scenario_yaml(name: str) -> dict:
    path = WW1_DIR / "scenarios" / name / "scenario.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _load_scenario_config(name: str):
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig
    raw = _load_scenario_yaml(name)
    return CampaignScenarioConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Somme Day 1 — scenario loading & era validation
# ---------------------------------------------------------------------------


class TestSommeScenarioLoading:
    """Somme Day 1 scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("somme_july1")
        assert raw["name"] == "Somme Day 1 (July 1, 1916)"

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("somme_july1")
        assert cfg.era == "ww1"

    def test_terrain_type(self) -> None:
        cfg = _load_scenario_config("somme_july1")
        assert cfg.terrain.terrain_type == "trench_warfare"

    def test_two_sides(self) -> None:
        cfg = _load_scenario_config("somme_july1")
        assert len(cfg.sides) == 2
        names = {s.side for s in cfg.sides}
        assert names == {"british", "german"}

    def test_era_config_correct(self) -> None:
        from stochastic_warfare.core.era import get_era_config
        cfg = get_era_config("ww1")
        assert "cbrn" not in cfg.disabled_modules
        assert "ew" in cfg.disabled_modules

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("somme_july1")
        assert len(raw["documented_outcomes"]) >= 2


# ---------------------------------------------------------------------------
# Cambrai — scenario loading & tank integration
# ---------------------------------------------------------------------------


class TestCambraiScenarioLoading:
    """Cambrai scenario YAML loads correctly."""

    def test_yaml_loads(self) -> None:
        raw = _load_scenario_yaml("cambrai")
        assert "Cambrai" in raw["name"]

    def test_config_validates(self) -> None:
        cfg = _load_scenario_config("cambrai")
        assert cfg.era == "ww1"

    def test_has_tanks(self) -> None:
        cfg = _load_scenario_config("cambrai")
        british = [s for s in cfg.sides if s.side == "british"][0]
        tank_entries = [u for u in british.units if u.get("unit_type") == "mark_iv_tank"]
        assert len(tank_entries) > 0

    def test_has_objectives(self) -> None:
        cfg = _load_scenario_config("cambrai")
        assert len(cfg.objectives) >= 3

    def test_documented_outcomes(self) -> None:
        raw = _load_scenario_yaml("cambrai")
        assert len(raw["documented_outcomes"]) >= 2


# ---------------------------------------------------------------------------
# Trench system integration
# ---------------------------------------------------------------------------


class TestTrenchIntegration:
    """Trench system engine integration with scenarios."""

    @pytest.fixture()
    def trench_engine(self):
        from stochastic_warfare.terrain.trenches import (
            TrenchConfig, TrenchSegment, TrenchSystemEngine, TrenchType,
        )
        eng = TrenchSystemEngine(TrenchConfig())
        # Somme-like setup: 3 German trench lines
        for i, (y, tt) in enumerate([
            (2000, TrenchType.FIRE_TRENCH),
            (2300, TrenchType.SUPPORT_TRENCH),
            (2600, TrenchType.FIRE_TRENCH),
        ]):
            eng.add_trench(TrenchSegment(
                trench_id=f"german_line_{i}",
                trench_type=tt,
                side="german",
                points=[[0, y], [10000, y]],
                has_wire=True,
                has_dugout=(i == 0),
            ))
        eng.add_no_mans_land((0, 1000), (10000, 1000), width_m=1000.0)
        return eng

    def test_german_first_line_cover(self, trench_engine) -> None:
        cover = trench_engine.cover_value_at(5000.0, 2000.0)
        assert cover >= 0.8  # Fire trench

    def test_no_mans_land_slow(self, trench_engine) -> None:
        factor = trench_engine.movement_factor_at(5000.0, 1000.0)
        assert factor <= 0.3

    def test_wire_present(self, trench_engine) -> None:
        result = trench_engine.query_trench(5000.0, 2000.0)
        assert result.has_wire is True

    def test_dugout_first_line(self, trench_engine) -> None:
        result = trench_engine.query_trench(5000.0, 2000.0)
        assert result.has_dugout is True

    def test_no_dugout_second_line(self, trench_engine) -> None:
        result = trench_engine.query_trench(5000.0, 2300.0)
        assert result.has_dugout is False


# ---------------------------------------------------------------------------
# Barrage integration
# ---------------------------------------------------------------------------


class TestBarrageIntegration:
    """Barrage engine behavior for WW1 scenarios."""

    def test_standing_barrage_suppresses(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        eng = BarrageEngine(rng=make_rng(42))
        eng.create_barrage(
            "pre_assault", BarrageType.STANDING, "british",
            5000.0, 2000.0, fire_density=300.0,
        )
        effects = eng.compute_effects(5000.0, 2000.0)
        assert effects["suppression_p"] > 0.5

    def test_creeping_barrage_advances(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        eng = BarrageEngine(rng=make_rng(42))
        zone = eng.create_barrage(
            "creeping", BarrageType.CREEPING, "british",
            5000.0, 1500.0, heading_deg=0.0,
        )
        initial = zone.center_northing
        eng.update(120.0)  # 2 minutes
        assert zone.center_northing > initial + 90.0  # ~100m at 50m/min

    def test_dugout_protection_matters(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        eng = BarrageEngine(rng=make_rng(42))
        eng.create_barrage(
            "heavy", BarrageType.STANDING, "british",
            5000.0, 2000.0, fire_density=500.0,
        )
        open_e = eng.compute_effects(5000.0, 2000.0, in_dugout=False)
        dug_e = eng.compute_effects(5000.0, 2000.0, in_dugout=True)
        assert dug_e["casualty_p"] < open_e["casualty_p"] * 0.5

    def test_barrage_timing_critical(self) -> None:
        """Advancing before barrage lifts is dangerous."""
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        eng = BarrageEngine(rng=make_rng(42))
        eng.create_barrage(
            "creep", BarrageType.CREEPING, "british",
            5000.0, 1500.0, heading_deg=0.0,
        )
        # Infantry at barrage line → not safe
        assert eng.is_safe_to_advance(5000.0, 1500.0, "creep") is False
        # Infantry well behind → safe
        assert eng.is_safe_to_advance(5000.0, 1200.0, "creep") is True


# ---------------------------------------------------------------------------
# Gas warfare integration
# ---------------------------------------------------------------------------


class TestGasWarfareIntegration:
    """Gas warfare in WW1 context."""

    def test_chlorine_agent_exists(self) -> None:
        agent = DATA_DIR / "cbrn" / "agents" / "chlorine.yaml"
        assert agent.exists()

    def test_phosgene_agent_exists(self) -> None:
        agent = DATA_DIR / "cbrn" / "agents" / "phosgene.yaml"
        assert agent.exists()

    def test_gas_mask_provides_protection(self) -> None:
        from stochastic_warfare.combat.gas_warfare import (
            GasWarfareEngine,
            GasMaskType,
        )
        eng = GasWarfareEngine()
        mopp = eng.set_unit_gas_mask("inf_1", GasMaskType.SMALL_BOX_RESPIRATOR)
        assert mopp == 3  # Good protection

    def test_no_mask_is_vulnerable(self) -> None:
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
        eng = GasWarfareEngine()
        mopp = eng.get_unit_mopp_level("unprotected_unit")
        assert mopp == 0  # No protection


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    """Deterministic replay of WW1 engine operations."""

    def test_trench_query_deterministic(self) -> None:
        from stochastic_warfare.terrain.trenches import (
            TrenchConfig, TrenchSegment, TrenchSystemEngine, TrenchType,
        )
        results = []
        for _ in range(2):
            eng = TrenchSystemEngine()
            eng.add_trench(TrenchSegment(
                trench_id="t1",
                trench_type=TrenchType.FIRE_TRENCH,
                side="a",
                points=[[0, 0], [100, 0]],
            ))
            results.append(eng.cover_value_at(50.0, 0.0))
        assert results[0] == results[1]

    def test_barrage_deterministic(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        results = []
        for _ in range(2):
            eng = BarrageEngine(rng=make_rng(42))
            eng.create_barrage("b1", BarrageType.CREEPING, "a", 500, 500)
            eng.update(300.0)
            z = eng._barrages["b1"]
            results.append((
                z.center_northing,
                z.drift_easting_m,
                z.drift_northing_m,
            ))
        assert results[0] == results[1]

    def test_gas_bombardment_deterministic(self) -> None:
        from unittest.mock import MagicMock
        from stochastic_warfare.combat.gas_warfare import GasWarfareEngine

        positions = []
        for _ in range(2):
            cbrn = MagicMock()
            cbrn.release_agent = MagicMock(return_value="p1")
            eng = GasWarfareEngine(cbrn_engine=cbrn, rng=make_rng(42))
            eng.execute_gas_bombardment("chlorine", 500, 500, num_shells=3)
            call_positions = [
                (c.kwargs["position"].easting, c.kwargs["position"].northing)
                for c in cbrn.release_agent.call_args_list
            ]
            positions.append(call_positions)
        assert positions[0] == positions[1]

    def test_barrage_state_roundtrip_deterministic(self) -> None:
        from stochastic_warfare.combat.barrage import BarrageEngine, BarrageType
        eng1 = BarrageEngine(rng=make_rng(42))
        eng1.create_barrage("b1", BarrageType.STANDING, "a", 500, 500)
        state = eng1.get_state()

        eng2 = BarrageEngine(rng=make_rng(99))
        eng2.set_state(state)
        assert eng2._barrages["b1"].center_easting == 500.0
        assert eng2._barrages["b1"].active is True
