"""Scenario and unit discovery helpers.

Scans both ``data/scenarios/`` and ``data/eras/*/scenarios/`` for scenario
YAML files.  Also scans ``data/units/`` and ``data/eras/*/units/`` for unit
definitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class _ScanCache:
    """Mtime-based filesystem scan cache."""

    def __init__(self) -> None:
        self._scenarios: list[dict[str, Any]] | None = None
        self._scenarios_mtime: float = 0.0
        self._units: list[dict[str, Any]] | None = None
        self._units_mtime: float = 0.0

    @staticmethod
    def _dir_mtime(*dirs: Path) -> float:
        max_mt = 0.0
        for d in dirs:
            if d.exists():
                try:
                    max_mt = max(max_mt, d.stat().st_mtime)
                except OSError:
                    pass
        return max_mt

    def get_scenarios(self, data_dir: Path) -> list[dict[str, Any]] | None:
        mt = self._dir_mtime(data_dir / "scenarios", data_dir / "eras")
        if self._scenarios is not None and mt == self._scenarios_mtime:
            return self._scenarios
        return None

    def set_scenarios(self, data_dir: Path, results: list[dict[str, Any]]) -> None:
        self._scenarios = results
        self._scenarios_mtime = self._dir_mtime(data_dir / "scenarios", data_dir / "eras")

    def get_units(self, data_dir: Path) -> list[dict[str, Any]] | None:
        mt = self._dir_mtime(data_dir / "units", data_dir / "eras")
        if self._units is not None and mt == self._units_mtime:
            return self._units
        return None

    def set_units(self, data_dir: Path, results: list[dict[str, Any]]) -> None:
        self._units = results
        self._units_mtime = self._dir_mtime(data_dir / "units", data_dir / "eras")


_cache = _ScanCache()


def invalidate_cache() -> None:
    """Reset scan cache. Used by tests."""
    global _cache
    _cache = _ScanCache()


def resolve_scenario(name: str, data_dir: Path) -> Path:
    """Find a scenario YAML by directory name.

    Searches base ``data/scenarios/{name}/`` first, then
    ``data/eras/*/scenarios/{name}/``.

    Raises ``FileNotFoundError`` if not found.
    """
    base = data_dir / "scenarios" / name / "scenario.yaml"
    if base.exists():
        return base
    eras_dir = data_dir / "eras"
    if eras_dir.exists():
        for era_dir in sorted(eras_dir.iterdir()):
            if era_dir.is_dir():
                era_path = era_dir / "scenarios" / name / "scenario.yaml"
                if era_path.exists():
                    return era_path
    raise FileNotFoundError(f"Scenario '{name}' not found")


def scan_scenarios(data_dir: Path) -> list[dict[str, Any]]:
    """Scan all scenario directories and load YAML headers.

    Returns list of dicts with keys: name, path, config (parsed YAML).
    Results are cached until the scenario directories' mtime changes.
    """
    cached = _cache.get_scenarios(data_dir)
    if cached is not None:
        return cached

    import yaml

    results: list[dict[str, Any]] = []

    # Base scenarios
    scenarios_dir = data_dir / "scenarios"
    if scenarios_dir.exists():
        for d in sorted(scenarios_dir.iterdir()):
            yaml_path = d / "scenario.yaml"
            if yaml_path.exists():
                try:
                    with open(yaml_path) as f:
                        cfg = yaml.safe_load(f)
                    results.append({"name": d.name, "path": str(yaml_path), "config": cfg})
                except Exception:
                    results.append({"name": d.name, "path": str(yaml_path), "config": {}})

    # Era scenarios
    eras_dir = data_dir / "eras"
    if eras_dir.exists():
        for era_dir in sorted(eras_dir.iterdir()):
            if not era_dir.is_dir():
                continue
            era_scenarios = era_dir / "scenarios"
            if not era_scenarios.exists():
                continue
            for d in sorted(era_scenarios.iterdir()):
                yaml_path = d / "scenario.yaml"
                if yaml_path.exists():
                    try:
                        with open(yaml_path) as f:
                            cfg = yaml.safe_load(f)
                        results.append({
                            "name": d.name,
                            "path": str(yaml_path),
                            "config": cfg,
                        })
                    except Exception:
                        results.append({"name": d.name, "path": str(yaml_path), "config": {}})

    _cache.set_scenarios(data_dir, results)
    return results


def scan_units(data_dir: Path) -> list[dict[str, Any]]:
    """Scan all unit YAML files and load definitions.

    Returns list of dicts with keys: unit_type, display_name, domain,
    category, era, max_speed, crew_size, path.
    Results are cached until the unit directories' mtime changes.
    """
    cached = _cache.get_units(data_dir)
    if cached is not None:
        return cached

    import yaml

    results: list[dict[str, Any]] = []

    def _scan_dir(units_dir: Path, era: str = "modern") -> None:
        if not units_dir.exists():
            return
        for yaml_file in sorted(units_dir.rglob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    defn = yaml.safe_load(f)
                if not isinstance(defn, dict):
                    continue
                cat = yaml_file.parent.name if yaml_file.parent != units_dir else ""
                results.append({
                    "unit_type": defn.get("unit_type", yaml_file.stem),
                    "display_name": defn.get("display_name", ""),
                    "domain": defn.get("domain", ""),
                    "category": cat,
                    "era": era,
                    "max_speed": defn.get("max_speed", 0),
                    "crew_size": len(defn.get("crew", [])),
                    "path": str(yaml_file),
                })
            except Exception:
                pass

    # Base units
    _scan_dir(data_dir / "units")

    # Era units
    eras_dir = data_dir / "eras"
    if eras_dir.exists():
        for era_dir in sorted(eras_dir.iterdir()):
            if era_dir.is_dir():
                _scan_dir(era_dir / "units", era=era_dir.name)

    _cache.set_units(data_dir, results)
    return results
