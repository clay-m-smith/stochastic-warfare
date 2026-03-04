"""Doctrinal AI schools — Strategy-pattern classes for AI decision-making.

Nine named schools representing distinct warfare philosophies:

- **Clausewitzian**: Center-of-gravity targeting, decisive engagement
- **Maneuverist**: Tempo-driven OODA, bypass strongpoints (Boyd)
- **Attrition**: Exchange ratio optimization, deliberate operations
- **AirLand Battle**: Simultaneous deep/close/rear operations
- **Air Power**: Five Rings strategic targeting (Warden)
- **Sun Tzu**: Intel-first, deception, opponent modeling
- **Deep Battle**: Echeloned assault, operational depth (Tukhachevsky)
- **Mahanian**: Fleet concentration, decisive naval battle
- **Corbettian**: Fleet-in-being, sea denial, selective engagement

Each school produces modifier dicts injected into existing engine methods
via optional parameters.  No engine subclassing or wrapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# School Registry
# ---------------------------------------------------------------------------


class SchoolRegistry:
    """Registry of doctrinal school instances.

    Stores instantiated :class:`DoctrinalSchool` objects and tracks
    unit-to-school assignments.  Follows the same pattern as
    :class:`~stochastic_warfare.cbrn.agents.AgentRegistry`.
    """

    def __init__(self) -> None:
        self._schools: dict[str, DoctrinalSchool] = {}
        self._unit_assignments: dict[str, str] = {}  # unit_id -> school_id

    def register(self, school: DoctrinalSchool) -> None:
        """Register a doctrinal school instance."""
        self._schools[school.school_id] = school
        logger.debug("Registered doctrinal school: %s", school.school_id)

    def get(self, school_id: str) -> DoctrinalSchool | None:
        """Look up a school by ID.  Returns ``None`` if not found."""
        return self._schools.get(school_id)

    def all_schools(self) -> list[DoctrinalSchool]:
        """Return all registered school instances."""
        return list(self._schools.values())

    def assign_to_unit(self, unit_id: str, school_id: str) -> None:
        """Assign a doctrinal school to a unit.

        Raises
        ------
        KeyError
            If *school_id* has not been registered.
        """
        if school_id not in self._schools:
            raise KeyError(f"School {school_id!r} not registered")
        self._unit_assignments[unit_id] = school_id

    def get_for_unit(self, unit_id: str) -> DoctrinalSchool | None:
        """Return the school assigned to *unit_id*, or ``None``."""
        school_id = self._unit_assignments.get(unit_id)
        if school_id is None:
            return None
        return self._schools.get(school_id)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Serialize for checkpoint/restore."""
        return {
            "schools": {
                sid: s.definition.model_dump()
                for sid, s in self._schools.items()
            },
            "unit_assignments": dict(self._unit_assignments),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore from checkpoint.

        Note: only restores unit assignments.  Schools must be
        re-registered by the loader before calling ``set_state``.
        """
        self._unit_assignments = dict(state.get("unit_assignments", {}))


# ---------------------------------------------------------------------------
# School Loader
# ---------------------------------------------------------------------------


class SchoolLoader:
    """YAML loader for doctrinal school definitions.

    Follows the :class:`~stochastic_warfare.c2.ai.doctrine.DoctrineTemplateLoader`
    pattern.

    Parameters
    ----------
    data_dir : Path | None
        Directory containing school YAML files.  Defaults to
        ``data/schools`` relative to the project root.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            # c2/ai/schools/__init__.py -> parents[4] = project root
            data_dir = Path(__file__).resolve().parents[4] / "data" / "schools"
        self._data_dir = data_dir
        self._definitions: dict[str, SchoolDefinition] = {}

    def load_definition(self, path: Path) -> SchoolDefinition:
        """Load a single school YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        defn = SchoolDefinition.model_validate(data)
        self._definitions[defn.school_id] = defn
        logger.debug("Loaded school definition: %s", defn.school_id)
        return defn

    def load_all(self) -> list[SchoolDefinition]:
        """Load all ``*.yaml`` files in the data directory.

        Returns
        -------
        list[SchoolDefinition]
            All loaded definitions.
        """
        for path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_definition(path)
        return list(self._definitions.values())

    def get_definition(self, school_id: str) -> SchoolDefinition:
        """Return a loaded definition by *school_id*.

        Raises
        ------
        KeyError
            If the requested id has not been loaded.
        """
        return self._definitions[school_id]

    def available_schools(self) -> list[str]:
        """Return all loaded school IDs."""
        return sorted(self._definitions.keys())
