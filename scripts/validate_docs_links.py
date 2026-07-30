"""Prove that strict MkDocs validation rejects missing fragment anchors."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


_CONFIG = """\
site_name: Phase 112 anchor validation
docs_dir: docs
site_dir: site
validation:
  links:
    anchors: warn
nav:
  - Home: index.md
  - Target: target.md
"""
_EXPECTED_MISSING_ANCHOR_DIAGNOSTIC = (
    "contains a link 'target.md#missing', but the doc 'target.md' does not contain an anchor '#missing'"
)


def _has_expected_missing_anchor_diagnostic(output: str) -> bool:
    """Recognize only the locked MkDocs missing-anchor control diagnostic."""
    return _EXPECTED_MISSING_ANCHOR_DIAGNOSTIC in output


def _run_build(root: Path, *, fragment: str) -> subprocess.CompletedProcess[str]:
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True)
    (root / "mkdocs.yml").write_text(_CONFIG, encoding="utf-8")
    (docs_dir / "index.md").write_text(
        f"# Home\n\n[Target](target.md#{fragment})\n",
        encoding="utf-8",
    )
    (docs_dir / "target.md").write_text(
        "# Target\n\n## Existing fragment\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(root / "mkdocs.yml"),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sw-doc-links-") as temp_root:
        invalid = _run_build(Path(temp_root) / "invalid", fragment="missing")
        valid = _run_build(
            Path(temp_root) / "valid",
            fragment="existing-fragment",
        )

    invalid_output = f"{invalid.stdout}\n{invalid.stderr}"
    invalid_diagnostic = _has_expected_missing_anchor_diagnostic(
        invalid_output,
    )
    payload = {
        "invalid_exit_code": invalid.returncode,
        "invalid_diagnostic": invalid_diagnostic,
        "valid_exit_code": valid.returncode,
    }
    print(json.dumps(payload, sort_keys=True))

    if invalid.returncode == 0:
        print("missing-fragment control unexpectedly passed", file=sys.stderr)
        return 1
    if not invalid_diagnostic:
        print(
            "exact missing-fragment anchor diagnostic was not reported",
            file=sys.stderr,
        )
        print(invalid_output, file=sys.stderr)
        return 1
    if valid.returncode != 0:
        print(valid.stdout, file=sys.stderr)
        print(valid.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
