"""Tests for entities/organization/orbat.py."""

from pathlib import Path

import numpy as np

from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.orbat import OrbatLoader, TOEDefinition

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UNITS_DIR = DATA_DIR / "units"
ORG_DIR = DATA_DIR / "organizations" / "us_modern"


class TestTOEDefinition:
    def test_valid(self) -> None:
        t = TOEDefinition(
            name="Test Plt", echelon="PLATOON", nation="US", era="modern",
            subordinates=[{"unit_type": "us_rifle_squad", "count": 3, "echelon": "SQUAD"}],
        )
        assert t.name == "Test Plt"
        assert len(t.subordinates) == 1

    def test_default_staff(self) -> None:
        t = TOEDefinition(
            name="Test", echelon="SQUAD",
            subordinates=[],
        )
        assert t.staff == []


class TestLoadTOE:
    def test_load_infantry_platoon(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "infantry_platoon.yaml")
        assert toe.name == "US Infantry Platoon"
        assert toe.echelon == "PLATOON"
        assert len(toe.subordinates) == 1
        assert toe.subordinates[0].unit_type == "us_rifle_squad"
        assert toe.subordinates[0].count == 3

    def test_load_tank_company(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "tank_company.yaml")
        assert toe.name == "US Tank Company"
        assert toe.echelon == "COMPANY"
        assert toe.subordinates[0].count == 14


class TestBuildHierarchy:
    def test_infantry_platoon(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "infantry_platoon.yaml")
        unit_loader = UnitLoader(UNITS_DIR)
        unit_loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))

        tree = OrbatLoader.build_hierarchy(
            toe, unit_loader, "plt-hq", "blue", rng,
        )
        assert len(tree) == 4  # 1 HQ + 3 squads
        assert tree.get_parent("plt-hq") is None
        children = tree.get_children("plt-hq")
        assert len(children) == 3
        for cid in children:
            assert tree.get_node(cid).echelon == EchelonLevel.SQUAD

    def test_tank_company(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "tank_company.yaml")
        unit_loader = UnitLoader(UNITS_DIR)
        unit_loader.load_all()
        rng = np.random.Generator(np.random.PCG64(42))

        tree = OrbatLoader.build_hierarchy(
            toe, unit_loader, "co-hq", "blue", rng,
        )
        assert len(tree) == 15  # 1 HQ + 14 tanks
        children = tree.get_children("co-hq")
        assert len(children) == 14

    def test_deterministic(self) -> None:
        toe = OrbatLoader.load_toe(ORG_DIR / "infantry_platoon.yaml")
        unit_loader = UnitLoader(UNITS_DIR)
        unit_loader.load_all()

        rng1 = np.random.Generator(np.random.PCG64(99))
        rng2 = np.random.Generator(np.random.PCG64(99))
        tree1 = OrbatLoader.build_hierarchy(toe, unit_loader, "p1", "blue", rng1)
        tree2 = OrbatLoader.build_hierarchy(toe, unit_loader, "p2", "blue", rng2)

        assert len(tree1) == len(tree2)
