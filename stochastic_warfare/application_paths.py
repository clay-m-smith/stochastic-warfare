"""Typed filesystem and package-resource ownership for the application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from importlib import resources
import os
from pathlib import Path
import stat
from typing import Mapping

from stochastic_warfare.scenario_names import validate_scenario_name


CATALOG_ROOT_ENV = "STOCHASTIC_WARFARE_DATA_ROOT"
DATABASE_PATH_ENV = "STOCHASTIC_WARFARE_DB_PATH"
FRONTEND_ROOT_ENV = "STOCHASTIC_WARFARE_FRONTEND_ROOT"
ARTIFACT_ROOT_ENV = "STOCHASTIC_WARFARE_ARTIFACT_ROOT"
STATE_ROOT_ENV = "STOCHASTIC_WARFARE_STATE_ROOT"

_REQUIRED_CATALOG_DIRECTORIES = (
    "ammunition",
    "cbrn",
    "commander_profiles",
    "comms",
    "doctrine",
    "eras",
    "escalation",
    "ew",
    "formations",
    "logistics",
    "logistics/supply_items",
    "organizations",
    "scenarios",
    "schools",
    "sensors",
    "signatures",
    "space",
    "units",
    "validation",
    "weapons",
)
_HISTORICAL_CLAIMS_RELATIVE_PATH = Path(
    "validation/historical_claims.yaml",
)


class ApplicationResourceError(RuntimeError):
    """A required application resource is unavailable or malformed."""


class ApplicationResourceMode(str, Enum):
    """How the immutable catalog was resolved."""

    CHECKOUT = "checkout"
    PACKAGE = "package"
    EXTERNAL = "external"


class HistoricalClaimAuditMode(str, Enum):
    """Which immutable-source surface a claim receipt may audit."""

    REPOSITORY = "repository"
    PACKAGE = "package"


@dataclass(frozen=True, slots=True)
class CatalogResourceFile:
    """One immutable catalog payload in canonical relative-path order."""

    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CatalogResourceDigest:
    """Digest and cardinality of the wheel-eligible catalog payload."""

    sha256: str
    file_count: int


def catalog_resource_manifest(
    catalog_root: str | Path,
) -> tuple[CatalogResourceFile, ...]:
    """Return the exact YAML catalog manifest used by the wheel build."""
    root = Path(catalog_root).resolve(strict=True)
    if not root.is_dir():
        raise ApplicationResourceError(
            f"catalog root is not a directory: {root}",
        )
    entries: list[CatalogResourceFile] = []
    for directory, child_directories, filenames in os.walk(
        root,
        followlinks=False,
    ):
        current = Path(directory)
        retained_directories: list[str] = []
        for child_name in sorted(child_directories):
            child = current / child_name
            metadata = child.lstat()
            relative = child.relative_to(root).as_posix()
            if stat.S_ISLNK(metadata.st_mode):
                raise ApplicationResourceError(
                    "catalog resources do not permit directory symlinks: "
                    f"{relative!r}",
                )
            if not stat.S_ISDIR(metadata.st_mode):
                raise ApplicationResourceError(
                    f"catalog resource entry is not a directory: {relative!r}",
                )
            if child_name != "terrain_cache":
                retained_directories.append(child_name)
        child_directories[:] = retained_directories

        for filename in sorted(filenames):
            if not filename.endswith(".yaml"):
                continue
            path = current / filename
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ApplicationResourceError(
                    f"catalog resources do not permit symlinks: {relative!r}",
                )
            if not stat.S_ISREG(metadata.st_mode):
                raise ApplicationResourceError(
                    f"catalog resource is not a regular file: {relative!r}",
                )
            payload = path.read_bytes()
            entries.append(
                CatalogResourceFile(
                    relative_path=relative,
                    size=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                ),
            )
    if not entries:
        raise ApplicationResourceError(
            f"catalog root contains no YAML resources: {root}",
        )
    return tuple(entries)


def catalog_resource_digest(
    catalog_root: str | Path,
) -> CatalogResourceDigest:
    """Return one canonical digest for the wheel-eligible catalog."""
    manifest = catalog_resource_manifest(catalog_root)
    digest = hashlib.sha256()
    for entry in manifest:
        digest.update(entry.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(entry.sha256.encode("ascii"))
        digest.update(b"\n")
    return CatalogResourceDigest(
        sha256=digest.hexdigest(),
        file_count=len(manifest),
    )


def _configured_path(
    explicit: str | Path | None,
    environment: Mapping[str, str],
    variable: str,
    *,
    relative_to: Path | None = None,
) -> Path | None:
    value = explicit if explicit is not None else environment.get(variable)
    if value is None:
        return None
    raw = os.fspath(value)
    if not raw or raw != raw.strip():
        raise ApplicationResourceError(
            f"{variable} must be a non-empty trimmed path",
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        if relative_to is None:
            raise ApplicationResourceError(
                f"{variable} must be an absolute path",
            )
        path = relative_to / path
    return path.resolve()


def _packaged_catalog() -> tuple[Path, Path] | None:
    resource_root = resources.files("stochastic_warfare.resources")
    catalog = resource_root.joinpath("data")
    if not catalog.is_dir():
        return None
    try:
        resource_path = Path(resource_root).resolve()
        catalog_path = Path(catalog).resolve()
    except TypeError as exc:
        raise ApplicationResourceError(
            "packaged catalog is not filesystem-backed; configure "
            f"{CATALOG_ROOT_ENV} with an extracted external catalog",
        ) from exc
    return resource_path, catalog_path


def _checkout_catalog() -> tuple[Path, Path] | None:
    application_root = Path(__file__).resolve().parent.parent
    catalog = application_root / "data"
    if not (application_root / "pyproject.toml").is_file():
        return None
    if not catalog.is_dir():
        return None
    return application_root, catalog.resolve()


def _validate_catalog(
    catalog_root: Path,
    *,
    require_local_claim_receipt: bool,
) -> None:
    if not catalog_root.is_dir():
        raise ApplicationResourceError(
            f"catalog root is not a directory: {catalog_root}",
        )
    missing = tuple(
        name
        for name in _REQUIRED_CATALOG_DIRECTORIES
        if not (catalog_root / name).is_dir()
    )
    if missing:
        raise ApplicationResourceError(
            "catalog root is missing required directories: "
            + ", ".join(missing),
        )
    if require_local_claim_receipt:
        claims = catalog_root / _HISTORICAL_CLAIMS_RELATIVE_PATH
        if not claims.is_file():
            raise ApplicationResourceError(
                f"historical claim receipt is missing: {claims}",
            )


def _user_state_root(environment: Mapping[str, str]) -> Path:
    configured = _configured_path(
        None,
        environment,
        STATE_ROOT_ENV,
    )
    if configured is not None:
        return configured
    xdg_state = environment.get("XDG_STATE_HOME")
    if xdg_state:
        path = Path(xdg_state).expanduser()
        if not path.is_absolute():
            raise ApplicationResourceError(
                "XDG_STATE_HOME must be an absolute path",
            )
        return path.resolve() / "stochastic-warfare"
    return Path.home().resolve() / ".local/state/stochastic-warfare"


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    """Resolved immutable inputs and mutable application output locations."""

    mode: ApplicationResourceMode
    application_root: Path
    catalog_root: Path
    scenario_root: Path
    historical_claims_path: Path
    historical_claim_audit_mode: HistoricalClaimAuditMode
    database_path: Path
    frontend_bundle: Path | None
    artifact_root: Path

    @classmethod
    def discover(
        cls,
        *,
        catalog_root: str | Path | None = None,
        database_path: str | Path | None = None,
        frontend_bundle: str | Path | None = None,
        artifact_root: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> ApplicationPaths:
        """Resolve explicit, packaged, or checkout resources without CWD use."""
        env = os.environ if environment is None else environment
        packaged = _packaged_catalog()
        checkout = _checkout_catalog()
        if packaged is not None:
            base_mode = ApplicationResourceMode.PACKAGE
            base_application_root, base_catalog = packaged
        elif checkout is not None:
            base_mode = ApplicationResourceMode.CHECKOUT
            base_application_root, base_catalog = checkout
        else:
            raise ApplicationResourceError(
                "no application resources are available; install a wheel "
                "with bundled resources",
            )
        configured_catalog = _configured_path(
            catalog_root,
            env,
            CATALOG_ROOT_ENV,
            relative_to=base_application_root,
        )
        if configured_catalog is not None:
            mode = ApplicationResourceMode.EXTERNAL
            application_root = base_application_root
            resolved_catalog = configured_catalog
        else:
            mode = base_mode
            application_root = base_application_root
            resolved_catalog = base_catalog

        _validate_catalog(
            resolved_catalog,
            require_local_claim_receipt=(
                mode is not ApplicationResourceMode.EXTERNAL
            ),
        )
        state_root = _user_state_root(env)
        raw_database = (
            database_path
            if database_path is not None
            else env.get(DATABASE_PATH_ENV)
        )
        if raw_database == ":memory:":
            configured_database = Path(":memory:")
        else:
            configured_database = _configured_path(
                database_path,
                env,
                DATABASE_PATH_ENV,
                relative_to=application_root,
            )
        if configured_database is None:
            configured_database = (
                resolved_catalog / "api_runs.db"
                if mode is ApplicationResourceMode.CHECKOUT
                else state_root / "api_runs.db"
            )
        configured_artifacts = _configured_path(
            artifact_root,
            env,
            ARTIFACT_ROOT_ENV,
            relative_to=application_root,
        )
        if configured_artifacts is None:
            configured_artifacts = (
                application_root / "artifacts"
                if mode is ApplicationResourceMode.CHECKOUT
                else state_root / "artifacts"
            )

        configured_frontend = _configured_path(
            frontend_bundle,
            env,
            FRONTEND_ROOT_ENV,
            relative_to=application_root,
        )
        explicit_frontend = (
            frontend_bundle is not None
            or FRONTEND_ROOT_ENV in env
        )
        if configured_frontend is None:
            checkout_frontend = application_root / "frontend/dist"
            configured_frontend = (
                checkout_frontend.resolve()
                if checkout_frontend.is_dir()
                else None
            )
        elif not configured_frontend.is_dir():
            raise ApplicationResourceError(
                f"frontend bundle is not a directory: {configured_frontend}",
            )
        if explicit_frontend and configured_frontend is None:
            raise ApplicationResourceError(
                "configured frontend bundle is unavailable",
            )

        historical_claims_path = (
            base_catalog / _HISTORICAL_CLAIMS_RELATIVE_PATH
        ).resolve()
        if not historical_claims_path.is_file():
            raise ApplicationResourceError(
                f"historical claim receipt is missing: {historical_claims_path}",
            )

        return cls(
            mode=mode,
            application_root=application_root.resolve(),
            catalog_root=resolved_catalog.resolve(),
            scenario_root=(resolved_catalog / "scenarios").resolve(),
            historical_claims_path=historical_claims_path,
            historical_claim_audit_mode=(
                HistoricalClaimAuditMode.PACKAGE
                if base_mode is ApplicationResourceMode.PACKAGE
                else HistoricalClaimAuditMode.REPOSITORY
            ),
            database_path=configured_database,
            frontend_bundle=configured_frontend,
            artifact_root=configured_artifacts,
        )

    def prepare_output_directories(self) -> None:
        """Create only mutable application-output directories."""
        if self.database_path != Path(":memory:"):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def resolve_scenario(self, reference: str | Path) -> Path:
        """Resolve a catalog name or explicit scenario file."""
        raw = os.fspath(reference)
        if not raw or raw != raw.strip():
            raise ApplicationResourceError(
                "scenario reference must be a non-empty trimmed value",
            )
        candidate = Path(raw).expanduser()
        if candidate.is_absolute() or len(candidate.parts) > 1:
            resolved = candidate.resolve()
            if not resolved.is_file():
                raise ApplicationResourceError(
                    f"scenario file does not exist: {resolved}",
                )
            return resolved

        try:
            name = validate_scenario_name(raw)
        except ValueError as exc:
            raise ApplicationResourceError(str(exc)) from exc
        base = self.scenario_root / name / "scenario.yaml"
        if base.is_file():
            return base.resolve()
        eras_root = self.catalog_root / "eras"
        if eras_root.is_dir():
            for era_root in sorted(eras_root.iterdir()):
                candidate = era_root / "scenarios" / name / "scenario.yaml"
                if candidate.is_file():
                    return candidate.resolve()
        raise ApplicationResourceError(
            f"scenario {name!r} was not found below {self.scenario_root}",
        )
