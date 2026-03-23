"""Unit tests for IadsEngine — IADS sectors, health, SEAD, air track processing."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.iads import (
    IadsConfig,
    IadsEngine,
    IadsSector,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_iads_engine(seed: int = 42, **cfg_kwargs) -> IadsEngine:
    bus = EventBus()
    config = IadsConfig(**cfg_kwargs) if cfg_kwargs else None
    return IadsEngine(bus, _rng(seed), config)


def _make_sector(
    sector_id: str = "alpha",
    *,
    ew_radars: list[str] | None = None,
    acq_radars: list[str] | None = None,
    sam_batteries: list[str] | None = None,
    aaa_positions: list[str] | None = None,
    command_node: str | None = "cmd_1",
) -> IadsSector:
    return IadsSector(
        sector_id=sector_id,
        center=Position(0.0, 0.0, 0.0),
        radius_m=50_000.0,
        early_warning_radars=ew_radars or ["ew_1", "ew_2"],
        acquisition_radars=acq_radars or ["acq_1"],
        sam_batteries=sam_batteries or ["sam_1", "sam_2"],
        aaa_positions=aaa_positions or ["aaa_1"],
        command_node=command_node,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSectorRegistration:
    """Sectors should be registered and retrievable."""

    def test_register_and_get(self):
        eng = _make_iads_engine(seed=100)
        sector = _make_sector("bravo")
        eng.register_sector(sector)
        retrieved = eng.get_sector("bravo")
        assert retrieved.sector_id == "bravo"

    def test_component_health_initialized(self):
        eng = _make_iads_engine(seed=101)
        sector = _make_sector("charlie")
        eng.register_sector(sector)
        s = eng.get_sector("charlie")
        # All components should start at 1.0 health
        for comp_id in ["ew_1", "ew_2", "acq_1", "sam_1", "sam_2", "aaa_1", "cmd_1"]:
            assert s.component_health[comp_id] == pytest.approx(1.0)

    def test_missing_sector_raises(self):
        eng = _make_iads_engine(seed=102)
        with pytest.raises(KeyError):
            eng.get_sector("nonexistent")


class TestSectorHealth:
    """Health computation should be a compound of radar, SAM, and command."""

    def test_fully_operational(self):
        eng = _make_iads_engine(seed=200)
        sector = _make_sector()
        eng.register_sector(sector)
        health = eng.compute_sector_health("alpha")
        # All components at 1.0: radar=1.0, sam=1.0, cmd=1.0 -> 1.0
        assert health == pytest.approx(1.0)

    def test_degraded_components_reduce_health(self):
        eng = _make_iads_engine(seed=201)
        sector = _make_sector()
        eng.register_sector(sector)

        # Degrade one SAM battery
        sector.component_health["sam_1"] = 0.0
        health = eng.compute_sector_health("alpha")
        assert health < 1.0

    def test_all_sams_destroyed_zero_health(self):
        eng = _make_iads_engine(seed=202)
        sector = _make_sector()
        eng.register_sector(sector)

        sector.component_health["sam_1"] = 0.0
        sector.component_health["sam_2"] = 0.0
        health = eng.compute_sector_health("alpha")
        assert health == pytest.approx(0.0)


class TestSEADDamage:
    """SEAD strikes should degrade targeted components."""

    def test_sead_reduces_component_health(self):
        eng = _make_iads_engine(seed=300, sead_degradation_rate=0.3)
        sector = _make_sector()
        eng.register_sector(sector)

        old_health = sector.component_health["sam_1"]
        new_health = eng.apply_sead_damage("alpha", "sam_1")
        # Health should decrease (with stochastic noise, could vary slightly)
        assert new_health < old_health

    def test_arm_effectiveness_for_radars(self):
        """Radar targets should use sead_arm_effectiveness (0.8 default)."""
        eng = _make_iads_engine(
            seed=301,
            sead_degradation_rate=0.5,
            sead_arm_effectiveness=0.9,
            sead_effectiveness=0.3,
        )
        sector = _make_sector()
        eng.register_sector(sector)

        # SEAD on a radar target uses ARM effectiveness
        new_health_radar = eng.apply_sead_damage("alpha", "ew_1")
        # Damage = 0.5 * 0.9 = 0.45; health ~ 1.0 - 0.45 = 0.55 (+ noise)
        assert new_health_radar < 0.75  # generous bound accounting for noise

    def test_repeated_sead_destroys_component(self):
        eng = _make_iads_engine(seed=302, sead_degradation_rate=0.5)
        sector = _make_sector()
        eng.register_sector(sector)

        for _ in range(10):
            eng.apply_sead_damage("alpha", "sam_1")

        assert sector.component_health["sam_1"] < 0.3


class TestProcessAirTrack:
    """Air track processing through the IADS radar chain."""

    def test_process_returns_engagement_data(self):
        eng = _make_iads_engine(seed=400)
        sector = _make_sector()
        eng.register_sector(sector)

        track = Position(25_000.0, 0.0, 5000.0)
        result = eng.process_air_track("alpha", track)

        assert result["sector_id"] == "alpha"
        assert result["ew_available"] is True
        assert result["sam_available"] is True
        assert result["autonomous"] is False
        assert result["effectiveness"] > 0.0

    def test_no_ew_increases_handoff_time(self):
        eng = _make_iads_engine(seed=401)
        sector = _make_sector()
        eng.register_sector(sector)

        # Full system
        track = Position(10_000.0, 0.0, 3000.0)
        res_full = eng.process_air_track("alpha", track)

        # Destroy EW radars
        sector.component_health["ew_1"] = 0.0
        sector.component_health["ew_2"] = 0.0
        res_no_ew = eng.process_air_track("alpha", track)

        assert res_no_ew["handoff_time_s"] > res_full["handoff_time_s"]


class TestAutonomousFallback:
    """Destroyed command node should force autonomous mode with reduced effectiveness."""

    def test_command_node_destroyed(self):
        eng = _make_iads_engine(seed=500, autonomous_effectiveness_mult=0.4)
        sector = _make_sector()
        eng.register_sector(sector)

        # Full system
        track = Position(10_000.0, 0.0, 3000.0)
        res_full = eng.process_air_track("alpha", track)

        # Destroy command node
        sector.component_health["cmd_1"] = 0.0
        res_auto = eng.process_air_track("alpha", track)

        assert res_auto["autonomous"] is True
        assert res_auto["effectiveness"] < res_full["effectiveness"]


class TestStateRoundtrip:
    """get_state / set_state should preserve sector data."""

    def test_state_roundtrip(self):
        eng = _make_iads_engine(seed=600)
        sector = _make_sector("delta")
        eng.register_sector(sector)

        # Apply some damage
        eng.apply_sead_damage("delta", "sam_1")
        damaged_health = eng.get_sector("delta").component_health["sam_1"]

        state = eng.get_state()

        # Create new engine and restore
        eng2 = _make_iads_engine(seed=999)
        eng2.set_state(state)

        restored = eng2.get_sector("delta")
        assert restored.component_health["sam_1"] == pytest.approx(damaged_health)
        assert restored.sector_id == "delta"
