"""Phase 47g: Historical accuracy regression tests.

Validates that all scenarios complete without error and that historical
scenarios produce the correct winner.  The MC test (marked slow) runs
N=5 seeds and asserts >=60% correct — a lightweight smoke check that
calibration hasn't regressed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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

# Scenarios with known engine limitations
KNOWN_ISSUES: set[str] = set()

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
EVALUATE_SCRIPT = SCRIPTS_DIR / "evaluate_scenarios.py"


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
        timeout=600,
        cwd=str(SCRIPTS_DIR.parent),
    )
    if result.returncode != 0:
        pytest.fail(f"evaluate_scenarios.py failed:\n{result.stderr[-2000:]}")
    with open(output_path) as f:
        return json.load(f)


class TestAllScenariosComplete:
    """Every scenario must complete without error (seed=42)."""

    @pytest.fixture(scope="class")
    def eval_results(self, tmp_path_factory):
        out = tmp_path_factory.mktemp("eval") / "results.json"
        return _run_evaluation(out, seed=42)

    def test_no_failures(self, eval_results):
        failed = [r for r in eval_results if not r["success"]]
        assert not failed, f"Failed scenarios: {[r['scenario_name'] for r in failed]}"

    def test_minimum_scenario_count(self, eval_results):
        assert len(eval_results) >= 35, f"Only {len(eval_results)} scenarios ran"


class TestHistoricalWinnersSeed42:
    """Historical scenarios produce correct winner with seed=42."""

    @pytest.fixture(scope="class")
    def eval_results(self, tmp_path_factory):
        out = tmp_path_factory.mktemp("eval") / "results.json"
        return _run_evaluation(out, seed=42)

    @pytest.fixture(scope="class")
    def results_by_name(self, eval_results):
        return {r["scenario_name"]: r for r in eval_results}

    @pytest.mark.parametrize("scenario,expected_winner", list(HISTORICAL_WINNERS.items()))
    def test_correct_winner(self, results_by_name, scenario, expected_winner):
        if scenario in KNOWN_ISSUES:
            pytest.skip(f"Known engine limitation: {scenario}")
        if scenario not in results_by_name:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = results_by_name[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == expected_winner, (
            f"{scenario}: expected {expected_winner}, got {actual} "
            f"(condition={result.get('victory_condition', '?')})"
        )

    @pytest.mark.parametrize("scenario", sorted(DRAW_SCENARIOS))
    def test_draw_scenarios(self, results_by_name, scenario):
        if scenario not in results_by_name:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = results_by_name[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == "draw", (
            f"{scenario}: expected draw, got {actual}"
        )


@pytest.mark.slow
class TestHistoricalAccuracyMC:
    """Monte Carlo validation: correct winner in >=60% of N=5 runs.

    Marked slow — run with ``pytest -m slow``.
    """

    N_SEEDS = 5
    MIN_CORRECT_FRACTION = 0.6

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
