"""Phase 69d — Command hierarchy enforcement tests."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.c2.command import CommandConfig, CommandEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import TaskOrgManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rng():
    return np.random.Generator(np.random.PCG64(42))


def _build_two_side_hierarchy():
    """Build a hierarchy with 2 sides, virtual HQs, and subordinates."""
    hierarchy = HierarchyTree()
    # Blue side
    hierarchy.add_unit("blue_hq", EchelonLevel.DIVISION, side="blue")
    hierarchy.add_unit("blue_infantry", EchelonLevel.COMPANY, parent_id="blue_hq", side="blue")
    hierarchy.add_unit("blue_armor", EchelonLevel.COMPANY, parent_id="blue_hq", side="blue")
    # Red side
    hierarchy.add_unit("red_hq", EchelonLevel.DIVISION, side="red")
    hierarchy.add_unit("red_infantry", EchelonLevel.COMPANY, parent_id="red_hq", side="red")
    return hierarchy


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHierarchyBuilding:
    """Phase 69d: hierarchy from scenario unit structure."""

    def test_virtual_hq_per_side(self):
        """Each side gets a virtual HQ node."""
        hierarchy = _build_two_side_hierarchy()
        assert hierarchy.get_node("blue_hq").echelon == EchelonLevel.DIVISION
        assert hierarchy.get_node("red_hq").echelon == EchelonLevel.DIVISION

    def test_units_under_side_hq(self):
        """All units are children of their side's HQ."""
        hierarchy = _build_two_side_hierarchy()
        blue_children = hierarchy.get_children("blue_hq")
        assert "blue_infantry" in blue_children
        assert "blue_armor" in blue_children
        red_children = hierarchy.get_children("red_hq")
        assert "red_infantry" in red_children


class TestAuthorityCheck:
    """Phase 69d: CommandEngine authority enforcement."""

    def _make_engine(self):
        hierarchy = _build_two_side_hierarchy()
        task_org = TaskOrgManager(hierarchy)
        engine = CommandEngine(hierarchy, task_org, {}, EventBus(), _rng(), CommandConfig())
        # Register units
        for uid in ["blue_hq", "blue_infantry", "blue_armor", "red_hq", "red_infantry"]:
            engine.register_unit(uid, uid)
        return engine

    def test_hq_to_subordinate_passes(self):
        """HQ can issue order to its subordinate."""
        engine = self._make_engine()
        assert engine.can_issue_order("blue_hq", "blue_infantry") is True

    def test_peer_cannot_issue_to_peer(self):
        """Peer unit cannot issue orders to another peer."""
        engine = self._make_engine()
        assert engine.can_issue_order("blue_infantry", "blue_armor") is False

    def test_self_order_passes(self):
        """Unit can issue order to itself (same CoC)."""
        engine = self._make_engine()
        # Self is in own chain of command
        assert engine.can_issue_order("blue_infantry", "blue_infantry") is True

    def test_cross_side_order_rejected(self):
        """Orders across sides are rejected."""
        engine = self._make_engine()
        assert engine.can_issue_order("blue_hq", "red_infantry") is False


class TestCalibrationGate:
    """Phase 69d: enable_command_hierarchy flag gating."""

    def test_flag_default_false(self):
        """Default flag is False."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema()
        assert cal.enable_command_hierarchy is False

    def test_flag_enabled(self):
        """Flag can be set to True."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(enable_command_hierarchy=True)
        assert cal.enable_command_hierarchy is True
