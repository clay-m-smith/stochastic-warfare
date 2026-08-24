"""Audit the exact union and disjointness of repository pytest partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

if __name__ == "__main__":
    _PYCACHE_DIRECTORY = tempfile.TemporaryDirectory(
        prefix="stochastic-warfare-audit-pycache-",
    )
    sys.dont_write_bytecode = True
    sys.pycache_prefix = _PYCACHE_DIRECTORY.name

if __package__:
    from scripts.run_pytest_partition import (
        AUDITED_PARTITIONS,
        PartitionCollectionError,
        collect_node_ids,
        collect_partition_node_ids,
        partition_selector_payload,
        repository_revision,
        validate_partition_sets,
    )
else:
    from run_pytest_partition import (
        AUDITED_PARTITIONS,
        PartitionCollectionError,
        collect_node_ids,
        collect_partition_node_ids,
        partition_selector_payload,
        repository_revision,
        validate_partition_sets,
    )


def _digest(node_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(node_ids).encode("utf-8")).hexdigest()


def build_audit_payload(
    superset: Sequence[str],
    partitions: Mapping[str, Sequence[str]],
    *,
    revision: Mapping[str, object],
) -> dict[str, object]:
    """Build deterministic machine-readable partition evidence."""

    return {
        "schema_version": 2,
        "revision": dict(revision),
        "superset": {
            "count": len(superset),
            "node_ids_sha256": _digest(superset),
            "node_ids": list(superset),
        },
        "partitions": {
            name: {
                "count": len(partitions[name]),
                "node_ids_sha256": _digest(partitions[name]),
                "node_ids": list(partitions[name]),
                "selector": partition_selector_payload(name),
            }
            for name in AUDITED_PARTITIONS
        },
        "exact_union": True,
        "pairwise_disjoint": True,
    }


def run_audit(*, output_path: Path | None) -> dict[str, object]:
    """Collect the locked-environment superset and all six partitions."""

    initial_revision = repository_revision()
    superset = collect_node_ids(("tests",))
    partitions = {
        name: collect_partition_node_ids(name) for name in AUDITED_PARTITIONS
    }
    validate_partition_sets(superset, partitions)
    final_revision = repository_revision()
    if final_revision != initial_revision:
        raise PartitionCollectionError(
            "repository revision changed while pytest partitions were collected",
        )
    payload = build_audit_payload(
        superset,
        partitions,
        revision=initial_revision,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    counts = {
        name: payload["partitions"][name]["count"]  # type: ignore[index]
        for name in AUDITED_PARTITIONS
    }
    print(
        json.dumps(
            {
                "exact_union": True,
                "pairwise_disjoint": True,
                "superset_count": len(superset),
                "partition_counts": counts,
            },
            sort_keys=True,
        )
    )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the deterministic node-ID audit JSON to this path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        run_audit(output_path=arguments.output)
    except (PartitionCollectionError, ValueError) as error:
        print(f"PARTITION_AUDIT_ERROR={error}", file=sys.stderr)
        if arguments.output is not None:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "exact_union": False,
                        "pairwise_disjoint": False,
                        "error": str(error),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
