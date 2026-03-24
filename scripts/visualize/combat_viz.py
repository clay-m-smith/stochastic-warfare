"""Phase 4 combat analysis visualization — hit probability, penetration, suppression, morale.

Generates four diagnostic plots that exercise the combat and morale engines:

1. Engagement range vs P(hit) curves for different weapon types
2. Penetration success probability vs armor thickness (KE and HEAT)
3. Suppression decay over time from PINNED to NONE
4. Morale Markov transition matrix heatmaps (good vs dire conditions)

Usage:
    uv run python scripts/visualize/combat_viz.py
    uv run python scripts/visualize/combat_viz.py --show
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.combat.suppression import (
    SuppressionEngine,
    SuppressionLevel,
    UnitSuppressionState,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.morale.state import MoraleState, MoraleStateMachine

logger = get_logger(__name__)

OUT_DIR = Path(__file__).resolve().parent / "output"

# ---------------------------------------------------------------------------
# Synthetic weapon / ammo definitions for visualization
# ---------------------------------------------------------------------------


def _make_tank_cannon() -> tuple[WeaponDefinition, AmmoDefinition]:
    """120 mm smoothbore tank cannon firing APFSDS."""
    weapon = WeaponDefinition(
        weapon_id="m256_120mm",
        display_name="M256 120mm Smoothbore",
        category="CANNON",
        caliber_mm=120.0,
        muzzle_velocity_mps=1750.0,
        max_range_m=4000.0,
        rate_of_fire_rpm=6.0,
        base_accuracy_mrad=0.2,
    )
    ammo = AmmoDefinition(
        ammo_id="m829a3_apfsds",
        display_name="M829A3 APFSDS",
        ammo_type="AP",
        mass_kg=8.0,
        diameter_mm=120.0,
        drag_coefficient=0.15,
        penetration_mm_rha=700.0,
        penetration_reference_range_m=2000.0,
    )
    return weapon, ammo


def _make_machine_gun() -> tuple[WeaponDefinition, AmmoDefinition]:
    """7.62 mm medium machine gun."""
    weapon = WeaponDefinition(
        weapon_id="m240b",
        display_name="M240B 7.62mm MG",
        category="MACHINE_GUN",
        caliber_mm=7.62,
        muzzle_velocity_mps=853.0,
        max_range_m=1800.0,
        rate_of_fire_rpm=650.0,
        base_accuracy_mrad=1.5,
    )
    ammo = AmmoDefinition(
        ammo_id="762_nato_ball",
        display_name="7.62x51mm NATO Ball",
        ammo_type="HE",
        mass_kg=0.0095,
        diameter_mm=7.62,
        drag_coefficient=0.35,
        penetration_mm_rha=0.0,
    )
    return weapon, ammo


def _make_guided_missile() -> tuple[WeaponDefinition, AmmoDefinition]:
    """TOW-type anti-tank guided missile."""
    weapon = WeaponDefinition(
        weapon_id="tow_launcher",
        display_name="TOW Missile Launcher",
        category="MISSILE_LAUNCHER",
        caliber_mm=152.0,
        muzzle_velocity_mps=0.0,
        max_range_m=3750.0,
        rate_of_fire_rpm=2.0,
        base_accuracy_mrad=0.1,
    )
    ammo = AmmoDefinition(
        ammo_id="tow2b_missile",
        display_name="TOW-2B ATGM",
        ammo_type="MISSILE",
        mass_kg=21.5,
        diameter_mm=152.0,
        drag_coefficient=0.3,
        penetration_mm_rha=900.0,
        penetration_reference_range_m=0.0,
        guidance="WIRE",
        seeker_range_m=3750.0,
        pk_at_reference=0.90,
        countermeasure_susceptibility=0.3,
        max_speed_mps=300.0,
        flight_time_s=20.0,
    )
    return weapon, ammo


def _make_heat_round() -> AmmoDefinition:
    """HEAT round for penetration comparison against APFSDS."""
    return AmmoDefinition(
        ammo_id="m830a1_heat",
        display_name="M830A1 HEAT-MP-T",
        ammo_type="HEAT",
        mass_kg=11.3,
        diameter_mm=120.0,
        drag_coefficient=0.3,
        penetration_mm_rha=600.0,
        penetration_reference_range_m=0.0,
    )


# ---------------------------------------------------------------------------
# Plot 1: Engagement range vs P(hit) curves
# ---------------------------------------------------------------------------


def plot_phit_vs_range(show: bool) -> None:
    """Plot hit probability degradation with range for three weapon types."""
    logger.info("Generating P(hit) vs range plot")
    rng = np.random.Generator(np.random.PCG64(42))
    ballistics = BallisticsEngine(rng=rng)

    tank_wpn, tank_ammo = _make_tank_cannon()
    mg_wpn, mg_ammo = _make_machine_gun()
    missile_wpn, missile_ammo = _make_guided_missile()

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_title("Engagement Range vs P(hit) by Weapon Type", fontsize=14)

    # Tank cannon (direct fire, unguided)
    hit_engine = HitProbabilityEngine(ballistics, rng)
    ranges_tank = np.linspace(200, 4000, 200)
    phits_tank = [
        hit_engine.compute_phit(
            tank_wpn, tank_ammo, r, target_size_m2=8.0, crew_skill=0.7,
        ).p_hit
        for r in ranges_tank
    ]
    ax.plot(ranges_tank, phits_tank, "b-", linewidth=2, label="120mm Tank Cannon (APFSDS)")

    # Machine gun (unguided, large dispersion)
    ranges_mg = np.linspace(50, 1800, 200)
    phits_mg = [
        hit_engine.compute_phit(
            mg_wpn, mg_ammo, r, target_size_m2=1.5, crew_skill=0.5,
        ).p_hit
        for r in ranges_mg
    ]
    ax.plot(ranges_mg, phits_mg, "g-", linewidth=2, label="7.62mm Machine Gun")

    # Guided missile (Pk model)
    ranges_missile = np.linspace(100, 3750, 200)
    pks_missile = [
        hit_engine.compute_guided_pk(missile_ammo, r, target_signature=0.8)
        for r in ranges_missile
    ]
    ax.plot(ranges_missile, pks_missile, "r--", linewidth=2, label="TOW-2B ATGM (guided Pk)")

    ax.set_xlabel("Range (m)")
    ax.set_ylabel("P(hit) / Pk")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "phit_vs_range.png", dpi=150, bbox_inches="tight")
    logger.info("Saved: %s", OUT_DIR / "phit_vs_range.png")
    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 2: Penetration success probability vs armor thickness
# ---------------------------------------------------------------------------


def plot_penetration_vs_armor(show: bool) -> None:
    """Plot penetration probability for KE (APFSDS) and HEAT vs armor thickness."""
    logger.info("Generating penetration vs armor plot")
    rng = np.random.Generator(np.random.PCG64(42))
    event_bus = EventBus()
    damage_engine = DamageEngine(event_bus, rng)

    _, apfsds = _make_tank_cannon()
    heat = _make_heat_round()

    armor_thicknesses = np.linspace(50, 1200, 200)

    # For each thickness, compute deterministic penetration result.
    # Penetration is binary (pen > effective armor), so we compute the
    # margin at two representative ranges for KE (range-dependent) and
    # the constant-range HEAT result.
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Penetration vs Armor Thickness", fontsize=14)

    # Panel 1: KE penetration margin at different ranges
    ax = axes[0]
    ax.set_title("APFSDS (M829A3) — Penetration Margin vs Armor")
    for range_m, color, style in [
        (500, "darkblue", "-"),
        (1000, "blue", "-"),
        (2000, "steelblue", "--"),
        (3000, "lightblue", "--"),
    ]:
        margins = []
        for armor_mm in armor_thicknesses:
            result = damage_engine.compute_penetration(
                apfsds, armor_mm, impact_angle_deg=0.0, range_m=range_m,
            )
            margins.append(result.margin_mm)
        ax.plot(
            armor_thicknesses, margins, color=color, linestyle=style,
            linewidth=2, label=f"Range {range_m}m",
        )

    ax.axhline(y=0, color="red", linestyle=":", linewidth=1, alpha=0.7, label="Penetration threshold")
    ax.set_xlabel("Armor Thickness (mm RHA)")
    ax.set_ylabel("Penetration Margin (mm)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Panel 2: HEAT penetration margin (range-independent)
    ax = axes[1]
    ax.set_title("HEAT (M830A1) — Penetration Margin vs Armor")
    margins_heat = []
    for armor_mm in armor_thicknesses:
        result = damage_engine.compute_penetration(
            heat, armor_mm, impact_angle_deg=0.0, range_m=0.0,
        )
        margins_heat.append(result.margin_mm)
    ax.plot(armor_thicknesses, margins_heat, "r-", linewidth=2, label="HEAT (any range)")

    # Also show the effect of obliquity
    for angle, color, style in [(30, "orange", "--"), (60, "gold", ":")]:
        margins_angled = []
        for armor_mm in armor_thicknesses:
            result = damage_engine.compute_penetration(
                heat, armor_mm, impact_angle_deg=angle, range_m=0.0,
            )
            margins_angled.append(result.margin_mm)
        ax.plot(
            armor_thicknesses, margins_angled, color=color, linestyle=style,
            linewidth=2, label=f"HEAT @ {angle} deg obliquity",
        )

    ax.axhline(y=0, color="red", linestyle=":", linewidth=1, alpha=0.7, label="Penetration threshold")
    ax.set_xlabel("Armor Thickness (mm RHA)")
    ax.set_ylabel("Penetration Margin (mm)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "penetration_vs_armor.png", dpi=150, bbox_inches="tight")
    logger.info("Saved: %s", OUT_DIR / "penetration_vs_armor.png")
    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 3: Suppression decay over time
# ---------------------------------------------------------------------------


def plot_suppression_decay(show: bool) -> None:
    """Show how suppression decays from PINNED back to NONE over time."""
    logger.info("Generating suppression decay plot")
    rng = np.random.Generator(np.random.PCG64(42))
    event_bus = EventBus()
    engine = SuppressionEngine(event_bus, rng)

    # Start at PINNED (value = 1.0)
    state = UnitSuppressionState(value=1.0)
    dt = 0.5  # half-second timestep

    times: list[float] = [0.0]
    values: list[float] = [state.value]
    levels: list[SuppressionLevel] = [engine._level_from_value(state.value)]

    t = 0.0
    while t < 30.0:
        t += dt
        engine.update_suppression(state, dt)
        times.append(t)
        values.append(state.value)
        levels.append(engine._level_from_value(state.value))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle("Suppression Decay Over Time (from PINNED)", fontsize=14)

    # Panel 1: continuous value
    ax1.plot(times, values, "b-", linewidth=2)
    ax1.set_ylabel("Suppression Value")
    ax1.set_ylim(-0.05, 1.05)
    ax1.grid(True, alpha=0.3)

    # Shade threshold regions
    cfg = engine._config
    thresholds = [
        (0.0, cfg.light_threshold, "NONE", "#e8f5e9"),
        (cfg.light_threshold, cfg.moderate_threshold, "LIGHT", "#fff9c4"),
        (cfg.moderate_threshold, cfg.heavy_threshold, "MODERATE", "#ffe0b2"),
        (cfg.heavy_threshold, cfg.pinned_threshold, "HEAVY", "#ffccbc"),
        (cfg.pinned_threshold, 1.0, "PINNED", "#ffcdd2"),
    ]
    for low, high, label, color in thresholds:
        ax1.axhspan(low, high, color=color, alpha=0.3)
        ax1.text(
            0.5, (low + high) / 2, label,
            fontsize=8, color="gray", ha="left", va="center",
        )

    # Panel 2: discrete level as step plot
    level_ints = [int(lv) for lv in levels]
    ax2.step(times, level_ints, "r-", linewidth=2, where="post")
    ax2.set_yticks([0, 1, 2, 3, 4])
    ax2.set_yticklabels([lv.name for lv in SuppressionLevel])
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Suppression Level")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "suppression_decay.png", dpi=150, bbox_inches="tight")
    logger.info("Saved: %s", OUT_DIR / "suppression_decay.png")
    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Plot 4: Morale state transition matrix heatmaps
# ---------------------------------------------------------------------------


def plot_morale_transitions(show: bool) -> None:
    """Visualize Markov transition matrices under good and dire conditions."""
    logger.info("Generating morale transition matrix plot")
    rng = np.random.Generator(np.random.PCG64(42))
    event_bus = EventBus()
    machine = MoraleStateMachine(event_bus, rng)

    state_names = [s.name for s in MoraleState]
    n_states = len(state_names)

    # "Good" conditions: low casualties, no suppression, leadership, high cohesion,
    # favorable force ratio
    matrix_good = machine.compute_transition_matrix(
        casualty_rate=0.0,
        suppression_level=0.0,
        leadership_present=True,
        cohesion=0.9,
        force_ratio=2.0,
    )

    # "Dire" conditions: heavy casualties, high suppression, no leadership,
    # low cohesion, outnumbered
    matrix_dire = machine.compute_transition_matrix(
        casualty_rate=0.4,
        suppression_level=0.8,
        leadership_present=False,
        cohesion=0.1,
        force_ratio=0.3,
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Morale Markov Transition Matrices", fontsize=14)

    # Good conditions
    im1 = ax1.imshow(matrix_good, cmap="YlGn", vmin=0.0, vmax=1.0, aspect="equal")
    ax1.set_title("Good Conditions\n(no casualties, leadership, high cohesion, 2:1 ratio)")
    ax1.set_xticks(range(n_states))
    ax1.set_xticklabels(state_names, rotation=45, ha="right", fontsize=9)
    ax1.set_yticks(range(n_states))
    ax1.set_yticklabels(state_names, fontsize=9)
    ax1.set_xlabel("To State")
    ax1.set_ylabel("From State")

    # Annotate cells
    for i in range(n_states):
        for j in range(n_states):
            val = matrix_good[i, j]
            text_color = "white" if val > 0.6 else "black"
            ax1.text(j, i, f"{val:.2f}", ha="center", va="center",
                     fontsize=8, color=text_color)

    # Dire conditions
    im2 = ax2.imshow(matrix_dire, cmap="YlOrRd", vmin=0.0, vmax=1.0, aspect="equal")
    ax2.set_title("Dire Conditions\n(40% casualties, heavy suppression, no leader, 0.3:1 ratio)")
    ax2.set_xticks(range(n_states))
    ax2.set_xticklabels(state_names, rotation=45, ha="right", fontsize=9)
    ax2.set_yticks(range(n_states))
    ax2.set_yticklabels(state_names, fontsize=9)
    ax2.set_xlabel("To State")
    ax2.set_ylabel("From State")

    for i in range(n_states):
        for j in range(n_states):
            val = matrix_dire[i, j]
            text_color = "white" if val > 0.6 else "black"
            ax2.text(j, i, f"{val:.2f}", ha="center", va="center",
                     fontsize=8, color=text_color)

    fig.colorbar(im1, ax=ax1, shrink=0.8, label="Transition Probability")
    fig.colorbar(im2, ax=ax2, shrink=0.8, label="Transition Probability")

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "morale_transitions.png", dpi=150, bbox_inches="tight")
    logger.info("Saved: %s", OUT_DIR / "morale_transitions.png")
    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4 combat analysis visualizations",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Display plots interactively via plt.show()",
    )
    args = parser.parse_args()

    logger.info("Generating Phase 4 combat visualizations...")

    plot_phit_vs_range(args.show)
    plot_penetration_vs_armor(args.show)
    plot_suppression_decay(args.show)
    plot_morale_transitions(args.show)

    logger.info("All Phase 4 visualizations complete. Output in %s", OUT_DIR)


if __name__ == "__main__":
    main()
