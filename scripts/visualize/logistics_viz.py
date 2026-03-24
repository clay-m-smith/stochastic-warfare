"""Logistics visualization — supply network, depot levels, consumption rates.

Run with: uv run python scripts/visualize/logistics_viz.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.logistics.consumption import (
    ActivityLevel,
    ConsumptionEngine,
)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def plot_consumption_by_activity() -> None:
    """Bar chart: consumption rates by activity level and supply class."""
    bus = EventBus()
    rng = RNGManager(42).get_stream(ModuleId.LOGISTICS)
    engine = ConsumptionEngine(event_bus=bus, rng=rng)

    activities = [ActivityLevel.IDLE, ActivityLevel.DEFENSE,
                  ActivityLevel.MARCH, ActivityLevel.COMBAT]
    labels = [a.name for a in activities]

    food, water, fuel, ammo, medical = [], [], [], [], []
    for activity in activities:
        r = engine.compute_consumption(
            personnel_count=100, equipment_count=10,
            base_fuel_rate_per_hour=50.0,
            activity=int(activity), dt_hours=1.0,
        )
        food.append(r.food_kg)
        water.append(r.water_liters)
        fuel.append(r.fuel_liters)
        ammo.append(r.ammo_units)
        medical.append(r.medical_units)

    x = np.arange(len(labels))
    width = 0.15

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - 2 * width, food, width, label="Food (kg)")
    ax.bar(x - width, water, width, label="Water (L)")
    ax.bar(x, fuel, width, label="Fuel (L)")
    ax.bar(x + width, ammo, width, label="Ammo (units)")
    ax.bar(x + 2 * width, [m * 100 for m in medical], width, label="Medical (x100)")

    ax.set_xlabel("Activity Level")
    ax.set_ylabel("Consumption per Hour (100 pers, 10 equip)")
    ax.set_title("Supply Consumption by Activity Level")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.savefig(OUTPUT_DIR / "consumption_by_activity.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_DIR / 'consumption_by_activity.png'}")


def plot_naval_fuel_curve() -> None:
    """Line plot: naval fuel consumption vs speed (cubic law)."""
    bus = EventBus()
    rng = RNGManager(42).get_stream(ModuleId.LOGISTICS)
    engine = ConsumptionEngine(event_bus=bus, rng=rng)

    max_speed = 15.0
    speeds = np.linspace(0, max_speed, 100)
    fuel_rates = [
        engine.fuel_consumption_naval(
            speed_mps=s, dt_hours=1.0,
            max_speed_mps=max_speed,
            fuel_capacity_liters=100000.0,
            design_endurance_hours=200.0,
        )
        for s in speeds
    ]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(speeds * 1.944, fuel_rates, linewidth=2)  # m/s to knots
    ax.set_xlabel("Speed (knots)")
    ax.set_ylabel("Fuel Consumption (L/h)")
    ax.set_title("Naval Fuel Consumption — Cubic Speed Law")
    ax.grid(alpha=0.3)

    fig.savefig(OUTPUT_DIR / "naval_fuel_curve.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_DIR / 'naval_fuel_curve.png'}")


def plot_supply_network() -> None:
    """Node-link diagram of a sample supply network."""
    bus = EventBus()
    rng = RNGManager(42).get_stream(ModuleId.LOGISTICS)

    positions = {
        "Theater Depot": (0, 0),
        "Corps Depot": (3, 2),
        "Div LSA": (6, 1),
        "Bde FSB": (9, 3),
        "Bn Supply": (12, 2),
        "Port": (0, 4),
        "Airfield": (6, 5),
    }

    edges = [
        ("Theater Depot", "Corps Depot", "ROAD", 10.0),
        ("Corps Depot", "Div LSA", "ROAD", 8.0),
        ("Div LSA", "Bde FSB", "ROAD", 5.0),
        ("Bde FSB", "Bn Supply", "ROAD", 3.0),
        ("Port", "Theater Depot", "SEA", 20.0),
        ("Airfield", "Bde FSB", "AIR", 15.0),
        ("Theater Depot", "Airfield", "ROAD", 6.0),
    ]

    fig, ax = plt.subplots(figsize=(12, 7))

    # Draw edges
    for src, dst, mode, cap in edges:
        x0, y0 = positions[src]
        x1, y1 = positions[dst]
        color = {"ROAD": "#555555", "SEA": "#2196F3", "AIR": "#FF9800"}[mode]
        style = {"ROAD": "-", "SEA": "--", "AIR": ":"}[mode]
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color=color,
                                    linestyle=style, linewidth=1.5))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx, my + 0.2, f"{cap:.0f} t/h", fontsize=7, ha="center",
                color=color)

    # Draw nodes
    node_colors = {
        "Theater Depot": "#4CAF50",
        "Corps Depot": "#8BC34A",
        "Div LSA": "#CDDC39",
        "Bde FSB": "#FFC107",
        "Bn Supply": "#FF5722",
        "Port": "#2196F3",
        "Airfield": "#FF9800",
    }
    for name, (x, y) in positions.items():
        color = node_colors[name]
        ax.scatter(x, y, s=200, c=color, zorder=5, edgecolors="black")
        ax.text(x, y - 0.4, name, ha="center", fontsize=8, fontweight="bold")

    ax.set_xlim(-1, 14)
    ax.set_ylim(-1.5, 6)
    ax.set_title("Supply Network Topology")
    ax.set_aspect("equal")
    ax.axis("off")

    fig.savefig(OUTPUT_DIR / "supply_network.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_DIR / 'supply_network.png'}")


if __name__ == "__main__":
    plot_consumption_by_activity()
    plot_naval_fuel_curve()
    plot_supply_network()
    print("All logistics visualizations generated.")
