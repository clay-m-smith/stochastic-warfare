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

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stochastic_warfare.c2.ai.schools.base import DoctrinalSchool, SchoolDefinition
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# School Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchoolAssignmentPlan:
    """Validated deterministic school-assignment state."""

    assignments: tuple[tuple[str, str], ...]


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
        plan = self.prepare_assignments({unit_id: school_id})
        self.commit_assignments(plan)

    def prepare_assignments(
        self,
        assignments: Mapping[str, str],
        *,
        expected_unit_ids: set[str] | None = None,
    ) -> SchoolAssignmentPlan:
        """Validate assignment updates without mutating registry state."""
        staged: list[tuple[str, str]] = []
        for unit_id, school_id in sorted(assignments.items()):
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError(
                    "School assignment unit IDs must be non-empty strings",
                )
            if (
                expected_unit_ids is not None
                and unit_id not in expected_unit_ids
            ):
                raise ValueError(
                    f"School assignment references unknown unit {unit_id!r}",
                )
            if school_id not in self._schools:
                raise KeyError(f"School {school_id!r} not registered")
            staged.append((unit_id, school_id))
        return SchoolAssignmentPlan(tuple(staged))

    def commit_assignments(
        self,
        plan: SchoolAssignmentPlan,
        *,
        replace: bool = False,
    ) -> None:
        """Commit a validated school assignment plan."""
        assignments = {} if replace else dict(self._unit_assignments)
        assignments.update(plan.assignments)
        self._unit_assignments = assignments

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
                for sid, s in sorted(self._schools.items())
            },
            "unit_assignments": dict(
                sorted(self._unit_assignments.items()),
            ),
        }

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_unit_ids: set[str] | None = None,
    ) -> SchoolAssignmentPlan:
        """Validate checkpoint state without mutating the live registry.

        Schools must already be registered by the scenario loader.
        """
        if set(state) != {"schools", "unit_assignments"}:
            raise ValueError(
                "School checkpoint state must contain schools and "
                "unit_assignments",
            )
        expected_schools = {
            school_id: school.definition.model_dump()
            for school_id, school in sorted(self._schools.items())
        }
        if state["schools"] != expected_schools:
            raise ValueError(
                "School checkpoint catalog does not match the runtime",
            )
        raw_assignments = state["unit_assignments"]
        if not isinstance(raw_assignments, Mapping):
            raise ValueError(
                "School checkpoint assignments must be a mapping",
            )
        return self.prepare_assignments(
            raw_assignments,
            expected_unit_ids=expected_unit_ids,
        )

    def commit_state(self, plan: SchoolAssignmentPlan) -> None:
        """Replace live assignment state from a validated checkpoint plan."""
        self.commit_assignments(plan, replace=True)

    def set_state(self, state: Mapping[str, Any]) -> None:
        """Restore independently validated assignment state."""
        self.commit_state(self.stage_state(state))


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


# ---------------------------------------------------------------------------
# School factory
# ---------------------------------------------------------------------------


def _build_school_class_map() -> dict[str, type[DoctrinalSchool]]:
    """Lazily import all school subclasses and build the ID→class mapping."""
    from stochastic_warfare.c2.ai.schools.clausewitzian import ClausewitzianSchool
    from stochastic_warfare.c2.ai.schools.maneuverist import ManeuveristSchool
    from stochastic_warfare.c2.ai.schools.attrition import AttritionSchool
    from stochastic_warfare.c2.ai.schools.airland_battle import AirLandBattleSchool
    from stochastic_warfare.c2.ai.schools.air_power import AirPowerSchool
    from stochastic_warfare.c2.ai.schools.sun_tzu import SunTzuSchool
    from stochastic_warfare.c2.ai.schools.deep_battle import DeepBattleSchool
    from stochastic_warfare.c2.ai.schools.maritime import MahanianSchool, CorbettianSchool

    return {
        "clausewitzian": ClausewitzianSchool,
        "maneuverist": ManeuveristSchool,
        "attrition": AttritionSchool,
        "airland_battle": AirLandBattleSchool,
        "air_power": AirPowerSchool,
        "sun_tzu": SunTzuSchool,
        "deep_battle": DeepBattleSchool,
        "maritime_mahanian": MahanianSchool,
        "maritime_corbettian": CorbettianSchool,
    }


_SCHOOL_ID_TO_CLASS: dict[str, type[DoctrinalSchool]] | None = None


def create_school(definition: SchoolDefinition) -> DoctrinalSchool:
    """Factory: create correct school subclass from a definition.

    Raises
    ------
    KeyError
        If *definition.school_id* is not a recognised school.
    """
    global _SCHOOL_ID_TO_CLASS
    if _SCHOOL_ID_TO_CLASS is None:
        _SCHOOL_ID_TO_CLASS = _build_school_class_map()
    cls = _SCHOOL_ID_TO_CLASS.get(definition.school_id)
    if cls is None:
        raise KeyError(f"Unknown school_id: {definition.school_id!r}")
    return cls(definition)
