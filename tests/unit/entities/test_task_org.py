"""Tests for entities/organization/task_org.py."""

import pytest

from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import (
    CommandRelationship,
    TaskOrgManager,
)


def _build_bn() -> HierarchyTree:
    """Build a battalion with 3 companies."""
    tree = HierarchyTree()
    tree.add_unit("bn", EchelonLevel.BATTALION)
    for i in range(3):
        tree.add_unit(f"co-{i}", EchelonLevel.COMPANY, parent_id="bn")
        for j in range(3):
            tree.add_unit(f"plt-{i}-{j}", EchelonLevel.PLATOON,
                          parent_id=f"co-{i}")
    return tree


class TestCommandRelationship:
    def test_values(self) -> None:
        assert CommandRelationship.ORGANIC == 0
        assert CommandRelationship.REINFORCING == 6

    def test_count(self) -> None:
        assert len(CommandRelationship) == 7


class TestAttach:
    def test_basic_attach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        a = mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        assert a.unit_id == "plt-0-0"
        assert a.original_parent == "co-0"
        assert a.current_parent == "co-1"
        assert a.relationship == int(CommandRelationship.OPCON)

    def test_attach_root_raises(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        with pytest.raises(ValueError):
            mgr.attach("bn", "co-0", CommandRelationship.OPCON)

    def test_effective_parent_after_attach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-2", CommandRelationship.TACON)
        assert mgr.get_effective_parent("plt-0-0") == "co-2"

    def test_organic_parent_unchanged(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        # The organic tree is unchanged
        assert tree.get_parent("plt-0-0") == "co-0"


class TestDetach:
    def test_detach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        mgr.detach("plt-0-0")
        assert mgr.get_effective_parent("plt-0-0") == "co-0"

    def test_detach_not_attached_raises(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        with pytest.raises(KeyError):
            mgr.detach("plt-0-0")


class TestEffectiveSubordinates:
    def test_without_task_org(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        subs = mgr.get_effective_subordinates("co-0")
        assert set(subs) == {"plt-0-0", "plt-0-1", "plt-0-2"}

    def test_unit_moved_away(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        subs = mgr.get_effective_subordinates("co-0")
        assert "plt-0-0" not in subs

    def test_unit_added(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        subs = mgr.get_effective_subordinates("co-1")
        assert "plt-0-0" in subs


class TestRelationship:
    def test_organic_default(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        assert mgr.get_relationship("plt-0-0") == CommandRelationship.ORGANIC

    def test_after_attach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.DIRECT_SUPPORT)
        assert mgr.get_relationship("plt-0-0") == CommandRelationship.DIRECT_SUPPORT

    def test_after_detach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        mgr.detach("plt-0-0")
        assert mgr.get_relationship("plt-0-0") == CommandRelationship.ORGANIC


class TestIsTaskOrganized:
    def test_false_by_default(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        assert not mgr.is_task_organized("plt-0-0")

    def test_true_after_attach(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        assert mgr.is_task_organized("plt-0-0")


class TestTaskOrgState:
    def test_roundtrip(self) -> None:
        tree = _build_bn()
        mgr = TaskOrgManager(tree)
        mgr.attach("plt-0-0", "co-1", CommandRelationship.OPCON)
        mgr.attach("plt-1-0", "co-2", CommandRelationship.TACON)

        state = mgr.get_state()
        restored = TaskOrgManager(tree)
        restored.set_state(state)

        assert restored.get_effective_parent("plt-0-0") == "co-1"
        assert restored.get_relationship("plt-1-0") == CommandRelationship.TACON
