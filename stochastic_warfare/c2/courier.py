"""Napoleonic courier C2 — physical messengers with interception risk.

Overlays the existing ``MESSENGER`` :class:`CommType`.  Adds interception
risk, courier pool limits, terrain-dependent travel time, and ADC system.
``c2_delay_multiplier=8.0`` (no telephone at all).
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


class CourierType(enum.IntEnum):
    """Type of courier/messenger."""

    MOUNTED_ADC = 0
    GALLOPER = 1
    FOOT_MESSENGER = 2
    DRUM_BUGLE = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CourierConfig(BaseModel):
    """Configuration for Napoleonic courier system."""

    speeds_by_terrain: dict[int, dict[str, float]] = {
        CourierType.MOUNTED_ADC: {"road": 8.0, "open": 5.0, "rough": 3.0},
        CourierType.GALLOPER: {"road": 7.0, "open": 4.0, "rough": 2.5},
        CourierType.FOOT_MESSENGER: {"road": 2.0, "open": 1.5, "rough": 1.0},
        CourierType.DRUM_BUGLE: {"road": 0.0, "open": 0.0, "rough": 0.0},
    }

    interception_risk_per_km: dict[int, float] = {
        CourierType.MOUNTED_ADC: 0.02,
        CourierType.GALLOPER: 0.03,
        CourierType.FOOT_MESSENGER: 0.05,
        CourierType.DRUM_BUGLE: 0.0,
    }

    drum_bugle_range_m: float = 300.0
    max_couriers_per_hq: int = 4


# ---------------------------------------------------------------------------
# Message state
# ---------------------------------------------------------------------------


@dataclass
class CourierMessage:
    """Tracks a single courier message in transit."""

    message_id: str
    courier_type: CourierType
    from_pos: tuple[float, float]
    to_pos: tuple[float, float]
    depart_time_s: float
    arrival_time_s: float
    intercepted: bool = False
    delivered: bool = False
    hq_id: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CourierEngine:
    """Manages Napoleonic courier dispatch and delivery.

    Parameters
    ----------
    config:
        Courier configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: CourierConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or CourierConfig()
        self._rng = rng
        self._messages: dict[str, CourierMessage] = {}
        self._active_couriers_by_hq: dict[str, int] = {}

    def compute_travel_time(
        self,
        distance_m: float,
        courier_type: CourierType,
        terrain_type: str = "open",
    ) -> float:
        """Compute travel time in seconds for a courier.

        Parameters
        ----------
        distance_m:
            Straight-line distance in metres.
        courier_type:
            Type of courier.
        terrain_type:
            Terrain category (``"road"``, ``"open"``, ``"rough"``).

        Returns
        -------
        Travel time in seconds, or ``float('inf')`` for drum/bugle
        beyond range.
        """
        cfg = self._config

        # Drum/bugle: instantaneous but range-limited
        if courier_type == CourierType.DRUM_BUGLE:
            if distance_m <= cfg.drum_bugle_range_m:
                return 2.0  # signal propagation time
            return float("inf")

        speeds = cfg.speeds_by_terrain.get(int(courier_type), {})
        speed = speeds.get(terrain_type, speeds.get("open", 1.0))
        if speed <= 0:
            return float("inf")
        return distance_m / speed

    def dispatch_courier(
        self,
        message_id: str,
        courier_type: CourierType,
        from_pos: tuple[float, float],
        to_pos: tuple[float, float],
        terrain_type: str = "open",
        enemy_km: float = 0.0,
        sim_time_s: float = 0.0,
        hq_id: str = "",
    ) -> CourierMessage | None:
        """Dispatch a courier with a message.

        Parameters
        ----------
        enemy_km:
            Kilometres of route passing through enemy-controlled territory.

        Returns
        -------
        The :class:`CourierMessage`, or ``None`` if no courier available.
        """
        cfg = self._config

        # Check courier pool
        if hq_id:
            active = self._active_couriers_by_hq.get(hq_id, 0)
            if active >= cfg.max_couriers_per_hq:
                logger.warning(
                    "No couriers available at HQ %s (%d/%d)",
                    hq_id, active, cfg.max_couriers_per_hq,
                )
                return None

        distance_m = math.sqrt(
            (to_pos[0] - from_pos[0]) ** 2 + (to_pos[1] - from_pos[1]) ** 2,
        )
        travel_time = self.compute_travel_time(distance_m, courier_type, terrain_type)

        # Interception check
        risk_per_km = cfg.interception_risk_per_km.get(int(courier_type), 0.0)
        p_intercept = 1.0 - (1.0 - risk_per_km) ** enemy_km if enemy_km > 0 else 0.0
        intercepted = bool(self._rng.random() < p_intercept)

        msg = CourierMessage(
            message_id=message_id,
            courier_type=courier_type,
            from_pos=from_pos,
            to_pos=to_pos,
            depart_time_s=sim_time_s,
            arrival_time_s=sim_time_s + travel_time,
            intercepted=intercepted,
            hq_id=hq_id,
        )
        self._messages[message_id] = msg

        if hq_id:
            self._active_couriers_by_hq[hq_id] = (
                self._active_couriers_by_hq.get(hq_id, 0) + 1
            )

        logger.info(
            "Dispatched %s courier %s: %.0fm, ETA %.0fs%s",
            CourierType(courier_type).name, message_id,
            distance_m, travel_time,
            " (INTERCEPTED)" if intercepted else "",
        )
        return msg

    def update(self, sim_time_s: float) -> list[CourierMessage]:
        """Check for delivered messages at current sim time.

        Returns list of messages delivered this tick.
        """
        delivered: list[CourierMessage] = []
        for msg in self._messages.values():
            if msg.delivered or msg.intercepted:
                continue
            if sim_time_s >= msg.arrival_time_s:
                msg.delivered = True
                delivered.append(msg)
                # Free courier back to pool
                if msg.hq_id:
                    self._active_couriers_by_hq[msg.hq_id] = max(
                        0,
                        self._active_couriers_by_hq.get(msg.hq_id, 1) - 1,
                    )
        return delivered

    def available_couriers(self, hq_id: str) -> int:
        """Return number of available couriers at an HQ."""
        active = self._active_couriers_by_hq.get(hq_id, 0)
        return max(0, self._config.max_couriers_per_hq - active)

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "messages": {
                mid: {
                    "message_id": m.message_id,
                    "courier_type": int(m.courier_type),
                    "from_pos": list(m.from_pos),
                    "to_pos": list(m.to_pos),
                    "depart_time_s": m.depart_time_s,
                    "arrival_time_s": m.arrival_time_s,
                    "intercepted": m.intercepted,
                    "delivered": m.delivered,
                    "hq_id": m.hq_id,
                }
                for mid, m in self._messages.items()
            },
            "active_couriers_by_hq": dict(self._active_couriers_by_hq),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._messages.clear()
        for mid, mdata in state.get("messages", {}).items():
            self._messages[mid] = CourierMessage(
                message_id=mdata["message_id"],
                courier_type=CourierType(mdata["courier_type"]),
                from_pos=tuple(mdata["from_pos"]),
                to_pos=tuple(mdata["to_pos"]),
                depart_time_s=mdata["depart_time_s"],
                arrival_time_s=mdata["arrival_time_s"],
                intercepted=mdata["intercepted"],
                delivered=mdata["delivered"],
                hq_id=mdata.get("hq_id", ""),
            )
        self._active_couriers_by_hq = dict(
            state.get("active_couriers_by_hq", {}),
        )
