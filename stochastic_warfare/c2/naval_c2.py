"""Naval C2 engine — task force hierarchy, data links, submarine comms.

Models the US Navy's task-force organizational structure (TF/TG/TU/TE),
tactical data links (Link 11, Link 16), and submarine communication
constraints (VLF/ELF one-way, SATCOM at periscope depth only).

Flagship loss triggers flag transfer to the next senior unit in the
formation, with a delay during which the formation operates degraded.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.communications import (
    CommType,
    CommunicationsEngine,
)
from stochastic_warfare.c2.events import CommandStatusChangeEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NavalFormationType(enum.IntEnum):
    """Task organization echelons (naval)."""

    TASK_FORCE = 0
    TASK_GROUP = 1
    TASK_UNIT = 2
    TASK_ELEMENT = 3


class NavalDataLinkType(enum.IntEnum):
    """Tactical data link types."""

    LINK_11 = 0
    LINK_16 = 1


class SubCommMethod(enum.IntEnum):
    """Methods for communicating with submarines."""

    VLF = 0      # One-way (shore→sub), very low bandwidth
    ELF = 1      # One-way (shore→sub), extremely low bandwidth
    SATELLITE = 2  # Two-way, requires periscope depth
    TRAILING_WIRE = 3  # One-way receive, at depth


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NavalC2Config:
    """Configuration for naval C2 engine."""

    def __init__(
        self,
        flag_transfer_delay_s: float = 600.0,
        link16_max_participants: int = 256,
        link11_max_participants: int = 32,
        vlf_bandwidth_bps: float = 300.0,
        elf_bandwidth_bps: float = 10.0,
    ) -> None:
        self.flag_transfer_delay_s = flag_transfer_delay_s
        self.link16_max_participants = link16_max_participants
        self.link11_max_participants = link11_max_participants
        self.vlf_bandwidth_bps = vlf_bandwidth_bps
        self.elf_bandwidth_bps = elf_bandwidth_bps


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class NavalFormation:
    """A task force / group / unit / element."""

    formation_id: str
    formation_type: NavalFormationType
    flagship_id: str
    member_ids: list[str]
    parent_formation_id: str | None = None


@dataclass
class DataLinkNetwork:
    """A tactical data link network."""

    network_id: str
    link_type: NavalDataLinkType
    participant_ids: list[str]
    shared_contacts: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NavalC2Engine:
    """Manages naval task force C2, data links, and submarine communications.

    Parameters
    ----------
    comms_engine : CommunicationsEngine
        Underlying communications layer.
    event_bus : EventBus
        For publishing C2 events.
    rng : numpy.random.Generator
        Deterministic PRNG.
    config : NavalC2Config | None
        Tuning parameters.
    """

    def __init__(
        self,
        comms_engine: CommunicationsEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalC2Config | None = None,
    ) -> None:
        self._comms = comms_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalC2Config()
        self._formations: dict[str, NavalFormation] = {}
        self._data_links: dict[str, DataLinkNetwork] = {}
        self._sub_capabilities: dict[str, set[SubCommMethod]] = {}
        self._sub_at_periscope_depth: set[str] = set()
        self._flag_transfer_timers: dict[str, float] = {}

    # -- Formation management -----------------------------------------------

    def create_formation(
        self,
        formation_id: str,
        formation_type: NavalFormationType,
        flagship_id: str,
        member_ids: list[str],
        parent_formation_id: str | None = None,
    ) -> NavalFormation:
        """Create a new naval formation."""
        formation = NavalFormation(
            formation_id=formation_id,
            formation_type=formation_type,
            flagship_id=flagship_id,
            member_ids=list(member_ids),
            parent_formation_id=parent_formation_id,
        )
        self._formations[formation_id] = formation
        return formation

    def get_formation(self, formation_id: str) -> NavalFormation:
        """Return a formation by ID."""
        return self._formations[formation_id]

    def get_flagship(self, formation_id: str) -> str:
        """Return the flagship unit_id for a formation."""
        return self._formations[formation_id].flagship_id

    # -- Data links ---------------------------------------------------------

    def establish_data_link(
        self,
        network_id: str,
        link_type: NavalDataLinkType,
        participant_ids: list[str],
    ) -> DataLinkNetwork:
        """Establish a tactical data link network."""
        max_participants = (
            self._config.link16_max_participants
            if link_type == NavalDataLinkType.LINK_16
            else self._config.link11_max_participants
        )
        if len(participant_ids) > max_participants:
            raise ValueError(
                f"Data link {link_type.name} supports max {max_participants} "
                f"participants, got {len(participant_ids)}"
            )
        network = DataLinkNetwork(
            network_id=network_id,
            link_type=link_type,
            participant_ids=list(participant_ids),
        )
        self._data_links[network_id] = network
        return network

    def share_contact(
        self,
        network_id: str,
        contact_id: str,
        contact_data: dict,
    ) -> None:
        """Share a contact on a data link network."""
        network = self._data_links[network_id]
        network.shared_contacts[contact_id] = contact_data

    def get_shared_picture(self, network_id: str) -> dict[str, dict]:
        """Return all shared contacts on a data link network."""
        return dict(self._data_links[network_id].shared_contacts)

    def get_link_participants(self, network_id: str) -> list[str]:
        """Return participant unit_ids for a data link network."""
        return list(self._data_links[network_id].participant_ids)

    # -- Submarine comms ----------------------------------------------------

    def register_submarine(
        self,
        sub_id: str,
        capabilities: list[SubCommMethod],
    ) -> None:
        """Register a submarine with its communication capabilities."""
        self._sub_capabilities[sub_id] = set(capabilities)

    def set_periscope_depth(self, sub_id: str, at_periscope: bool) -> None:
        """Update whether a submarine is at periscope depth."""
        if at_periscope:
            self._sub_at_periscope_depth.add(sub_id)
        else:
            self._sub_at_periscope_depth.discard(sub_id)

    def can_contact_submarine(
        self,
        sub_id: str,
        method: SubCommMethod,
    ) -> bool:
        """Check if a submarine can be contacted via the given method."""
        if sub_id not in self._sub_capabilities:
            return False
        if method not in self._sub_capabilities[sub_id]:
            return False
        if method == SubCommMethod.SATELLITE:
            return sub_id in self._sub_at_periscope_depth
        # VLF, ELF, TRAILING_WIRE: always available (one-way to sub)
        return True

    def send_to_submarine(
        self,
        sub_id: str,
        method: SubCommMethod,
        message_size_bits: int = 100,
    ) -> tuple[bool, float]:
        """Send a message to a submarine. Returns (success, latency_s).

        VLF/ELF/TRAILING_WIRE are one-way (shore→sub).
        SATELLITE is two-way but requires periscope depth.
        """
        if not self.can_contact_submarine(sub_id, method):
            return False, 0.0

        if method in (SubCommMethod.VLF, SubCommMethod.TRAILING_WIRE):
            latency = message_size_bits / self._config.vlf_bandwidth_bps
            # VLF reliability is inherently high but slow
            success = bool(self._rng.random() < 0.85)
            return success, latency
        elif method == SubCommMethod.ELF:
            latency = message_size_bits / self._config.elf_bandwidth_bps
            success = bool(self._rng.random() < 0.80)
            return success, latency
        elif method == SubCommMethod.SATELLITE:
            latency = 0.5 + message_size_bits / 64000.0
            success = bool(self._rng.random() < 0.90)
            return success, latency

        return False, 0.0

    # -- Flagship loss ------------------------------------------------------

    def handle_flagship_loss(
        self,
        formation_id: str,
        timestamp: datetime,
    ) -> None:
        """Handle loss of the flagship — flag transfers to next senior unit."""
        formation = self._formations[formation_id]
        old_flagship = formation.flagship_id

        # Find next ship in member list (proxy for seniority)
        candidates = [
            m for m in formation.member_ids if m != old_flagship
        ]
        if not candidates:
            logger.warning("No ships to receive flag for %s", formation_id)
            return

        new_flagship = candidates[0]
        formation.flagship_id = new_flagship
        self._flag_transfer_timers[formation_id] = self._config.flag_transfer_delay_s

        self._event_bus.publish(CommandStatusChangeEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=formation_id,
            old_status=0, new_status=1,  # FULLY_OP → DEGRADED
            cause="flagship_loss",
        ))
        logger.info(
            "Flag transfer %s: %s → %s (delay %.0fs)",
            formation_id, old_flagship, new_flagship,
            self._config.flag_transfer_delay_s,
        )

    # -- Update -------------------------------------------------------------

    def update(self, dt_seconds: float, timestamp: datetime) -> None:
        """Advance flag transfer timers."""
        completed = []
        for fid, timer in self._flag_transfer_timers.items():
            timer -= dt_seconds
            self._flag_transfer_timers[fid] = timer
            if timer <= 0:
                completed.append(fid)
                self._event_bus.publish(CommandStatusChangeEvent(
                    timestamp=timestamp, source=ModuleId.C2,
                    unit_id=fid,
                    old_status=1, new_status=0,  # DEGRADED → FULLY_OP
                    cause="recovery",
                ))
        for fid in completed:
            del self._flag_transfer_timers[fid]

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "formations": {
                fid: {
                    "formation_id": f.formation_id,
                    "formation_type": int(f.formation_type),
                    "flagship_id": f.flagship_id,
                    "member_ids": list(f.member_ids),
                    "parent_formation_id": f.parent_formation_id,
                }
                for fid, f in self._formations.items()
            },
            "data_links": {
                nid: {
                    "network_id": n.network_id,
                    "link_type": int(n.link_type),
                    "participant_ids": list(n.participant_ids),
                    "shared_contacts": dict(n.shared_contacts),
                }
                for nid, n in self._data_links.items()
            },
            "sub_capabilities": {
                sid: sorted(int(m) for m in methods)
                for sid, methods in self._sub_capabilities.items()
            },
            "sub_at_periscope_depth": sorted(self._sub_at_periscope_depth),
            "flag_transfer_timers": dict(self._flag_transfer_timers),
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._formations.clear()
        for fid, fd in state["formations"].items():
            self._formations[fid] = NavalFormation(
                formation_id=fd["formation_id"],
                formation_type=NavalFormationType(fd["formation_type"]),
                flagship_id=fd["flagship_id"],
                member_ids=fd["member_ids"],
                parent_formation_id=fd["parent_formation_id"],
            )
        self._data_links.clear()
        for nid, nd in state["data_links"].items():
            self._data_links[nid] = DataLinkNetwork(
                network_id=nd["network_id"],
                link_type=NavalDataLinkType(nd["link_type"]),
                participant_ids=nd["participant_ids"],
                shared_contacts=nd["shared_contacts"],
            )
        self._sub_capabilities = {
            sid: {SubCommMethod(m) for m in methods}
            for sid, methods in state["sub_capabilities"].items()
        }
        self._sub_at_periscope_depth = set(state["sub_at_periscope_depth"])
        self._flag_transfer_timers = dict(state["flag_transfer_timers"])
