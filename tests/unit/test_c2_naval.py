"""Tests for c2/naval_c2.py — task force hierarchy, data links, submarine comms."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.communications import (
    CommEquipmentLoader,
    CommunicationsEngine,
)
from stochastic_warfare.c2.events import CommandStatusChangeEvent
from stochastic_warfare.c2.naval_c2 import (
    NavalC2Config,
    NavalC2Engine,
    NavalDataLinkType,
    NavalFormationType,
    SubCommMethod,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_engine(seed: int = 42) -> tuple[NavalC2Engine, EventBus]:
    bus = EventBus()
    rng_mgr = RNGManager(seed)
    comms_rng = rng_mgr.get_stream(ModuleId.C2)
    naval_rng = rng_mgr.get_stream(ModuleId.ENTITIES)  # Use different stream
    comms = CommunicationsEngine(
        event_bus=bus, rng=comms_rng, equipment_loader=CommEquipmentLoader(),
    )
    engine = NavalC2Engine(comms_engine=comms, event_bus=bus, rng=naval_rng)
    return engine, bus


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestNavalEnums:
    """Naval C2 enums."""

    def test_formation_type_values(self) -> None:
        assert NavalFormationType.TASK_FORCE == 0
        assert NavalFormationType.TASK_ELEMENT == 3
        assert len(NavalFormationType) == 4

    def test_data_link_type_values(self) -> None:
        assert NavalDataLinkType.LINK_11 == 0
        assert NavalDataLinkType.LINK_16 == 1

    def test_sub_comm_method_values(self) -> None:
        assert SubCommMethod.VLF == 0
        assert SubCommMethod.TRAILING_WIRE == 3
        assert len(SubCommMethod) == 4


# ---------------------------------------------------------------------------
# Formation management
# ---------------------------------------------------------------------------


class TestFormations:
    """Naval task force hierarchy."""

    def test_create_task_force(self) -> None:
        engine, bus = _make_engine()
        tf = engine.create_formation(
            "tf_alpha", NavalFormationType.TASK_FORCE,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2", "cg1"],
        )
        assert tf.formation_id == "tf_alpha"
        assert tf.flagship_id == "ddg1"
        assert len(tf.member_ids) == 3

    def test_nested_formations(self) -> None:
        engine, bus = _make_engine()
        tf = engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="cv1", member_ids=["cv1", "cg1"],
        )
        tg = engine.create_formation(
            "tg1", NavalFormationType.TASK_GROUP,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2"],
            parent_formation_id="tf1",
        )
        tu = engine.create_formation(
            "tu1", NavalFormationType.TASK_UNIT,
            flagship_id="ffg1", member_ids=["ffg1"],
            parent_formation_id="tg1",
        )
        assert tg.parent_formation_id == "tf1"
        assert tu.parent_formation_id == "tg1"

    def test_get_flagship(self) -> None:
        engine, bus = _make_engine()
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="cv1", member_ids=["cv1", "cg1"],
        )
        assert engine.get_flagship("tf1") == "cv1"


# ---------------------------------------------------------------------------
# Data links
# ---------------------------------------------------------------------------


class TestDataLinks:
    """Tactical data link networks."""

    def test_establish_link16(self) -> None:
        engine, bus = _make_engine()
        net = engine.establish_data_link(
            "alpha_net", NavalDataLinkType.LINK_16,
            participant_ids=["ddg1", "ddg2", "cg1"],
        )
        assert net.network_id == "alpha_net"
        assert len(net.participant_ids) == 3

    def test_share_contact_on_link(self) -> None:
        engine, bus = _make_engine()
        engine.establish_data_link(
            "net1", NavalDataLinkType.LINK_16,
            participant_ids=["ddg1", "ddg2"],
        )
        engine.share_contact("net1", "contact_001", {
            "position": [1000, 2000], "type": "surface",
        })
        picture = engine.get_shared_picture("net1")
        assert "contact_001" in picture
        assert picture["contact_001"]["type"] == "surface"

    def test_link16_participant_limit(self) -> None:
        engine, bus = _make_engine()
        config = NavalC2Config(link16_max_participants=5)
        engine._config = config
        with pytest.raises(ValueError, match="max 5"):
            engine.establish_data_link(
                "net1", NavalDataLinkType.LINK_16,
                participant_ids=[f"ship{i}" for i in range(10)],
            )

    def test_link11_participant_limit(self) -> None:
        engine, bus = _make_engine()
        config = NavalC2Config(link11_max_participants=3)
        engine._config = config
        with pytest.raises(ValueError, match="max 3"):
            engine.establish_data_link(
                "net1", NavalDataLinkType.LINK_11,
                participant_ids=[f"ship{i}" for i in range(5)],
            )

    def test_get_link_participants(self) -> None:
        engine, bus = _make_engine()
        engine.establish_data_link(
            "net1", NavalDataLinkType.LINK_16,
            participant_ids=["ddg1", "cg1"],
        )
        assert engine.get_link_participants("net1") == ["ddg1", "cg1"]

    def test_multiple_contacts_shared(self) -> None:
        engine, bus = _make_engine()
        engine.establish_data_link(
            "net1", NavalDataLinkType.LINK_16,
            participant_ids=["ddg1", "ddg2"],
        )
        engine.share_contact("net1", "c1", {"type": "air"})
        engine.share_contact("net1", "c2", {"type": "sub"})
        picture = engine.get_shared_picture("net1")
        assert len(picture) == 2


# ---------------------------------------------------------------------------
# Submarine communications
# ---------------------------------------------------------------------------


class TestSubmarineComms:
    """Submarine communication constraints."""

    def test_vlf_one_way(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.VLF, SubCommMethod.SATELLITE])
        assert engine.can_contact_submarine("ssn1", SubCommMethod.VLF) is True

    def test_satellite_requires_periscope_depth(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.VLF, SubCommMethod.SATELLITE])
        # Not at periscope depth
        assert engine.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is False

    def test_satellite_at_periscope_depth(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.VLF, SubCommMethod.SATELLITE])
        engine.set_periscope_depth("ssn1", True)
        assert engine.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is True

    def test_periscope_depth_toggle(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.SATELLITE])
        engine.set_periscope_depth("ssn1", True)
        assert engine.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is True
        engine.set_periscope_depth("ssn1", False)
        assert engine.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is False

    def test_unregistered_sub_cannot_contact(self) -> None:
        engine, bus = _make_engine()
        assert engine.can_contact_submarine("phantom", SubCommMethod.VLF) is False

    def test_sub_missing_capability(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.VLF])
        assert engine.can_contact_submarine("ssn1", SubCommMethod.SATELLITE) is False

    def test_vlf_send_slow_latency(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.VLF])
        success, latency = engine.send_to_submarine("ssn1", SubCommMethod.VLF, 300)
        # 300 bits / 300 bps = 1s
        if success:
            assert latency == pytest.approx(1.0, rel=0.01)

    def test_elf_extremely_slow(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.ELF])
        success, latency = engine.send_to_submarine("ssn1", SubCommMethod.ELF, 100)
        # 100 bits / 10 bps = 10s
        if success:
            assert latency == pytest.approx(10.0, rel=0.01)

    def test_send_fails_if_cannot_contact(self) -> None:
        engine, bus = _make_engine()
        engine.register_submarine("ssn1", [SubCommMethod.SATELLITE])
        # Not at periscope depth
        success, latency = engine.send_to_submarine("ssn1", SubCommMethod.SATELLITE)
        assert success is False
        assert latency == 0.0


# ---------------------------------------------------------------------------
# Flagship loss
# ---------------------------------------------------------------------------


class TestFlagshipLoss:
    """Flag transfer on flagship loss."""

    def test_flag_transfer(self) -> None:
        engine, bus = _make_engine()
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2", "cg1"],
        )
        engine.handle_flagship_loss("tf1", _TS)
        assert engine.get_flagship("tf1") == "ddg2"

    def test_flag_transfer_publishes_event(self) -> None:
        engine, bus = _make_engine()
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2"],
        )
        events: list[CommandStatusChangeEvent] = []
        bus.subscribe(CommandStatusChangeEvent, events.append)
        engine.handle_flagship_loss("tf1", _TS)
        assert len(events) == 1
        assert events[0].cause == "flagship_loss"

    def test_flag_transfer_recovery_after_timer(self) -> None:
        config = NavalC2Config(flag_transfer_delay_s=100.0)
        engine, bus = _make_engine()
        engine._config = config
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2"],
        )
        events: list[CommandStatusChangeEvent] = []
        bus.subscribe(CommandStatusChangeEvent, events.append)

        engine.handle_flagship_loss("tf1", _TS)
        engine.update(101.0, _TS)
        # Should get recovery event
        assert len(events) == 2
        assert events[1].cause == "recovery"


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestNavalC2State:
    """Checkpoint / restore."""

    def test_state_round_trip(self) -> None:
        engine, bus = _make_engine()
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="ddg1", member_ids=["ddg1", "ddg2"],
        )
        engine.establish_data_link(
            "net1", NavalDataLinkType.LINK_16,
            participant_ids=["ddg1", "ddg2"],
        )
        engine.register_submarine("ssn1", [SubCommMethod.VLF, SubCommMethod.SATELLITE])
        engine.set_periscope_depth("ssn1", True)

        state = engine.get_state()
        engine2, bus2 = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

    def test_state_preserves_formations(self) -> None:
        engine, bus = _make_engine()
        engine.create_formation(
            "tf1", NavalFormationType.TASK_FORCE,
            flagship_id="cv1", member_ids=["cv1", "cg1"],
        )
        state = engine.get_state()
        engine2, bus2 = _make_engine()
        engine2.set_state(state)
        assert engine2.get_flagship("tf1") == "cv1"


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------


class TestNavalReplay:
    """Deterministic replay."""

    def test_deterministic_sub_comms(self) -> None:
        def run(seed: int) -> list[bool]:
            engine, bus = _make_engine(seed=seed)
            engine.register_submarine("ssn1", [SubCommMethod.VLF])
            return [
                engine.send_to_submarine("ssn1", SubCommMethod.VLF, 100)[0]
                for _ in range(20)
            ]
        assert run(77) == run(77)
