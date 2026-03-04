"""Animated battle replay from simulation snapshots.

Produces ``FuncAnimation`` objects showing unit positions, engagement
lines, and destroyed markers over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ReplayConfig(BaseModel):
    """Configuration for replay animation."""

    figsize: tuple[float, float] = (12, 8)
    fps: int = 10
    trail_length: int = 5
    side_colors: dict[str, str] = {"blue": "#4477AA", "red": "#CC6677"}
    output_format: str = "gif"  # "gif" or "mp4"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UnitFrame:
    """Position and status of one unit at one tick."""

    unit_id: str
    side: str
    x: float
    y: float
    active: bool


@dataclass
class EngagementFrame:
    """An engagement happening at a tick."""

    attacker_x: float
    attacker_y: float
    target_x: float
    target_y: float
    result: str  # "hit" | "miss"


@dataclass
class ReplayFrame:
    """All data for one tick of replay."""

    tick: int
    units: list[UnitFrame] = field(default_factory=list)
    engagements: list[EngagementFrame] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------


def extract_replay_frames(
    snapshots: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> list[ReplayFrame]:
    """Extract replay frames from simulation snapshots and events.

    Parameters
    ----------
    snapshots:
        List of state snapshot dicts. Each should have ``tick`` and
        ``units`` (list of ``{unit_id, side, position: {easting, northing}, active}``).
    events:
        Optional engagement events for engagement lines.

    Returns
    -------
    list[ReplayFrame]
        One frame per snapshot, in tick order.
    """
    # Index events by tick
    event_by_tick: dict[int, list[dict[str, Any]]] = {}
    if events:
        for ev in events:
            tick = ev.get("tick", 0)
            event_by_tick.setdefault(tick, []).append(ev)

    frames: list[ReplayFrame] = []
    for snap in sorted(snapshots, key=lambda s: s.get("tick", 0)):
        tick = snap.get("tick", 0)

        # Extract units
        unit_frames: list[UnitFrame] = []
        for u in snap.get("units", []):
            pos = u.get("position", {})
            unit_frames.append(
                UnitFrame(
                    unit_id=u.get("unit_id", ""),
                    side=u.get("side", ""),
                    x=pos.get("easting", 0.0),
                    y=pos.get("northing", 0.0),
                    active=u.get("active", True),
                )
            )

        # Extract engagements at this tick
        eng_frames: list[EngagementFrame] = []
        for ev in event_by_tick.get(tick, []):
            eng_frames.append(
                EngagementFrame(
                    attacker_x=ev.get("attacker_x", 0.0),
                    attacker_y=ev.get("attacker_y", 0.0),
                    target_x=ev.get("target_x", 0.0),
                    target_y=ev.get("target_y", 0.0),
                    result=ev.get("result", "unknown"),
                )
            )

        frames.append(ReplayFrame(tick=tick, units=unit_frames, engagements=eng_frames))

    return frames


# ---------------------------------------------------------------------------
# Animation creation
# ---------------------------------------------------------------------------


def create_replay(
    frames: list[ReplayFrame],
    terrain_extent: tuple[float, float, float, float] | None = None,
    config: ReplayConfig | None = None,
) -> Any:
    """Create a ``FuncAnimation`` from replay frames.

    Parameters
    ----------
    frames:
        Output from ``extract_replay_frames()``.
    terrain_extent:
        ``(x_min, x_max, y_min, y_max)`` for axis limits.
    config:
        Replay configuration.

    Returns ``matplotlib.animation.FuncAnimation``.
    """
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    cfg = config or ReplayConfig()
    fig, ax = plt.subplots(figsize=cfg.figsize)

    if terrain_extent:
        ax.set_xlim(terrain_extent[0], terrain_extent[1])
        ax.set_ylim(terrain_extent[2], terrain_extent[3])

    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    title = ax.set_title("Tick 0")

    # Collections for scatter
    scatter_objs: dict[str, Any] = {}
    destroyed_scatter: Any = None
    engagement_lines: list[Any] = []

    def init():
        nonlocal destroyed_scatter
        for side, color in cfg.side_colors.items():
            scatter_objs[side] = ax.scatter([], [], c=color, s=50, label=side, zorder=5)
        destroyed_scatter = ax.scatter([], [], c="black", marker="x", s=40, zorder=4, label="Destroyed")
        ax.legend(loc="upper right", fontsize=8)
        return list(scatter_objs.values()) + [destroyed_scatter]

    def update(frame_idx):
        nonlocal engagement_lines
        if frame_idx >= len(frames):
            return []

        frame = frames[frame_idx]
        title.set_text(f"Tick {frame.tick}")

        # Clear old engagement lines
        for line in engagement_lines:
            line.remove()
        engagement_lines = []

        # Update unit positions
        side_positions: dict[str, tuple[list[float], list[float]]] = {
            side: ([], []) for side in cfg.side_colors
        }
        destroyed_x: list[float] = []
        destroyed_y: list[float] = []

        for u in frame.units:
            if u.active:
                if u.side in side_positions:
                    side_positions[u.side][0].append(u.x)
                    side_positions[u.side][1].append(u.y)
            else:
                destroyed_x.append(u.x)
                destroyed_y.append(u.y)

        for side, scat in scatter_objs.items():
            xs, ys = side_positions.get(side, ([], []))
            scat.set_offsets(np.column_stack([xs, ys]) if xs else np.empty((0, 2)))

        destroyed_scatter.set_offsets(
            np.column_stack([destroyed_x, destroyed_y]) if destroyed_x else np.empty((0, 2))
        )

        # Draw engagement lines
        for eng in frame.engagements:
            color = "#CC0000" if eng.result == "hit" else "#999999"
            line, = ax.plot(
                [eng.attacker_x, eng.target_x],
                [eng.attacker_y, eng.target_y],
                color=color, alpha=0.6, linewidth=1,
            )
            engagement_lines.append(line)

        return list(scatter_objs.values()) + [destroyed_scatter] + engagement_lines

    anim = FuncAnimation(
        fig, update, init_func=init,
        frames=len(frames), interval=1000 // cfg.fps,
        blit=False,
    )

    plt.close(fig)
    return anim


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_replay(
    anim: Any,
    output_path: str | Path,
    config: ReplayConfig | None = None,
) -> bool:
    """Save animation to file.

    Parameters
    ----------
    anim:
        ``FuncAnimation`` from ``create_replay()``.
    output_path:
        Destination path (.gif or .mp4).
    config:
        Replay configuration for fps and format.

    Returns True if saved successfully, False if writer unavailable.
    """
    cfg = config or ReplayConfig()
    path = Path(output_path)

    try:
        if path.suffix == ".gif" or cfg.output_format == "gif":
            anim.save(str(path), writer="pillow", fps=cfg.fps)
        else:
            anim.save(str(path), writer="ffmpeg", fps=cfg.fps)
        return True
    except Exception as e:
        logger.warning("Failed to save replay: %s", e)
        return False
