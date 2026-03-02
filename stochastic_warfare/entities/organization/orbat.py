"""Order of Battle (ORBAT) loading from YAML TO&E definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree

logger = get_logger(__name__)


class TOEEntry(BaseModel):
    """One subordinate entry in a Table of Organization & Equipment."""

    unit_type: str
    count: int = 1
    echelon: str = "SQUAD"


class TOEDefinition(BaseModel):
    """Full Table of Organization & Equipment loaded from YAML."""

    name: str
    echelon: str
    nation: str = "US"
    era: str = "modern"
    subordinates: list[TOEEntry]
    staff: list[str] = []


class OrbatLoader:
    """Build a hierarchy from a YAML TO&E definition."""

    @staticmethod
    def load_toe(path: Path) -> TOEDefinition:
        """Load and validate a TO&E definition from YAML."""
        with open(path) as f:
            raw = yaml.safe_load(f)
        return TOEDefinition.model_validate(raw)

    @staticmethod
    def build_hierarchy(
        toe: TOEDefinition,
        unit_loader: UnitLoader,
        parent_id: str,
        side: str,
        rng: np.random.Generator,
        base_position: Position = Position(0.0, 0.0),
    ) -> HierarchyTree:
        """Create a HierarchyTree populated from *toe*.

        The parent unit is placed at echelon from *toe.echelon*.
        Subordinates are created via *unit_loader* and placed as children.
        """
        tree = HierarchyTree()
        echelon = EchelonLevel[toe.echelon.upper()]
        tree.add_unit(parent_id, echelon, parent_id=None, side=side)

        counter = 0
        for entry in toe.subordinates:
            sub_echelon = EchelonLevel[entry.echelon.upper()]
            for i in range(entry.count):
                uid = f"{parent_id}-{entry.unit_type}-{counter}"
                tree.add_unit(uid, sub_echelon, parent_id=parent_id, side=side)
                # Create the actual unit entity via loader
                unit_loader.create_unit(
                    entry.unit_type, uid, base_position, side, rng,
                )
                counter += 1

        logger.info("Built hierarchy for %s: %d units", toe.name, len(tree))
        return tree
