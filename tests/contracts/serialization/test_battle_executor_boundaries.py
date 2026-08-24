"""Structural contracts for the typed battle executor boundary."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from stochastic_warfare.simulation.battle import _BattleExecutorOwnerAdapter
from stochastic_warfare.simulation.battle_executor_contracts import (
    BattleExecutorOwner,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "stochastic_warfare/simulation/battle_executor_contracts.py"
BATTLE_PATH = ROOT / "stochastic_warfare/simulation/battle.py"
EXECUTOR_PATHS = (
    ROOT / "stochastic_warfare/simulation/battle_ooda_executor.py",
    ROOT / "stochastic_warfare/simulation/battle_movement_executor.py",
    ROOT / "stochastic_warfare/simulation/battle_engagement_executor.py",
    ROOT / "stochastic_warfare/simulation/battle_checkpoint_executor.py",
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _direct_methods(class_node: ast.ClassDef) -> tuple[ast.FunctionDef, ...]:
    return tuple(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
    )


def _signature_shape(callable_value: object) -> tuple[tuple[str, object, bool], ...]:
    return tuple(
        (
            parameter.name,
            parameter.kind,
            parameter.default is inspect.Parameter.empty,
        )
        for parameter in inspect.signature(callable_value).parameters.values()
    )


def test_owner_protocol_and_adapter_use_exact_non_any_signatures() -> None:
    """The adapter implements every typed owner operation without catch-alls."""
    for path, class_name in (
        (CONTRACT_PATH, "BattleExecutorOwner"),
        (BATTLE_PATH, "_BattleExecutorOwnerAdapter"),
    ):
        class_node = _class(_tree(path), class_name)
        for method in _direct_methods(class_node):
            assert method.args.vararg is None, f"{path.name}:{method.lineno} uses *args"
            assert method.args.kwarg is None, f"{path.name}:{method.lineno} uses **kwargs"
            annotations = [
                node
                for node in ast.walk(method)
                if isinstance(node, ast.Name) and node.id == "Any"
            ]
            assert not annotations, f"{path.name}:{method.lineno} exposes Any"

    for name, protocol_member in BattleExecutorOwner.__dict__.items():
        if name.startswith("_"):
            continue
        protocol_callable = (
            protocol_member.fget
            if isinstance(protocol_member, property)
            else protocol_member
        )
        adapter_member = _BattleExecutorOwnerAdapter.__dict__.get(name)
        assert adapter_member is not None, f"adapter is missing {name}"
        adapter_callable = (
            adapter_member.fget
            if isinstance(adapter_member, property)
            else adapter_member
        )
        assert _signature_shape(adapter_callable) == _signature_shape(
            protocol_callable,
        ), f"adapter signature diverges for {name}"


def test_facade_executor_entrypoints_use_typed_context_and_completions() -> None:
    """Compatibility delegates cannot regress to untyped transaction inputs."""
    battle_class = _class(_tree(BATTLE_PATH), "BattleManager")
    methods = {method.name: method for method in _direct_methods(battle_class)}
    for method_name in (
        "execute_ooda_interval",
        "execute_tick",
        "_process_ooda_completions",
        "_execute_movement",
        "_execute_engagements",
    ):
        method = methods[method_name]
        ctx = next(argument for argument in method.args.args if argument.arg == "ctx")
        assert ctx.annotation is not None
        assert ast.unparse(ctx.annotation) == "SimulationContext"
        annotations = tuple(
            argument.annotation
            for argument in (
                *method.args.args,
                *method.args.kwonlyargs,
            )
            if argument.annotation is not None
        )
        assert not any(
            isinstance(node, ast.Name) and node.id == "Any"
            for annotation in annotations
            for node in ast.walk(annotation)
        )

    completions = next(
        argument
        for argument in methods["_process_ooda_completions"].args.args
        if argument.arg == "completions"
    )
    assert completions.annotation is not None
    assert ast.unparse(completions.annotation) == (
        "Collection[tuple[str, OODAPhase]]"
    )

    contracts_tree = _tree(CONTRACT_PATH)
    completion_request = _class(contracts_tree, "OODACompletionRequest")
    completion_field = next(
        node
        for node in completion_request.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "completions"
    )
    assert ast.unparse(completion_field.annotation) == (
        "tuple[tuple[str, OODAPhase], ...]"
    )


@pytest.mark.test_evidence("structural_only")
def test_requests_expose_only_exact_frozen_runtime_capabilities() -> None:
    """Executor envelopes cannot retain or rediscover SimulationContext."""
    contracts_tree = _tree(CONTRACT_PATH)
    runtime_classes = (
        "BattleExecutionRuntime",
        "BattleTargetingRuntime",
        "BattleOODARuntime",
        "BattleMovementRuntime",
        "BattleEngagementRuntime",
    )
    expected_requests = {
        "OODAIntervalRequest": "BattleOODARuntime",
        "OODACompletionRequest": "BattleOODARuntime",
        "MovementExecutionRequest": "BattleMovementRuntime",
        "EngagementExecutionRequest": "BattleEngagementRuntime",
    }
    for class_name in (*runtime_classes, *expected_requests):
        class_node = _class(contracts_tree, class_name)
        forbidden_names = {
            node.id
            for node in ast.walk(class_node)
            if isinstance(node, ast.Name)
            and node.id in {"Any", "SimulationContext"}
        }
        assert forbidden_names == set(), class_name
        discovery_calls = [
            node.lineno
            for node in ast.walk(class_node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
        ]
        assert discovery_calls == [], class_name

    for class_name, runtime_name in expected_requests.items():
        class_node = _class(contracts_tree, class_name)
        fields = {
            node.target.id: ast.unparse(node.annotation)
            for node in class_node.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
        }
        assert "context" not in fields
        assert fields["runtime"] == runtime_name

    for path in EXECUTOR_PATHS:
        tree = _tree(path)
        assert not any(
            isinstance(node, ast.Name) and node.id == "SimulationContext"
            for node in ast.walk(tree)
        ), path.name
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "request"
            ):
                assert node.attr != "context", f"{path.name}:{node.lineno}"
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "hasattr"}
                and node.args
                and (
                    ast.unparse(node.args[0]) in {"ctx", "runtime"}
                    or ast.unparse(node.args[0]).startswith((
                        "ctx.",
                        "runtime.",
                        "request.runtime",
                    ))
                )
            ):
                raise AssertionError(
                    f"{path.name}:{node.lineno} dynamically discovers runtime owners",
                )


@pytest.mark.test_evidence("structural_only")
def test_executors_do_not_reach_private_or_raw_manager_state() -> None:
    """Executors mutate manager state only through typed owner operations."""
    forbidden_owner_attributes = {
        "battles",
        "config",
        "pending_decisions",
        "deferred_battle_ids",
        "cached_assessments",
        "undigging",
        "concealment_scores",
        "ammo_expended",
        "suppression_states",
        "vls_launches",
        "lod_tiers",
    }
    for path in EXECUTOR_PATHS:
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Attribute):
                continue
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in {"owner", "executor_owner"}
                and node.attr in forbidden_owner_attributes
            ):
                raise AssertionError(
                    f"{path.name}:{node.lineno} reaches owner.{node.attr}",
                )
            if (
                node.attr.startswith("_")
                and not node.attr.startswith("__")
                and not (
                    isinstance(node.value, ast.Name)
                    and node.value.id in {"self", "cls"}
                )
            ):
                raise AssertionError(
                    f"{path.name}:{node.lineno} reaches private {node.attr}",
                )


def test_facade_uses_public_defining_owner_commands() -> None:
    """Known cross-owner mutations cannot regress to private attributes."""
    forbidden = {
        "_active_zones",
        "_charges",
        "_default_level",
        "_mopp_levels",
    }
    violations = [
        (node.lineno, node.attr)
        for node in ast.walk(_tree(BATTLE_PATH))
        if isinstance(node, ast.Attribute) and node.attr in forbidden
    ]
    assert violations == []


def test_targeting_revalidation_annotations_preserve_tuple_order() -> None:
    """Disposition precedes attachment in both protocol and adapter."""
    for path, class_name in (
        (CONTRACT_PATH, "BattleExecutorOwner"),
        (BATTLE_PATH, "_BattleExecutorOwnerAdapter"),
    ):
        class_node = _class(_tree(path), class_name)
        method = next(
            candidate
            for candidate in _direct_methods(class_node)
            if candidate.name == "revalidate_tactical_engagement"
        )
        assert method.returns is not None
        assert ast.unparse(method.returns) == (
            "tuple[TargetingDisposition, WeaponAttachment | None]"
        )
