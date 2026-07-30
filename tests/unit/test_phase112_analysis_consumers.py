"""Production consumer proofs for the strict Phase 112 analysis boundary."""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

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
    SimulationRuntimeFactory,
    _resolve_code_revision,
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


ROOT = Path(__file__).resolve().parents[2]
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
) -> None:
    repo, _, code_marker = _initialize_identity_repo(tmp_path)
    prepared = _prepare_identity_repo(repo)

    code_marker.write_text("IDENTITY = 2\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="code changed before runtime construction",
    ):
        prepared.build("identity", seed=112, max_ticks=1)


def test_runtime_rejects_unverifiable_code_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "unversioned-data"
    data_root.mkdir()
    (data_root / "marker.txt").write_text("data\n", encoding="utf-8")
    source_config = load_campaign_scenario_config(SCENARIO_PATH)
    monkeypatch.setattr(
        runtime_module,
        "_has_git_control_marker",
        lambda start: False,
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
