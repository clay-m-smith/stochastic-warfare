"""REM-052 legacy FOW update retirement contract and obligation map.

The direct-update suites were retired only after their unique obligations were
mapped to canonical owners:

* ``test_fog_of_war.py`` keeps its state/view and ground-truth contracts here;
  stochastic contact lifecycle and continuation are exercised by
  ``test_fow_receipts.py``, ``test_contact_state.py``, and the production FOW
  checkpoint integration suite.
* ``test_phase115_fow_witness.py`` keeps DetectionEngine scan compatibility in
  ``test_fow_witness.py``; witness identity, aliasing, rollback, and observer
  support live in receipt, observer-support, and targeting-control tests.
* ``test_phase84_detection_culling.py`` maps to the closed-boundary and RNG
  parity cases in ``tests/integration/performance/test_rng_culling.py``.
* ``test_phase84_scan_scheduling.py`` keeps SensorDefinition validation in
  ``tests/unit/performance/test_scan_scheduling.py``; runtime cadence belongs
  to the typed receipt/cadence transaction tests.
* ``test_phase89_parallel_detection.py`` maps to
  ``tests/integration/performance/test_parallel_detection.py`` and the
  three-side targeting production oracle.
* ``test_phase116_fow_contact_state.py`` now primes contacts through the typed
  receipt transaction; all restore corruption and atomicity cases remain.

The legacy conventional-RNG and side-at-a-time parity cases had no supported
equivalent: those missing owners are precisely why ``update()`` now rejects.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.indexed_rng import IndexedFOWRNG
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.detection.fog_of_war import (
    FogOfWarManager,
    UnsupportedLegacyFogOfWarUpdateError,
)


class _UnreadableInputs(list[dict[str, Any]]):
    """Prove the unsupported boundary does not inspect caller containers."""

    def __iter__(self):
        raise AssertionError("legacy update inspected its own-unit input")

    def __len__(self) -> int:
        raise AssertionError("legacy update inspected its own-unit input")

    def __getitem__(self, index: object) -> dict[str, Any]:
        del index
        raise AssertionError("legacy update inspected its own-unit input")


def _run_empty_canonical_cycle(
    manager: FogOfWarManager,
) -> tuple[dict[str, Any], object, object]:
    tick = manager.cadence.committed_ordinal
    transaction = manager.begin_update_transaction(("blue",))
    cadence = manager.cadence.stage_interval(())
    indexed = IndexedFOWRNG(139_052)
    allocation = indexed.begin_interval(
        module=ModuleId.DETECTION,
        engine_tick=tick,
        reporting_sides=("blue",),
    )
    side_plan = manager.update_with_receipt(
        "blue",
        [],
        [],
        5.0,
        transaction=transaction,
        cadence_plan=cadence,
        indexed_rng=allocation.acquire_side("blue"),
        lod_tiers={},
        current_time=(tick + 1) * 5.0,
        current_tick=tick,
        detection_culling=True,
    )
    publication = manager.prevalidate_update_transaction(
        transaction,
        (side_plan,),
    )
    indexed_record = indexed.commit_interval(allocation)
    manager.cadence.commit_interval(cadence)
    manager.commit_update_transaction(publication)
    return manager.get_state(), side_plan.receipt, indexed_record


def test_legacy_update_rejects_before_inputs_state_or_rng_are_touched() -> None:
    """The compatibility signature is an immediate, typed migration error."""
    candidate = FogOfWarManager(rng=np.random.default_rng(52))
    control = FogOfWarManager(rng=np.random.default_rng(52))
    caller_rng = np.random.default_rng(5_200)
    caller_rng_before = copy.deepcopy(caller_rng.bit_generator.state)
    state_before = copy.deepcopy(candidate.get_state())

    with pytest.raises(
        UnsupportedLegacyFogOfWarUpdateError,
        match="receipt-bearing complete-side transaction",
    ):
        candidate.update(
            "blue",
            _UnreadableInputs(),
            _UnreadableInputs(),
            5.0,
            rng=caller_rng,
        )

    assert candidate.get_state() == state_before
    assert caller_rng.bit_generator.state == caller_rng_before
    assert candidate.cadence.has_active_interval is False
    assert candidate.cadence.poisoned is False

    candidate_result = _run_empty_canonical_cycle(candidate)
    control_result = _run_empty_canonical_cycle(control)
    assert candidate_result == control_result
