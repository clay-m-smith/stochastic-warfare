#!/usr/bin/env python3
"""Validate scenario and unit data integrity.

Checks that all unit YAML files and scenario YAML files are internally
consistent.  Unit equipment is preflighted through the same typed
``RuntimeLoadoutBuilder`` and mapping registry used by ``ScenarioLoader``;
scenario files are loaded through ``ScenarioLoader`` itself.

Usage:
    uv run python scripts/validate_scenario_data.py                  # all
    uv run python scripts/validate_scenario_data.py --units-only     # units
    uv run python scripts/validate_scenario_data.py --scenarios-only # scenarios
    uv run python scripts/validate_scenario_data.py --space-only     # space
    uv run python scripts/validate_scenario_data.py --file path.yaml # single file
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(PROJECT_ROOT))
from stochastic_warfare.core.era import get_era_config  # noqa: E402
from stochastic_warfare.core.strict_yaml import load_yaml_unique  # noqa: E402
from stochastic_warfare.entities.equipment import EquipmentCategory  # noqa: E402
from stochastic_warfare.entities.loader import (  # noqa: E402
    SensorPolicy,
    UnitDefinition,
    UnitLoader,
)
from stochastic_warfare.simulation.equipment_mappings import (  # noqa: E402
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.loadouts import (  # noqa: E402
    EquipmentMappingError,
    EquipmentMappingRegistry,
    RuntimeLoadoutBuilder,
)
from stochastic_warfare.simulation.scenario import (  # noqa: E402
    ScenarioLoader,
)
from stochastic_warfare.space.catalog import (  # noqa: E402
    SpaceCatalog,
    validate_asat_weapon_file,
    validate_constellation_file,
)

_ERA_NAMES = (
    "modern",
    "ancient_medieval",
    "napoleonic",
    "ww1",
    "ww2",
)

type EquipmentMappingKey = tuple[EquipmentCategory, str]


def _collect_unit_yamls() -> list[Path]:
    """Find all unit YAML files across base and era directories."""
    paths: list[Path] = []
    # Base units
    base_units = DATA_DIR / "units"
    if base_units.is_dir():
        paths.extend(base_units.rglob("*.yaml"))
    # Era units
    eras_dir = DATA_DIR / "eras"
    if eras_dir.is_dir():
        for era in eras_dir.iterdir():
            era_units = era / "units"
            if era_units.is_dir():
                paths.extend(era_units.rglob("*.yaml"))
    return sorted(paths)


def _collect_scenario_yamls() -> list[Path]:
    """Find all scenario.yaml files."""
    paths: list[Path] = []
    for scenario_yaml in DATA_DIR.rglob("scenario.yaml"):
        paths.append(scenario_yaml)
    return sorted(paths)


def _known_unit_types() -> set[str]:
    """Collect all unit_type values from unit YAML files."""
    types: set[str] = set()
    for path in _collect_unit_yamls():
        with open(path, encoding="utf-8") as unit_file:
            raw = load_yaml_unique(unit_file)
        if isinstance(raw, dict) and "unit_type" in raw:
            types.add(raw["unit_type"])
    return types


@dataclass(frozen=True, slots=True)
class MappingCoverageStats:
    """Exact distinct-key coverage for the full authored unit catalog."""

    authored_keys: int = 0
    registry_keys: int = 0
    covered_keys: int = 0
    unmapped_authored_keys: int = 0
    stale_registry_keys: int = 0


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    classifications: list[str] = field(default_factory=list)
    mapping_coverage: MappingCoverageStats | None = None

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass(frozen=True, slots=True)
class CatalogValidationStats:
    """Exact unit-catalog coverage and typed sensor-policy counts."""

    units: int = 0
    authored_mapping_entries: int = 0
    distinct_authored_mapping_keys: int = 0
    sensor_required: int = 0
    sensor_intentionally_none: int = 0


@dataclass(frozen=True, slots=True)
class SpaceCatalogValidationStats:
    """Exact strict space-catalog definition counts."""

    constellations: int = 0
    asat_weapons: int = 0


def _unit_catalog_dir(era: str) -> Path:
    if era == "modern":
        return DATA_DIR / "units"
    return DATA_DIR / "eras" / era / "units"


def _era_for_unit_path(path: Path) -> str:
    """Return the effective production era for a repository unit file."""
    try:
        relative = path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError as exc:
        raise ValueError(
            f"{path}: unit file is outside the repository data catalog",
        ) from exc
    parts = relative.parts
    if len(parts) >= 2 and parts[0] == "units":
        return "modern"
    if (
        len(parts) >= 4
        and parts[0] == "eras"
        and parts[2] == "units"
        and parts[1] in _ERA_NAMES
    ):
        return parts[1]
    raise ValueError(
        f"{path}: expected a unit file below data/units or "
        "data/eras/<era>/units",
    )


def _authored_mapping_keys(
    definitions: dict[str, UnitDefinition],
) -> set[EquipmentMappingKey]:
    keys: set[EquipmentMappingKey] = set()
    for definition in definitions.values():
        for equipment in definition.equipment:
            try:
                category = EquipmentCategory[equipment.category.upper()]
            except KeyError:
                # RuntimeLoadoutBuilder provides the contextual validation error.
                continue
            if category in (EquipmentCategory.WEAPON, EquipmentCategory.SENSOR):
                keys.add((category, equipment.name))
    return keys


def _authored_mapping_entry_count(
    definitions: dict[str, UnitDefinition],
) -> int:
    """Count authored occurrences without misreporting them as distinct keys."""
    return sum(
        1
        for definition in definitions.values()
        for equipment in definition.equipment
        if equipment.category.upper() in {"WEAPON", "SENSOR"}
    )


def _registry_mapping_keys(
    registry: EquipmentMappingRegistry,
) -> set[EquipmentMappingKey]:
    return {
        (record.category, record.equipment_name)
        for record in registry.records
        if record.category in (
            EquipmentCategory.WEAPON,
            EquipmentCategory.SENSOR,
        )
    }


def _mapping_key_label(key: EquipmentMappingKey) -> str:
    category, equipment_name = key
    return f"({category.name}, {equipment_name!r})"


def compare_equipment_mapping_coverage(
    authored_keys: set[EquipmentMappingKey],
    *,
    registry: EquipmentMappingRegistry | None = None,
) -> tuple[ValidationResult, MappingCoverageStats]:
    """Compare distinct full-catalog keys with the production registry."""
    effective_registry = (
        EQUIPMENT_MAPPING_REGISTRY
        if registry is None
        else registry
    )
    registry_keys = _registry_mapping_keys(effective_registry)
    unmapped_authored = sorted(
        authored_keys - registry_keys,
        key=lambda key: (key[0].name, key[1]),
    )
    stale_registry = sorted(
        registry_keys - authored_keys,
        key=lambda key: (key[0].name, key[1]),
    )
    covered = authored_keys & registry_keys

    stats = MappingCoverageStats(
        authored_keys=len(authored_keys),
        registry_keys=len(registry_keys),
        covered_keys=len(covered),
        unmapped_authored_keys=len(unmapped_authored),
        stale_registry_keys=len(stale_registry),
    )
    result = ValidationResult(mapping_coverage=stats)
    result.errors.extend(
        "Full-catalog equipment coverage: authored key "
        f"{_mapping_key_label(key)} has no registry declaration"
        for key in unmapped_authored
    )
    result.errors.extend(
        "Full-catalog equipment coverage: stale registry key "
        f"{_mapping_key_label(key)} is not authored by any unit catalog"
        for key in stale_registry
    )
    return result, stats


def _effective_loaders(era: str) -> dict[str, Any]:
    """Use the production loader composition for one effective era catalog."""
    return ScenarioLoader(DATA_DIR)._create_loaders(era=era)


def _build_catalog_boundary(
    *,
    era: str,
    definitions: dict[str, UnitDefinition],
    loaders: dict[str, Any],
) -> RuntimeLoadoutBuilder:
    return RuntimeLoadoutBuilder(
        weapon_loader=loaders["weapon_loader"],
        ammo_loader=loaders["ammo_loader"],
        sensor_loader=loaders["sensor_loader"],
        unit_definitions=definitions,
        era_config=get_era_config(era),
        assignment_overrides={},
        reachable_unit_types=tuple(sorted(definitions)),
        registry=EQUIPMENT_MAPPING_REGISTRY,
    )


def _sensor_policy_result(
    *,
    era: str,
    definitions: dict[str, UnitDefinition],
) -> tuple[ValidationResult, CatalogValidationStats]:
    result = ValidationResult()
    required = 0
    intentionally_none = 0
    for unit_type, definition in sorted(definitions.items()):
        if definition.sensor_policy is SensorPolicy.REQUIRED:
            required += 1
        elif definition.sensor_policy is SensorPolicy.INTENTIONALLY_NONE:
            intentionally_none += 1
            result.classifications.append(
                f"{era}/{unit_type}: sensor_policy='intentionally_none' — "
                f"{definition.sensor_policy_reason}",
            )
        else:  # pragma: no cover - Pydantic owns the closed enum
            result.errors.append(
                f"{era}/{unit_type}: unknown sensor policy "
                f"{definition.sensor_policy!r}",
            )
    return result, CatalogValidationStats(
        units=len(definitions),
        authored_mapping_entries=_authored_mapping_entry_count(definitions),
        distinct_authored_mapping_keys=len(_authored_mapping_keys(definitions)),
        sensor_required=required,
        sensor_intentionally_none=intentionally_none,
    )


def _preflight_catalog(
    *,
    era: str,
    definitions: dict[str, UnitDefinition],
    loaders: dict[str, Any],
) -> ValidationResult:
    """Preflight one catalog, retaining per-unit context if the batch fails."""
    result = ValidationResult()
    try:
        _build_catalog_boundary(
            era=era,
            definitions=definitions,
            loaders=loaders,
        )
        return result
    except (EquipmentMappingError, TypeError, ValueError) as batch_error:
        per_unit_errors = 0
        for unit_type in sorted(definitions):
            try:
                _build_catalog_boundary(
                    era=era,
                    definitions={unit_type: definitions[unit_type]},
                    loaders=loaders,
                )
            except (EquipmentMappingError, TypeError, ValueError) as unit_error:
                result.errors.append(
                    f"{era}/{unit_type}: RuntimeLoadoutBuilder preflight "
                    f"failed: {unit_error}",
                )
                per_unit_errors += 1
        if per_unit_errors == 0:
            result.errors.append(
                f"{era}: RuntimeLoadoutBuilder batch preflight failed: "
                f"{batch_error}",
            )
    return result


def _validate_unit_catalog(
    era: str,
    *,
    unit_file: Path | None = None,
) -> tuple[
    ValidationResult,
    CatalogValidationStats,
    dict[str, UnitDefinition] | None,
]:
    """Validate one era's unit definitions through the production boundary."""
    result = ValidationResult()
    if era not in _ERA_NAMES:
        result.errors.append(f"Unknown unit catalog era {era!r}")
        return result, CatalogValidationStats(), None

    try:
        unit_loader = UnitLoader(_unit_catalog_dir(era))
        if unit_file is None:
            unit_loader.load_all()
        else:
            unit_loader.load_definition(unit_file)
        definitions = dict(unit_loader.definitions())
        loaders = _effective_loaders(era)
    except (OSError, TypeError, ValueError) as exc:
        subject = unit_file if unit_file is not None else _unit_catalog_dir(era)
        result.errors.append(f"{subject}: typed catalog loading failed: {exc}")
        return result, CatalogValidationStats(), None

    policy_result, stats = _sensor_policy_result(
        era=era,
        definitions=definitions,
    )
    result.errors.extend(policy_result.errors)
    result.classifications.extend(policy_result.classifications)
    preflight_result = _preflight_catalog(
        era=era,
        definitions=definitions,
        loaders=loaders,
    )
    result.errors.extend(preflight_result.errors)
    return result, stats, definitions


def validate_unit_catalog(
    era: str,
    *,
    unit_file: Path | None = None,
) -> tuple[ValidationResult, CatalogValidationStats]:
    """Validate one era, without unrelated full-registry stale-key checks."""
    result, stats, _ = _validate_unit_catalog(era, unit_file=unit_file)
    return result, stats


def validate_unit_catalogs() -> tuple[
    ValidationResult,
    dict[str, CatalogValidationStats],
]:
    """Validate all 184 unit definitions in their effective era envelopes."""
    combined = ValidationResult()
    stats_by_era: dict[str, CatalogValidationStats] = {}
    authored_keys: set[EquipmentMappingKey] = set()
    coverage_complete = True
    for era in _ERA_NAMES:
        result, stats, definitions = _validate_unit_catalog(era)
        stats_by_era[era] = stats
        combined.errors.extend(result.errors)
        combined.warnings.extend(result.warnings)
        combined.classifications.extend(result.classifications)
        if definitions is None:
            coverage_complete = False
        else:
            authored_keys.update(_authored_mapping_keys(definitions))
    if coverage_complete:
        coverage_result, coverage_stats = compare_equipment_mapping_coverage(
            authored_keys,
        )
        combined.errors.extend(coverage_result.errors)
        combined.mapping_coverage = coverage_stats
    return combined, stats_by_era


def validate_unit_yaml(path: Path) -> ValidationResult:
    """Validate one unit definition through its effective production boundary."""
    try:
        era = _era_for_unit_path(path)
    except ValueError as exc:
        return ValidationResult(errors=[str(exc)])
    result, _ = validate_unit_catalog(era, unit_file=path)
    return result


def validate_space_catalogs() -> tuple[
    ValidationResult,
    SpaceCatalogValidationStats,
]:
    """Validate all space catalogs through the production catalog boundary."""
    try:
        catalog = SpaceCatalog.load(DATA_DIR)
    except (OSError, TypeError, ValueError) as exc:
        return (
            ValidationResult(
                errors=[f"Space catalog production loading failed: {exc}"],
            ),
            SpaceCatalogValidationStats(),
        )
    return (
        ValidationResult(),
        SpaceCatalogValidationStats(
            constellations=len(catalog.constellations),
            asat_weapons=len(catalog.weapons),
        ),
    )


def validate_space_yaml(path: Path) -> ValidationResult:
    """Validate one space definition with its exact strict schema."""
    try:
        if path.parent.name == "constellations":
            validate_constellation_file(path)
        elif path.parent.name == "asat_weapons":
            validate_asat_weapon_file(path)
        else:
            raise ValueError(
                f"{path}: expected data/space/constellations or "
                "data/space/asat_weapons",
            )
    except (OSError, TypeError, ValueError) as exc:
        return ValidationResult(errors=[str(exc)])
    return ValidationResult()


def validate_scenario_yaml(path: Path, known_types: set[str]) -> ValidationResult:
    """Validate a scenario YAML for unit type references and structure."""
    result = ValidationResult()
    with open(path, encoding="utf-8") as scenario_file:
        raw = load_yaml_unique(scenario_file)

    if not isinstance(raw, dict):
        result.errors.append(f"{path}: not a valid YAML dict")
        return result

    sides = raw.get("sides", [])
    if not isinstance(sides, list):
        return result  # Not a campaign-format scenario

    for side_entry in sides:
        if not isinstance(side_entry, dict):
            continue
        side_name = side_entry.get("side", "?")
        units = side_entry.get("units", [])
        if not isinstance(units, list):
            continue
        for unit_entry in units:
            if not isinstance(unit_entry, dict):
                continue
            unit_type = unit_entry.get("unit_type", "")
            if unit_type and unit_type not in known_types:
                result.errors.append(
                    f"{path}: side '{side_name}' references unit_type "
                    f"'{unit_type}' which does not exist in any unit YAML"
                )

    return result


def validate_scenario_loads(path: Path) -> ValidationResult:
    """Try loading a scenario through ScenarioLoader and check armed/sensored."""
    result = ValidationResult()

    # Only attempt load on campaign-format scenarios
    with open(path, encoding="utf-8") as scenario_file:
        raw = load_yaml_unique(scenario_file)
    if not isinstance(raw, dict):
        return result
    required = ("sides", "date", "duration_hours", "terrain")
    if not all(k in raw for k in required):
        return result  # Not a loadable scenario

    try:
        loader = ScenarioLoader(DATA_DIR)
        ctx = loader.load(path, seed=42)

        # Check units exist
        for side, units in ctx.units_by_side.items():
            if len(units) == 0:
                result.errors.append(
                    f"{path}: side '{side}' has 0 units after loading"
                )

        # Check weapons
        all_weapons = sum(
            len(ctx.unit_weapons.get(u.entity_id, []))
            for units in ctx.units_by_side.values()
            for u in units
        )
        if all_weapons == 0:
            result.errors.append(f"{path}: no units have weapons after loading")

        # Check sensors
        all_sensors = sum(
            len(ctx.unit_sensors.get(u.entity_id, []))
            for units in ctx.units_by_side.values()
            for u in units
        )
        if all_sensors == 0:
            result.errors.append(f"{path}: no units have sensors after loading")

    except Exception as e:
        result.errors.append(f"{path}: ScenarioLoader.load() failed: {e}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate scenario/unit data integrity")
    parser.add_argument("--units-only", action="store_true", help="Only check unit YAMLs")
    parser.add_argument("--scenarios-only", action="store_true", help="Only check scenario YAMLs")
    parser.add_argument("--space-only", action="store_true", help="Only check space YAMLs")
    parser.add_argument("--file", type=Path, help="Check a single YAML file")
    parser.add_argument("--no-load", action="store_true", help="Skip ScenarioLoader load test")
    parser.add_argument("--quiet", action="store_true", help="Only show errors")
    args = parser.parse_args()
    if sum((args.units_only, args.scenarios_only, args.space_only)) > 1:
        parser.error(
            "--units-only, --scenarios-only, and --space-only are mutually "
            "exclusive",
        )

    total_errors = 0
    total_warnings = 0
    total_classifications = 0

    if args.file:
        # Single file mode
        p = args.file.resolve()
        if p.parent.name in {"constellations", "asat_weapons"}:
            r = validate_space_yaml(p)
        elif "scenario" in p.name:
            known = _known_unit_types()
            r = validate_scenario_yaml(p, known)
            if not args.no_load:
                r2 = validate_scenario_loads(p)
                r.errors.extend(r2.errors)
                r.warnings.extend(r2.warnings)
        else:
            r = validate_unit_yaml(p)
        for e in r.errors:
            print(f"  ERROR: {e}")
        for w in r.warnings:
            if not args.quiet:
                print(f"  WARN:  {w}")
        for classification in r.classifications:
            if not args.quiet:
                print(f"  CLASSIFIED: {classification}")
        return 0 if r.ok else 1

    # Unit validation
    if not args.scenarios_only and not args.space_only:
        unit_paths = _collect_unit_yamls()
        print(
            f"Checking {len(unit_paths)} unit YAML files through the "
            "production RuntimeLoadoutBuilder...",
        )
        r, stats_by_era = validate_unit_catalogs()
        total_errors += len(r.errors)
        total_warnings += len(r.warnings)
        total_classifications += len(r.classifications)
        for era, stats in stats_by_era.items():
            print(
                f"  {era}: {stats.units} units, "
                f"{stats.authored_mapping_entries} authored WEAPON/SENSOR "
                f"occurrences ({stats.distinct_authored_mapping_keys} "
                "distinct keys), "
                f"{stats.sensor_required} sensor-required, "
                f"{stats.sensor_intentionally_none} intentionally sensorless",
            )
        if r.mapping_coverage is not None:
            coverage = r.mapping_coverage
            print(
                "  Full-catalog registry coverage: "
                f"{coverage.covered_keys}/{coverage.authored_keys} authored "
                f"keys covered by {coverage.registry_keys} registry keys; "
                f"{coverage.unmapped_authored_keys} unmapped, "
                f"{coverage.stale_registry_keys} stale",
            )
        for error in r.errors:
            print(f"  ERROR: {error}")
        for warning in r.warnings:
            if not args.quiet:
                print(f"  WARN:  {warning}")
        for classification in r.classifications:
            if not args.quiet:
                print(f"  CLASSIFIED: {classification}")

    # Space catalog validation
    if args.space_only or not (args.units_only or args.scenarios_only):
        print(
            "Checking space YAML files through the production SpaceCatalog...",
        )
        r, space_stats = validate_space_catalogs()
        total_errors += len(r.errors)
        total_warnings += len(r.warnings)
        print(
            f"  {space_stats.constellations} constellation definitions, "
            f"{space_stats.asat_weapons} ASAT weapon definitions",
        )
        for error in r.errors:
            print(f"  ERROR: {error}")
        for warning in r.warnings:
            if not args.quiet:
                print(f"  WARN:  {warning}")

    # Scenario validation
    if not args.units_only and not args.space_only:
        known = _known_unit_types()
        scenario_paths = _collect_scenario_yamls()
        print(f"Checking {len(scenario_paths)} scenario YAML files...")
        for path in scenario_paths:
            r = validate_scenario_yaml(path, known)
            total_errors += len(r.errors)
            total_warnings += len(r.warnings)
            for e in r.errors:
                print(f"  ERROR: {e}")
            for w in r.warnings:
                if not args.quiet:
                    print(f"  WARN:  {w}")

        if not args.no_load:
            print("Running ScenarioLoader load tests...")
            for path in scenario_paths:
                r = validate_scenario_loads(path)
                total_errors += len(r.errors)
                total_warnings += len(r.warnings)
                for e in r.errors:
                    print(f"  ERROR: {e}")

    # Summary
    print(
        "\nCatalog validation results: "
        f"{total_errors} errors, {total_warnings} warnings, "
        f"{total_classifications} explicit sensorless classifications",
    )
    if total_errors > 0:
        print("FAILED — fix errors above before committing")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
