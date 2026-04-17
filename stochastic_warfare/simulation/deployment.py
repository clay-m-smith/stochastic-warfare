"""Unit deployment strategies for scenario initialization (Phase 104).

Replaces the legacy line-abreast position assignment with configurable
deployment modes, selectable per-scenario via the ``deployment:`` block
in scenario YAML:

* ``legacy``      — single line along Y at ``start_x`` / ``start_y``
                    (preserves pre-Phase-104 behavior; default)
* ``bounding_box`` — uniform fill of a rectangular region
* ``clustered``   — group units by key (ground_type / unit_type / domain)
                    and place each cluster in a sub-region
* ``doctrinal``   — follow a formation template from ``data/formations/``
                    (brigade attack / defense / urban / etc.)
* ``manual``      — every unit has an explicit ``position:`` in YAML; no
                    auto-deployment (bounding_box fallback if missing)

Per-unit ``position: [x, y]`` overrides always win in any mode.

Rationale: scaling the 4 Block 11 golden scenarios revealed that the
legacy line-abreast placement overflows the map for forces >150 units
(Bint Jbeil's 150 blue units at 80m spacing stretches 12 km vs the 9 km
map), causing some blue units to land adjacent to red and the engine to
jump straight to TACTICAL resolution on tick 0. Phase 104 provides both
a structural fix (bounding-box fill bounded by the map) and progressively
higher-fidelity options (clustered, doctrinal) for scenarios that want
realistic initial deployments.
"""

from __future__ import annotations

import enum
import math
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, field_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DeploymentMode(str, enum.Enum):
    """How to place units at scenario start."""
    LEGACY = "legacy"
    BOUNDING_BOX = "bounding_box"
    CLUSTERED = "clustered"
    DOCTRINAL = "doctrinal"
    MANUAL = "manual"


class GroupKey(str, enum.Enum):
    """Which attribute to group units on for clustered / doctrinal modes."""
    GROUND_TYPE = "ground_type"
    UNIT_TYPE = "unit_type"
    DOMAIN = "domain"


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class DeploymentBox(BaseModel):
    """Rectangular deployment region in ENU meters.

    ``(x_min, y_min)`` is the SW corner, ``(x_max, y_max)`` the NE corner.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @field_validator("x_max")
    @classmethod
    def _x_order(cls, v: float, info: Any) -> float:
        x_min = info.data.get("x_min", 0.0)
        if v <= x_min:
            raise ValueError(f"x_max ({v}) must exceed x_min ({x_min})")
        return v

    @field_validator("y_max")
    @classmethod
    def _y_order(cls, v: float, info: Any) -> float:
        y_min = info.data.get("y_min", 0.0)
        if v <= y_min:
            raise ValueError(f"y_max ({v}) must exceed y_min ({y_min})")
        return v

    @property
    def width_m(self) -> float:
        return self.x_max - self.x_min

    @property
    def height_m(self) -> float:
        return self.y_max - self.y_min

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    def overlaps(self, other: "DeploymentBox") -> bool:
        return not (
            self.x_max <= other.x_min
            or self.x_min >= other.x_max
            or self.y_max <= other.y_min
            or self.y_min >= other.y_max
        )

    def min_separation_to(self, other: "DeploymentBox") -> float:
        """Shortest edge-to-edge distance to another box (0 if overlapping)."""
        if self.overlaps(other):
            return 0.0
        dx = max(0.0, other.x_min - self.x_max, self.x_min - other.x_max)
        dy = max(0.0, other.y_min - self.y_max, self.y_min - other.y_max)
        return math.hypot(dx, dy)


class DeploymentConfig(BaseModel):
    """Scenario-level deployment config (Phase 104)."""

    mode: DeploymentMode = DeploymentMode.LEGACY
    blue_box: DeploymentBox | None = None
    red_box: DeploymentBox | None = None
    blue_template: str | None = None
    red_template: str | None = None
    min_spacing_m: float = 40.0
    min_side_separation_m: float = 500.0  # warning threshold only
    group_key: GroupKey = GroupKey.GROUND_TYPE
    cluster_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Deployment dispatch
# ---------------------------------------------------------------------------


def deploy_units(
    units: list[Unit],
    side: str,
    config: DeploymentConfig,
    legacy_start_x: float | None = None,
    legacy_start_y: float | None = None,
    legacy_spacing_m: float = 50.0,
    template: Any | None = None,
    rng: np.random.Generator | None = None,
) -> None:
    """Place `units` according to `config.mode`. Mutates `unit.position`.

    Units with ``_manually_positioned`` flag set are skipped (they were
    placed via per-unit ``position:`` YAML override).

    Parameters
    ----------
    units:
        List of Unit instances to deploy (all belonging to `side`).
    side:
        "blue", "red", etc. Used to pick the per-side box / template.
    config:
        Deployment configuration from scenario YAML.
    legacy_start_x, legacy_start_y, legacy_spacing_m:
        Pre-Phase-104 deployment parameters from ``calibration_overrides``.
        Used when mode is LEGACY or when the target mode lacks a box.
    template:
        Loaded FormationTemplate for doctrinal mode (Phase 104c).
    rng:
        Deterministic PRNG for any jitter / randomized placement.
    """
    auto = [u for u in units if not getattr(u, "_manually_positioned", False)]
    if not auto:
        return

    box = config.blue_box if side == "blue" else config.red_box

    mode = config.mode
    if mode == DeploymentMode.LEGACY:
        _deploy_legacy(auto, legacy_start_x, legacy_start_y, legacy_spacing_m)
        return

    if mode == DeploymentMode.MANUAL:
        logger.warning(
            "deployment mode=manual for side=%s but %d units lack explicit position",
            side, len(auto),
        )
        if box is not None:
            _deploy_bounding_box(auto, box, config.min_spacing_m)
        else:
            _deploy_legacy(auto, legacy_start_x, legacy_start_y, legacy_spacing_m)
        return

    if mode == DeploymentMode.BOUNDING_BOX:
        if box is None:
            logger.warning(
                "bounding_box mode for side=%s but %s_box is None — falling back to legacy",
                side, side,
            )
            _deploy_legacy(auto, legacy_start_x, legacy_start_y, legacy_spacing_m)
            return
        _deploy_bounding_box(auto, box, config.min_spacing_m)
        return

    if mode == DeploymentMode.CLUSTERED:
        if box is None:
            logger.warning(
                "clustered mode for side=%s but %s_box is None — falling back to legacy",
                side, side,
            )
            _deploy_legacy(auto, legacy_start_x, legacy_start_y, legacy_spacing_m)
            return
        _deploy_clustered(
            auto, box, config.group_key, config.cluster_overrides,
            config.min_spacing_m,
        )
        return

    if mode == DeploymentMode.DOCTRINAL:
        if box is None or template is None:
            logger.warning(
                "doctrinal mode for side=%s missing box or template — falling back to bounding_box/legacy",
                side,
            )
            if box is not None:
                _deploy_bounding_box(auto, box, config.min_spacing_m)
            else:
                _deploy_legacy(auto, legacy_start_x, legacy_start_y, legacy_spacing_m)
            return
        # Phase 104b: infer forward direction from opposing box position.
        # Templates author offset_y_frac with "1 = forward / toward enemy".
        # If opposing box is at lower y than this side's box, the scenario
        # is attacking toward -Y and we flip offset_y_frac.
        opposing_box = config.red_box if side == "blue" else config.blue_box
        flip_y = False
        if opposing_box is not None:
            if opposing_box.center_y < box.center_y:
                flip_y = True
        _deploy_doctrinal(
            auto, box, template, config.group_key, config.min_spacing_m,
            flip_y=flip_y,
        )
        return


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _deploy_legacy(
    units: list[Unit],
    start_x: float | None,
    start_y: float | None,
    spacing_m: float,
) -> None:
    """Pre-Phase-104 line-abreast placement. Preserved for backward compat."""
    if start_x is None or start_y is None:
        logger.warning(
            "legacy deployment missing start coords — placing all at (0, 0)",
        )
        start_x = start_x or 0.0
        start_y = start_y or 0.0
    n = len(units)
    for i, u in enumerate(units):
        offset_y = (i - n / 2.0) * spacing_m
        object.__setattr__(u, "position", Position(start_x, start_y + offset_y, 0.0))


def _deploy_bounding_box(
    units: list[Unit],
    box: DeploymentBox,
    min_spacing_m: float,
) -> None:
    """Uniform fill of the box with computed near-square spacing."""
    n = len(units)
    if n == 0:
        return
    aspect = max(box.width_m, 1.0) / max(box.height_m, 1.0)
    cols = max(1, int(math.ceil(math.sqrt(n * aspect))))
    rows = max(1, int(math.ceil(n / cols)))
    spacing_x = box.width_m / cols
    spacing_y = box.height_m / rows
    actual = min(spacing_x, spacing_y)
    if actual < min_spacing_m:
        logger.warning(
            "bounding_box %.0fx%.0fm too small for %d units at min_spacing=%.0fm "
            "(actual spacing %.0fm)",
            box.width_m, box.height_m, n, min_spacing_m, actual,
        )
    for i, u in enumerate(units):
        col, row = i % cols, i // cols
        x = box.x_min + (col + 0.5) * spacing_x
        y = box.y_min + (row + 0.5) * spacing_y
        object.__setattr__(u, "position", Position(x, y, 0.0))


def _deploy_clustered(
    units: list[Unit],
    box: DeploymentBox,
    group_key: GroupKey,
    cluster_overrides: dict[str, dict[str, Any]],
    min_spacing_m: float,
) -> None:
    """Group units by key; place each group in a vertical strip of the box.

    Override per-group via ``cluster_overrides[<group>] = {anchor_frac,
    radius_m}`` to use a circular cluster around an anchor instead of a
    strip.
    """
    groups: dict[str, list[Unit]] = {}
    for u in units:
        key = _group_key_of(u, group_key)
        groups.setdefault(key, []).append(u)

    sorted_keys = sorted(groups.keys())
    n_groups = len(sorted_keys)
    if n_groups == 0:
        return
    strip_w = box.width_m / n_groups

    for i, gkey in enumerate(sorted_keys):
        sub = DeploymentBox(
            x_min=box.x_min + i * strip_w,
            y_min=box.y_min,
            x_max=box.x_min + (i + 1) * strip_w,
            y_max=box.y_max,
        )
        override = cluster_overrides.get(gkey, {})
        anchor = override.get("anchor_frac")
        radius = override.get("radius_m")
        members = groups[gkey]
        if anchor is not None and radius is not None:
            _deploy_circular(members, sub, anchor, float(radius), min_spacing_m)
        else:
            _deploy_bounding_box(members, sub, min_spacing_m)


def _deploy_circular(
    units: list[Unit],
    sub_box: DeploymentBox,
    anchor_frac: list[float] | tuple[float, float],
    radius_m: float,
    min_spacing_m: float,
) -> None:
    """Place units around an anchor in concentric rings."""
    cx = sub_box.x_min + float(anchor_frac[0]) * sub_box.width_m
    cy = sub_box.y_min + float(anchor_frac[1]) * sub_box.height_m
    n = len(units)
    if n == 0:
        return
    # Simple concentric-ring packing
    placed = 0
    ring = 0
    while placed < n:
        if ring == 0:
            object.__setattr__(units[placed], "position", Position(cx, cy, 0.0))
            placed += 1
        else:
            ring_r = ring * max(min_spacing_m, radius_m / max(1, int(math.sqrt(n))))
            circumference = 2.0 * math.pi * ring_r
            ring_cap = max(6, int(circumference / min_spacing_m))
            for j in range(ring_cap):
                if placed >= n:
                    break
                theta = 2.0 * math.pi * j / ring_cap
                x = cx + ring_r * math.cos(theta)
                y = cy + ring_r * math.sin(theta)
                # Clamp to sub_box
                x = min(max(x, sub_box.x_min), sub_box.x_max)
                y = min(max(y, sub_box.y_min), sub_box.y_max)
                object.__setattr__(units[placed], "position", Position(x, y, 0.0))
                placed += 1
        ring += 1
        if ring > 100:  # safety
            logger.warning("_deploy_circular ring overflow at %d units", n)
            break


def _deploy_doctrinal(
    units: list[Unit],
    box: DeploymentBox,
    template: Any,
    group_key: GroupKey,
    min_spacing_m: float,
    flip_y: bool = False,
) -> None:
    """Follow a formation template — echelons with offset_y_frac + group_type
    allocations within the box's frontage/depth.

    Template schema (Phase 104c):

        template_id: str
        depth_m: float
        frontage_m: float
        echelons: list[Echelon]
          - name: str
            offset_y_frac: float  # 0..1, 1 = forward (towards enemy)
            offset_x_frac: float  # 0..1, 0.5 = center
            frontage_frac: float  # width of echelon's strip
            units:
              - group_type: str  # matches group_key value
                count_frac: float  # fraction of that group_type to place here

    The template is applied within ``box``, with ``offset_y_frac`` mapping
    to distance from ``y_min`` (= 0) to ``y_max`` (= 1). If template
    dimensions (``depth_m`` / ``frontage_m``) differ from box dims, the
    template is scaled to fit.
    """
    # Group units by the template's matching key
    groups: dict[str, list[Unit]] = {}
    for u in units:
        key = _group_key_of(u, group_key)
        groups.setdefault(key, []).append(u)

    # Make mutable copies so we can pop as we allocate
    remaining = {k: list(v) for k, v in groups.items()}

    echelons = getattr(template, "echelons", []) or []
    if not echelons:
        logger.warning("doctrinal template has no echelons — falling back to bounding_box")
        _deploy_bounding_box(units, box, min_spacing_m)
        return

    for ech in echelons:
        ech_name = ech.get("name", "unnamed") if isinstance(ech, dict) else getattr(ech, "name", "unnamed")
        off_y = float(ech.get("offset_y_frac", 0.5)) if isinstance(ech, dict) else float(getattr(ech, "offset_y_frac", 0.5))
        off_x = float(ech.get("offset_x_frac", 0.5)) if isinstance(ech, dict) else float(getattr(ech, "offset_x_frac", 0.5))
        front_f = float(ech.get("frontage_frac", 0.6)) if isinstance(ech, dict) else float(getattr(ech, "frontage_frac", 0.6))
        ech_units_spec = ech.get("units", []) if isinstance(ech, dict) else getattr(ech, "units", [])

        # Derive echelon bounding box
        # flip_y=True inverts offset_y_frac (attack toward -Y instead of +Y)
        eff_off_y = (1.0 - off_y) if flip_y else off_y
        ech_cx = box.x_min + off_x * box.width_m
        ech_cy = box.y_min + eff_off_y * box.height_m
        ech_half_w = (front_f * box.width_m) / 2.0
        # Phase 104b: scale echelon thickness with box size so large-map
        # scenarios (Khafji 50km) don't pack a full echelon into a 100m band.
        ech_half_h = max(50.0, 0.05 * box.height_m)
        sub_box = DeploymentBox(
            x_min=max(box.x_min, ech_cx - ech_half_w),
            y_min=max(box.y_min, ech_cy - ech_half_h),
            x_max=min(box.x_max, ech_cx + ech_half_w),
            y_max=min(box.y_max, ech_cy + ech_half_h),
        )

        # Gather units to place in this echelon
        ech_pool: list[Unit] = []
        for spec in ech_units_spec:
            gt = spec.get("group_type") if isinstance(spec, dict) else getattr(spec, "group_type", None)
            cf = float(spec.get("count_frac", 1.0)) if isinstance(spec, dict) else float(getattr(spec, "count_frac", 1.0))
            if gt is None or gt not in remaining:
                continue
            take_n = int(math.ceil(len(remaining[gt]) * cf))
            for _ in range(min(take_n, len(remaining[gt]))):
                ech_pool.append(remaining[gt].pop())

        if not ech_pool:
            continue

        _deploy_bounding_box(ech_pool, sub_box, min_spacing_m)
        logger.debug("echelon %s: placed %d units", ech_name, len(ech_pool))

    # Any leftover units (groups not allocated by template) — fill rest of box
    leftover = [u for units_ in remaining.values() for u in units_]
    if leftover:
        logger.debug(
            "doctrinal template left %d units unallocated — filling box",
            len(leftover),
        )
        _deploy_bounding_box(leftover, box, min_spacing_m)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_key_of(unit: Unit, key: GroupKey) -> str:
    """Extract the grouping key value from a unit."""
    if key == GroupKey.GROUND_TYPE:
        gt = getattr(unit, "ground_type", None)
        if gt is None:
            return "UNKNOWN"
        return gt.name if hasattr(gt, "name") else str(gt)
    if key == GroupKey.UNIT_TYPE:
        return getattr(unit, "unit_type", "UNKNOWN") or "UNKNOWN"
    if key == GroupKey.DOMAIN:
        d = getattr(unit, "domain", None)
        if d is None:
            return "UNKNOWN"
        return d.name if hasattr(d, "name") else str(d)
    return "DEFAULT"


class FormationTemplate(BaseModel):
    """Doctrinal formation template (Phase 104c).

    Loaded from ``data/formations/*.yaml`` and consumed by ``_deploy_doctrinal``.
    ``offset_y_frac`` runs 0 (rear / y_min) to 1 (forward / y_max); offset_x_frac
    centered at 0.5. ``count_frac`` controls what fraction of available units of
    each ``group_type`` are placed in that echelon.
    """

    template_id: str
    description: str = ""
    depth_m: float = 2000.0
    frontage_m: float = 2000.0
    echelons: list[dict[str, Any]] = Field(default_factory=list)


class FormationTemplateLoader:
    """Load formation templates from ``data/formations/*.yaml``."""

    def __init__(self, data_dir: Any) -> None:
        from pathlib import Path
        self._dir = Path(data_dir)
        self._cache: dict[str, FormationTemplate] = {}

    def load_all(self) -> None:
        import yaml
        self._cache.clear()
        if not self._dir.exists():
            logger.warning("formation templates dir does not exist: %s", self._dir)
            return
        for f in self._dir.glob("*.yaml"):
            try:
                raw = yaml.safe_load(f.read_text(encoding="utf-8"))
                tpl = FormationTemplate.model_validate(raw)
                self._cache[tpl.template_id] = tpl
            except Exception:
                logger.warning("failed to load formation template %s", f, exc_info=True)

    def get(self, template_id: str) -> FormationTemplate | None:
        return self._cache.get(template_id)

    def available(self) -> list[str]:
        return sorted(self._cache.keys())


def check_side_separation(
    blue_box: DeploymentBox | None,
    red_box: DeploymentBox | None,
    min_separation_m: float,
) -> bool:
    """Warn if deployment boxes are too close. Returns True if OK.

    Does NOT raise — Phase 104 design decision is "just warn for overlap".
    """
    if blue_box is None or red_box is None:
        return True
    if blue_box.overlaps(red_box):
        logger.warning(
            "deployment boxes overlap: blue=[%s] red=[%s] — forces will engage at tick 0",
            blue_box, red_box,
        )
        return False
    sep = blue_box.min_separation_to(red_box)
    if sep < min_separation_m:
        logger.warning(
            "deployment boxes closer than min_side_separation_m=%.0f (actual %.0f) — "
            "forces may engage at tick 0",
            min_separation_m, sep,
        )
        return False
    return True
