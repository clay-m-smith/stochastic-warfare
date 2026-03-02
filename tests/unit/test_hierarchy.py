"""Tests for entities/organization/hierarchy.py."""

import pytest

from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree


def _build_platoon() -> HierarchyTree:
    """Build a platoon with 3 squads, each with 2 fire teams."""
    tree = HierarchyTree()
    tree.add_unit("plt", EchelonLevel.PLATOON, side="blue")
    for i in range(3):
        sid = f"squad-{i}"
        tree.add_unit(sid, EchelonLevel.SQUAD, parent_id="plt")
        for j in range(2):
            tree.add_unit(f"ft-{i}-{j}", EchelonLevel.FIRE_TEAM, parent_id=sid)
    return tree


class TestAddUnit:
    def test_root(self) -> None:
        tree = HierarchyTree()
        node = tree.add_unit("root", EchelonLevel.BATTALION)
        assert node.unit_id == "root"
        assert node.parent_id is None
        assert len(tree) == 1

    def test_with_parent(self) -> None:
        tree = HierarchyTree()
        tree.add_unit("bn", EchelonLevel.BATTALION)
        tree.add_unit("co", EchelonLevel.COMPANY, parent_id="bn")
        assert tree.get_parent("co") == "bn"
        assert "co" in tree.get_children("bn")

    def test_duplicate_raises(self) -> None:
        tree = HierarchyTree()
        tree.add_unit("a", EchelonLevel.SQUAD)
        with pytest.raises(ValueError):
            tree.add_unit("a", EchelonLevel.SQUAD)

    def test_missing_parent_raises(self) -> None:
        tree = HierarchyTree()
        with pytest.raises(KeyError):
            tree.add_unit("child", EchelonLevel.SQUAD, parent_id="nonexistent")


class TestRemoveUnit:
    def test_remove_leaf(self) -> None:
        tree = _build_platoon()
        tree.remove_unit("ft-0-0")
        assert "ft-0-0" not in tree
        assert "ft-0-0" not in tree.get_children("squad-0")

    def test_remove_middle_reparents(self) -> None:
        tree = _build_platoon()
        tree.remove_unit("squad-0")
        assert "squad-0" not in tree
        # Fire teams should be reparented to platoon
        assert "ft-0-0" in tree.get_children("plt")
        assert "ft-0-1" in tree.get_children("plt")


class TestQueries:
    def test_get_parent(self) -> None:
        tree = _build_platoon()
        assert tree.get_parent("squad-1") == "plt"
        assert tree.get_parent("ft-2-0") == "squad-2"
        assert tree.get_parent("plt") is None

    def test_get_children(self) -> None:
        tree = _build_platoon()
        assert len(tree.get_children("plt")) == 3
        assert len(tree.get_children("squad-0")) == 2

    def test_chain_of_command(self) -> None:
        tree = _build_platoon()
        chain = tree.get_chain_of_command("ft-1-0")
        assert chain == ["plt", "squad-1", "ft-1-0"]

    def test_chain_root(self) -> None:
        tree = _build_platoon()
        assert tree.get_chain_of_command("plt") == ["plt"]

    def test_all_subordinates(self) -> None:
        tree = _build_platoon()
        subs = tree.get_all_subordinates("plt")
        assert len(subs) == 9  # 3 squads + 6 fire teams

    def test_all_subordinates_squad(self) -> None:
        tree = _build_platoon()
        subs = tree.get_all_subordinates("squad-0")
        assert set(subs) == {"ft-0-0", "ft-0-1"}

    def test_siblings(self) -> None:
        tree = _build_platoon()
        sibs = tree.get_siblings("squad-1")
        assert set(sibs) == {"squad-0", "squad-2"}

    def test_siblings_root(self) -> None:
        tree = _build_platoon()
        assert tree.get_siblings("plt") == []

    def test_units_at_echelon(self) -> None:
        tree = _build_platoon()
        squads = tree.get_units_at_echelon(EchelonLevel.SQUAD)
        assert len(squads) == 3
        fts = tree.get_units_at_echelon(EchelonLevel.FIRE_TEAM)
        assert len(fts) == 6

    def test_contains(self) -> None:
        tree = _build_platoon()
        assert "plt" in tree
        assert "nonexistent" not in tree

    def test_len(self) -> None:
        tree = _build_platoon()
        assert len(tree) == 10  # 1 plt + 3 squads + 6 fire teams


class TestHierarchyState:
    def test_roundtrip(self) -> None:
        original = _build_platoon()
        state = original.get_state()

        restored = HierarchyTree()
        restored.set_state(state)

        assert len(restored) == len(original)
        assert restored.get_parent("squad-0") == "plt"
        assert set(restored.get_children("squad-1")) == set(
            original.get_children("squad-1")
        )
        chain = restored.get_chain_of_command("ft-2-1")
        assert chain == ["plt", "squad-2", "ft-2-1"]

    def test_roundtrip_preserves_echelon(self) -> None:
        original = _build_platoon()
        state = original.get_state()
        restored = HierarchyTree()
        restored.set_state(state)
        assert restored.get_node("plt").echelon == EchelonLevel.PLATOON
        assert restored.get_node("squad-0").echelon == EchelonLevel.SQUAD
