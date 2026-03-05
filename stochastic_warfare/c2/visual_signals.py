"""Visual and audible C2 for pre-courier armies.

Ancient C2 is synchronous presence-based (see the banner = know the order)
vs Napoleonic asynchronous delivery (courier carries a message).

Signal types:
* BANNER — LOS required, 1000m range, instant.
* HORN — no LOS needed (sound), 500m range, instant.
* RUNNER — async delivery, slow (3 m/s), reliable.
* FIRE_BEACON — long range (10km), LOS required, binary signal only.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalType(enum.IntEnum):
    """Type of visual/audible signal."""

    BANNER = 0
    HORN = 1
    RUNNER = 2
    FIRE_BEACON = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class VisualSignalConfig(BaseModel):
    """Configuration for visual/audible signaling system."""

    banner_range_m: float = 1000.0
    banner_requires_los: bool = True
    horn_range_m: float = 500.0
    horn_requires_los: bool = False
    runner_speed_mps: float = 3.0
    fire_beacon_range_m: float = 10000.0
    fire_beacon_requires_los: bool = True
    fire_beacon_binary_only: bool = True
    signal_reliability: dict[int, float] = {
        SignalType.BANNER: 0.90,
        SignalType.HORN: 0.85,
        SignalType.RUNNER: 0.95,
        SignalType.FIRE_BEACON: 0.99,
    }


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@dataclass
class SignalMessage:
    """Tracks a single signal message."""

    message_id: str
    signal_type: SignalType
    sender_pos: tuple[float, float]
    receiver_pos: tuple[float, float]
    sent_time_s: float
    received_time_s: float | None = None
    received: bool = False
    content_fidelity: float = 1.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class VisualSignalEngine:
    """Manages ancient visual/audible C2 signals.

    Parameters
    ----------
    config:
        Signal configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: VisualSignalConfig | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or VisualSignalConfig()
        self._rng = rng or np.random.default_rng(42)
        self._pending: dict[str, SignalMessage] = {}
        self._delivered: list[SignalMessage] = []
        self._msg_counter: int = 0

    def _distance(
        self,
        pos_a: tuple[float, float],
        pos_b: tuple[float, float],
    ) -> float:
        """Euclidean distance between two positions."""
        return math.sqrt(
            (pos_b[0] - pos_a[0]) ** 2 + (pos_b[1] - pos_a[1]) ** 2,
        )

    def _get_range(self, signal_type: SignalType) -> float:
        """Return maximum range for a signal type."""
        cfg = self._config
        if signal_type == SignalType.BANNER:
            return cfg.banner_range_m
        elif signal_type == SignalType.HORN:
            return cfg.horn_range_m
        elif signal_type == SignalType.RUNNER:
            return float("inf")  # runner range limited by time, not distance
        elif signal_type == SignalType.FIRE_BEACON:
            return cfg.fire_beacon_range_m
        return 0.0  # pragma: no cover

    def _requires_los(self, signal_type: SignalType) -> bool:
        """Check if a signal type requires line of sight."""
        cfg = self._config
        if signal_type == SignalType.BANNER:
            return cfg.banner_requires_los
        elif signal_type == SignalType.FIRE_BEACON:
            return cfg.fire_beacon_requires_los
        return False

    def _get_fidelity(self, signal_type: SignalType) -> float:
        """Return content fidelity for a signal type."""
        if signal_type == SignalType.RUNNER:
            return 1.0  # verbal message, full content
        elif signal_type == SignalType.BANNER:
            return 0.7  # visual interpretation
        elif signal_type == SignalType.HORN:
            return 0.5  # limited signal vocabulary
        elif signal_type == SignalType.FIRE_BEACON:
            return 0.0  # binary only (lit/unlit)
        return 0.5  # pragma: no cover

    def check_range(self, signal_type: SignalType, distance_m: float) -> bool:
        """Check if a signal can reach the given distance."""
        return distance_m <= self._get_range(signal_type)

    def send_signal(
        self,
        signal_type: SignalType,
        sender_pos: tuple[float, float],
        receiver_pos: tuple[float, float],
        has_los: bool = True,
        sim_time_s: float = 0.0,
    ) -> SignalMessage | None:
        """Send a signal from sender to receiver.

        Parameters
        ----------
        signal_type:
            Type of signal.
        sender_pos:
            Sender position (easting, northing).
        receiver_pos:
            Receiver position (easting, northing).
        has_los:
            Whether line of sight exists between sender and receiver.
        sim_time_s:
            Current simulation time.

        Returns
        -------
        The signal message, or None if signal fails (out of range, no LOS).
        """
        cfg = self._config
        distance = self._distance(sender_pos, receiver_pos)

        # Range check
        max_range = self._get_range(signal_type)
        if distance > max_range and signal_type != SignalType.RUNNER:
            return None

        # LOS check
        if self._requires_los(signal_type) and not has_los:
            return None

        # Reliability check
        reliability = cfg.signal_reliability.get(int(signal_type), 0.9)
        if self._rng.random() >= reliability:
            return None

        self._msg_counter += 1
        msg_id = f"sig_{self._msg_counter}"

        # Compute delivery time
        if signal_type == SignalType.RUNNER:
            travel_time = distance / cfg.runner_speed_mps if cfg.runner_speed_mps > 0 else float("inf")
            received_time: float | None = sim_time_s + travel_time
        else:
            # Instant signals (banner, horn, fire beacon)
            received_time = sim_time_s

        fidelity = self._get_fidelity(signal_type)

        msg = SignalMessage(
            message_id=msg_id,
            signal_type=signal_type,
            sender_pos=sender_pos,
            receiver_pos=receiver_pos,
            sent_time_s=sim_time_s,
            received_time_s=received_time,
            received=signal_type != SignalType.RUNNER,  # instant signals received immediately
            content_fidelity=fidelity,
        )

        if signal_type == SignalType.RUNNER:
            self._pending[msg_id] = msg
        else:
            self._delivered.append(msg)

        return msg

    def update(self, dt_s: float, sim_time_s: float) -> list[SignalMessage]:
        """Check for delivered runner messages at current sim time.

        Returns list of messages delivered this tick.
        """
        delivered: list[SignalMessage] = []
        completed_ids: list[str] = []

        for msg_id, msg in self._pending.items():
            if msg.received_time_s is not None and sim_time_s >= msg.received_time_s:
                msg.received = True
                delivered.append(msg)
                self._delivered.append(msg)
                completed_ids.append(msg_id)

        for msg_id in completed_ids:
            del self._pending[msg_id]

        return delivered

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        def _msg_dict(msg: SignalMessage) -> dict[str, Any]:
            return {
                "message_id": msg.message_id,
                "signal_type": int(msg.signal_type),
                "sender_pos": list(msg.sender_pos),
                "receiver_pos": list(msg.receiver_pos),
                "sent_time_s": msg.sent_time_s,
                "received_time_s": msg.received_time_s,
                "received": msg.received,
                "content_fidelity": msg.content_fidelity,
            }

        return {
            "pending": {mid: _msg_dict(m) for mid, m in self._pending.items()},
            "msg_counter": self._msg_counter,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._msg_counter = state.get("msg_counter", 0)
        self._pending.clear()
        self._delivered.clear()
        for mid, mdata in state.get("pending", {}).items():
            self._pending[mid] = SignalMessage(
                message_id=mdata["message_id"],
                signal_type=SignalType(mdata["signal_type"]),
                sender_pos=tuple(mdata["sender_pos"]),
                receiver_pos=tuple(mdata["receiver_pos"]),
                sent_time_s=mdata["sent_time_s"],
                received_time_s=mdata["received_time_s"],
                received=mdata["received"],
                content_fidelity=mdata["content_fidelity"],
            )
