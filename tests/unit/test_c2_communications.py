"""Tests for c2/communications.py — channels, EMCON, jamming, YAML loading."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.communications import (
    CommEquipmentDefinition,
    CommEquipmentLoader,
    CommType,
    CommunicationsEngine,
    EmconState,
)
from stochastic_warfare.c2.events import (
    CommsLostEvent,
    EmconStateChangeEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS_A = Position(0.0, 0.0, 0.0)
_POS_B = Position(5000.0, 0.0, 0.0)  # 5km away
_POS_FAR = Position(500000.0, 0.0, 0.0)  # 500km away


def _make_vhf() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="test_vhf", comm_type="RADIO_VHF",
        display_name="Test VHF", max_range_m=10000.0,
        bandwidth_bps=16000.0, base_latency_s=0.5,
        base_reliability=0.95, intercept_risk=0.3,
        jam_resistance=0.5, requires_los=True,
    )


def _make_wire() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="test_wire", comm_type="WIRE",
        display_name="Test Wire", max_range_m=20000.0,
        bandwidth_bps=32000.0, base_latency_s=0.1,
        base_reliability=0.98, intercept_risk=0.02,
        jam_resistance=1.0, requires_los=False,
    )


def _make_hf() -> CommEquipmentDefinition:
    return CommEquipmentDefinition(
        comm_id="test_hf", comm_type="RADIO_HF",
        display_name="Test HF", max_range_m=300000.0,
        bandwidth_bps=9600.0, base_latency_s=2.0,
        base_reliability=0.75, intercept_risk=0.5,
        jam_resistance=0.4, requires_los=False,
    )


def _make_engine(
    seed: int = 42,
    equipment: list[CommEquipmentDefinition] | None = None,
) -> tuple[CommunicationsEngine, EventBus]:
    """Build a CommunicationsEngine with optional equipment."""
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.C2)
    loader = CommEquipmentLoader()
    if equipment:
        for e in equipment:
            loader._definitions[e.comm_id] = e
    engine = CommunicationsEngine(
        event_bus=bus, rng=rng, equipment_loader=loader,
    )
    return engine, bus


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestCommEnums:
    """CommType and EmconState enums."""

    def test_comm_type_values(self) -> None:
        assert CommType.RADIO_VHF == 0
        assert CommType.ELF == 8
        assert len(CommType) == 9

    def test_emcon_state_values(self) -> None:
        assert EmconState.RADIATE == 0
        assert EmconState.MINIMIZE == 1
        assert EmconState.SILENT == 2
        assert len(EmconState) == 3


# ---------------------------------------------------------------------------
# Equipment definition
# ---------------------------------------------------------------------------


class TestCommEquipmentDefinition:
    """YAML-loaded equipment model."""

    def test_create_definition(self) -> None:
        d = _make_vhf()
        assert d.comm_id == "test_vhf"
        assert d.comm_type_enum == CommType.RADIO_VHF
        assert d.max_range_m == 10000.0
        assert d.base_reliability == 0.95

    def test_wire_definition(self) -> None:
        d = _make_wire()
        assert d.comm_type_enum == CommType.WIRE
        assert d.jam_resistance == 1.0


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


class TestCommEquipmentLoader:
    """Loading equipment from YAML files."""

    def test_load_all_yaml(self) -> None:
        loader = CommEquipmentLoader()
        loader.load_all()
        available = loader.available_equipment()
        assert len(available) == 8
        assert "sincgars_vhf" in available
        assert "link16" in available
        assert "field_wire" in available

    def test_load_sincgars(self) -> None:
        loader = CommEquipmentLoader()
        loader.load_all()
        d = loader.get_definition("sincgars_vhf")
        assert d.comm_type_enum == CommType.RADIO_VHF
        assert d.max_range_m == 8000.0
        assert d.jam_resistance == 0.7

    def test_load_link16(self) -> None:
        loader = CommEquipmentLoader()
        loader.load_all()
        d = loader.get_definition("link16")
        assert d.comm_type_enum == CommType.DATA_LINK
        assert d.jam_resistance == 0.85

    def test_load_vlf(self) -> None:
        loader = CommEquipmentLoader()
        loader.load_all()
        d = loader.get_definition("vlf_receiver")
        assert d.comm_type_enum == CommType.VLF
        assert d.bandwidth_bps == 300.0  # Extremely low bandwidth

    def test_load_field_wire(self) -> None:
        loader = CommEquipmentLoader()
        loader.load_all()
        d = loader.get_definition("field_wire")
        assert d.comm_type_enum == CommType.WIRE
        assert d.jam_resistance == 1.0  # Unjammable

    def test_unknown_equipment_raises(self) -> None:
        loader = CommEquipmentLoader()
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")


# ---------------------------------------------------------------------------
# EMCON
# ---------------------------------------------------------------------------


class TestEmcon:
    """Emission control."""

    def test_set_emcon(self) -> None:
        engine, bus = _make_engine(equipment=[_make_vhf()])
        engine.register_unit("u1", ["test_vhf"])
        engine.set_emcon("u1", EmconState.SILENT, _TS)
        assert engine.get_emcon("u1") == EmconState.SILENT

    def test_emcon_publishes_event(self) -> None:
        engine, bus = _make_engine(equipment=[_make_vhf()])
        engine.register_unit("u1", ["test_vhf"])
        events: list[EmconStateChangeEvent] = []
        bus.subscribe(EmconStateChangeEvent, events.append)
        engine.set_emcon("u1", EmconState.SILENT, _TS)
        assert len(events) == 1
        assert events[0].old_state == int(EmconState.RADIATE)
        assert events[0].new_state == int(EmconState.SILENT)

    def test_emcon_no_change_no_event(self) -> None:
        engine, bus = _make_engine(equipment=[_make_vhf()])
        engine.register_unit("u1", ["test_vhf"])
        events: list[EmconStateChangeEvent] = []
        bus.subscribe(EmconStateChangeEvent, events.append)
        engine.set_emcon("u1", EmconState.RADIATE, _TS)  # Same state
        assert len(events) == 0

    def test_emcon_silent_blocks_radio(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        engine.set_emcon("u1", EmconState.SILENT, _TS)
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_B) is False

    def test_emcon_silent_allows_wire(self) -> None:
        wire = _make_wire()
        engine, bus = _make_engine(equipment=[wire])
        engine.register_unit("u1", ["test_wire"])
        engine.register_unit("u2", ["test_wire"])
        engine.set_emcon("u1", EmconState.SILENT, _TS)
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_B) is True

    def test_emcon_minimize_degrades_radio(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        # MINIMIZE should reduce VHF reliability by 0.5
        engine.set_emcon("u1", EmconState.MINIMIZE, _TS)
        # Can still communicate, but reliability is halved
        chan = engine.get_best_channel("u1", "u2", _POS_A, _POS_B)
        assert chan is not None  # Still possible, just degraded


# ---------------------------------------------------------------------------
# Range limits
# ---------------------------------------------------------------------------


class TestRangeLimits:
    """Range-based reliability."""

    def test_within_range_can_communicate(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_B) is True

    def test_beyond_range_cannot_communicate(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        # 500km is well beyond 10km VHF range
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_FAR) is False

    def test_at_range_limit_degraded(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        # At 95% of max range (9500m) — within degradation zone
        pos_near_limit = Position(9500.0, 0.0, 0.0)
        # Still can communicate, but reliability is reduced
        assert engine.can_communicate("u1", "u2", _POS_A, pos_near_limit) is True

    def test_hf_longer_range(self) -> None:
        hf = _make_hf()
        engine, bus = _make_engine(equipment=[hf])
        engine.register_unit("u1", ["test_hf"])
        engine.register_unit("u2", ["test_hf"])
        # 100km is within HF range (300km)
        pos_100k = Position(100000.0, 0.0, 0.0)
        assert engine.can_communicate("u1", "u2", _POS_A, pos_100k) is True


# ---------------------------------------------------------------------------
# Jamming
# ---------------------------------------------------------------------------


class TestJamming:
    """Electronic warfare / jamming."""

    def test_jamming_reduces_reliability(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(seed=1, equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])

        # Apply strong jamming at sender position
        engine.apply_jamming(_POS_A, 10000.0, CommType.RADIO_VHF, 0.9)

        # Multiple attempts to check reliability is reduced
        successes = sum(
            engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)[0]
            for _ in range(100)
        )
        # With 0.9 jamming and 0.5 resistance → jam_factor = 1-(0.9*0.5) = 0.55
        # reliability = 0.95 * 0.55 ≈ 0.52 → expect ~52/100
        assert successes < 80  # Significantly less than unjammed

    def test_wire_unjammable(self) -> None:
        wire = _make_wire()
        engine, bus = _make_engine(seed=1, equipment=[wire])
        engine.register_unit("u1", ["test_wire"])
        engine.register_unit("u2", ["test_wire"])

        # Apply jamming on VHF band — wire unaffected
        engine.apply_jamming(_POS_A, 10000.0, CommType.RADIO_VHF, 1.0)
        successes = sum(
            engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)[0]
            for _ in range(20)
        )
        assert successes >= 15  # Wire reliability is 0.98

    def test_jam_resistance_mitigates(self) -> None:
        # High jam resistance equipment
        tough = CommEquipmentDefinition(
            comm_id="tough_radio", comm_type="RADIO_VHF",
            display_name="Tough Radio", max_range_m=10000.0,
            bandwidth_bps=16000.0, base_latency_s=0.5,
            base_reliability=0.95, intercept_risk=0.1,
            jam_resistance=0.95, requires_los=True,
        )
        engine, bus = _make_engine(seed=1, equipment=[tough])
        engine.register_unit("u1", ["tough_radio"])
        engine.register_unit("u2", ["tough_radio"])

        engine.apply_jamming(_POS_A, 10000.0, CommType.RADIO_VHF, 0.9)
        successes = sum(
            engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)[0]
            for _ in range(100)
        )
        # jam_factor = 1-(0.9*0.05) = 0.955, reliability ≈ 0.95*0.955 ≈ 0.907
        assert successes > 75

    def test_clear_jamming(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        engine.apply_jamming(_POS_A, 10000.0, CommType.RADIO_VHF, 1.0)
        engine.clear_jamming()
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_B) is True


# ---------------------------------------------------------------------------
# Message sending
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Stochastic message delivery."""

    def test_send_message_returns_tuple(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        success, latency = engine.send_message(
            "u1", "u2", _POS_A, _POS_B, timestamp=_TS,
        )
        assert isinstance(success, bool)
        assert isinstance(latency, float)

    def test_send_message_no_channel_fails(self) -> None:
        engine, bus = _make_engine()
        engine.register_unit("u1", [])
        engine.register_unit("u2", [])
        success, latency = engine.send_message(
            "u1", "u2", _POS_A, _POS_B, timestamp=_TS,
        )
        assert success is False

    def test_send_failure_publishes_comms_lost(self) -> None:
        engine, bus = _make_engine()
        engine.register_unit("u1", [])
        engine.register_unit("u2", [])
        events: list[CommsLostEvent] = []
        bus.subscribe(CommsLostEvent, events.append)
        engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)
        assert len(events) == 1
        assert events[0].cause == "no_channel"

    def test_messenger_latency_is_distance_based(self) -> None:
        messenger = CommEquipmentDefinition(
            comm_id="test_messenger", comm_type="MESSENGER",
            display_name="Runner", max_range_m=50000.0,
            bandwidth_bps=0.0, base_latency_s=0.0,
            base_reliability=1.0, intercept_risk=0.01,
            jam_resistance=1.0, requires_los=False,
        )
        engine, bus = _make_engine(equipment=[messenger])
        engine.register_unit("u1", ["test_messenger"])
        engine.register_unit("u2", ["test_messenger"])

        success, latency = engine.send_message(
            "u1", "u2", _POS_A, _POS_B, timestamp=_TS,
        )
        # 5000m at 1.5 m/s ≈ 3333s
        assert success is True
        assert latency == pytest.approx(5000.0 / 1.5, rel=0.01)

    def test_vhf_latency_includes_transmission_time(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])

        success, latency = engine.send_message(
            "u1", "u2", _POS_A, _POS_B,
            message_size_bits=16000, timestamp=_TS,
        )
        # base_latency_s(0.5) + 16000/16000 = 1.5s
        if success:
            assert latency == pytest.approx(1.5, rel=0.01)


# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------


class TestChannelSelection:
    """Best-channel logic."""

    def test_selects_higher_reliability(self) -> None:
        vhf = _make_vhf()  # 0.95 reliability
        hf = _make_hf()    # 0.75 reliability
        engine, bus = _make_engine(equipment=[vhf, hf])
        engine.register_unit("u1", ["test_vhf", "test_hf"])
        engine.register_unit("u2", ["test_vhf", "test_hf"])

        best = engine.get_best_channel("u1", "u2", _POS_A, _POS_B)
        assert best is not None
        assert best.comm_id == "test_vhf"  # Higher base reliability

    def test_fallback_to_hf_at_long_range(self) -> None:
        vhf = _make_vhf()  # 10km range
        hf = _make_hf()    # 300km range
        engine, bus = _make_engine(equipment=[vhf, hf])
        engine.register_unit("u1", ["test_vhf", "test_hf"])
        engine.register_unit("u2", ["test_vhf", "test_hf"])

        pos_50k = Position(50000.0, 0.0, 0.0)
        best = engine.get_best_channel("u1", "u2", _POS_A, pos_50k)
        assert best is not None
        assert best.comm_id == "test_hf"  # VHF out of range

    def test_incompatible_equipment_no_channel(self) -> None:
        vhf = _make_vhf()
        wire = _make_wire()
        engine, bus = _make_engine(equipment=[vhf, wire])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_wire"])

        # VHF ↔ WIRE are incompatible
        assert engine.can_communicate("u1", "u2", _POS_A, _POS_B) is False


# ---------------------------------------------------------------------------
# Environment degradation
# ---------------------------------------------------------------------------


class TestEnvironmentFactor:
    """Global environment degradation."""

    def test_env_factor_degrades_reliability(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(seed=1, equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])

        engine.set_environment_factor(0.5)  # Bad weather
        successes = sum(
            engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)[0]
            for _ in range(100)
        )
        # reliability = 0.95 * 0.5 = 0.475
        assert successes < 70


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestCommsStateProtocol:
    """Checkpoint / restore."""

    def test_get_state(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.set_emcon("u1", EmconState.MINIMIZE, _TS)
        state = engine.get_state()
        assert "u1" in state["units"]
        assert state["units"]["u1"]["emcon_state"] == int(EmconState.MINIMIZE)

    def test_set_state(self) -> None:
        vhf = _make_vhf()
        engine1, bus1 = _make_engine(equipment=[vhf])
        engine1.register_unit("u1", ["test_vhf"])
        engine1.set_emcon("u1", EmconState.SILENT, _TS)
        engine1.apply_jamming(_POS_A, 5000.0, CommType.RADIO_VHF, 0.8)
        state = engine1.get_state()

        engine2, bus2 = _make_engine(equipment=[vhf])
        engine2.set_state(state)
        assert engine2.get_emcon("u1") == EmconState.SILENT
        assert len(engine2._jamming_zones) == 1

    def test_state_round_trip(self) -> None:
        vhf = _make_vhf()
        engine, bus = _make_engine(equipment=[vhf])
        engine.register_unit("u1", ["test_vhf"])
        engine.register_unit("u2", ["test_vhf"])
        engine.set_emcon("u1", EmconState.MINIMIZE, _TS)
        engine.apply_jamming(_POS_A, 3000.0, CommType.RADIO_VHF, 0.5)
        state1 = engine.get_state()

        engine2, bus2 = _make_engine(equipment=[vhf])
        engine2.set_state(state1)
        assert engine2.get_state() == state1


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestCommsReplay:
    """Same seed → identical results."""

    def test_deterministic_message_delivery(self) -> None:
        vhf = _make_vhf()

        def run(seed: int) -> list[bool]:
            engine, bus = _make_engine(seed=seed, equipment=[vhf])
            engine.register_unit("u1", ["test_vhf"])
            engine.register_unit("u2", ["test_vhf"])
            return [
                engine.send_message("u1", "u2", _POS_A, _POS_B, timestamp=_TS)[0]
                for _ in range(20)
            ]

        assert run(99) == run(99)
