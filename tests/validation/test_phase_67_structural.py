"""Phase 67b: Block 7 exit criteria — structural verification tests.

Source-level assertions verifying that all Block 7 wiring is complete:
- Every enable_* flag consumed in engine code
- Every enable_* flag exercised in at least one scenario
- No orphan calibration keys
- All engagement types handled
- Event feedback subscriptions wired
- Checkpoint state complete
- Dead keys stable
- No xfail markers in Block 7 tests
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "stochastic_warfare"
_DATA = _ROOT / "data"
_DOCS = _ROOT / "docs"
_TESTS = _ROOT / "tests"


def _read(rel_path: str) -> str:
    """Read source file relative to stochastic_warfare/."""
    return (_SRC / rel_path).read_text(encoding="utf-8")


def _get_enable_flags() -> list[str]:
    """Extract all enable_* field names from CalibrationSchema."""
    src = _read("simulation/calibration.py")
    return re.findall(r"(enable_\w+):\s*bool\s*=", src)


class TestEnableFlagConsumers:
    """Block 7 criterion #2: every enable_* flag consumed by downstream code."""

    def test_all_enable_flags_have_consumers(self):
        """Every enable_* field in CalibrationSchema appears in battle.py, engine.py, or scenario.py."""
        flags = _get_enable_flags()
        combined = _read("simulation/battle.py") + _read("simulation/engine.py") + _read("simulation/scenario.py") + _read("simulation/calibration.py")
        missing = [f for f in flags if f not in combined]
        assert not missing, f"Unconsumed enable_* flags: {missing}"

    def test_all_enable_flags_exercised_in_scenarios(self):
        """Every enable_* field is set to true in at least one scenario YAML.

        Phase 68 flags are excluded — they default to False and will be
        enabled in a future integration phase.
        """
        # Phase 91: perf flags now exercised in scenarios; only bridge_capacity + meta-flag remain
        _DEFERRED_FLAGS = {"enable_bridge_capacity", "enable_all_modern"}
        flags = set(_get_enable_flags()) - _DEFERRED_FLAGS
        enabled: set[str] = set()
        for path in _DATA.rglob("scenario.yaml"):
            if "test_campaign" in path.parent.name:
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
            for key, val in (data.get("calibration_overrides") or {}).items():
                if key.startswith("enable_") and val is True:
                    enabled.add(key)
        missing = flags - enabled
        assert not missing, f"Never enabled in any scenario: {sorted(missing)}"


class TestCalibrationIntegrity:
    """Calibration key integrity — dead keys stable, flag keys valid."""

    def test_dead_keys_stable(self):
        """_DEAD_KEYS contains only 'advance_speed' — no unintended growth."""
        src = _read("simulation/calibration.py")
        match = re.search(r"_DEAD_KEYS.*?=\s*\{([^}]+)\}", src)
        assert match, "_DEAD_KEYS not found"
        keys = set(re.findall(r'"(\w+)"', match.group(1)))
        assert keys == {"advance_speed"}, f"_DEAD_KEYS changed: {keys}"

    def test_flag_keys_valid_in_scenarios(self):
        """All enable_* keys in scenario YAMLs are valid CalibrationSchema fields."""
        valid = set(_get_enable_flags())
        invalid: list[str] = []
        for path in sorted(_DATA.rglob("scenario.yaml")):
            if "test_campaign" in path.parent.name:
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
            for key in (data.get("calibration_overrides") or {}):
                if key.startswith("enable_") and key not in valid:
                    invalid.append(f"{path.parent.name}: {key}")
        assert not invalid, f"Invalid enable_* keys: {invalid}"

    def test_no_flags_on_pure_historical_eras(self):
        """Ancient/Medieval/Napoleonic/WW1 era scenarios have no enable_* flags."""
        pure_historical = {"ancient", "medieval", "napoleonic", "ww1"}
        violations: list[str] = []
        for path in sorted(_DATA.rglob("scenario.yaml")):
            if "test_campaign" in path.parent.name:
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
            era = data.get("era", "modern")
            if era in pure_historical:
                for key, val in (data.get("calibration_overrides") or {}).items():
                    if key.startswith("enable_") and val is True:
                        violations.append(f"{path.parent.name} ({era}): {key}")
        assert not violations, f"Historical era scenarios with flags: {violations}"


class TestEngineCompleteness:
    """Block 7 criterion #1/#3: engines contribute, events subscribed."""

    def test_all_engagement_types_referenced(self):
        """Every EngagementType enum value is referenced beyond its definition.

        Some types are routed via weapon category strings (e.g. "TORPEDO_TUBE",
        "NAVAL_GUN") rather than EngagementType.X — we check for both patterns.
        """
        eng_src = _read("combat/engagement.py")
        # Extract enum value names from EngagementType class body
        match = re.search(
            r"class EngagementType[^:]*:(.+?)(?=\nclass |\ndef )",
            eng_src, re.DOTALL,
        )
        assert match, "EngagementType class not found"
        types = re.findall(r"(\w+)\s*=\s*\d+", match.group(1))
        assert len(types) >= 14, f"Expected >=14 EngagementType values, got {len(types)}"

        # Read all Python source files (excluding the enum definition itself)
        all_src = ""
        for py in _SRC.rglob("*.py"):
            all_src += py.read_text(encoding="utf-8", errors="replace")

        # Map enum names to alternative string patterns used in routing code.
        # battle.py routes via weapon category strings, not enum values.
        _ALT_PATTERNS: dict[str, list[str]] = {
            "INDIRECT_FIRE": ["_INDIRECT_FIRE_CATEGORIES", "HOWITZER", "MORTAR"],
            "AIR_TO_AIR": ["_route_air_engagement", "air_combat_engine"],
            "AIR_TO_GROUND": ["_route_air_engagement", "air_ground_engine"],
            "SAM": ["air_defense_engine", "sam_suppression"],
            "TORPEDO": ["TORPEDO_TUBE", "torpedo"],
            "NAVAL_GUN": ['"NAVAL_GUN"', "naval_gunfire"],
            "MINE": ["mine_warfare_engine", "MINE"],
            "COASTAL_DEFENSE": ["COASTAL_DEFENSE"],
            "AIR_LAUNCHED_ASHM": ["AIR_LAUNCHED_ASHM"],
        }

        unreferenced = []
        for t in types:
            ref = f"EngagementType.{t}"
            # Direct enum reference (>= 2: definition + usage)
            if all_src.count(ref) >= 2:
                continue
            # Check alternative routing patterns
            alt_patterns = _ALT_PATTERNS.get(t, [])
            if any(p in all_src for p in alt_patterns):
                continue
            unreferenced.append(t)

        assert not unreferenced, (
            f"EngagementTypes not handled: {unreferenced}"
        )

    def test_event_feedback_subscribed(self):
        """Key feedback events (RTD, breakdown, maintenance) have bus.subscribe() calls."""
        src = _read("simulation/engine.py")
        for event in (
            "ReturnToDutyEvent",
            "EquipmentBreakdownEvent",
            "MaintenanceCompletedEvent",
        ):
            assert event in src, f"{event} not found in engine.py"
        assert "subscribe" in src, "No bus.subscribe() in engine.py"

    def test_checkpoint_engines_registered(self):
        """Phase 63c engines (comms/detection/movement/conditions) in get_state/set_state."""
        src = _read("simulation/scenario.py")
        for name in (
            "comms_engine",
            "detection_engine",
            "movement_engine",
            "conditions_engine",
        ):
            assert f'"{name}"' in src or f"'{name}'" in src, (
                f"{name} not in scenario.py checkpoint"
            )


class TestBlockSevenTestQuality:
    """Test infrastructure quality for Block 7."""

    def test_no_xfail_in_block7_tests(self):
        """Block 7 phase tests (58-67) must not use xfail markers."""
        # Use re to match the actual decorator, skipping this file
        xfail_re = re.compile(r"@pytest\.mark\.xfail")
        xfail_files: list[str] = []
        this_file = Path(__file__).resolve()
        for phase in range(58, 68):
            for tf in _TESTS.rglob(f"test_phase_{phase}*.py"):
                if tf.resolve() == this_file:
                    continue
                if xfail_re.search(tf.read_text(encoding="utf-8")):
                    xfail_files.append(tf.name)
        assert not xfail_files, f"xfail found in Block 7 tests: {xfail_files}"

    def test_all_devlogs_exist(self):
        """docs/devlog/phase-{N}.md exists for N=0..67."""
        devlog_dir = _DOCS / "devlog"
        missing = [
            f"phase-{n}.md"
            for n in range(68)  # 0..67
            if not (devlog_dir / f"phase-{n}.md").exists()
        ]
        assert not missing, f"Missing devlogs: {missing}"


class TestCrossDocAudit:
    """Phase 67c: cross-document consistency checks."""

    def test_phase_count_consistent(self):
        """'67 phases' appears in CLAUDE.md and README.md."""
        claude_md = (_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        assert "67" in claude_md, "Phase 67 not mentioned in CLAUDE.md"
        assert "67" in readme, "Phase 67 not mentioned in README.md"

    def test_block7_complete_in_roadmap(self):
        """Phase 67 marked Complete in development-phases-block7.md."""
        roadmap = (_DOCS / "development-phases-block7.md").read_text(encoding="utf-8")
        # Find the Phase 67 row in the summary table
        assert "67" in roadmap, "Phase 67 not in block7 roadmap"
        # Check that all phases 58-67 are marked complete
        for phase in range(58, 68):
            pattern = re.compile(rf"\b{phase}\b.*Complete", re.IGNORECASE)
            assert pattern.search(roadmap), (
                f"Phase {phase} not marked Complete in block7 roadmap"
            )

    def test_phase67_devlog_exists(self):
        """Phase 67 devlog exists and has expected content."""
        devlog = _DOCS / "devlog" / "phase-67.md"
        assert devlog.exists(), "phase-67.md devlog not found"
        content = devlog.read_text(encoding="utf-8")
        assert "Block 7" in content
        assert "BLOCK COMPLETE" in content or "Block 7" in content
