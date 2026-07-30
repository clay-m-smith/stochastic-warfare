"""Audit the exact union and disjointness of Phase 112 pytest partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Mapping, Sequence

if __package__:
    from scripts.run_pytest_partition import (
        AUDITED_PARTITIONS,
        PARTITION_SPECS,
        PartitionCollectionError,
        collect_node_ids,
        collect_partition_node_ids,
    )
else:
    from run_pytest_partition import (
        AUDITED_PARTITIONS,
        PARTITION_SPECS,
        PartitionCollectionError,
        collect_node_ids,
        collect_partition_node_ids,
    )


def _digest(node_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(node_ids).encode("utf-8")).hexdigest()


def validate_partition_sets(
    superset: Sequence[str],
    partitions: Mapping[str, Sequence[str]],
) -> None:
    """Reject empty, overlapping, missing, or extra partition node-ID sets."""

    superset_set = set(superset)
    errors: list[str] = []
    for name in AUDITED_PARTITIONS:
        node_ids = set(partitions.get(name, ()))
        if not node_ids:
            errors.append(f"partition {name!r} is empty")
        outside = sorted(node_ids - superset_set)
        if outside:
            errors.append(
                f"partition {name!r} contains {len(outside)} nodes outside "
                f"superset; first={outside[0]!r}"
            )

    for left, right in combinations(AUDITED_PARTITIONS, 2):
        overlap = sorted(set(partitions.get(left, ())) & set(partitions.get(right, ())))
        if overlap:
            errors.append(
                f"partitions {left!r} and {right!r} overlap on "
                f"{len(overlap)} nodes; first={overlap[0]!r}"
            )

    union: set[str] = set()
    for name in AUDITED_PARTITIONS:
        union.update(partitions.get(name, ()))
    missing = sorted(superset_set - union)
    extra = sorted(union - superset_set)
    if missing:
        errors.append(
            f"partition union misses {len(missing)} superset nodes; "
            f"first={missing[0]!r}"
        )
    if extra:
        errors.append(
            f"partition union contains {len(extra)} extra nodes; first={extra[0]!r}"
        )
    if errors:
        raise ValueError("\n".join(errors))


def build_audit_payload(
    superset: Sequence[str],
    partitions: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    """Build deterministic machine-readable partition evidence."""

    return {
        "schema_version": 1,
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
                "selector": {
                    "paths": list(PARTITION_SPECS[name].paths),
                    "ignored_paths": list(PARTITION_SPECS[name].ignored_paths),
                    "marker_expression": PARTITION_SPECS[name].marker_expression,
                },
            }
            for name in AUDITED_PARTITIONS
        },
        "exact_union": True,
        "pairwise_disjoint": True,
    }


def run_audit(*, output_path: Path | None) -> dict[str, object]:
    """Collect the locked-environment superset and all six partitions."""

    superset = collect_node_ids(("tests",))
    partitions = {
        name: collect_partition_node_ids(name) for name in AUDITED_PARTITIONS
    }
    validate_partition_sets(superset, partitions)
    payload = build_audit_payload(superset, partitions)

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
                        "schema_version": 1,
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
