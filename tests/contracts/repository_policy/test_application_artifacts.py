"""Installed-artifact contracts for the production Python application."""

from __future__ import annotations

from email.parser import BytesParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile

import pytest

from stochastic_warfare.application_paths import (
    ApplicationPaths,
    ApplicationResourceError,
    ApplicationResourceMode,
    catalog_resource_manifest,
)
from stochastic_warfare.build_source import (
    PROHIBITED_CHECKOUT_BUILD_FILES,
    SOURCE_MANIFEST_FILENAME,
    SOURCE_REVISION_ENV,
    SOURCE_REVISION_FILENAME,
    prepare_clean_wheel_build_root,
    resolve_source_revision,
    validated_checkout_build_inputs,
    write_sdist_input_manifest,
)
from stochastic_warfare.validation.historical_backtest import (
    HistoricalClaimLedgerLoader,
)
from tests.artifact_support import (
    BuiltArtifacts,
    run_command,
)

pytest_plugins = ("tests.artifact_support",)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESOURCE_PREFIX = "stochastic_warfare/resources/data/"


def _source_python_files() -> set[str]:
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for root_name in ("api", "stochastic_warfare")
        for path in (REPOSITORY_ROOT / root_name).rglob("*.py")
        if "__pycache__" not in path.parts
    }


def _source_catalog_files() -> dict[str, bytes]:
    data_root = REPOSITORY_ROOT / "data"
    return {
        entry.relative_path: (data_root / entry.relative_path).read_bytes()
        for entry in catalog_resource_manifest(data_root)
    }


def _wheel_dist_info(version: str) -> set[str]:
    root = f"stochastic_warfare-{version}.dist-info"
    return {
        f"{root}/METADATA",
        f"{root}/RECORD",
        f"{root}/WHEEL",
        f"{root}/entry_points.txt",
        f"{root}/licenses/LICENSE.md",
        f"{root}/top_level.txt",
    }


def _initialize_clean_parent_worktree(root: Path) -> str:
    root.mkdir()
    (root / ".gitignore").write_text(
        "external-data/\nsite/\nstate/\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Artifact Parent Test"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "artifact-parent@example.invalid",
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "add", ".gitignore"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "parent"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _initialize_minimal_build_checkout(root: Path) -> str:
    root.mkdir()
    root_files = {
        "LICENSE.md": "test license\n",
        "README.md": "test readme\n",
        "build_hooks.py": "# build hook\n",
        "pyproject.toml": "[build-system]\n",
    }
    for relative, payload in root_files.items():
        (root / relative).write_text(payload, encoding="utf-8")
    for relative, payload in {
        "api/__init__.py": "",
        "stochastic_warfare/__init__.py": "",
        "stochastic_warfare/module.py": "VALUE = 1\n",
        "data/units/example.yaml": "id: example\n",
    }.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    (root / ".gitignore").write_text(
        "data/terrain_cache/\n"
        "data/units/ignored.yaml\n"
        "stochastic_warfare/__pycache__/\n"
        "stochastic_warfare/ignored.py\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Build Source Test"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "build-source@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "source"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_checkout_paths_do_not_depend_on_cwd_and_partial_external_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    paths = ApplicationPaths.discover(environment={})
    assert paths.mode is ApplicationResourceMode.CHECKOUT
    assert paths.application_root == REPOSITORY_ROOT
    assert paths.catalog_root == REPOSITORY_ROOT / "data"

    partial = tmp_path / "external-catalog"
    for name in ("ammunition", "scenarios", "sensors", "signatures", "units"):
        (partial / name).mkdir(parents=True)
    with pytest.raises(
        ApplicationResourceError,
        match="missing required directories: .*weapons",
    ):
        ApplicationPaths.discover(
            catalog_root=partial,
            environment={},
        )


@pytest.mark.test_evidence("structural_only")
def test_setuptools_discovery_and_implicit_data_are_fail_closed() -> None:
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    configuration = pyproject["tool"]["setuptools"]

    assert configuration["include-package-data"] is False
    assert pyproject["project"]["license-files"] == ["LICENSE.md"]
    assert configuration["packages"]["find"] == {
        "include": [
            "stochastic_warfare",
            "stochastic_warfare.*",
            "api",
            "api.*",
        ],
        "namespaces": False,
    }
    assert configuration["exclude-package-data"] == {
        "*": ["*.pyi", "py.typed"],
    }
    assert all(
        not (REPOSITORY_ROOT / name).exists()
        for name in PROHIBITED_CHECKOUT_BUILD_FILES
    )
    observed_license_inputs = {
        path.name
        for pattern in ("AUTHORS*", "COPYING*", "LICEN[CS]E*", "NOTICE*")
        for path in REPOSITORY_ROOT.glob(pattern)
    }
    assert observed_license_inputs == {"LICENSE.md"}


@pytest.mark.test_evidence("structural_only")
def test_docker_image_copies_build_backend_inputs_before_sync() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    _frontend_stage, python_separator, python_stage = dockerfile.partition(
        "FROM python:",
    )
    assert python_separator
    python_stage, _next_stage, _remainder = python_stage.partition("\nFROM ")
    before_sync, sync_separator, _after_sync = python_stage.partition(
        "RUN uv sync --locked --extra api --no-dev",
    )
    assert sync_separator
    copied_inputs = {
        token
        for line in before_sync.splitlines()
        if line.startswith("COPY ") and not line.startswith("COPY --from=")
        for token in line.removeprefix("COPY ").split()[:-1]
    }
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    command_modules = {
        value.rsplit(".", 1)[0].replace(".", "/") + ".py"
        for value in pyproject["tool"]["setuptools"]["cmdclass"].values()
    }
    required_inputs = {
        ".python-version",
        "pyproject.toml",
        "uv.lock",
        *pyproject["project"]["license-files"],
        *command_modules,
    }
    assert required_inputs <= copied_inputs


def test_external_catalog_missing_unconditional_loader_root_fails(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external-catalog"
    shutil.copytree(REPOSITORY_ROOT / "data", external)
    shutil.rmtree(external / "logistics/supply_items")

    with pytest.raises(
        ApplicationResourceError,
        match="logistics/supply_items",
    ):
        ApplicationPaths.discover(
            catalog_root=external,
            environment={},
        )


@pytest.mark.test_evidence("behavioral_oracle")
def test_packaged_claim_projection_rejects_tampered_full_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package-resources"
    for scenario in (REPOSITORY_ROOT / "data").rglob("scenario.yaml"):
        relative = scenario.relative_to(REPOSITORY_ROOT / "data")
        destination = root / "data" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(scenario, destination)
    source_ledger = REPOSITORY_ROOT / "data/validation/historical_claims.yaml"
    ledger = root / "data/validation/historical_claims.yaml"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = source_ledger.read_text(encoding="utf-8")
    head, separator, _digest = payload.rpartition("ledger_sha256: ")
    assert separator
    ledger.write_text(
        head + separator + ("0" * 64) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="historical claim ledger digest does not match",
    ):
        HistoricalClaimLedgerLoader(root).load_packaged_scenario_catalog(
            ledger,
        )


@pytest.mark.test_evidence("behavioral_oracle")
def test_wheel_and_sdist_are_exact_allowlisted_artifacts(
    built_artifacts: BuiltArtifacts,
) -> None:
    project = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )["project"]
    version = project["version"]
    python_files = _source_python_files()
    catalog = _source_catalog_files()

    with zipfile.ZipFile(built_artifacts.wheel) as archive:
        wheel_files = set(archive.namelist())
        expected_wheel = (
            python_files
            | {
                RESOURCE_PREFIX + relative
                for relative in catalog
            }
            | _wheel_dist_info(version)
            | {"stochastic_warfare/_build_identity.json"}
        )
        assert wheel_files == expected_wheel
        for relative, source_payload in catalog.items():
            assert archive.read(RESOURCE_PREFIX + relative) == source_payload

        identity = json.loads(
            archive.read("stochastic_warfare/_build_identity.json"),
        )
        assert identity["schema_version"] == 2
        assert identity["artifact_layout"] == "python-distribution"
        assert identity["commit"] == built_artifacts.revision

        dist_info = f"stochastic_warfare-{version}.dist-info"
        entry_points = archive.read(
            f"{dist_info}/entry_points.txt",
        ).decode("utf-8")
        assert entry_points == (
            "[console_scripts]\n"
            "stochastic-warfare = stochastic_warfare.cli:main\n"
        )
        metadata = BytesParser().parsebytes(
            archive.read(f"{dist_info}/METADATA"),
        )
        assert metadata["Version"] == version
        assert set(metadata.get_all("Provides-Extra")) == {
            "api",
            "dev",
            "docs",
            "mcp",
            "perf",
            "terrain",
        }
        base_requirements = [
            value
            for value in metadata.get_all("Requires-Dist")
            if "; extra ==" not in value
        ]
        assert all(
            optional not in "\n".join(base_requirements).lower()
            for optional in ("aiosqlite", "fastapi", "mcp", "uvicorn")
        )

    with tarfile.open(built_artifacts.sdist, "r:gz") as archive:
        members = [member.name for member in archive if member.isfile()]
        roots = {name.split("/", 1)[0] for name in members}
        assert len(roots) == 1
        relative_files = {
            name.split("/", 1)[1]
            for name in members
        }
        expected_sdist = (
            python_files
            | {f"data/{relative}" for relative in catalog}
            | {
                "LICENSE.md",
                "PKG-INFO",
                "README.md",
                "SOURCE_REVISION",
                "SOURCE_MANIFEST.json",
                "build_hooks.py",
                "pyproject.toml",
                "setup.cfg",
            }
        )
        assert relative_files == expected_sdist


@pytest.mark.test_evidence("behavioral_oracle")
def test_sdist_rebuilds_without_git_and_wheel_runs_production_cli(
    built_artifacts: BuiltArtifacts,
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    rebuilt = tmp_path / "rebuilt"
    environment = dict(os.environ)
    environment.pop("SOURCE_REVISION", None)
    environment["UV_OFFLINE"] = "1"
    run_command(
        [
            uv,
            "build",
            os.fspath(built_artifacts.sdist),
            "--wheel",
            "--offline",
            "--out-dir",
            os.fspath(rebuilt),
        ],
        cwd=tmp_path,
        environment=environment,
    )
    rebuilt_wheel, = rebuilt.glob("*.whl")

    extracted = tmp_path / "tampered"
    with tarfile.open(built_artifacts.sdist, "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    extracted_root, = extracted.iterdir()
    cli_path = extracted_root / "stochastic_warfare/cli.py"
    cli_path.write_text(
        cli_path.read_text(encoding="utf-8") + "\n# tampered\n",
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [
            uv,
            "build",
            os.fspath(extracted_root),
            "--wheel",
            "--offline",
            "--out-dir",
            os.fspath(tmp_path / "rejected"),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "sdist input manifest mismatch" in rejected.stderr

    configured_environment = dict(environment)
    configured_environment[SOURCE_REVISION_ENV] = built_artifacts.revision
    configured_rejected = subprocess.run(
        [
            uv,
            "build",
            os.fspath(extracted_root),
            "--wheel",
            "--offline",
            "--out-dir",
            os.fspath(tmp_path / "configured-rejected"),
        ],
        cwd=tmp_path,
        env=configured_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert configured_rejected.returncode != 0
    assert "sdist input manifest mismatch" in configured_rejected.stderr

    deployment = tmp_path / "parent-worktree"
    parent_commit = _initialize_clean_parent_worktree(deployment)
    site = deployment / "site"
    run_command(
        [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--offline",
            "--no-deps",
            "--target",
            os.fspath(site),
            os.fspath(rebuilt_wheel),
        ],
        cwd=deployment,
        environment=environment,
    )
    runtime_environment = dict(environment)
    runtime_environment.update(
        {
            "PYTHONPATH": os.fspath(site),
            "XDG_STATE_HOME": os.fspath(deployment / "state"),
        },
    )
    probe = run_command(
        [
            sys.executable,
            "-c",
            (
                "import json, pathlib, sys; "
                "blocked={'aiosqlite','fastapi','mcp','pydantic_settings','uvicorn'}; "
                "before=set(sys.modules); "
                "import stochastic_warfare; "
                "from stochastic_warfare.application_paths import ApplicationPaths; "
                "from stochastic_warfare.build_identity import load_verified_build_identity; "
                "paths=ApplicationPaths.discover(); "
                "identity=load_verified_build_identity(pathlib.Path(stochastic_warfare.__file__)); "
                "assert not (blocked & (set(sys.modules)-before)); "
                "print(json.dumps({'module':stochastic_warfare.__file__,"
                "'version':stochastic_warfare.__version__,'mode':paths.mode.value,"
                "'catalog':str(paths.catalog_root),'commit':identity.commit}))"
            ),
        ],
        cwd=deployment,
        environment=runtime_environment,
    )
    installed = json.loads(probe.stdout)
    assert Path(installed["module"]).is_relative_to(site)
    assert Path(installed["catalog"]).is_relative_to(site)
    assert installed["mode"] == "package"
    assert installed["commit"] == built_artifacts.revision
    assert installed["commit"] != parent_commit

    help_result = run_command(
        [
            os.fspath(site / "bin/stochastic-warfare"),
            "--help",
        ],
        cwd=deployment,
        environment=runtime_environment,
    )
    assert "{run}" in help_result.stdout

    completed = run_command(
        [
            sys.executable,
            "-m",
            "stochastic_warfare",
            "run",
            "test_campaign",
            "--seed",
            "112",
            "--max-ticks",
            "1",
        ],
        cwd=deployment,
        environment=runtime_environment,
    )
    summary = json.loads(completed.stdout)
    assert summary["scenario"] == "Test Campaign - Minimal"
    assert summary["ticks_executed"] == 1
    assert summary["execution_mode"] == "strict"
    assert summary["authoritative"] is True
    assert summary["provenance"]["code_revision"]["commit"] == (
        built_artifacts.revision
    )

    external_data = deployment / "external-data"
    shutil.copytree(REPOSITORY_ROOT / "data", external_data)
    external_completed = run_command(
        [
            sys.executable,
            "-m",
            "stochastic_warfare",
            "run",
            "test_campaign",
            "--data-root",
            os.fspath(external_data),
            "--seed",
            "112",
            "--max-ticks",
            "1",
        ],
        cwd=deployment,
        environment=runtime_environment,
    )
    external_summary = json.loads(external_completed.stdout)
    assert external_summary["catalog_root"] == os.fspath(external_data)
    assert external_summary["provenance"]["code_revision"]["commit"] == (
        built_artifacts.revision
    )
    parent_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=deployment,
        check=True,
        capture_output=True,
    )
    assert parent_status.stdout == b""


@pytest.mark.parametrize(
    "marker",
    (SOURCE_REVISION_FILENAME, SOURCE_MANIFEST_FILENAME),
)
def test_partial_sdist_source_receipt_is_rejected(
    tmp_path: Path,
    marker: str,
) -> None:
    marker_payload = (
        "a" * 40 + "\n"
        if marker == SOURCE_REVISION_FILENAME
        else "{}\n"
    )
    (tmp_path / marker).write_text(marker_payload, encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="requires both SOURCE_REVISION and SOURCE_MANIFEST.json",
    ):
        resolve_source_revision(
            tmp_path,
            environment={SOURCE_REVISION_ENV: "a" * 40},
        )


def test_sdist_source_receipt_rejects_mismatched_pipeline_revision(
    tmp_path: Path,
) -> None:
    receipt_revision = "a" * 40
    (tmp_path / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    (tmp_path / SOURCE_REVISION_FILENAME).write_text(
        receipt_revision + "\n",
        encoding="utf-8",
    )
    write_sdist_input_manifest(
        tmp_path,
        receipt_revision,
        ["pyproject.toml"],
    )

    assert (
        resolve_source_revision(
            tmp_path,
            environment={SOURCE_REVISION_ENV: receipt_revision},
        )
        == receipt_revision
    )
    with pytest.raises(
        RuntimeError,
        match="SOURCE_REVISION does not match sdist receipt revision",
    ):
        resolve_source_revision(
            tmp_path,
            environment={SOURCE_REVISION_ENV: "b" * 40},
        )


def test_dirty_source_requires_explicit_pipeline_revision(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    _initialize_minimal_build_checkout(checkout)
    module = checkout / "stochastic_warfare/module.py"
    module.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="refusing to label dirty application inputs",
    ):
        resolve_source_revision(checkout, environment={})


@pytest.mark.parametrize(
    ("relative", "payload"),
    (
        ("stochastic_warfare/ignored.py", "VALUE = 2\n"),
        ("data/units/ignored.yaml", "id: ignored\n"),
    ),
)
def test_git_revision_rejects_ignored_build_inputs(
    tmp_path: Path,
    relative: str,
    payload: str,
) -> None:
    checkout = tmp_path / "checkout"
    _initialize_minimal_build_checkout(checkout)
    destination = checkout / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")

    with pytest.raises(RuntimeError, match="added_or_ignored"):
        resolve_source_revision(checkout, environment={})


def test_git_revision_ignores_nonartifact_cache_inputs(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    revision = _initialize_minimal_build_checkout(checkout)
    cache = checkout / "stochastic_warfare/__pycache__/module.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"cache")
    terrain = checkout / "data/terrain_cache/ignored.yaml"
    terrain.parent.mkdir(parents=True)
    terrain.write_text("cache: true\n", encoding="utf-8")

    assert resolve_source_revision(checkout, environment={}) == revision


@pytest.mark.parametrize("flag", ("--assume-unchanged", "--skip-worktree"))
def test_git_revision_rejects_hidden_index_flags(
    tmp_path: Path,
    flag: str,
) -> None:
    checkout = tmp_path / "checkout"
    _initialize_minimal_build_checkout(checkout)
    relative = "stochastic_warfare/module.py"
    subprocess.run(
        ["git", "update-index", flag, relative],
        cwd=checkout,
        check=True,
    )
    (checkout / relative).write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unsupported .* index flags"):
        resolve_source_revision(checkout, environment={})


def test_git_revision_rejects_hidden_executable_mode_drift(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _initialize_minimal_build_checkout(checkout)
    subprocess.run(
        ["git", "config", "core.filemode", "false"],
        cwd=checkout,
        check=True,
    )
    (checkout / "stochastic_warfare/module.py").chmod(0o755)

    with pytest.raises(RuntimeError, match="modes differ from immutable Git HEAD"):
        resolve_source_revision(checkout, environment={})


def test_build_layout_rejects_tracked_python_symlink_with_pipeline_revision(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    _initialize_minimal_build_checkout(checkout)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 2\n", encoding="utf-8")
    module = checkout / "stochastic_warfare/module.py"
    module.unlink()
    module.symlink_to(outside)
    subprocess.run(["git", "add", "-A"], cwd=checkout, check=True)
    subprocess.run(
        ["git", "commit", "-m", "symlink"],
        cwd=checkout,
        check=True,
        capture_output=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    outside.write_text("VALUE = 3\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="do not permit file symlinks"):
        resolve_source_revision(
            checkout,
            environment={SOURCE_REVISION_ENV: revision},
        )


@pytest.mark.parametrize(
    "legacy_name",
    PROHIBITED_CHECKOUT_BUILD_FILES,
)
def test_build_layout_rejects_legacy_configuration_with_pipeline_revision(
    tmp_path: Path,
    legacy_name: str,
) -> None:
    checkout = tmp_path / "checkout"
    revision = _initialize_minimal_build_checkout(checkout)
    (checkout / legacy_name).write_text("# prohibited\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="prohibited legacy build configuration"):
        resolve_source_revision(
            checkout,
            environment={SOURCE_REVISION_ENV: revision},
        )


@pytest.mark.parametrize(
    ("relative", "message"),
    (
        ("NOTICE-local", "license inputs must be exactly"),
        (
            "stochastic_warfare/.hidden.py",
            "outside the explicit regular-package layout",
        ),
        (
            "stochastic_warfare/assets/tool.py",
            "below a non-package directory",
        ),
    ),
)
def test_build_layout_rejects_implicit_or_ambiguous_inputs(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    checkout = tmp_path / "checkout"
    revision = _initialize_minimal_build_checkout(checkout)
    destination = checkout / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        resolve_source_revision(
            checkout,
            environment={SOURCE_REVISION_ENV: revision},
        )


def test_build_layout_rejects_symlinked_source_root(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    revision = _initialize_minimal_build_checkout(checkout)
    shutil.rmtree(checkout / "data")
    outside = tmp_path / "outside-data"
    outside.mkdir()
    (outside / "catalog.yaml").write_text("id: outside\n", encoding="utf-8")
    (checkout / "data").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="regular non-symlink directory"):
        resolve_source_revision(
            checkout,
            environment={SOURCE_REVISION_ENV: revision},
        )


@pytest.mark.test_evidence("behavioral_oracle")
def test_wheel_build_cleanup_rejects_symlinked_parent(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    victim = tmp_path / "victim"
    victim_lib = victim / "lib"
    victim_lib.mkdir(parents=True)
    sentinel = victim_lib / "sentinel.txt"
    sentinel.write_text("preserve\n", encoding="utf-8")
    (checkout / "build").symlink_to(victim, target_is_directory=True)

    with pytest.raises(RuntimeError, match="regular non-symlink directories"):
        prepare_clean_wheel_build_root(checkout, checkout / "build/lib")
    assert sentinel.read_text(encoding="utf-8") == "preserve\n"


def test_checkout_build_input_enumerator_matches_artifact_sources() -> None:
    inputs = set(validated_checkout_build_inputs(REPOSITORY_ROOT))
    assert inputs == (
        _source_python_files()
        | {f"data/{relative}" for relative in _source_catalog_files()}
        | {"LICENSE.md", "README.md", "build_hooks.py", "pyproject.toml"}
    )
