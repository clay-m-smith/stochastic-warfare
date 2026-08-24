"""State-only contracts for fog-of-war views and contact projections.

Detection-cycle behavior belongs to the receipt-bearing transaction tests;
this module intentionally does not exercise the unsupported legacy update.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.estimation import Track, TrackState
from stochastic_warfare.detection.fog_of_war import (
    ContactRecord,
    FogOfWarManager,
    SideWorldView,
)
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel


def _track(
    *,
    track_id: str = "track-1",
    easting: float = 1_000.0,
    northing: float = 2_000.0,
) -> Track:
    info = ContactInfo(
        ContactLevel.DETECTED,
        None,
        None,
        None,
        0.5,
    )
    return Track(
        track_id=track_id,
        side="blue",
        contact_info=info,
        state=TrackState(
            position=np.array([easting, northing]),
            velocity=np.array([0.0, 0.0]),
            covariance=np.eye(4),
            last_update_time=0.0,
        ),
    )


def _record(
    contact_id: str,
    track: Track,
    *,
    confidence: float = 0.5,
) -> ContactRecord:
    return ContactRecord(
        contact_id=contact_id,
        track=track,
        contact_info=ContactInfo(
            ContactLevel.DETECTED,
            None,
            None,
            None,
            confidence,
        ),
        first_detected_time=0.0,
        last_sensor_contact_time=0.0,
    )


def test_side_world_view_state_is_exact() -> None:
    view = SideWorldView(side="red", last_update_time=100.0)
    assert view.get_state() == {
        "side": "red",
        "contacts": {},
        "last_update_time": 100.0,
    }


def test_empty_manager_views_are_independent_and_noncontacting() -> None:
    manager = FogOfWarManager(rng=np.random.default_rng(3))
    blue = manager.get_world_view("blue")
    red = manager.get_world_view("red")
    assert blue is not red
    assert blue.side == "blue"
    assert red.side == "red"
    assert manager.get_contact("blue", "missing") is None


def test_ground_truth_comparison_reports_one_miss() -> None:
    result = FogOfWarManager.ground_truth_comparison(
        SideWorldView(side="blue"),
        {"enemy": Position(1_000.0, 2_000.0, 0.0)},
    )
    assert result["correct_detections"] == 0
    assert result["missed_units"] == 1
    assert result["false_tracks"] == 0


def test_ground_truth_comparison_reports_exact_detection() -> None:
    view = SideWorldView(side="blue")
    view.contacts["enemy"] = _record("enemy", _track())
    result = FogOfWarManager.ground_truth_comparison(
        view,
        {"enemy": Position(1_000.0, 2_000.0, 0.0)},
    )
    assert result["correct_detections"] == 1
    assert result["missed_units"] == 0
    assert result["false_tracks"] == 0
    assert result["position_errors"]["enemy"] == pytest.approx(0.0)


def test_ground_truth_comparison_reports_false_track() -> None:
    view = SideWorldView(side="blue")
    view.contacts["ghost"] = _record(
        "ghost",
        _track(easting=999.0, northing=999.0),
    )
    result = FogOfWarManager.ground_truth_comparison(view, {})
    assert result["correct_detections"] == 0
    assert result["missed_units"] == 0
    assert result["false_tracks"] == 1


def test_contact_record_state_preserves_sensor_order() -> None:
    record = _record("enemy", _track())
    record.contact_info = ContactInfo(
        ContactLevel.CLASSIFIED,
        "GROUND",
        "ARMOR",
        None,
        0.7,
    )
    record.last_sensor_contact_time = 10.0
    record.reporting_sensors.extend(("eye", "radar"))
    state = record.get_state()
    assert state["contact_id"] == "enemy"
    assert state["contact_info"]["level"] == int(ContactLevel.CLASSIFIED)
    assert state["reporting_sensors"] == ["eye", "radar"]
