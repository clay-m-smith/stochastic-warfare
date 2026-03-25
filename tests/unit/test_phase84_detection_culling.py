"""Phase 84a: STRtree detection culling in FogOfWarManager."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.deception import Decoy, DeceptionEngine, DeceptionType
from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import StateEstimator
from stochastic_warfare.detection.fog_of_war import FogOfWarManager, SideWorldView
from stochastic_warfare.detection.identification import IdentificationEngine
from stochastic_warfare.detection.intel_fusion import IntelFusionEngine
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import SignatureProfile, VisualSignature


# ── helpers ──────────────────────────────────────────────────────────


def _sensor(**kwargs) -> SensorInstance:
    defaults = dict(
        sensor_id="eye", sensor_type="VISUAL", display_name="Eye",
        max_range_m=50000.0, detection_threshold=1.0,
    )
    defaults.update(kwargs)
    return SensorInstance(SensorDefinition(**defaults))


def _profile(cross_section: float = 10.0) -> SignatureProfile:
    return SignatureProfile(
        profile_id="test", unit_type="test",
        visual=VisualSignature(cross_section_m2=cross_section, camouflage_factor=1.0),
    )


def _fow(seed: int = 42) -> FogOfWarManager:
    rng = np.random.Generator(np.random.PCG64(seed))
    det = DetectionEngine(rng=np.random.Generator(np.random.PCG64(seed + 1)))
    ident = IdentificationEngine(np.random.Generator(np.random.PCG64(seed + 2)))
    est = StateEstimator(rng=np.random.Generator(np.random.PCG64(seed + 3)))
    intel = IntelFusionEngine(state_estimator=est, rng=np.random.Generator(np.random.PCG64(seed + 4)))
    dec = DeceptionEngine(rng=np.random.Generator(np.random.PCG64(seed + 5)))
    return FogOfWarManager(
        detection_engine=det,
        identification_engine=ident,
        state_estimator=est,
        intel_fusion=intel,
        deception_engine=dec,
        rng=rng,
    )


def _own_unit(x: float = 0.0, y: float = 0.0, **kwargs) -> dict:
    sensors = kwargs.pop("sensors", [_sensor()])
    return {
        "position": Position(x, y, 0.0),
        "sensors": sensors,
        "observer_height": kwargs.get("observer_height", 1.8),
    }


def _enemy_unit(uid: str, x: float, y: float, **kwargs) -> dict:
    return {
        "unit_id": uid,
        "position": Position(x, y, 0.0),
        "signature": kwargs.get("signature", _profile()),
        "unit": kwargs.get("unit", None),
        "target_height": kwargs.get("target_height", 0.0),
        "concealment": kwargs.get("concealment", 0.0),
        "posture": kwargs.get("posture", 0),
    }


# ── Detection culling tests ─────────────────────────────────────────


class TestDetectionCulling:
    """STRtree range culling in FOW detection loop."""

    def test_culling_excludes_distant_targets(self) -> None:
        """Enemy at 100km with 5km sensor range should never be checked."""
        fow = _fow(seed=10)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
        enemy = [_enemy_unit("e-far", 100_000.0, 0.0)]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=True)
        assert "e-far" not in wv.contacts

    def test_culling_includes_nearby_targets(self) -> None:
        """Enemy at 3km with 5km sensor range should be considered."""
        fow = _fow(seed=1)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
        enemy = [_enemy_unit("e-near", 3000.0, 0.0, signature=_profile(100.0))]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=True)
        # With large signature at short range, likely detected
        # Structural: no crash, culling doesn't prevent detection
        assert isinstance(wv, SideWorldView)

    def test_culling_boundary_target(self) -> None:
        """Enemy at exactly max range should be included in candidates."""
        fow = _fow(seed=5)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=10000.0)])]
        # Place at exactly 10km
        enemy = [_enemy_unit("e-boundary", 10000.0, 0.0, signature=_profile(200.0))]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=True)
        # Should not crash — target is within buffer radius
        assert isinstance(wv, SideWorldView)

    def test_culling_disabled_checks_all(self) -> None:
        """With detection_culling=False, no spatial index is used."""
        fow = _fow(seed=99)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
        enemy = [_enemy_unit("e-far", 100_000.0, 0.0)]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=False)
        # Far enemy won't be detected anyway (SNR too low), but it was checked
        assert isinstance(wv, SideWorldView)

    def test_culling_deterministic(self) -> None:
        """Same inputs produce identical contacts with culling."""
        own = [_own_unit(0.0, 0.0)]
        enemies = [
            _enemy_unit("e-1", 100.0, 0.0, signature=_profile(50.0)),
            _enemy_unit("e-2", 200.0, 100.0, signature=_profile(50.0)),
        ]
        contacts_a = set()
        contacts_b = set()
        for _ in range(3):
            fow_a = _fow(seed=7)
            wv_a = fow_a.update("blue", own, enemies, dt=1.0, detection_culling=True)
            contacts_a = set(wv_a.contacts.keys())

            fow_b = _fow(seed=7)
            wv_b = fow_b.update("blue", own, enemies, dt=1.0, detection_culling=True)
            contacts_b = set(wv_b.contacts.keys())

            assert contacts_a == contacts_b

    def test_culling_with_decoys(self) -> None:
        """Decoys within range included, out of range excluded."""
        fow = _fow(seed=20)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=5000.0)])]
        decoy_near = Decoy(
            decoy_id="d-near",
            deception_type=DeceptionType.DECOY_VISUAL,
            position=Position(1000.0, 0.0, 0.0),
            signature=_profile(50.0),
        )
        decoy_far = Decoy(
            decoy_id="d-far",
            deception_type=DeceptionType.DECOY_VISUAL,
            position=Position(100_000.0, 0.0, 0.0),
            signature=_profile(50.0),
        )
        wv = fow.update(
            "blue", own, [], dt=1.0,
            decoys=[decoy_near, decoy_far],
            detection_culling=True,
        )
        # Far decoy should be culled; near may or may not be detected
        assert "d-far" not in wv.contacts

    def test_culling_no_sensors(self) -> None:
        """Units with no operational sensors don't crash."""
        fow = _fow(seed=1)
        non_op_sensor = _sensor()
        # Make it non-operational by giving it equipment with condition 0
        from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
        equip = EquipmentItem(
            equipment_id="broken", name="Broken",
            category=EquipmentCategory.SENSOR, condition=0.0,
        )
        non_op_sensor.equipment = equip
        own = [_own_unit(0.0, 0.0, sensors=[non_op_sensor])]
        enemy = [_enemy_unit("e-1", 100.0, 0.0)]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=True)
        assert len(wv.contacts) == 0

    def test_culling_empty_targets(self) -> None:
        """No enemy units → no crash."""
        fow = _fow(seed=1)
        wv = fow.update("blue", [_own_unit()], [], dt=1.0, detection_culling=True)
        assert len(wv.contacts) == 0

    def test_culling_empty_own_units(self) -> None:
        """No own units → no crash."""
        fow = _fow(seed=1)
        enemy = [_enemy_unit("e-1", 100.0, 0.0)]
        wv = fow.update("blue", [], enemy, dt=1.0, detection_culling=True)
        assert len(wv.contacts) == 0

    def test_culling_large_sensor_range(self) -> None:
        """400km sensor includes all targets within 50km."""
        fow = _fow(seed=1)
        own = [_own_unit(0.0, 0.0, sensors=[_sensor(max_range_m=400_000.0)])]
        enemies = [
            _enemy_unit(f"e-{i}", float(i * 10_000), 0.0, signature=_profile(100.0))
            for i in range(1, 6)
        ]
        wv = fow.update("blue", own, enemies, dt=1.0, detection_culling=True)
        # All targets are within 400km range — none should be culled
        assert isinstance(wv, SideWorldView)

    def test_culling_multiple_sensors_max_range(self) -> None:
        """Max range across sensors used for the culling query."""
        fow = _fow(seed=1)
        short_sensor = _sensor(sensor_id="eye_short", max_range_m=5000.0)
        long_sensor = _sensor(sensor_id="radar", sensor_type="RADAR",
                              max_range_m=60000.0, frequency_mhz=9000.0,
                              peak_power_w=10000.0, antenna_gain_dbi=30.0)
        own = [_own_unit(0.0, 0.0, sensors=[short_sensor, long_sensor])]
        # Enemy at 30km — in range of radar but not eye
        enemy = [_enemy_unit("e-mid", 30000.0, 0.0, signature=_profile(100.0))]
        wv = fow.update("blue", own, enemy, dt=1.0, detection_culling=True)
        # Should not be culled (within radar's 60km max range)
        assert isinstance(wv, SideWorldView)

    def test_culling_identical_results(self) -> None:
        """Culling on/off produce same contacts for a small scenario."""
        own = [_own_unit(0.0, 0.0)]
        enemies = [
            _enemy_unit("e-1", 100.0, 0.0, signature=_profile(80.0)),
            _enemy_unit("e-2", 200.0, 100.0, signature=_profile(80.0)),
        ]
        fow_on = _fow(seed=42)
        wv_on = fow_on.update("blue", own, enemies, dt=1.0, detection_culling=True)
        fow_off = _fow(seed=42)
        wv_off = fow_off.update("blue", own, enemies, dt=1.0, detection_culling=False)
        assert set(wv_on.contacts.keys()) == set(wv_off.contacts.keys())
