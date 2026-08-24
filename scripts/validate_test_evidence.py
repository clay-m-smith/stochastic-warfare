"""Audit source-local test-evidence annotations at definition scope."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from scripts.run_pytest_partition import (
        _pytest_command,
        _subprocess_environment,
    )
else:
    from run_pytest_partition import (
        _pytest_command,
        _subprocess_environment,
    )


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_MARKER = "test_evidence"
_NODE_PATTERN = re.compile(r"^(tests/[^:\s]+\.py)(?:::.*)$")
_PHASE_OWNED_TEST_PATTERN = re.compile(r"^test_(?:phase_?\d|block_?\d)")
_ROOT_TEST_DIRECTORIES = frozenset(
    {
        "tests/integration",
        "tests/unit",
        "tests/validation",
    },
)
_SUPPORTED_TEST_DIRECTORIES = frozenset(
    {
        "tests/api",
        "tests/benchmarks",
        "tests/contracts",
        "tests/e2e",
        "tests/integration",
        "tests/unit",
        "tests/validation",
    },
)
_SOURCE_CALLS = {
    "getsource",
    "getsourcelines",
    "read_text",
    "read_bytes",
    "parse",
    "signature",
    "getmembers",
    "getattr_static",
    "import_module",
}
_DIRECT_CONTEXTS = {"raises", "warns", "fail"}
_MOCK_ASSERTION_PREFIXES = (
    "assert_called",
    "assert_awaited",
    "assert_not_called",
    "assert_any_call",
    "assert_has_calls",
    "assert_any_await",
    "assert_has_awaits",
)
_MOCK_STATE_ATTRIBUTES = {
    "called",
    "call_count",
    "await_count",
    "call_args",
    "call_args_list",
    "await_args",
    "await_args_list",
    "mock_calls",
    "method_calls",
}
_SHAPE_CALLS = {
    "all",
    "any",
    "callable",
    "hasattr",
    "isinstance",
    "issubdtype",
    "issubclass",
}
_SHAPE_ATTRIBUTES = {
    "dtype",
    "ndim",
    "shape",
    "size",
}
_CLASSIFICATIONS = frozenset(
    {
        "behavioral_oracle",
        "helper_assertion",
        "invariant_only",
        "structural_only",
    },
)
_NO_DIRECT_CLASSIFICATIONS = frozenset(
    {
        "helper_assertion",
        "invariant_only",
        "structural_only",
    },
)
_WEAK_CLASSIFICATIONS = frozenset(
    {
        "behavioral_oracle",
        "structural_only",
    },
)
_GENERIC_TEST_NAMES = frozenset(
    {
        "test_case",
        "test_it",
        "test_placeholder",
        "test_something",
        "test_todo",
        "test_works",
    },
)
_INVARIANT_CONTRACT_PATTERNS = (
    re.compile(r"\bno[\s-]*ops?\b"),
    re.compile(r"\bnoop\b"),
    re.compile(r"\b(?:no|without) errors?\b"),
    re.compile(r"\b(?:does|should)(?: still)? not error\b"),
    re.compile(r"\bdoesn['’]?t error\b"),
    re.compile(r"\b(?:does|should)(?: still)? not raise\b"),
    re.compile(r"\bdoesn['’]?t raise\b"),
    re.compile(r"\bnot raised\b"),
    re.compile(r"\bwithout raising\b"),
    re.compile(r"\b(?:does|should)(?: still)? not crash\b"),
    re.compile(r"\bdoesn['’]?t crash\b"),
    re.compile(r"\bno crash\b"),
)
_BEHAVIORAL_CLAIM_PATTERNS = {
    "integration": re.compile(r"\bintegrations?\b"),
    "wiring": re.compile(r"\bwiring\b"),
    "consumption": re.compile(r"\bconsumption\b"),
    "execution": re.compile(r"\bexecution\b"),
    "production": re.compile(r"\bproduction\b"),
    "outcome": re.compile(r"\boutcomes?\b"),
    "closure": re.compile(r"\bclosure\b"),
    "exit": re.compile(r"\bexits?\b"),
}


@dataclass(frozen=True)
class EvidenceAnnotation:
    """One literal source-local evidence classification."""

    classification: str
    scope: str
    scope_id: str
    lineno: int


@dataclass(frozen=True)
class TestDefinition:
    path: str
    qualified_name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    module_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    class_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    local_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    annotation: EvidenceAnnotation | None = None
    annotation_chain: tuple[EvidenceAnnotation, ...] = ()
    structural_context: bool = False

    @property
    def definition_id(self) -> str:
        """Return the source identity shared by every parametrized case."""
        return f"{self.path}::{self.qualified_name}"

    @property
    def direct_signal(self) -> bool:
        return _has_direct_signal(self.node)

    @property
    def called_helpers_with_signal(self) -> tuple[str, ...]:
        helpers: set[str] = set()
        for child in _runtime_walk(self.node):
            if not isinstance(child, ast.Call):
                continue
            target = child.func
            helper: ast.FunctionDef | ast.AsyncFunctionDef | None = None
            if isinstance(target, ast.Name):
                helper = self.local_definitions.get(target.id) or self.module_definitions.get(target.id)
            elif (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in {"self", "cls"}
            ):
                helper = self.class_definitions.get(target.attr)
            if helper is not None and _has_direct_signal(helper):
                helpers.add(helper.name)
        return tuple(sorted(helpers))

    @property
    def weak_reasons(self) -> tuple[str, ...]:
        reasons: set[str] = set()
        if self.structural_context or _has_explicit_structural_marker(self.node):
            reasons.add("declared structural scope")
        leaves = set(_call_leaves(self.node))
        source_calls = _source_call_labels(self.node)
        if source_calls:
            reasons.add(f"source/signature/import call: {', '.join(source_calls)}")
        mock_calls = sorted(leaf for leaf in leaves if leaf.startswith(_MOCK_ASSERTION_PREFIXES))
        if mock_calls:
            reasons.add(f"mock-call oracle: {', '.join(mock_calls)}")
        attributes = {child.attr for child in ast.walk(self.node) if isinstance(child, ast.Attribute)}
        mock_state = sorted(attributes & _MOCK_STATE_ATTRIBUTES)
        if mock_state:
            reasons.add(f"mock call/await state: {', '.join(mock_state)}")
        assertions = [child for child in ast.walk(self.node) if isinstance(child, ast.Assert)]
        if (
            assertions
            and not (set(_call_leaves(self.node)) & _DIRECT_CONTEXTS)
            and not any(leaf.startswith("assert") for leaf in _call_leaves(self.node))
            and all(_is_shape_or_nonnull_assertion(assertion.test) for assertion in assertions)
        ):
            reasons.add("shape/non-null-only assertion set")
        return tuple(sorted(reasons))


def _expression_path(node: ast.expr) -> tuple[str, ...]:
    """Return an exact dotted expression path, unwrapping decorator calls."""
    while isinstance(node, ast.Call):
        node = node.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ()
    parts.append(node.id)
    return tuple(reversed(parts))


_EVIDENCE_MARKER_PATH = ("pytest", "mark", EVIDENCE_MARKER)
_STRUCTURAL_MARKER_PATH = ("pytest", "mark", "structural")


def _annotation_from_call(
    call: ast.Call,
    *,
    scope: str,
    scope_id: str,
) -> EvidenceAnnotation:
    """Parse one exact literal marker call or reject ambiguous metadata."""

    if _expression_path(call.func) != _EVIDENCE_MARKER_PATH:
        raise ValueError(f"{scope_id}: unsupported test-evidence annotation")
    if len(call.args) != 1 or call.keywords:
        raise ValueError(
            f"{scope_id}: test-evidence annotation requires one literal classification",
        )
    classification_node = call.args[0]
    if not (
        isinstance(classification_node, ast.Constant)
        and isinstance(classification_node.value, str)
    ):
        raise ValueError(
            f"{scope_id}: test-evidence classification must be a literal string",
        )
    classification = classification_node.value
    if not classification.strip():
        raise ValueError(f"{scope_id}: test-evidence classification must not be empty")
    if classification != classification.strip():
        raise ValueError(
            f"{scope_id}: test-evidence classification must not contain surrounding whitespace",
        )
    if classification not in _CLASSIFICATIONS:
        raise ValueError(
            f"{scope_id}: unknown test-evidence classification {classification!r}",
        )
    if scope != "function" and classification != "structural_only":
        raise ValueError(
            f"{scope_id}: {classification!r} is definition-local and cannot classify a {scope}",
        )
    return EvidenceAnnotation(
        classification=classification,
        scope=scope,
        scope_id=scope_id,
        lineno=call.lineno,
    )


def _decorator_annotation(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    scope: str,
    scope_id: str,
) -> EvidenceAnnotation | None:
    annotations: list[EvidenceAnnotation] = []
    for decorator in node.decorator_list:
        if _expression_path(decorator) != _EVIDENCE_MARKER_PATH:
            continue
        if not isinstance(decorator, ast.Call):
            raise ValueError(
                f"{scope_id}: test-evidence marker must be called with literal metadata",
            )
        annotations.append(
            _annotation_from_call(
                decorator,
                scope=scope,
                scope_id=scope_id,
            ),
        )
    if len(annotations) > 1:
        raise ValueError(f"{scope_id}: conflicting test-evidence annotations")
    return annotations[0] if annotations else None


def _pytestmark_values(expression: ast.expr, *, scope_id: str) -> tuple[ast.expr, ...]:
    if isinstance(expression, (ast.List, ast.Tuple)):
        return tuple(expression.elts)
    if any(
        _expression_path(child) == _EVIDENCE_MARKER_PATH
        for child in ast.walk(expression)
        if isinstance(child, ast.expr)
    ) and _expression_path(expression) != _EVIDENCE_MARKER_PATH:
        raise ValueError(
            f"{scope_id}: test-evidence marker must be a direct pytestmark value",
        )
    return (expression,)


def _module_annotation(
    tree: ast.Module,
    *,
    relative: str,
) -> EvidenceAnnotation | None:
    annotations: list[EvidenceAnnotation] = []
    scope_id = f"{relative}::<module>"
    for statement in tree.body:
        value: ast.expr | None = None
        targets: tuple[ast.expr, ...] = ()
        if isinstance(statement, ast.Assign):
            value = statement.value
            targets = tuple(statement.targets)
        elif isinstance(statement, ast.AnnAssign):
            value = statement.value
            targets = (statement.target,)
        elif isinstance(statement, ast.AugAssign):
            value = statement.value
            targets = (statement.target,)
        if value is None or not any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in targets
        ):
            continue
        for marker_value in _pytestmark_values(value, scope_id=scope_id):
            if _expression_path(marker_value) != _EVIDENCE_MARKER_PATH:
                continue
            if not isinstance(marker_value, ast.Call):
                raise ValueError(
                    f"{scope_id}: test-evidence marker must be called with literal metadata",
                )
            annotations.append(
                _annotation_from_call(
                    marker_value,
                    scope="module",
                    scope_id=scope_id,
                ),
            )
    if len(annotations) > 1:
        raise ValueError(f"{scope_id}: conflicting test-evidence annotations")
    return annotations[0] if annotations else None


def _has_explicit_structural_marker(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Recognize only the repository's exact pytest structural decorator."""
    return any(
        _expression_path(decorator) == _STRUCTURAL_MARKER_PATH
        for decorator in node.decorator_list
    )


def _call_leaf(call: ast.Call) -> str:
    target = call.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _call_leaves(node: ast.AST) -> tuple[str, ...]:
    return tuple(leaf for child in _runtime_walk(node) if isinstance(child, ast.Call) and (leaf := _call_leaf(child)))


def _is_python_source_open(call: ast.Call) -> bool:
    """Recognize read-only built-in ``open`` calls targeting Python source."""
    if not isinstance(call.func, ast.Name) or call.func.id != "open":
        return False

    path: ast.AST | None = call.args[0] if call.args else None
    mode: ast.AST | None = call.args[1] if len(call.args) > 1 else None
    for keyword in call.keywords:
        if keyword.arg == "file" and path is None:
            path = keyword.value
        elif keyword.arg == "mode" and mode is None:
            mode = keyword.value
    if path is None:
        return False

    if mode is not None:
        if not (
            isinstance(mode, ast.Constant)
            and isinstance(mode.value, str)
            and "r" in mode.value
            and not set(mode.value) & {"a", "w", "x", "+"}
        ):
            return False

    def is_dunder_file_reference(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id == "__file__") or (
            isinstance(node, ast.Attribute) and node.attr == "__file__"
        )

    if is_dunder_file_reference(path):
        return True
    if (
        isinstance(path, ast.Call)
        and _call_leaf(path) == "Path"
        and len(path.args) == 1
        and not path.keywords
        and is_dunder_file_reference(path.args[0])
    ):
        return True

    for part in ast.walk(path):
        if (
            isinstance(part, ast.Constant)
            and isinstance(part.value, str)
            and part.value.lower().endswith((".py", ".pyi"))
        ):
            return True
    return False


def _source_call_labels(node: ast.AST) -> tuple[str, ...]:
    """Return narrow labels for source and introspection calls in ``node``."""
    labels: set[str] = set()
    for child in _runtime_walk(node):
        if not isinstance(child, ast.Call):
            continue
        leaf = _call_leaf(child)
        if leaf in _SOURCE_CALLS:
            labels.add(leaf)
        if _is_python_source_open(child):
            labels.add("open-python-source")
    return tuple(sorted(labels))


def _has_direct_signal(node: ast.AST) -> bool:
    if any(isinstance(child, ast.Assert) for child in _runtime_walk(node)):
        return True
    return any(leaf in _DIRECT_CONTEXTS or leaf.startswith("assert") for leaf in _call_leaves(node))


def _assigned_names(target: ast.AST) -> set[str]:
    """Return simple names stored by an assignment target."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.List, ast.Tuple)):
        return set().union(*(_assigned_names(item) for item in target.elts))
    return set()


def _source_tainted_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Trace values assigned directly from source/introspection calls."""
    assignments: list[tuple[set[str], ast.AST]] = []
    for child in _runtime_walk(node):
        if isinstance(child, ast.Assign):
            names = set().union(*(_assigned_names(target) for target in child.targets))
            assignments.append((names, child.value))
        elif isinstance(child, ast.AnnAssign) and child.value is not None:
            assignments.append((_assigned_names(child.target), child.value))
        elif isinstance(child, ast.NamedExpr):
            assignments.append((_assigned_names(child.target), child.value))

    return set().union(
        *(
            assigned
            for assigned, value in assignments
            if _source_call_labels(value)
        ),
    )


def _behavioral_signal_reasons(definition: TestDefinition) -> tuple[str, ...]:
    """Return direct runtime oracles beyond source/mock/shape diagnostics."""
    reasons: set[str] = set()
    leaves = set(_call_leaves(definition.node))
    source_labels = set(_source_call_labels(definition.node))
    runtime_leaves = {
        leaf
        for leaf in leaves
        if leaf
        and leaf not in _DIRECT_CONTEXTS
        and leaf not in _SHAPE_CALLS
        and leaf not in _SOURCE_CALLS
        and not leaf.startswith("assert")
    }
    if "open-python-source" in source_labels:
        runtime_leaves.discard("open")
    contexts = sorted(leaves & _DIRECT_CONTEXTS)
    if contexts:
        reasons.add(f"runtime exception/warning contract: {', '.join(contexts)}")

    tainted = _source_tainted_names(definition.node)
    for assertion in (
        child
        for child in _runtime_walk(definition.node)
        if isinstance(child, ast.Assert)
    ):
        assertion_leaves = set(_call_leaves(assertion.test))
        assertion_names = {
            child.id
            for child in ast.walk(assertion.test)
            if isinstance(child, ast.Name)
        }
        assertion_attributes = {
            child.attr
            for child in ast.walk(assertion.test)
            if isinstance(child, ast.Attribute)
        }
        if _source_call_labels(assertion.test) or assertion_names & tainted:
            continue
        if (
            assertion_attributes & _MOCK_STATE_ATTRIBUTES
            or any(
                leaf.startswith(_MOCK_ASSERTION_PREFIXES)
                for leaf in assertion_leaves
            )
        ):
            continue
        if _is_shape_or_nonnull_assertion(assertion.test):
            if runtime_leaves:
                reasons.add("runtime-produced shape or presence assertion")
            continue
        reasons.add("runtime value assertion")

    if any(
        leaf.startswith("assert")
        and not leaf.startswith(_MOCK_ASSERTION_PREFIXES)
        for leaf in leaves
    ):
        reasons.add("runtime assertion API")
    return tuple(sorted(reasons))


def _runtime_walk(node: ast.AST) -> tuple[ast.AST, ...]:
    """Walk executable children without entering nested definitions."""
    walked: list[ast.AST] = []

    def visit(current: ast.AST) -> None:
        walked.append(current)
        for child in ast.iter_child_nodes(current):
            if isinstance(
                child,
                (
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.Lambda,
                ),
            ):
                continue
            visit(child)

    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        walked.append(node)
        for statement in node.body:
            if isinstance(
                statement,
                (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef),
            ):
                continue
            visit(statement)
    else:
        visit(node)
    return tuple(walked)


def _is_shape_or_nonnull_assertion(expression: ast.AST) -> bool:
    """Return true only when the whole assertion is a weak shape/type check."""
    if isinstance(expression, ast.BoolOp):
        return bool(expression.values) and all(_is_shape_or_nonnull_assertion(value) for value in expression.values)
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        return _is_shape_or_nonnull_assertion(expression.operand)
    if isinstance(expression, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return _is_shape_or_nonnull_assertion(expression.elt)
    if isinstance(expression, ast.DictComp):
        return _is_shape_or_nonnull_assertion(expression.key) and _is_shape_or_nonnull_assertion(expression.value)
    if isinstance(expression, ast.Call):
        leaf = _call_leaf(expression)
        if leaf in {"all", "any"}:
            return bool(expression.args) and all(
                _is_shape_or_nonnull_assertion(argument) for argument in expression.args
            )
        return leaf in _SHAPE_CALLS
    if isinstance(expression, ast.Attribute):
        return expression.attr in _SHAPE_ATTRIBUTES
    if not isinstance(expression, ast.Compare):
        return False

    operands = [expression.left, *expression.comparators]
    pairs = tuple(
        zip(
            operands[:-1],
            expression.ops,
            operands[1:],
            strict=True,
        )
    )
    if pairs and all(
        isinstance(operator, ast.IsNot)
        and (
            (isinstance(left, ast.Constant) and left.value is None)
            or (isinstance(right, ast.Constant) and right.value is None)
        )
        for left, operator, right in pairs
    ):
        return True

    attributes = {child.attr for child in ast.walk(expression) if isinstance(child, ast.Attribute)}
    if attributes & _SHAPE_ATTRIBUTES:
        return True

    has_zero = any(isinstance(operand, ast.Constant) and operand.value == 0 for operand in operands)
    has_nonnegative_operator = any(isinstance(operator, (ast.GtE, ast.LtE)) for operator in expression.ops)
    count_calls = {leaf for leaf in _call_leaves(expression) if leaf == "len" or "count" in leaf}
    return has_zero and has_nonnegative_operator and bool(count_calls)


def _direct_definitions(
    nodes: list[ast.stmt],
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {node.name: node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _local_definitions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def visit(current: ast.AST) -> None:
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.setdefault(child.name, child)
                continue
            if isinstance(child, (ast.ClassDef, ast.Lambda)):
                continue
            visit(child)

    visit(node)
    return definitions


def _definitions_from_tree(
    relative: str,
    tree: ast.Module,
) -> dict[tuple[str, str], TestDefinition]:
    """Index tests and their nearest literal source-local classification."""
    index: dict[tuple[str, str], TestDefinition] = {}
    module_definitions = _direct_definitions(tree.body)
    module_annotation = _module_annotation(tree, relative=relative)
    declared_annotations: dict[str, EvidenceAnnotation] = {}
    used_annotation_scopes: set[str] = set()
    if module_annotation is not None:
        declared_annotations[module_annotation.scope_id] = module_annotation

    def visit(
        nodes: list[ast.stmt],
        parents: tuple[str, ...] = (),
        class_definitions: (
            dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None
        ) = None,
        annotation_chain: tuple[EvidenceAnnotation, ...] = (),
    ) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                qualified = "::".join((*parents, node.name))
                scope_id = f"{relative}::{qualified}"
                if _has_explicit_structural_marker(node):
                    raise ValueError(
                        f"{scope_id}: legacy structural marker must use "
                        f"pytest.mark.{EVIDENCE_MARKER}('structural_only')",
                    )
                annotation = _decorator_annotation(
                    node,
                    scope="class",
                    scope_id=scope_id,
                )
                if annotation is not None:
                    if (
                        annotation_chain
                        and annotation_chain[-1].classification
                        == annotation.classification
                    ):
                        raise ValueError(
                            f"{scope_id}: redundant inherited test-evidence annotation",
                        )
                    declared_annotations[scope_id] = annotation
                nested_chain = (
                    (*annotation_chain, annotation)
                    if annotation is not None
                    else annotation_chain
                )
                visit(
                    node.body,
                    (*parents, node.name),
                    _direct_definitions(node.body),
                    nested_chain,
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = "::".join((*parents, node.name))
                scope_id = f"{relative}::{qualified}"
                if _has_explicit_structural_marker(node):
                    raise ValueError(
                        f"{scope_id}: legacy structural marker must use "
                        f"pytest.mark.{EVIDENCE_MARKER}('structural_only')",
                    )
                annotation = _decorator_annotation(
                    node,
                    scope="function",
                    scope_id=scope_id,
                )
                if annotation is not None:
                    if (
                        annotation_chain
                        and annotation_chain[-1].classification
                        == annotation.classification
                    ):
                        raise ValueError(
                            f"{scope_id}: redundant inherited test-evidence annotation",
                        )
                    declared_annotations[scope_id] = annotation
                effective_chain = (
                    (*annotation_chain, annotation)
                    if annotation is not None
                    else annotation_chain
                )
                if node.name.startswith("test"):
                    used_annotation_scopes.update(
                        item.scope_id for item in effective_chain
                    )
                    index[(relative, qualified)] = TestDefinition(
                        path=relative,
                        qualified_name=qualified,
                        node=node,
                        module_definitions=module_definitions,
                        class_definitions=class_definitions or {},
                        local_definitions=_local_definitions(node),
                        annotation=(
                            effective_chain[-1]
                            if effective_chain
                            else None
                        ),
                        annotation_chain=effective_chain,
                        structural_context=any(
                            item.classification == "structural_only"
                            for item in effective_chain
                        ),
                    )

    initial_chain = (
        (module_annotation,) if module_annotation is not None else ()
    )
    visit(tree.body, annotation_chain=initial_chain)
    unused = sorted(set(declared_annotations) - used_annotation_scopes)
    if unused:
        raise ValueError(
            "stale test-evidence annotations do not classify a test "
            f"definition: {unused[:20]}",
        )
    return index


def _definition_index() -> dict[tuple[str, str], TestDefinition]:
    index: dict[tuple[str, str], TestDefinition] = {}
    paths = sorted((ROOT / "tests").rglob("test_*.py"))
    _validate_durable_test_paths(paths)
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        index.update(_definitions_from_tree(relative, tree))
    return index


def _validate_durable_test_paths(paths: list[Path]) -> None:
    """Reject active tests without a durable subsystem owner."""
    relative_paths = [
        path.relative_to(ROOT) if path.is_absolute() else path
        for path in paths
    ]
    unsupported = sorted(
        path.as_posix()
        for path in relative_paths
        if (
            len(path.parts) < 2
            or "/".join(path.parts[:2])
            not in _SUPPORTED_TEST_DIRECTORIES
        )
    )
    if unsupported:
        raise ValueError(
            "active tests must live under a supported top-level test "
            f"boundary: {unsupported[:20]}",
        )
    phase_owned = sorted(
        path.as_posix()
        for path in relative_paths
        if _PHASE_OWNED_TEST_PATTERN.match(path.name)
    )
    if phase_owned:
        raise ValueError(
            "active tests must be owned by a durable product boundary, not a "
            f"phase or block number: {phase_owned[:20]}",
        )
    root_owned = sorted(
        path.as_posix()
        for path in relative_paths
        if path.parent.as_posix() in _ROOT_TEST_DIRECTORIES
    )
    if root_owned:
        raise ValueError(
            "unit, integration, and validation tests must live below a "
            f"durable subsystem directory: {root_owned[:20]}",
        )


def _collect_node_ids(
    *,
    marker: str | None = None,
) -> tuple[list[str], str]:
    arguments = ["--collect-only", "-q"]
    if marker is not None:
        arguments.extend(["-m", marker])
    command = _pytest_command(*arguments)
    with tempfile.TemporaryDirectory(
        prefix="stochastic-warfare-evidence-pycache-",
    ) as pycache_prefix:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=_subprocess_environment(pycache_prefix),
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"pytest collection failed ({result.returncode})\n"
            f"command: {' '.join(command)}\n{result.stdout}\n{result.stderr}"
        )
    node_ids = sorted(line.strip() for line in result.stdout.splitlines() if _NODE_PATTERN.match(line.strip()))
    if not node_ids:
        raise RuntimeError(f"pytest collection returned no node IDs: {' '.join(command)}")
    return node_ids, " ".join(command)


def definition_id_from_node_id(node_id: str) -> str:
    """Collapse one collected pytest node ID to its source definition ID."""
    definition_id = node_id.split("[", 1)[0]
    parts = definition_id.split("::")
    if len(parts) < 2:
        raise ValueError(f"invalid pytest node ID: {node_id}")
    return "::".join(parts)


def _definition_for_id(
    identifier: str,
    index: dict[tuple[str, str], TestDefinition],
) -> TestDefinition:
    definition_id = definition_id_from_node_id(identifier)
    parts = definition_id.split("::")
    path = parts[0]
    qualified_parts = parts[1:]
    key = (path, "::".join(qualified_parts))
    try:
        return index[key]
    except KeyError as error:
        raise ValueError(
            f"no source test definition found for {definition_id}",
        ) from error


def _normalized_contract_text(definition: TestDefinition) -> str:
    """Return searchable test-name/docstring text with stable token boundaries."""
    qualified_name = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        " ",
        definition.qualified_name,
    )
    docstring = ast.get_docstring(definition.node) or ""
    return re.sub(
        r"[_:\-]+",
        " ",
        f"{qualified_name} {docstring}",
    ).lower()


def _has_meaningful_review_intent(definition: TestDefinition) -> bool:
    """Require an informative test name or an explicit contract docstring."""
    function_name = definition.qualified_name.rsplit("::", 1)[-1].lower()
    docstring = (ast.get_docstring(definition.node) or "").strip()
    if docstring:
        return True
    if function_name in _GENERIC_TEST_NAMES:
        return False
    intent = function_name.removeprefix("test_")
    return any(character.isalnum() for character in intent)


def _invariant_contract_violations(
    definition: TestDefinition,
) -> tuple[str, ...]:
    """Reject invariant-only labels that conceal a behavioral evidence claim."""
    contract_text = _normalized_contract_text(definition)
    violations: list[str] = []
    if not any(pattern.search(contract_text) for pattern in _INVARIANT_CONTRACT_PATTERNS):
        violations.append(
            "does not explicitly name a no-raise, no-error, no-crash, or no-op invariant",
        )

    claim_terms = tuple(name for name, pattern in _BEHAVIORAL_CLAIM_PATTERNS.items() if pattern.search(contract_text))
    if claim_terms:
        violations.append(
            f"name/docstring claims behavioral evidence ({', '.join(claim_terms)})",
        )
    return tuple(violations)


def _derived_candidates() -> tuple[
    list[TestDefinition],
    list[TestDefinition],
    str,
    dict[tuple[str, str], TestDefinition],
    list[str],
]:
    node_ids, command = _collect_node_ids()
    index = _definition_index()
    no_direct: list[TestDefinition] = []
    weak: list[TestDefinition] = []
    collected_definition_ids = sorted(
        {definition_id_from_node_id(node_id) for node_id in node_ids},
    )
    for definition_id in collected_definition_ids:
        definition = _definition_for_id(definition_id, index)
        if not definition.direct_signal:
            no_direct.append(definition)
        if definition.weak_reasons:
            weak.append(definition)
    return no_direct, weak, command, index, node_ids


def _validate_source_annotations(
    *,
    no_direct: list[TestDefinition],
    weak: list[TestDefinition],
    definitions: dict[tuple[str, str], TestDefinition],
    collected_definition_ids: set[str],
) -> tuple[set[str], int, int, int]:
    """Require exactly one applicable annotation for every review candidate."""

    no_direct_ids = {item.definition_id for item in no_direct}
    weak_ids = {item.definition_id for item in weak}
    candidate_ids = no_direct_ids | weak_ids
    annotated = {
        definition.definition_id: definition
        for definition in definitions.values()
        if definition.annotation is not None
    }
    missing = sorted(candidate_ids - set(annotated))
    stale = sorted(set(annotated) - candidate_ids)
    uncollected = sorted(set(annotated) - collected_definition_ids)
    if missing or stale or uncollected:
        raise ValueError(
            "source-local evidence annotations disagree with current "
            f"candidates; missing={missing[:20]} stale={stale[:20]} "
            f"uncollected={uncollected[:20]}",
        )

    errors: list[str] = []
    structural_ids: set[str] = set()
    behavioral_count = 0
    annotation_scopes: set[str] = set()
    for definition_id in sorted(candidate_ids):
        definition = annotated[definition_id]
        annotation = definition.annotation
        if annotation is None:  # pragma: no cover - guarded above.
            continue
        classification = annotation.classification
        annotation_scopes.update(item.scope_id for item in definition.annotation_chain)
        if not _has_meaningful_review_intent(definition):
            errors.append(
                f"{definition_id}: annotated test needs a meaningful name or docstring",
            )
        if definition_id in no_direct_ids and classification not in _NO_DIRECT_CLASSIFICATIONS:
            errors.append(
                f"{definition_id}: {classification!r} cannot classify a no-direct test",
            )
        if definition_id in weak_ids and classification not in _WEAK_CLASSIFICATIONS:
            errors.append(
                f"{definition_id}: {classification!r} cannot classify a weak-oracle candidate",
            )
        if classification == "helper_assertion" and not definition.called_helpers_with_signal:
            errors.append(
                f"{definition_id}: helper_assertion has no called local assertion helper",
            )
        if classification == "behavioral_oracle":
            if not definition.direct_signal:
                errors.append(
                    f"{definition_id}: behavioral_oracle has no direct runtime signal",
                )
            elif not _behavioral_signal_reasons(definition):
                errors.append(
                    f"{definition_id}: behavioral_oracle is only source, mock, or shape evidence",
                )
        if classification == "invariant_only":
            violations = _invariant_contract_violations(definition)
            if violations:
                errors.append(
                    f"{definition_id}: invalid invariant_only classification: "
                    f"{'; '.join(violations)}",
                )
        if classification == "structural_only":
            if not definition.weak_reasons:
                errors.append(
                    f"{definition_id}: structural_only has no derived weak or structural reason",
                )
            structural_ids.add(definition_id)
        elif classification == "behavioral_oracle":
            behavioral_count += 1
    if errors:
        raise ValueError(
            f"invalid source-local evidence classifications ({len(errors)}):\n"
            + "\n".join(errors),
        )
    return structural_ids, behavioral_count, len(annotated), len(annotation_scopes)


def main() -> int:
    try:
        no_direct, weak, command, definitions, collected_nodes = (
            _derived_candidates()
        )
        collected_definition_ids = {
            definition_id_from_node_id(node_id)
            for node_id in collected_nodes
        }
        (
            structural_definition_ids,
            reviewed_behavioral_count,
            annotated_definition_count,
            annotation_scope_count,
        ) = _validate_source_annotations(
            no_direct=no_direct,
            weak=weak,
            definitions=definitions,
            collected_definition_ids=collected_definition_ids,
        )
        classification_counts = Counter(
            definition.annotation.classification
            for definition in definitions.values()
            if definition.annotation is not None
        )

        expected_structural_nodes = {
            node_id
            for node_id in collected_nodes
            if definition_id_from_node_id(node_id)
            in structural_definition_ids
        }
        collected_structural, structural_command = _collect_node_ids(
            marker="structural",
        )
        if set(collected_structural) != expected_structural_nodes:
            missing = sorted(
                expected_structural_nodes - set(collected_structural),
            )
            extra = sorted(
                set(collected_structural) - expected_structural_nodes,
            )
            raise ValueError(
                "structural marker selection disagrees with source-local "
                f"annotations; missing={missing[:20]} extra={extra[:20]}"
            )
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "collection_command": command,
                "annotated_definitions": annotated_definition_count,
                "annotation_scopes": annotation_scope_count,
                "classification_counts": dict(
                    sorted(classification_counts.items()),
                ),
                "no_direct_definitions": len(no_direct),
                "reviewed_behavioral_definitions": (
                    reviewed_behavioral_count
                ),
                "structural_command": structural_command,
                "structural_definitions": len(
                    structural_definition_ids,
                ),
                "structural_nodes": len(expected_structural_nodes),
                "weak_definitions": len(weak),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
