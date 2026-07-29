"""Atomic checkpoint integrity for typed multi-ammunition loadouts."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from stochastic_warfare.simulation.engine import SimulationEngine
from stochastic_warfare.simulation.scenario import ScenarioLoader


DATA_DIR = Path("data")
KURSK_SCENARIO = DATA_DIR / "eras/ww2/scenarios/kursk/scenario.yaml"
WEAPON_ID = "kwk40_l48_75mm"


def _engine(seed: int = 109) -> SimulationEngine:
    return SimulationEngine(
        ScenarioLoader(DATA_DIR).load(KURSK_SCENARIO, seed=seed),
    )


def _attachment(engine: SimulationEngine):
    ctx = engine._ctx
    return next(
        (entity_id, index, attachment)
        for entity_id, attachments in ctx.unit_weapons.items()
        for index, attachment in enumerate(attachments)
        if attachment.weapon.weapon_id == WEAPON_ID
    )


def _saved_ammo_state(state, entity_id: str, index: int):
    return state["context"]["unit_weapon_states"][entity_id][index][
        "ammo_state"
    ]


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_key",
        "extra_key",
        "bool_rounds",
        "non_integer_rounds",
        "negative_rounds",
        "bool_total",
        "non_integer_total",
        "negative_total",
    ),
)
def test_invalid_ammunition_checkpoint_is_atomic_in_place_and_fresh(
    mutation: str,
) -> None:
    source = _engine()
    entity_id, index, attachment = _attachment(source)
    ammo_ids = [ammo.ammo_id for ammo in attachment.ammunition]
    assert len(ammo_ids) == 2
    invalid = copy.deepcopy(source.get_state())
    ammo_state = _saved_ammo_state(invalid, entity_id, index)

    if mutation == "missing_key":
        ammo_state["rounds_by_type"].pop(ammo_ids[1])
        expected = "ammunition topology"
    elif mutation == "extra_key":
        ammo_state["rounds_by_type"]["phase109_extra_round"] = 1
        expected = "ammunition topology"
    elif mutation == "bool_rounds":
        ammo_state["rounds_by_type"][ammo_ids[0]] = True
        expected = "non-negative integer"
    elif mutation == "non_integer_rounds":
        ammo_state["rounds_by_type"][ammo_ids[0]] = 1.5
        expected = "non-negative integer"
    elif mutation == "negative_rounds":
        ammo_state["rounds_by_type"][ammo_ids[0]] = -1
        expected = "non-negative integer"
    elif mutation == "bool_total":
        ammo_state["total_rounds_fired"] = False
        expected = "total_rounds_fired"
    elif mutation == "non_integer_total":
        ammo_state["total_rounds_fired"] = 2.5
        expected = "total_rounds_fired"
    else:
        ammo_state["total_rounds_fired"] = -1
        expected = "total_rounds_fired"

    fresh = _engine()
    for candidate in (source, fresh):
        before = candidate.checkpoint()
        with pytest.raises(ValueError, match=expected):
            candidate.set_state(invalid)
        assert candidate.checkpoint() == before


def test_fresh_restore_preserves_ammo_topology_and_exact_continuation() -> None:
    control = _engine(seed=10_909)
    entity_id, index, attachment = _attachment(control)
    first_ammo, second_ammo = attachment.ammunition
    assert attachment.weapon.fire(first_ammo.ammo_id)
    assert attachment.weapon.fire(second_ammo.ammo_id)
    checkpoint = control.checkpoint()

    resumed = _engine(seed=10_909)
    _, _, pre_restore_attachment = _attachment(resumed)
    assert pre_restore_attachment is not attachment
    resumed.restore(checkpoint)
    resumed_attachment = resumed._ctx.unit_weapons[entity_id][index]

    assert resumed_attachment is pre_restore_attachment
    assert tuple(
        ammo.ammo_id for ammo in resumed_attachment.ammunition
    ) == tuple(ammo.ammo_id for ammo in attachment.ammunition)
    assert resumed_attachment.weapon.get_state() == attachment.weapon.get_state()

    control.step()
    resumed.step()
    assert resumed.checkpoint() == control.checkpoint()
