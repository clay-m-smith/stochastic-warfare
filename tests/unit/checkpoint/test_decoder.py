"""Strict shared checkpoint decoding for Phase 118."""

from __future__ import annotations

import json

import numpy as np
import pytest

import stochastic_warfare.core.checkpoint as checkpoint_module
from stochastic_warfare.core.checkpoint import (
    CheckpointManager,
    NumpyEncoder,
    decode_checkpoint_json,
)


@pytest.mark.parametrize(
    "array",
    (
        np.array([[1, 2], [3, 4]], dtype=np.uint64),
        np.array(7, dtype=np.int64),
        np.array(1.5, dtype=np.float32),
        np.array(True, dtype=np.bool_),
    ),
    ids=("matrix", "integer-scalar", "float-scalar", "boolean-scalar"),
)
def test_strict_decoder_round_trips_supported_numpy_array(
    array: np.ndarray,
) -> None:
    payload = json.dumps(
        {"rng": array},
        cls=NumpyEncoder,
    ).encode("utf-8")

    decoded = decode_checkpoint_json(payload)

    assert decoded["rng"].dtype == array.dtype
    assert decoded["rng"].shape == array.shape
    np.testing.assert_array_equal(decoded["rng"], array)


@pytest.mark.parametrize(
    "payload",
    (
        b'{"value":1,"value":2}',
        b'{"outer":{"value":1,"value":2}}',
    ),
)
def test_strict_decoder_rejects_duplicate_keys(payload: bytes) -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_checkpoint_json(payload)


@pytest.mark.parametrize(
    "payload",
    (
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"value":1e400}',
    ),
)
def test_strict_decoder_rejects_nonfinite_numbers(payload: bytes) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        decode_checkpoint_json(payload)


@pytest.mark.parametrize(
    "marker",
    (
        {"__ndarray__": [1, 2]},
        {"__dtype__": "uint64"},
        {"__ndarray__": [1, 2], "__dtype__": "uint64", "extra": 1},
        {"__ndarray__": [1, 2], "__dtype__": "object"},
        {"__ndarray__": [[1], [2, 3]], "__dtype__": "float64"},
        {"__ndarray__": [1.0, float("inf")], "__dtype__": "float64"},
        {"__ndarray__": [True, 2], "__dtype__": "int64"},
        {"__ndarray__": True, "__dtype__": "int64"},
        {"__ndarray__": [1.75, 2.0], "__dtype__": "int64"},
        {"__ndarray__": 1.75, "__dtype__": "int64"},
        {"__ndarray__": ["1", 2], "__dtype__": "int64"},
        {"__ndarray__": [256], "__dtype__": "uint8"},
        {"__ndarray__": 256, "__dtype__": "uint8"},
        {"__ndarray__": [-129], "__dtype__": "int8"},
        {"__ndarray__": [1, False], "__dtype__": "bool"},
        {"__ndarray__": 1, "__dtype__": "bool"},
        {"__ndarray__": [True, 2.0], "__dtype__": "float64"},
        {"__ndarray__": True, "__dtype__": "float64"},
        {"__ndarray__": ["1.0"], "__dtype__": "float64"},
        {"__ndarray__": None, "__dtype__": "float64"},
        {"__ndarray__": {"value": 1.0}, "__dtype__": "float64"},
        {"__ndarray__": [1e40], "__dtype__": "float32"},
    ),
)
def test_strict_decoder_rejects_malformed_numpy_markers(
    marker: dict[str, object],
) -> None:
    payload = json.dumps(marker).encode("utf-8")

    with pytest.raises(ValueError):
        decode_checkpoint_json(payload)


def test_strict_decoder_rejects_invalid_utf8_and_nonobject_top_level() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        decode_checkpoint_json(b'{"value":"\xff"}')
    with pytest.raises(ValueError, match="top level"):
        decode_checkpoint_json(b"[]")


def _legacy_weapon_payload(*, versioned: bool, token: str = "-Infinity") -> bytes:
    version = '"checkpoint_version":116,' if versioned else ""
    return (
        "{" + version + '"context":{"unit_weapon_states":{"unit-1":' + '[{"last_fire_time_s":' + token + "}]}}}"
    ).encode("utf-8")


def test_versionless_migration_accepts_only_exact_weapon_sentinel_path() -> None:
    decoded = decode_checkpoint_json(
        _legacy_weapon_payload(versioned=False),
        allow_versionless_weapon_sentinels=True,
    )

    assert decoded["context"]["unit_weapon_states"]["unit-1"][0]["last_fire_time_s"] is None


def test_versionless_migration_skips_legacy_walk_without_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        pytest.fail(f"unexpected legacy sentinel walk: {args!r}, {kwargs!r}")

    monkeypatch.setattr(
        checkpoint_module,
        "_replace_legacy_weapon_sentinels",
        fail_if_called,
    )

    assert decode_checkpoint_json(
        b'{"context":{"unit_weapon_states":{}}}',
        allow_versionless_weapon_sentinels=True,
    ) == {"context": {"unit_weapon_states": {}}}


def test_legacy_weapon_sentinel_rejects_versioned_or_wrong_path() -> None:
    with pytest.raises(ValueError, match="versionless"):
        decode_checkpoint_json(
            _legacy_weapon_payload(versioned=True),
            allow_versionless_weapon_sentinels=True,
        )
    with pytest.raises(ValueError, match="outside a weapon timestamp"):
        decode_checkpoint_json(
            b'{"context":{"other":-Infinity}}',
            allow_versionless_weapon_sentinels=True,
        )


def test_checkpoint_manager_does_not_fallback_for_malformed_json() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        CheckpointManager().restore_checkpoint(b'{"value":1,"value":2}')
