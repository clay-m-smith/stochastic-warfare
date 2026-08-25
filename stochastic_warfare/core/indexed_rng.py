"""Identity-addressed random decisions for fog-of-war adjudication.

This module implements the Phase 118 ``FOW_DETECTION`` random-access
boundary.  It deliberately does not expose a mutable ``Generator`` to
consumers: callers receive one four-lane Philox decision whose lane use is
validated and whose successful interval is committed to a rolling transcript.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import math
import threading
from typing import Final, Sequence

import numpy as np

from stochastic_warfare.core.types import ModuleId


INDEXED_FOW_ALGORITHM: Final = "numpy-philox-4x64"
INDEXED_FOW_SCHEMA_VERSION: Final = 1
INDEXED_FOW_NAMESPACE: Final = "FOW_DETECTION"

_KEY_DOMAIN: Final = b"stochastic-warfare/indexed-philox-key/v1\x00"
_DECISION_DOMAIN: Final = b"stochastic-warfare/fow-decision/v1\x00"
_TRANSCRIPT_INITIAL_DOMAIN: Final = b"stochastic-warfare/fow-transcript/v1\x00"
_TRANSCRIPT_RECORD_DOMAIN: Final = b"stochastic-warfare/fow-transcript-record/v1\x00"
_TRANSCRIPT_FOLD_DOMAIN: Final = b"stochastic-warfare/fow-transcript-fold/v1\x00"
_MAX_U8: Final = (1 << 8) - 1
_MAX_U16: Final = (1 << 16) - 1
_MAX_U32: Final = (1 << 32) - 1
_MAX_U64: Final = (1 << 64) - 1
_MASK_U64: Final = (1 << 64) - 1


class IndexedRNGValidationError(ValueError):
    """An indexed-RNG value or persisted state violates the contract."""


class IndexedRNGLifecycleError(RuntimeError):
    """An indexed-RNG allocation was used outside its valid lifecycle."""


class FOWTargetKind(IntEnum):
    """Closed target-kind codec for indexed fog-of-war decisions."""

    UNIT = 1
    DECOY = 2


class FOWDecisionLane(IntEnum):
    """The only consumer-visible lanes in one Philox decision block."""

    DETECTION = 0
    IDENTIFICATION = 1


@dataclass(frozen=True, slots=True)
class FOWDecisionIdentity:
    """Complete typed identity of one potential stochastic opportunity."""

    engine_tick: int
    reporting_side: str
    observer_unit_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str
    target_kind: FOWTargetKind
    target_id: str
    opportunity_ordinal: int = 0
    schema_version: int = INDEXED_FOW_SCHEMA_VERSION
    namespace: str = INDEXED_FOW_NAMESPACE


@dataclass(frozen=True, slots=True)
class _FOWDecisionIdentitySnapshot:
    """Compact immutable issuance seal for one validated decision identity."""

    engine_tick: int
    reporting_side: str
    observer_unit_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: str
    target_kind: FOWTargetKind
    target_id: str
    opportunity_ordinal: int
    schema_version: int
    namespace_type: type[object]


@dataclass(frozen=True, slots=True)
class FOWIndexedEntry:
    """One committed decision entry, including exact evidence material."""

    reporting_side: str
    decision_preimage: bytes
    counter: bytes
    raw_lanes: tuple[int, int, int, int]
    consumed_lane_mask: int


@dataclass(frozen=True, slots=True)
class FOWDetectionAdjudication:
    """Modeled probability and outcome for one indexed detection lane."""

    reporting_side: str
    decision_preimage: bytes
    counter: bytes
    probability: float
    detected: bool


@dataclass(frozen=True, slots=True)
class FOWIndexedIntervalRecord:
    """Canonical raw record and resulting rolling-transcript state."""

    engine_tick: int
    reporting_sides: tuple[str, ...]
    entries: tuple[FOWIndexedEntry, ...]
    adjudications: tuple[FOWDetectionAdjudication, ...]
    record_bytes: bytes
    previous_digest_hex: str
    transcript_digest_hex: str
    committed_interval_count: int
    committed_entry_count: int
    complete_from_tick_zero: bool


@dataclass(frozen=True, slots=True)
class FOWIndexedCommitPlan:
    """Owner-bound, fully prepared indexed-transcript publication."""

    record: FOWIndexedIntervalRecord
    _allocation: FOWIndexedAllocation
    _next_digest: bytes
    _owner_token: object


def _strict_uint(value: object, *, bits: int, label: str) -> int:
    if type(value) is not int:
        raise IndexedRNGValidationError(f"{label} must be a strict integer")
    maximum = (1 << bits) - 1
    if value < 0 or value > maximum:
        raise IndexedRNGValidationError(f"{label} must be in [0, {maximum}]")
    return value


def _strict_master_seed(value: object) -> int:
    if type(value) is not int or value < 0:
        raise IndexedRNGValidationError("master_seed must be a strict non-negative Python integer")
    return value


def _u8(value: int) -> bytes:
    return _strict_uint(value, bits=8, label="u8 value").to_bytes(1, "big")


def _u16(value: int) -> bytes:
    return _strict_uint(value, bits=16, label="u16 value").to_bytes(2, "big")


def _u32(value: int) -> bytes:
    return _strict_uint(value, bits=32, label="u32 value").to_bytes(4, "big")


def _u64(value: int) -> bytes:
    return _strict_uint(value, bits=64, label="u64 value").to_bytes(8, "big")


def _text_bytes(value: object, *, label: str) -> bytes:
    if type(value) is not str or not value or value.strip() != value:
        raise IndexedRNGValidationError(f"{label} must be a non-empty, trimmed string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise IndexedRNGValidationError(f"{label} must be valid UTF-8 text") from exc
    if len(encoded) > _MAX_U32:
        raise IndexedRNGValidationError(f"{label} exceeds the u32 UTF-8 byte-length bound")
    return _u32(len(encoded)) + encoded


def _canonical_reporting_sides(
    reporting_sides: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(reporting_sides, (str, bytes)):
        raise IndexedRNGValidationError("reporting_sides must be an ordered side sequence")
    try:
        sides = tuple(reporting_sides)
    except TypeError as exc:
        raise IndexedRNGValidationError("reporting_sides must be an ordered side sequence") from exc
    if not sides:
        raise IndexedRNGValidationError("reporting_sides must contain the complete non-empty side set")
    if len(sides) > _MAX_U32:
        raise IndexedRNGValidationError("reporting_sides exceeds the u32 side-count bound")
    encoded: list[bytes] = []
    for index, side in enumerate(sides):
        value = _text_bytes(side, label=f"reporting_sides[{index}]")
        encoded.append(value[4:])
    if len(set(sides)) != len(sides):
        raise IndexedRNGValidationError("reporting_sides contains a duplicate")
    if encoded != sorted(encoded):
        raise IndexedRNGValidationError("reporting_sides must be in ascending UTF-8 byte order")
    return sides


def derive_indexed_fow_key(master_seed: int) -> tuple[bytes, bytes, bytes]:
    """Return the exact key, key preimage, and preimage digest."""
    seed = _strict_master_seed(master_seed)
    seed_size = max(1, (seed.bit_length() + 7) // 8)
    if seed_size > _MAX_U32:
        raise IndexedRNGValidationError("master_seed minimal byte representation exceeds u32")
    seed_bytes = seed.to_bytes(seed_size, "big")
    preimage = _KEY_DOMAIN + _u32(seed_size) + seed_bytes
    preimage_digest = hashlib.sha256(preimage).digest()
    return preimage_digest[:16], preimage, preimage_digest


def encode_fow_decision(identity: FOWDecisionIdentity) -> bytes:
    """Encode the exact non-tick decision preimage from the Phase 118 spec."""
    if type(identity) is not FOWDecisionIdentity:
        raise IndexedRNGValidationError("identity must be an exact FOWDecisionIdentity")
    _strict_uint(identity.engine_tick, bits=64, label="engine_tick")
    if type(identity.schema_version) is not int or identity.schema_version != INDEXED_FOW_SCHEMA_VERSION:
        raise IndexedRNGValidationError("identity schema_version is not supported")
    if identity.namespace != INDEXED_FOW_NAMESPACE:
        raise IndexedRNGValidationError("identity namespace is not supported")
    if type(identity.target_kind) is not FOWTargetKind:
        raise IndexedRNGValidationError("target_kind must be an exact FOWTargetKind")
    return b"".join(
        (
            _DECISION_DOMAIN,
            _u16(INDEXED_FOW_SCHEMA_VERSION),
            _text_bytes(identity.reporting_side, label="reporting_side"),
            _text_bytes(identity.observer_unit_id, label="observer_unit_id"),
            _u64(
                _strict_uint(
                    identity.source_equipment_index,
                    bits=64,
                    label="source_equipment_index",
                )
            ),
            _text_bytes(identity.sensor_id, label="sensor_id"),
            _text_bytes(identity.modeled_role, label="modeled_role"),
            _u8(identity.target_kind.value),
            _text_bytes(identity.target_id, label="target_id"),
            _u32(
                _strict_uint(
                    identity.opportunity_ordinal,
                    bits=32,
                    label="opportunity_ordinal",
                )
            ),
        )
    )


def _fow_decision_identity_snapshot(
    identity: FOWDecisionIdentity,
) -> _FOWDecisionIdentitySnapshot:
    """Capture validated scalar values without retaining mutable namespace state."""
    return _FOWDecisionIdentitySnapshot(
        engine_tick=identity.engine_tick,
        reporting_side=identity.reporting_side,
        observer_unit_id=identity.observer_unit_id,
        source_equipment_index=identity.source_equipment_index,
        sensor_id=identity.sensor_id,
        modeled_role=identity.modeled_role,
        target_kind=identity.target_kind,
        target_id=identity.target_id,
        opportunity_ordinal=identity.opportunity_ordinal,
        schema_version=identity.schema_version,
        namespace_type=type(identity.namespace),
    )


def _fow_decision_identity_prefix_matches_snapshot(
    identity: FOWDecisionIdentity,
    snapshot: _FOWDecisionIdentitySnapshot,
) -> bool:
    """Check fields observed before the encoder's namespace comparison."""
    return not (
        type(identity.engine_tick) is not int
        or identity.engine_tick != snapshot.engine_tick
        or type(identity.schema_version) is not int
        or identity.schema_version != snapshot.schema_version
        or type(identity.namespace) is not snapshot.namespace_type
    )


def _fow_decision_identity_suffix_matches_snapshot(
    identity: FOWDecisionIdentity,
    snapshot: _FOWDecisionIdentitySnapshot,
) -> bool:
    """Check the remaining strict fields after namespace validation."""
    return (
        type(identity.target_kind) is FOWTargetKind
        and identity.target_kind is snapshot.target_kind
        and type(identity.reporting_side) is str
        and identity.reporting_side == snapshot.reporting_side
        and type(identity.observer_unit_id) is str
        and identity.observer_unit_id == snapshot.observer_unit_id
        and type(identity.source_equipment_index) is int
        and identity.source_equipment_index == snapshot.source_equipment_index
        and type(identity.sensor_id) is str
        and identity.sensor_id == snapshot.sensor_id
        and type(identity.modeled_role) is str
        and identity.modeled_role == snapshot.modeled_role
        and type(identity.target_id) is str
        and identity.target_id == snapshot.target_id
        and type(identity.opportunity_ordinal) is int
        and identity.opportunity_ordinal == snapshot.opportunity_ordinal
    )


def _fow_decision_identity_strict_fields_match_snapshot(
    identity: FOWDecisionIdentity,
    snapshot: _FOWDecisionIdentitySnapshot,
) -> bool:
    """Check all non-callback identity fields without observing namespace."""
    return _fow_decision_identity_prefix_matches_snapshot(
        identity,
        snapshot,
    ) and _fow_decision_identity_suffix_matches_snapshot(identity, snapshot)


def _fow_decision_identity_matches_snapshot(
    identity: FOWDecisionIdentity,
    snapshot: _FOWDecisionIdentitySnapshot,
) -> bool:
    """Compare one issued identity in encoder order without allocating."""
    if not _fow_decision_identity_prefix_matches_snapshot(identity, snapshot):
        return False
    namespace = identity.namespace
    try:
        if namespace != INDEXED_FOW_NAMESPACE:
            return False
    except Exception:  # An accepted comparator that now fails is tampering.
        return False
    return identity.namespace is namespace and _fow_decision_identity_strict_fields_match_snapshot(
        identity,
        snapshot,
    )


def raw_u64_to_uniform(raw: int) -> float:
    """Convert a raw unsigned lane to binary64 without a distribution API."""
    value = _strict_uint(raw, bits=64, label="raw Philox lane")
    return (value >> 11) * (2.0**-53)


def _strict_detection_probability(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise IndexedRNGValidationError(
            "detection probability must be finite in [0, 1]",
        )
    return float(value)


class _ReusablePhilox:
    """One reusable Philox bit generator with an exact counter reset."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) != 16:
            raise IndexedRNGValidationError("Philox key must be exactly 16 bytes")
        self._key = key
        self._key_int = int.from_bytes(key, "big")
        self._bit_generator = np.random.Philox(counter=0, key=self._key_int)

    @staticmethod
    def _words(value: int, count: int) -> np.ndarray:
        return np.array(
            [(value >> (64 * index)) & _MASK_U64 for index in range(count)],
            dtype=np.uint64,
        )

    def draw_block(self, counter: bytes) -> tuple[int, int, int, int]:
        """Reset all mutable Philox state and return one raw 4x64 block."""
        if type(counter) is not bytes or len(counter) != 32:
            raise IndexedRNGValidationError("Philox counter must be exactly 32 bytes")
        counter_int = int.from_bytes(counter, "big")
        self._bit_generator.state = {
            "bit_generator": "Philox",
            "state": {
                "counter": self._words(counter_int, 4),
                "key": self._words(self._key_int, 2),
            },
            "buffer": np.zeros(4, dtype=np.uint64),
            "buffer_pos": 4,
            "has_uint32": 0,
            "uinteger": 0,
        }
        raw = self._bit_generator.random_raw(4)
        return tuple(int(value) for value in raw)  # type: ignore[return-value]

    def get_state(self) -> dict[str, object]:
        """Return the complete mutable bit-generator state for parity tests."""
        return deepcopy(self._bit_generator.state)


class FOWIndexedDecision:
    """Lane-disciplined access to one identity-addressed Philox block."""

    __slots__ = (
        "_adjudication",
        "_entry",
        "_handle",
        "_identity",
        "_identity_snapshot",
        "_mask",
    )

    def __init__(
        self,
        handle: FOWIndexedSideHandle,
        identity: FOWDecisionIdentity,
        identity_snapshot: _FOWDecisionIdentitySnapshot,
        entry: FOWIndexedEntry,
    ) -> None:
        self._handle = handle
        self._identity = identity
        self._identity_snapshot = identity_snapshot
        self._entry = entry
        self._mask = 0
        self._adjudication: FOWDetectionAdjudication | None = None

    @property
    def counter(self) -> bytes:
        """Return the exact 256-bit counter bytes."""
        return self._entry.counter

    @property
    def raw_lanes(self) -> tuple[int, int, int, int]:
        """Return all raw lanes for bounded evidence recording."""
        return self._entry.raw_lanes

    @property
    def consumed_lane_mask(self) -> int:
        """Return the currently consumed lane mask (zero before detection)."""
        return self._mask

    def _issued_preimage(
        self,
        identity: FOWDecisionIdentity,
    ) -> bytes:
        """Return the preimage already validated for this exact identity."""
        try:
            self._handle._require_open()
            if identity is not self._identity:
                raise IndexedRNGValidationError(
                    "indexed decision identity is not its issued identity",
                )
            if not _fow_decision_identity_matches_snapshot(
                identity,
                self._identity_snapshot,
            ):
                raise IndexedRNGValidationError(
                    "indexed decision identity changed after issuance",
                )
            return self._entry.decision_preimage
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._handle._allocation._poison()
            raise

    def detection_uniform(self, *, probability: float) -> float:
        """Consume lane zero and bind its exact modeled adjudication."""
        try:
            modeled_probability = _strict_detection_probability(probability)
            uniform = self.consume_lane(FOWDecisionLane.DETECTION)
            self._adjudication = FOWDetectionAdjudication(
                reporting_side=self._entry.reporting_side,
                decision_preimage=self._entry.decision_preimage,
                counter=self._entry.counter,
                probability=modeled_probability,
                detected=uniform < modeled_probability,
            )
            return uniform
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._handle._allocation._poison()
            raise

    @property
    def detection_succeeded(self) -> bool:
        """Return the bound lane-zero outcome after detection adjudication."""
        if self._adjudication is None:
            raise IndexedRNGLifecycleError(
                "detection outcome is unavailable before lane-zero adjudication",
            )
        return self._adjudication.detected

    def identification_uniform(self, *, detection_succeeded: bool) -> float:
        """Consume lane one after a successful detection only."""
        return self.consume_lane(
            FOWDecisionLane.IDENTIFICATION,
            detection_succeeded=detection_succeeded,
        )

    def consume_lane(
        self,
        lane: FOWDecisionLane,
        *,
        detection_succeeded: bool = False,
    ) -> float:
        """Consume a typed lane while enforcing the detection-first contract."""
        try:
            self._handle._require_open()
            if type(lane) is not FOWDecisionLane:
                raise IndexedRNGValidationError("lane must be an exact FOWDecisionLane")
            if type(detection_succeeded) is not bool:
                raise IndexedRNGValidationError("detection_succeeded must be a strict boolean")
            if lane is FOWDecisionLane.DETECTION:
                if detection_succeeded:
                    raise IndexedRNGValidationError("detection lane does not accept a success assertion")
                if self._mask != 0:
                    raise IndexedRNGLifecycleError("detection lane was already consumed")
                self._mask = 1
                return raw_u64_to_uniform(self._entry.raw_lanes[0])
            if self._mask & 1 == 0:
                raise IndexedRNGLifecycleError("identification lane requires detection first")
            if not detection_succeeded:
                raise IndexedRNGLifecycleError("identification lane requires a successful detection")
            if self._adjudication is None or not self._adjudication.detected:
                raise IndexedRNGLifecycleError(
                    "identification lane disagrees with the indexed detection adjudication",
                )
            if self._mask & 2:
                raise IndexedRNGLifecycleError("identification lane was already consumed")
            self._mask |= 2
            return raw_u64_to_uniform(self._entry.raw_lanes[1])
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._handle._allocation._poison()
            raise

    def _committed_entry(self) -> FOWIndexedEntry:
        if self._mask not in (1, 3):
            raise IndexedRNGLifecycleError("every issued block must consume the detection lane")
        if self._adjudication is None:
            raise IndexedRNGLifecycleError(
                "every issued block must retain its detection adjudication",
            )
        return FOWIndexedEntry(
            reporting_side=self._entry.reporting_side,
            decision_preimage=self._entry.decision_preimage,
            counter=self._entry.counter,
            raw_lanes=self._entry.raw_lanes,
            consumed_lane_mask=self._mask,
        )

    def _committed_adjudication(self) -> FOWDetectionAdjudication:
        self._committed_entry()
        if self._adjudication is None:  # pragma: no cover - guarded above.
            raise IndexedRNGLifecycleError(
                "indexed detection adjudication is unavailable",
            )
        return self._adjudication


class FOWIndexedSideHandle:
    """One manager/module/tick/side-bound transactional Philox owner."""

    __slots__ = (
        "_allocation",
        "_decisions",
        "_finished",
        "_philox",
        "_side",
    )

    def __init__(
        self,
        allocation: FOWIndexedAllocation,
        side: str,
        key: bytes,
    ) -> None:
        self._allocation = allocation
        self._side = side
        self._philox = _ReusablePhilox(key)
        self._decisions: list[FOWIndexedDecision] = []
        self._finished = False

    @property
    def reporting_side(self) -> str:
        return self._side

    @property
    def engine_tick(self) -> int:
        return self._allocation.engine_tick

    def _require_open(self) -> None:
        self._allocation._require_active()
        if self._finished:
            raise IndexedRNGLifecycleError(f"indexed side handle {self._side!r} was already completed")

    def issue(self, identity: FOWDecisionIdentity) -> FOWIndexedDecision:
        """Issue one unique block for a complete, handle-bound identity."""
        try:
            self._require_open()
            if type(identity) is not FOWDecisionIdentity:
                raise IndexedRNGValidationError(
                    "identity must be an exact FOWDecisionIdentity",
                )
            identity_snapshot = _fow_decision_identity_snapshot(identity)
            issued_namespace = identity.namespace
            preimage = encode_fow_decision(identity)
            if identity.namespace is not issued_namespace or not _fow_decision_identity_strict_fields_match_snapshot(
                identity,
                identity_snapshot,
            ):
                raise IndexedRNGValidationError(
                    "indexed decision identity changed during issuance",
                )
            if identity.engine_tick != self.engine_tick:
                raise IndexedRNGValidationError("identity engine_tick disagrees with its allocation")
            if identity.reporting_side != self._side:
                raise IndexedRNGValidationError("identity reporting_side disagrees with its handle")
            digest = self._allocation._register_preimage(preimage)
            counter = digest + _u64(self.engine_tick)
            raw_lanes = self._philox.draw_block(counter)
            entry = FOWIndexedEntry(
                reporting_side=self._side,
                decision_preimage=preimage,
                counter=counter,
                raw_lanes=raw_lanes,
                consumed_lane_mask=0,
            )
            decision = FOWIndexedDecision(
                self,
                identity,
                identity_snapshot,
                entry,
            )
            self._decisions.append(decision)
            return decision
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._allocation._poison()
            raise

    def complete(self) -> tuple[FOWIndexedEntry, ...]:
        """Freeze this side's validated entries for coordinator commit."""
        try:
            self._require_open()
            entries = tuple(decision._committed_entry() for decision in self._decisions)
            self._finished = True
            return entries
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._allocation._poison()
            raise

    def _entries(self) -> tuple[FOWIndexedEntry, ...]:
        if not self._finished:
            raise IndexedRNGLifecycleError(f"indexed side handle {self._side!r} is incomplete")
        return tuple(decision._committed_entry() for decision in self._decisions)

    def _adjudications(self) -> tuple[FOWDetectionAdjudication, ...]:
        if not self._finished:
            raise IndexedRNGLifecycleError(
                f"indexed side handle {self._side!r} is incomplete",
            )
        return tuple(decision._committed_adjudication() for decision in self._decisions)


class FOWIndexedAllocation:
    """One complete all-side fog-of-war RNG transaction."""

    __slots__ = (
        "_acquired",
        "_lock",
        "_owner",
        "_preimages",
        "_state",
        "engine_tick",
        "module",
        "reporting_sides",
    )

    def __init__(
        self,
        owner: IndexedFOWRNG,
        *,
        module: ModuleId,
        engine_tick: int,
        reporting_sides: tuple[str, ...],
    ) -> None:
        self._owner = owner
        self.module = module
        self.engine_tick = engine_tick
        self.reporting_sides = reporting_sides
        self._state = "active"
        self._acquired: dict[str, FOWIndexedSideHandle] = {}
        self._preimages: dict[bytes, bytes] = {}
        self._lock = threading.RLock()

    def _require_active(self) -> None:
        if self._state != "active" or self._owner._active is not self:
            raise IndexedRNGLifecycleError(f"indexed allocation is not active (state={self._state})")
        if self._owner._poisoned:
            raise IndexedRNGLifecycleError("indexed RNG owner is poisoned")

    def acquire_side(self, reporting_side: str) -> FOWIndexedSideHandle:
        """Acquire exactly one independently reusable handle for a listed side."""
        try:
            with self._lock:
                self._require_active()
                _text_bytes(reporting_side, label="reporting_side")
                if reporting_side not in self.reporting_sides:
                    raise IndexedRNGValidationError("reporting side is not in the allocated complete side set")
                if reporting_side in self._acquired:
                    raise IndexedRNGLifecycleError(f"reporting side {reporting_side!r} was already acquired")
                handle = FOWIndexedSideHandle(
                    self,
                    reporting_side,
                    self._owner.key,
                )
                self._acquired[reporting_side] = handle
                return handle
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            self._poison()
            raise

    def _register_preimage(self, preimage: bytes) -> bytes:
        with self._lock:
            self._require_active()
            digest = self._owner._decision_digest(preimage)
            if type(digest) is not bytes or len(digest) != 24:
                raise IndexedRNGValidationError("decision digest must be exactly 24 bytes")
            prior = self._preimages.get(digest)
            if prior is not None:
                if prior == preimage:
                    raise IndexedRNGLifecycleError("indexed decision identity was issued more than once")
                raise IndexedRNGLifecycleError("distinct indexed decision preimages collided")
            self._preimages[digest] = preimage
            return digest

    def _poison(self) -> None:
        with self._lock:
            if self._state == "committed":
                return
            self._state = "poisoned"
            self._owner._mark_poisoned(self)

    def abort(self) -> None:
        """Abort this interval and make incomplete evidence fail closed."""
        self._poison()


class IndexedFOWRNG:
    """Persisted indexed key/transcript owner used by :class:`RNGManager`."""

    def __init__(
        self,
        master_seed: int,
        *,
        complete_from_tick_zero: bool = True,
    ) -> None:
        if type(complete_from_tick_zero) is not bool:
            raise IndexedRNGValidationError("complete_from_tick_zero must be a strict boolean")
        key, _preimage, preimage_digest = derive_indexed_fow_key(master_seed)
        self._master_seed = master_seed
        self.key = key
        self._key_preimage_digest = preimage_digest
        self._transcript_digest = hashlib.sha256(_TRANSCRIPT_INITIAL_DOMAIN).digest()
        self._committed_interval_count = 0
        self._committed_entry_count = 0
        self._complete_from_tick_zero = complete_from_tick_zero
        self._active: FOWIndexedAllocation | None = None
        self._prepared_commit: FOWIndexedCommitPlan | None = None
        self._commit_owner_token = object()
        self._poisoned = False

    @staticmethod
    def _decision_digest(preimage: bytes) -> bytes:
        return hashlib.sha256(preimage).digest()[:24]

    @property
    def complete_from_tick_zero(self) -> bool:
        return self._complete_from_tick_zero

    @property
    def committed_interval_count(self) -> int:
        return self._committed_interval_count

    @property
    def committed_entry_count(self) -> int:
        return self._committed_entry_count

    @property
    def transcript_digest_hex(self) -> str:
        return self._transcript_digest.hex()

    def begin_interval(
        self,
        *,
        module: ModuleId,
        engine_tick: int,
        reporting_sides: Sequence[str],
    ) -> FOWIndexedAllocation:
        """Begin the sole supported module/tick/ordered-side allocation."""
        if self._poisoned:
            raise IndexedRNGLifecycleError("indexed RNG owner is poisoned")
        if self._active is not None:
            raise IndexedRNGLifecycleError("an indexed FOW allocation is already active")
        if type(module) is not ModuleId or module is not ModuleId.DETECTION:
            raise IndexedRNGValidationError("indexed FOW allocation requires ModuleId.DETECTION")
        tick = _strict_uint(engine_tick, bits=64, label="engine_tick")
        sides = _canonical_reporting_sides(reporting_sides)
        allocation = FOWIndexedAllocation(
            self,
            module=module,
            engine_tick=tick,
            reporting_sides=sides,
        )
        self._active = allocation
        return allocation

    def _mark_poisoned(self, allocation: FOWIndexedAllocation) -> None:
        if self._active is allocation:
            self._active = None
        self._prepared_commit = None
        self._poisoned = True

    def abort_interval(self, allocation: FOWIndexedAllocation) -> None:
        """Reject wrong ownership and poison an in-flight interval."""
        if type(allocation) is not FOWIndexedAllocation:
            raise IndexedRNGValidationError("allocation must be an exact FOWIndexedAllocation")
        if allocation._owner is not self:
            allocation._poison()
            raise IndexedRNGLifecycleError("indexed allocation belongs to a different RNG manager")
        allocation.abort()

    def prepare_interval_commit(
        self,
        allocation: FOWIndexedAllocation,
    ) -> FOWIndexedCommitPlan:
        """Validate and freeze a complete interval without publishing it."""
        if type(allocation) is not FOWIndexedAllocation:
            raise IndexedRNGValidationError("allocation must be an exact FOWIndexedAllocation")
        if allocation._owner is not self:
            allocation._poison()
            raise IndexedRNGLifecycleError("indexed allocation belongs to a different RNG manager")
        try:
            allocation._require_active()
            if self._prepared_commit is not None:
                raise IndexedRNGLifecycleError("indexed allocation already has a prepared commit")
            if allocation.module is not ModuleId.DETECTION:
                raise IndexedRNGValidationError("indexed allocation module binding changed")
            if tuple(allocation._acquired) != allocation.reporting_sides:
                raise IndexedRNGLifecycleError("indexed allocation is missing a complete ordered side union")
            entries = tuple(
                entry for side in allocation.reporting_sides for entry in allocation._acquired[side]._entries()
            )
            entries = tuple(
                sorted(
                    entries,
                    key=lambda entry: (
                        entry.reporting_side.encode("utf-8"),
                        entry.counter,
                    ),
                )
            )
            adjudications = tuple(
                adjudication
                for side in allocation.reporting_sides
                for adjudication in allocation._acquired[side]._adjudications()
            )
            adjudications = tuple(
                sorted(
                    adjudications,
                    key=lambda adjudication: (
                        adjudication.reporting_side.encode("utf-8"),
                        adjudication.counter,
                    ),
                )
            )
            if len(adjudications) != len(entries):
                raise IndexedRNGLifecycleError(
                    "indexed entries and detection adjudications differ in count",
                )
            for entry, adjudication in zip(
                entries,
                adjudications,
                strict=True,
            ):
                if (
                    adjudication.reporting_side != entry.reporting_side
                    or adjudication.decision_preimage != entry.decision_preimage
                    or adjudication.counter != entry.counter
                ):
                    raise IndexedRNGLifecycleError(
                        "indexed entry and detection adjudication identities differ",
                    )
                probability = _strict_detection_probability(
                    adjudication.probability,
                )
                expected_detected = raw_u64_to_uniform(entry.raw_lanes[0]) < probability
                if type(adjudication.detected) is not bool or adjudication.detected is not expected_detected:
                    raise IndexedRNGLifecycleError(
                        "indexed detection adjudication disagrees with lane zero",
                    )
                if entry.consumed_lane_mask == 3 and not adjudication.detected:
                    raise IndexedRNGLifecycleError(
                        "indexed identification consumption requires detection success",
                    )
            if len(entries) > _MAX_U64:
                raise IndexedRNGValidationError("indexed interval entry count exceeds u64")
            if self._committed_interval_count == _MAX_U64:
                raise IndexedRNGValidationError("indexed transcript interval count exceeds u64")
            if self._committed_entry_count > _MAX_U64 - len(entries):
                raise IndexedRNGValidationError("indexed transcript entry count exceeds u64")
            record_parts = [
                _TRANSCRIPT_RECORD_DOMAIN,
                _u16(INDEXED_FOW_SCHEMA_VERSION),
                _u64(allocation.engine_tick),
                _u32(len(allocation.reporting_sides)),
            ]
            record_parts.extend(_text_bytes(side, label="reporting_side") for side in allocation.reporting_sides)
            record_parts.append(_u64(len(entries)))
            for entry in entries:
                if entry.consumed_lane_mask not in (1, 3):
                    raise IndexedRNGLifecycleError("indexed entry has an invalid consumed-lane mask")
                record_parts.extend(
                    (
                        _text_bytes(
                            entry.reporting_side,
                            label="entry reporting_side",
                        ),
                        entry.counter,
                        _u8(entry.consumed_lane_mask),
                    )
                )
            record = b"".join(record_parts)
            if len(record) > _MAX_U64:
                raise IndexedRNGValidationError("indexed transcript record exceeds u64")
            previous_digest = self._transcript_digest
            next_digest = hashlib.sha256(
                _TRANSCRIPT_FOLD_DOMAIN + previous_digest + _u64(len(record)) + record
            ).digest()
            prepared_record = FOWIndexedIntervalRecord(
                engine_tick=allocation.engine_tick,
                reporting_sides=allocation.reporting_sides,
                entries=entries,
                adjudications=adjudications,
                record_bytes=record,
                previous_digest_hex=previous_digest.hex(),
                transcript_digest_hex=next_digest.hex(),
                committed_interval_count=self._committed_interval_count + 1,
                committed_entry_count=(self._committed_entry_count + len(entries)),
                complete_from_tick_zero=self._complete_from_tick_zero,
            )
        except (IndexedRNGLifecycleError, IndexedRNGValidationError):
            allocation._poison()
            raise

        plan = FOWIndexedCommitPlan(
            record=prepared_record,
            _allocation=allocation,
            _next_digest=next_digest,
            _owner_token=self._commit_owner_token,
        )
        self._prepared_commit = plan
        allocation._state = "prepared"
        return plan

    def validate_prepared_interval_commit(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> None:
        """Validate a prepared commit before an outer transaction publishes."""
        if type(plan) is not FOWIndexedCommitPlan:
            raise IndexedRNGValidationError("plan must be an exact FOWIndexedCommitPlan")
        if plan._owner_token is not self._commit_owner_token:
            raise IndexedRNGLifecycleError("indexed commit plan belongs to another RNG owner")
        if self._prepared_commit is not plan:
            raise IndexedRNGLifecycleError("indexed commit plan is stale or inactive")
        if self._active is not plan._allocation:
            raise IndexedRNGLifecycleError("indexed commit allocation is stale or inactive")
        if plan._allocation._state != "prepared" or self._poisoned:
            raise IndexedRNGLifecycleError("indexed commit allocation is not prepared")

    def _commit_prevalidated_interval(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> FOWIndexedIntervalRecord:
        """Publish a previously validated plan using assignment-only swaps."""
        record = plan.record
        self._transcript_digest = plan._next_digest
        self._committed_interval_count = record.committed_interval_count
        self._committed_entry_count = record.committed_entry_count
        plan._allocation._state = "committed"
        self._active = None
        self._prepared_commit = None
        return record

    def commit_prepared_interval(
        self,
        plan: FOWIndexedCommitPlan,
    ) -> FOWIndexedIntervalRecord:
        """Validate and publish a prepared standalone-owner interval."""
        self.validate_prepared_interval_commit(plan)
        return self._commit_prevalidated_interval(plan)

    def commit_interval(
        self,
        allocation: FOWIndexedAllocation,
    ) -> FOWIndexedIntervalRecord:
        """Prepare and commit one standalone-owner interval."""
        return self.commit_prepared_interval(
            self.prepare_interval_commit(allocation),
        )

    def mark_history_incomplete(self) -> None:
        """Permanently qualify a legacy-derived transcript as incomplete."""
        if self._active is not None or self._poisoned:
            raise IndexedRNGLifecycleError("cannot change completeness during an invalid allocation state")
        self._complete_from_tick_zero = False

    def get_state(self) -> dict[str, object]:
        """Return strict JSON-safe key derivation and transcript state."""
        if self._active is not None:
            raise IndexedRNGLifecycleError("cannot checkpoint an active indexed FOW allocation")
        if self._poisoned:
            raise IndexedRNGLifecycleError("cannot checkpoint a poisoned indexed FOW allocation")
        return {
            "algorithm": INDEXED_FOW_ALGORITHM,
            "schema_version": INDEXED_FOW_SCHEMA_VERSION,
            "namespace": INDEXED_FOW_NAMESPACE,
            "key_hex": self.key.hex(),
            "key_preimage_sha256": self._key_preimage_digest.hex(),
            "complete_from_tick_zero": self._complete_from_tick_zero,
            "transcript": {
                "digest_hex": self._transcript_digest.hex(),
                "committed_interval_count": self._committed_interval_count,
                "committed_entry_count": self._committed_entry_count,
            },
        }

    @classmethod
    def from_state(
        cls,
        master_seed: int,
        state: object,
    ) -> IndexedFOWRNG:
        """Validate, rederive, and construct without partially mutating state."""
        seed = _strict_master_seed(master_seed)
        if type(state) is not dict:
            raise IndexedRNGValidationError("indexed_fow state must be an exact mapping")
        expected_keys = {
            "algorithm",
            "schema_version",
            "namespace",
            "key_hex",
            "key_preimage_sha256",
            "complete_from_tick_zero",
            "transcript",
        }
        if set(state) != expected_keys:
            raise IndexedRNGValidationError("indexed_fow state has invalid key topology")
        if type(state["algorithm"]) is not str or state["algorithm"] != INDEXED_FOW_ALGORITHM:
            raise IndexedRNGValidationError("indexed FOW algorithm mismatch")
        if type(state["schema_version"]) is not int or state["schema_version"] != INDEXED_FOW_SCHEMA_VERSION:
            raise IndexedRNGValidationError("indexed FOW schema mismatch")
        if type(state["namespace"]) is not str or state["namespace"] != INDEXED_FOW_NAMESPACE:
            raise IndexedRNGValidationError("indexed FOW namespace mismatch")
        derived = cls(seed)
        if state["key_hex"] != derived.key.hex():
            raise IndexedRNGValidationError("indexed FOW key derivation mismatch")
        if state["key_preimage_sha256"] != derived._key_preimage_digest.hex():
            raise IndexedRNGValidationError("indexed FOW key-preimage digest mismatch")
        complete = state["complete_from_tick_zero"]
        if type(complete) is not bool:
            raise IndexedRNGValidationError("complete_from_tick_zero must be a strict boolean")
        transcript = state["transcript"]
        if type(transcript) is not dict or set(transcript) != {
            "digest_hex",
            "committed_interval_count",
            "committed_entry_count",
        }:
            raise IndexedRNGValidationError("indexed FOW transcript has invalid key topology")
        digest_hex = transcript["digest_hex"]
        if type(digest_hex) is not str or len(digest_hex) != 64:
            raise IndexedRNGValidationError("indexed FOW transcript digest must be 32-byte lowercase hex")
        try:
            digest = bytes.fromhex(digest_hex)
        except ValueError as exc:
            raise IndexedRNGValidationError("indexed FOW transcript digest is not hexadecimal") from exc
        if digest.hex() != digest_hex:
            raise IndexedRNGValidationError("indexed FOW transcript digest must use lowercase hex")
        intervals = _strict_uint(
            transcript["committed_interval_count"],
            bits=64,
            label="committed_interval_count",
        )
        entries = _strict_uint(
            transcript["committed_entry_count"],
            bits=64,
            label="committed_entry_count",
        )
        initial_digest = hashlib.sha256(_TRANSCRIPT_INITIAL_DOMAIN).digest()
        if intervals == 0 and (entries != 0 or digest != initial_digest):
            raise IndexedRNGValidationError("empty indexed transcript counters and digest disagree")
        if entries > 0 and intervals == 0:
            raise IndexedRNGValidationError("indexed transcript entries require a committed interval")
        derived._transcript_digest = digest
        derived._committed_interval_count = intervals
        derived._committed_entry_count = entries
        derived._complete_from_tick_zero = complete
        return derived
