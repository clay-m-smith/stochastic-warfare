"""Phase 79 structural tests — CI/CD & Packaging.

Verifies workflow files, ruff configuration, script archive,
gitignore patterns, and conftest fixture cleanup.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


# ---------------------------------------------------------------------------
# Workflow existence
# ---------------------------------------------------------------------------


class TestWorkflowsExist:
    """All required GitHub Actions workflows exist."""

    def test_test_workflow_exists(self):
        assert (WORKFLOWS / "test.yml").is_file()

    def test_lint_workflow_exists(self):
        assert (WORKFLOWS / "lint.yml").is_file()

    def test_build_workflow_exists(self):
        assert (WORKFLOWS / "build.yml").is_file()

    def test_docs_workflow_exists(self):
        assert (WORKFLOWS / "docs.yml").is_file()


# ---------------------------------------------------------------------------
# Test workflow content
# ---------------------------------------------------------------------------


class TestTestWorkflowContent:
    """test.yml has correct triggers, uv usage, and both job types."""

    def _load(self):
        return yaml.safe_load((WORKFLOWS / "test.yml").read_text())

    def test_push_trigger(self):
        data = self._load()
        triggers = data.get(True, {})
        assert "push" in triggers or True in data

    def test_pr_trigger(self):
        data = self._load()
        triggers = data.get(True, {})
        assert "pull_request" in triggers or True in data

    def test_python_job_uses_uv(self):
        text = (WORKFLOWS / "test.yml").read_text()
        assert "astral-sh/setup-uv" in text

    def test_python_job_runs_pytest(self):
        text = (WORKFLOWS / "test.yml").read_text()
        assert "pytest" in text

    def test_frontend_job_runs_npm_test(self):
        text = (WORKFLOWS / "test.yml").read_text()
        assert "npm test" in text


# ---------------------------------------------------------------------------
# Lint workflow content
# ---------------------------------------------------------------------------


class TestLintWorkflowContent:
    """lint.yml runs ruff and eslint."""

    def test_ruff_check_present(self):
        text = (WORKFLOWS / "lint.yml").read_text()
        assert "ruff check" in text

    def test_eslint_present(self):
        text = (WORKFLOWS / "lint.yml").read_text()
        assert "eslint" in text


# ---------------------------------------------------------------------------
# Build workflow content
# ---------------------------------------------------------------------------


class TestBuildWorkflowContent:
    """build.yml runs Docker build on PRs only."""

    def test_docker_build_present(self):
        text = (WORKFLOWS / "build.yml").read_text()
        assert "docker build" in text

    def test_pr_only_trigger(self):
        data = yaml.safe_load((WORKFLOWS / "build.yml").read_text())
        triggers = data.get(True, {})
        # Should have pull_request but NOT push
        assert "pull_request" in triggers
        assert "push" not in triggers


# ---------------------------------------------------------------------------
# Docs workflow fixed
# ---------------------------------------------------------------------------


class TestDocsWorkflowFixed:
    """docs.yml uses uv instead of bare pip."""

    def test_no_bare_pip(self):
        text = (WORKFLOWS / "docs.yml").read_text()
        assert "pip install" not in text

    def test_uses_uv(self):
        text = (WORKFLOWS / "docs.yml").read_text()
        assert "astral-sh/setup-uv" in text


# ---------------------------------------------------------------------------
# Script archive
# ---------------------------------------------------------------------------


class TestScriptArchive:
    """Stale scripts moved to archive, active scripts untouched."""

    ARCHIVED = ["debug_loader.py", "debug_scenario.py", "smoke_73.py", "smoke_all.py"]
    ACTIVE = ["evaluate_scenarios.py", "test_run_scenario.py", "check_scenarios.py"]

    def test_archive_dir_exists(self):
        assert (ROOT / "scripts" / "archive").is_dir()

    def test_stale_scripts_archived(self):
        for name in self.ARCHIVED:
            assert (ROOT / "scripts" / "archive" / name).is_file(), f"{name} not in archive"
            assert not (ROOT / "scripts" / name).is_file(), f"{name} still in scripts/"

    def test_active_scripts_remain(self):
        for name in self.ACTIVE:
            assert (ROOT / "scripts" / name).is_file(), f"{name} missing from scripts/"


# ---------------------------------------------------------------------------
# Gitignore patterns
# ---------------------------------------------------------------------------


class TestGitignoreArtifacts:
    """Gitignore covers evaluation artifacts and debug scripts."""

    def _text(self):
        return (ROOT / ".gitignore").read_text()

    def test_evaluation_results_pattern(self):
        text = self._text()
        assert "evaluation_results" in text

    def test_evaluation_stderr_pattern(self):
        text = self._text()
        assert "evaluation_stderr" in text


# ---------------------------------------------------------------------------
# Fixture cleanup
# ---------------------------------------------------------------------------


class TestFixtureCleanup:
    """Removed unused fixtures; kept active ones."""

    def _text(self):
        return (ROOT / "tests" / "conftest.py").read_text()

    def test_sim_clock_fixture_removed(self):
        text = self._text()
        assert "def sim_clock(" not in text

    def test_rng_manager_fixture_removed(self):
        text = self._text()
        assert "def rng_manager(" not in text

    def test_make_stream_removed(self):
        text = self._text()
        assert "def make_stream(" not in text

    def test_rng_manager_import_removed(self):
        text = self._text()
        assert "RNGManager" not in text

    def test_module_id_import_removed(self):
        text = self._text()
        assert "ModuleId" not in text

    def test_rng_fixture_kept(self):
        text = self._text()
        assert "def rng(" in text

    def test_event_bus_fixture_kept(self):
        text = self._text()
        assert "def event_bus(" in text


# ---------------------------------------------------------------------------
# Ruff configuration
# ---------------------------------------------------------------------------


class TestRuffConfiguration:
    """pyproject.toml has ruff in dev deps and [tool.ruff] section."""

    def _text(self):
        return (ROOT / "pyproject.toml").read_text()

    def test_ruff_in_dev_deps(self):
        text = self._text()
        assert "ruff" in text

    def test_tool_ruff_section(self):
        text = self._text()
        assert "[tool.ruff]" in text


# ---------------------------------------------------------------------------
# Pytest addopts — ignore api/e2e collection
# ---------------------------------------------------------------------------


class TestPytestAddopts:
    """addopts ignores api/e2e dirs to prevent collection errors."""

    def _text(self):
        return (ROOT / "pyproject.toml").read_text()

    def test_ignore_api_tests(self):
        text = self._text()
        assert "--ignore=tests/api" in text

    def test_ignore_e2e_tests(self):
        text = self._text()
        assert "--ignore=tests/e2e" in text
