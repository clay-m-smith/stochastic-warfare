"""Detection scan-owner contracts retained after legacy FOW retirement.

FOW witness emission, indexed identity, side ordering, aliasing, and checkpoint
continuation are exercised through ``test_fow_receipts.py`` and production
checkpoint/targeting integration tests.
"""

from __future__ import annotations

import copy

import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.detection import (
    DetectionEngine,
    DetectionScanIdentity,
)
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance
from stochastic_warfare.detection.signatures import (
    SignatureProfile,
    VisualSignature,
)


def _sensor() -> SensorInstance:
    return SensorInstance(
        SensorDefinition(
            sensor_id="shared-catalog-eye",
            sensor_type="VISUAL",
            display_name="Shared eye",
            max_range_m=50_000.0,
            detection_threshold=-100.0,
        ),
    )


def _signature() -> SignatureProfile:
    return SignatureProfile(
        profile_id="scan-owner-target",
        unit_type="test",
        visual=VisualSignature(
            cross_section_m2=500.0,
            camouflage_factor=1.0,
        ),
    )


def test_integration_gain_is_attachment_local_and_continues_exactly() -> None:
    engine = DetectionEngine(rng=np.random.default_rng(115))
    sensor = _sensor()
    observer = Position(0.0, 0.0, 0.0)
    target = Position(0.0, 100.0, 0.0)
    identities = (
        DetectionScanIdentity("blue", "blue-observer", 2),
        DetectionScanIdentity("green", "green-observer", 2),
    )

    first = [
        engine.check_detection(
            observer,
            target,
            sensor,
            _signature(),
            target_id="shared-target",
            scan_identity=identity,
        )
        for identity in identities
    ]
    second = [
        engine.check_detection(
            observer,
            target,
            sensor,
            _signature(),
            target_id="shared-target",
            scan_identity=identity,
        )
        for identity in identities
    ]
    assert first[0].snr_db == first[1].snr_db
    assert second[0].snr_db == second[1].snr_db
    assert second[0].snr_db > first[0].snr_db

    state = engine.get_state()
    restored = DetectionEngine(rng=np.random.default_rng(999))
    restored.set_state(copy.deepcopy(state))
    control = engine.check_detection(
        observer,
        target,
        sensor,
        _signature(),
        target_id="shared-target",
        scan_identity=identities[0],
    )
    continued = restored.check_detection(
        observer,
        target,
        sensor,
        _signature(),
        target_id="shared-target",
        scan_identity=identities[0],
    )
    assert continued == control
    assert restored.get_state() == engine.get_state()


def test_legacy_two_component_scan_key_remains_readable() -> None:
    engine = DetectionEngine(rng=np.random.default_rng(115))
    engine.set_state(
        {
            "rng_state": engine.get_state()["rng_state"],
            "scan_counts": {"legacy-eye:legacy-target": 3},
        },
    )
    assert engine.get_state()["scan_counts"] == {
        "legacy-eye:legacy-target": 3,
    }
