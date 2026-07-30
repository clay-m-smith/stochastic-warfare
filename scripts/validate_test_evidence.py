"""Audit Phase 112 structural and weak-oracle test evidence ledgers."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "tests" / "validation" / "evidence_ledgers"
NO_DIRECT_PATH = EVIDENCE_ROOT / "no_direct_oracles.json"
WEAK_PATH = EVIDENCE_ROOT / "weak_oracles.json"
REVIEWED_BEHAVIORAL_PATH = EVIDENCE_ROOT / "reviewed_behavioral_oracles.json"
HISTORY_PATH = EVIDENCE_ROOT / "phase112_remediations.json"
PHASE_START_COMMIT = "0460ac70be86784bcc6e359ae4202f4bcb938c60"

_NODE_PATTERN = re.compile(r"^(tests/[^:\s]+\.py)(?:::.*)$")
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
_STRUCTURAL_FILES = {
    "tests/unit/test_phase78_structural.py",
    "tests/unit/test_phase_60_structural.py",
    "tests/unit/test_phase_61_structural.py",
    "tests/unit/test_phase_62_structural.py",
    "tests/unit/test_phase_63_structural.py",
    "tests/unit/test_phase_64_structural.py",
    "tests/unit/test_phase_65_structural.py",
    "tests/unit/test_phase_66_structural.py",
    "tests/validation/test_block8_exit.py",
    "tests/validation/test_calibration_coverage.py",
    "tests/validation/test_deficit_closure.py",
    "tests/validation/test_phase_67_structural.py",
    "tests/validation/test_phase112_ci_contract.py",
    "tests/validation/test_structural_audit.py",
}
_CLASSIFICATIONS = {
    "helper_assertion",
    "exception_contract",
    "invariant_only",
    "structural_only",
}
_HISTORY_ACTIONS = {"removed", "renamed", "repaired_behavioral"}
_REVIEWED_BEHAVIORAL_CLASSIFICATIONS = {"behavioral_oracle"}
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
_REQUIRED_PHASE_START_REMEDIATIONS = {
    "tests/api/test_concurrency.py::test_batch_semaphore_limits_concurrency",
    ("tests/integration/test_phase1_integration.py::TestFullTerrainStack::test_coordinate_consistency"),
    ("tests/unit/simulation/test_calibration_schema.py::TestCalibrationSchemaEdgeCases::test_dead_key_dropped"),
    ("tests/unit/test_phase_12a_c2_depth.py::TestNetworkDegradation::test_mid_load_increases_latency"),
    ("tests/unit/test_phase_17c_isr_ew.py::TestISROverpass::test_timing_gap"),
    ("tests/unit/test_phase49_calibration_schema.py::TestSchemaConstruction::test_dead_key_advance_speed_dropped"),
    ("tests/unit/test_phase50_combat_fidelity.py::TestAirPosture::test_on_station_aircraft_engages"),
    ("tests/unit/test_phase_27c_naval.py::TestNavalGun::test_event_published"),
    ("tests/unit/test_phase_64d_stratagem_activation.py::TestStratagemConcentration::test_activate_stratagem_called"),
    ("tests/unit/test_phase78_structural.py::TestFatigueTemperatureStress::test_parameter_accepted"),
    ("tests/unit/test_phase87_morale_jit.py::TestMoraleEngineIntegration::test_check_transition_uses_kernel"),
    ("tests/unit/test_phase87_morale_jit.py::TestMoraleEngineIntegration::test_continuous_mode_uses_kernel"),
    ("tests/unit/test_simulation_engine.py::TestStrategicTick::test_strategic_runs_campaign_update"),
    ("tests/unit/test_simulation_engine.py::TestEdgeCases::test_multiple_battles_simultaneously"),
}


@dataclass(frozen=True)
class TestDefinition:
    path: str
    qualified_name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    module_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    class_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    local_definitions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    enclosing_structural: bool = False

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
        phase_start_node_id = f"{self.path}::{self.qualified_name}"
        if (
            self.enclosing_structural
            or _has_explicit_structural_marker(self.node)
        ):
            reasons.add("explicit structural marker")
        if self.path in _STRUCTURAL_FILES and phase_start_node_id not in _REQUIRED_PHASE_START_REMEDIATIONS:
            reasons.add("declared structural cluster")
        leaves = set(_call_leaves(self.node))
        source_calls = sorted(leaves & _SOURCE_CALLS)
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


def _has_explicit_structural_marker(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Recognize only the repository's exact pytest structural decorator."""
    return any(_expression_path(decorator) == ("pytest", "mark", "structural") for decorator in node.decorator_list)


def _call_leaf(call: ast.Call) -> str:
    target = call.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _call_leaves(node: ast.AST) -> tuple[str, ...]:
    return tuple(leaf for child in _runtime_walk(node) if isinstance(child, ast.Call) and (leaf := _call_leaf(child)))


def _has_direct_signal(node: ast.AST) -> bool:
    if any(isinstance(child, ast.Assert) for child in _runtime_walk(node)):
        return True
    return any(leaf in _DIRECT_CONTEXTS or leaf.startswith("assert") for leaf in _call_leaves(node))


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
    """Index test definitions and exact inherited structural decorators."""
    index: dict[tuple[str, str], TestDefinition] = {}
    module_definitions = _direct_definitions(tree.body)

    def visit(
        nodes: list[ast.stmt],
        parents: tuple[str, ...] = (),
        class_definitions: (
            dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None
        ) = None,
        enclosing_structural: bool = False,
    ) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                visit(
                    node.body,
                    (*parents, node.name),
                    _direct_definitions(node.body),
                    (
                        enclosing_structural
                        or _has_explicit_structural_marker(node)
                    ),
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = "::".join((*parents, node.name))
                if node.name.startswith("test"):
                    index[(relative, qualified)] = TestDefinition(
                        path=relative,
                        qualified_name=qualified,
                        node=node,
                        module_definitions=module_definitions,
                        class_definitions=class_definitions or {},
                        local_definitions=_local_definitions(node),
                        enclosing_structural=enclosing_structural,
                    )

    visit(tree.body)
    return index


def _definition_index() -> dict[tuple[str, str], TestDefinition]:
    index: dict[tuple[str, str], TestDefinition] = {}
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        index.update(_definitions_from_tree(relative, tree))
    return index


def _collect_node_ids(
    *,
    marker: str | None = None,
) -> tuple[list[str], str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
    ]
    if marker is not None:
        command.extend(["-m", marker])
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
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


def _node_definition(
    node_id: str,
    index: dict[tuple[str, str], TestDefinition],
) -> TestDefinition:
    parts = node_id.split("::")
    path = parts[0]
    qualified_parts = parts[1:]
    qualified_parts[-1] = qualified_parts[-1].split("[", 1)[0]
    key = (path, "::".join(qualified_parts))
    try:
        return index[key]
    except KeyError as error:
        raise ValueError(f"no source test definition found for {node_id}") from error


def _entry(
    node_id: str,
    definition: TestDefinition,
) -> dict[str, str]:
    """Describe a no-direct-signal review candidate without classifying it."""
    helpers = definition.called_helpers_with_signal
    return {
        "node_id": node_id,
        "review_context": (
            f"local helpers with assertions: {', '.join(helpers)}"
            if helpers
            else "no local helper with a direct assertion was found"
        ),
    }


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


def _derived_ledgers() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    str,
    dict[tuple[str, str], TestDefinition],
]:
    node_ids, command = _collect_node_ids()
    index = _definition_index()
    no_direct: list[dict[str, str]] = []
    weak: list[dict[str, str]] = []
    for node_id in node_ids:
        definition = _node_definition(node_id, index)
        if not definition.direct_signal:
            no_direct.append(_entry(node_id, definition))
        if definition.weak_reasons:
            weak.append(
                {
                    "node_id": node_id,
                    "heuristic_reasons": "; ".join(
                        definition.weak_reasons,
                    ),
                }
            )
    return no_direct, weak, command, index


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ledger_payload(
    *,
    kind: str,
    command: str,
    entries: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "derivation_command": command,
        "entries": entries,
    }


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"missing evidence ledger: {path.relative_to(ROOT)}") from error
    if payload.get("schema_version") != 1:
        raise ValueError(f"{path.name}: unsupported schema_version")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{path.name}: entries must be a list")
    seen: set[str] = set()
    for entry in entries:
        if set(entry) != {
            "classification",
            "node_id",
            "rationale",
            "strongest_oracle",
        }:
            raise ValueError(f"{path.name}: malformed entry keys: {entry}")
        node_id = entry["node_id"]
        if node_id in seen:
            raise ValueError(f"{path.name}: duplicate node ID: {node_id}")
        seen.add(node_id)
        if path == HISTORY_PATH:
            allowed_classifications = _HISTORY_ACTIONS
        elif path == REVIEWED_BEHAVIORAL_PATH:
            allowed_classifications = _REVIEWED_BEHAVIORAL_CLASSIFICATIONS
        else:
            allowed_classifications = _CLASSIFICATIONS
        if entry["classification"] not in allowed_classifications:
            raise ValueError(f"{path.name}: invalid classification for {node_id}: {entry['classification']}")
        if not entry["strongest_oracle"].strip() or not entry["rationale"].strip():
            raise ValueError(f"{path.name}: empty evidence context for {node_id}")
    return payload


def _validate_history() -> None:
    payload = _load_ledger(HISTORY_PATH)
    if payload.get("kind") != "phase112_remediations":
        raise ValueError("phase112_remediations.json: invalid kind")
    if payload.get("phase_start_commit") != PHASE_START_COMMIT:
        raise ValueError("phase112_remediations.json: wrong phase-start commit")
    recorded_nodes = {entry["node_id"] for entry in payload["entries"]}
    missing = sorted(_REQUIRED_PHASE_START_REMEDIATIONS - recorded_nodes)
    extra = sorted(recorded_nodes - _REQUIRED_PHASE_START_REMEDIATIONS)
    if missing or extra:
        raise ValueError(
            f"phase112_remediations.json: mandatory phase-start review set disagrees; missing={missing} extra={extra}"
        )
    for entry in payload["entries"]:
        if entry["classification"] not in _HISTORY_ACTIONS:
            raise ValueError(
                f"phase112_remediations.json: classification must record a historical action: {entry['node_id']}"
            )


def _validate_current(
    path: Path,
    *,
    kind: str,
    derived: list[dict[str, str]],
    definitions: dict[tuple[str, str], TestDefinition],
) -> set[str]:
    payload = _load_ledger(path)
    if payload.get("kind") != kind:
        raise ValueError(f"{path.name}: invalid kind")
    expected_ids = {entry["node_id"] for entry in derived}
    actual_ids = {entry["node_id"] for entry in payload["entries"]}
    if expected_ids != actual_ids:
        missing = sorted(expected_ids - actual_ids)
        stale = sorted(actual_ids - expected_ids)
        raise ValueError(f"{path.name}: unreviewed evidence drift; missing={missing[:20]} stale={stale[:20]}")

    invariant_violations: list[str] = []
    for entry in payload["entries"]:
        if entry["classification"] != "invariant_only":
            continue
        node_id = entry["node_id"]
        violations = _invariant_contract_violations(
            _node_definition(node_id, definitions),
        )
        if violations:
            invariant_violations.append(
                f"{node_id}: {'; '.join(violations)}",
            )
    if invariant_violations:
        raise ValueError(
            f"{path.name}: invalid invariant_only classifications "
            f"({len(invariant_violations)}):\n" + "\n".join(invariant_violations),
        )
    return {entry["node_id"] for entry in payload["entries"] if entry["classification"] == "structural_only"}


def _validate_reviewed_weak_candidates(
    derived: list[dict[str, str]],
) -> tuple[set[str], int]:
    """Require a preserved human disposition for every heuristic candidate."""
    weak_payload = _load_ledger(WEAK_PATH)
    if weak_payload.get("kind") != "weak_oracles":
        raise ValueError("weak_oracles.json: invalid kind")
    behavioral_payload = _load_ledger(REVIEWED_BEHAVIORAL_PATH)
    if behavioral_payload.get("kind") != "reviewed_behavioral_oracles":
        raise ValueError(
            "reviewed_behavioral_oracles.json: invalid kind",
        )

    candidate_ids = {entry["node_id"] for entry in derived}
    weak_ids = {entry["node_id"] for entry in weak_payload["entries"]}
    behavioral_ids = {entry["node_id"] for entry in behavioral_payload["entries"]}
    overlap = sorted(weak_ids & behavioral_ids)
    missing = sorted(candidate_ids - weak_ids - behavioral_ids)
    stale = sorted((weak_ids | behavioral_ids) - candidate_ids)
    if overlap or missing or stale:
        raise ValueError(
            "heuristic evidence candidates lack one exact reviewed "
            "disposition; "
            f"overlap={overlap[:20]} missing={missing[:20]} "
            f"stale={stale[:20]}",
        )

    structural_ids = {
        entry["node_id"] for entry in weak_payload["entries"] if entry["classification"] == "structural_only"
    }
    return structural_ids, len(behavioral_ids)


def _refresh_derivation_command(path: Path, command: str) -> None:
    """Refresh machine metadata without overwriting reviewed entries."""
    payload = _load_ledger(path)
    payload["derivation_command"] = command
    _write_json(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "refresh derivation metadata only after every candidate has an "
            "exact reviewed disposition; never overwrite review text"
        ),
    )
    args = parser.parse_args()

    try:
        no_direct, weak, command, definitions = _derived_ledgers()

        structural_ids = _validate_current(
            NO_DIRECT_PATH,
            kind="no_direct_oracles",
            derived=no_direct,
            definitions=definitions,
        )
        reviewed_weak_structural, reviewed_behavioral_count = _validate_reviewed_weak_candidates(weak)
        structural_ids.update(reviewed_weak_structural)
        _validate_history()

        if args.write:
            for path in (
                NO_DIRECT_PATH,
                WEAK_PATH,
                REVIEWED_BEHAVIORAL_PATH,
            ):
                _refresh_derivation_command(path, command)

        collected_structural, structural_command = _collect_node_ids(
            marker="structural",
        )
        if set(collected_structural) != structural_ids:
            missing = sorted(structural_ids - set(collected_structural))
            extra = sorted(set(collected_structural) - structural_ids)
            raise ValueError(
                f"structural marker selection disagrees with ledgers; missing={missing[:20]} extra={extra[:20]}"
            )
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "collection_command": command,
                "no_direct_oracles": len(no_direct),
                "reviewed_behavioral_oracles": (reviewed_behavioral_count),
                "structural_command": structural_command,
                "structural_nodes": len(structural_ids),
                "weak_oracles": len(weak),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
