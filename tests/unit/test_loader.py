"""Tests for entities/loader.py — YAML unit definition loading."""

from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.loader import UnitDefinition, UnitLoader
from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, GroundUnitType
from stochastic_warfare.entities.unit_classes.naval import NavalUnit
from stochastic_warfare.entities.unit_classes.support import SupportUnit

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "units"


# ── UnitDefinition pydantic model ────────────────────────────────────


class TestUnitDefinition:
    def test_valid_minimal(self) -> None:
        d = UnitDefinition(
            unit_type="test",
            domain="ground",
            display_name="Test Unit",
            max_speed=5.0,
            crew=[{"role": "COMMANDER", "count": 1}],
            equipment=[{"name": "Gun", "category": "WEAPON"}],
        )
        assert d.unit_type == "test"
        assert d.domain == "ground"

    def test_invalid_domain(self) -> None:
        with pytest.raises(Exception):
            UnitDefinition(
                unit_type="test",
                domain="space",
                display_name="Test",
                max_speed=5.0,
                crew=[{"role": "COMMANDER", "count": 1}],
                equipment=[{"name": "Gun", "category": "WEAPON"}],
            )


# ── Single file loading ─────────────────────────────────────────────


class TestLoadSingle:
    def test_load_m1a2(self) -> None:
        loader = UnitLoader(DATA_DIR)
        defn = loader.load_definition(DATA_DIR / "armor" / "m1a2.yaml")
        assert defn.unit_type == "m1a2"
        assert defn.domain == "ground"
        assert defn.max_speed == 18.0
        assert len(defn.crew) == 4
        assert len(defn.equipment) == 5

    def test_load_f16c(self) -> None:
        loader = UnitLoader(DATA_DIR)
        defn = loader.load_definition(DATA_DIR / "air_fixed_wing" / "f16c.yaml")
        assert defn.unit_type == "f16c"
        assert defn.domain == "aerial"

    def test_load_ddg51(self) -> None:
        loader = UnitLoader(DATA_DIR)
        defn = loader.load_definition(DATA_DIR / "naval_surface" / "ddg51.yaml")
        assert defn.unit_type == "ddg51"
        assert defn.domain == "naval"
        assert defn.draft == 9.4

    def test_load_ssn688(self) -> None:
        loader = UnitLoader(DATA_DIR)
        defn = loader.load_definition(DATA_DIR / "naval_subsurface" / "ssn688.yaml")
        assert defn.unit_type == "ssn688"
        assert defn.max_depth == 450.0


# ── Load all ─────────────────────────────────────────────────────────


class TestLoadAll:
    def test_load_all_recursive(self) -> None:
        loader = UnitLoader(DATA_DIR)
        loader.load_all()
        types = loader.available_types()
        assert len(types) >= 11
        assert "m1a2" in types
        assert "f16c" in types
        assert "ddg51" in types
        assert "ssn688" in types
        assert "hemtt" in types

    def test_available_types_sorted(self) -> None:
        loader = UnitLoader(DATA_DIR)
        loader.load_all()
        types = loader.available_types()
        assert types == sorted(types)


# ── Unit creation ────────────────────────────────────────────────────


class TestCreateUnit:
    @pytest.fixture()
    def loader(self) -> UnitLoader:
        l = UnitLoader(DATA_DIR)
        l.load_all()
        return l

    def _rng(self, seed: int = 42) -> np.random.Generator:
        return np.random.Generator(np.random.PCG64(seed))

    def test_create_m1a2(self, loader: UnitLoader) -> None:
        u = loader.create_unit("m1a2", "tank-01", Position(100.0, 200.0), Side.BLUE, self._rng())
        assert isinstance(u, GroundUnit)
        assert u.entity_id == "tank-01"
        assert u.unit_type == "m1a2"
        assert u.max_speed == 18.0
        assert u.ground_type == GroundUnitType.ARMOR
        assert u.armor_front == 600.0
        assert len(u.personnel) == 4
        assert len(u.equipment) == 5

    def test_create_infantry(self, loader: UnitLoader) -> None:
        u = loader.create_unit("us_rifle_squad", "sq-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, GroundUnit)
        assert len(u.personnel) == 9  # 1 + 7 + 1

    def test_create_f16c(self, loader: UnitLoader) -> None:
        u = loader.create_unit("f16c", "viper-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, AerialUnit)
        assert u.domain == Domain.AERIAL
        assert u.service_ceiling == 15240.0

    def test_create_mq9(self, loader: UnitLoader) -> None:
        u = loader.create_unit("mq9", "reaper-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, AerialUnit)
        assert u.is_uav
        assert u.data_link_range == 250000.0

    def test_create_ddg51(self, loader: UnitLoader) -> None:
        u = loader.create_unit("ddg51", "ddg-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, NavalUnit)
        assert u.domain == Domain.NAVAL
        assert u.draft == 9.4

    def test_create_ssn688(self, loader: UnitLoader) -> None:
        u = loader.create_unit("ssn688", "ssn-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, NavalUnit)
        assert u.is_submarine
        assert u.max_depth == 450.0

    def test_create_patriot(self, loader: UnitLoader) -> None:
        u = loader.create_unit("patriot", "ad-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, AirDefenseUnit)
        assert u.max_engagement_range == 160000.0

    def test_create_hemtt(self, loader: UnitLoader) -> None:
        u = loader.create_unit("hemtt", "truck-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, SupportUnit)
        assert u.cargo_capacity_tons == 10.0

    def test_create_ah64d(self, loader: UnitLoader) -> None:
        u = loader.create_unit("ah64d", "apache-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, AerialUnit)
        assert u.is_rotary_wing

    def test_create_lhd1(self, loader: UnitLoader) -> None:
        u = loader.create_unit("lhd1", "lhd-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        assert isinstance(u, NavalUnit)
        assert u.domain == Domain.AMPHIBIOUS

    def test_unknown_type_raises(self, loader: UnitLoader) -> None:
        with pytest.raises(KeyError):
            loader.create_unit("nonexistent", "x", Position(0.0, 0.0),
                               Side.BLUE, self._rng())

    def test_crew_ids_unique(self, loader: UnitLoader) -> None:
        u = loader.create_unit("ddg51", "ddg-01", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        ids = [m.member_id for m in u.personnel]
        assert len(ids) == len(set(ids))

    def test_equipment_ids_unique(self, loader: UnitLoader) -> None:
        u = loader.create_unit("m1a2", "t1", Position(0.0, 0.0),
                               Side.BLUE, self._rng())
        ids = [e.equipment_id for e in u.equipment]
        assert len(ids) == len(set(ids))

    def test_deterministic_creation(self, loader: UnitLoader) -> None:
        u1 = loader.create_unit("m1a2", "t1", Position(0.0, 0.0),
                                Side.BLUE, self._rng(99))
        u2 = loader.create_unit("m1a2", "t1", Position(0.0, 0.0),
                                Side.BLUE, self._rng(99))
        assert u1.personnel[0].experience == u2.personnel[0].experience
        assert u1.personnel[1].experience == u2.personnel[1].experience


class TestCreateUnitStateRoundtrip:
    def test_roundtrip_all_types(self) -> None:
        loader = UnitLoader(DATA_DIR)
        loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))
        for utype in loader.available_types():
            u = loader.create_unit(utype, f"rt-{utype}", Position(50.0, 60.0),
                                   Side.RED, rng)
            state = u.get_state()
            assert state["entity_id"] == f"rt-{utype}"
            assert state["unit_type"] == utype
