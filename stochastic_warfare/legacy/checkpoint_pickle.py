"""Trusted, offline conversion for obsolete pickle checkpoints.

Pickle can execute arbitrary code while decoding.  Nothing in the runtime
checkpoint path imports or calls this module.  Operators must opt in with the
literal ``trusted=True`` argument (or ``--trusted-input`` in the module CLI)
after independently establishing the payload's provenance.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pickle
from typing import Any, Sequence

from stochastic_warfare.core.checkpoint import NumpyEncoder


class UnsafeLegacyCheckpointError(ValueError):
    """A legacy checkpoint was not explicitly trusted or was malformed."""


def load_trusted_pickle_checkpoint(
    data: bytes,
    *,
    trusted: bool = False,
) -> dict[str, Any]:
    """Decode one explicitly trusted binary pickle checkpoint.

    This function is intentionally unsafe for untrusted bytes.  The opt-in is
    a misuse guard, not a sandbox or a substitute for provenance verification.
    """
    if trusted is not True:
        raise UnsafeLegacyCheckpointError(
            "legacy pickle decoding requires explicit trusted=True",
        )
    if not isinstance(data, bytes) or not data.startswith(b"\x80"):
        raise UnsafeLegacyCheckpointError(
            "legacy input must be a binary-protocol pickle payload",
        )
    value = pickle.loads(data)  # noqa: S301 - explicit trusted migration only
    if not isinstance(value, dict):
        raise UnsafeLegacyCheckpointError(
            "legacy checkpoint top level must be a mapping",
        )
    return value


def convert_trusted_pickle_checkpoint(
    data: bytes,
    *,
    trusted: bool = False,
) -> bytes:
    """Convert one explicitly trusted legacy payload to strict JSON bytes."""
    value = load_trusted_pickle_checkpoint(data, trusted=trusted)
    try:
        return json.dumps(
            value,
            cls=NumpyEncoder,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise UnsafeLegacyCheckpointError(
            "legacy checkpoint cannot be represented as strict JSON",
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a trusted legacy pickle checkpoint to JSON. Pickle can "
            "execute code; never use this tool with an untrusted payload."
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--trusted-input",
        action="store_true",
        help="confirm that the input provenance was independently verified",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit local conversion command."""
    args = _parser().parse_args(argv)
    if not args.trusted_input:
        raise SystemExit(
            "refusing to unpickle without --trusted-input; verify provenance first",
        )
    input_path = args.input.resolve(strict=True)
    output_path = args.output.resolve()
    if input_path == output_path:
        raise SystemExit("input and output paths must differ")
    if output_path.exists() and not args.force:
        raise SystemExit("output exists; pass --force to replace it")
    converted = convert_trusted_pickle_checkpoint(
        input_path.read_bytes(),
        trusted=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(converted)
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "UnsafeLegacyCheckpointError",
    "convert_trusted_pickle_checkpoint",
    "load_trusted_pickle_checkpoint",
    "main",
]
