"""Repository-level contracts for the Codex phase workflow skills."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[2]
CLAUDE_SKILLS = REPO_ROOT / ".claude" / "skills"
CODEX_SKILLS = REPO_ROOT / ".agents" / "skills"
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
        path.name
        for path in CLAUDE_SKILLS.iterdir()
        if (path / "SKILL.md").is_file() or (path / "prompt.md").is_file()
    }
    codex_routes = {
        path.name
        for path in CODEX_SKILLS.iterdir()
        if (path / "SKILL.md").is_file()
    }

    assert claude_routes == set(EXPECTED_ROUTES)
    assert codex_routes == claude_routes


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
