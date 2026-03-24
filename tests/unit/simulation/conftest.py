"""Shared fixtures and factory functions for simulation unit tests.

Supplements the top-level ``tests/conftest.py``.  Factories here build
lightweight simulation domain objects without requiring full engine graphs.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# RNG helper (independent of fixtures — usable at module scope)
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    """Create a deterministic PRNG."""
    return np.random.Generator(np.random.PCG64(seed))


# ---------------------------------------------------------------------------
# Unit factory
# ---------------------------------------------------------------------------

def _make_unit(
    unit_id: str = "unit_1",
    side: str = "blue",
    position: Position | None = None,
    *,
    domain: str = "GROUND",
    status: str = "ACTIVE",
    personnel_count: int = 10,
    equipment_count: int = 2,
    support_type: str | None = None,
    ground_type: str | None = None,
    unit_type: str = "infantry",
    speed: float = 5.0,
) -> SimpleNamespace:
    """Lightweight mock unit for simulation tests."""
    ns = SimpleNamespace(
        entity_id=unit_id,
        side=side,
        position=position or Position(0.0, 0.0, 0.0),
        domain=domain,
        status=status,
        personnel=[f"p{i}" for i in range(personnel_count)],
        equipment=[
            SimpleNamespace(equipment_id=f"eq_{unit_id}_{i}", operational=True)
            for i in range(equipment_count)
        ],
        unit_type=unit_type,
        speed=speed,
    )
    if support_type is not None:
        ns.support_type = SimpleNamespace(name=support_type)
    if ground_type is not None:
        ns.ground_type = SimpleNamespace(name=ground_type)
    return ns


# ---------------------------------------------------------------------------
# Simulation context factory
# ---------------------------------------------------------------------------

def _make_ctx(
    units_by_side: dict[str, list] | None = None,
    *,
    morale_states: dict | None = None,
    stockpile_manager: object | None = None,
    sig_loader: object | None = None,
    calibration: object | None = None,
) -> SimpleNamespace:
    """Lightweight mock SimulationContext."""
    ubs = units_by_side or {}
    ctx = SimpleNamespace(
        units_by_side=ubs,
        morale_states=morale_states or {},
        stockpile_manager=stockpile_manager,
        sig_loader=sig_loader,
        calibration=calibration,
    )

    def active_units(side: str) -> list:
        return [u for u in ubs.get(side, []) if u.status == "ACTIVE"]

    def side_names() -> list[str]:
        return list(ubs.keys())

    ctx.active_units = active_units
    ctx.side_names = side_names
    return ctx


# ---------------------------------------------------------------------------
# Weapon factory
# ---------------------------------------------------------------------------

def _make_weapon_instance(
    weapon_id: str = "test_wpn",
    category: str = "CANNON",
    max_range_m: float = 3000.0,
    ammo_ids: list[str] | None = None,
) -> SimpleNamespace:
    """Lightweight mock weapon instance."""
    aids = ammo_ids or ["test_ap"]
    defn = SimpleNamespace(
        weapon_id=weapon_id,
        category=category,
        max_range_m=max_range_m,
    )
    ammo_state = SimpleNamespace()

    def can_fire(ammo_id: str) -> bool:
        return ammo_id in aids

    return SimpleNamespace(
        definition=defn,
        ammo_state=ammo_state,
        can_fire=can_fire,
    )


# ---------------------------------------------------------------------------
# Illumination factory
# ---------------------------------------------------------------------------

def _make_illumination(
    is_day: bool = True,
    twilight_stage: str | None = None,
) -> SimpleNamespace:
    """Mock illumination object."""
    return SimpleNamespace(is_day=is_day, twilight_stage=twilight_stage)
