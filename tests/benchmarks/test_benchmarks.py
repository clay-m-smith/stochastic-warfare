"""Tests for strict benchmark gate and workload-transition evidence."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError
import yaml

from tests.benchmarks import benchmark_suite as benchmark_module
from tests.benchmarks.benchmark_suite import (
    BASELINES_PATH,
    PAIR_ORDERS,
    ROOT,
    BaselineFile,
    BenchmarkBaseline,
    BenchmarkComparisonError,
    BenchmarkPolicy,
    BenchmarkResult,
    BenchmarkTransitionError,
    ComparisonArtifact,
    DATA_DIR,
    GitIdentity,
    PairSample,
    ProductionClosureRun,
    RuntimeInputManifest,
    SCENARIOS_DIR,
    TransitionArtifact,
    TransitionFinalTreeVerification,
    TransitionPolicy,
    WorkerRun,
    _write_artifact,
    canonical_json_bytes,
    canonical_sha256,
    evaluate_paired_samples,
    run_benchmark,
    run_paired_comparison,
    run_revision_closure,
    run_revision_worker,
    run_workload_transition,
    validate_artifact,
    validate_transition_artifact,
    validate_transition_final_tree_verification,
    validate_workload_transition,
    verify_transition_final_tree,
)


def _gate_policy() -> BenchmarkPolicy:
    return BenchmarkBaseline().load()["golan_heights"].policy


def _synthetic_gate_policy() -> BenchmarkPolicy:
    payload = _gate_policy().model_dump(mode="python")
    payload["workload"] = {
        "name": "default",
        "calibration_patch": {},
    }
    return BenchmarkPolicy.model_validate(payload)


def _synthetic_transition_policy() -> TransitionPolicy:
    return TransitionPolicy.model_validate(
        {
            "policy_version": 4,
            "mode": "transition_qualified",
            "manual": False,
            "reference_commit": benchmark_module.REFERENCE_COMMIT,
            "workload": {
                "name": "default",
                "calibration_patch": {},
            },
            "closures_per_revision": 1,
        }
    )


def _worker_with_duration(
    worker: WorkerRun,
    *,
    revision: str,
    duration_s: float,
) -> WorkerRun:
    return WorkerRun.model_validate(
        {
            **worker.model_dump(mode="python"),
            "revision": revision,
            "duration_s": duration_s,
        }
    )


def _minimal_manifest() -> RuntimeInputManifest:
    payload = {
        "policy_version": 3,
        "scenario_path": "data/scenarios/test/scenario.yaml",
        "scenario_sha256": "a" * 64,
        "dependency_lock_sha256": "b" * 64,
        "seed": 42,
        "max_ticks": 20_000,
        "recorder_config": {
            "enabled": True,
            "max_events": 5_000_000,
            "snapshot_interval_ticks": 0,
        },
        "effective_inputs": {"test": True},
        "sources": [
            {
                "path": "data/scenarios/test/scenario.yaml",
                "sha256": "a" * 64,
                "mode": "100644",
                "role": "scenario",
            },
            {
                "path": "uv.lock",
                "sha256": "b" * 64,
                "mode": "100644",
                "role": "dependency_lock",
            },
        ],
    }
    return RuntimeInputManifest(
        **payload,
        fingerprint=canonical_sha256(payload),
    )


def _manifest_with_effective_inputs(
    template: RuntimeInputManifest,
    effective_inputs: dict[str, object],
    **updates: object,
) -> RuntimeInputManifest:
    payload = template.fingerprint_payload()
    payload["effective_inputs"] = effective_inputs
    payload.update(updates)
    return RuntimeInputManifest(
        **payload,
        fingerprint=canonical_sha256(payload),
    )


def _synthetic_transition_fixture() -> tuple[
    ProductionClosureRun,
    ProductionClosureRun,
    benchmark_module.WorkloadTransitionContract,
]:
    template = _minimal_manifest()
    reference_manifest = _manifest_with_effective_inputs(
        template,
        {"control": {"enabled": False}},
    )
    candidate_manifest = _manifest_with_effective_inputs(
        template,
        {"control": {"enabled": True}},
    )
    semantic = BenchmarkBaseline().load()["golan_heights"].semantic_envelope
    assert semantic is not None
    candidate_semantic = semantic.model_copy(
        update={"roster_loadout_digest": "c" * 64},
    )
    reference = ProductionClosureRun(
        revision="reference",
        commit=benchmark_module.REFERENCE_COMMIT,
        runtime_input=reference_manifest,
        semantic_envelope=semantic,
    )
    candidate = ProductionClosureRun(
        revision="candidate",
        commit="1" * 40,
        runtime_input=candidate_manifest,
        semantic_envelope=candidate_semantic,
    )
    observed = benchmark_module.compute_transition_differences(
        reference_manifest.effective_inputs,
        candidate_manifest.effective_inputs,
        surface="effective_inputs",
    )
    observed.extend(
        benchmark_module.compute_transition_differences(
            {"fingerprint": reference_manifest.fingerprint},
            {"fingerprint": candidate_manifest.fingerprint},
            surface="runtime_input",
        )
    )
    observed.extend(
        benchmark_module.compute_transition_differences(
            semantic.model_dump(mode="json"),
            candidate_semantic.model_dump(mode="json"),
            surface="semantic_envelope",
        )
    )
    classifications = {
        ("effective_inputs", "/control/enabled"): "sensing_aware_standoff_enablement",
        ("runtime_input", "/fingerprint"): "derived_runtime_input_fingerprint",
        ("semantic_envelope", "/roster_loadout_digest"): "derived_roster_loadout_digest",
    }
    approvals = [
        benchmark_module.TransitionApproval(
            surface=difference.surface,
            pointer=difference.pointer,
            operation=difference.operation,
            before_sha256=difference.before_sha256,
            after_sha256=difference.after_sha256,
            classification=classifications[(difference.surface, difference.pointer)],
            authorities=["synthetic-transition-test"],
            rationale="Synthetic exact-difference contract for harness tests.",
        )
        for difference in sorted(
            observed,
            key=lambda item: (item.surface, item.pointer),
        )
    ]
    contract = benchmark_module.WorkloadTransitionContract(
        predecessor=benchmark_module.TransitionPredecessorLineage(
            format_version=3,
            policy_version=3,
            commit="2" * 40,
            document_sha256="3" * 64,
            entry_sha256="4" * 64,
        ),
        reference=benchmark_module.TransitionEndpoint(
            runtime_input=benchmark_module.ReferenceInput(
                scenario_path=reference_manifest.scenario_path,
                scenario_sha256=reference_manifest.scenario_sha256,
                dependency_lock_sha256=(reference_manifest.dependency_lock_sha256),
                fingerprint=reference_manifest.fingerprint,
            ),
            semantic_envelope=semantic,
        ),
        candidate=benchmark_module.TransitionEndpoint(
            runtime_input=benchmark_module.ReferenceInput(
                scenario_path=candidate_manifest.scenario_path,
                scenario_sha256=candidate_manifest.scenario_sha256,
                dependency_lock_sha256=(candidate_manifest.dependency_lock_sha256),
                fingerprint=candidate_manifest.fingerprint,
            ),
            semantic_envelope=candidate_semantic,
        ),
        approvals=approvals,
    )
    return reference, candidate, contract


def _valid_pass_artifact() -> ComparisonArtifact:
    entry = BenchmarkBaseline().load()["golan_heights"]
    assert entry.policy.reference_commit is not None
    assert entry.semantic_envelope is not None
    manifest = _minimal_manifest()
    environment_payload = benchmark_module._environment_metadata().model_dump(mode="python")
    environment_payload["dependency_lock_sha256"] = manifest.dependency_lock_sha256
    environment = benchmark_module.BenchmarkEnvironment.model_validate(
        environment_payload,
    )

    reference = WorkerRun(
        revision="reference",
        commit=entry.policy.reference_commit,
        duration_s=1.0,
        runtime_input=manifest,
        semantic_envelope=entry.semantic_envelope,
    )
    candidate = WorkerRun(
        revision="candidate",
        commit="1" * 40,
        duration_s=1.1,
        runtime_input=manifest,
        semantic_envelope=entry.semantic_envelope,
    )
    pairs = [
        PairSample(
            pair_index=index,
            order=order,
            reference=reference,
            candidate=candidate,
            candidate_over_reference=1.1,
        )
        for index, order in enumerate(PAIR_ORDERS)
    ]
    decision = evaluate_paired_samples(
        entry.policy,
        reference_seconds=[1.0, 1.0, 1.0],
        candidate_seconds=[1.1, 1.1, 1.1],
    )
    baseline_source = benchmark_module._runtime_source(
        ROOT,
        BASELINES_PATH,
        role="runtime_tree",
    )
    identity_manifest = sorted(
        [*manifest.sources, baseline_source],
        key=lambda source: source.path,
    )
    return ComparisonArtifact(
        created_at_utc="2026-07-29T00:00:00+00:00",
        scenario_name="golan_heights",
        status="pass",
        errors=[],
        policy=entry.policy,
        baseline_identity=benchmark_module.BenchmarkBaselineIdentity(
            authoritative=True,
            source="checked_in",
            document_sha256=benchmark_module._file_sha256(BASELINES_PATH),
            entry_sha256=canonical_sha256(
                entry.model_dump(mode="json"),
            ),
        ),
        environment=environment,
        reference_identity=GitIdentity(
            commit=entry.policy.reference_commit,
            dirty=False,
            status=[],
            runtime_manifest=identity_manifest,
        ),
        candidate_identity=GitIdentity(
            commit=candidate.commit,
            dirty=False,
            status=[],
            runtime_manifest=identity_manifest,
        ),
        warmups={
            "reference": reference,
            "candidate": candidate,
        },
        pairs=pairs,
        decision=decision,
    )


def _valid_transition_artifact() -> TransitionArtifact:
    reference, candidate, contract = _synthetic_transition_fixture()
    policy = _synthetic_transition_policy()
    environment_payload = benchmark_module._environment_metadata().model_dump(mode="python")
    environment_payload["dependency_lock_sha256"] = reference.runtime_input.dependency_lock_sha256
    return TransitionArtifact(
        created_at_utc="2026-08-02T00:00:00+00:00",
        scenario_name="synthetic",
        status="transition_qualified",
        errors=[],
        policy=policy,
        baseline_identity=benchmark_module.BenchmarkBaselineIdentity(
            authoritative=False,
            source="custom",
            document_sha256="d" * 64,
            entry_sha256="e" * 64,
        ),
        environment=benchmark_module.BenchmarkEnvironment.model_validate(
            environment_payload,
        ),
        reference_identity=GitIdentity(
            commit=reference.commit,
            dirty=False,
            status=[],
            runtime_manifest=reference.runtime_input.sources,
        ),
        candidate_identity=GitIdentity(
            commit=candidate.commit,
            dirty=False,
            status=[],
            runtime_manifest=candidate.runtime_input.sources,
        ),
        closures={"reference": reference, "candidate": candidate},
        contract=contract,
        verified_approvals=validate_workload_transition(
            reference,
            candidate,
            contract,
        ),
        timing_assessment=benchmark_module.TransitionTimingAssessment(),
    )


def _initialize_runtime_repository(repo: Path) -> None:
    (repo / "data" / "scenarios" / "test").mkdir(parents=True)
    (repo / "stochastic_warfare").mkdir()
    (repo / "tests" / "benchmarks").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "data" / "scenarios" / "test" / "scenario.yaml").write_text(
        "terrain:\n  terrain_source: procedural\n",
        encoding="utf-8",
    )
    (repo / "stochastic_warfare" / "runtime.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (repo / "tests" / "benchmarks" / "benchmark_suite.py").write_text(
        "# benchmark worker\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "run_paired_benchmark.py").write_text(
        "# benchmark entry point\n",
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    benchmark_module._git(repo, "init")
    benchmark_module._git(repo, "config", "user.name", "Phase 112 Test")
    benchmark_module._git(
        repo,
        "config",
        "user.email",
        "phase112@example.invalid",
    )
    benchmark_module._git(repo, "add", ".")
    benchmark_module._git(repo, "commit", "-m", "initial runtime")


def _runtime_input_for_identity(
    identity: GitIdentity,
) -> RuntimeInputManifest:
    sources_by_path = {source.path: source for source in identity.runtime_manifest}
    scenario_path = "data/scenarios/test/scenario.yaml"
    scenario_source = sources_by_path[scenario_path]
    lock_source = sources_by_path["uv.lock"]
    payload = {
        "policy_version": 3,
        "scenario_path": scenario_path,
        "scenario_sha256": scenario_source.sha256,
        "dependency_lock_sha256": lock_source.sha256,
        "seed": 42,
        "max_ticks": 20_000,
        "recorder_config": {
            "enabled": True,
            "max_events": 5_000_000,
            "snapshot_interval_ticks": 0,
        },
        "effective_inputs": {"test": True, "optional": None},
        "sources": [
            {
                **scenario_source.model_dump(mode="python"),
                "role": "scenario",
            },
            {
                **lock_source.model_dump(mode="python"),
                "role": "dependency_lock",
            },
        ],
    }
    payload["sources"] = sorted(
        payload["sources"],
        key=lambda source: source["path"],
    )
    return RuntimeInputManifest(
        **payload,
        fingerprint=canonical_sha256(payload),
    )


def _pass_artifact_for_identity(
    candidate_identity: GitIdentity,
    runtime_input: RuntimeInputManifest,
    *,
    baseline_identity: (benchmark_module.BenchmarkBaselineIdentity | None) = None,
    scenario_name: str = "73_easting",
    policy: BenchmarkPolicy | None = None,
) -> ComparisonArtifact:
    template = _valid_pass_artifact()
    assert template.reference_identity is not None
    assert template.environment is not None
    assert template.policy is not None
    assert template.decision is not None
    semantic_envelope = template.warmups["candidate"].semantic_envelope
    environment = template.environment.model_copy(
        update={
            "dependency_lock_sha256": (runtime_input.dependency_lock_sha256),
        },
    )
    reference = WorkerRun(
        revision="reference",
        commit=template.reference_identity.commit,
        duration_s=1.0,
        runtime_input=runtime_input,
        semantic_envelope=semantic_envelope,
    )
    candidate = WorkerRun(
        revision="candidate",
        commit=candidate_identity.commit,
        duration_s=1.1,
        runtime_input=runtime_input,
        semantic_envelope=semantic_envelope,
    )
    return ComparisonArtifact(
        created_at_utc="2026-07-29T00:00:00+00:00",
        scenario_name=scenario_name,
        status="pass",
        errors=[],
        policy=policy or template.policy,
        baseline_identity=baseline_identity or template.baseline_identity,
        environment=environment,
        reference_identity=GitIdentity(
            commit=reference.commit,
            dirty=False,
            status=[],
            runtime_manifest=candidate_identity.runtime_manifest,
        ),
        candidate_identity=candidate_identity,
        warmups={
            "reference": reference,
            "candidate": candidate,
        },
        pairs=[
            PairSample(
                pair_index=index,
                order=order,
                reference=reference,
                candidate=candidate,
                candidate_over_reference=1.1,
            )
            for index, order in enumerate(PAIR_ORDERS)
        ],
        decision=template.decision,
    )


def _write_synthetic_gate_baseline(
    path: Path,
    runtime_input: RuntimeInputManifest,
) -> benchmark_module.BaselineEntry:
    template = BenchmarkBaseline().load()["golan_heights"]
    assert template.semantic_envelope is not None
    entry = benchmark_module.BaselineEntry(
        scenario_name="synthetic",
        scenario_path=runtime_input.scenario_path,
        policy=_synthetic_gate_policy(),
        reference_input=benchmark_module.ReferenceInput(
            scenario_path=runtime_input.scenario_path,
            scenario_sha256=runtime_input.scenario_sha256,
            dependency_lock_sha256=(runtime_input.dependency_lock_sha256),
            fingerprint=runtime_input.fingerprint,
        ),
        semantic_envelope=template.semantic_envelope,
        transition_contract=None,
    )
    BenchmarkBaseline(path).save_file(
        BaselineFile(
            description="Synthetic paired-driver policy fixture.",
            entries={"synthetic": entry},
        )
    )
    return entry


def _write_synthetic_transition_baseline(
    path: Path,
    contract: benchmark_module.WorkloadTransitionContract,
) -> benchmark_module.BaselineEntry:
    entry = benchmark_module.BaselineEntry(
        scenario_name="synthetic",
        scenario_path=contract.reference.runtime_input.scenario_path,
        policy=_synthetic_transition_policy(),
        reference_input=None,
        semantic_envelope=None,
        transition_contract=contract,
    )
    BenchmarkBaseline(path).save_file(
        BaselineFile(
            description="Synthetic workload-transition policy fixture.",
            entries={"synthetic": entry},
        )
    )
    return entry


def _prepare_dirty_final_tree(
    repo: Path,
) -> tuple[
    ComparisonArtifact,
    RuntimeInputManifest,
    Path,
]:
    _initialize_runtime_repository(repo)
    (repo / "stochastic_warfare" / "runtime.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )
    initial_dirty_identity = benchmark_module._git_identity(
        repo,
        require_clean=False,
    )
    runtime_input = _runtime_input_for_identity(initial_dirty_identity)
    baseline_path = repo / "tests" / "benchmarks" / "baselines.json"
    entry = _write_synthetic_gate_baseline(
        baseline_path,
        runtime_input,
    )
    candidate_identity = benchmark_module._git_identity(
        repo,
        require_clean=False,
    )
    baseline_identity = benchmark_module.BenchmarkBaselineIdentity(
        authoritative=True,
        source="checked_in",
        document_sha256=benchmark_module._file_sha256(baseline_path),
        entry_sha256=canonical_sha256(
            entry.model_dump(mode="json"),
        ),
    )
    artifact = _pass_artifact_for_identity(
        candidate_identity,
        runtime_input,
        baseline_identity=baseline_identity,
        scenario_name="synthetic",
        policy=entry.policy,
    )
    return artifact, runtime_input, baseline_path


def _prepare_dirty_transition_tree(
    repo: Path,
) -> tuple[TransitionArtifact, RuntimeInputManifest, Path]:
    _initialize_runtime_repository(repo)
    (repo / "stochastic_warfare" / "runtime.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )
    initial_dirty_identity = benchmark_module._git_identity(
        repo,
        require_clean=False,
    )
    base_manifest = _runtime_input_for_identity(initial_dirty_identity)
    reference_manifest = _manifest_with_effective_inputs(
        base_manifest,
        {"optional": None, "test": False},
    )
    candidate_manifest = _manifest_with_effective_inputs(
        base_manifest,
        {"optional": None, "test": True},
    )
    semantic = BenchmarkBaseline().load()["golan_heights"].semantic_envelope
    assert semantic is not None
    candidate_semantic = semantic.model_copy(
        update={"roster_loadout_digest": "c" * 64},
    )
    reference = ProductionClosureRun(
        revision="reference",
        commit=benchmark_module.REFERENCE_COMMIT,
        runtime_input=reference_manifest,
        semantic_envelope=semantic,
    )
    baseline_path = repo / "tests" / "benchmarks" / "baselines.json"
    predecessor_entry = {
        "policy": {
            **_synthetic_gate_policy().model_dump(mode="json"),
            "policy_version": 3,
        },
        "reference_input": {
            "scenario_path": reference_manifest.scenario_path,
            "scenario_sha256": reference_manifest.scenario_sha256,
            "dependency_lock_sha256": (reference_manifest.dependency_lock_sha256),
            "fingerprint": reference_manifest.fingerprint,
        },
        "scenario_name": "synthetic",
        "scenario_path": reference_manifest.scenario_path,
        "semantic_envelope": semantic.model_dump(mode="json"),
    }
    predecessor_document = {
        "description": "Synthetic version-3 predecessor.",
        "entries": {"synthetic": predecessor_entry},
        "format_version": 3,
    }
    baseline_path.write_text(
        json.dumps(predecessor_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    predecessor_document_sha256 = benchmark_module._file_sha256(
        baseline_path,
    )
    benchmark_module._git(repo, "add", ".")
    benchmark_module._git(repo, "commit", "-m", "v3 predecessor baseline")
    predecessor_commit = benchmark_module._full_commit(repo)
    candidate = ProductionClosureRun(
        revision="candidate",
        commit=predecessor_commit,
        runtime_input=candidate_manifest,
        semantic_envelope=candidate_semantic,
    )
    (repo / "stochastic_warfare" / "runtime.py").write_text(
        "VALUE = 3\n",
        encoding="utf-8",
    )
    observed = benchmark_module.compute_transition_differences(
        reference_manifest.effective_inputs,
        candidate_manifest.effective_inputs,
        surface="effective_inputs",
    )
    observed.extend(
        benchmark_module.compute_transition_differences(
            {"fingerprint": reference_manifest.fingerprint},
            {"fingerprint": candidate_manifest.fingerprint},
            surface="runtime_input",
        )
    )
    observed.extend(
        benchmark_module.compute_transition_differences(
            semantic.model_dump(mode="json"),
            candidate_semantic.model_dump(mode="json"),
            surface="semantic_envelope",
        )
    )
    classifications = {
        ("effective_inputs", "/test"): "sensing_aware_standoff_enablement",
        ("runtime_input", "/fingerprint"): "derived_runtime_input_fingerprint",
        ("semantic_envelope", "/roster_loadout_digest"): "derived_roster_loadout_digest",
    }
    contract = benchmark_module.WorkloadTransitionContract(
        predecessor=benchmark_module.TransitionPredecessorLineage(
            format_version=3,
            policy_version=3,
            commit=predecessor_commit,
            document_sha256=predecessor_document_sha256,
            entry_sha256=canonical_sha256(predecessor_entry),
        ),
        reference=benchmark_module.TransitionEndpoint(
            runtime_input=benchmark_module.ReferenceInput(
                scenario_path=reference_manifest.scenario_path,
                scenario_sha256=reference_manifest.scenario_sha256,
                dependency_lock_sha256=(reference_manifest.dependency_lock_sha256),
                fingerprint=reference_manifest.fingerprint,
            ),
            semantic_envelope=semantic,
        ),
        candidate=benchmark_module.TransitionEndpoint(
            runtime_input=benchmark_module.ReferenceInput(
                scenario_path=candidate_manifest.scenario_path,
                scenario_sha256=candidate_manifest.scenario_sha256,
                dependency_lock_sha256=(candidate_manifest.dependency_lock_sha256),
                fingerprint=candidate_manifest.fingerprint,
            ),
            semantic_envelope=candidate_semantic,
        ),
        approvals=[
            benchmark_module.TransitionApproval(
                surface=difference.surface,
                pointer=difference.pointer,
                operation=difference.operation,
                before_sha256=difference.before_sha256,
                after_sha256=difference.after_sha256,
                classification=classifications[(difference.surface, difference.pointer)],
                authorities=["synthetic-transition-test"],
                rationale=("Synthetic exact-difference contract for final-tree tests."),
            )
            for difference in sorted(
                observed,
                key=lambda item: (item.surface, item.pointer),
            )
        ],
    )
    entry = _write_synthetic_transition_baseline(baseline_path, contract)
    candidate_identity = benchmark_module._git_identity(
        repo,
        require_clean=False,
    )
    environment_payload = benchmark_module._environment_metadata().model_dump(mode="python")
    environment_payload["dependency_lock_sha256"] = candidate_manifest.dependency_lock_sha256
    artifact = TransitionArtifact(
        created_at_utc="2026-08-02T00:00:00+00:00",
        scenario_name="synthetic",
        status="transition_qualified",
        errors=[],
        policy=entry.policy,
        baseline_identity=benchmark_module.BenchmarkBaselineIdentity(
            authoritative=True,
            source="checked_in",
            document_sha256=benchmark_module._file_sha256(baseline_path),
            entry_sha256=canonical_sha256(entry.model_dump(mode="json")),
        ),
        environment=benchmark_module.BenchmarkEnvironment.model_validate(
            environment_payload,
        ),
        reference_identity=GitIdentity(
            commit=reference.commit,
            dirty=False,
            status=[],
            runtime_manifest=candidate_identity.runtime_manifest,
        ),
        candidate_identity=candidate_identity,
        closures={"reference": reference, "candidate": candidate},
        contract=contract,
        verified_approvals=validate_workload_transition(
            reference,
            candidate,
            contract,
        ),
        timing_assessment=benchmark_module.TransitionTimingAssessment(),
    )
    return artifact, candidate_manifest, baseline_path


@pytest.mark.benchmark
class TestPairedPolicy:
    def test_exact_policy_contract_is_loaded(self) -> None:
        entries = BenchmarkBaseline().load()
        easting = entries["73_easting"]
        policy = easting.policy

        assert isinstance(policy, BenchmarkPolicy)
        assert policy.policy_version == 4
        assert policy.mode == "gate"
        assert policy.manual is False
        assert policy.reference_commit == (
            "271ec49ceb508bdd050e2d5c3072ac91456cca7c"
        )
        assert policy.warmup_runs_per_revision == 1
        assert policy.timed_pairs == 3
        assert policy.pair_orders == PAIR_ORDERS
        assert policy.maximum_median_slowdown_ratio == 1.20
        assert policy.maximum_relative_sample_range == 0.20
        assert policy.timing_scope == "SimulationEngine.run"
        assert policy.workload.name == "morale_neutral_control_plane"
        assert policy.workload.calibration_patch.model_dump(
            mode="python",
            exclude_none=True,
        ) == {
            "morale": {
                "base_degrade_rate": 0.0,
                "base_recover_rate": 0.0,
                "casualty_weight": 0.0,
                "suppression_weight": 0.0,
                "leadership_weight": 0.0,
                "cohesion_weight": 0.0,
                "force_ratio_weight": 0.0,
            },
        }
        assert easting.transition_contract is None
        assert easting.reference_input is not None
        assert easting.reference_input.model_dump(mode="python") == {
            "scenario_path": "data/scenarios/73_easting/scenario.yaml",
            "scenario_sha256": (
                "328467cd1f200cf2f0157da917ab20b9e9bbc43fb7ee985f5d4472d2df3cd3e5"
            ),
            "dependency_lock_sha256": (
                "bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39"
            ),
            "fingerprint": (
                "3ef1e72ff1ebdb099a6e89cc6917540f49d774593816c439bfe9e96d6d87f879"
            ),
        }
        assert easting.semantic_envelope is not None
        assert easting.semantic_envelope.model_dump(mode="python") == {
            "unit_count": 71,
            "roster_loadout_digest": (
                "1344d0fdffe8cf42cd5329a4cbc808398a449f47c14c95fb17807f671f3a32a2"
            ),
            "winner": "blue",
            "victory_condition_type": "time_expired",
            "ticks": 360,
            "logical_duration_s": 1800.0,
            "status_counts": {
                "blue": {"ACTIVE": 21},
                "red": {"ACTIVE": 50},
            },
            "event_count": 1,
            "event_digest": (
                "2784db62737dac1df07bb13e64cadb9b6b6f0d3e48cee291efcfc0d51cb8e798"
            ),
        }

        golan = entries["golan_heights"]
        assert golan.policy.mode == "gate"
        assert golan.policy.manual is True
        assert golan.policy.timed_pairs == 3
        assert golan.policy.pair_orders == PAIR_ORDERS
        assert golan.policy.maximum_median_slowdown_ratio == 1.20
        assert golan.policy.maximum_relative_sample_range == 0.20
        assert golan.policy.timing_scope == "SimulationEngine.run"
        assert entries["benchmark_battalion"].policy.mode == "measurement_only"
        assert entries["benchmark_brigade"].policy.mode == "measurement_only"
        for name in ("benchmark_battalion", "benchmark_brigade"):
            measurement = entries[name].policy
            assert isinstance(measurement, BenchmarkPolicy)
            assert measurement.timed_pairs == 3
            assert measurement.pair_orders == PAIR_ORDERS
            assert measurement.maximum_median_slowdown_ratio == 1.20
            assert measurement.maximum_relative_sample_range == 0.20
            assert measurement.timing_scope == "SimulationEngine.run"

    def test_morale_neutral_workload_rejects_every_non_73_scenario(self) -> None:
        entry = BenchmarkBaseline().load()["73_easting"]
        payload = entry.model_dump(mode="python")
        payload["scenario_name"] = "future_benchmark"

        with pytest.raises(
            ValidationError,
            match="only the routine 73_easting benchmark",
        ):
            benchmark_module.BaselineEntry.model_validate(payload)

    def test_transition_contract_is_canonical_and_rejects_unapproved_deltas(
        self,
    ) -> None:
        reference, candidate, contract = _synthetic_transition_fixture()

        validate_workload_transition(reference, candidate, contract)
        assert [approval.pointer for approval in contract.approvals] == [
            "/control/enabled",
            "/fingerprint",
            "/roster_loadout_digest",
        ]
        assert contract.approvals[0].operation == "replace"

        unexpected_manifest = _manifest_with_effective_inputs(
            candidate.runtime_input,
            {
                "control": {"enabled": True},
                "unexpected": True,
            },
        )
        unexpected_candidate = candidate.model_copy(
            update={"runtime_input": unexpected_manifest},
        )
        unexpected_contract = contract.model_copy(
            update={
                "candidate": contract.candidate.model_copy(
                    update={
                        "runtime_input": benchmark_module.ReferenceInput(
                            scenario_path=unexpected_manifest.scenario_path,
                            scenario_sha256=unexpected_manifest.scenario_sha256,
                            dependency_lock_sha256=(unexpected_manifest.dependency_lock_sha256),
                            fingerprint=unexpected_manifest.fingerprint,
                        ),
                    },
                ),
            },
        )
        with pytest.raises(ValueError, match="unapproved"):
            validate_workload_transition(
                reference,
                unexpected_candidate,
                unexpected_contract,
            )

        stale_approval = contract.approvals[0].model_copy(
            update={"pointer": "/not-observed"},
        )
        stale_contract = contract.model_copy(
            update={
                "approvals": sorted(
                    [*contract.approvals, stale_approval],
                    key=lambda approval: (
                        approval.surface,
                        approval.pointer,
                    ),
                ),
            },
        )
        with pytest.raises(ValueError, match="stale"):
            validate_workload_transition(
                reference,
                candidate,
                stale_contract,
            )
        payload = contract.model_dump(mode="python")
        payload["approvals"].append(
            copy.deepcopy(payload["approvals"][0]),
        )
        with pytest.raises(ValidationError, match="unique and surface/path-sorted"):
            benchmark_module.WorkloadTransitionContract.model_validate(payload)
        payload = contract.model_dump(mode="python")
        payload["approvals"] = []
        with pytest.raises(ValidationError, match="at least one"):
            benchmark_module.WorkloadTransitionContract.model_validate(payload)

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("operation", "remove"),
            ("before_sha256", "f" * 64),
            ("after_sha256", "f" * 64),
        ),
    )
    def test_transition_rejects_changed_approved_value_contract(
        self,
        field: str,
        value: str,
    ) -> None:
        reference, candidate, contract = _synthetic_transition_fixture()
        payload = contract.model_dump(mode="python")
        payload["approvals"][0][field] = value
        changed_contract = benchmark_module.WorkloadTransitionContract.model_validate(
            payload,
        )

        with pytest.raises(ValueError, match="differs from observed value"):
            validate_workload_transition(
                reference,
                candidate,
                changed_contract,
            )

    def test_authoritative_validator_rejects_reclassified_approval(
        self,
        tmp_path: Path,
    ) -> None:
        _reference, _candidate, contract = _synthetic_transition_fixture()
        baseline_path = tmp_path / "transition-baseline.json"
        entry = _write_synthetic_transition_baseline(
            baseline_path,
            contract,
        )
        approvals = list(contract.approvals)
        approvals[0] = approvals[0].model_copy(
            update={"classification": "vvs2_target_domain_expansion"},
        )
        reclassified = contract.model_copy(
            update={"approvals": approvals},
        )
        artifact = TransitionArtifact(
            created_at_utc="2026-08-02T00:00:00+00:00",
            scenario_name="synthetic",
            status="error",
            errors=["synthetic reclassification rejection"],
            policy=entry.policy,
            baseline_identity=benchmark_module.BenchmarkBaselineIdentity(
                authoritative=True,
                source="checked_in",
                document_sha256=benchmark_module._file_sha256(
                    baseline_path,
                ),
                entry_sha256=canonical_sha256(
                    entry.model_dump(mode="json"),
                ),
            ),
            environment=None,
            reference_identity=None,
            candidate_identity=None,
            closures={},
            contract=reclassified,
            verified_approvals=[],
            timing_assessment=benchmark_module.TransitionTimingAssessment(),
        )
        artifact_path = tmp_path / "reclassified-transition.json"
        benchmark_module._write_transition_artifact(artifact_path, artifact)

        with pytest.raises(
            ValueError,
            match="policy or contract differs from authoritative baseline",
        ):
            validate_transition_artifact(
                artifact_path,
                authoritative_baseline_path=baseline_path,
            )

    def test_predecessor_lineage_rejects_tampered_document_digest(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _reference, _candidate, contract = _synthetic_transition_fixture()
        changed_contract = contract.model_copy(
            update={
                "predecessor": (
                    contract.predecessor.model_copy(
                        update={"document_sha256": "f" * 64},
                    )
                ),
            },
        )
        monkeypatch.setattr(
            benchmark_module.subprocess,
            "run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=(b"{}\n" if "show" in command else b""),
                stderr=b"",
            ),
        )

        with pytest.raises(ValueError, match="document digest differs from git"):
            benchmark_module._verify_transition_predecessor(
                ROOT,
                scenario_name="synthetic",
                policy=_synthetic_transition_policy(),
                contract=changed_contract,
            )

    @pytest.mark.parametrize(
        "mutation",
        (
            "scenario",
            "dependency_lock",
            "seed",
            "max_ticks",
            "recorder_config",
            "sources",
        ),
    )
    def test_transition_rejects_every_immutable_runtime_input_change(
        self,
        mutation: str,
    ) -> None:
        reference, candidate, contract = _synthetic_transition_fixture()
        candidate_payload = candidate.runtime_input.fingerprint_payload()
        if mutation == "scenario":
            candidate_payload["scenario_sha256"] = "c" * 64
            candidate_payload["sources"] = [
                {
                    **source,
                    "sha256": ("c" * 64 if source["path"] == candidate_payload["scenario_path"] else source["sha256"]),
                }
                for source in candidate_payload["sources"]
            ]
        elif mutation == "dependency_lock":
            candidate_payload["dependency_lock_sha256"] = "c" * 64
            candidate_payload["sources"] = [
                {
                    **source,
                    "sha256": ("c" * 64 if source["path"] == "uv.lock" else source["sha256"]),
                }
                for source in candidate_payload["sources"]
            ]
        elif mutation == "seed":
            candidate_payload["seed"] = 43
        elif mutation == "max_ticks":
            candidate_payload["max_ticks"] = 20_001
        elif mutation == "recorder_config":
            candidate_payload["recorder_config"] = {
                **candidate_payload["recorder_config"],
                "max_events": 4_999_999,
            }
        elif mutation == "sources":
            candidate_payload["sources"] = sorted(
                [
                    *candidate_payload["sources"],
                    {
                        "path": "data/units/extra.yaml",
                        "sha256": "f" * 64,
                        "mode": "100644",
                        "role": "resolved_units",
                    },
                ],
                key=lambda source: source["path"],
            )
        else:
            raise AssertionError(mutation)
        changed_manifest = RuntimeInputManifest(
            **candidate_payload,
            fingerprint=canonical_sha256(candidate_payload),
        )
        changed_candidate = candidate.model_copy(
            update={"runtime_input": changed_manifest},
        )
        changed_contract = contract.model_copy(
            update={
                "candidate": contract.candidate.model_copy(
                    update={
                        "runtime_input": benchmark_module.ReferenceInput(
                            scenario_path=changed_manifest.scenario_path,
                            scenario_sha256=changed_manifest.scenario_sha256,
                            dependency_lock_sha256=(changed_manifest.dependency_lock_sha256),
                            fingerprint=changed_manifest.fingerprint,
                        ),
                    },
                ),
            },
        )

        with pytest.raises(ValueError, match="immutable inputs differ"):
            validate_workload_transition(
                reference,
                changed_candidate,
                changed_contract,
            )

    @pytest.mark.parametrize(
        ("pointer", "classification"),
        (("not-absolute", "valid"), ("/bad~2escape", "valid"), ("/ok", "")),
    )
    def test_transition_approval_rejects_invalid_pointer_or_classification(
        self,
        pointer: str,
        classification: str,
    ) -> None:
        with pytest.raises(ValidationError):
            benchmark_module.TransitionApproval(
                surface="effective_inputs",
                pointer=pointer,
                operation="replace",
                before_sha256="a" * 64,
                after_sha256="b" * 64,
                classification=classification,
                authorities=["synthetic-transition-test"],
                rationale="Synthetic approval validation.",
            )

    def test_transition_root_difference_uses_rfc6901_empty_pointer(self) -> None:
        differences = benchmark_module.compute_transition_differences(
            False,
            True,
            surface="effective_inputs",
        )

        assert len(differences) == 1
        assert differences[0].pointer == ""
        approval = benchmark_module.TransitionApproval(
            surface="effective_inputs",
            pointer="",
            operation=differences[0].operation,
            before_sha256=differences[0].before_sha256,
            after_sha256=differences[0].after_sha256,
            classification="sensing_aware_standoff_enablement",
            authorities=["synthetic-transition-test"],
            rationale="Synthetic root-pointer validation.",
        )
        assert approval.pointer == ""

    def test_transition_artifact_has_no_performance_claim(self) -> None:
        artifact = _valid_transition_artifact()

        assert artifact.status == "transition_qualified"
        payload = artifact.model_dump(mode="python")
        assert "pairs" not in payload
        assert "decision" not in payload
        assert "duration_s" not in payload["closures"]["reference"]
        assert payload["timing_assessment"] == {
            "applicability": "not_applicable",
            "reason": "workloads_differ",
        }
        for field, value in (
            ("pairs", []),
            ("decision", None),
            ("ratio", 1.0),
        ):
            invalid = copy.deepcopy(payload)
            invalid[field] = value
            with pytest.raises(ValidationError, match="Extra inputs"):
                TransitionArtifact.model_validate(invalid)
        invalid = copy.deepcopy(payload)
        invalid["closures"]["reference"]["duration_s"] = 1.0
        with pytest.raises(ValidationError, match="Extra inputs"):
            TransitionArtifact.model_validate(invalid)
        invalid = copy.deepcopy(payload)
        invalid["contract"] = None
        with pytest.raises(ValidationError, match="complete policy"):
            TransitionArtifact.model_validate(invalid)

    def test_transition_policy_rejects_every_timing_field(self) -> None:
        policy = _synthetic_transition_policy()
        for field, value in (
            ("timed_pairs", 0),
            ("pair_orders", []),
            ("timing_scope", None),
            ("maximum_median_slowdown_ratio", None),
        ):
            payload = policy.model_dump(mode="python")
            payload[field] = value
            with pytest.raises(ValidationError, match="Extra inputs"):
                TransitionPolicy.model_validate(payload)

    def test_gate_artifact_rejects_transition_status_and_contract(self) -> None:
        payload = _valid_pass_artifact().model_dump(mode="python")
        payload["status"] = "transition_qualified"
        with pytest.raises(ValidationError):
            ComparisonArtifact.model_validate(payload)
        payload = _valid_pass_artifact().model_dump(mode="python")
        payload["contract"] = _valid_transition_artifact().contract.model_dump(
            mode="python",
        )
        with pytest.raises(ValidationError, match="Extra inputs"):
            ComparisonArtifact.model_validate(payload)

    def test_transition_rejects_extra_semantic_difference_even_if_endpoint_bound(
        self,
    ) -> None:
        reference, candidate, contract = _synthetic_transition_fixture()
        changed_semantics = candidate.semantic_envelope.model_copy(
            update={"event_count": candidate.semantic_envelope.event_count + 1},
        )
        changed_candidate = candidate.model_copy(
            update={"semantic_envelope": changed_semantics},
        )
        changed_contract = contract.model_copy(
            update={
                "candidate": contract.candidate.model_copy(
                    update={"semantic_envelope": changed_semantics},
                ),
            },
        )

        with pytest.raises(ValueError, match="unapproved"):
            validate_workload_transition(
                reference,
                changed_candidate,
                changed_contract,
            )

    def test_compare_explicitly_rejects_transition_mode(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _reference, _candidate, contract = _synthetic_transition_fixture()
        baseline_path = tmp_path / "transition-baseline.json"
        entry = _write_synthetic_transition_baseline(
            baseline_path,
            contract,
        )
        artifact_path = tmp_path / "wrong-mode.json"
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("compare launched a transition worker"),
            ),
        )
        with pytest.raises(
            BenchmarkComparisonError,
            match="cannot run as an ordinary gate",
        ):
            run_paired_comparison(
                scenario_name=entry.scenario_name,
                candidate_root=ROOT,
                baseline_path=baseline_path,
                artifact_path=artifact_path,
                allow_dirty_candidate=True,
            )
        artifact, _ = validate_artifact(artifact_path)
        assert artifact.status == "error"
        assert artifact.pairs == []
        assert artifact.decision is None

    @pytest.mark.parametrize("late_identity_change", (False, True))
    def test_transition_driver_runs_two_closures_without_timing_workers(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        late_identity_change: bool,
    ) -> None:
        reference, candidate, contract = _synthetic_transition_fixture()
        baseline_path = tmp_path / "transition-baseline.json"
        entry = _write_synthetic_transition_baseline(
            baseline_path,
            contract,
        )
        candidate_root = tmp_path / "candidate"
        candidate_root.mkdir()
        identities = {
            "reference": GitIdentity(
                commit=reference.commit,
                dirty=False,
                status=[],
                runtime_manifest=reference.runtime_input.sources,
            ),
            "candidate": GitIdentity(
                commit=candidate.commit,
                dirty=False,
                status=[],
                runtime_manifest=candidate.runtime_input.sources,
            ),
        }
        environment = benchmark_module._environment_metadata().model_copy(
            update={
                "dependency_lock_sha256": (reference.runtime_input.dependency_lock_sha256),
            },
        )
        calls: list[str] = []
        candidate_identity_calls = 0

        def fake_identity(root: Path, **kwargs: object) -> GitIdentity:
            nonlocal candidate_identity_calls
            del kwargs
            if root.name == "reference":
                return identities["reference"]
            candidate_identity_calls += 1
            identity = identities["candidate"]
            if late_identity_change and candidate_identity_calls > 1:
                return identity.model_copy(
                    update={
                        "dirty": True,
                        "status": [" M stochastic_warfare/runtime.py"],
                    },
                )
            return identity

        def fake_closure(**kwargs: object) -> ProductionClosureRun:
            revision = str(kwargs["revision"])
            calls.append(revision)
            return reference if revision == "reference" else candidate

        monkeypatch.setattr(
            benchmark_module,
            "_environment_metadata",
            lambda _root: environment,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_scenario_external_runtime_paths",
            lambda *args: frozenset(),
        )
        monkeypatch.setattr(benchmark_module, "_git_identity", fake_identity)
        monkeypatch.setattr(
            benchmark_module,
            "_verify_transition_predecessor",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_materialize_candidate_snapshot",
            lambda **kwargs: kwargs["snapshot_root"].mkdir(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_file_sha256",
            lambda path: reference.runtime_input.dependency_lock_sha256,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_closure_subprocess",
            fake_closure,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("transition invoked timing worker"),
            ),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_runtime_tree_manifest",
            lambda root, **kwargs: candidate.runtime_input.sources,
        )
        monkeypatch.setattr(
            benchmark_module,
            "evaluate_paired_samples",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("transition invoked paired timing policy"),
            ),
        )

        artifact_path = tmp_path / "transition.json"
        if late_identity_change:
            with pytest.raises(
                BenchmarkTransitionError,
                match="ended error",
            ):
                run_workload_transition(
                    scenario_name=entry.scenario_name,
                    candidate_root=candidate_root,
                    baseline_path=baseline_path,
                    artifact_path=artifact_path,
                )
            artifact, _ = validate_transition_artifact(artifact_path)
            assert artifact.verified_approvals == []
        else:
            artifact = run_workload_transition(
                scenario_name=entry.scenario_name,
                candidate_root=candidate_root,
                baseline_path=baseline_path,
                artifact_path=artifact_path,
            )

        assert calls == ["reference", "candidate"]
        assert artifact.status == ("error" if late_identity_change else "transition_qualified")
        assert set(artifact.closures) == {"reference", "candidate"}
        assert artifact.timing_assessment.applicability == "not_applicable"

    def test_hosted_73_easting_job_declares_paired_evidence(
        self,
    ) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "benchmark.yml").read_text(
                encoding="utf-8",
            ),
        )
        steps = workflow["jobs"]["easting"]["steps"]
        run_commands = [str(step["run"]) for step in steps if "run" in step]
        assert any(
            "run_paired_benchmark.py" in command
            and "--scenario 73_easting" in command
            and " transition" not in command
            for command in run_commands
        )
        upload = next(step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact@"))
        assert upload["if"] == "always()"
        assert "paired-73-easting.json" in upload["with"]["path"]
        easting_text = json.dumps(workflow["jobs"]["easting"])
        assert "transition-73-easting" not in easting_text
        assert "run_paired_benchmark.py transition" not in easting_text
        assert "Bind comparison" in easting_text

    def test_environment_metadata_is_complete_without_nullable_hardware(self) -> None:
        metadata = benchmark_module._environment_metadata()

        for key in (
            "os",
            "kernel",
            "architecture",
            "cpu_model",
            "python_implementation",
            "python_version",
            "dependency_lock_sha256",
        ):
            value = getattr(metadata, key)
            assert isinstance(value, str)
            assert value
            assert value != "unavailable"
        assert metadata.logical_core_count > 0
        assert metadata.physical_core_count > 0
        assert metadata.physical_core_count_source in {
            "psutil",
            "linux_topology",
        }
        assert metadata.total_ram_bytes > 0
        assert metadata.total_ram_source in {"psutil", "sysconf"}
        assert metadata.runner_identity.provider in {
            "github-actions",
            "local",
        }
        assert set(metadata.runner_identity.labels) == {
            "image_os",
            "image_version",
            "runner_arch",
            "runner_environment",
            "runner_group",
            "runner_name",
            "runner_os",
        }
        assert set(metadata.dependencies) == {
            "numpy",
            "scipy",
            "networkx",
            "pydantic",
            "pyproj",
            "PyYAML",
            "shapely",
        }
        assert metadata.unprofiled_peak_memory_mb is None

    def test_missing_physical_topology_fails_instead_of_fabricating(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(sys.modules, "psutil", None)
        monkeypatch.setattr(
            benchmark_module.platform,
            "system",
            lambda: "unsupported-test-os",
        )

        with pytest.raises(RuntimeError, match="physical CPU topology"):
            benchmark_module._physical_core_count()

    def test_artifact_target_must_be_outside_measured_worktree(self) -> None:
        target = ROOT / "artifacts" / "self-dirtying-evidence.json"
        with pytest.raises(ValueError, match="outside the candidate worktree"):
            run_paired_comparison(
                scenario_name="73_easting",
                candidate_root=ROOT,
                artifact_path=target,
            )
        assert not target.exists()

    @pytest.mark.parametrize("mutate_snapshot", (False, True))
    def test_driver_runs_exact_order_and_excludes_warmups(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mutate_snapshot: bool,
    ) -> None:
        manifest = _minimal_manifest()
        entry = _write_synthetic_gate_baseline(
            tmp_path / "baseline.json",
            manifest,
        )
        candidate_root = tmp_path / "candidate"
        candidate_root.mkdir()
        reference_commit = entry.policy.reference_commit
        assert reference_commit is not None
        candidate_commit = "1" * 40
        identities = {
            "reference": GitIdentity(
                commit=reference_commit,
                dirty=False,
                status=[],
                runtime_manifest=manifest.sources,
            ),
            "candidate": GitIdentity(
                commit=candidate_commit,
                dirty=False,
                status=[],
                runtime_manifest=manifest.sources,
            ),
        }
        environment = benchmark_module._environment_metadata().model_copy(
            update={
                "dependency_lock_sha256": (manifest.dependency_lock_sha256),
            },
        )
        calls: list[str] = []
        expected_order = [
            "reference",
            "candidate",
            "reference",
            "candidate",
            "candidate",
            "reference",
            "reference",
            "candidate",
        ]

        def fake_identity(
            root: Path,
            *,
            require_clean: bool,
            external_runtime_paths: frozenset[str],
        ) -> GitIdentity:
            del require_clean, external_runtime_paths
            revision = "reference" if root.name == "reference" else "candidate"
            return identities[revision]

        def fake_worker(**kwargs: object) -> WorkerRun:
            revision = str(kwargs["revision"])
            calls.append(revision)
            call_index = len(calls) - 1
            if mutate_snapshot and call_index == 7:
                snapshot_root = Path(str(kwargs["repo_root"]))
                (snapshot_root / "mutated.py").write_text(
                    "MUTATED = True\n",
                    encoding="utf-8",
                )
            if call_index == 0:
                duration = 999.0
            elif call_index == 1:
                duration = 0.001
            else:
                duration = 1.0 if revision == "reference" else 1.1
            return WorkerRun(
                revision=revision,
                commit=identities[revision].commit,
                duration_s=duration,
                runtime_input=manifest,
                semantic_envelope=entry.semantic_envelope,
            )

        monkeypatch.setattr(
            benchmark_module,
            "_environment_metadata",
            lambda _root: environment,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_scenario_external_runtime_paths",
            lambda *args: frozenset(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git_identity",
            fake_identity,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_materialize_candidate_snapshot",
            lambda **kwargs: kwargs["snapshot_root"].mkdir(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_file_sha256",
            lambda path: manifest.dependency_lock_sha256,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            fake_worker,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_runtime_tree_manifest",
            lambda root, **kwargs: [] if (root / "mutated.py").is_file() else manifest.sources,
        )
        artifact_path = tmp_path / "paired.json"

        if mutate_snapshot:
            with pytest.raises(
                BenchmarkComparisonError,
                match="snapshot runtime manifest changed",
            ):
                run_paired_comparison(
                    scenario_name="synthetic",
                    candidate_root=candidate_root,
                    baseline_path=tmp_path / "baseline.json",
                    artifact_path=artifact_path,
                )
            artifact, _ = validate_artifact(artifact_path)
            assert artifact.status == "error"
            assert "snapshot runtime manifest changed" in artifact.errors[0]
        else:
            artifact = run_paired_comparison(
                scenario_name="synthetic",
                candidate_root=candidate_root,
                baseline_path=tmp_path / "baseline.json",
                artifact_path=artifact_path,
            )

        assert calls == expected_order
        assert artifact.status == ("error" if mutate_snapshot else "pass")
        if mutate_snapshot:
            return
        assert artifact.baseline_identity is not None
        assert artifact.baseline_identity.authoritative is False
        assert artifact.warmups["reference"].duration_s == 999.0
        assert artifact.warmups["candidate"].duration_s == 0.001
        assert artifact.decision is not None
        assert artifact.decision.ratios == pytest.approx([1.1] * 3)
        assert artifact.decision.median_ratio == pytest.approx(1.1)
        assert [pair.order for pair in artifact.pairs] == PAIR_ORDERS

    def test_driver_rejects_dependency_lock_mismatch_before_workers(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manifest = _minimal_manifest()
        entry = _write_synthetic_gate_baseline(
            tmp_path / "baseline.json",
            manifest,
        )
        candidate_root = tmp_path / "candidate"
        candidate_root.mkdir()
        assert entry.policy.reference_commit is not None
        identities = {
            "reference": GitIdentity(
                commit=entry.policy.reference_commit,
                dirty=False,
                status=[],
                runtime_manifest=manifest.sources,
            ),
            "candidate": GitIdentity(
                commit="1" * 40,
                dirty=False,
                status=[],
                runtime_manifest=manifest.sources,
            ),
        }
        environment = benchmark_module._environment_metadata().model_copy(
            update={
                "dependency_lock_sha256": (manifest.dependency_lock_sha256),
            },
        )
        worker_calls: list[str] = []

        monkeypatch.setattr(
            benchmark_module,
            "_environment_metadata",
            lambda _root: environment,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_scenario_external_runtime_paths",
            lambda *args: frozenset(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git_identity",
            lambda root, **kwargs: identities["reference" if root.name == "reference" else "candidate"],
        )
        monkeypatch.setattr(
            benchmark_module,
            "_materialize_candidate_snapshot",
            lambda **kwargs: kwargs["snapshot_root"].mkdir(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_file_sha256",
            lambda path: "a" * 64 if path.parent.name == "reference" else "b" * 64,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            lambda **kwargs: worker_calls.append(str(kwargs["revision"])),
        )
        artifact_path = tmp_path / "lock-mismatch.json"

        with pytest.raises(
            BenchmarkComparisonError,
            match="dependency locks differ",
        ):
            run_paired_comparison(
                scenario_name="synthetic",
                candidate_root=candidate_root,
                baseline_path=tmp_path / "baseline.json",
                artifact_path=artifact_path,
            )

        artifact, _ = validate_artifact(artifact_path)
        assert artifact.status == "error"
        assert "dependency locks differ" in artifact.errors[0]
        assert worker_calls == []

    @pytest.mark.parametrize(
        ("mutation", "match"),
        (
            ("environment", "environment"),
            ("worker_commit", "worker commit"),
            ("runtime_input", "runtime inputs"),
            ("semantic_envelope", "semantic envelopes"),
            ("identity_source", "not bound to the candidate runtime manifest"),
        ),
    )
    def test_pass_artifact_binds_every_identity_and_workload(
        self,
        mutation: str,
        match: str,
    ) -> None:
        payload = _valid_pass_artifact().model_dump(mode="python")
        if mutation == "environment":
            payload["environment"] = {}
        elif mutation == "worker_commit":
            payload["pairs"][1]["candidate"]["commit"] = "2" * 40
        elif mutation == "runtime_input":
            runtime_input = payload["pairs"][1]["candidate"]["runtime_input"]
            runtime_input["effective_inputs"] = {"different": True}
            fingerprint_payload = {key: value for key, value in runtime_input.items() if key != "fingerprint"}
            runtime_input["fingerprint"] = canonical_sha256(
                fingerprint_payload,
            )
        elif mutation == "semantic_envelope":
            payload["pairs"][1]["candidate"]["semantic_envelope"]["event_digest"] = "c" * 64
        elif mutation == "identity_source":
            payload["candidate_identity"]["runtime_manifest"] = []
        else:
            raise AssertionError(mutation)

        with pytest.raises(ValidationError, match=match):
            ComparisonArtifact.model_validate(payload)

    def test_faster_candidate_with_semantic_mismatch_cannot_pass(self) -> None:
        payload = _valid_pass_artifact().model_dump(mode="python")
        payload["warmups"]["candidate"]["duration_s"] = 0.5
        for pair in payload["pairs"]:
            pair["candidate"]["duration_s"] = 0.5
            pair["candidate_over_reference"] = 0.5
        payload["pairs"][1]["candidate"]["semantic_envelope"]["event_digest"] = "c" * 64
        payload["decision"] = evaluate_paired_samples(
            _gate_policy(),
            reference_seconds=[1.0, 1.0, 1.0],
            candidate_seconds=[0.5, 0.5, 0.5],
        ).model_dump(mode="python")

        with pytest.raises(ValidationError, match="semantic envelopes"):
            ComparisonArtifact.model_validate(payload)

    def test_median_paired_ratio_passes_at_boundary(self) -> None:
        decision = evaluate_paired_samples(
            _gate_policy(),
            reference_seconds=[10.0, 10.0, 10.0],
            candidate_seconds=[12.0, 12.0, 12.0],
        )

        assert decision.status == "pass"
        assert decision.median_ratio == pytest.approx(1.20)
        assert decision.reference_relative_range == 0.0
        assert decision.candidate_relative_range == 0.0

    def test_median_paired_ratio_fails_above_boundary(self) -> None:
        decision = evaluate_paired_samples(
            _gate_policy(),
            reference_seconds=[10.0, 10.0, 10.0],
            candidate_seconds=[12.01, 12.01, 12.01],
        )

        assert decision.status == "fail"
        assert decision.median_ratio > 1.20

    def test_excess_dispersion_is_inconclusive_even_when_fast(self) -> None:
        decision = evaluate_paired_samples(
            _gate_policy(),
            reference_seconds=[8.0, 10.0, 12.1],
            candidate_seconds=[7.0, 8.0, 9.0],
        )

        assert decision.status == "inconclusive"
        assert decision.reference_relative_range > 0.20

    @pytest.mark.parametrize(
        ("reference", "candidate"),
        (
            ([1.0, 1.0], [1.0, 1.0]),
            ([1.0, 1.0, 0.0], [1.0, 1.0, 1.0]),
            ([1.0, 1.0, math.inf], [1.0, 1.0, 1.0]),
            ([1.0, 1.0, 1.0], [1.0, -1.0, 1.0]),
        ),
    )
    def test_missing_or_invalid_samples_reject(
        self,
        reference: list[float],
        candidate: list[float],
    ) -> None:
        with pytest.raises(ValueError):
            evaluate_paired_samples(
                _gate_policy(),
                reference_seconds=reference,
                candidate_seconds=candidate,
            )

    def test_measurement_only_policy_cannot_make_a_decision(self) -> None:
        policy = BenchmarkBaseline().load()["benchmark_battalion"].policy
        with pytest.raises(ValueError, match="measurement_only"):
            evaluate_paired_samples(
                policy,
                reference_seconds=[1.0, 1.0, 1.0],
                candidate_seconds=[1.0, 1.0, 1.0],
            )

    def test_legacy_unpaired_helper_always_refuses(self) -> None:
        result = BenchmarkResult(
            scenario_name="golan_heights",
            unit_count=290,
            wall_clock_s=129.5,
            ticks_executed=6480,
            ticks_per_second=50.0,
            peak_memory_mb=None,
        )
        with pytest.raises(ValueError, match="unpaired"):
            BenchmarkBaseline().check_regression(
                "golan_heights",
                result,
            )


@pytest.mark.benchmark
class TestCanonicalEvidence:
    def test_canonical_json_is_order_independent_for_mappings(self) -> None:
        first = {"b": [2, 1], "a": {"z": None, "x": 1.0}}
        second = {"a": {"x": 1.0, "z": None}, "b": [2, 1]}

        assert canonical_json_bytes(first) == canonical_json_bytes(second)
        assert canonical_sha256(first) == canonical_sha256(second)

    def test_pydantic_json_projection_preserves_explicit_null(self) -> None:
        class CanonicalExample(BaseModel):
            timestamp: datetime
            optional_value: str | None = None

        value = CanonicalExample(
            timestamp=datetime(
                2026,
                7,
                29,
                tzinfo=timezone.utc,
            ),
        )

        assert canonical_json_bytes(value) == canonical_json_bytes(
            {
                "timestamp": "2026-07-29T00:00:00Z",
                "optional_value": None,
            }
        )

    @pytest.mark.parametrize("value", (math.inf, -math.inf, math.nan))
    def test_canonical_json_rejects_nonfinite_numbers(
        self,
        value: float,
    ) -> None:
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json_bytes({"value": value})

    def test_runtime_manifest_rejects_fingerprint_tampering(self) -> None:
        manifest = _minimal_manifest()
        payload = manifest.model_dump(mode="python")
        payload["fingerprint"] = "0" * 64

        with pytest.raises(ValidationError, match="fingerprint"):
            RuntimeInputManifest.model_validate(payload)

    def test_version_one_or_extra_baseline_fields_reject(
        self,
        tmp_path: Path,
    ) -> None:
        raw = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
        raw["format_version"] = 1
        raw["unexpected"] = True
        path = tmp_path / "bad-baseline.json"
        path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(ValueError, match="version-4"):
            BenchmarkBaseline(path).load_file()

    def test_artifact_digest_detects_tampering(
        self,
        tmp_path: Path,
    ) -> None:
        baseline = BenchmarkBaseline().load()["golan_heights"]
        assert baseline.reference_input is not None
        assert baseline.semantic_envelope is not None
        reference = WorkerRun(
            revision="reference",
            commit=baseline.policy.reference_commit,
            duration_s=1.0,
            runtime_input=_minimal_manifest(),
            semantic_envelope=baseline.semantic_envelope,
        )
        candidate = _worker_with_duration(
            reference,
            revision="candidate",
            duration_s=1.1,
        )
        pair = PairSample(
            pair_index=0,
            order=PAIR_ORDERS[0],
            reference=reference,
            candidate=candidate,
            candidate_over_reference=1.1,
        )
        artifact = ComparisonArtifact(
            created_at_utc="2026-07-29T00:00:00+00:00",
            scenario_name="73_easting",
            status="error",
            errors=["synthetic policy test"],
            policy=baseline.policy,
            baseline_identity=None,
            environment=None,
            reference_identity=None,
            candidate_identity=None,
            warmups={},
            pairs=[pair],
            decision=None,
        )
        path = tmp_path / "artifact.json"
        _write_artifact(path, artifact)
        validated, digest = validate_artifact(path)
        assert validated == artifact
        assert len(digest) == 64

        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["status"] = "pass"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ValueError, match="digest"):
            validate_artifact(path)


@pytest.mark.benchmark
class TestRuntimeClosure:
    @pytest.mark.parametrize(
        "relative_path",
        (
            "data/terrain/a.hgt",
            "data/terrain/a.tif",
            "data/terrain/a.tiff",
            "data/terrain/a.geojson",
            "data/terrain/a.nc",
            "data/terrain/a.netcdf",
            "data/terrain/a.npz",
        ),
    )
    def test_loader_consumed_formats_are_declared(
        self,
        relative_path: str,
    ) -> None:
        assert benchmark_module._is_loader_data_path(relative_path)

    def test_resolved_data_sources_exclude_validation_evidence(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        scenario = repo / "data/scenarios/test/scenario.yaml"
        selected = repo / "data/units/selected.yaml"
        unrelated = repo / "data/units/unrelated.yaml"
        validation = repo / "data/validation/historical_studies/control.yaml"
        terrain = repo / "data/terrain/selected.hgt"

        for path in (scenario, selected, unrelated, validation, terrain):
            path.parent.mkdir(parents=True, exist_ok=True)

        scenario.write_text("name: Synthetic closure\n", encoding="utf-8")
        selected.write_text("unit_type: selected_unit\n", encoding="utf-8")
        unrelated.write_text("unit_type: unrelated_unit\n", encoding="utf-8")
        validation.write_text(
            "study_id: synthetic-control\nscenario_id: selected_unit\n",
            encoding="utf-8",
        )
        terrain.write_bytes(b"selected terrain")
        (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")

        sources = benchmark_module._resolved_data_sources(
            repo,
            scenario,
            {"selected_unit"},
            frozenset({"data/terrain/selected.hgt"}),
        )

        assert [(source.path, source.role) for source in sources] == [
            ("data/scenarios/test/scenario.yaml", "scenario"),
            ("data/terrain/selected.hgt", "external_runtime_input"),
            ("data/units/selected.yaml", "resolved_units"),
            ("uv.lock", "dependency_lock"),
        ]

    def test_working_tree_mode_and_type_are_exact(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        _initialize_runtime_repository(repo)
        runtime_path = repo / "stochastic_warfare" / "runtime.py"

        original = benchmark_module._git_identity(
            repo,
            require_clean=True,
        )
        runtime_path.chmod(0o755)
        dirty = benchmark_module._git_identity(
            repo,
            require_clean=False,
        )

        original_source = {source.path: source for source in original.runtime_manifest}["stochastic_warfare/runtime.py"]
        dirty_source = {source.path: source for source in dirty.runtime_manifest}["stochastic_warfare/runtime.py"]
        assert original_source.mode == "100644"
        assert dirty_source.mode == "100755"
        with pytest.raises(ValueError, match="worktree is dirty"):
            benchmark_module._git_identity(
                repo,
                require_clean=True,
            )

        link_path = repo / "stochastic_warfare" / "linked.py"
        link_path.symlink_to(runtime_path.name)
        with pytest.raises(ValueError, match="symlinks are unsupported"):
            benchmark_module._git_identity(
                repo,
                require_clean=False,
            )

    def test_candidate_snapshot_is_exact_and_immutable(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        snapshot = tmp_path / "snapshot"
        _initialize_runtime_repository(repo)
        runtime_path = repo / "stochastic_warfare" / "runtime.py"
        runtime_path.write_text("VALUE = 2\n", encoding="utf-8")
        identity = benchmark_module._git_identity(
            repo,
            require_clean=False,
        )

        benchmark_module._materialize_candidate_snapshot(
            candidate_root=repo,
            snapshot_root=snapshot,
            identity=identity,
            scenario_relative="data/scenarios/test/scenario.yaml",
            external_runtime_paths=frozenset(),
        )
        assert benchmark_module._runtime_tree_manifest(snapshot) == (identity.runtime_manifest)
        snapshot_runtime = snapshot / "stochastic_warfare" / "runtime.py"
        assert snapshot_runtime.read_text(encoding="utf-8") == "VALUE = 2\n"

        runtime_path.write_text("VALUE = 3\n", encoding="utf-8")
        assert snapshot_runtime.read_text(encoding="utf-8") == "VALUE = 2\n"

    def test_ignored_external_cache_is_scenario_closure_aware(
        self,
        tmp_path: Path,
    ) -> None:
        from stochastic_warfare.terrain.data_pipeline import (
            BoundingBox,
            compute_cache_key,
        )

        repo = tmp_path / "repo"
        _initialize_runtime_repository(repo)
        (repo / ".gitignore").write_text(
            "data/terrain_cache/\n",
            encoding="utf-8",
        )
        cache_dir = repo / "data" / "terrain_cache"
        cache_dir.mkdir(parents=True)
        unrelated_cache = cache_dir / "unrelated.npz"
        unrelated_cache.write_bytes(b"ignored procedural cache")
        scenario_relative = "data/scenarios/test/scenario.yaml"

        procedural_paths = benchmark_module._scenario_external_runtime_paths(
            repo,
            scenario_relative,
        )
        assert procedural_paths == frozenset()
        procedural_identity = benchmark_module._git_identity(
            repo,
            require_clean=False,
            external_runtime_paths=procedural_paths,
        )
        assert all(source.path != "data/terrain_cache/unrelated.npz" for source in procedural_identity.runtime_manifest)

        scenario_path = repo / scenario_relative
        scenario_path.write_text(
            "latitude: 29.5\n"
            "longitude: 46.5\n"
            "terrain:\n"
            "  terrain_source: real\n"
            "  width_m: 1000.0\n"
            "  height_m: 1000.0\n"
            "  cell_size_m: 100.0\n",
            encoding="utf-8",
        )
        raw_tile = repo / "data" / "terrain_raw" / "srtm" / "N29E046.hgt"
        raw_tile.parent.mkdir(parents=True)
        raw_tile.write_bytes(b"synthetic SRTM identity")
        half_height = (1000.0 / 2.0) / 111_320.0
        half_width = (1000.0 / 2.0) / (111_320.0 * math.cos(math.radians(29.5)))
        bbox = BoundingBox(
            south=29.5 - half_height,
            west=46.5 - half_width,
            north=29.5 + half_height,
            east=46.5 + half_width,
        )
        cache_key = compute_cache_key("srtm", bbox, 100.0)
        selected_cache = cache_dir / f"srtm_{cache_key}.npz"
        selected_cache.write_bytes(b"selected cache")

        external_paths = benchmark_module._scenario_external_runtime_paths(
            repo,
            scenario_relative,
        )
        assert raw_tile.relative_to(repo).as_posix() in external_paths
        assert selected_cache.relative_to(repo).as_posix() in external_paths
        with pytest.raises(
            ValueError,
            match="ignored runtime-affecting",
        ):
            benchmark_module._git_identity(
                repo,
                require_clean=False,
                external_runtime_paths=external_paths,
            )

    def test_strict_recorder_rejects_fallback_and_capacity_drop(
        self,
    ) -> None:
        from stochastic_warfare.core.events import Event, EventBus
        from stochastic_warfare.core.types import ModuleId

        @dataclass(frozen=True)
        class UnsupportedEvent(Event):
            payload: object

        class Context:
            def __init__(self) -> None:
                self.event_bus = EventBus()

        context = Context()
        recorder, _ = benchmark_module._strict_recorder(context)
        recorder.start()
        with pytest.raises(TypeError, match="canonical JSON"):
            context.event_bus.publish(
                UnsupportedEvent(
                    timestamp=datetime.now(timezone.utc),
                    source=ModuleId.CORE,
                    payload=object(),
                )
            )
        assert recorder.event_count() == 0

        capacity_context = Context()
        capacity_recorder, _ = benchmark_module._strict_recorder(
            capacity_context,
        )
        capacity_recorder._config.max_events = 1
        capacity_recorder.start()
        event = Event(
            timestamp=datetime.now(timezone.utc),
            source=ModuleId.CORE,
        )
        capacity_context.event_bus.publish(event)
        with pytest.raises(RuntimeError, match="capacity would drop"):
            capacity_context.event_bus.publish(event)
        assert capacity_recorder.event_count() == 1


@pytest.mark.benchmark
class TestFinalTreeVerification:
    def test_transition_qualification_binds_to_clean_final_commit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        artifact, runtime_input, baseline_path = _prepare_dirty_transition_tree(repo)
        transition_path = tmp_path / "transition-artifact.json"
        verification_path = tmp_path / "transition-final-tree.json"
        benchmark_module._write_transition_artifact(transition_path, artifact)
        benchmark_module._git(repo, "add", ".")
        benchmark_module._git(
            repo,
            "commit",
            "-m",
            "final transition runtime tree",
        )
        final_commit = benchmark_module._full_commit(repo)
        reproduction = ProductionClosureRun(
            revision="candidate",
            commit=final_commit,
            runtime_input=runtime_input,
            semantic_envelope=(artifact.closures["candidate"].semantic_envelope),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_closure_subprocess",
            lambda **kwargs: reproduction,
        )

        verification = verify_transition_final_tree(
            transition_artifact_path=transition_path,
            verification_path=verification_path,
            final_root=repo,
        )
        validated, _ = validate_transition_final_tree_verification(
            verification_path,
            transition_artifact_path=transition_path,
            authoritative_baseline_path=baseline_path,
        )

        assert validated == verification
        assert isinstance(verification, TransitionFinalTreeVerification)
        assert verification.status == "transition_qualified"
        assert verification.transition_candidate_identity.dirty is True
        assert verification.final_identity.dirty is False
        assert verification.timing_assessment.applicability == "not_applicable"
        payload = verification.model_dump(mode="python")
        assert "reproduction_run" not in payload
        assert "duration_s" not in payload["reproduction_closure"]

    def test_dirty_precommit_artifact_binds_to_clean_final_commit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        artifact, runtime_input, baseline_path = _prepare_dirty_final_tree(repo)
        comparison_path = tmp_path / "comparison.json"
        verification_path = tmp_path / "final-tree.json"
        _write_artifact(comparison_path, artifact)
        benchmark_module._git(repo, "add", ".")
        benchmark_module._git(
            repo,
            "commit",
            "-m",
            "final runtime tree",
        )
        final_commit = benchmark_module._full_commit(repo)
        reproduction = WorkerRun(
            revision="candidate",
            commit=final_commit,
            duration_s=1.0,
            runtime_input=runtime_input,
            semantic_envelope=(artifact.warmups["candidate"].semantic_envelope),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            lambda **kwargs: reproduction,
        )

        verification = benchmark_module.verify_final_tree(
            comparison_artifact_path=comparison_path,
            verification_path=verification_path,
            final_root=repo,
        )
        validated, digest = benchmark_module.validate_final_tree_verification(
            verification_path,
            comparison_artifact_path=comparison_path,
            authoritative_baseline_path=baseline_path,
        )

        assert validated == verification
        assert verification.status == "pass"
        assert verification.comparison_candidate_identity.dirty is True
        assert verification.final_identity.dirty is False
        assert verification.comparison_candidate_identity.commit != verification.final_identity.commit
        assert (
            verification.comparison_candidate_identity.runtime_manifest == verification.final_identity.runtime_manifest
        )
        assert len(digest) == 64

    def test_final_mode_change_rejects_precommit_manifest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        artifact, _runtime_input, _baseline_path = _prepare_dirty_final_tree(repo)
        comparison_path = tmp_path / "comparison.json"
        _write_artifact(comparison_path, artifact)
        (repo / "stochastic_warfare" / "runtime.py").chmod(0o755)
        benchmark_module._git(repo, "add", ".")
        benchmark_module._git(
            repo,
            "commit",
            "-m",
            "final tree with changed mode",
        )
        worker_calls: list[str] = []
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            lambda **kwargs: worker_calls.append("called"),
        )

        with pytest.raises(
            ValueError,
            match="final runtime manifest differs",
        ):
            benchmark_module.verify_final_tree(
                comparison_artifact_path=comparison_path,
                verification_path=tmp_path / "final-tree.json",
                final_root=repo,
            )
        assert worker_calls == []

    def test_custom_baseline_cannot_yield_closure_proof(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        artifact, _runtime_input, _baseline_path = _prepare_dirty_final_tree(repo)
        assert artifact.baseline_identity is not None
        custom_artifact = artifact.model_copy(
            update={
                "baseline_identity": (
                    artifact.baseline_identity.model_copy(
                        update={
                            "authoritative": False,
                            "source": "custom",
                        },
                    )
                ),
            },
        )
        comparison_path = tmp_path / "custom-comparison.json"
        _write_artifact(comparison_path, custom_artifact)

        with pytest.raises(
            ValueError,
            match="checked-in authoritative baseline",
        ):
            benchmark_module.verify_final_tree(
                comparison_artifact_path=comparison_path,
                verification_path=tmp_path / "final-tree.json",
                final_root=repo,
            )


def test_morale_timing_identity_unifies_only_discrete_default() -> None:
    """Schema-112 implicit false matches 113 false while true stays distinct."""

    def payload(value: bool | None) -> dict[str, object]:
        morale: dict[str, object] = {}
        flat: dict[str, object] = {}
        if value is not None:
            morale["use_continuous_time"] = value
            flat["morale_use_continuous_time"] = value
        return {
            "configuration": {
                "calibration_overrides": {"morale": dict(morale)},
            },
            "calibration": {"morale": dict(morale)},
            "calibration_flat": flat,
        }

    implicit_discrete = payload(None)
    assert benchmark_module._normalize_morale_timing_identity(payload(False)) == implicit_discrete

    continuous = payload(True)
    assert benchmark_module._normalize_morale_timing_identity(continuous) == (payload(True))
    assert continuous != implicit_discrete


@pytest.mark.parametrize(
    "strict_field",
    ("strict_extraction_errors", "strict_overflow"),
)
def test_recorder_identity_unifies_only_legacy_false_strictness(
    strict_field: str,
) -> None:
    """Legacy absence equals false, while either strict mode stays distinct."""
    legacy = {
        "max_events": benchmark_module.WORKER_RECORDER_MAX_EVENTS,
        "snapshot_interval_ticks": 0,
        "enabled": True,
    }
    current_defaults = {
        **legacy,
        "strict_overflow": False,
        "strict_extraction_errors": False,
    }

    normalized_defaults = benchmark_module._normalize_recorder_config_identity(
        current_defaults,
    )
    legacy_digest = benchmark_module.canonical_sha256(legacy)
    assert normalized_defaults == legacy
    assert benchmark_module.canonical_sha256(normalized_defaults) == legacy_digest

    strict = {**current_defaults, strict_field: True}
    normalized_strict = benchmark_module._normalize_recorder_config_identity(
        strict,
    )
    assert normalized_strict[strict_field] is True
    assert benchmark_module.canonical_sha256(normalized_strict) != legacy_digest


@pytest.mark.benchmark
class TestProductionWorker:
    def test_morale_neutral_workload_executes_exact_runtime_draw_budget(
        self,
    ) -> None:
        from stochastic_warfare.core.types import ModuleId
        from stochastic_warfare.morale.state import MoraleState
        from stochastic_warfare.simulation.engine import EngineConfig
        from stochastic_warfare.simulation.runtime import (
            AnalysisVariant,
            SimulationRuntimeFactory,
        )

        entry = BenchmarkBaseline().load()["73_easting"]
        variant = AnalysisVariant(
            variant_id="morale-neutral-draw-proof",
            calibration_patch=(
                entry.policy.workload.calibration_patch.model_dump(
                    mode="python",
                    exclude_none=True,
                )
            ),
        )
        prepared = SimulationRuntimeFactory().prepare(
            ROOT / entry.scenario_path,
            DATA_DIR,
            (variant,),
        )
        session = prepared.build(
            variant.variant_id,
            seed=42,
            max_ticks=20_000,
            engine_config=EngineConfig(
                max_ticks=20_000,
                snapshot_interval_ticks=0,
            ),
            strict_mode=True,
        )
        morale_rng = session.context.rng_manager.get_stream(ModuleId.MORALE)
        expected = np.random.default_rng()
        expected.bit_generator.state = copy.deepcopy(
            morale_rng.bit_generator.state,
        )

        result = session.engine.run()

        records = tuple(session.context.morale_runtime.records.values())
        assert result.ticks_executed == 360
        assert len(records) == 71
        assert all(record.current_state is MoraleState.STEADY for record in records)
        assert all(record.generation == 30 for record in records)
        assert sum(record.generation for record in records) == 2_130
        expected.random(2_130)
        assert morale_rng.bit_generator.state == expected.bit_generator.state

    @pytest.mark.slow
    def test_exact_reference_worker_uses_historical_adapter(
        self,
        tmp_path: Path,
    ) -> None:
        reference_root = tmp_path / "reference"
        benchmark_module._git(
            ROOT,
            "clone",
            "--shared",
            "--no-checkout",
            str(ROOT),
            str(reference_root),
        )
        benchmark_module._git(
            reference_root,
            "checkout",
            "--detach",
            benchmark_module.REFERENCE_COMMIT,
        )
        run = benchmark_module._run_worker_subprocess(
            worker_path=ROOT / "tests/benchmarks/benchmark_suite.py",
            repo_root=reference_root,
            scenario_relative="data/scenarios/73_easting/scenario.yaml",
            revision="reference",
            workload=BenchmarkBaseline().load()["73_easting"].policy.workload,
            timeout_s=60.0,
        )

        assert run.commit == benchmark_module.REFERENCE_COMMIT
        assert run.runtime_input.fingerprint == (
            "9d85b6f8489e961eaf3765220d2e2672e1e8955f8a9b58827a8ce0c1b9931e77"
        )
        assert run.semantic_envelope.model_dump(mode="python") == {
            "unit_count": 71,
            "roster_loadout_digest": (
                "b598b36d78604a60cd16bd3313e29e7a8a677e2cb9b83417dc4b00cab778a1b3"
            ),
            "winner": "blue",
            "victory_condition_type": "time_expired",
            "ticks": 360,
            "logical_duration_s": 1800.0,
            "status_counts": {
                "blue": {"ACTIVE": 21},
                "red": {"ACTIVE": 50},
            },
            "event_count": 1,
            "event_digest": (
                "2784db62737dac1df07bb13e64cadb9b6b6f0d3e48cee291efcfc0d51cb8e798"
            ),
        }
        assert run.semantic_envelope.ticks == 360
        assert run.semantic_envelope.event_count == 1

    @pytest.mark.slow
    def test_promoted_reference_worker_uses_production_factory(
        self,
        tmp_path: Path,
    ) -> None:
        entry = BenchmarkBaseline().load()["73_easting"]
        assert isinstance(entry.policy, BenchmarkPolicy)
        assert entry.policy.reference_commit is not None
        assert entry.reference_input is not None
        assert entry.semantic_envelope is not None
        reference_root = tmp_path / "promoted-reference"
        benchmark_module._git(
            ROOT,
            "clone",
            "--shared",
            "--no-checkout",
            str(ROOT),
            str(reference_root),
        )
        benchmark_module._git(
            reference_root,
            "checkout",
            "--detach",
            entry.policy.reference_commit,
        )

        run = benchmark_module._run_closure_subprocess(
            worker_path=ROOT / "tests/benchmarks/benchmark_suite.py",
            repo_root=reference_root,
            scenario_relative=entry.scenario_path,
            revision="reference",
            workload=entry.policy.workload,
            timeout_s=60.0,
        )

        assert run.commit == entry.policy.reference_commit
        assert run.runtime_input.fingerprint == entry.reference_input.fingerprint
        assert run.semantic_envelope == entry.semantic_envelope

    @pytest.mark.slow
    def test_73_easting_matches_authoritative_semantics_without_timing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = BenchmarkBaseline().load()["73_easting"]
        assert entry.reference_input is not None
        assert entry.semantic_envelope is not None
        monkeypatch.setattr(
            benchmark_module,
            "_benchmark_timer",
            lambda: (_ for _ in ()).throw(
                AssertionError("duration-free closure sampled timing clock"),
            ),
        )
        run = run_revision_closure(
            repo_root=ROOT,
            scenario_relative=entry.scenario_path,
            revision="candidate",
        )

        assert run.runtime_input.fingerprint == entry.reference_input.fingerprint
        assert run.semantic_envelope == entry.semantic_envelope
        assert run.semantic_envelope.unit_count == 71
        assert run.semantic_envelope.winner == "blue"
        assert run.semantic_envelope.victory_condition_type == "time_expired"
        assert run.semantic_envelope.ticks == 360
        assert run.semantic_envelope.logical_duration_s == 1800.0
        assert run.semantic_envelope.event_count == 1

        default_run = run_revision_closure(
            repo_root=ROOT,
            scenario_relative=entry.scenario_path,
            revision="candidate",
            workload=benchmark_module.BenchmarkWorkload(
                name="default",
                calibration_patch=(benchmark_module.BenchmarkCalibrationPatch()),
            ),
        )
        assert default_run.runtime_input.fingerprint != (run.runtime_input.fingerprint)
        assert default_run.semantic_envelope.model_dump(mode="python") == {
            "unit_count": 71,
            "roster_loadout_digest": ("68efa36274ce5643f052310306a073597268c439492fc1c170c34e34a9b57645"),
            "winner": "blue",
            "victory_condition_type": "time_expired",
            "ticks": 360,
            "logical_duration_s": 1800.0,
            "status_counts": {
                "blue": {"ACTIVE": 20, "SURRENDERED": 1},
                "red": {"ACTIVE": 50},
            },
            "event_count": 120,
            "event_digest": ("fc1c92e76778571beed49e58c8f9c27fd858f2b7d4b19d9323aa079e68e125a7"),
        }

    def test_missing_scenario_fails_instead_of_skipping(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            run_revision_worker(
                repo_root=ROOT,
                scenario_relative="data/scenarios/does_not_exist/scenario.yaml",
                revision="candidate",
            )

    def test_unknown_measurement_override_fails(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            run_benchmark(
                SCENARIOS_DIR / "73_easting" / "scenario.yaml",
                profile=False,
                calibration_overrides={
                    "not_a_real_phase112_override": True,
                },
            )

    def test_unbaselined_scenario_refuses_paired_gate(
        self,
        tmp_path: Path,
    ) -> None:
        artifact = tmp_path / "measurement-only-error.json"
        with pytest.raises(BenchmarkComparisonError, match="error"):
            run_paired_comparison(
                scenario_name="benchmark_battalion",
                artifact_path=artifact,
            )
        evidence, _ = validate_artifact(artifact)
        assert evidence.status == "error"
        assert "measurement_only" in evidence.errors[0]

    def test_invalid_baseline_still_writes_a_typed_error_artifact(
        self,
        tmp_path: Path,
    ) -> None:
        artifact = tmp_path / "invalid-baseline-error.json"
        with pytest.raises(BenchmarkComparisonError, match="error"):
            run_paired_comparison(
                scenario_name="73_easting",
                baseline_path=tmp_path / "missing-baseline.json",
                artifact_path=artifact,
            )

        evidence, digest = validate_artifact(artifact)
        assert evidence.status == "error"
        assert evidence.policy is None
        assert evidence.decision is None
        assert evidence.pairs == []
        assert "not found" in evidence.errors[0]
        assert len(digest) == 64

    def test_interrupted_worker_preserves_latest_typed_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = BenchmarkBaseline().load()["golan_heights"]
        assert entry.policy.reference_commit is not None
        assert entry.semantic_envelope is not None
        reference_run = WorkerRun(
            revision="reference",
            commit=entry.policy.reference_commit,
            duration_s=1.0,
            runtime_input=_minimal_manifest(),
            semantic_envelope=entry.semantic_envelope,
        )
        complete_environment = benchmark_module._environment_metadata()

        def fake_identity(
            root: Path,
            *,
            require_clean: bool,
            external_runtime_paths: frozenset[str],
        ) -> GitIdentity:
            del require_clean, external_runtime_paths
            commit = entry.policy.reference_commit if root.name == "reference" else "1" * 40
            return GitIdentity(
                commit=commit,
                dirty=False,
                status=[],
                runtime_manifest=[],
            )

        def interrupted_worker(**kwargs: object) -> WorkerRun:
            if kwargs["revision"] == "reference":
                return reference_run
            raise KeyboardInterrupt("synthetic job-level interruption")

        monkeypatch.setattr(
            benchmark_module,
            "_environment_metadata",
            lambda _root: complete_environment,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git_identity",
            fake_identity,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_materialize_candidate_snapshot",
            lambda **kwargs: kwargs["snapshot_root"].mkdir(),
        )
        monkeypatch.setattr(
            benchmark_module,
            "_git",
            lambda *args, **kwargs: "",
        )
        monkeypatch.setattr(
            benchmark_module,
            "_file_sha256",
            lambda path: "a" * 64,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_run_worker_subprocess",
            interrupted_worker,
        )
        monkeypatch.setattr(
            benchmark_module,
            "_scenario_external_runtime_paths",
            lambda *args: frozenset(),
        )

        artifact_path = tmp_path / "interrupted.json"
        with pytest.raises(KeyboardInterrupt, match="job-level"):
            run_paired_comparison(
                scenario_name="golan_heights",
                candidate_root=ROOT,
                artifact_path=artifact_path,
                allow_dirty_candidate=True,
            )

        artifact, digest = validate_artifact(artifact_path)
        assert artifact.status == "error"
        assert artifact.errors == [
            "comparison in progress: reference warm-up completed",
        ]
        assert set(artifact.warmups) == {"reference"}
        assert artifact.pairs == []
        assert len(digest) == 64


@pytest.mark.benchmark
class TestMeasurementOnlyScenarios:
    @pytest.mark.slow
    @pytest.mark.parametrize(
        ("scenario", "expected_units"),
        (
            ("benchmark_battalion", 1000),
            ("benchmark_brigade", 5000),
        ),
    )
    def test_large_scenario_schema_and_roster_only(
        self,
        scenario: str,
        expected_units: int,
    ) -> None:
        from stochastic_warfare.simulation.scenario import ScenarioLoader

        path = SCENARIOS_DIR / scenario / "scenario.yaml"
        context = ScenarioLoader(DATA_DIR).load(path, seed=42)
        assert sum(len(units) for units in context.units_by_side.values()) == expected_units

    def test_no_synthetic_paired_error_is_suppressed(self) -> None:
        with pytest.raises(BenchmarkComparisonError):
            raise BenchmarkComparisonError("explicit harness failure")


def test_checked_in_baseline_document_is_exact_v4() -> None:
    baseline = BaselineFile.model_validate_json(
        BASELINES_PATH.read_text(encoding="utf-8"),
    )
    assert baseline.format_version == 4
    assert sorted(baseline.entries) == [
        "73_easting",
        "benchmark_battalion",
        "benchmark_brigade",
        "golan_heights",
    ]
