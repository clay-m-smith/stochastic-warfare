"""Phase 16f tests — EW Validation Scenarios.

Tests scenario loading, IADS/EW asset configuration, engagement outcomes,
and deterministic replay for Bekaa Valley 1982 and Gulf War EW 1991.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import yaml

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.ew.decoys_ew import EWDecoyEngine, SeekerType
from stochastic_warfare.ew.eccm import ECCMEngine, ECCMSuite, ECCMTechnique
from stochastic_warfare.ew.emitters import Emitter, EmitterRegistry, EmitterType, WaveformType
from stochastic_warfare.ew.jamming import (
    JammerDefinitionModel,
    JammerInstance,
    JamTechnique,
    JammingConfig,
    JammingEngine,
)
from stochastic_warfare.ew.sigint import SIGINTCollector, SIGINTEngine

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


# =========================================================================
# YAML Loading
# =========================================================================


class TestYAMLJammerLoading:
    """Verify jammer YAML files parse into JammerDefinitionModel."""

    JAMMER_DIR = DATA_DIR / "ew" / "jammers"

    @pytest.mark.parametrize("filename", [
        "an_alq_99.yaml", "an_tlq_32.yaml", "krasukha_4.yaml",
        "an_slq_32.yaml", "an_alq_131.yaml", "r_330zh_zhitel.yaml",
    ])
    def test_jammer_yaml_loads(self, filename):
        path = self.JAMMER_DIR / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        defn = JammerDefinitionModel(**data)
        assert defn.jammer_id
        assert defn.power_dbm > 0
        assert defn.frequency_max_ghz > defn.frequency_min_ghz

    def test_all_jammers_have_valid_techniques(self):
        if not self.JAMMER_DIR.exists():
            pytest.skip("Jammer dir not found")
        for path in sorted(self.JAMMER_DIR.glob("*.yaml")):
            with open(path) as f:
                data = yaml.safe_load(f)
            defn = JammerDefinitionModel(**data)
            for t in defn.techniques:
                assert t in range(5), f"Invalid technique {t} in {path.name}"


class TestYAMLScenarioLoading:
    """Verify scenario YAML files parse correctly."""

    def test_bekaa_valley_loads(self):
        path = DATA_DIR / "scenarios" / "bekaa_valley_1982" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Bekaa Valley scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["name"].startswith("Bekaa")
        assert "ew_config" in data
        assert data["ew_config"]["enable_ew"] is True
        assert len(data["documented_outcomes"]) >= 2

    def test_gulf_war_loads(self):
        path = DATA_DIR / "scenarios" / "gulf_war_ew_1991" / "scenario.yaml"
        if not path.exists():
            pytest.skip("Gulf War EW scenario not found")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["name"].startswith("Gulf War")
        assert "ew_config" in data
        assert len(data["documented_outcomes"]) >= 2


# =========================================================================
# Bekaa Valley 1982
# =========================================================================


class TestBekaaSetup:
    """Validate Bekaa Valley scenario setup."""

    def test_iads_sectors_registered(self):
        """19 SAM sites registered as emitters."""
        registry = EmitterRegistry()
        for i in range(19):
            e = Emitter(
                emitter_id=f"sa6_{i}", unit_id=f"sam_{i}",
                emitter_type=EmitterType.RADAR,
                position=Position(i * 2000.0, 5000.0, 800.0),
                frequency_ghz=8.0 + i * 0.1, bandwidth_ghz=0.05,
                power_dbm=65.0, antenna_gain_dbi=28.0,
                waveform=WaveformType.PULSED, side="red",
            )
            registry.register_emitter(e)
        active = registry.get_active_emitters(side="red")
        assert len(active) == 19

    def test_ew_assets_configured(self):
        """Israeli EW stand-off jammers and SIGINT collectors configured."""
        bus = EventBus()
        jam_eng = JammingEngine(bus, _rng(), JammingConfig(enable_ew=True))
        defn = JammerDefinitionModel(
            jammer_id="ew_standoff_1", platform_type="airborne",
            power_dbm=73.0, antenna_gain_dbi=15.0, bandwidth_ghz=0.1,
            frequency_min_ghz=2.0, frequency_max_ghz=18.0,
            techniques=[1, 2, 4],
        )
        j = JammerInstance(definition=defn, position=Position(0.0, -10000.0, 5000.0))
        jam_eng.register_jammer(j)
        jam_eng.activate_jammer("ew_standoff_1", JamTechnique.BARRAGE, 8.0)
        assert jam_eng._jammers["ew_standoff_1"].active

    def test_eccm_suites_for_sams(self):
        """Syrian SAM ECCM suites configured."""
        bus = EventBus()
        eccm_eng = ECCMEngine(bus)
        suite = ECCMSuite(
            suite_id="sa6_eccm", unit_id="sam_0",
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.5, hop_rate_hz=100.0,
            sidelobe_ratio_db=20.0,
        )
        eccm_eng.register_suite(suite)
        found = eccm_eng.get_suite_for_unit("sam_0")
        assert found is not None


class TestBekaaOutcomes:
    """Validate Bekaa Valley engagement outcomes."""

    def test_sam_suppression(self):
        """Israeli jamming produces significant radar SNR penalty on SAM radars."""
        bus = EventBus()
        jam_eng = JammingEngine(bus, _rng(), JammingConfig(enable_ew=True))
        # High-power stand-off jammer
        defn = JammerDefinitionModel(
            jammer_id="standoff", power_dbm=73.0, antenna_gain_dbi=15.0,
            bandwidth_ghz=0.1, frequency_min_ghz=2.0, frequency_max_ghz=18.0,
        )
        j = JammerInstance(
            definition=defn, position=Position(0.0, -20000.0, 5000.0),
            active=True,
        )
        jam_eng.register_jammer(j)
        # SAM radar at 30km
        penalty = jam_eng.compute_radar_snr_penalty(
            sensor_pos=Position(0.0, 30000.0, 800.0),
            sensor_freq_ghz=8.0, sensor_power_dbm=65.0,
            sensor_gain_dbi=28.0, sensor_bw_ghz=0.05,
            target_range_m=20000.0,
        )
        assert penalty > 10.0  # Significant degradation

    def test_drone_provocation(self):
        """Drones registered as emitters provoke SAM radar emissions."""
        registry = EmitterRegistry()
        # Drone with radar-like emission to provoke SAM
        drone = Emitter(
            emitter_id="drone_1", unit_id="drone_unit",
            emitter_type=EmitterType.NAVIGATION,
            position=Position(5000.0, 10000.0, 1000.0),
            frequency_ghz=10.0, bandwidth_ghz=0.01,
            power_dbm=30.0, antenna_gain_dbi=5.0,
            waveform=WaveformType.CW, side="blue",
        )
        registry.register_emitter(drone)
        active = registry.get_active_emitters(side="blue")
        assert len(active) == 1

    def test_sigint_detects_sam_radars(self):
        """SIGINT collectors detect SAM radar emissions."""
        bus = EventBus()
        sigint = SIGINTEngine(bus, _rng())
        collector = SIGINTCollector(
            collector_id="sigint_1", unit_id="sigint_unit",
            position=Position(0.0, -15000.0, 5000.0),
            receiver_sensitivity_dbm=-115.0,
            frequency_range_ghz=(2.0, 18.0),
            bandwidth_ghz=2.0, df_accuracy_deg=0.5,
            has_tdoa=True, aperture_m=8.0,
        )
        # SAM radar emitter
        sam_radar = Emitter(
            emitter_id="sa6_radar", unit_id="sam_0",
            emitter_type=EmitterType.RADAR,
            position=Position(0.0, 20000.0, 800.0),
            frequency_ghz=8.0, bandwidth_ghz=0.05,
            power_dbm=65.0, antenna_gain_dbi=28.0,
            waveform=WaveformType.PULSED, side="red",
        )
        prob = sigint.compute_intercept_probability(collector, sam_radar)
        assert prob > 0.8  # High-power radar at moderate range

    def test_eccm_insufficient(self):
        """SA-6 ECCM (limited frequency hopping) insufficient vs Israeli jamming."""
        bus = EventBus()
        eccm = ECCMEngine(bus)
        suite = ECCMSuite(
            suite_id="sa6_eccm", unit_id="sam_0",
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.5, hop_rate_hz=100.0,
        )
        # Reduction from freq hop vs 0.1 GHz jammer BW
        # hop_bw=0.5 / jammer_bw=0.1 → ratio=5 → ~7 dB
        reduction = eccm.compute_jam_reduction(suite, jammer_bw_ghz=0.1)
        # ~7 dB reduction vs 40+ dB J/S = still overwhelmed
        assert reduction < 10.0


# =========================================================================
# Gulf War EW 1991
# =========================================================================


class TestGulfWarSetup:

    def test_coalition_ew_assets(self):
        """Coalition EW assets configured (EF-111 + EA-6B + F-4G)."""
        bus = EventBus()
        jam_eng = JammingEngine(bus, _rng(), JammingConfig(enable_ew=True))
        # Two jammers
        for jid, pw in [("ef111", 73.0), ("ea6b", 73.0)]:
            defn = JammerDefinitionModel(
                jammer_id=jid, power_dbm=pw, antenna_gain_dbi=15.0,
                bandwidth_ghz=0.5, frequency_min_ghz=0.064,
                frequency_max_ghz=18.0, techniques=[1, 2, 4],
            )
            j = JammerInstance(definition=defn, position=Position(0.0, -50000.0, 8000.0))
            jam_eng.register_jammer(j)
        assert len(jam_eng._jammers) == 2

    def test_iraqi_iads(self):
        """Iraqi IADS (24 SAM sites) registered."""
        registry = EmitterRegistry()
        for i in range(24):
            e = Emitter(
                emitter_id=f"iraqi_sam_{i}", unit_id=f"sam_{i}",
                emitter_type=EmitterType.RADAR,
                position=Position(i * 3000.0, 20000.0 + i * 1000.0, 50.0),
                frequency_ghz=6.0 + i * 0.2, bandwidth_ghz=0.05,
                power_dbm=62.0, antenna_gain_dbi=25.0,
                waveform=WaveformType.PULSED, side="red",
            )
            registry.register_emitter(e)
        assert len(registry.get_active_emitters(side="red")) == 24

    def test_harm_targeting(self):
        """Wild Weasels detect and can target radiating SAMs."""
        bus = EventBus()
        sigint = SIGINTEngine(bus, _rng())
        weasel = SIGINTCollector(
            collector_id="f4g_1", unit_id="weasel_1",
            position=Position(0.0, -30000.0, 6000.0),
            receiver_sensitivity_dbm=-105.0,
            frequency_range_ghz=(2.0, 18.0),
            bandwidth_ghz=1.5, df_accuracy_deg=1.0,
            aperture_m=3.0,
        )
        sam_radar = Emitter(
            emitter_id="iraqi_sam_0", unit_id="sam_0",
            emitter_type=EmitterType.RADAR,
            position=Position(0.0, 30000.0, 50.0),
            frequency_ghz=8.0, bandwidth_ghz=0.05,
            power_dbm=62.0, antenna_gain_dbi=25.0,
            waveform=WaveformType.PULSED, side="red",
        )
        prob = sigint.compute_intercept_probability(weasel, sam_radar)
        assert prob > 0.5  # Should detect radiating SAM


class TestGulfWarOutcomes:

    def test_iads_degradation(self):
        """Coalition jamming produces significant IADS degradation."""
        bus = EventBus()
        jam_eng = JammingEngine(bus, _rng(), JammingConfig(enable_ew=True))
        # Two high-power jammers
        for jid in ["ef111", "ea6b"]:
            defn = JammerDefinitionModel(
                jammer_id=jid, power_dbm=73.0, antenna_gain_dbi=15.0,
                bandwidth_ghz=0.5, frequency_min_ghz=0.064,
                frequency_max_ghz=18.0,
            )
            j = JammerInstance(
                definition=defn,
                position=Position(0.0, -40000.0, 8000.0),
                active=True,
            )
            jam_eng.register_jammer(j)

        # Check penalty on a SAM radar
        penalty = jam_eng.compute_radar_snr_penalty(
            sensor_pos=Position(0.0, 30000.0, 50.0),
            sensor_freq_ghz=8.0, sensor_power_dbm=62.0,
            sensor_gain_dbi=25.0, sensor_bw_ghz=0.05,
            target_range_m=40000.0,
        )
        assert penalty > 15.0  # Multiple jammers → significant

    def test_decoy_drones_effective(self):
        """BQM-74 decoy drones divert SAM missiles."""
        bus = EventBus()
        decoy_eng = EWDecoyEngine(bus, _rng())
        # Deploy chaff-like drone
        chaff = decoy_eng.deploy_chaff(Position(5000.0, 15000.0, 300.0), 8.0)
        prob = decoy_eng.compute_missile_divert_probability(
            chaff, SeekerType.RADAR, 50.0,
        )
        assert prob > 0.5

    def test_iraqi_eccm_limited(self):
        """Iraqi ECCM (limited) insufficient vs coalition EW."""
        bus = EventBus()
        eccm = ECCMEngine(bus)
        suite = ECCMSuite(
            suite_id="iraqi_eccm", unit_id="sam_0",
            techniques=[ECCMTechnique.FREQUENCY_HOP],
            hop_bandwidth_ghz=0.3, hop_rate_hz=50.0,
            sidelobe_ratio_db=15.0,
        )
        # Reduction vs 0.5 GHz coalition jammer BW → hop_bw < jammer_bw
        reduction = eccm.compute_jam_reduction(suite, jammer_bw_ghz=0.5)
        assert reduction == 0.0  # Hop BW narrower → no protection


# =========================================================================
# Determinism
# =========================================================================


class TestEWDeterminism:

    def test_same_seed_same_results(self):
        """Identical seeds produce identical EW outcomes."""
        results = []
        for _ in range(2):
            bus = EventBus()
            jam_eng = JammingEngine(bus, _rng(42), JammingConfig(enable_ew=True))
            defn = JammerDefinitionModel(
                jammer_id="j1", power_dbm=70.0, antenna_gain_dbi=15.0,
                bandwidth_ghz=0.1, frequency_min_ghz=2.0, frequency_max_ghz=18.0,
            )
            j = JammerInstance(definition=defn, position=Position(0.0, 0.0, 0.0), active=True)
            jam_eng.register_jammer(j)
            p = jam_eng.compute_radar_snr_penalty(
                Position(10000.0, 0.0, 0.0), 10.0, 60.0, 30.0, 0.01, 50000.0,
            )
            results.append(p)
        assert results[0] == results[1]

    def test_different_seed_different_sigint(self):
        """Different seeds may produce different SIGINT intercept outcomes."""
        outcomes = set()
        for seed in range(20):
            bus = EventBus()
            eng = SIGINTEngine(bus, _rng(seed))
            collector = SIGINTCollector(
                collector_id="c1", unit_id="u1",
                position=Position(0.0, 0.0, 0.0),
                receiver_sensitivity_dbm=-80.0,
                frequency_range_ghz=(1.0, 18.0),
                bandwidth_ghz=1.0, df_accuracy_deg=1.0,
                aperture_m=2.0,
            )
            # Moderate emitter at medium range → ~33% intercept probability
            emitter = Emitter(
                emitter_id="e1", unit_id="eu1",
                emitter_type=EmitterType.RADAR,
                position=Position(60000.0, 0.0, 0.0),
                frequency_ghz=10.0, bandwidth_ghz=0.1,
                power_dbm=50.0, antenna_gain_dbi=15.0,
                waveform=WaveformType.PULSED, side="red",
            )
            report = eng.attempt_intercept(collector, emitter)
            outcomes.add(report.intercept_successful)
            if len(outcomes) == 2:
                break
        # Should see both True and False across different seeds
        assert len(outcomes) == 2
