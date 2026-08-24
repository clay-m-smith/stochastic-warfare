"""Production headless command-line interface."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

from stochastic_warfare import __version__
from stochastic_warfare.application_paths import (
    ApplicationPaths,
    ApplicationResourceError,
)
from stochastic_warfare.simulation.engine import RuntimeExecutionMode
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)
from stochastic_warfare.tools.serializers import serialize_to_dict


@dataclass(frozen=True, slots=True)
class CliRunSummary:
    """Stable JSON summary emitted by one production CLI run."""

    version: str
    scenario: str
    scenario_path: str
    catalog_root: str
    seed: int
    max_ticks: int
    ticks_executed: int
    duration_s: float
    execution_mode: str
    authoritative: bool
    victory: dict[str, object]
    provenance: dict[str, object]


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "value must be a non-negative integer",
        ) from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be a non-negative integer",
        )
    return parsed


def _positive_int(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError(
            "value must be a positive integer",
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser without resolving application resources."""
    parser = argparse.ArgumentParser(
        prog="stochastic-warfare",
        description="Run Stochastic Warfare scenarios through the production runtime",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run",
        help="run one catalog scenario",
    )
    run.add_argument(
        "scenario",
        help="catalog scenario name or explicit scenario.yaml path",
    )
    run.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="external authoritative data directory",
    )
    run.add_argument("--seed", type=_non_negative_int, default=42)
    run.add_argument("--max-ticks", type=_positive_int, default=10_000)
    return parser


def run_scenario(
    *,
    scenario_reference: str | Path,
    data_root: str | Path | None,
    seed: int,
    max_ticks: int,
) -> CliRunSummary:
    """Execute one scenario through the authoritative production factory."""
    paths = ApplicationPaths.discover(catalog_root=data_root)
    scenario_path = paths.resolve_scenario(scenario_reference)
    variant = AnalysisVariant(variant_id="cli-run")
    prepared = SimulationRuntimeFactory().prepare(
        scenario_path,
        paths.catalog_root,
        (variant,),
    )
    session = prepared.build(
        variant.variant_id,
        seed=seed,
        max_ticks=max_ticks,
        execution_mode=RuntimeExecutionMode.STRICT,
    )
    result = session.run_to_completion()
    provenance = session.provenance()
    if not result.authoritative or not provenance.authoritative:
        raise RuntimeError(
            "production CLI cannot publish a degraded runtime result",
        )
    return CliRunSummary(
        version=__version__,
        scenario=prepared.source_config.name,
        scenario_path=str(prepared.scenario_path),
        catalog_root=str(prepared.data_root),
        seed=seed,
        max_ticks=max_ticks,
        ticks_executed=result.ticks_executed,
        duration_s=result.duration_s,
        execution_mode=result.execution_mode.value,
        authoritative=True,
        victory=serialize_to_dict(result.victory_result),
        provenance=serialize_to_dict(provenance),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the product CLI and return a process exit status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command != "run":
            parser.error(f"unsupported command: {arguments.command!r}")
        summary = run_scenario(
            scenario_reference=arguments.scenario,
            data_root=arguments.data_root,
            seed=arguments.seed,
            max_ticks=arguments.max_ticks,
        )
    except (
        ApplicationResourceError,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"stochastic-warfare: error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            asdict(summary),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    return 0
