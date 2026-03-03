"""Tests for detection/signatures.py — signature profiles, loader, resolver."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from stochastic_warfare.detection.signatures import (
    AcousticSignature,
    EMSignature,
    RadarSignature,
    SignatureDomain,
    SignatureLoader,
    SignatureProfile,
    SignatureResolver,
    ThermalSignature,
    VisualSignature,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "signatures"


# ── SignatureDomain enum ──────────────────────────────────────────────


class TestSignatureDomain:
    def test_values(self) -> None:
        assert SignatureDomain.VISUAL == 0
        assert SignatureDomain.THERMAL == 1
        assert SignatureDomain.RADAR == 2
        assert SignatureDomain.ACOUSTIC == 3
        assert SignatureDomain.ELECTROMAGNETIC == 4

    def test_all_domains_exist(self) -> None:
        assert len(SignatureDomain) == 5


# ── Sub-model defaults ────────────────────────────────────────────────


class TestSubModelDefaults:
    def test_visual_defaults(self) -> None:
        v = VisualSignature()
        assert v.height_m == 0.0
        assert v.cross_section_m2 == 1.0
        assert v.camouflage_factor == 1.0

    def test_thermal_defaults(self) -> None:
        t = ThermalSignature()
        assert t.emissivity == 0.9
        assert t.heat_output_kw == 0.0
        assert t.contrast_modifier == 1.0

    def test_radar_defaults(self) -> None:
        r = RadarSignature()
        assert r.rcs_frontal_m2 == 1.0
        assert r.rcs_side_m2 == 1.0
        assert r.rcs_rear_m2 == 1.0

    def test_acoustic_defaults(self) -> None:
        a = AcousticSignature()
        assert a.noise_db == 60.0
        assert a.speed_coefficient == 3.0

    def test_em_defaults(self) -> None:
        e = EMSignature()
        assert e.emitting is False
        assert e.power_dbm == 0.0
        assert e.frequency_ghz == 0.0


# ── SignatureProfile ──────────────────────────────────────────────────


class TestSignatureProfile:
    def test_minimal(self) -> None:
        p = SignatureProfile(profile_id="test", unit_type="test")
        assert p.profile_id == "test"
        assert p.visual.cross_section_m2 == 1.0

    def test_full(self) -> None:
        p = SignatureProfile(
            profile_id="m1a2",
            unit_type="m1a2",
            visual=VisualSignature(height_m=2.4, cross_section_m2=8.5, camouflage_factor=0.8),
            thermal=ThermalSignature(emissivity=0.95, heat_output_kw=1100.0),
            radar=RadarSignature(rcs_frontal_m2=15.0, rcs_side_m2=35.0, rcs_rear_m2=10.0),
        )
        assert p.visual.height_m == 2.4
        assert p.thermal.heat_output_kw == 1100.0
        assert p.radar.rcs_side_m2 == 35.0


# ── SignatureLoader ───────────────────────────────────────────────────


class TestSignatureLoader:
    def test_load_single(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        profile = loader.load_profile(DATA_DIR / "m1a2.yaml")
        assert profile.profile_id == "m1a2"
        assert profile.unit_type == "m1a2"
        assert profile.visual.height_m == 2.4

    def test_load_all(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        profiles = loader.available_profiles()
        assert len(profiles) == 15
        assert "m1a2" in profiles
        assert "ssn688" in profiles
        assert "f16c" in profiles

    def test_get_profile(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        p = loader.get_profile("ddg51")
        assert p.unit_type == "ddg51"
        assert p.radar.rcs_frontal_m2 == 1000.0

    def test_get_profile_not_found(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        with pytest.raises(KeyError):
            loader.get_profile("nonexistent")

    def test_available_profiles_sorted(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        profiles = loader.available_profiles()
        assert profiles == sorted(profiles)

    def test_all_profiles_valid(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        for pid in loader.available_profiles():
            p = loader.get_profile(pid)
            assert p.profile_id == pid
            assert p.unit_type != ""

    def test_m1a2_thermal(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        p = loader.get_profile("m1a2")
        assert p.thermal.heat_output_kw == 1100.0
        assert p.thermal.emissivity == 0.95

    def test_ssn688_em_not_emitting(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        p = loader.get_profile("ssn688")
        assert p.electromagnetic.emitting is False

    def test_f16c_em_emitting(self) -> None:
        loader = SignatureLoader(DATA_DIR)
        loader.load_all()
        p = loader.get_profile("f16c")
        assert p.electromagnetic.emitting is True
        assert p.electromagnetic.power_dbm == 60.0


# ── SignatureResolver — effective visual ──────────────────────────────


class TestEffectiveVisual:
    def _profile(self) -> SignatureProfile:
        return SignatureProfile(
            profile_id="test",
            unit_type="test",
            visual=VisualSignature(cross_section_m2=10.0, camouflage_factor=0.8),
        )

    def test_base(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit)
        assert val == pytest.approx(10.0 * 0.8)

    def test_concealment_reduces(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, concealment=0.5)
        assert val == pytest.approx(10.0 * 0.8 * 0.5)

    def test_full_concealment(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, concealment=1.0)
        assert val == pytest.approx(0.0)

    def test_posture_moving(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, posture=0)  # MOVING
        assert val == pytest.approx(10.0 * 0.8 * 1.0)

    def test_posture_dug_in(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, posture=3)  # DUG_IN
        assert val == pytest.approx(10.0 * 0.8 * 0.3)

    def test_posture_fortified(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, posture=4)  # FORTIFIED
        assert val == pytest.approx(10.0 * 0.8 * 0.2)

    def test_concealment_plus_posture(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_visual(p, unit, concealment=0.3, posture=2)
        expected = 10.0 * 0.8 * (1.0 - 0.3) * 0.5  # DEFENSIVE=0.5
        assert val == pytest.approx(expected)


# ── SignatureResolver — effective thermal ─────────────────────────────


class TestEffectiveThermal:
    def _profile(self) -> SignatureProfile:
        return SignatureProfile(
            profile_id="test",
            unit_type="test",
            thermal=ThermalSignature(
                emissivity=0.95, heat_output_kw=1100.0, contrast_modifier=1.2
            ),
        )

    def test_base(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_thermal(p, unit)
        expected = 1100.0 * 0.95 * 1.2 * 1.0 * 1.0  # contrast=1.0, posture=MOVING
        assert val == pytest.approx(expected)

    def test_thermal_contrast(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_thermal(p, unit, thermal_contrast=0.5)
        expected = 1100.0 * 0.95 * 1.2 * 0.5 * 1.0
        assert val == pytest.approx(expected)

    def test_posture_reduces(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        val = SignatureResolver.effective_thermal(p, unit, posture=3)  # DUG_IN
        expected = 1100.0 * 0.95 * 1.2 * 1.0 * 0.5
        assert val == pytest.approx(expected)


# ── SignatureResolver — effective RCS ─────────────────────────────────


class TestEffectiveRCS:
    def _profile(self) -> SignatureProfile:
        return SignatureProfile(
            profile_id="test",
            unit_type="test",
            radar=RadarSignature(rcs_frontal_m2=15.0, rcs_side_m2=35.0, rcs_rear_m2=10.0),
        )

    def test_frontal(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        assert SignatureResolver.effective_rcs(p, unit, 0.0) == pytest.approx(15.0)

    def test_broadside(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        assert SignatureResolver.effective_rcs(p, unit, 90.0) == pytest.approx(35.0)

    def test_rear(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        assert SignatureResolver.effective_rcs(p, unit, 180.0) == pytest.approx(10.0)

    def test_45_degrees(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        expected = 15.0 * 0.5 + 35.0 * 0.5  # midpoint frontal-side
        assert SignatureResolver.effective_rcs(p, unit, 45.0) == pytest.approx(expected)

    def test_135_degrees(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        expected = 35.0 * 0.5 + 10.0 * 0.5  # midpoint side-rear
        assert SignatureResolver.effective_rcs(p, unit, 135.0) == pytest.approx(expected)

    def test_negative_angle(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        # -90 should be the same as 90
        assert SignatureResolver.effective_rcs(p, unit, -90.0) == pytest.approx(35.0)

    def test_270_degrees(self) -> None:
        p = self._profile()
        unit = SimpleNamespace()
        # 270 wraps to 90
        assert SignatureResolver.effective_rcs(p, unit, 270.0) == pytest.approx(35.0)


# ── SignatureResolver — effective acoustic ────────────────────────────


class TestEffectiveAcoustic:
    def _profile(self) -> SignatureProfile:
        return SignatureProfile(
            profile_id="test",
            unit_type="test",
            acoustic=AcousticSignature(noise_db=85.0, speed_coefficient=2.0),
        )

    def test_stationary(self) -> None:
        p = self._profile()
        unit = SimpleNamespace(speed=0.0)
        assert SignatureResolver.effective_acoustic(p, unit) == pytest.approx(85.0)

    def test_moving(self) -> None:
        p = self._profile()
        unit = SimpleNamespace(speed=10.0)
        expected = 85.0 + 2.0 * 10.0
        assert SignatureResolver.effective_acoustic(p, unit) == pytest.approx(expected)

    def test_naval_model(self) -> None:
        """Naval units with noise_signature_base use the submarine speed-noise curve."""
        p = self._profile()
        unit = SimpleNamespace(speed=15.0, noise_signature_base=110.0)
        quiet_speed = 5.0
        expected = 110.0 + 20.0 * math.log10(15.0 / quiet_speed)
        assert SignatureResolver.effective_acoustic(p, unit) == pytest.approx(expected)

    def test_naval_at_quiet_speed(self) -> None:
        p = self._profile()
        unit = SimpleNamespace(speed=5.0, noise_signature_base=110.0)
        assert SignatureResolver.effective_acoustic(p, unit) == pytest.approx(110.0)

    def test_naval_below_quiet_speed(self) -> None:
        p = self._profile()
        unit = SimpleNamespace(speed=2.0, noise_signature_base=110.0)
        assert SignatureResolver.effective_acoustic(p, unit) == pytest.approx(110.0)


# ── SignatureResolver — effective EM ──────────────────────────────────


class TestEffectiveEM:
    def test_not_emitting(self) -> None:
        p = SignatureProfile(profile_id="t", unit_type="t")
        unit = SimpleNamespace()
        assert SignatureResolver.effective_em(p, unit) == float("-inf")

    def test_emitting(self) -> None:
        p = SignatureProfile(
            profile_id="t",
            unit_type="t",
            electromagnetic=EMSignature(emitting=True, power_dbm=60.0, frequency_ghz=9.4),
        )
        unit = SimpleNamespace()
        assert SignatureResolver.effective_em(p, unit) == pytest.approx(60.0)
