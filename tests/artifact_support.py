"""Shared offline artifact fixture for standard and API partitions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterator

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BuiltArtifacts:
    wheel: Path
    sdist: Path
    revision: str


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module", name="built_artifacts")
def built_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[BuiltArtifacts]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required for the isolated artifact contract")
    revision = subprocess.run(
        ("git", "-C", os.fspath(REPOSITORY_ROOT), "rev-parse", "--verify", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    output = tmp_path_factory.mktemp("application-artifacts")
    environment = dict(os.environ)
    environment.update(
        {
            "SOURCE_REVISION": revision,
            "UV_OFFLINE": "1",
        },
    )
    stale_outputs = (
        REPOSITORY_ROOT / "build/lib/evil.py",
        REPOSITORY_ROOT / "build/lib/stochastic_warfare/tools/profiling.py",
        REPOSITORY_ROOT / "build/lib/stochastic_warfare_extra/stale.py",
    )
    for stale in stale_outputs:
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("STALE = True\n", encoding="utf-8")
    try:
        run_command(
            [uv, "build", "--offline", "--out-dir", os.fspath(output)],
            cwd=REPOSITORY_ROOT,
            environment=environment,
        )
    finally:
        for stale in stale_outputs:
            stale.unlink(missing_ok=True)
    wheel, = output.glob("*.whl")
    sdist, = output.glob("*.tar.gz")
    yield BuiltArtifacts(wheel=wheel, sdist=sdist, revision=revision)
