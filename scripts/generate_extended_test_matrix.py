"""Generate the nightly slow/benchmark CI matrix from one audit manifest."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

if __name__ == "__main__":
    _PYCACHE_DIRECTORY = tempfile.TemporaryDirectory(
        prefix="stochastic-warfare-matrix-pycache-",
    )
    sys.dont_write_bytecode = True
    sys.pycache_prefix = _PYCACHE_DIRECTORY.name

if __package__:
    from scripts.run_pytest_partition import (
        PartitionCollectionError,
        _plan_shards,
        load_audit_manifest,
    )
else:
    from run_pytest_partition import (
        PartitionCollectionError,
        _plan_shards,
        load_audit_manifest,
    )


@dataclass(frozen=True)
class ExtendedPartitionPolicy:
    """Operational shard and timeout policy for one nightly partition."""

    partition: str
    shard_count: int
    timeout_seconds: int


EXTENDED_PARTITION_POLICIES = (
    ExtendedPartitionPolicy("slow-only", shard_count=15, timeout_seconds=14_400),
    ExtendedPartitionPolicy("benchmark-only", shard_count=3, timeout_seconds=2_400),
    ExtendedPartitionPolicy("slow-benchmark", shard_count=1, timeout_seconds=4_200),
)


def build_extended_matrix(
    partitions: Mapping[str, Sequence[str]],
) -> dict[str, list[dict[str, int | str]]]:
    """Expand policy into deterministic rows and reject any empty shard."""

    include: list[dict[str, int | str]] = []
    for policy in EXTENDED_PARTITION_POLICIES:
        node_ids = partitions.get(policy.partition, ())
        plan = _plan_shards(node_ids, shard_count=policy.shard_count)
        empty = [index for index, shard in enumerate(plan.shards) if not shard]
        if empty:
            raise PartitionCollectionError(
                f"generated {policy.partition!r} matrix has empty shards: {empty}",
            )
        include.extend(
            {
                "partition": policy.partition,
                "shard_index": shard_index,
                "shard_count": policy.shard_count,
                "timeout_seconds": policy.timeout_seconds,
            }
            for shard_index in range(policy.shard_count)
        )
    return {"include": include}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-manifest", required=True, type=Path)
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Prefix compact JSON with 'matrix=' for GITHUB_OUTPUT.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        audit = load_audit_manifest(arguments.audit_manifest)
        matrix = build_extended_matrix(audit.partitions)
    except (PartitionCollectionError, ValueError) as error:
        print(f"EXTENDED_MATRIX_ERROR={error}", file=sys.stderr)
        return 1
    serialized = json.dumps(matrix, separators=(",", ":"), sort_keys=True)
    print(f"matrix={serialized}" if arguments.github_output else serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
