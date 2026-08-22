"""Phase 118 SimulationContext checkpoint tests for indexed FOW RNG state."""

from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest

from stochastic_warfare.core.types import ModuleId

from tests.unit.test_phase_105_checkpoint_integrity import (
    _as_versionless_legacy_context,
    _context,
)


def test_current_context_checkpoint_requires_indexed_fow_atomically() -> None:
    context = _context(seed=118_201)
    checkpoint = deepcopy(context.get_state())
    checkpoint["rng"].pop("indexed_fow")
    before = context.get_state()
    conventional_owners = {module: context.rng_manager.get_stream(module) for module in ModuleId}

    with pytest.raises(
        ValueError,
        match="Invalid checkpoint clock or RNG state",
    ):
        context.set_state(checkpoint)

    assert context.get_state() == before
    assert all(context.rng_manager.get_stream(module) is owner for module, owner in conventional_owners.items())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("algorithm",), "PCG64"),
        (("schema_version",), True),
        (("namespace",), "other"),
        (("key_hex",), "0" * 32),
        (("key_preimage_sha256",), "0" * 64),
        (("complete_from_tick_zero",), 1),
        (("transcript", "digest_hex"), "0" * 64),
        (("transcript", "committed_interval_count"), -1),
        (("transcript", "committed_entry_count"), True),
    ],
)
def test_current_context_rejects_malformed_indexed_fow_before_mutation(
    path: tuple[str, ...],
    value: object,
) -> None:
    context = _context(seed=118_202)
    checkpoint = deepcopy(context.get_state())
    target = checkpoint["rng"]["indexed_fow"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    before = context.get_state()
    detection_owner = context.rng_manager.get_stream(ModuleId.DETECTION)

    with pytest.raises(
        ValueError,
        match="Invalid checkpoint clock or RNG state",
    ):
        context.set_state(checkpoint)

    assert context.get_state() == before
    assert context.rng_manager.get_stream(ModuleId.DETECTION) is detection_owner


def test_versionless_context_synthesizes_empty_incomplete_indexed_state() -> None:
    source = _context(seed=118_203)
    legacy = _as_versionless_legacy_context(source.get_state())
    assert "indexed_fow" not in legacy["rng"]
    expected_conventional = deepcopy(legacy["rng"]["streams"])
    target = _context(seed=999)
    conventional_owners = {module: target.rng_manager.get_stream(module) for module in ModuleId}

    target.set_state(legacy, allow_legacy_morale=True)

    restored = target.rng_manager.get_state()
    indexed = restored["indexed_fow"]
    assert indexed["complete_from_tick_zero"] is False
    assert indexed["transcript"] == {
        "digest_hex": hashlib.sha256(b"stochastic-warfare/fow-transcript/v1\x00").hexdigest(),
        "committed_interval_count": 0,
        "committed_entry_count": 0,
    }
    assert restored["streams"] == expected_conventional
    assert all(target.rng_manager.get_stream(module) is owner for module, owner in conventional_owners.items())


def test_versionless_context_cannot_promote_indexed_completeness() -> None:
    source = _context(seed=118_204)
    legacy = _as_versionless_legacy_context(source.get_state())
    target = _context(seed=999)
    target.set_state(legacy, allow_legacy_morale=True)

    allocation = target.rng_manager.begin_fow_detection_interval(
        0,
        ("blue", "red"),
    )
    for side in ("blue", "red"):
        allocation.acquire_side(side).complete()
    target.rng_manager.commit_fow_detection_interval(allocation)

    indexed = target.get_state()["rng"]["indexed_fow"]
    assert indexed["complete_from_tick_zero"] is False
    assert indexed["transcript"]["committed_interval_count"] == 1
    assert indexed["transcript"]["committed_entry_count"] == 0


def test_rng_restore_cannot_promote_legacy_completeness_atomically() -> None:
    source = _context(seed=118_206)
    legacy = _as_versionless_legacy_context(source.get_state())
    target = _context(seed=999)
    target.set_state(legacy, allow_legacy_morale=True)
    before = target.rng_manager.get_state()
    promoted = deepcopy(before)
    promoted["indexed_fow"]["complete_from_tick_zero"] = True

    with pytest.raises(ValueError, match="completeness cannot be promoted"):
        target.rng_manager.set_state(promoted)

    assert target.rng_manager.get_state() == before


def test_versionless_context_rejects_mixed_format_indexed_state_atomically() -> None:
    context = _context(seed=118_205)
    legacy = _as_versionless_legacy_context(context.get_state())
    legacy["rng"]["indexed_fow"] = context.rng_manager.get_state()["indexed_fow"]
    before = context.get_state()

    with pytest.raises(ValueError, match="Versionless.*format-118"):
        context.set_state(legacy, allow_legacy_morale=True)

    assert context.get_state() == before
