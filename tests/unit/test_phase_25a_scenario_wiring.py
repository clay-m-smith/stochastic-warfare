"""Phase 25a — ScenarioLoader auto-wiring tests.

Tests that CampaignScenarioConfig accepts new optional config blocks and
that ScenarioLoader._create_optional_engines() instantiates the correct
engines (or leaves them None) based on those blocks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
    TerrainConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_SIDES = [
    {"side": "blue", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
    {"side": "red", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
]


def _minimal_config(**overrides: Any) -> CampaignScenarioConfig:
    """Build minimal valid CampaignScenarioConfig with optional overrides."""
    base = {
        "name": "test",
        "date": "2024-06-15",
        "duration_hours": 1.0,
        "terrain": {"width_m": 1000, "height_m": 1000, "cell_size_m": 100},
        "sides": _MINIMAL_SIDES,
    }
    base.update(overrides)
    return CampaignScenarioConfig.model_validate(base)


def _make_rng_mgr(seed: int = 42) -> RNGManager:
    return RNGManager(seed)


def _make_bus() -> EventBus:
    return EventBus()


# =========================================================================
# 1. Config parsing — new fields accepted, null valid, defaults None
# =========================================================================


class TestConfigParsing:
    """New config blocks are accepted and default to None."""

    def test_defaults_all_none(self) -> None:
        cfg = _minimal_config()
        assert cfg.ew_config is None
        assert cfg.space_config is None
        assert cfg.cbrn_config is None
        assert cfg.school_config is None
        assert cfg.commander_config is None
        assert cfg.escalation_config is None

    def test_ew_config_accepted(self) -> None:
        cfg = _minimal_config(ew_config={"enable_ew": True})
        assert cfg.ew_config == {"enable_ew": True}

    def test_space_config_accepted(self) -> None:
        cfg = _minimal_config(space_config={"enable_space": True})
        assert cfg.space_config == {"enable_space": True}

    def test_cbrn_config_accepted(self) -> None:
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        assert cfg.cbrn_config == {"enable_cbrn": True}

    def test_school_config_accepted(self) -> None:
        cfg = _minimal_config(school_config={"unit_assignments": {}})
        assert cfg.school_config == {"unit_assignments": {}}

    def test_commander_config_accepted(self) -> None:
        cfg = _minimal_config(commander_config={"side_defaults": {"blue": "balanced_default"}})
        assert cfg.commander_config is not None

    def test_escalation_config_accepted(self) -> None:
        cfg = _minimal_config(escalation_config={"some_key": 1})
        assert cfg.escalation_config == {"some_key": 1}

    def test_null_ew_config(self) -> None:
        cfg = _minimal_config(ew_config=None)
        assert cfg.ew_config is None

    def test_null_space_config(self) -> None:
        cfg = _minimal_config(space_config=None)
        assert cfg.space_config is None

    def test_null_cbrn_config(self) -> None:
        cfg = _minimal_config(cbrn_config=None)
        assert cfg.cbrn_config is None


# =========================================================================
# 2. EW creation
# =========================================================================


class TestEWCreation:
    """EW engines created when ew_config present, None otherwise."""

    def test_ew_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None  # not needed for EW
        rng_mgr = _make_rng_mgr()
        bus = _make_bus()
        cfg = _minimal_config(ew_config={"enable_ew": True})

        result = loader._create_ew_engines(rng_mgr, bus, cfg.ew_config)
        assert result["ew_engine"] is not None
        assert result["eccm_engine"] is not None
        assert result["sigint_engine"] is not None
        assert result["ew_decoy_engine"] is not None

    def test_ew_null_no_engines(self) -> None:
        cfg = _minimal_config(ew_config=None)
        rng_mgr = _make_rng_mgr()
        bus = _make_bus()

        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        result = loader._create_optional_engines(rng_mgr, bus, cfg, c2_rng)
        assert result.get("ew_engine") is None
        assert result.get("eccm_engine") is None

    def test_ew_engine_is_jamming_engine(self) -> None:
        from stochastic_warfare.ew.jamming import JammingEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(), {"enable_ew": False},
        )
        assert isinstance(result["ew_engine"], JammingEngine)

    def test_eccm_engine_type(self) -> None:
        from stochastic_warfare.ew.eccm import ECCMEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(), {"enable_ew": True},
        )
        assert isinstance(result["eccm_engine"], ECCMEngine)

    def test_sigint_engine_type(self) -> None:
        from stochastic_warfare.ew.sigint import SIGINTEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(), {"enable_ew": True},
        )
        assert isinstance(result["sigint_engine"], SIGINTEngine)

    def test_ew_decoy_engine_type(self) -> None:
        from stochastic_warfare.ew.decoys_ew import EWDecoyEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(), {"enable_ew": True},
        )
        assert isinstance(result["ew_decoy_engine"], EWDecoyEngine)

    def test_ew_config_validates(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(),
            {"enable_ew": True, "js_threshold_db": 5.0},
        )
        assert result["ew_engine"] is not None

    def test_ew_config_custom_threshold(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_ew_engines(
            _make_rng_mgr(), _make_bus(),
            {"enable_ew": True, "js_threshold_db": 10.0},
        )
        assert result["ew_engine"]._config.js_threshold_db == 10.0


# =========================================================================
# 3. Space creation
# =========================================================================


class TestSpaceCreation:
    """Space engine created when space_config present, None otherwise."""

    def test_space_engine_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_space_engines(
            _make_rng_mgr(), _make_bus(),
            {"enable_space": True, "theater_lat": 32.0, "theater_lon": 35.0},
        )
        assert result["space_engine"] is not None

    def test_space_null_no_engine(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(space_config=None)
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("space_engine") is None

    def test_space_engine_type(self) -> None:
        from stochastic_warfare.space.constellations import SpaceEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_space_engines(
            _make_rng_mgr(), _make_bus(), {"enable_space": True},
        )
        assert isinstance(result["space_engine"], SpaceEngine)

    def test_space_has_sub_engines(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_space_engines(
            _make_rng_mgr(), _make_bus(), {"enable_space": True},
        )
        engine = result["space_engine"]
        assert engine.gps_engine is not None
        assert engine.isr_engine is not None
        assert engine.satcom_engine is not None
        assert engine.asat_engine is not None

    def test_space_config_params(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_space_engines(
            _make_rng_mgr(), _make_bus(),
            {"enable_space": True, "theater_lat": 45.0},
        )
        assert result["space_engine"]._config.theater_lat == 45.0

    def test_space_default_disabled(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_space_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert result["space_engine"]._config.enable_space is False


# =========================================================================
# 4. CBRN creation
# =========================================================================


class TestCBRNCreation:
    """CBRN engine + sub-engines created when cbrn_config present."""

    def test_cbrn_engine_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["cbrn_engine"] is not None

    def test_cbrn_engine_type(self) -> None:
        from stochastic_warfare.cbrn.engine import CBRNEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert isinstance(result["cbrn_engine"], CBRNEngine)

    def test_cbrn_null_no_engine(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config=None)
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("cbrn_engine") is None

    def test_cbrn_uses_terrain_grid(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(
            cbrn_config={"enable_cbrn": True},
            terrain={"width_m": 2000, "height_m": 1000, "cell_size_m": 50},
        )
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        # Should have created contamination grid matching terrain
        engine = result["cbrn_engine"]
        assert engine is not None

    def test_cbrn_default_disabled(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["cbrn_engine"]._config.enable_cbrn is False

    def test_cbrn_enabled_in_config(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["cbrn_engine"]._config.enable_cbrn is True

    def test_cbrn_has_sub_engines(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        engine = result["cbrn_engine"]
        assert engine._dispersal is not None
        assert engine._contamination is not None
        assert engine._protection is not None

    def test_cbrn_has_nuclear_engine(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(cbrn_config={"enable_cbrn": True})
        result = loader._create_cbrn_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["cbrn_engine"]._nuclear is not None


# =========================================================================
# 5. Schools creation
# =========================================================================


class TestSchoolsCreation:
    """School registry created from school_config with factory."""

    def test_school_registry_created(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        result = loader._create_school_engines({"unit_assignments": {}})
        registry = result["school_registry"]
        assert registry is not None
        assert len(registry.all_schools()) == 9

    def test_school_null_no_registry(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(school_config=None)
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("school_registry") is None

    def test_school_factory_clausewitzian(self) -> None:
        from stochastic_warfare.c2.ai.schools import create_school, SchoolLoader
        from stochastic_warfare.c2.ai.schools.clausewitzian import ClausewitzianSchool

        sl = SchoolLoader()
        sl.load_all()
        defn = sl.get_definition("clausewitzian")
        school = create_school(defn)
        assert isinstance(school, ClausewitzianSchool)

    def test_school_factory_maneuverist(self) -> None:
        from stochastic_warfare.c2.ai.schools import create_school, SchoolLoader
        from stochastic_warfare.c2.ai.schools.maneuverist import ManeuveristSchool

        sl = SchoolLoader()
        sl.load_all()
        defn = sl.get_definition("maneuverist")
        school = create_school(defn)
        assert isinstance(school, ManeuveristSchool)

    def test_school_factory_unknown_raises(self) -> None:
        from stochastic_warfare.c2.ai.schools import create_school
        from stochastic_warfare.c2.ai.schools.base import SchoolDefinition

        fake_defn = SchoolDefinition(
            school_id="nonexistent_school",
            name="Fake",
            display_name="Fake School",
            description="Does not exist",
        )
        with pytest.raises(KeyError, match="Unknown school_id"):
            create_school(fake_defn)

    def test_school_unit_assignments(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        result = loader._create_school_engines({
            "unit_assignments": {"unit_1": "clausewitzian", "unit_2": "maneuverist"},
        })
        registry = result["school_registry"]
        s1 = registry.get_for_unit("unit_1")
        s2 = registry.get_for_unit("unit_2")
        assert s1 is not None and s1.school_id == "clausewitzian"
        assert s2 is not None and s2.school_id == "maneuverist"

    def test_school_all_nine_registered(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        result = loader._create_school_engines({"unit_assignments": {}})
        registry = result["school_registry"]
        school_ids = {s.school_id for s in registry.all_schools()}
        expected = {
            "clausewitzian", "maneuverist", "attrition", "airland_battle",
            "air_power", "sun_tzu", "deep_battle",
            "maritime_mahanian", "maritime_corbettian",
        }
        assert school_ids == expected

    def test_school_empty_assignments(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        result = loader._create_school_engines({})
        registry = result["school_registry"]
        assert registry.get_for_unit("nobody") is None


# =========================================================================
# 6. Commander creation
# =========================================================================


class TestCommanderCreation:
    """Commander engine created when commander_config present."""

    def test_commander_engine_created(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {})
        assert result["commander_engine"] is not None

    def test_commander_engine_type(self) -> None:
        from pathlib import Path
        from stochastic_warfare.c2.ai.commander import CommanderEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {})
        assert isinstance(result["commander_engine"], CommanderEngine)

    def test_commander_null_no_engine(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(commander_config=None)
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("commander_engine") is None

    def test_commander_with_config_params(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {
            "ooda_speed_base_mult": 1.5,
            "noise_sigma": 0.2,
        })
        engine = result["commander_engine"]
        assert engine._config.ooda_speed_base_mult == 1.5

    def test_commander_side_defaults_ignored_here(self) -> None:
        """side_defaults is handled in load(), not in engine creation."""
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        # Should not raise even with side_defaults present
        result = loader._create_commander_engine(c2_rng, {
            "side_defaults": {"blue": "balanced_default"},
        })
        assert result["commander_engine"] is not None

    def test_commander_profiles_loaded(self) -> None:
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_commander_engine(c2_rng, {})
        engine = result["commander_engine"]
        # Should have loaded profiles from data/commander_profiles/
        assert len(engine._loader.available_profiles()) >= 3


# =========================================================================
# 7. Escalation creation
# =========================================================================


class TestEscalationCreation:
    """All 9 escalation/unconventional engines created from escalation_config."""

    def test_all_escalation_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_escalation_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert result["escalation_engine"] is not None
        assert result["political_engine"] is not None
        assert result["consequence_engine"] is not None
        assert result["war_termination_engine"] is not None
        assert result["unconventional_engine"] is not None
        assert result["sof_engine"] is not None
        assert result["insurgency_engine"] is not None
        assert result["incendiary_engine"] is not None
        assert result["uxo_engine"] is not None

    def test_escalation_null_no_engines(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(escalation_config=None)
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("escalation_engine") is None
        assert result.get("political_engine") is None

    def test_escalation_engine_types(self) -> None:
        from stochastic_warfare.escalation.ladder import EscalationLadder
        from stochastic_warfare.escalation.political import PoliticalPressureEngine
        from stochastic_warfare.escalation.consequences import ConsequenceEngine
        from stochastic_warfare.escalation.war_termination import WarTerminationEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_escalation_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert isinstance(result["escalation_engine"], EscalationLadder)
        assert isinstance(result["political_engine"], PoliticalPressureEngine)
        assert isinstance(result["consequence_engine"], ConsequenceEngine)
        assert isinstance(result["war_termination_engine"], WarTerminationEngine)

    def test_unconventional_engine_types(self) -> None:
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine
        from stochastic_warfare.c2.ai.sof_ops import SOFOpsEngine
        from stochastic_warfare.population.insurgency import InsurgencyEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_escalation_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert isinstance(result["unconventional_engine"], UnconventionalWarfareEngine)
        assert isinstance(result["sof_engine"], SOFOpsEngine)
        assert isinstance(result["insurgency_engine"], InsurgencyEngine)

    def test_incendiary_uxo_types(self) -> None:
        from stochastic_warfare.combat.damage import IncendiaryDamageEngine, UXOEngine
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_escalation_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert isinstance(result["incendiary_engine"], IncendiaryDamageEngine)
        assert isinstance(result["uxo_engine"], UXOEngine)

    def test_escalation_engine_count(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        result = loader._create_escalation_engines(
            _make_rng_mgr(), _make_bus(), {},
        )
        assert len(result) == 9


# =========================================================================
# 8. Era engines
# =========================================================================


class TestEraEngines:
    """Era-specific engines created for non-modern eras."""

    def test_modern_no_era_engines(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(era="modern")
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        # No era-specific engines for modern
        assert result.get("trench_engine") is None
        assert result.get("volley_fire_engine") is None
        assert result.get("archery_engine") is None

    def test_ww2_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(era="ww2")
        result = loader._create_era_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["naval_gunnery_engine"] is not None
        assert result["convoy_engine"] is not None
        assert result["strategic_bombing_engine"] is not None

    def test_ww1_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(era="ww1")
        result = loader._create_era_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["trench_engine"] is not None
        assert result["barrage_engine"] is not None
        assert result["gas_warfare_engine"] is not None

    def test_napoleonic_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(era="napoleonic")
        result = loader._create_era_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["volley_fire_engine"] is not None
        assert result["melee_engine"] is not None
        assert result["cavalry_engine"] is not None
        assert result["formation_napoleonic_engine"] is not None
        assert result["courier_engine"] is not None
        assert result["foraging_engine"] is not None

    def test_ancient_engines_created(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config(era="ancient")
        result = loader._create_era_engines(_make_rng_mgr(), _make_bus(), cfg)
        assert result["archery_engine"] is not None
        assert result["siege_engine"] is not None
        assert result["formation_ancient_engine"] is not None
        assert result["naval_oar_engine"] is not None
        assert result["visual_signals_engine"] is not None


# =========================================================================
# 9. Integration / backward compat
# =========================================================================


class TestIntegration:
    """Full optional engine wiring + backward compatibility."""

    def test_all_none_backward_compat(self) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = None
        cfg = _minimal_config()
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert len(result) == 0

    def test_context_new_fields_default_none(self) -> None:
        from stochastic_warfare.core.clock import SimulationClock
        from datetime import timedelta, datetime, timezone

        ctx = SimulationContext(
            config=_minimal_config(),
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=10),
            ),
            rng_manager=_make_rng_mgr(),
            event_bus=_make_bus(),
        )
        assert ctx.commander_engine is None
        assert ctx.eccm_engine is None
        assert ctx.sigint_engine is None
        assert ctx.ew_decoy_engine is None

    def test_state_roundtrip_includes_new_engines(self) -> None:
        """New engine fields appear in get_state when populated."""
        from stochastic_warfare.core.clock import SimulationClock
        from datetime import timedelta, datetime, timezone

        ctx = SimulationContext(
            config=_minimal_config(),
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=10),
            ),
            rng_manager=_make_rng_mgr(),
            event_bus=_make_bus(),
        )
        state = ctx.get_state()
        # New engine keys should not appear when engines are None
        assert "commander_engine" not in state
        assert "eccm_engine" not in state

    def test_multiple_configs_simultaneous(self) -> None:
        """Multiple config blocks can be set together."""
        from pathlib import Path
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        loader = ScenarioLoader.__new__(ScenarioLoader)
        loader._data_dir = Path("data")
        cfg = _minimal_config(
            ew_config={"enable_ew": True},
            school_config={"unit_assignments": {}},
            commander_config={},
        )
        c2_rng = _make_rng_mgr().get_stream(ModuleId.C2)
        result = loader._create_optional_engines(_make_rng_mgr(), _make_bus(), cfg, c2_rng)
        assert result.get("ew_engine") is not None
        assert result.get("school_registry") is not None
        assert result.get("commander_engine") is not None
