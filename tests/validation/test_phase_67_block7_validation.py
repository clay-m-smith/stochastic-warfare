"""Phase 67a: Block 7 validation — flag enablement and scenario regression.

Validates that enabling Block 7 flags in curated scenarios:
- Doesn't break any scenario (all complete without error)
- Preserves correct historical outcomes
- Passes MC statistical validation (slow tests)

Uses the evaluate_scenarios.py evaluator via subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
_EVALUATE_SCRIPT = _SCRIPTS / "evaluate_scenarios.py"

# -----------------------------------------------------------------------
# The 10 scenarios with Phase 67 flag enablement
# -----------------------------------------------------------------------

FLAGGED_SCENARIOS = [
    "73_easting",
    "golan_heights",
    "eastern_front_1943",
    "bekaa_valley_1982",
    "gulf_war_ew_1991",
    "korean_peninsula",
    "suwalki_gap",
    "taiwan_strait",
    "falklands_naval",
    "coin_campaign",
]

# Expected winners for flagged scenarios
FLAGGED_WINNERS: dict[str, str] = {
    "73_easting": "blue",
    "golan_heights": "blue",
    "eastern_front_1943": "blue",
    "bekaa_valley_1982": "blue",
    "gulf_war_ew_1991": "blue",
    "korean_peninsula": "blue",
    "suwalki_gap": "blue",
    "taiwan_strait": "blue",
    "falklands_naval": "blue",
}

FLAGGED_DRAWS: set[str] = {"coin_campaign"}

# Flagged scenarios that must resolve via decisive combat, not time_expired
FLAGGED_DECISIVE: set[str] = {
    "73_easting",
    "bekaa_valley_1982",
    "korean_peninsula",
    "suwalki_gap",
    "taiwan_strait",
    "falklands_naval",
    "gulf_war_ew_1991",
}


def _run_evaluation(output_path: Path, seed: int = 42) -> list[dict]:
    """Run evaluate_scenarios.py and return parsed results."""
    cmd = [
        sys.executable,
        str(_EVALUATE_SCRIPT),
        "--output",
        str(output_path),
        "--seed",
        str(seed),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=str(_ROOT),
    )
    if result.returncode != 0:
        pytest.fail(f"evaluate_scenarios.py failed:\n{result.stderr[-2000:]}")
    with open(output_path) as f:
        return json.load(f)


# -----------------------------------------------------------------------
# Module-scoped fixture: single evaluator run at seed=42
# -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def eval_results(tmp_path_factory):
    """Single evaluator run at seed=42 shared across test classes."""
    out = tmp_path_factory.mktemp("eval67") / "results.json"
    return _run_evaluation(out, seed=42)


@pytest.fixture(scope="module")
def results_by_name(eval_results):
    """Results indexed by scenario name."""
    return {r["scenario_name"]: r for r in eval_results}


@pytest.mark.slow
class TestFlaggedScenariosComplete:
    """All flagged scenarios complete without error."""

    @pytest.mark.parametrize("scenario", FLAGGED_SCENARIOS)
    def test_completes(self, results_by_name, scenario):
        assert scenario in results_by_name, f"Scenario {scenario} not in results"
        r = results_by_name[scenario]
        assert r["success"], (
            f"{scenario} failed: {r.get('error', '')[:200]}"
        )

    def test_no_failures_overall(self, eval_results):
        """No scenario failures across entire evaluation."""
        failed = [r for r in eval_results if not r["success"]]
        assert not failed, (
            f"Failed scenarios: {[r['scenario_name'] for r in failed]}"
        )

    def test_minimum_scenario_count(self, eval_results):
        """At least 37 scenarios evaluated."""
        assert len(eval_results) >= 37, (
            f"Only {len(eval_results)} scenarios ran"
        )


@pytest.mark.slow
class TestFlaggedWinners:
    """Flagged scenarios still produce correct winners at seed=42."""

    @pytest.mark.parametrize(
        "scenario,expected", list(FLAGGED_WINNERS.items())
    )
    def test_correct_winner(self, results_by_name, scenario, expected):
        if scenario not in results_by_name:
            pytest.skip(f"{scenario} not in results")
        actual = results_by_name[scenario].get("victory_side", "") or "draw"
        assert actual == expected, (
            f"{scenario}: expected {expected}, got {actual} "
            f"(condition={results_by_name[scenario].get('victory_condition', '?')})"
        )

    @pytest.mark.parametrize("scenario", sorted(FLAGGED_DRAWS))
    def test_draw_scenarios(self, results_by_name, scenario):
        if scenario not in results_by_name:
            pytest.skip(f"{scenario} not in results")
        actual = results_by_name[scenario].get("victory_side", "") or "draw"
        assert actual == "draw", f"{scenario}: expected draw, got {actual}"


@pytest.mark.slow
class TestFlaggedVictoryConditions:
    """Decisive flagged scenarios resolve via combat, not time expiry."""

    @pytest.mark.parametrize("scenario", sorted(FLAGGED_DECISIVE))
    def test_not_time_expired(self, results_by_name, scenario):
        if scenario not in results_by_name:
            pytest.skip(f"{scenario} not in results")
        condition = results_by_name[scenario].get("victory_condition", "")
        assert condition != "time_expired", (
            f"{scenario} resolved via time_expired — should reach decisive outcome"
        )


@pytest.mark.slow
class TestFlaggedMC:
    """Monte Carlo validation for flagged scenarios.

    N=10 seeds, >=80% correct — matches Phase 57 standard.
    """

    N_SEEDS = 10
    MIN_CORRECT_FRACTION = 0.8

    @pytest.fixture(scope="class")
    def mc_results(self, tmp_path_factory):
        all_results: dict[str, list[str]] = {}
        for seed in range(self.N_SEEDS):
            out = tmp_path_factory.mktemp("mc67") / f"results_seed{seed}.json"
            results = _run_evaluation(out, seed=seed)
            for r in results:
                name = r["scenario_name"]
                if name in FLAGGED_SCENARIOS:
                    winner = r.get("victory_side", "") or "draw"
                    all_results.setdefault(name, []).append(winner)
        return all_results

    @pytest.mark.parametrize(
        "scenario,expected", list(FLAGGED_WINNERS.items())
    )
    def test_mc_correct_winner(self, mc_results, scenario, expected):
        if scenario not in mc_results:
            pytest.skip(f"{scenario} not found in MC results")
        winners = mc_results[scenario]
        correct = sum(1 for w in winners if w == expected)
        fraction = correct / len(winners)
        assert fraction >= self.MIN_CORRECT_FRACTION, (
            f"{scenario}: {expected} won {correct}/{len(winners)} "
            f"({fraction:.0%}) — need {self.MIN_CORRECT_FRACTION:.0%}. "
            f"Winners: {winners}"
        )
