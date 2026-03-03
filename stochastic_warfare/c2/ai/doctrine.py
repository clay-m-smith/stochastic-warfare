"""Doctrinal template engine -- loads and applies military doctrine templates.

Doctrine templates define standard tactical approaches (attack, defend, delay,
etc.) with echelon-appropriate actions, phase sequences, and force allocation
ratios.  Templates are YAML-driven and faction-specific (US, Russian, NATO,
generic).
"""

from __future__ import annotations

import enum
from pathlib import Path

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DoctrineCategory(enum.IntEnum):
    """High-level doctrine classification."""

    OFFENSIVE = 0
    DEFENSIVE = 1
    RETROGRADE = 2
    STABILITY = 3
    ENABLING = 4


_CATEGORY_MAP: dict[str, DoctrineCategory] = {c.name: c for c in DoctrineCategory}


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class DoctrineTemplate(BaseModel):
    """A single doctrinal template loaded from YAML."""

    doctrine_id: str
    display_name: str
    category: str  # maps to DoctrineCategory via _CATEGORY_MAP
    faction: str  # "us", "russian", "nato", "generic"
    description: str
    min_echelon: int  # minimum EchelonLevel required
    max_echelon: int  # maximum EchelonLevel applicable
    applicable_domains: list[str]  # "LAND", "SEA", "AIR", etc.
    phases: list[str]  # standard phase sequence for this doctrine
    force_ratios: dict[str, float]  # e.g. {"main_effort": 0.6, ...}
    actions: list[str]  # available tactical actions
    priorities: list[str]  # priority order
    risk_tolerance: str  # "low", "moderate", "high"
    tempo: str  # "slow", "moderate", "high"

    @property
    def category_enum(self) -> DoctrineCategory:
        """Resolve string *category* to a :class:`DoctrineCategory` enum."""
        return _CATEGORY_MAP[self.category]


# ---------------------------------------------------------------------------
# YAML loader (follows standard project pattern)
# ---------------------------------------------------------------------------


class DoctrineTemplateLoader:
    """Load doctrine template definitions from YAML files.

    Parameters
    ----------
    data_dir : Path | None
        Directory containing YAML files.  Defaults to ``data/doctrine``
        relative to the project root.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            # c2/ai/doctrine.py -> parents[3] = project root
            data_dir = Path(__file__).resolve().parents[3] / "data" / "doctrine"
        self._data_dir = data_dir
        self._definitions: dict[str, DoctrineTemplate] = {}

    def load_definition(self, path: Path) -> DoctrineTemplate:
        """Load a single YAML file and register it."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = DoctrineTemplate.model_validate(data)
        self._definitions[defn.doctrine_id] = defn
        return defn

    def load_all(self) -> None:
        """Load all ``*.yaml`` files under the data directory (recursively)."""
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)

    def get_definition(self, doctrine_id: str) -> DoctrineTemplate:
        """Return a loaded template by *doctrine_id*.

        Raises
        ------
        KeyError
            If the requested id has not been loaded.
        """
        return self._definitions[doctrine_id]

    def all_definitions(self) -> list[DoctrineTemplate]:
        """Return all loaded templates (sorted by doctrine_id)."""
        return [self._definitions[k] for k in sorted(self._definitions)]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DoctrineEngine:
    """High-level queries over loaded doctrine templates.

    Parameters
    ----------
    loader : DoctrineTemplateLoader
        A loader that has already called :meth:`load_all` (or at least loaded
        the templates that should be considered).
    """

    def __init__(self, loader: DoctrineTemplateLoader) -> None:
        self._loader = loader

    # -- Lookup / matching --------------------------------------------------

    def get_applicable_doctrine(
        self,
        preferred_id: str | None,
        echelon: int,
        domain: str = "LAND",
    ) -> DoctrineTemplate | None:
        """Return the best-matching doctrine template.

        If *preferred_id* is supplied and the corresponding template exists
        **and** satisfies the echelon/domain constraints it is returned
        directly.  Otherwise the method scans all loaded templates and
        returns the first match (sorted by doctrine_id for determinism),
        or ``None`` when nothing fits.

        Parameters
        ----------
        preferred_id : str | None
            Explicit doctrine id requested by the commander.
        echelon : int
            Caller's echelon level (``EchelonLevel`` int value).
        domain : str
            Operating domain (``"LAND"``, ``"SEA"``, ``"AIR"``).
        """
        # Try preferred first
        if preferred_id is not None:
            try:
                tmpl = self._loader.get_definition(preferred_id)
                if self._matches(tmpl, echelon, domain):
                    return tmpl
            except KeyError:
                pass

        # Fallback: scan all loaded templates
        for tmpl in self._loader.all_definitions():
            if self._matches(tmpl, echelon, domain):
                return tmpl

        return None

    @staticmethod
    def _matches(tmpl: DoctrineTemplate, echelon: int, domain: str) -> bool:
        """Check whether *tmpl* is valid for *echelon* and *domain*."""
        if echelon < tmpl.min_echelon or echelon > tmpl.max_echelon:
            return False
        if domain not in tmpl.applicable_domains:
            return False
        return True

    # -- Action filtering ---------------------------------------------------

    def filter_actions(
        self,
        template: DoctrineTemplate,
        candidate_indices: list[int],
        action_names: list[str],
    ) -> list[int]:
        """Return only those candidate indices whose action is in the template.

        Parameters
        ----------
        template : DoctrineTemplate
            Active doctrine.
        candidate_indices : list[int]
            Indices into *action_names* to consider.
        action_names : list[str]
            Full list of action names (parallel to some external COA list).

        Returns
        -------
        list[int]
            Subset of *candidate_indices* whose corresponding action name
            appears in ``template.actions``.
        """
        allowed = frozenset(template.actions)
        return [i for i in candidate_indices if action_names[i] in allowed]

    # -- Force allocation ---------------------------------------------------

    def get_force_allocation(self, template: DoctrineTemplate) -> dict[str, float]:
        """Return the force-ratio dict from the template."""
        return dict(template.force_ratios)

    # -- Priority actions ---------------------------------------------------

    def get_priority_actions(
        self,
        template: DoctrineTemplate,
        n: int = 3,
    ) -> list[str]:
        """Return the first *n* priorities from the template."""
        return list(template.priorities[:n])
