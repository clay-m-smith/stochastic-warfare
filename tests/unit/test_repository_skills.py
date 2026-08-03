"""Repository-level contracts for the Codex phase workflow skills."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[2]
CLAUDE_SKILLS = REPO_ROOT / ".claude" / "skills"
CODEX_SKILLS = REPO_ROOT / ".agents" / "skills"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
BACKGROUND_HOOK = REPO_ROOT / ".claude" / "hooks" / "force-background-tests.sh"
EXPECTED_ROUTES = (
    "audit-determinism",
    "backtest",
    "calibrate",
    "compare",
    "cross-doc-audit",
    "design-review",
    "evaluate-scenarios",
    "orbat",
    "postmortem",
    "profile",
    "research-military",
    "research-models",
    "scenario",
    "simplify",
    "spec",
    "timeline",
    "update-docs",
    "validate-conventions",
    "validate-data",
    "what-if",
)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0] == "---", f"{path} has no YAML frontmatter"
    try:
        closing_index = lines.index("---", 1)
    except ValueError:
        pytest.fail(f"{path} has unclosed YAML frontmatter")
    metadata = yaml.safe_load("\n".join(lines[1:closing_index]))
    assert isinstance(metadata, dict), f"{path} frontmatter is not a mapping"
    return metadata


def test_every_claude_route_has_a_codex_port() -> None:
    claude_routes = {
        path.name for path in CLAUDE_SKILLS.iterdir() if (path / "SKILL.md").is_file() or (path / "prompt.md").is_file()
    }
    codex_routes = {path.name for path in CODEX_SKILLS.iterdir() if (path / "SKILL.md").is_file()}

    assert claude_routes == set(EXPECTED_ROUTES)
    assert codex_routes == claude_routes


def test_claude_routes_exactly_mirror_canonical_repository_skills() -> None:
    mismatches: list[str] = []
    obsolete_prompts: list[str] = []
    for route in EXPECTED_ROUTES:
        canonical = CODEX_SKILLS / route / "SKILL.md"
        provider = CLAUDE_SKILLS / route / "SKILL.md"
        if provider.read_bytes() != canonical.read_bytes():
            mismatches.append(route)
        if (CLAUDE_SKILLS / route / "prompt.md").exists():
            obsolete_prompts.append(route)

    assert mismatches == []
    assert obsolete_prompts == []


def test_claude_edit_hooks_express_current_rng_and_sensor_contract() -> None:
    settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    pre_tool_hooks = settings["hooks"]["PreToolUse"]
    prompt_hooks = [
        (hook["matcher"], hook["hooks"][0]["prompt"]) for hook in pre_tool_hooks if hook["hooks"][0]["type"] == "prompt"
    ]
    assert len(prompt_hooks) == 2
    assert all(matcher == "Edit|Write" for matcher, _ in prompt_hooks)

    python_prompt = next(prompt for _, prompt in prompt_hooks if "PRNG violations" in prompt)
    assert "RNGManager.get_stream(ModuleId.<SUBSYSTEM>)" in python_prompt
    assert "direct `default_rng()`" in python_prompt

    yaml_prompt = next(prompt for _, prompt in prompt_hooks if "UNIT YAML" in prompt)
    assert "sensor_policy" in yaml_prompt
    assert "EQUIPMENT_MAPPING_REGISTRY" in yaml_prompt
    assert "Mk 1 Eyeball" not in yaml_prompt
    assert "Field Binoculars" not in yaml_prompt
    assert "Naked Eye Observation" not in yaml_prompt

    command_hook = next(hook["hooks"][0] for hook in pre_tool_hooks if hook["hooks"][0]["type"] == "command")
    assert command_hook["command"] == "bash .claude/hooks/force-background-tests.sh"


def test_background_hook_keeps_focused_evaluation_in_foreground() -> None:
    def invoke(command: str) -> dict[str, object]:
        completed = subprocess.run(
            ["bash", str(BACKGROUND_HOOK)],
            input=json.dumps({"tool_input": {"command": command}}),
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    focused = invoke(
        "uv run python scripts/evaluate_scenarios.py --scenario 73_easting",
    )
    broad = invoke("uv run python scripts/evaluate_scenarios.py --no-details")

    focused_output = focused["hookSpecificOutput"]
    broad_output = broad["hookSpecificOutput"]
    assert "updatedInput" not in focused_output
    assert broad_output["updatedInput"]["run_in_background"] is True


@pytest.mark.parametrize("route", EXPECTED_ROUTES)
def test_codex_skill_manifest_is_portable_and_discoverable(route: str) -> None:
    skill_path = CODEX_SKILLS / route / "SKILL.md"
    metadata = _frontmatter(skill_path)
    text = skill_path.read_text(encoding="utf-8")

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == route
    assert isinstance(metadata["description"], str)
    assert metadata["description"].strip()
    assert "$ARGUMENTS" not in text
    assert "allowed-tools:" not in text
    assert "context: fork" not in text
    assert "agent: general-purpose" not in text


@pytest.mark.parametrize("route", EXPECTED_ROUTES)
def test_codex_skill_ui_metadata_matches_manifest(route: str) -> None:
    metadata_path = CODEX_SKILLS / route / "agents" / "openai.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))

    assert isinstance(metadata, dict)
    assert set(metadata) == {"interface"}
    interface = metadata["interface"]
    assert isinstance(interface, dict)
    assert set(interface) == {
        "display_name",
        "short_description",
        "default_prompt",
    }
    assert isinstance(interface["display_name"], str)
    assert 25 <= len(interface["short_description"]) <= 64
    assert f"${route}" in interface["default_prompt"]
