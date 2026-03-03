"""Phase 7 validation visualizations.

Generates:
- MC distribution histograms for each scenario metric
- Scenario comparison bar charts
- Convergence plots (running mean vs iteration count)

Usage::

    uv run python scripts/visualize/validation_viz.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from stochastic_warfare.validation.historical_data import HistoricalDataLoader
from stochastic_warfare.validation.metrics import EngagementMetrics
from stochastic_warfare.validation.monte_carlo import MonteCarloConfig, MonteCarloHarness
from stochastic_warfare.validation.scenario_runner import ScenarioRunner, ScenarioRunnerConfig

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

SCENARIOS = {
    "73_easting": "data/scenarios/73_easting/scenario.yaml",
    "falklands_naval": "data/scenarios/falklands_naval/scenario.yaml",
    "golan_heights": "data/scenarios/golan_heights/scenario.yaml",
}

NUM_ITERATIONS = 30  # fast default for visualization; use 100+ for real analysis
SEED = 42


def run_mc(scenario_path: str, n: int = NUM_ITERATIONS) -> dict:
    """Run Monte Carlo for a scenario and return raw per-run metrics."""
    loader = HistoricalDataLoader()
    eng = loader.load(Path(scenario_path))

    runner_config = ScenarioRunnerConfig(master_seed=SEED, max_ticks=10000, data_dir="data")
    runner = ScenarioRunner(runner_config)

    mc_config = MonteCarloConfig(num_iterations=n, base_seed=SEED)
    harness = MonteCarloHarness(runner, mc_config)
    mc_result = harness.run(eng)

    # Collect per-run metrics
    all_metrics: dict[str, list[float]] = {}
    for run in mc_result.runs:
        for k, v in run.metrics.items():
            all_metrics.setdefault(k, []).append(v)
    return all_metrics


def plot_histograms(scenario_name: str, metrics: dict, historical: dict) -> None:
    """Plot histograms for key metrics with historical reference lines."""
    key_metrics = [
        ("exchange_ratio", "Exchange Ratio (red:blue)"),
        ("duration_s", "Duration (s)"),
        ("red_units_destroyed", "Red Units Destroyed"),
        ("blue_units_destroyed", "Blue Units Destroyed"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f"{scenario_name} — MC Distribution (N={NUM_ITERATIONS})", fontsize=14)

    for ax, (metric_key, label) in zip(axes.flat, key_metrics):
        values = metrics.get(metric_key, [])
        if not values:
            ax.set_title(label)
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            continue

        # Filter out inf for plotting
        finite_vals = [v for v in values if np.isfinite(v)]
        inf_count = len(values) - len(finite_vals)

        if finite_vals:
            ax.hist(finite_vals, bins=20, alpha=0.7, edgecolor="black")
        if inf_count > 0:
            ax.set_title(f"{label} ({inf_count} inf values)")
        else:
            ax.set_title(label)

        # Historical reference line
        hist_val = historical.get(metric_key)
        if hist_val is not None and np.isfinite(hist_val):
            ax.axvline(hist_val, color="red", linestyle="--", linewidth=2, label=f"Historical: {hist_val}")
            ax.legend()

        ax.set_xlabel(label)
        ax.set_ylabel("Count")

    plt.tight_layout()
    out_path = OUTPUT_DIR / f"{scenario_name}_histograms.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {out_path}")


def plot_convergence(scenario_name: str, metrics: dict) -> None:
    """Plot running mean of exchange ratio vs iteration count."""
    values = metrics.get("exchange_ratio", [])
    finite_vals = [v for v in values if np.isfinite(v)]
    if len(finite_vals) < 5:
        return

    running_mean = np.cumsum(finite_vals) / np.arange(1, len(finite_vals) + 1)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(range(1, len(running_mean) + 1), running_mean, "b-", linewidth=1.5)
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Running Mean Exchange Ratio")
    ax.set_title(f"{scenario_name} — Exchange Ratio Convergence")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = OUTPUT_DIR / f"{scenario_name}_convergence.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {out_path}")


def plot_scenario_comparison(all_results: dict) -> None:
    """Bar chart comparing exchange ratios across scenarios."""
    names = []
    means = []
    stds = []
    historicals = []

    loader = HistoricalDataLoader()
    for name, path in SCENARIOS.items():
        eng = loader.load(Path(path))
        hist_exchange = None
        for m in eng.documented_outcomes:
            if m.name == "exchange_ratio":
                hist_exchange = m.value
                break

        values = all_results.get(name, {}).get("exchange_ratio", [])
        finite_vals = [v for v in values if np.isfinite(v)]

        if finite_vals:
            names.append(name.replace("_", " ").title())
            means.append(np.mean(finite_vals))
            stds.append(np.std(finite_vals))
            historicals.append(hist_exchange if hist_exchange else 0)

    if not names:
        return

    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, means, width, yerr=stds, label="Simulated (mean +/- std)", alpha=0.8)
    ax.bar(x + width / 2, historicals, width, label="Historical", alpha=0.8, color="orange")

    ax.set_xlabel("Scenario")
    ax.set_ylabel("Exchange Ratio (red:blue)")
    ax.set_title("Scenario Comparison — Exchange Ratios")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out_path = OUTPUT_DIR / "scenario_comparison.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved {out_path}")


def main() -> None:
    """Generate all Phase 7 validation plots."""
    print(f"Running MC with {NUM_ITERATIONS} iterations per scenario...\n")

    all_results: dict[str, dict] = {}
    loader = HistoricalDataLoader()

    for name, path in SCENARIOS.items():
        print(f"Scenario: {name}")
        metrics = run_mc(path, NUM_ITERATIONS)
        all_results[name] = metrics

        # Get historical values for reference lines
        eng = loader.load(Path(path))
        historical = {m.name: m.value for m in eng.documented_outcomes}

        plot_histograms(name, metrics, historical)
        plot_convergence(name, metrics)
        print()

    plot_scenario_comparison(all_results)
    print("\nAll visualizations saved to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
