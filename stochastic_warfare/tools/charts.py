"""Reusable chart library for simulation visualization.

Six standalone chart functions, each returning a ``matplotlib.figure.Figure``.
No ``plt.show()`` — callers decide how to display or save.
"""

from __future__ import annotations

from typing import Any

import numpy as np

import matplotlib
matplotlib.use("Agg")

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

_SUPPLY_CRITICAL_THRESHOLD = 0.2


def force_strength_chart(
    time_series_by_side: dict[str, list[tuple[float, float]]],
) -> Any:
    """Stacked area chart of active units over time.

    Parameters
    ----------
    time_series_by_side:
        ``{side_name: [(tick, count), ...]}``

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    for side, series in sorted(time_series_by_side.items()):
        if not series:
            continue
        ticks = [p[0] for p in series]
        counts = [p[1] for p in series]
        ax.plot(ticks, counts, label=side, linewidth=2)
        ax.fill_between(ticks, counts, alpha=0.2)

    ax.set_xlabel("Tick")
    ax.set_ylabel("Active Units")
    ax.set_title("Force Strength Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def engagement_network(
    events: list[dict[str, Any]],
    unit_sides: dict[str, str],
) -> Any:
    """Network graph of engagement relationships.

    Parameters
    ----------
    events:
        List of engagement event dicts with ``attacker_id``, ``target_id``, ``result``.
    unit_sides:
        ``{unit_id: side_name}`` for coloring nodes.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt
    import networkx as nx

    G = nx.DiGraph()
    for ev in events:
        attacker = ev.get("attacker_id", "?")
        target = ev.get("target_id", "?")
        result = ev.get("result", "unknown")
        G.add_node(attacker)
        G.add_node(target)
        G.add_edge(attacker, target, result=result)

    fig, ax = plt.subplots(figsize=(10, 8))

    if len(G.nodes) == 0:
        ax.text(0.5, 0.5, "No engagements", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    pos = nx.spring_layout(G, seed=42)
    side_colors = {"blue": "#4477AA", "red": "#CC6677"}
    node_colors = [side_colors.get(unit_sides.get(n, ""), "#999999") for n in G.nodes]

    edge_colors = []
    for u, v, d in G.edges(data=True):
        r = d.get("result", "")
        if r == "hit":
            edge_colors.append("#CC0000")
        elif r == "miss":
            edge_colors.append("#AAAAAA")
        else:
            edge_colors.append("#666666")

    nx.draw(
        G, pos, ax=ax,
        node_color=node_colors, node_size=300,
        edge_color=edge_colors,
        with_labels=True, font_size=7,
        arrows=True, arrowsize=12,
    )
    ax.set_title("Engagement Network")
    plt.close(fig)
    return fig


def supply_flow_diagram(
    snapshots: list[dict[str, Any]],
    side: str,
) -> Any:
    """Supply level timeline with depletion markers.

    Parameters
    ----------
    snapshots:
        List of ``{tick, supply_level}`` dicts.
    side:
        Side name for title.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))

    if not snapshots:
        ax.text(0.5, 0.5, "No supply data", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    ticks = [s.get("tick", 0) for s in snapshots]
    levels = [s.get("supply_level", 1.0) for s in snapshots]

    ax.plot(ticks, levels, linewidth=2, color="#44AA77")
    ax.fill_between(ticks, levels, alpha=0.2, color="#44AA77")
    ax.axhline(y=_SUPPLY_CRITICAL_THRESHOLD, color="red", linestyle="--", alpha=0.5, label="Critical threshold")

    # Mark depletion points
    for i, level in enumerate(levels):
        if level < _SUPPLY_CRITICAL_THRESHOLD:
            ax.axvline(x=ticks[i], color="red", alpha=0.1)

    ax.set_xlabel("Tick")
    ax.set_ylabel("Supply Level")
    ax.set_title(f"Supply Flow — {side}")
    ax.set_ylim(-0.05, 1.05)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def engagement_timeline(
    events: list[dict[str, Any]],
) -> Any:
    """Scatter plot of engagements (x=tick, y=range, color=result).

    Parameters
    ----------
    events:
        List of engagement event dicts with ``tick``, ``range_m``, ``result``.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    if not events:
        ax.text(0.5, 0.5, "No engagements", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    result_colors = {"hit": "#CC0000", "miss": "#4477AA", "aborted": "#999999"}

    for result_type, color in result_colors.items():
        filtered = [e for e in events if e.get("result") == result_type]
        if filtered:
            ticks = [e.get("tick", 0) for e in filtered]
            ranges = [e.get("range_m", 0) for e in filtered]
            ax.scatter(ticks, ranges, c=color, label=result_type, alpha=0.7, s=30)

    ax.set_xlabel("Tick")
    ax.set_ylabel("Range (m)")
    ax.set_title("Engagement Timeline")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def morale_progression(
    events: list[dict[str, Any]],
) -> Any:
    """Step plot of morale state changes over time.

    Parameters
    ----------
    events:
        List of morale event dicts with ``tick``, ``unit_id``, ``new_state``.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    if not events:
        ax.text(0.5, 0.5, "No morale data", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    # Group by unit
    unit_data: dict[str, list[tuple[int, int]]] = {}
    for ev in events:
        uid = ev.get("unit_id", "?")
        unit_data.setdefault(uid, []).append((ev.get("tick", 0), ev.get("new_state", 0)))

    for uid, data in sorted(unit_data.items()):
        data.sort(key=lambda x: x[0])
        ticks = [d[0] for d in data]
        states = [d[1] for d in data]
        ax.step(ticks, states, where="post", label=uid, alpha=0.8)

    ax.set_xlabel("Tick")
    ax.set_ylabel("Morale State")
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_yticklabels(["STEADY", "SHAKEN", "BROKEN", "ROUTED", "SURRENDERED"])
    ax.set_title("Morale Progression")
    if len(unit_data) <= 10:
        ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.close(fig)
    return fig


def mc_distribution_grid(
    mc_metrics: dict[str, list[float]],
    metric_names: list[str] | None = None,
    historical: dict[str, float] | None = None,
) -> Any:
    """Histogram grid of Monte Carlo metric distributions.

    Parameters
    ----------
    mc_metrics:
        ``{metric_name: [values]}``.
    metric_names:
        Subset of metrics to plot. If None, plots all.
    historical:
        Optional ``{metric_name: reference_value}`` for vertical lines.

    Returns ``matplotlib.figure.Figure``.
    """
    import matplotlib.pyplot as plt

    names = metric_names or sorted(mc_metrics.keys())
    names = [n for n in names if n in mc_metrics]

    if not names:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No metrics to plot", transform=ax.transAxes, ha="center")
        plt.close(fig)
        return fig

    n = len(names)
    cols = min(3, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4 * rows))
    if n == 1:
        axes = np.array([axes])
    axes_flat = np.array(axes).flatten()

    for i, name in enumerate(names):
        ax = axes_flat[i]
        values = mc_metrics[name]
        ax.hist(values, bins=min(20, max(5, len(values) // 3)), alpha=0.7, color="#4477AA")
        ax.set_title(name, fontsize=10)
        ax.set_ylabel("Count")

        if historical and name in historical:
            ax.axvline(x=historical[name], color="red", linestyle="--", linewidth=2, label="Historical")
            ax.legend(fontsize=8)

    # Hide unused axes
    for j in range(n, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.suptitle("Monte Carlo Distributions", fontsize=12)
    fig.tight_layout()
    plt.close(fig)
    return fig
