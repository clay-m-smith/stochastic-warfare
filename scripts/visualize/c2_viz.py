"""Phase 5 C2 analysis visualization — propagation delay, reliability, command status.

Generates three diagnostic plots:

1. Order propagation delay vs echelon level (OPORD vs FRAGO vs WARNO)
2. Communication reliability vs range for different equipment types
3. Command status state machine (text diagram)

Usage:
    uv run python scripts/visualize/c2_viz.py
    uv run python scripts/visualize/c2_viz.py --show
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.command import CommandEngine
from stochastic_warfare.c2.communications import (
    CommEquipmentLoader,
    CommunicationsEngine,
)
from stochastic_warfare.c2.orders.propagation import (
    OrderPropagationEngine,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderPriority,
    OrderType,
)
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import TaskOrgManager

OUTPUT_DIR = Path(__file__).parent / "output"


def plot_propagation_delay(ax: plt.Axes) -> None:
    """Plot 1: Order propagation delay vs echelon level."""
    echelons = [
        (EchelonLevel.SQUAD, "Squad"),
        (EchelonLevel.PLATOON, "Platoon"),
        (EchelonLevel.COMPANY, "Company"),
        (EchelonLevel.BATTALION, "Battalion"),
        (EchelonLevel.BRIGADE, "Brigade"),
        (EchelonLevel.DIVISION, "Division"),
        (EchelonLevel.CORPS, "Corps"),
    ]

    # Build minimal engine for delay computation
    hierarchy = HierarchyTree()
    hierarchy.add_unit("top", EchelonLevel.THEATER)
    task_org = TaskOrgManager(hierarchy)
    bus = EventBus()
    rng_mgr = RNGManager(42)
    cmd = CommandEngine(hierarchy, task_org, {}, bus, rng_mgr.get_stream(ModuleId.C2))

    comms = CommunicationsEngine(bus, rng_mgr.get_stream(ModuleId.ENVIRONMENT))
    prop = OrderPropagationEngine(
        comms, cmd, bus, rng_mgr.get_stream(ModuleId.MOVEMENT),
    )

    order_types = [
        (OrderType.OPORD, "OPORD", "b"),
        (OrderType.FRAGO, "FRAGO", "r"),
        (OrderType.WARNO, "WARNO", "g"),
    ]

    for ot, label, color in order_types:
        delays_median = []
        delays_p10 = []
        delays_p90 = []
        for ech, _name in echelons:
            samples = []
            for _ in range(200):
                order = Order(
                    order_id="x", issuer_id="a", recipient_id="b",
                    timestamp=None, order_type=ot,  # type: ignore[arg-type]
                    echelon_level=int(ech), priority=OrderPriority.ROUTINE,
                    mission_type=int(MissionType.ATTACK),
                )
                d = prop.compute_delay(int(ech), 1.0, order)
                samples.append(d)
            delays_median.append(np.median(samples))
            delays_p10.append(np.percentile(samples, 10))
            delays_p90.append(np.percentile(samples, 90))

        x = range(len(echelons))
        ax.semilogy(x, delays_median, f"{color}-o", label=f"{label} (median)")
        ax.fill_between(x, delays_p10, delays_p90, alpha=0.15, color=color)

    ax.set_xticks(range(len(echelons)))
    ax.set_xticklabels([n for _, n in echelons], rotation=45, ha="right")
    ax.set_ylabel("Delay (seconds, log scale)")
    ax.set_title("Order Propagation Delay vs Echelon")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


def plot_comms_reliability(ax: plt.Axes) -> None:
    """Plot 2: Communication reliability vs range."""
    loader = CommEquipmentLoader()
    loader.load_all()

    equipment = ["sincgars_vhf", "harris_hf", "link16", "satcom_uhf", "field_wire"]
    colors = ["b", "r", "g", "purple", "brown"]

    for eid, color in zip(equipment, colors):
        defn = loader.get_definition(eid)
        ranges = np.linspace(0, defn.max_range_m, 100)
        reliabilities = []
        for r in ranges:
            # Linear degradation in last 20%
            threshold = defn.max_range_m * 0.8
            if r <= threshold:
                range_factor = 1.0
            elif r <= defn.max_range_m:
                range_factor = 1.0 - (r - threshold) / (defn.max_range_m - threshold)
            else:
                range_factor = 0.0
            reliabilities.append(defn.base_reliability * range_factor)

        ax.plot(
            ranges / 1000, reliabilities,
            color=color, label=f"{defn.display_name}",
        )

    ax.set_xlabel("Range (km)")
    ax.set_ylabel("Reliability")
    ax.set_title("Communication Reliability vs Range")
    ax.legend(fontsize=7, loc="lower left")
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)


def plot_command_status(ax: plt.Axes) -> None:
    """Plot 3: Command status state machine (text diagram)."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Command Authority State Machine", fontsize=12)

    # States
    states = {
        "FULLY_OPERATIONAL": (2, 8),
        "DEGRADED": (8, 8),
        "DISRUPTED": (5, 4),
        "DESTROYED": (5, 1),
    }
    for name, (x, y) in states.items():
        circle = plt.Circle((x, y), 0.8, fill=False, linewidth=2)
        ax.add_patch(circle)
        ax.text(x, y, name.replace("_", "\n"), ha="center", va="center", fontsize=6)

    # Transitions (arrows as annotations)
    transitions = [
        ("FULLY_OPERATIONAL", "DEGRADED", "comms\nloss"),
        ("DEGRADED", "DISRUPTED", "comms loss\nor KIA"),
        ("DISRUPTED", "DESTROYED", "HQ\ndestroyed"),
        ("DEGRADED", "FULLY_OPERATIONAL", "recovery"),
        ("DISRUPTED", "DEGRADED", "succession\ncomplete"),
    ]
    for start, end, label in transitions:
        sx, sy = states[start]
        ex, ey = states[end]
        ax.annotate(
            "", xy=(ex, ey), xytext=(sx, sy),
            arrowprops=dict(arrowstyle="->", lw=1.5),
        )
        mx, my = (sx + ex) / 2, (sy + ey) / 2 + 0.3
        ax.text(mx, my, label, ha="center", va="center", fontsize=5,
                bbox=dict(boxstyle="round,pad=0.2", fc="lightyellow", alpha=0.8))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 C2 visualizations")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    plot_propagation_delay(axes[0])
    plot_comms_reliability(axes[1])
    plot_command_status(axes[2])

    fig.suptitle("Phase 5: C2 Infrastructure Analysis", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    out_path = OUTPUT_DIR / "c2_analysis.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path}")

    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
