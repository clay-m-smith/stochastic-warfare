"""Typed construction boundary for production simulation runtimes.

The boundary in this module deliberately owns the pieces that used to be
reimplemented by analysis, API, MCP, validation, and benchmark consumers:
source configuration preparation, effective calibration variants, roster
preflight, victory construction, and fresh ``SimulationEngine`` sessions.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import stat
import subprocess
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from stochastic_warfare.build_identity import (
    BUILD_IDENTITY_RELATIVE_PATH,
    BuildIdentityError,
    load_verified_build_identity,
)
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import BattleConfig
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.engine import (
    EngineConfig,
    SimulationEngine,
    SimulationRunResult,
)
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    DoctrineSideAssignment,
    ScenarioLoader,
    SimulationContext,
    load_campaign_scenario_config,
    parse_campaign_scenario_config,
)
from stochastic_warfare.simulation.victory import (
    ObjectiveState,
    VictoryEvaluator,
)


class AnalysisInputError(ValueError):
    """User-authored analysis input is invalid before execution."""


def _json_value(value: Any) -> Any:
    """Return one strict canonical-JSON-compatible public value."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(nested) for nested in value]
    if isinstance(value, (set, frozenset)):
        return [_json_value(nested) for nested in sorted(value, key=str)]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _canonical_digest(value: Any) -> str:
    """Return a deterministic SHA-256 for one public typed value."""
    encoded = json.dumps(
        _json_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CodeRevision:
    """Exact repository identity without inventing cleanliness."""

    commit: str
    dirty: bool
    worktree_fingerprint: str


@dataclass(frozen=True)
class UnitCommandAssignment:
    """One exact runtime unit's profile and doctrinal-school assignment."""

    unit_id: str
    side: str
    commander_profile_id: str | None
    doctrine_school_id: str | None


@dataclass(frozen=True)
class RuntimeProvenance:
    """Production-derived static and arrival-aware runtime provenance."""

    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    doctrine_assignment_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    final_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitCommandAssignment, ...]
    arriving_unit_assignments: tuple[UnitCommandAssignment, ...]


def _run_git(repo: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    ).stdout


def _untracked_entry_identity(
    repo: Path,
    relative: str,
) -> dict[str, Any]:
    """Identify an untracked regular file without following indirection."""
    path = repo / relative
    metadata = path.lstat()
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    mode = "100755" if metadata.st_mode & executable_bits else "100644"
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(
            f"worktree provenance does not permit symlinks: {relative!r}",
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"untracked provenance entry must be a regular file: {relative!r}",
        )

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    size = 0
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_metadata.st_mode)
            or opened_metadata.st_dev != metadata.st_dev
            or opened_metadata.st_ino != metadata.st_ino
        ):
            raise ValueError(
                f"untracked provenance entry changed during capture: {relative!r}",
            )
        while payload := os.read(descriptor, 1024 * 1024):
            digest.update(payload)
            size += len(payload)
    finally:
        os.close(descriptor)
    return {
        "path": relative,
        "kind": "regular",
        "mode": mode,
        "size": size,
        "sha256": digest.hexdigest(),
    }


def _reject_special_worktree_entries(repo: Path) -> None:
    """Reject filesystem entries Git cannot safely include in status output."""
    ignored_directories = {
        item.decode("utf-8").rstrip("/")
        for item in _run_git(
            repo,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
        ).split(b"\0")
        if item
    }
    for directory, child_directories, filenames in os.walk(
        repo,
        followlinks=False,
    ):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(repo)
        retained_directories: list[str] = []
        for child_name in child_directories:
            child_path = directory_path / child_name
            relative = (relative_directory / child_name).as_posix()
            if relative == ".git" or relative in ignored_directories:
                continue
            metadata = child_path.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                retained_directories.append(child_name)
            elif stat.S_ISLNK(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance does not permit symlinks: {relative!r}",
                )
            else:
                raise ValueError(
                    f"worktree provenance entry must be a directory: {relative!r}",
                )
        child_directories[:] = retained_directories

        for filename in filenames:
            path = directory_path / filename
            relative = (relative_directory / filename).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance does not permit symlinks: {relative!r}",
                )
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"worktree provenance entry must be a regular file: {relative!r}",
                )


def _has_git_control_marker(start: Path) -> bool:
    """Report whether ``start`` is below an explicit Git worktree marker."""
    candidate = start.absolute()
    if candidate.is_file():
        candidate = candidate.parent
    try:
        start_device = candidate.stat().st_dev
    except OSError as exc:
        raise RuntimeError(
            "Authoritative analysis cannot inspect its source location",
        ) from exc
    cross_filesystems = os.environ.get(
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "",
    ).lower() not in {"", "0", "false", "no"}
    for directory in (candidate, *candidate.parents):
        try:
            directory_device = directory.stat().st_dev
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect Git worktree ancestry",
            ) from exc
        if not cross_filesystems and directory_device != start_device:
            break
        marker = directory / ".git"
        try:
            marker.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect Git worktree metadata",
            ) from exc
        else:
            return True

        # A packaged identity defines the application-root ceiling for Git
        # marker discovery. Git still wins at or below that root, but an
        # unrelated corrupt marker in a parent deployment directory cannot
        # reclassify the verified nested package as its worktree.
        identity_marker = directory / BUILD_IDENTITY_RELATIVE_PATH
        try:
            identity_marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError(
                "Authoritative analysis cannot inspect build identity metadata",
            ) from exc
        return False
    return False


def _discover_git_worktree(start: Path) -> Path | None:
    """Return the Git root, falling back only when no worktree can exist."""
    try:
        root_payload = _run_git(start, "rev-parse", "--show-toplevel")
    except FileNotFoundError as exc:
        if _has_git_control_marker(start):
            raise RuntimeError(
                "Authoritative analysis requires Git to verify this worktree",
            ) from exc
        return None
    except subprocess.CalledProcessError as exc:
        if _has_git_control_marker(start):
            raise RuntimeError(
                "Authoritative analysis cannot verify this Git worktree",
            ) from exc
        return None
    except OSError as exc:
        raise RuntimeError(
            "Authoritative analysis cannot execute Git provenance capture",
        ) from exc
    try:
        decoded_root = root_payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "Authoritative analysis received invalid Git worktree metadata",
        ) from exc
    if not decoded_root:
        raise RuntimeError(
            "Authoritative analysis received an empty Git worktree root",
        )
    return Path(decoded_root).resolve()


def _resolve_git_code_revision(repo: Path) -> CodeRevision:
    """Resolve the existing content-sensitive Git worktree identity."""
    try:
        commit = _run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        _reject_special_worktree_entries(repo)
        status = _run_git(
            repo,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        dirty = bool(status)
        if not dirty:
            worktree_fingerprint = _canonical_digest(
                {"commit": commit, "dirty": False},
            )
        else:
            tracked_diff = _run_git(
                repo,
                "diff",
                "--binary",
                "--full-index",
                "HEAD",
                "--",
            )
            untracked_raw = _run_git(
                repo,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            )
            untracked_manifest = []
            for raw_relative in sorted(item for item in untracked_raw.split(b"\0") if item):
                relative = raw_relative.decode("utf-8")
                untracked_manifest.append(
                    _untracked_entry_identity(repo, relative),
                )
            worktree_fingerprint = _canonical_digest(
                {
                    "commit": commit,
                    "dirty": True,
                    "status_sha256": hashlib.sha256(status).hexdigest(),
                    "tracked_diff_sha256": hashlib.sha256(
                        tracked_diff,
                    ).hexdigest(),
                    "untracked": untracked_manifest,
                },
            )
        return CodeRevision(
            commit=commit,
            dirty=dirty,
            worktree_fingerprint=worktree_fingerprint,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeDecodeError,
    ) as exc:
        raise RuntimeError(
            "Authoritative analysis requires a verifiable Git code revision",
        ) from exc


def _resolve_code_revision(start: Path) -> CodeRevision:
    """Resolve strict Git provenance or a verified immutable-build identity."""
    repo = _discover_git_worktree(start)
    if repo is not None:
        return _resolve_git_code_revision(repo)

    try:
        identity = load_verified_build_identity(start)
    except (BuildIdentityError, OSError) as exc:
        raise RuntimeError(
            "Authoritative analysis requires a verifiable Git code revision "
            "or verified immutable build identity",
        ) from exc
    return CodeRevision(
        commit=identity.commit,
        dirty=False,
        worktree_fingerprint=_canonical_digest(
            {
                "kind": "immutable-build",
                "commit": identity.commit,
                "source_manifest_sha256": (
                    identity.source_manifest_sha256
                ),
            },
        ),
    )


def _data_tree_revision(
    data_root: Path,
    *,
    excluded_relative_paths: tuple[str, ...] = (),
) -> tuple[str, int]:
    """Fingerprint authored inputs while excluding known derived runtime state."""
    runtime_outputs = {
        "api_runs.db",
        "api_runs.db-journal",
        "api_runs.db-shm",
        "api_runs.db-wal",
    }
    runtime_output_directories = {
        "terrain_cache",
    }
    excluded = runtime_outputs | set(excluded_relative_paths)
    manifest: list[dict[str, Any]] = []
    for path in sorted(
        candidate
        for candidate in data_root.rglob("*")
        if candidate.is_file()
    ):
        relative = path.relative_to(data_root).as_posix()
        if relative in excluded or any(
            relative.startswith(f"{directory}/")
            for directory in runtime_output_directories
        ):
            continue
        payload = path.read_bytes()
        manifest.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    if not manifest:
        raise ValueError(f"data_root contains no files: {data_root}")
    return _canonical_digest(manifest), len(manifest)


def _definition_map(loader: Any) -> dict[str, Any]:
    definitions = loader.definitions()
    return {key: _json_value(definition) for key, definition in sorted(definitions.items())}


def _resolved_catalog_revision(context: SimulationContext) -> str:
    """Fingerprint the actual effective catalogs published by the loader."""
    signature_profiles = {
        profile_id: _json_value(context.sig_loader.get_profile(profile_id))
        for profile_id in context.sig_loader.available_profiles()
    }
    supply_items = {
        item_id: _json_value(
            context.supply_item_loader.get_definition(item_id),
        )
        for item_id in context.supply_item_loader.available_items()
    }
    school_catalog = context.school_registry.get_state()["schools"] if context.school_registry is not None else {}
    return _canonical_digest(
        {
            "units": _definition_map(context.unit_loader),
            "weapons": _definition_map(context.weapon_loader),
            "ammunition": _definition_map(context.ammo_loader),
            "sensors": _definition_map(context.sensor_loader),
            "signatures": signature_profiles,
            "supply_items": supply_items,
            "commander_profiles": _definition_map(
                context.commander_profile_loader,
            ),
            "doctrine_schools": school_catalog,
            "era": _json_value(context.era_config),
            "loadout_builder": (context.loadout_builder.fingerprint() if context.loadout_builder is not None else None),
        },
    )


def _runtime_unit_assignments(
    context: SimulationContext,
) -> tuple[UnitCommandAssignment, ...]:
    units = {
        unit.entity_id: (
            side,
            unit,
        )
        for side in sorted(context.units_by_side)
        for unit in context.units_by_side[side]
    }
    profile_assignments = dict(context.commander_engine.assignments()) if context.commander_engine is not None else {}
    if context.commander_engine is not None and (set(profile_assignments) != set(units)):
        raise RuntimeError(
            "Commander assignment topology does not match the runtime roster",
        )
    school_assignments = (
        context.school_registry.get_state()["unit_assignments"] if context.school_registry is not None else {}
    )
    unknown_school_units = set(school_assignments) - set(units)
    if unknown_school_units:
        raise RuntimeError(
            f"Doctrine assignment topology contains unknown runtime units: {sorted(unknown_school_units)!r}",
        )
    return tuple(
        UnitCommandAssignment(
            unit_id=unit_id,
            side=units[unit_id][0],
            commander_profile_id=profile_assignments.get(unit_id),
            doctrine_school_id=school_assignments.get(unit_id),
        )
        for unit_id in sorted(units)
    )


def _roster_loadout_fingerprint(context: SimulationContext) -> str:
    topology_keys = set(context.equipment_resolutions)
    unit_ids = {unit.entity_id for units in context.units_by_side.values() for unit in units}
    if topology_keys != unit_ids:
        raise RuntimeError(
            "Loadout topology does not match the exact runtime roster",
        )
    roster_loadout = [
        {
            "side": side,
            "unit_id": unit.entity_id,
            "definition_id": unit.unit_type,
            "position": list(unit.position),
            "loadout": [resolution.topology() for resolution in context.equipment_resolutions[unit.entity_id]],
        }
        for side in sorted(context.units_by_side)
        for unit in sorted(
            context.units_by_side[side],
            key=lambda candidate: candidate.entity_id,
        )
    ]
    return _canonical_digest(roster_loadout)


def _assert_finite(value: Any, *, path: str) -> None:
    """Reject non-finite numbers anywhere in an analysis-owned payload."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _assert_finite(nested, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_finite(nested, path=f"{path}[{index}]")


def _strict_calibration_patch(value: Any) -> CalibrationSchema:
    """Validate a sparse calibration patch without inventing defaults."""
    if isinstance(value, CalibrationSchema):
        raw = value.to_sparse_patch(mode="python")
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise ValueError("calibration_patch must be a mapping")
    _assert_finite(raw, path="calibration_patch")
    return CalibrationSchema.model_validate(raw, strict=True)


class DoctrineAnalysisVariant(BaseModel):
    """Ordered, duplicate-safe per-side school policy for one variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assignments: tuple[DoctrineSideAssignment, ...] = Field(min_length=1)

    @field_validator("assignments", mode="before")
    @classmethod
    def _ordered_assignments(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise ValueError(
                "doctrine assignments must be an ordered list or tuple",
            )
        return value

    @model_validator(mode="after")
    def _unique_sides(self) -> DoctrineAnalysisVariant:
        sides = [assignment.side for assignment in self.assignments]
        if len(sides) != len(set(sides)):
            raise ValueError(
                f"doctrine assignment sides must be unique: {sides!r}",
            )
        return self


class AnalysisVariant(BaseModel):
    """One independently applied sparse calibration variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str
    calibration_patch: CalibrationSchema = Field(
        default_factory=CalibrationSchema,
    )
    doctrine_variant: DoctrineAnalysisVariant | None = None

    @field_validator("variant_id", mode="before")
    @classmethod
    def _valid_variant_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("variant_id must be a non-empty trimmed string")
        return value

    @field_validator("calibration_patch", mode="before")
    @classmethod
    def _valid_patch(cls, value: Any) -> CalibrationSchema:
        return _strict_calibration_patch(value)


@dataclass(frozen=True)
class PreparedVariant:
    """One immutable effective configuration prepared from the same source."""

    variant_id: str
    config_json: str
    config_fingerprint: str
    doctrine_side_assignments: tuple[DoctrineSideAssignment, ...]

    @property
    def config(self) -> CampaignScenarioConfig:
        """Return a fresh typed copy of the effective configuration."""
        return CampaignScenarioConfig.model_validate_json(self.config_json)


@dataclass(frozen=True)
class RuntimeSession:
    """Fresh production runtime for one variant/seed pair."""

    variant_id: str
    seed: int
    max_ticks: int
    context: SimulationContext
    victory_evaluator: VictoryEvaluator
    engine: SimulationEngine
    recorder: SimulationRecorder | None
    source_fingerprint: str
    config_fingerprint: str
    authored_roster: tuple[tuple[str, int], ...]
    loaded_roster: tuple[tuple[str, int], ...]
    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    catalog_revision: str
    doctrine_catalog_fingerprint: str
    loaded_roster_loadout_fingerprint: str
    initial_unit_assignments: tuple[UnitCommandAssignment, ...]

    def run_to_completion(self) -> SimulationRunResult:
        """Run the production engine and return its public terminal result."""
        result = self.engine.run()
        if not result.victory_result.game_over:
            raise RuntimeError(
                "Simulation ended without a public terminal victory result",
            )
        return result

    def step(self) -> bool:
        """Advance one production tick and report public terminal state."""
        return self.engine.step()

    def finalize(self) -> SimulationRunResult:
        """Return a result only after :meth:`step` reports termination."""
        return self.engine.finalize()

    def provenance(self) -> RuntimeProvenance:
        """Capture exact production assignments, including arrivals so far."""
        current_assignments = _runtime_unit_assignments(self.context)
        current_by_id = {assignment.unit_id: assignment for assignment in current_assignments}
        initial_ids = {assignment.unit_id for assignment in self.initial_unit_assignments}
        current_initial = tuple(
            current_by_id[assignment.unit_id]
            for assignment in self.initial_unit_assignments
            if assignment.unit_id in current_by_id
        )
        if current_initial != self.initial_unit_assignments:
            raise RuntimeError(
                "Initial profile or doctrine assignments changed during runtime execution",
            )
        arriving_assignments = tuple(
            assignment for assignment in current_assignments if assignment.unit_id not in initial_ids
        )
        return RuntimeProvenance(
            code_revision=self.code_revision,
            data_revision=self.data_revision,
            data_file_count=self.data_file_count,
            catalog_revision=self.catalog_revision,
            doctrine_catalog_fingerprint=(self.doctrine_catalog_fingerprint),
            doctrine_assignment_fingerprint=_canonical_digest(
                current_assignments,
            ),
            loaded_roster_loadout_fingerprint=(self.loaded_roster_loadout_fingerprint),
            final_roster_loadout_fingerprint=(_roster_loadout_fingerprint(self.context)),
            initial_unit_assignments=self.initial_unit_assignments,
            arriving_unit_assignments=arriving_assignments,
        )


@dataclass(frozen=True)
class PreparedScenario:
    """Source-once scenario preparation and its independent variants."""

    scenario_path: Path
    data_root: Path
    source_config_json: str
    source_fingerprint: str
    variants: tuple[PreparedVariant, ...]
    authored_roster: tuple[tuple[str, int], ...]
    code_revision: CodeRevision
    data_revision: str
    data_file_count: int
    data_revision_exclusions: tuple[str, ...]

    @property
    def source_config(self) -> CampaignScenarioConfig:
        """Return a fresh typed copy of the validated source configuration."""
        return CampaignScenarioConfig.model_validate_json(
            self.source_config_json,
        )

    @property
    def side_ids(self) -> tuple[str, ...]:
        """Return exact authored side IDs in source order."""
        return tuple(side for side, _ in self.authored_roster)

    def variant(self, variant_id: str) -> PreparedVariant:
        """Resolve a variant by exact ID."""
        for variant in self.variants:
            if variant.variant_id == variant_id:
                return variant
        raise ValueError(f"Unknown analysis variant {variant_id!r}")

    def _assert_source_identity(self, *, stage: str) -> None:
        """Reject a runtime assembled from sources unlike its preparation."""
        current_data_revision, current_data_file_count = _data_tree_revision(
            self.data_root,
            excluded_relative_paths=self.data_revision_exclusions,
        )
        current_code_revision = _resolve_code_revision(self.data_root)
        if current_data_revision != self.data_revision or current_data_file_count != self.data_file_count:
            raise RuntimeError(
                f"Prepared scenario data changed {stage}: "
                f"prepared=({self.data_revision!r}, "
                f"{self.data_file_count}), "
                f"current=({current_data_revision!r}, "
                f"{current_data_file_count})",
            )
        if current_code_revision != self.code_revision:
            raise RuntimeError(
                f"Prepared scenario code changed {stage}: "
                f"prepared={self.code_revision!r}, "
                f"current={current_code_revision!r}",
            )

    def build(
        self,
        variant: str | PreparedVariant,
        seed: int,
        max_ticks: int,
        recorder: SimulationRecorder | None = None,
        *,
        record_events: bool = False,
        recorder_factory: (Callable[[SimulationContext], SimulationRecorder] | None) = None,
        engine_config: EngineConfig | None = None,
        campaign_config: CampaignConfig | None = None,
        battle_config: BattleConfig | None = None,
        strict_mode: bool = False,
    ) -> RuntimeSession:
        """Construct a fresh, independently revalidated production runtime."""
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed must be a non-negative strict integer")
        if not isinstance(max_ticks, int) or isinstance(max_ticks, bool) or max_ticks <= 0:
            raise ValueError("max_ticks must be a positive strict integer")

        selected = self.variant(variant) if isinstance(variant, str) else variant
        if not any(selected is prepared_variant for prepared_variant in self.variants):
            raise ValueError(
                "PreparedVariant does not belong to this PreparedScenario",
            )

        self._assert_source_identity(stage="before runtime construction")
        effective = CampaignScenarioConfig.model_validate(
            selected.config.model_dump(mode="python"),
        )
        context = ScenarioLoader(self.data_root).load(
            self.scenario_path,
            seed=seed,
            scenario_config=effective,
            doctrine_side_assignments=(selected.doctrine_side_assignments),
        )
        loaded_side_ids = tuple(context.units_by_side)
        if loaded_side_ids != self.side_ids:
            raise RuntimeError(
                "Loaded side topology does not match authored topology: "
                f"authored={self.side_ids!r}, loaded={loaded_side_ids!r}",
            )
        loaded_roster = tuple((side, len(context.units_by_side.get(side, ()))) for side, _ in self.authored_roster)
        if loaded_roster != self.authored_roster:
            raise RuntimeError(
                "Loaded roster does not match authored roster: "
                f"authored={self.authored_roster!r}, "
                f"loaded={loaded_roster!r}",
            )
        loaded_ids = [unit.entity_id for side in self.side_ids for unit in context.units_by_side[side]]
        if len(loaded_ids) != len(set(loaded_ids)):
            raise RuntimeError("Loaded roster contains duplicate unit IDs")
        initial_unit_assignments = _runtime_unit_assignments(context)
        loaded_roster_loadout_fingerprint = _roster_loadout_fingerprint(context)
        catalog_revision = _resolved_catalog_revision(context)
        doctrine_catalog_fingerprint = _canonical_digest(
            (context.school_registry.get_state()["schools"] if context.school_registry is not None else {}),
        )

        objectives = [
            ObjectiveState(
                objective_id=objective.objective_id,
                position=Position(
                    easting=objective.position[0],
                    northing=objective.position[1],
                    altitude=(objective.position[2] if len(objective.position) == 3 else 0.0),
                ),
                radius_m=objective.radius_m,
            )
            for objective in effective.objectives
        ]
        victory_evaluator = VictoryEvaluator(
            objectives=objectives,
            conditions=list(effective.victory_conditions),
            event_bus=context.event_bus,
            max_duration_s=effective.duration_hours * 3600.0,
        )
        recorder_modes = sum(
            (
                recorder is not None,
                record_events,
                recorder_factory is not None,
            ),
        )
        if recorder_modes > 1:
            raise ValueError(
                "recorder, record_events, and recorder_factory are mutually exclusive",
            )
        runtime_recorder = (
            SimulationRecorder(context.event_bus)
            if record_events
            else (recorder_factory(context) if recorder_factory is not None else recorder)
        )
        runtime_engine_config = (
            EngineConfig.model_validate(
                engine_config.model_dump(mode="python"),
            )
            if engine_config is not None
            else EngineConfig(max_ticks=max_ticks)
        )
        if runtime_engine_config.max_ticks != max_ticks:
            raise ValueError(
                "engine_config.max_ticks must equal the runtime max_ticks",
            )
        engine = SimulationEngine(
            context,
            config=runtime_engine_config,
            campaign_config=(
                CampaignConfig.model_validate(
                    campaign_config.model_dump(mode="python"),
                )
                if campaign_config is not None
                else None
            ),
            battle_config=(
                BattleConfig.model_validate(
                    battle_config.model_dump(mode="python"),
                )
                if battle_config is not None
                else None
            ),
            victory_evaluator=victory_evaluator,
            recorder=runtime_recorder,
            strict_mode=strict_mode,
        )
        self._assert_source_identity(stage="during runtime construction")
        return RuntimeSession(
            variant_id=selected.variant_id,
            seed=seed,
            max_ticks=max_ticks,
            context=context,
            victory_evaluator=victory_evaluator,
            engine=engine,
            recorder=runtime_recorder,
            source_fingerprint=self.source_fingerprint,
            config_fingerprint=selected.config_fingerprint,
            authored_roster=self.authored_roster,
            loaded_roster=loaded_roster,
            code_revision=self.code_revision,
            data_revision=self.data_revision,
            data_file_count=self.data_file_count,
            catalog_revision=catalog_revision,
            doctrine_catalog_fingerprint=doctrine_catalog_fingerprint,
            loaded_roster_loadout_fingerprint=(loaded_roster_loadout_fingerprint),
            initial_unit_assignments=initial_unit_assignments,
        )


class SimulationRuntimeFactory:
    """Authoritative constructor for consumers claiming production execution."""

    @staticmethod
    def _resolve_data_root(
        scenario_path: Path,
        data_root: str | Path | None,
    ) -> Path:
        if data_root is not None:
            resolved = Path(data_root).resolve()
            if not resolved.is_dir():
                raise ValueError(
                    f"data_root is not a directory: {resolved}",
                )
            return resolved
        for parent in scenario_path.parents:
            if parent.name == "scenarios":
                if parent.parent.parent.name == "eras":
                    return parent.parent.parent.parent.resolve()
                return parent.parent.resolve()
        raise AnalysisInputError(
            "Cannot infer data_root from a scenario outside a scenarios directory; pass data_root explicitly",
        )

    def prepare(
        self,
        path: str | Path,
        data_root: str | Path | None,
        variants: Sequence[AnalysisVariant],
    ) -> PreparedScenario:
        """Read a source once and prepare independent typed variants."""
        scenario_path = Path(path).resolve()
        if not scenario_path.is_file():
            raise FileNotFoundError(scenario_path)

        source_bytes = scenario_path.read_bytes()
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Scenario source is not valid UTF-8: {scenario_path}",
            ) from exc
        try:
            raw = load_yaml_unique(io.StringIO(source_text))
            source_config = parse_campaign_scenario_config(raw)
        except (TypeError, ValueError) as exc:
            raise AnalysisInputError(
                f"Invalid scenario source {scenario_path}: {exc}",
            ) from exc
        return self._prepare_config(
            scenario_path=scenario_path,
            source_data_path=scenario_path,
            data_root=self._resolve_data_root(scenario_path, data_root),
            source_config=source_config,
            source_fingerprint=hashlib.sha256(source_bytes).hexdigest(),
            variants=variants,
        )

    def prepare_config(
        self,
        source_config: CampaignScenarioConfig,
        data_root: str | Path,
        variants: Sequence[AnalysisVariant],
        *,
        source_label: str = "<typed-config>",
    ) -> PreparedScenario:
        """Prepare a typed source without a temporary serialization path."""
        if not isinstance(source_config, CampaignScenarioConfig):
            raise TypeError(
                "source_config must be a CampaignScenarioConfig",
            )
        if not isinstance(source_label, str) or not source_label or source_label != source_label.strip():
            raise ValueError(
                "source_label must be a non-empty trimmed string",
            )
        resolved_data_root = Path(data_root).resolve()
        if not resolved_data_root.is_dir():
            raise ValueError(
                f"data_root is not a directory: {resolved_data_root}",
            )
        copied_source = CampaignScenarioConfig.model_validate(
            source_config.model_dump(mode="python"),
        )
        return self._prepare_config(
            scenario_path=Path(source_label),
            source_data_path=None,
            data_root=resolved_data_root,
            source_config=copied_source,
            source_fingerprint=_canonical_digest(
                copied_source.model_dump(mode="json"),
            ),
            variants=variants,
        )

    def _prepare_config(
        self,
        *,
        scenario_path: Path,
        source_data_path: Path | None,
        data_root: Path,
        source_config: CampaignScenarioConfig,
        source_fingerprint: str,
        variants: Sequence[AnalysisVariant],
    ) -> PreparedScenario:
        """Share strict source preparation across file and typed inputs."""
        if not variants:
            raise AnalysisInputError(
                "At least one analysis variant is required",
            )
        if any(not isinstance(variant, AnalysisVariant) for variant in variants):
            raise TypeError("variants must contain only AnalysisVariant values")
        variant_ids = [variant.variant_id for variant in variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise AnalysisInputError(
                f"Analysis variant IDs must be unique: {variant_ids!r}",
            )

        authored_roster = tuple(
            (
                side.side,
                sum(unit.count for unit in side.units),
            )
            for side in source_config.sides
        )
        empty_sides = [side for side, authored_count in authored_roster if authored_count <= 0]
        if empty_sides:
            raise AnalysisInputError(
                f"Authored roster is empty for sides: {empty_sides!r}",
            )

        authored_sides = {side for side, _ in authored_roster}
        doctrine_variants = [variant.doctrine_variant for variant in variants if variant.doctrine_variant is not None]
        if doctrine_variants:
            from stochastic_warfare.c2.ai.schools import SchoolLoader

            school_loader = SchoolLoader(data_root / "schools")
            school_loader.load_all()
            available_schools = set(school_loader.available_schools())
            for doctrine_variant in doctrine_variants:
                if doctrine_variant is None:
                    continue
                assignment_sides = {assignment.side for assignment in doctrine_variant.assignments}
                unknown_sides = sorted(
                    assignment_sides - authored_sides,
                )
                if unknown_sides:
                    raise AnalysisInputError(
                        f"Doctrine variant references unknown scenario sides: {unknown_sides!r}",
                    )
                unknown_schools = sorted(
                    {assignment.school_id for assignment in doctrine_variant.assignments} - available_schools
                )
                if unknown_schools:
                    raise AnalysisInputError(
                        f"Doctrine variant references unknown schools: {unknown_schools!r}",
                    )

        data_revision_exclusions: tuple[str, ...] = ()
        if source_data_path is not None:
            try:
                source_relative = source_data_path.relative_to(data_root)
            except ValueError:
                pass
            else:
                data_revision_exclusions = (source_relative.as_posix(),)
        data_revision, data_file_count = _data_tree_revision(
            data_root,
            excluded_relative_paths=data_revision_exclusions,
        )
        prepared_variants: list[PreparedVariant] = []
        for variant in variants:
            patch = variant.calibration_patch.to_sparse_patch(
                mode="python",
            )
            effective = load_campaign_scenario_config(
                None,
                patch,
                source_config=source_config,
            )
            doctrine_side_assignments = (
                variant.doctrine_variant.assignments if variant.doctrine_variant is not None else ()
            )
            prepared_variants.append(
                PreparedVariant(
                    variant_id=variant.variant_id,
                    config_json=effective.model_dump_json(),
                    config_fingerprint=_canonical_digest(
                        {
                            "scenario_config": effective.model_dump(
                                mode="json",
                            ),
                            "doctrine_side_assignments": (doctrine_side_assignments),
                        },
                    ),
                    doctrine_side_assignments=doctrine_side_assignments,
                ),
            )

        return PreparedScenario(
            scenario_path=scenario_path,
            data_root=data_root,
            source_config_json=source_config.model_dump_json(),
            source_fingerprint=source_fingerprint,
            variants=tuple(prepared_variants),
            authored_roster=authored_roster,
            code_revision=_resolve_code_revision(data_root),
            data_revision=data_revision,
            data_file_count=data_file_count,
            data_revision_exclusions=data_revision_exclusions,
        )
