#!/usr/bin/env python3
"""Validate scenario and unit data integrity.

Checks that all unit YAML files and scenario YAML files are internally
consistent and will load correctly through ScenarioLoader with armed and
sensored units.

Usage:
    uv run python scripts/validate_scenario_data.py                  # all
    uv run python scripts/validate_scenario_data.py --units-only     # units
    uv run python scripts/validate_scenario_data.py --scenarios-only # scenarios
    uv run python scripts/validate_scenario_data.py --file path.yaml # single file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Import the canonical maps from the engine
sys.path.insert(0, str(PROJECT_ROOT))
from stochastic_warfare.validation.scenario_runner import (  # noqa: E402
    _SENSOR_NAME_MAP,
    _WEAPON_NAME_MAP,
)


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
        with open(path) as f:
            raw = yaml.safe_load(f)
        if isinstance(raw, dict) and "unit_type" in raw:
            types.add(raw["unit_type"])
    return types


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def validate_unit_yaml(path: Path) -> ValidationResult:
    """Validate a single unit YAML file for equipment mapping issues."""
    result = ValidationResult()
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        result.errors.append(f"{path}: not a valid YAML dict")
        return result

    equipment = raw.get("equipment", [])
    if not isinstance(equipment, list):
        result.errors.append(f"{path}: 'equipment' is not a list")
        return result

    has_sensor = False
    has_weapon = False
    valid_categories = {
        "WEAPON", "SENSOR", "PROPULSION", "PROTECTION",
        "COMMUNICATION", "NAVIGATION", "UTILITY", "POWER",
    }

    for entry in equipment:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        category = entry.get("category", "")

        # Check category is valid
        if category and category not in valid_categories:
            result.errors.append(
                f"{path}: equipment '{name}' has invalid category '{category}' "
                f"(valid: {', '.join(sorted(valid_categories))})"
            )

        if category == "WEAPON":
            has_weapon = True
            if name and name not in _WEAPON_NAME_MAP:
                result.errors.append(
                    f"{path}: WEAPON equipment '{name}' not in _WEAPON_NAME_MAP — "
                    "add mapping to scenario_runner.py"
                )

        if category == "SENSOR":
            has_sensor = True
            if name and name not in _SENSOR_NAME_MAP:
                result.errors.append(
                    f"{path}: SENSOR equipment '{name}' not in _SENSOR_NAME_MAP — "
                    "add mapping to scenario_runner.py"
                )

    if not has_sensor:
        result.warnings.append(
            f"{path}: no SENSOR equipment entry — units of this type will have "
            "no sensors. Add a default sensor (e.g., 'Mk 1 Eyeball' or "
            "'Field Binoculars') if appropriate."
        )

    return result


def validate_scenario_yaml(path: Path, known_types: set[str]) -> ValidationResult:
    """Validate a scenario YAML for unit type references and structure."""
    result = ValidationResult()
    with open(path) as f:
        raw = yaml.safe_load(f)

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
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        return result
    required = ("sides", "date", "duration_hours", "terrain")
    if not all(k in raw for k in required):
        return result  # Not a loadable scenario

    try:
        from stochastic_warfare.simulation.scenario import ScenarioLoader
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
    parser.add_argument("--file", type=Path, help="Check a single YAML file")
    parser.add_argument("--no-load", action="store_true", help="Skip ScenarioLoader load test")
    parser.add_argument("--quiet", action="store_true", help="Only show errors")
    args = parser.parse_args()

    total_errors = 0
    total_warnings = 0

    if args.file:
        # Single file mode
        p = args.file.resolve()
        if "scenario" in p.name:
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
        return 0 if r.ok else 1

    # Unit validation
    if not args.scenarios_only:
        unit_paths = _collect_unit_yamls()
        print(f"Checking {len(unit_paths)} unit YAML files...")
        for path in unit_paths:
            r = validate_unit_yaml(path)
            total_errors += len(r.errors)
            total_warnings += len(r.warnings)
            for e in r.errors:
                print(f"  ERROR: {e}")
            for w in r.warnings:
                if not args.quiet:
                    print(f"  WARN:  {w}")

    # Scenario validation
    if not args.units_only:
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
    print(f"\nResults: {total_errors} errors, {total_warnings} warnings")
    if total_errors > 0:
        print("FAILED — fix errors above before committing")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
