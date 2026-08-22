"""Current-engine scenario-evaluator terminal regression.

The legacy filename is retained for test-history continuity.  These assertions
are deliberately *not* historical validation, calibration evidence, or a
predictive-accuracy claim.  They freeze the terminal winner and victory
condition currently produced by the production runtime for one declared seed.

Snapshot provenance:

``scripts/evaluate_scenarios.py --seed 42 --no-details``

Historical outcome envelopes require separate sourced, predeclared,
multi-seed validation.  A changed row here is therefore a regression-review
signal, not proof that either the old or new outcome is historically correct.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EVALUATE_SCRIPT = ROOT / "scripts" / "evaluate_scenarios.py"

SNAPSHOT_SEED = 42
EVALUATOR_TIMEOUT_SECONDS = 12_000
SNAPSHOT_PROVENANCE = "scripts/evaluate_scenarios.py --seed 42 --no-details"
EVALUATOR_EXCLUSIONS = {
    "benchmark_battalion",
    "benchmark_brigade",
}

# Exact production-runtime terminal snapshot captured for SNAPSHOT_SEED.  The
# tuple is (winning side, victory condition); an empty winning side is
# normalized to "draw", matching the evaluator's user-facing summary.
# Phase 117's final-tree data repairs produced canonical mapping SHA-256
# 7be878c370a41ae0fdc36bff88212f0dd45b2c0b997ad9385197cbebea32b5b4,
# independently reproduced by detached Phase 117, earlier Phase 118, and the
# Phase 118 slow-only shard-11 run.  This remains a non-historical snapshot.
CURRENT_ENGINE_TERMINAL_SNAPSHOT: dict[str, tuple[str, str]] = {
    "agincourt": ("english", "force_destroyed"),
    "cannae": ("carthaginian", "force_destroyed"),
    "hastings": ("norman", "force_destroyed"),
    "salamis": ("greek", "force_destroyed"),
    "austerlitz": ("french", "force_destroyed"),
    "trafalgar": ("franco_spanish", "morale_collapsed"),
    "waterloo": ("british", "force_destroyed"),
    "cambrai": ("british", "force_destroyed"),
    # Phase 114 binds contact discovered in one interval to the next
    # interval's cadence. The reviewed seed-42 result remains British but now
    # reaches force_destroyed. The Phase 117 claim ledger retains the separate
    # multi-seed historical disposition; this row is only a regression signal.
    "jutland": ("british", "force_destroyed"),
    "somme_july1": ("german", "time_expired"),
    "kursk": ("soviet", "time_expired"),
    "midway": ("usn", "force_destroyed"),
    "normandy_bocage": ("us", "territory_control"),
    "stalingrad": ("german", "force_destroyed"),
    "73_easting": ("blue", "time_expired"),
    "bekaa_valley_1982": ("blue", "force_destroyed"),
    "bint_jbeil_2006": ("blue", "force_destroyed"),
    "calibration_air_ground": ("red", "force_destroyed"),
    "calibration_arctic": ("red", "force_destroyed"),
    "calibration_urban_cbrn": ("red", "force_destroyed"),
    "cbrn_chemical_defense": ("blue", "time_expired"),
    "cbrn_nuclear_tactical": ("red", "time_expired"),
    "coin_campaign": ("draw", "time_expired"),
    "debecka_pass": ("red", "time_expired"),
    "eastern_front_1943": ("red", "force_destroyed"),
    "falklands_campaign": ("draw", "max_ticks"),
    "falklands_goose_green": ("red", "force_destroyed"),
    "falklands_naval": ("blue", "time_expired"),
    "falklands_san_carlos": ("blue", "force_destroyed"),
    "fallujah_phase_line_fran": ("blue", "force_destroyed"),
    "golan_campaign": ("red", "force_destroyed"),
    "golan_heights": ("blue", "time_expired"),
    "gulf_war_ew_1991": ("blue", "time_expired"),
    "halabja_1988": ("red", "territory_control"),
    "hybrid_gray_zone": ("draw", "time_expired"),
    "ins_hanit_2006": ("blue", "time_expired"),
    "khafji": ("blue", "morale_collapsed"),
    "korean_peninsula": ("blue", "force_destroyed"),
    "space_asat_escalation": ("draw", "time_expired"),
    "space_gps_denial": ("draw", "time_expired"),
    "space_isr_gap": ("draw", "time_expired"),
    "srebrenica_1995": ("red", "territory_control"),
    "suwalki_gap": ("red", "force_destroyed"),
    "taiwan_strait": ("blue", "force_destroyed"),
    "test_scenario": ("blue", "force_destroyed"),
    "time_on_target_validation": ("draw", "time_expired"),
}


def _run_evaluation(output_path: Path) -> list[dict]:
    """Run the declared evaluator provenance and return its JSON rows."""
    command = [
        sys.executable,
        str(EVALUATE_SCRIPT),
        "--output",
        str(output_path),
        "--seed",
        str(SNAPSHOT_SEED),
        "--no-details",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        # Phase 117 recorded this exact 46-scenario production evaluator at
        # 7,948.60 seconds on a shared-core host.  This is operational
        # containment, not a performance threshold; the enclosing CI shard
        # retains a separate 14,400-second fail-closed boundary.
        timeout=EVALUATOR_TIMEOUT_SECONDS,
        cwd=ROOT,
    )
    if result.returncode != 0:
        pytest.fail(f"evaluate_scenarios.py failed for the seed-42 snapshot:\n{result.stderr[-2000:]}")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _shipped_scenario_names() -> set[str]:
    """Return catalog scenarios, excluding internal test-campaign fixtures."""
    return {
        path.parent.name for path in DATA_DIR.rglob("scenario.yaml") if not path.parent.name.startswith("test_campaign")
    }


@pytest.fixture(scope="module")
def evaluator_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Run the full production evaluator exactly once for this module."""
    output = tmp_path_factory.mktemp("current_terminal_snapshot") / "results.json"
    return _run_evaluation(output)


@pytest.mark.slow
class TestCurrentEngineTerminalSnapshot:
    """Exact seed-42 terminal regression; no historical claim is implied."""

    def test_exact_scenario_set(self, evaluator_rows: list[dict]) -> None:
        actual_names = {row["scenario_name"] for row in evaluator_rows}
        assert actual_names == set(CURRENT_ENGINE_TERMINAL_SNAPSHOT)
        assert len(actual_names) == 46

    def test_scenario_names_are_unique(self, evaluator_rows: list[dict]) -> None:
        ordered_names = [row["scenario_name"] for row in evaluator_rows]
        assert len(ordered_names) == len(set(ordered_names)) == 46

    def test_all_rows_succeed_and_publish_terminal_fields(
        self,
        evaluator_rows: list[dict],
    ) -> None:
        failed = [row["scenario_name"] for row in evaluator_rows if not row.get("success")]
        incomplete = [
            row["scenario_name"]
            for row in evaluator_rows
            if not row.get("victory_condition")
            or (not row.get("victory_side") and row.get("victory_condition") != "time_expired")
        ]
        assert not failed
        assert not incomplete

    def test_exact_winner_and_condition_snapshot(
        self,
        evaluator_rows: list[dict],
    ) -> None:
        actual = {
            row["scenario_name"]: (
                row.get("victory_side") or "draw",
                row["victory_condition"],
            )
            for row in evaluator_rows
        }
        assert actual == CURRENT_ENGINE_TERMINAL_SNAPSHOT


class TestScenarioEvaluatorCatalogContract:
    """Static catalog boundaries supporting the runtime snapshot."""

    def test_evaluator_exclusions_are_exact(self) -> None:
        shipped = _shipped_scenario_names()
        assert shipped - set(CURRENT_ENGINE_TERMINAL_SNAPSHOT) == (EVALUATOR_EXCLUSIONS)
        assert EVALUATOR_EXCLUSIONS <= shipped
        assert len(shipped) == 48

    def test_all_catalog_scenario_yaml_loads(self) -> None:
        failures: list[str] = []
        for path in sorted(DATA_DIR.rglob("scenario.yaml")):
            if path.parent.name.startswith("test_campaign"):
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                assert data is not None, f"Empty YAML: {path.parent.name}"
                assert "sides" in data or "forces" in data, f"No sides/forces: {path.parent.name}"
            except Exception as exc:
                failures.append(f"{path.parent.name}: {exc}")
        assert not failures, "Scenario YAML load failures:\n" + "\n".join(failures)
