"""Check or refresh provider views of canonical repository workflow skills."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = ROOT / ".agents" / "skills"
PROVIDER_ROOT = ROOT / ".claude" / "skills"


def _routes(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.parent.name
            for path in root.glob("*/SKILL.md")
        ),
    )


def _audit() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    canonical_routes = _routes(CANONICAL_ROOT)
    provider_routes = _routes(PROVIDER_ROOT)
    missing_or_stale = tuple(
        sorted(set(canonical_routes).symmetric_difference(provider_routes)),
    )
    unsafe: list[str] = []
    mismatched: list[str] = []
    for route in sorted(set(canonical_routes).intersection(provider_routes)):
        canonical = CANONICAL_ROOT / route / "SKILL.md"
        provider = PROVIDER_ROOT / route / "SKILL.md"
        if provider.is_symlink() or not provider.is_file():
            unsafe.append(route)
        elif provider.read_bytes() != canonical.read_bytes():
            mismatched.append(route)
    return missing_or_stale, tuple(unsafe), tuple(mismatched)


def _refresh() -> None:
    for route in _routes(CANONICAL_ROOT):
        canonical = CANONICAL_ROOT / route / "SKILL.md"
        provider = PROVIDER_ROOT / route / "SKILL.md"
        if provider.is_symlink():
            raise ValueError(
                f"provider skill projection must not be a symlink: {provider}",
            )
        provider.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(canonical, provider)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="refresh provider files from the canonical repository skills",
    )
    arguments = parser.parse_args()
    if arguments.write:
        _refresh()
    missing_or_stale, unsafe, mismatched = _audit()
    payload = {
        "canonical_routes": len(_routes(CANONICAL_ROOT)),
        "mismatched": list(mismatched),
        "missing_or_stale": list(missing_or_stale),
        "unsafe": list(unsafe),
    }
    print(json.dumps(payload, sort_keys=True))
    return int(bool(missing_or_stale or unsafe or mismatched))


if __name__ == "__main__":
    raise SystemExit(main())
