"""Production consumer proofs for the strict Phase 112 analysis boundary."""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

import stochastic_warfare.build_identity as build_identity_module
from stochastic_warfare.build_identity import (
    BUILD_IDENTITY_RELATIVE_PATH,
    BuildIdentityError,
    application_source_manifest_sha256,
    load_verified_build_identity,
    write_build_identity,
)
from stochastic_warfare.simulation.recorder import SimulationRecorder
import stochastic_warfare.simulation.runtime as runtime_module
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    CodeRevision,
    SimulationRuntimeFactory,
    _resolve_code_revision,
    _runtime_code_revision,
)
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.scenario import (
    load_campaign_scenario_config,
)
from stochastic_warfare.tools._run_helpers import AnalysisRunner
from stochastic_warfare.tools._run_helpers import run_scenario_batch
from stochastic_warfare.tools.comparison import (
    ComparisonConfig,
    run_comparison,
)
from stochastic_warfare.tools.mcp_server import (
    _create_server,
    _tool_modify_parameter,
    _tool_run_monte_carlo,
    _tool_run_scenario,
)


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
SCENARIO_PATH = DATA_DIR / "scenarios/test_campaign/scenario.yaml"


def _initialize_packaged_application(tmp_path: Path) -> Path:
    application_root = tmp_path / "immutable-application"
    package = application_root / "stochastic_warfare"
    api = application_root / "api"
    data = application_root / "data"
    package.mkdir(parents=True)
    api.mkdir()
    data.mkdir()
    (package / "__init__.py").write_text(
        '"""Immutable application fixture."""\n',
        encoding="utf-8",
    )
    (package / "runtime.py").write_text(
        "IDENTITY = 1\n",
        encoding="utf-8",
    )
    (api / "__init__.py").write_text("", encoding="utf-8")
    (api / "main.py").write_text("APP = 'fixture'\n", encoding="utf-8")
    (application_root / "pyproject.toml").write_text(
        "[project]\nname = 'immutable-fixture'\n",
        encoding="utf-8",
    )
    (application_root / "uv.lock").write_text(
        "version = 1\n",
        encoding="utf-8",
    )
    return application_root


def _initialize_identity_repo(
    tmp_path: Path,
    *,
    complete_data: bool = False,
) -> tuple[Path, Path, Path]:
    repo = tmp_path / "identity-repo"
    data_root = repo / "data"
    if complete_data:
        shutil.copytree(DATA_DIR, data_root)
    else:
        scenario = data_root / "scenarios/test_campaign/scenario.yaml"
        scenario.parent.mkdir(parents=True)
        shutil.copy2(SCENARIO_PATH, scenario)

    ignored_data = data_root / "mutable.identity"
    ignored_data.write_text("prepared\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "data/mutable.identity\n"
        "data/terrain_cache/\n",
        encoding="utf-8",
    )
    code_marker = repo / "runtime.py"
    code_marker.write_text("IDENTITY = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Phase 112 Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "phase112@example.invalid",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "identity fixture"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo, ignored_data, code_marker


def _initialize_runtime_provenance_repo(
    tmp_path: Path,
) -> tuple[Path, dict[str, Path]]:
    repo = tmp_path / "runtime-provenance-repo"
    package = repo / "stochastic_warfare"
    api = repo / "api"
    package.mkdir(parents=True)
    api.mkdir()
    files = {
        "stochastic_warfare/__init__.py": package / "__init__.py",
        "stochastic_warfare/runtime.py": package / "runtime.py",
        "api/__init__.py": api / "__init__.py",
        "api/main.py": api / "main.py",
        "build_hooks.py": repo / "build_hooks.py",
        "scripts/probe.py": repo / "scripts/probe.py",
        "scripts/sitecustomize.py": repo / "scripts/sitecustomize.py",
        "scripts/usercustomize.pyc": repo / "scripts/usercustomize.pyc",
        "launch/usercustomize/__init__.pyc": (
            repo / "launch/usercustomize/__init__.pyc"
        ),
        "tests/__init__.py": repo / "tests/__init__.py",
    }
    for relative, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"IDENTITY = {relative!r}\n", encoding="utf-8")
    files["scripts/probe.py"].write_text(
        "import pydantic\n\nprint(pydantic.__file__)\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        ".venv/\n"
        "artifacts/\n"
        "build/\n"
        "data/terrain_cache/\n"
        "api/ignored.py\n"
        "api/ignored.resource\n"
        "api/__pycache__/\n"
        "stochastic_warfare/ignored.py\n"
        "stochastic_warfare/ignored.resource\n"
        "stochastic_warfare/__pycache__/\n"
        "dependency_shadow/\n"
        "dependency_shadow_bytecode/\n"
        "dependency_shadow_extension/\n"
        "/dependency_link\n"
        "nested/usercustomize.py\n"
        "nested/usercustomize.pyc\n"
        "nested/sitecustomize/\n"
        "scripts/pydantic.py\n"
        "/shadow_dependency.py\n"
        "/shadow_dependency.pyc\n"
        "/shadow_extension.so\n"
        "/sitecustomize.py\n"
        "tools/sitecustomize.py\n"
        "tools/sitecustomize.cpython-312-x86_64-linux-gnu.so\n"
        "/usercustomize.py\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Runtime Provenance Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "runtime-provenance@example.invalid",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "runtime provenance fixture"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo, files


def _prepare_identity_repo(repo: Path):
    return SimulationRuntimeFactory().prepare(
        repo / "data/scenarios/test_campaign/scenario.yaml",
        repo / "data",
        (AnalysisVariant(variant_id="identity"),),
    )


def test_code_revision_rejects_untracked_symlinks_and_special_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Phase 112 Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "phase112@example.invalid",
        ],
        cwd=repo,
        check=True,
    )
    tracked = repo / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    outside = tmp_path / "outside.txt"
    outside.write_text("first outside content\n", encoding="utf-8")
    untracked = repo / "untracked.py"
    untracked.symlink_to(outside)
    with pytest.raises(ValueError, match="does not permit symlinks"):
        _resolve_code_revision(repo)

    untracked.unlink()
    os.mkfifo(untracked)
    with pytest.raises(ValueError, match="regular file"):
        _resolve_code_revision(repo)


def test_worktree_entry_identity_rejects_in_place_change_during_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    source = repo / "unstable.py"
    source.write_bytes(b"A" * 1024)
    real_read = runtime_module.os.read
    changed = False

    def read_then_change(descriptor: int, size: int) -> bytes:
        nonlocal changed
        payload = real_read(descriptor, size)
        if payload and not changed:
            changed = True
            source.write_bytes(b"B" * len(payload))
        return payload

    monkeypatch.setattr(runtime_module.os, "read", read_then_change)

    with pytest.raises(ValueError, match="entry changed during capture"):
        runtime_module._worktree_entry_identity(repo, "unstable.py")


def test_dirty_code_revision_binds_staged_index_bytes(tmp_path: Path) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    source = files["stochastic_warfare/runtime.py"]
    source.write_text("INDEX = 'first'\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "stochastic_warfare/runtime.py"],
        cwd=repo,
        check=True,
    )
    source.write_text("WORKTREE = 'constant'\n", encoding="utf-8")
    first_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    first = _resolve_code_revision(repo)

    source.write_text("INDEX = 'second'\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "stochastic_warfare/runtime.py"],
        cwd=repo,
        check=True,
    )
    source.write_text("WORKTREE = 'constant'\n", encoding="utf-8")
    second_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    second = _resolve_code_revision(repo)

    assert first_status == second_status
    assert first.dirty is True
    assert second.dirty is True
    assert first.worktree_fingerprint != second.worktree_fingerprint


def test_dirty_code_revision_rejects_change_during_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    source = files["stochastic_warfare/runtime.py"]
    source.write_text("IDENTITY = 'initial dirty bytes'\n", encoding="utf-8")
    real_manifest = runtime_module._runtime_worktree_manifest_sha256
    captures = 0

    def capture_then_change(
        git_repo: Path,
        head_tree: dict[str, tuple[str, str, str]],
        untracked_paths: list[str],
    ) -> str:
        nonlocal captures
        digest = real_manifest(git_repo, head_tree, untracked_paths)
        captures += 1
        if captures == 1:
            source.write_text(
                "IDENTITY = 'different dirty bytes'\n",
                encoding="utf-8",
            )
        return digest

    monkeypatch.setattr(
        runtime_module,
        "_runtime_worktree_manifest_sha256",
        capture_then_change,
    )

    with pytest.raises(
        RuntimeError,
        match="changed during dirty provenance attribution",
    ):
        _resolve_code_revision(repo)


def test_code_revision_rejects_tracked_external_symlinks(
    tmp_path: Path,
) -> None:
    repo, _, _ = _initialize_identity_repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    linked = repo / "linked.py"
    linked.symlink_to(outside)
    subprocess.run(["git", "add", "linked.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "tracked symlink"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    with pytest.raises(ValueError, match="does not permit symlinks"):
        _resolve_code_revision(repo)


def test_code_revision_rejects_ignored_package_directory_symlink(
    tmp_path: Path,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    external_package = tmp_path / "external-dependency"
    external_package.mkdir()
    (external_package / "__init__.py").write_text(
        "IDENTITY = 'external package'\n",
        encoding="utf-8",
    )
    dependency_link = repo / "dependency_link"
    dependency_link.symlink_to(external_package, target_is_directory=True)
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--ignored",
            "--",
            "dependency_link",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout.startswith(b"!! dependency_link")

    with pytest.raises(ValueError, match="does not permit symlinks"):
        _resolve_code_revision(repo)


def test_clean_code_revision_rechecks_ignored_symlink_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    external_package = tmp_path / "late-external-dependency"
    external_package.mkdir()
    (external_package / "__init__.py").write_text(
        "IDENTITY = 'late external package'\n",
        encoding="utf-8",
    )
    dependency_link = repo / "dependency_link"
    real_run_git = runtime_module._run_git

    def run_git_with_late_symlink(
        git_repo: Path,
        *arguments: str,
        input_payload: bytes | None = None,
    ) -> bytes:
        output = real_run_git(
            git_repo,
            *arguments,
            input_payload=input_payload,
        )
        if arguments and arguments[0] == "hash-object":
            dependency_link.symlink_to(
                external_package,
                target_is_directory=True,
            )
        return output

    monkeypatch.setattr(runtime_module, "_run_git", run_git_with_late_symlink)

    with pytest.raises(ValueError, match="does not permit symlinks"):
        _resolve_code_revision(repo)


def test_code_revision_clean_git_attribution_is_stable(
    tmp_path: Path,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    first = _resolve_code_revision(repo)
    second = _resolve_code_revision(repo)

    assert first == second
    assert first.commit == commit
    assert first.dirty is False
    assert len(first.worktree_fingerprint) == 64


def _hide_git_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run_git = runtime_module._run_git

    def run_git_without_status(
        repo: Path,
        *arguments: str,
        input_payload: bytes | None = None,
    ) -> bytes:
        if arguments and arguments[0] == "status":
            return b""
        return real_run_git(
            repo,
            *arguments,
            input_payload=input_payload,
        )

    monkeypatch.setattr(runtime_module, "_run_git", run_git_without_status)


@pytest.mark.parametrize(
    "relative",
    ("stochastic_warfare/runtime.py", "scripts/probe.py"),
)
def test_clean_code_revision_binds_raw_worktree_bytes_to_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    files[relative].write_text(
        "IDENTITY = 'different bytes'\n",
        encoding="utf-8",
    )
    _hide_git_status(monkeypatch)

    with pytest.raises(RuntimeError, match="bytes differ from Git HEAD"):
        _resolve_code_revision(repo)


def test_clean_code_revision_binds_exact_tracked_path_set_to_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    added = repo / "stochastic_warfare/added.py"
    added.write_text("ADDED = True\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "stochastic_warfare/added.py"],
        cwd=repo,
        check=True,
    )
    _hide_git_status(monkeypatch)

    with pytest.raises(RuntimeError, match="index paths differ from Git HEAD"):
        _resolve_code_revision(repo)


def test_dirty_code_revision_retains_content_sensitive_fingerprint(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    clean = _resolve_code_revision(repo)
    files["stochastic_warfare/runtime.py"].write_text(
        "IDENTITY = 'ordinary dirty change'\n",
        encoding="utf-8",
    )
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    first = _resolve_code_revision(repo)
    second = _resolve_code_revision(repo)

    assert first == second
    assert first.commit == clean.commit
    assert first.dirty is True
    assert first.worktree_fingerprint != clean.worktree_fingerprint
    assert len(first.worktree_fingerprint) == 64


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    "relative",
    ("stochastic_warfare/runtime.py", "scripts/probe.py"),
)
def test_dirty_code_revision_binds_raw_filtered_runtime_bytes(
    tmp_path: Path,
    relative: str,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    (repo / ".gitattributes").write_text(
        "*.py text eol=lf\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", ".gitattributes"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "normalize Python source"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    unrelated = repo / "untracked.txt"
    unrelated.write_text("constant unrelated state\n", encoding="utf-8")
    before = _resolve_code_revision(repo)

    source = files[relative]
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    subprocess.run(
        ["git", "add", "--renormalize", "--", relative],
        cwd=repo,
        check=True,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert status == b"?? untracked.txt\0"

    after = _resolve_code_revision(repo)

    assert before.dirty is True
    assert after.dirty is True
    assert after.commit == before.commit
    assert after.worktree_fingerprint != before.worktree_fingerprint


def test_dirty_code_revision_binds_mode_hidden_by_git_configuration(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    (repo / "untracked.txt").write_text(
        "constant unrelated state\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "config", "core.fileMode", "false"],
        cwd=repo,
        check=True,
    )
    before = _resolve_code_revision(repo)
    files["stochastic_warfare/runtime.py"].chmod(0o755)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    assert status == b"?? untracked.txt\0"

    after = _resolve_code_revision(repo)

    assert after.worktree_fingerprint != before.worktree_fingerprint


@pytest.mark.parametrize(
    "index_flag",
    ("--assume-unchanged", "--skip-worktree"),
)
@pytest.mark.parametrize(
    "relative",
    (
        "stochastic_warfare/runtime.py",
        "api/main.py",
        "scripts/probe.py",
        "scripts/sitecustomize.py",
    ),
)
def test_code_revision_rejects_hidden_runtime_source_index_flags(
    tmp_path: Path,
    index_flag: str,
    relative: str,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    subprocess.run(
        ["git", "update-index", index_flag, "--", relative],
        cwd=repo,
        check=True,
    )
    files[relative].write_text("IDENTITY = 'hidden change'\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", relative],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout == b""

    with pytest.raises(RuntimeError, match="unsupported Git index flags"):
        _resolve_code_revision(repo)


@pytest.mark.parametrize(
    "relative",
    ("stochastic_warfare/runtime.py", "scripts/probe.py"),
)
def test_code_revision_rejects_mode_change_hidden_by_git_configuration(
    tmp_path: Path,
    relative: str,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    source = files[relative]
    subprocess.run(
        ["git", "config", "core.fileMode", "false"],
        cwd=repo,
        check=True,
    )
    source.chmod(0o755)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", relative],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout == b""

    with pytest.raises(RuntimeError, match="modes differ from Git HEAD"):
        _resolve_code_revision(repo)


@pytest.mark.parametrize(
    ("git_state", "relative"),
    (
        ("tracked", "dependency_takeover/__init__.py"),
        ("staged", "dependency_takeover_bytecode/__init__.pyc"),
        (
            "untracked",
            "dependency_takeover_extension/"
            "__init__.cpython-312-x86_64-linux-gnu.so",
        ),
        ("tracked", "dependency_takeover.py"),
        ("staged", "dependency_takeover.pyc"),
        (
            "untracked",
            "dependency_takeover.cpython-312-x86_64-linux-gnu.so",
        ),
        ("staged", "dependency_takeover.pyd"),
    ),
)
def test_code_revision_rejects_unknown_checkout_import_candidates(
    tmp_path: Path,
    git_state: str,
    relative: str,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    candidate = repo / relative
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("IDENTITY = 'checkout shadow'\n", encoding="utf-8")
    if git_state in {"tracked", "staged"}:
        subprocess.run(["git", "add", "--", relative], cwd=repo, check=True)
    if git_state == "tracked":
        subprocess.run(
            ["git", "commit", "-m", "add checkout shadow"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    with pytest.raises(
        RuntimeError,
        match="unsupported root import candidates",
    ):
        _resolve_code_revision(repo)


def test_code_revision_rejects_ignored_script_directory_import_shadow(
    tmp_path: Path,
) -> None:
    repo, files = _initialize_runtime_provenance_repo(tmp_path)
    shadow = repo / "scripts/pydantic.py"
    shadow.write_text("IDENTITY = 'ignored script shadow'\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", "scripts/pydantic.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout == b""
    imported = subprocess.run(
        [sys.executable, "-B", os.fspath(files["scripts/probe.py"])],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(imported.stdout.strip()).resolve() == shadow.resolve()

    with pytest.raises(RuntimeError, match="ignored runtime source"):
        _resolve_code_revision(repo)


@pytest.mark.parametrize(
    "relative",
    (
        "stochastic_warfare/ignored.py",
        "stochastic_warfare/ignored.resource",
        "api/ignored.py",
        "api/ignored.resource",
        "dependency_shadow/__init__.py",
        "dependency_shadow_bytecode/__init__.pyc",
        "dependency_shadow_extension/__init__.cpython-312-x86_64-linux-gnu.so",
        "nested/usercustomize.py",
        "nested/usercustomize.pyc",
        "nested/sitecustomize/__init__.pyc",
        "shadow_dependency.py",
        "shadow_dependency.pyc",
        "shadow_extension.so",
        "sitecustomize.py",
        "tools/sitecustomize.py",
        "tools/sitecustomize.cpython-312-x86_64-linux-gnu.so",
        "usercustomize.py",
    ),
)
def test_code_revision_rejects_ignored_runtime_source(
    tmp_path: Path,
    relative: str,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    ignored_source = repo / relative
    ignored_source.parent.mkdir(parents=True, exist_ok=True)
    ignored_source.write_text("IDENTITY = 'ignored source'\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", relative],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout == b""

    with pytest.raises(RuntimeError, match="ignored runtime source"):
        _resolve_code_revision(repo)


def test_code_revision_allows_non_source_ignored_runtime_outputs(
    tmp_path: Path,
) -> None:
    repo, _ = _initialize_runtime_provenance_repo(tmp_path)
    allowed = (
        "stochastic_warfare/__pycache__/generated.py",
        "api/__pycache__/generated.py",
        "build/generated.py",
        ".venv/generated.py",
        "artifacts/generated.py",
        "data/terrain_cache/generated.py",
    )
    for relative in allowed:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("IGNORED = True\n", encoding="utf-8")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert status.stdout == b""

    revision = _resolve_code_revision(repo)

    assert revision.dirty is False


def test_code_revision_accepts_verified_immutable_build_without_git(
    tmp_path: Path,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    commit = "a" * 40
    write_build_identity(application_root, commit)

    revision = _resolve_code_revision(application_root / "data")

    assert revision.commit == commit
    assert revision.dirty is False
    assert len(revision.worktree_fingerprint) == 64
    assert load_verified_build_identity(application_root).commit == commit


def test_runtime_code_revision_is_anchored_to_imported_checkout() -> None:
    revision = _runtime_code_revision()

    assert revision == _resolve_code_revision(
        Path(runtime_module.__file__).resolve(),
    )


def test_code_revision_uses_build_identity_inside_parent_git_worktree(
    tmp_path: Path,
) -> None:
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    (deployment / ".gitignore").write_text(
        "immutable-application/\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "init"],
        cwd=deployment,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Artifact Parent Test"],
        cwd=deployment,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "artifact-parent@example.invalid",
        ],
        cwd=deployment,
        check=True,
    )
    subprocess.run(
        ["git", "add", ".gitignore"],
        cwd=deployment,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "parent"],
        cwd=deployment,
        check=True,
        capture_output=True,
    )
    parent_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=deployment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    application_root = _initialize_packaged_application(deployment)
    embedded_commit = "1" * 40
    assert embedded_commit != parent_commit
    write_build_identity(application_root, embedded_commit)

    revision = _resolve_code_revision(application_root / "data")

    assert revision.commit == embedded_commit
    assert revision.dirty is False


def test_code_revision_does_not_trust_nested_partial_git_worktree(
    tmp_path: Path,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    embedded_commit = "2" * 40
    nested_repo = application_root / "stochastic_warfare"
    subprocess.run(
        ["git", "init"],
        cwd=nested_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Nested Artifact Test"],
        cwd=nested_repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "nested-artifact@example.invalid",
        ],
        cwd=nested_repo,
        check=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=nested_repo,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "nested"],
        cwd=nested_repo,
        check=True,
        capture_output=True,
    )
    write_build_identity(application_root, embedded_commit)

    revision = _resolve_code_revision(nested_repo / "runtime.py")

    assert revision.commit == embedded_commit
    (application_root / "api/main.py").write_text(
        "APP = 'tampered'\n",
        encoding="utf-8",
    )
    with pytest.raises(
        RuntimeError,
        match="verified immutable build identity",
    ):
        _resolve_code_revision(nested_repo / "runtime.py")


def test_runtime_code_revision_rejects_shadow_package_outside_identity_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    write_build_identity(application_root, "3" * 40)
    shadow_runtime = application_root / "shadow/stochastic_warfare/runtime.py"
    shadow_runtime.parent.mkdir(parents=True)
    shadow_runtime.write_text("IDENTITY = 'shadow'\n", encoding="utf-8")
    monkeypatch.setattr(runtime_module, "__file__", os.fspath(shadow_runtime))

    with pytest.raises(
        RuntimeError,
        match="outside the build identity package tree",
    ):
        _runtime_code_revision()


@pytest.mark.parametrize(
    "payload",
    [
        "not JSON",
        "{}",
        (
            '{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"schema_version":true,'
            '"source_manifest_sha256":"'
            + ("0" * 64)
            + '"}'
        ),
        (
            '{"commit":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",'
            '"schema_version":1,'
            '"source_manifest_sha256":"'
            + ("0" * 64)
            + '"}'
        ),
        (
            '{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"extra":0,'
            '"schema_version":1,'
            '"source_manifest_sha256":"'
            + ("0" * 64)
            + '"}'
        ),
        (
            '{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"commit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
            '"schema_version":1,'
            '"source_manifest_sha256":"'
            + ("0" * 64)
            + '"}'
        ),
    ],
)
def test_code_revision_rejects_malformed_immutable_build_identity(
    tmp_path: Path,
    payload: str,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    identity_path = application_root / BUILD_IDENTITY_RELATIVE_PATH
    identity_path.write_text(payload, encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="verified immutable build identity",
    ):
        _resolve_code_revision(application_root / "data")


def test_code_revision_rejects_tampered_immutable_application_source(
    tmp_path: Path,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    write_build_identity(application_root, "b" * 40)
    (application_root / "api/main.py").write_text(
        "APP = 'tampered'\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="verified immutable build identity",
    ):
        _resolve_code_revision(application_root / "data")


def test_build_identity_rejects_source_change_during_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    write_build_identity(application_root, "b" * 40)
    source = application_root / "api/main.py"
    real_manifest = build_identity_module.application_source_manifest_sha256
    captures = 0

    def capture_then_change(
        root: Path,
        *,
        artifact_layout: str,
    ) -> str:
        nonlocal captures
        digest = real_manifest(root, artifact_layout=artifact_layout)
        captures += 1
        if captures == 1:
            source.write_text(
                "APP = 'changed during verification'\n",
                encoding="utf-8",
            )
        return digest

    monkeypatch.setattr(
        build_identity_module,
        "application_source_manifest_sha256",
        capture_then_change,
    )

    with pytest.raises(BuildIdentityError, match="changed during build identity"):
        load_verified_build_identity(application_root)


def test_build_identity_ignores_generated_identity_and_interpreter_caches(
    tmp_path: Path,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    identity_path = write_build_identity(application_root, "c" * 40)
    cache = application_root / "stochastic_warfare/__pycache__"
    cache.mkdir()
    (cache / "runtime.cpython-312.pyc").write_bytes(b"ignored cache")

    verified = load_verified_build_identity(application_root)

    assert verified.commit == "c" * 40
    assert identity_path == application_root / BUILD_IDENTITY_RELATIVE_PATH


def test_build_identity_rejects_source_symlinks_and_special_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    unsupported = application_root / "api/unsupported.py"
    unsupported.symlink_to(application_root / "api/main.py")

    with pytest.raises(BuildIdentityError, match="does not permit symlinks"):
        application_source_manifest_sha256(application_root)

    unsupported.unlink()
    os.mkfifo(unsupported)
    with pytest.raises(BuildIdentityError, match="regular file"):
        application_source_manifest_sha256(application_root)

    unsupported.unlink()
    unsupported.write_bytes(b"A" * 1024)
    real_read = build_identity_module.os.read
    changed = False

    def read_then_change(descriptor: int, size: int) -> bytes:
        nonlocal changed
        payload = real_read(descriptor, size)
        if payload and not changed:
            changed = True
            unsupported.write_bytes(b"B" * len(payload))
        return payload

    monkeypatch.setattr(build_identity_module.os, "read", read_then_change)
    with pytest.raises(BuildIdentityError, match="changed during capture"):
        build_identity_module._read_regular_file(
            unsupported,
            display_path="api/unsupported.py",
        )


def test_established_git_worktree_failure_cannot_use_build_identity_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    write_build_identity(application_root, "d" * 40)

    def failing_git(repo: Path, *arguments: str) -> bytes:
        if arguments == ("rev-parse", "--show-toplevel"):
            return f"{application_root}\n".encode()
        raise subprocess.CalledProcessError(128, ("git", *arguments))

    def forbidden_fallback(start: Path):
        raise AssertionError(
            f"immutable identity fallback used for Git worktree {start}",
        )

    monkeypatch.setattr(runtime_module, "_run_git", failing_git)
    monkeypatch.setattr(
        runtime_module,
        "load_verified_build_identity",
        forbidden_fallback,
    )

    with pytest.raises(
        RuntimeError,
        match="requires a verifiable Git code revision",
    ):
        _resolve_code_revision(application_root / "data")


def test_corrupt_git_marker_cannot_use_build_identity_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_root = _initialize_packaged_application(tmp_path)
    write_build_identity(application_root, "e" * 40)
    (application_root / ".git").mkdir()

    def failing_git(repo: Path, *arguments: str) -> bytes:
        raise subprocess.CalledProcessError(128, ("git", *arguments))

    def forbidden_fallback(start: Path):
        raise AssertionError(
            f"immutable identity fallback used for corrupt Git worktree {start}",
        )

    monkeypatch.setattr(runtime_module, "_run_git", failing_git)
    monkeypatch.setattr(
        runtime_module,
        "load_verified_build_identity",
        forbidden_fallback,
    )

    with pytest.raises(
        RuntimeError,
        match="cannot verify this Git worktree",
    ):
        _resolve_code_revision(application_root / "data")


def test_runtime_rejects_data_changed_after_preparation(
    tmp_path: Path,
) -> None:
    repo, ignored_data, _ = _initialize_identity_repo(tmp_path)
    prepared = _prepare_identity_repo(repo)

    ignored_data.write_text("changed after preparation\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="data changed before runtime construction",
    ):
        prepared.build("identity", seed=112, max_ticks=1)


def test_runtime_ignores_generated_terrain_cache_changes(
    tmp_path: Path,
) -> None:
    repo, _, _ = _initialize_identity_repo(
        tmp_path,
        complete_data=True,
    )
    prepared = _prepare_identity_repo(repo)
    cache_path = repo / "data/terrain_cache/generated.npz"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"derived cache state")

    session = prepared.build("identity", seed=112, max_ticks=1)

    assert session.loaded_roster == session.authored_roster


def test_runtime_rejects_code_changed_after_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _, _ = _initialize_identity_repo(tmp_path)
    prepared = _prepare_identity_repo(repo)
    changed = CodeRevision(
        commit=prepared.code_revision.commit,
        dirty=not prepared.code_revision.dirty,
        worktree_fingerprint="f" * 64,
    )
    monkeypatch.setattr(
        runtime_module,
        "_runtime_code_revision",
        lambda: changed,
    )

    with pytest.raises(
        RuntimeError,
        match="code changed before runtime construction",
    ):
        prepared.build("identity", seed=112, max_ticks=1)


def test_runtime_accepts_unversioned_external_data_with_verified_code(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "unversioned-data"
    data_root.mkdir()
    (data_root / "marker.txt").write_text("data\n", encoding="utf-8")
    source_config = load_campaign_scenario_config(SCENARIO_PATH)

    prepared = SimulationRuntimeFactory().prepare_config(
        source_config,
        data_root,
        (AnalysisVariant(variant_id="unversioned"),),
    )

    assert prepared.data_root == data_root
    assert prepared.code_revision == _runtime_code_revision()


def test_runtime_rejects_unverifiable_imported_code_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "external-data"
    data_root.mkdir()
    (data_root / "marker.txt").write_text("data\n", encoding="utf-8")
    source_config = load_campaign_scenario_config(SCENARIO_PATH)

    def reject_code_revision() -> CodeRevision:
        raise RuntimeError(
            "Authoritative analysis requires a verifiable Git code revision",
        )

    monkeypatch.setattr(
        runtime_module,
        "_runtime_code_revision",
        reject_code_revision,
    )
    with pytest.raises(
        RuntimeError,
        match="requires a verifiable Git code revision",
    ):
        SimulationRuntimeFactory().prepare_config(
            source_config,
            data_root,
            (AnalysisVariant(variant_id="unversioned"),),
        )


def test_runtime_rejects_data_changed_during_construction(
    tmp_path: Path,
) -> None:
    repo, ignored_data, _ = _initialize_identity_repo(
        tmp_path,
        complete_data=True,
    )
    prepared = _prepare_identity_repo(repo)

    def mutating_recorder_factory(context):
        ignored_data.write_text("changed during construction\n", encoding="utf-8")
        return SimulationRecorder(context.event_bus)

    with pytest.raises(
        RuntimeError,
        match="data changed during runtime construction",
    ):
        prepared.build(
            "identity",
            seed=112,
            max_ticks=1,
            recorder_factory=mutating_recorder_factory,
        )


def test_runtime_rejects_unexpected_loaded_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO_PATH,
        DATA_DIR,
        (AnalysisVariant(variant_id="topology"),),
    )
    original_load = ScenarioLoader.load

    def load_with_unexpected_side(loader, *args, **kwargs):
        context = original_load(loader, *args, **kwargs)
        context.units_by_side["unexpected_observer"] = []
        return context

    monkeypatch.setattr(ScenarioLoader, "load", load_with_unexpected_side)
    with pytest.raises(
        RuntimeError,
        match="Loaded side topology does not match authored topology",
    ):
        prepared.build("topology", seed=112, max_ticks=1)


def test_runtime_reads_source_yaml_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_reads = 0
    original_path_open = Path.open
    original_builtin_open = builtins.open

    def is_source(value) -> bool:
        try:
            return Path(value).resolve() == SCENARIO_PATH.resolve()
        except TypeError:
            return False

    def counting_path_open(path: Path, *args, **kwargs):
        nonlocal source_reads
        if is_source(path):
            source_reads += 1
        return original_path_open(path, *args, **kwargs)

    def counting_builtin_open(file, *args, **kwargs):
        nonlocal source_reads
        if is_source(file):
            source_reads += 1
        return original_builtin_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_path_open)
    monkeypatch.setattr(builtins, "open", counting_builtin_open)
    prepared = SimulationRuntimeFactory().prepare(
        SCENARIO_PATH,
        DATA_DIR,
        (AnalysisVariant(variant_id="source-once"),),
    )
    session = prepared.build("source-once", seed=112, max_ticks=1)

    assert session.loaded_roster == session.authored_roster
    assert source_reads == 1


@pytest.mark.test_evidence("behavioral_oracle")
@pytest.mark.parametrize(
    "invalid_value",
    ["10.0", True, float("nan"), float("inf")],
)
def test_file_source_rejects_coercive_or_nonfinite_calibration(
    invalid_value: object,
    tmp_path: Path,
) -> None:
    config = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    config["calibration_overrides"] = {
        "hit_probability_modifier": invalid_value,
    }
    scenario_path = tmp_path / "strict-source.yaml"
    scenario_path.write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Invalid scenario source",
    ):
        SimulationRuntimeFactory().prepare(
            scenario_path,
            DATA_DIR,
            (AnalysisVariant(variant_id="strict-source"),),
        )


def test_base_and_era_data_roots_infer_to_the_global_catalog() -> None:
    factory = SimulationRuntimeFactory()
    base = factory.prepare(
        SCENARIO_PATH,
        None,
        (AnalysisVariant(variant_id="base"),),
    )
    assert base.data_root == DATA_DIR.resolve()

    austerlitz_path = (
        DATA_DIR
        / "eras"
        / "napoleonic"
        / "scenarios"
        / "austerlitz"
        / "scenario.yaml"
    )
    era = factory.prepare(
        austerlitz_path,
        None,
        (AnalysisVariant(variant_id="era"),),
    )
    assert era.data_root == DATA_DIR.resolve()
    session = era.build("era", seed=112, max_ticks=1)
    assert session.authored_roster == (
        ("french", 10),
        ("coalition", 9),
    )
    assert session.loaded_roster == session.authored_roster
    assert any(
        unit.unit_type == "french_old_guard"
        for unit in session.context.units_by_side["french"]
    )


def test_public_python_batch_exposes_complete_outcome_evidence() -> None:
    results = [
        run_scenario_batch(
            scenario_path=str(SCENARIO_PATH),
            overrides={"hit_probability_modifier": modifier},
            num_iterations=3,
            base_seed=42,
            max_ticks=50,
            metric_names=["blue_destroyed", "red_destroyed"],
        )
        for modifier in (0.0, 10.0)
    ]

    for result in results:
        assert result.seeds == (42, 43, 44)
        assert result.authored_roster == result.loaded_roster
        assert len(result.source_fingerprint) == 64
        assert len(result.config_fingerprint) == 64
        assert len(result.runs) == 3
        assert all(run.game_over for run in result.runs)
        assert all(
            len(values) == 3
            for values in result.metrics_dict().values()
        )
        assert all(
            statistics["n"] == 3
            for statistics in result.statistics_dict().values()
        )
        assert len(result.provenance_dict()["runs"]) == 3
    assert results[0].config_fingerprint != results[1].config_fingerprint
    assert results[0].metrics_dict() != results[1].metrics_dict()


def test_public_python_comparison_exposes_complete_outcome_evidence() -> None:
    result = run_comparison(
        ComparisonConfig(
            scenario_path=str(SCENARIO_PATH),
            overrides_a={"hit_probability_modifier": 0.0},
            overrides_b={"hit_probability_modifier": 10.0},
            metric_names=["blue_destroyed", "red_destroyed"],
            num_iterations=3,
            base_seed=42,
            max_ticks=50,
            data_dir=str(DATA_DIR),
        ),
    )

    assert result.seeds == (42, 43, 44)
    assert result.ordered_metrics == (
        "blue_destroyed",
        "red_destroyed",
    )
    assert result.batch_a is not None
    assert result.batch_b is not None
    for batch in (result.batch_a, result.batch_b):
        assert batch.seeds == (42, 43, 44)
        assert batch.base_seed == 42
        assert batch.max_ticks == 50
        assert batch.authored_roster == batch.loaded_roster
        assert len(batch.source_fingerprint) == 64
        assert len(batch.config_fingerprint) == 64
        assert len(batch.data_revision) == 64
        assert batch.data_file_count > 0
        assert len(batch.catalog_revision) == 64
        assert len(batch.doctrine_catalog_fingerprint) == 64
        assert len(batch.loaded_roster_loadout_fingerprint) == 64
        assert [run.seed for run in batch.runs] == [42, 43, 44]
        assert all(run.game_over for run in batch.runs)
        assert all(
            len(values) == 3
            for values in batch.metrics_dict().values()
        )
        for run in batch.runs:
            provenance = run.runtime_provenance
            assert provenance.code_revision == batch.code_revision
            assert provenance.data_revision == batch.data_revision
            assert provenance.data_file_count == batch.data_file_count
            assert provenance.catalog_revision == batch.catalog_revision
            assert (
                provenance.doctrine_catalog_fingerprint
                == batch.doctrine_catalog_fingerprint
            )
            assert (
                provenance.loaded_roster_loadout_fingerprint
                == batch.loaded_roster_loadout_fingerprint
            )
            assert len(provenance.doctrine_assignment_fingerprint) == 64
            assert len(provenance.final_roster_loadout_fingerprint) == 64

    assert result.raw_a == result.batch_a.metrics_dict()
    assert result.raw_b == result.batch_b.metrics_dict()
    assert result.batch_a.config_fingerprint != (
        result.batch_b.config_fingerprint
    )
    assert any(
        result.raw_a[metric] != result.raw_b[metric]
        for metric in result.ordered_metrics
    )


def test_non_blue_red_metrics_use_exact_production_side_ids() -> None:
    """Metric resolution must use exact loaded sides without aliases."""
    scenario_path = DATA_DIR / "eras" / "napoleonic" / "scenarios" / "austerlitz" / "scenario.yaml"
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        DATA_DIR,
        (AnalysisVariant(variant_id="exact-sides"),),
    )
    assert prepared.side_ids == ("french", "coalition")
    assert prepared.authored_roster == (
        ("french", 10),
        ("coalition", 9),
    )

    runner = AnalysisRunner(
        prepared,
        [
            "french_active",
            "coalition_destroyed",
            "win_french",
            "ticks_executed",
        ],
    )
    batch = runner.run_variant(
        "exact-sides",
        num_iterations=1,
        base_seed=42,
        max_ticks=1,
    )

    assert batch.loaded_roster == prepared.authored_roster
    assert batch.metric_values("french_active") == (10.0,)
    assert batch.metric_values("coalition_destroyed") == (0.0,)
    assert batch.metric_values("win_french") == (0.0,)
    assert batch.metric_values("ticks_executed") == (1.0,)
    assert batch.runs[0].winning_side == "draw"
    assert batch.runs[0].condition_type == "max_ticks"

    for invalid_metric in (
        "french_act",
        "fr_active",
        "win_fren",
        "exchange_ratio",
    ):
        with pytest.raises(
            ValueError,
            match="Unsupported metrics",
        ):
            AnalysisRunner(prepared, [invalid_metric])


def _assert_runtime_provenance(provenance: dict) -> None:
    code_revision = provenance["code_revision"]
    status = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert code_revision["commit"] == commit
    assert code_revision["dirty"] == bool(status.stdout)
    assert len(code_revision["worktree_fingerprint"]) == 64

    assert len(provenance["data_revision"]) == 64
    assert provenance["data_file_count"] > 0
    assert len(provenance["catalog_revision"]) == 64
    assert len(provenance["doctrine_catalog_fingerprint"]) == 64
    assert len(provenance["doctrine_assignment_fingerprint"]) == 64
    assert len(provenance["loaded_roster_loadout_fingerprint"]) == 64
    assert len(provenance["final_roster_loadout_fingerprint"]) == 64
    assert provenance["initial_unit_assignments"]
    for assignment in [
        *provenance["initial_unit_assignments"],
        *provenance["arriving_unit_assignments"],
    ]:
        assert set(assignment) == {
            "unit_id",
            "side",
            "commander_profile_id",
            "doctrine_school_id",
        }


@pytest.mark.asyncio
async def test_fastmcp_dispatch_rejects_coercive_scalars_before_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.shared.memory import (
        create_connected_server_and_client_session,
    )
    from stochastic_warfare.tools import mcp_server

    helper_calls: list[tuple[tuple, dict]] = []

    def forbidden_helper(*args, **kwargs):
        helper_calls.append((args, kwargs))
        raise AssertionError("production helper must not be invoked")

    monkeypatch.setattr(
        mcp_server,
        "_tool_run_scenario",
        forbidden_helper,
    )
    monkeypatch.setattr(
        mcp_server,
        "_tool_run_monte_carlo",
        forbidden_helper,
    )
    monkeypatch.setattr(
        mcp_server,
        "_tool_modify_parameter",
        forbidden_helper,
    )
    invalid_calls = (
        (
            "run_scenario",
            {
                "scenario_name": (
                    "../eras/napoleonic/scenarios/austerlitz"
                ),
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "run_scenario",
            {
                "scenario_name": "test_campaign",
                "seed": "42",
                "max_ticks": 1,
            },
        ),
        (
            "run_scenario",
            {
                "scenario_name": "test_campaign",
                "seed": 42,
                "max_ticks": True,
            },
        ),
        (
            "run_scenario",
            {
                "scenario_name": "test_campaign",
                "seed": 42,
                "max_ticks": 1,
                "calibration_patch": {
                    "hit_probability_modifier": "10.0",
                },
            },
        ),
        (
            "run_scenario",
            {
                "scenario_name": "test_campaign",
                "seed": 42,
                "max_ticks": 1,
                "calibration_patch": {
                    "advance_speed": 1.0,
                },
            },
        ),
        (
            "run_monte_carlo",
            {
                "scenario_name": (
                    "../eras/napoleonic/scenarios/austerlitz"
                ),
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "run_monte_carlo",
            {
                "scenario_name": "test_campaign",
                "num_iterations": "2",
                "base_seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "run_monte_carlo",
            {
                "scenario_name": "test_campaign",
                "num_iterations": 2,
                "base_seed": False,
                "max_ticks": 1,
            },
        ),
        (
            "run_monte_carlo",
            {
                "scenario_name": "test_campaign",
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
                "calibration_patch": {
                    "not_a_calibration_field": 1.0,
                },
            },
        ),
        (
            "run_monte_carlo",
            {
                "scenario_name": "test_campaign",
                "num_iterations": 2,
                "base_seed": 42,
                "max_ticks": 1,
                "calibration_patch": {
                    "advance_speed": 1.0,
                },
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": (
                    "../eras/napoleonic/scenarios/austerlitz"
                ),
                "parameter_path": "hit_probability_modifier",
                "value": 1.0,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": "test_campaign",
                "parameter_path": "hit_probability_modifier",
                "value": "1.0",
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": "test_campaign",
                "parameter_path": "advance_speed",
                "value": 1.0,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": "test_campaign",
                "parameter_path": "morale.unknown_rate",
                "value": 1.0,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": "test_campaign",
                "parameter_path": "hit_probability_modifier",
                "value": 10**309,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
        (
            "modify_parameter",
            {
                "scenario_name": "test_campaign",
                "parameter_path": "hit_probability_modifier",
                "value": True,
                "seed": 42,
                "max_ticks": 1,
            },
        ),
    )

    async with create_connected_server_and_client_session(
        _create_server(),
        raise_exceptions=True,
    ) as session:
        for tool_name, arguments in invalid_calls:
            result = await session.call_tool(tool_name, arguments)
            assert result.isError is True

    assert helper_calls == []


@pytest.mark.asyncio
async def test_fastmcp_dispatch_executes_and_exposes_production_results() -> None:
    from mcp.shared.memory import (
        create_connected_server_and_client_session,
    )

    def payload(result) -> dict:
        assert result.isError is False
        assert len(result.content) == 1
        return json.loads(result.content[0].text)

    async with create_connected_server_and_client_session(
        _create_server(),
        raise_exceptions=True,
    ) as session:
        single_zero = payload(
            await session.call_tool(
                "run_scenario",
                {
                    "scenario_name": "test_campaign",
                    "seed": 42,
                    "max_ticks": 50,
                    "calibration_patch": {
                        "hit_probability_modifier": 0.0,
                    },
                },
            ),
        )
        single_ten = payload(
            await session.call_tool(
                "run_scenario",
                {
                    "scenario_name": "test_campaign",
                    "seed": 42,
                    "max_ticks": 50,
                    "calibration_patch": {
                        "hit_probability_modifier": 10.0,
                    },
                },
            ),
        )
        monte_carlo_zero = payload(
            await session.call_tool(
                "run_monte_carlo",
                {
                    "scenario_name": "test_campaign",
                    "num_iterations": 3,
                    "base_seed": 42,
                    "max_ticks": 50,
                    "calibration_patch": {
                        "hit_probability_modifier": 0.0,
                    },
                },
            ),
        )
        monte_carlo_ten = payload(
            await session.call_tool(
                "run_monte_carlo",
                {
                    "scenario_name": "test_campaign",
                    "num_iterations": 3,
                    "base_seed": 42,
                    "max_ticks": 50,
                    "calibration_patch": {
                        "hit_probability_modifier": 10.0,
                    },
                },
            ),
        )
        zero = payload(
            await session.call_tool(
                "modify_parameter",
                {
                    "scenario_name": "test_campaign",
                    "parameter_path": "hit_probability_modifier",
                    "value": 0.0,
                    "seed": 42,
                    "max_ticks": 50,
                },
            ),
        )
        ten = payload(
            await session.call_tool(
                "modify_parameter",
                {
                    "scenario_name": "test_campaign",
                    "parameter_path": "hit_probability_modifier",
                    "value": 10,
                    "seed": 42,
                    "max_ticks": 50,
                },
            ),
        )
        nested_morale = payload(
            await session.call_tool(
                "modify_parameter",
                {
                    "scenario_name": "test_campaign",
                    "parameter_path": "morale.base_degrade_rate",
                    "value": 0.9,
                    "seed": 42,
                    "max_ticks": 50,
                },
            ),
        )

    for single in (single_zero, single_ten):
        assert single["scenario_path"] == str(SCENARIO_PATH.resolve())
        assert single["max_ticks"] == 50
        assert single["ticks_executed"] == 50
        assert single["victory"]["game_over"] is True
        _assert_runtime_provenance(single["provenance"])
    assert single_zero["config_fingerprint"] != single_ten["config_fingerprint"]
    assert single_zero["sides"] != single_ten["sides"]

    for monte_carlo in (monte_carlo_zero, monte_carlo_ten):
        assert monte_carlo["scenario_path"] == str(
            SCENARIO_PATH.resolve(),
        )
        assert monte_carlo["max_ticks"] == 50
        assert monte_carlo["seeds"] == [42, 43, 44]
        assert all(len(values) == 3 for values in monte_carlo["raw_metrics"].values())
        assert len(monte_carlo["provenance"]["runs"]) == 3
        for run in monte_carlo["provenance"]["runs"]:
            _assert_runtime_provenance(run["runtime_provenance"])
    assert monte_carlo_zero["config_fingerprint"] != monte_carlo_ten["config_fingerprint"]
    assert monte_carlo_zero["raw_metrics"] != monte_carlo_ten["raw_metrics"]
    assert zero["modified"]["config_fingerprint"] != ten["modified"]["config_fingerprint"]
    assert zero["modified"]["sides"] != ten["modified"]["sides"]
    _assert_runtime_provenance(zero["modified"]["provenance"])
    _assert_runtime_provenance(ten["modified"]["provenance"])
    assert nested_morale["parameter"] == "morale.base_degrade_rate"
    assert (
        nested_morale["baseline"]["config_fingerprint"]
        != nested_morale["modified"]["config_fingerprint"]
    )
    _assert_runtime_provenance(
        nested_morale["modified"]["provenance"],
    )


def test_mcp_single_and_monte_carlo_expose_complete_provenance() -> None:
    single = json.loads(
        _tool_run_scenario("test_campaign", seed=42, max_ticks=20),
    )
    monte_carlo = json.loads(
        _tool_run_monte_carlo(
            "test_campaign",
            num_iterations=2,
            base_seed=42,
            max_ticks=20,
        ),
    )

    assert single.get("error") is not True
    assert single["scenario_path"] == str(SCENARIO_PATH.resolve())
    assert single["max_ticks"] == 20
    assert single["ticks_executed"] == 20
    assert len(single["source_fingerprint"]) == 64
    assert single["authored_roster"] == single["loaded_roster"]
    _assert_runtime_provenance(single["provenance"])

    assert monte_carlo.get("error") is not True
    assert monte_carlo["scenario_path"] == str(
        SCENARIO_PATH.resolve(),
    )
    assert monte_carlo["max_ticks"] == 20
    assert monte_carlo["seeds"] == [42, 43]
    assert monte_carlo["authored_roster"] == monte_carlo["loaded_roster"]
    assert all(len(values) == 2 for values in monte_carlo["raw_metrics"].values())
    assert all(statistics["n"] == 2 for statistics in monte_carlo["metrics"].values())
    batch_provenance = monte_carlo["provenance"]
    assert len(batch_provenance["source_fingerprint"]) == 64
    assert len(batch_provenance["data_revision"]) == 64
    assert len(batch_provenance["catalog_revision"]) == 64
    assert len(batch_provenance["doctrine_catalog_fingerprint"]) == 64
    assert len(batch_provenance["runs"]) == 2
    for run in batch_provenance["runs"]:
        _assert_runtime_provenance(run["runtime_provenance"])


def test_mcp_typed_parameter_change_affects_a_production_outcome() -> None:
    response = json.loads(
        _tool_modify_parameter(
            "test_campaign",
            "hit_probability_modifier",
            10.0,
            seed=42,
            max_ticks=200,
        ),
    )

    assert response.get("error") is not True
    assert response["baseline"]["source_fingerprint"] == response["modified"]["source_fingerprint"]
    assert response["baseline"]["config_fingerprint"] != response["modified"]["config_fingerprint"]
    assert response["baseline"]["sides"] != response["modified"]["sides"]


def test_mcp_unknown_parameter_fails_without_an_authoritative_result() -> None:
    response = json.loads(
        _tool_modify_parameter(
            "test_campaign",
            "not_a_calibration_field",
            1.0,
            seed=42,
            max_ticks=1,
        ),
    )

    assert response["error"] is True
    assert response["error_type"] == "SimulationError"
    assert "not_a_calibration_field" in response["message"]
    assert "baseline" not in response
    assert "modified" not in response
