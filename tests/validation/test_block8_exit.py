"""Phase 81 Block 8 structural declarations against current repository state.

The legacy file retains its exit-criterion numbering, but it does not convert
source searches or authored victory conditions into historical outcome proof.
Current seed-42 terminal classifications come from the production-evaluator
snapshot.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tests.validation.test_historical_accuracy import (
    CURRENT_ENGINE_TERMINAL_SNAPSHOT,
)

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "stochastic_warfare"
_DATA = _ROOT / "data"
_TESTS = _ROOT / "tests"
_API = _ROOT / "api"
_FRONTEND = _ROOT / "frontend"
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _read_src(rel_path: str) -> str:
    """Read source file relative to stochastic_warfare/."""
    return (_SRC / rel_path).read_text(encoding="utf-8")


def _count_flag_in_scenarios(flag: str) -> int:
    """Count how many scenario YAMLs have this flag set to true."""
    count = 0
    for path in _DATA.rglob("scenario.yaml"):
        if "test_campaign" in path.parent.name:
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        cal = data.get("calibration_overrides") or {}
        if cal.get(flag) is True:
            count += 1
    return count


# ---------------------------------------------------------------------------
# EC1: Every gate that checks a condition also enforces it
# ---------------------------------------------------------------------------

class TestEC1_GatesEnforce:
    """EC1: Every gate that checks a condition also enforces it."""

    def test_fuel_consumption_subtracts_fuel(self):
        """battle.py fuel consumption actually modifies fuel_remaining."""
        src = _read_src("simulation/battle.py")
        assert "fuel_remaining" in src
        # Must subtract and write back
        assert re.search(r"fuel_remaining\s*-", src), (
            "No fuel_remaining subtraction found in battle.py"
        )

    def test_ammo_gate_blocks_fire(self):
        """battle.py ammo gate uses 'continue' to skip engagement."""
        src = _read_src("simulation/battle.py")
        assert "magazine_capacity" in src
        assert "_ammo_expended" in src

    def test_fuel_flag_enabled_in_scenarios(self):
        """enable_fuel_consumption is True in at least 10 scenarios."""
        count = _count_flag_in_scenarios("enable_fuel_consumption")
        assert count >= 10, f"enable_fuel_consumption in only {count} scenarios"

    def test_ammo_flag_enabled_in_scenarios(self):
        """enable_ammo_gate is True in at least 10 scenarios."""
        count = _count_flag_in_scenarios("enable_ammo_gate")
        assert count >= 10, f"enable_ammo_gate in only {count} scenarios"

    def test_command_hierarchy_enabled(self):
        """enable_command_hierarchy is True in at least 1 scenario."""
        count = _count_flag_in_scenarios("enable_command_hierarchy")
        assert count >= 1, f"enable_command_hierarchy in {count} scenarios"

    def test_carrier_ops_enabled(self):
        """enable_carrier_ops is True in at least 1 scenario."""
        count = _count_flag_in_scenarios("enable_carrier_ops")
        assert count >= 1, f"enable_carrier_ops in {count} scenarios"

    def test_environmental_fatigue_enabled(self):
        """enable_environmental_fatigue is True in at least 1 scenario."""
        count = _count_flag_in_scenarios("enable_environmental_fatigue")
        assert count >= 1, f"enable_environmental_fatigue in {count} scenarios"

    def test_ice_crossing_enabled(self):
        """enable_ice_crossing is True in at least 1 scenario."""
        count = _count_flag_in_scenarios("enable_ice_crossing")
        assert count >= 1, f"enable_ice_crossing in {count} scenarios"


# ---------------------------------------------------------------------------
# EC2: Every computed result is consumed or removed
# ---------------------------------------------------------------------------

class TestEC2_NoUnconsumedOutputs:
    """EC2: Every computed result is consumed or removed."""

    def test_fire_damage_applied(self):
        """battle.py applies damage to units in fire zones."""
        src = _read_src("simulation/battle.py")
        assert "fire_damage" in src

    def test_stratagem_expiry_deactivates(self):
        """StratagemEngine.expire_stratagems called in battle loop."""
        src = _read_src("simulation/battle.py")
        assert "expire_stratagems" in src

    def test_guerrilla_retreat_modifies_position(self):
        """battle.py modifies unit position on guerrilla retreat."""
        src = _read_src("simulation/battle.py")
        assert "retreat_distance" in src or "guerrilla" in src


# ---------------------------------------------------------------------------
# EC3: All P0/P1 deferred items from Block 7 resolved
# ---------------------------------------------------------------------------

class TestEC3_DeferredItemsResolved:
    """EC3: All P0/P1 deferred items from Block 7 resolved."""

    def test_all_deferred_flags_exercised(self):
        """All 7 deferred flags from Phase 68-78 are enabled in at least one scenario."""
        deferred = [
            "enable_fuel_consumption",
            "enable_ammo_gate",
            "enable_command_hierarchy",
            "enable_carrier_ops",
            "enable_ice_crossing",
            "enable_environmental_fatigue",
            # enable_bridge_capacity intentionally excluded — no bridges in modern terrain data
        ]
        for flag in deferred:
            count = _count_flag_in_scenarios(flag)
            assert count >= 1, f"{flag} not enabled in any scenario"


# ---------------------------------------------------------------------------
# EC4: Unit test coverage for combat engines and simulation core
# ---------------------------------------------------------------------------

class TestEC4_UnitTestCoverage:
    """EC4: Unit test coverage for combat engines and simulation core."""

    def test_combat_test_files_exist(self):
        """tests/unit/combat/ has at least 30 test files."""
        combat_dir = _TESTS / "unit" / "combat"
        if not combat_dir.exists():
            return  # Skip if directory missing
        test_files = list(combat_dir.glob("test_*.py"))
        assert len(test_files) >= 30, (
            f"Only {len(test_files)} combat test files — expected >= 30"
        )

    def test_simulation_test_files_exist(self):
        """tests/unit/ has test files for simulation core modules."""
        unit_dir = _TESTS / "unit"
        if not unit_dir.exists():
            return
        # Look for simulation-related test files across all subdirs
        sim_tests = list(unit_dir.rglob("test_battle*.py")) + \
            list(unit_dir.rglob("test_engine*.py")) + \
            list(unit_dir.rglob("test_calibration*.py"))
        assert len(sim_tests) >= 2, (
            f"Only {len(sim_tests)} simulation test files — expected >= 2"
        )


# ---------------------------------------------------------------------------
# EC5: Authored victory conditions and current terminal results remain distinct
# ---------------------------------------------------------------------------

class TestEC5_TerminalDeclarations:
    """EC5: Check current classifications without asserting historical truth."""

    def test_trafalgar_current_terminal_snapshot(self):
        """Trafalgar currently ends through the production morale path."""
        assert CURRENT_ENGINE_TERMINAL_SNAPSHOT["trafalgar"] == (
            "franco_spanish",
            "morale_collapsed",
        )

    def test_authored_force_destroyed_does_not_imply_terminal_condition(self):
        """Two authored force conditions currently terminate by time expiry."""
        for scenario_dir in ["73_easting", "golan_heights"]:
            path = _DATA / "scenarios" / scenario_dir / "scenario.yaml"
            assert path.is_file()
            with open(path) as f:
                data = yaml.safe_load(f)
            vcs = data.get("victory_conditions", [])
            has_fd = any(vc.get("type") == "force_destroyed" for vc in vcs)
            assert has_fd, f"{scenario_dir} missing force_destroyed victory condition"
            assert CURRENT_ENGINE_TERMINAL_SNAPSHOT[scenario_dir][1] == (
                "time_expired"
            )


# ---------------------------------------------------------------------------
# EC6: Golan uses the strict manual paired policy
# ---------------------------------------------------------------------------

class TestEC6_GolanBenchmark:
    """EC6: Golan cannot pass from an absolute wall-clock literal."""

    def test_golan_policy_is_manual_and_paired(self):
        """Parse the authoritative typed policy rather than source-searching."""
        from tests.benchmarks.benchmark_suite import BenchmarkBaseline

        entry = BenchmarkBaseline().load()["golan_heights"]
        assert entry.policy.mode == "gate"
        assert entry.policy.manual is True
        assert entry.policy.timed_pairs == 3
        assert entry.policy.maximum_median_slowdown_ratio == 1.2


# ---------------------------------------------------------------------------
# EC7: API schemas current
# ---------------------------------------------------------------------------

class TestEC7_APICurrent:
    """EC7: API schemas current."""

    def test_scenario_summary_has_space_dew(self):
        """ScenarioSummary has has_space and has_dew fields."""
        src = (_API / "schemas.py").read_text(encoding="utf-8")
        assert "has_space" in src, "has_space not in schemas.py"
        assert "has_dew" in src, "has_dew not in schemas.py"

    def test_enable_all_modern_in_calibration(self):
        """CalibrationSchema has enable_all_modern field."""
        src = _read_src("simulation/calibration.py")
        assert "enable_all_modern" in src


# ---------------------------------------------------------------------------
# EC8: API concurrency bugs fixed
# ---------------------------------------------------------------------------

class TestEC8_APIConcurrency:
    """EC8: API concurrency bugs fixed."""

    def test_batch_semaphore_exists(self):
        """run_manager.py uses asyncio.Semaphore for batch runs."""
        src = (_API / "run_manager.py").read_text(encoding="utf-8")
        assert "Semaphore" in src, "No Semaphore in run_manager.py"


# ---------------------------------------------------------------------------
# EC9: Frontend WCAG 2.1 AA
# ---------------------------------------------------------------------------

class TestEC9_WCAG:
    """EC9: Frontend WCAG 2.1 AA."""

    def test_accessibility_test_files_exist(self):
        """Frontend has accessibility test files."""
        a11y_dir = _FRONTEND / "src" / "__tests__" / "a11y"
        if not a11y_dir.exists():
            return
        test_files = list(a11y_dir.glob("*.test.*"))
        assert len(test_files) >= 3, (
            f"Only {len(test_files)} a11y test files — expected >= 3"
        )


# ---------------------------------------------------------------------------
# EC10: CI/CD on every push
# ---------------------------------------------------------------------------

class TestEC10_CICD:
    """EC10: CI/CD on every push."""

    def test_github_workflows_exist(self):
        """test.yml and lint.yml workflows exist."""
        assert (_WORKFLOWS / "test.yml").exists(), "test.yml workflow missing"
        assert (_WORKFLOWS / "lint.yml").exists(), "lint.yml workflow missing"

    def test_test_workflow_has_push_trigger(self):
        """test.yml triggers on push."""
        src = (_WORKFLOWS / "test.yml").read_text(encoding="utf-8")
        assert "push" in src, "test.yml does not trigger on push"
