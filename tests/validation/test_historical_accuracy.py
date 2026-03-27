"""Phase 47g+57a: Historical accuracy regression tests.

Validates that all scenarios complete without error and that historical
scenarios produce the correct winner.  The MC test (marked slow) runs
N=10 seeds and asserts >=80% correct — a statistical validation that
calibration produces correct historical outcomes.

Phase 57 additions: tighter MC thresholds (60%→80%, 5→10 seeds),
victory condition checks, scenario coverage assertion, YAML load validation.
Shared module-scoped evaluation fixture to avoid redundant evaluator runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Expected winners for historical scenarios (from Phase 47 calibration)
# ---------------------------------------------------------------------------

HISTORICAL_WINNERS: dict[str, str] = {
    # Ancient & Medieval
    "agincourt": "english",
    "cannae": "carthaginian",
    "hastings": "norman",
    "salamis": "greek",
    # Napoleonic
    "austerlitz": "french",
    "trafalgar": "british",
    "waterloo": "british",
    # WW1
    "cambrai": "british",
    "jutland": "british",
    "somme_july1": "german",
    # WW2
    "kursk": "soviet",
    "midway": "usn",
    "normandy_bocage": "us",
    "stalingrad": "soviet",
    "eastern_front_1943": "blue",
    # Modern
    "73_easting": "blue",
    "bekaa_valley_1982": "blue",
    "golan_campaign": "blue",
    "golan_heights": "blue",
    "gulf_war_ew_1991": "blue",
    "falklands_goose_green": "blue",
    "falklands_naval": "blue",
    "falklands_san_carlos": "blue",
    "falklands_campaign": "blue",
    "korean_peninsula": "blue",
    "suwalki_gap": "blue",
    "taiwan_strait": "blue",
    # CBRN / Special
    "cbrn_chemical_defense": "blue",
    "cbrn_nuclear_tactical": "red",
    "test_scenario": "blue",
}

# Scenarios expected to produce a draw
DRAW_SCENARIOS: set[str] = {
    "coin_campaign",
    "halabja_1988",
    "hybrid_gray_zone",
    "space_asat_escalation",
    "space_gps_denial",
    "space_isr_gap",
    "srebrenica_1995",
}

# Calibration exercise scenarios — outcomes are seed/flag dependent and not
# tracked for regression.  They exist to exercise calibration parameters.
CALIBRATION_SCENARIOS: set[str] = {
    "calibration_air_ground",
    "calibration_arctic",
    "calibration_urban_cbrn",
    "benchmark_battalion",
    "benchmark_brigade",
}

# Scenarios with known engine limitations
KNOWN_ISSUES: set[str] = set()

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
EVALUATE_SCRIPT = SCRIPTS_DIR / "evaluate_scenarios.py"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Scenarios that should resolve via decisive combat, not time_expired
DECISIVE_COMBAT_SCENARIOS: set[str] = {
    "73_easting", "bekaa_valley_1982", "korean_peninsula",
    "taiwan_strait",
    "normandy_bocage", "stalingrad", "austerlitz", "waterloo",
    "cambrai", "hastings",
    # Phase 73: historical scenarios fixed to produce decisive outcomes
    "agincourt", "cannae", "salamis", "midway",
    # Phase 81: Trafalgar recalibrated for decisive combat
    "trafalgar",
}


def _run_evaluation(output_path: Path, seed: int = 42) -> list[dict]:
    """Run evaluate_scenarios.py and return parsed results."""
    cmd = [
        sys.executable,
        str(EVALUATE_SCRIPT),
        "--output",
        str(output_path),
        "--seed",
        str(seed),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=7200,
        cwd=str(SCRIPTS_DIR.parent),
    )
    if result.returncode != 0:
        pytest.fail(f"evaluate_scenarios.py failed:\n{result.stderr[-2000:]}")
    with open(output_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Module-scoped fixture: run evaluator ONCE for seed=42, share across classes
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def eval_results_seed42(tmp_path_factory):
    """Single evaluator run shared by all test classes in this module."""
    out = tmp_path_factory.mktemp("eval_shared") / "results.json"
    return _run_evaluation(out, seed=42)


@pytest.fixture(scope="module")
def results_by_name_seed42(eval_results_seed42):
    """Results indexed by scenario name."""
    return {r["scenario_name"]: r for r in eval_results_seed42}


@pytest.mark.slow
class TestAllScenariosComplete:
    """Every scenario must complete without error (seed=42)."""

    def test_no_failures(self, eval_results_seed42):
        failed = [r for r in eval_results_seed42 if not r["success"]]
        assert not failed, f"Failed scenarios: {[r['scenario_name'] for r in failed]}"

    def test_minimum_scenario_count(self, eval_results_seed42):
        assert len(eval_results_seed42) >= 35, f"Only {len(eval_results_seed42)} scenarios ran"


@pytest.mark.slow
class TestHistoricalWinnersSeed42:
    """Historical scenarios produce correct winner with seed=42."""

    @pytest.mark.parametrize("scenario,expected_winner", list(HISTORICAL_WINNERS.items()))
    def test_correct_winner(self, results_by_name_seed42, scenario, expected_winner):
        if scenario in KNOWN_ISSUES:
            pytest.skip(f"Known engine limitation: {scenario}")
        if scenario not in results_by_name_seed42:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = results_by_name_seed42[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == expected_winner, (
            f"{scenario}: expected {expected_winner}, got {actual} "
            f"(condition={result.get('victory_condition', '?')})"
        )

    @pytest.mark.parametrize("scenario", sorted(DRAW_SCENARIOS))
    def test_draw_scenarios(self, results_by_name_seed42, scenario):
        if scenario not in results_by_name_seed42:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = results_by_name_seed42[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == "draw", (
            f"{scenario}: expected draw, got {actual}"
        )


@pytest.mark.slow
class TestHistoricalAccuracyMC:
    """Monte Carlo validation: correct winner in >=80% of N=10 runs.

    Marked slow — run with ``pytest -m slow``.
    """

    N_SEEDS = 10
    MIN_CORRECT_FRACTION = 0.8

    @pytest.fixture(scope="class")
    def mc_results(self, tmp_path_factory):
        all_results: dict[str, list[str]] = {}
        for seed in range(self.N_SEEDS):
            out = tmp_path_factory.mktemp("mc") / f"results_seed{seed}.json"
            results = _run_evaluation(out, seed=seed)
            for r in results:
                name = r["scenario_name"]
                winner = r.get("victory_side", "") or "draw"
                all_results.setdefault(name, []).append(winner)
        return all_results

    @pytest.mark.parametrize("scenario,expected_winner", list(HISTORICAL_WINNERS.items()))
    def test_mc_correct_winner(self, mc_results, scenario, expected_winner):
        if scenario in KNOWN_ISSUES:
            pytest.skip(f"Known engine limitation: {scenario}")
        if scenario not in mc_results:
            pytest.skip(f"Scenario {scenario} not found")
        winners = mc_results[scenario]
        correct = sum(1 for w in winners if w == expected_winner)
        fraction = correct / len(winners)
        assert fraction >= self.MIN_CORRECT_FRACTION, (
            f"{scenario}: {expected_winner} won {correct}/{len(winners)} "
            f"({fraction:.0%}) — need {self.MIN_CORRECT_FRACTION:.0%}. "
            f"Winners: {winners}"
        )


@pytest.mark.slow
class TestVictoryConditions:
    """Modern/historical combat scenarios should resolve decisively."""

    @pytest.mark.parametrize("scenario", sorted(DECISIVE_COMBAT_SCENARIOS))
    def test_not_time_expired(self, results_by_name_seed42, scenario):
        """Scenario resolves via force_destroyed or morale_collapsed, not time_expired."""
        if scenario not in results_by_name_seed42:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = results_by_name_seed42[scenario]
        condition = result.get("victory_condition", "")
        assert condition != "time_expired", (
            f"{scenario} resolved via time_expired — should reach decisive outcome"
        )


@pytest.mark.slow
class TestVictoryConditionTypes:
    """Phase 73: Specific victory condition type assertions."""

    def test_somme_is_time_expired(self, results_by_name_seed42):
        """Somme should resolve via time_expired (German defensive victory)."""
        if "somme_july1" not in results_by_name_seed42:
            pytest.skip("somme_july1 not in evaluation results")
        result = results_by_name_seed42["somme_july1"]
        condition = result.get("victory_condition", "")
        assert condition == "time_expired", (
            f"Somme should be time_expired (German defense held), got {condition}"
        )

    def test_somme_not_force_destroyed(self, results_by_name_seed42):
        """Somme must NOT resolve via force_destroyed."""
        if "somme_july1" not in results_by_name_seed42:
            pytest.skip("somme_july1 not in evaluation results")
        result = results_by_name_seed42["somme_july1"]
        condition = result.get("victory_condition", "")
        assert condition != "force_destroyed", (
            "Somme should not resolve via force_destroyed — historically a failed offensive"
        )


class TestScenarioCoverage:
    """Every scenario YAML is tracked in the regression suite."""

    def _find_all_scenario_names(self) -> set[str]:
        """Discover all scenario directory names."""
        names: set[str] = set()
        for path in DATA_DIR.rglob("scenario.yaml"):
            name = path.parent.name
            if "test_campaign" in name:
                continue
            names.add(name)
        return names

    def test_all_scenarios_in_regression(self):
        """Every scenario YAML has an entry in HISTORICAL_WINNERS or DRAW_SCENARIOS."""
        all_names = self._find_all_scenario_names()
        tracked = set(HISTORICAL_WINNERS.keys()) | DRAW_SCENARIOS | CALIBRATION_SCENARIOS
        untracked = all_names - tracked
        assert not untracked, (
            f"Scenarios not tracked in regression suite: {sorted(untracked)}. "
            f"Add them to HISTORICAL_WINNERS or DRAW_SCENARIOS."
        )

    def test_all_scenarios_load_cleanly(self):
        """All scenario YAMLs parse without error."""
        failures = []
        for path in sorted(DATA_DIR.rglob("scenario.yaml")):
            name = path.parent.name
            if "test_campaign" in name:
                continue
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                assert data is not None, f"Empty YAML: {name}"
                assert "sides" in data or "forces" in data, f"No sides/forces: {name}"
            except Exception as exc:
                failures.append(f"{name}: {exc}")
        assert not failures, "Scenario YAML load failures:\n" + "\n".join(failures)
