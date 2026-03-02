"""Target signature profiles and effective-signature computation.

Each unit type has a :class:`SignatureProfile` (loaded from YAML) describing
what it looks like across visual, thermal, radar, acoustic, and EM domains.
:class:`SignatureResolver` computes the *effective* signature given the unit's
current state and environmental conditions.
"""

from __future__ import annotations

import enum
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignatureDomain(enum.IntEnum):
    """Physical domain in which a target can be observed."""

    VISUAL = 0
    THERMAL = 1
    RADAR = 2
    ACOUSTIC = 3
    ELECTROMAGNETIC = 4


# ---------------------------------------------------------------------------
# Pydantic sub-models
# ---------------------------------------------------------------------------


class VisualSignature(BaseModel):
    """Visual-spectrum observable characteristics."""

    height_m: float = 0.0
    cross_section_m2: float = 1.0
    camouflage_factor: float = 1.0  # 0–1, lower = better camo


class ThermalSignature(BaseModel):
    """Thermal/IR observable characteristics."""

    emissivity: float = 0.9
    heat_output_kw: float = 0.0
    contrast_modifier: float = 1.0


class RadarSignature(BaseModel):
    """Radar-cross-section (RCS) characteristics by aspect."""

    rcs_frontal_m2: float = 1.0
    rcs_side_m2: float = 1.0
    rcs_rear_m2: float = 1.0


class AcousticSignature(BaseModel):
    """Acoustic noise characteristics."""

    noise_db: float = 60.0  # baseline dB at reference speed
    speed_coefficient: float = 3.0  # dB per m/s above idle


class EMSignature(BaseModel):
    """Electromagnetic emission characteristics."""

    emitting: bool = False
    power_dbm: float = 0.0
    frequency_ghz: float = 0.0


# ---------------------------------------------------------------------------
# Composite profile
# ---------------------------------------------------------------------------


class SignatureProfile(BaseModel):
    """Complete signature profile for a unit type — loaded from YAML."""

    profile_id: str
    unit_type: str
    visual: VisualSignature = VisualSignature()
    thermal: ThermalSignature = ThermalSignature()
    radar: RadarSignature = RadarSignature()
    acoustic: AcousticSignature = AcousticSignature()
    electromagnetic: EMSignature = EMSignature()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class SignatureLoader:
    """Load and cache :class:`SignatureProfile` instances from YAML files."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._profiles: dict[str, SignatureProfile] = {}

    def load_profile(self, path: Path) -> SignatureProfile:
        """Load and validate a single YAML signature profile."""
        import yaml

        with open(path) as f:
            raw = yaml.safe_load(f)
        profile = SignatureProfile.model_validate(raw)
        self._profiles[profile.profile_id] = profile
        return profile

    def load_all(self) -> None:
        """Recursively load all ``*.yaml`` files under *data_dir*."""
        for yaml_path in sorted(self._data_dir.rglob("*.yaml")):
            self.load_profile(yaml_path)
        logger.info("Loaded %d signature profiles", len(self._profiles))

    def get_profile(self, profile_id: str) -> SignatureProfile:
        """Return a loaded profile.  Raises ``KeyError`` if not found."""
        return self._profiles[profile_id]

    def available_profiles(self) -> list[str]:
        """Return sorted list of loaded profile identifiers."""
        return sorted(self._profiles.keys())


# ---------------------------------------------------------------------------
# Posture modifiers (ground units)
# ---------------------------------------------------------------------------

# Posture enum values (from ground.py): MOVING=0, HALTED=1, DEFENSIVE=2,
# DUG_IN=3, FORTIFIED=4.  Maps to signature reduction factors.
_POSTURE_VISUAL: dict[int, float] = {
    0: 1.0,   # moving — full signature
    1: 0.8,   # halted
    2: 0.5,   # defensive
    3: 0.3,   # dug in
    4: 0.2,   # fortified
}

_POSTURE_THERMAL: dict[int, float] = {
    0: 1.0,
    1: 0.9,
    2: 0.7,
    3: 0.5,
    4: 0.4,
}


# ---------------------------------------------------------------------------
# Resolver: effective signatures given unit state & environment
# ---------------------------------------------------------------------------


class SignatureResolver:
    """Compute effective signature values given unit state and environment."""

    @staticmethod
    def effective_visual(
        profile: SignatureProfile,
        unit: Any,
        concealment: float = 0.0,
        posture: int = 0,
    ) -> float:
        """Return effective visual cross-section (m^2).

        Parameters
        ----------
        profile:
            The unit's signature profile.
        unit:
            The unit entity (used for future extensions).
        concealment:
            Terrain concealment factor 0–1 (1 = fully concealed).
        posture:
            Ground posture integer (0=MOVING .. 4=FORTIFIED).
        """
        vis = profile.visual
        posture_mod = _POSTURE_VISUAL.get(posture, 1.0)
        return vis.cross_section_m2 * vis.camouflage_factor * (1.0 - concealment) * posture_mod

    @staticmethod
    def effective_thermal(
        profile: SignatureProfile,
        unit: Any,
        thermal_contrast: float = 1.0,
        posture: int = 0,
    ) -> float:
        """Return effective thermal signature (kW equivalent).

        Parameters
        ----------
        thermal_contrast:
            Environmental thermal contrast multiplier (from conditions).
        posture:
            Ground posture integer.
        """
        th = profile.thermal
        posture_mod = _POSTURE_THERMAL.get(posture, 1.0)
        return th.heat_output_kw * th.emissivity * th.contrast_modifier * thermal_contrast * posture_mod

    @staticmethod
    def effective_rcs(
        profile: SignatureProfile,
        unit: Any,
        aspect_angle_deg: float = 0.0,
    ) -> float:
        """Return effective radar cross-section (m^2) for the given aspect.

        *aspect_angle_deg* is the relative bearing from the target's nose:
        0 = frontal, 90 = broadside, 180 = rear.  Intermediate values are
        linearly interpolated between the three cardinal aspects.
        """
        radar = profile.radar
        angle = abs(aspect_angle_deg) % 360
        if angle > 180:
            angle = 360 - angle

        if angle <= 90:
            # frontal → side
            t = angle / 90.0
            return radar.rcs_frontal_m2 * (1 - t) + radar.rcs_side_m2 * t
        else:
            # side → rear
            t = (angle - 90.0) / 90.0
            return radar.rcs_side_m2 * (1 - t) + radar.rcs_rear_m2 * t

    @staticmethod
    def effective_acoustic(
        profile: SignatureProfile,
        unit: Any,
    ) -> float:
        """Return effective acoustic source level (dB).

        For ground/aerial: noise_db + speed_coefficient * speed.
        For naval units with ``noise_signature_base``: uses the submarine
        speed-noise curve base + 20*log10(v/v_quiet) from Phase 2.
        """
        acou = profile.acoustic
        speed = getattr(unit, "speed", 0.0)

        # Naval submarine model (has noise_signature_base)
        noise_base = getattr(unit, "noise_signature_base", None)
        if noise_base is not None and noise_base > 0:
            quiet_speed = 5.0  # knots reference
            if speed > quiet_speed:
                return noise_base + 20.0 * math.log10(speed / quiet_speed)
            return noise_base

        # General model
        return acou.noise_db + acou.speed_coefficient * speed

    @staticmethod
    def effective_em(
        profile: SignatureProfile,
        unit: Any,
    ) -> float:
        """Return effective EM emission power (dBm).

        Returns ``-inf`` if not emitting.
        """
        em = profile.electromagnetic
        if not em.emitting:
            return float("-inf")
        return em.power_dbm
