"""Phase 2 visualization — unit positions, movement paths, formations, org hierarchy.

Usage:
    python scripts/visualize/entity_viz.py

Outputs PNG files to scripts/visualize/output/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stochastic_warfare.core.types import Domain, Position, Side
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.entities.organization.echelons import EchelonLevel
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.movement.engine import MovementConfig, MovementEngine
from stochastic_warfare.movement.formation import FormationManager, FormationType


def ensure_output_dir() -> Path:
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)
    return out


def viz_unit_positions() -> None:
    """Plot units from loaded YAML definitions on a 2D plane."""
    import matplotlib.pyplot as plt

    data_dir = Path(__file__).resolve().parents[2] / "data" / "units"
    loader = UnitLoader(data_dir)
    loader.load_all()
    rng = np.random.Generator(np.random.PCG64(42))

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    ax.set_title("Phase 2 — Unit Positions by Domain")

    domain_colors = {
        Domain.GROUND: "green",
        Domain.AERIAL: "blue",
        Domain.NAVAL: "navy",
        Domain.SUBMARINE: "purple",
        Domain.AMPHIBIOUS: "teal",
    }

    for i, unit_type in enumerate(loader.available_types()):
        pos = Position(rng.uniform(0, 5000), rng.uniform(0, 5000))
        unit = loader.create_unit(unit_type, f"viz-{unit_type}", pos, Side.BLUE, rng)
        color = domain_colors.get(unit.domain, "gray")
        ax.scatter(pos.easting, pos.northing, c=color, s=80, zorder=5)
        ax.annotate(unit_type, (pos.easting + 50, pos.northing + 50), fontsize=7)

    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    # Legend
    for domain, color in domain_colors.items():
        ax.scatter([], [], c=color, s=60, label=domain.name)
    ax.legend(loc="upper right")

    out = ensure_output_dir()
    fig.savefig(out / "unit_positions.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out / 'unit_positions.png'}")


def viz_movement_path() -> None:
    """Plot a unit moving across open terrain."""
    import matplotlib.pyplot as plt

    config = MovementConfig(noise_std=0.01)
    rng = np.random.Generator(np.random.PCG64(42))
    engine = MovementEngine(rng=rng, config=config)

    unit = Unit(entity_id="mover", position=Position(0.0, 0.0), max_speed=10.0)
    target = Position(2000.0, 1000.0)

    path = [unit.position]
    for _ in range(200):
        result = engine.move_unit(unit, target, 1.0)
        unit.position = result.new_position
        path.append(unit.position)
        if result.distance_moved < 0.01:
            break

    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    ax.set_title("Phase 2 — Unit Movement Path (Stochastic)")
    xs = [p.easting for p in path]
    ys = [p.northing for p in path]
    ax.plot(xs, ys, "b-", alpha=0.6, linewidth=1)
    ax.scatter(xs[0], ys[0], c="green", s=100, zorder=5, label="Start")
    ax.scatter(xs[-1], ys[-1], c="red", s=100, zorder=5, label="End")
    ax.scatter(target.easting, target.northing, c="orange", s=100,
               marker="x", zorder=5, label="Target")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.legend()

    out = ensure_output_dir()
    fig.savefig(out / "movement_path.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out / 'movement_path.png'}")


def viz_formations() -> None:
    """Plot all formation types."""
    import matplotlib.pyplot as plt

    formations = list(FormationType)
    fig, axes = plt.subplots(2, 5, figsize=(18, 8))
    fig.suptitle("Phase 2 — Tactical Formations", fontsize=14)

    for ax, ft in zip(axes.flat, formations):
        positions = FormationManager.compute_positions(
            Position(0.0, 0.0), 0.0, 6, ft, 50.0,
        )
        xs = [p.easting for p in positions]
        ys = [p.northing for p in positions]
        ax.scatter(xs, ys, c="blue", s=60)
        ax.scatter(xs[0], ys[0], c="red", s=100, zorder=5)
        ax.set_title(ft.name, fontsize=9)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-200, 200)
        ax.set_ylim(-350, 50)

    fig.tight_layout()
    out = ensure_output_dir()
    fig.savefig(out / "formations.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out / 'formations.png'}")


def viz_org_hierarchy() -> None:
    """Plot a simple org hierarchy as a text tree."""
    import matplotlib.pyplot as plt

    tree = HierarchyTree()
    tree.add_unit("BN", EchelonLevel.BATTALION)
    for i in range(3):
        co = f"CO-{chr(65+i)}"
        tree.add_unit(co, EchelonLevel.COMPANY, parent_id="BN")
        for j in range(3):
            plt_id = f"PLT-{chr(65+i)}{j+1}"
            tree.add_unit(plt_id, EchelonLevel.PLATOON, parent_id=co)

    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    ax.set_title("Phase 2 — Organization Hierarchy")

    # Simple layout: root at top, children spread below
    level_y = {EchelonLevel.BATTALION: 3.0, EchelonLevel.COMPANY: 2.0,
               EchelonLevel.PLATOON: 1.0}
    x_positions: dict[str, float] = {}

    # Assign x positions
    x = 0.0
    for uid in tree.all_unit_ids():
        node = tree.get_node(uid)
        if node.echelon == EchelonLevel.PLATOON:
            x_positions[uid] = x
            x += 1.0

    for uid in tree.all_unit_ids():
        node = tree.get_node(uid)
        if node.echelon == EchelonLevel.COMPANY:
            children = tree.get_children(uid)
            x_positions[uid] = sum(x_positions[c] for c in children) / len(children)

    x_positions["BN"] = sum(
        x_positions[c] for c in tree.get_children("BN")
    ) / 3

    for uid in tree.all_unit_ids():
        node = tree.get_node(uid)
        px = x_positions[uid]
        py = level_y[node.echelon]
        ax.scatter(px, py, c="steelblue", s=200, zorder=5)
        ax.annotate(uid, (px, py + 0.15), ha="center", fontsize=7)

        if node.parent_id and node.parent_id in x_positions:
            ppx = x_positions[node.parent_id]
            ppy = level_y[tree.get_node(node.parent_id).echelon]
            ax.plot([px, ppx], [py, ppy], "k-", alpha=0.5)

    ax.set_ylim(0.5, 3.8)
    ax.set_xlim(-1, x)
    ax.axis("off")

    out = ensure_output_dir()
    fig.savefig(out / "org_hierarchy.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out / 'org_hierarchy.png'}")


if __name__ == "__main__":
    viz_unit_positions()
    viz_movement_path()
    viz_formations()
    viz_org_hierarchy()
    print("All Phase 2 visualizations complete.")
