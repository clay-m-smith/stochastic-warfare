"""Detection visualization — Pd vs range curves, belief vs truth, coverage maps.

Usage:
    uv run python scripts/visualize/detection_viz.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from stochastic_warfare.detection.detection import DetectionEngine
from stochastic_warfare.detection.estimation import StateEstimator, TrackState
from stochastic_warfare.detection.identification import ContactInfo, ContactLevel
from stochastic_warfare.detection.sensors import SensorDefinition, SensorInstance, SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader, SignatureResolver

SIG_DIR = Path(__file__).resolve().parents[2] / "data" / "signatures"
SENSOR_DIR = Path(__file__).resolve().parents[2] / "data" / "sensors"
OUT_DIR = Path(__file__).resolve().parent / "output"


def plot_pd_vs_range() -> None:
    """Plot detection probability vs range for each sensor type."""
    sig_loader = SignatureLoader(SIG_DIR)
    sig_loader.load_all()
    sensor_loader = SensorLoader(SENSOR_DIR)
    sensor_loader.load_all()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Detection Probability vs Range by Sensor Type", fontsize=14)

    # Visual sensor vs M1A2
    ax = axes[0, 0]
    profile = sig_loader.get_profile("m1a2")
    defn = sensor_loader.get_definition("mk1_eyeball")
    sensor = SensorInstance(defn)
    ranges = np.linspace(100, 5000, 200)
    eff_vis = SignatureResolver.effective_visual(profile, None)
    pds = [
        DetectionEngine.detection_probability(
            DetectionEngine.compute_snr_visual(sensor, eff_vis, r, 1000.0),
            defn.detection_threshold,
        )
        for r in ranges
    ]
    ax.plot(ranges, pds, "b-", linewidth=2)
    ax.set_title("Visual: Mk1 Eyeball vs M1A2 (day)")
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("P(detection)")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)

    # Thermal sensor vs M1A2
    ax = axes[0, 1]
    defn_th = sensor_loader.get_definition("thermal_sight")
    sensor_th = SensorInstance(defn_th)
    eff_th = SignatureResolver.effective_thermal(profile, None)
    pds_th = [
        DetectionEngine.detection_probability(
            DetectionEngine.compute_snr_thermal(sensor_th, eff_th, r),
            defn_th.detection_threshold,
        )
        for r in ranges
    ]
    ax.plot(ranges, pds_th, "r-", linewidth=2)
    ax.set_title("Thermal: AN/TAS-6 vs M1A2")
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("P(detection)")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)

    # Radar vs F-16C
    ax = axes[1, 0]
    profile_f16 = sig_loader.get_profile("f16c")
    defn_radar = sensor_loader.get_definition("air_search_radar")
    sensor_radar = SensorInstance(defn_radar)
    ranges_radar = np.linspace(1000, 400000, 200)
    eff_rcs = SignatureResolver.effective_rcs(profile_f16, None, 0.0)
    pds_radar = [
        DetectionEngine.detection_probability(
            DetectionEngine.compute_snr_radar(sensor_radar, eff_rcs, r),
            defn_radar.detection_threshold,
        )
        for r in ranges_radar
    ]
    ax.plot(ranges_radar / 1000, pds_radar, "g-", linewidth=2)
    ax.set_title("Radar: AN/SPY-1D vs F-16C (frontal)")
    ax.set_xlabel("Range (km)")
    ax.set_ylabel("P(detection)")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)

    # Passive sonar vs DDG-51
    ax = axes[1, 1]
    profile_ddg = sig_loader.get_profile("ddg51")
    defn_sonar = sensor_loader.get_definition("passive_sonar")
    sensor_sonar = SensorInstance(defn_sonar)
    ranges_sonar = np.linspace(100, 100000, 200)
    eff_acou = SignatureResolver.effective_acoustic(profile_ddg, None)
    pds_sonar = [
        DetectionEngine.detection_probability(
            DetectionEngine.compute_snr_acoustic(sensor_sonar, eff_acou, r, 70.0),
            defn_sonar.detection_threshold,
        )
        for r in ranges_sonar
    ]
    ax.plot(ranges_sonar / 1000, pds_sonar, "m-", linewidth=2)
    ax.set_title("Passive Sonar: AN/SQR-19 vs DDG-51")
    ax.set_xlabel("Range (km)")
    ax.set_ylabel("P(detection)")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "pd_vs_range.png", dpi=150)
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'pd_vs_range.png'}")


def plot_belief_vs_truth() -> None:
    """Plot Kalman filter convergence: belief state vs ground truth."""
    rng = np.random.Generator(np.random.PCG64(42))
    est = StateEstimator(rng=rng)

    true_x, true_y = 5000.0, 3000.0
    R = np.diag([200.0, 200.0])
    ci = ContactInfo(ContactLevel.DETECTED, None, None, None, 0.5)

    # First measurement
    meas = np.array([true_x + rng.normal(0, 50), true_y + rng.normal(0, 50)])
    track = est.create_track("t-1", "blue", meas, R, ci, 0.0)

    history_x: list[float] = [track.state.position[0]]
    history_y: list[float] = [track.state.position[1]]
    unc_history: list[float] = [track.position_uncertainty]

    for t in range(1, 50):
        est.predict(track, dt=1.0)
        meas = np.array([true_x + rng.normal(0, 50), true_y + rng.normal(0, 50)])
        est.update(track, meas, R, float(t))
        history_x.append(track.state.position[0])
        history_y.append(track.state.position[1])
        unc_history.append(track.position_uncertainty)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Kalman Filter Convergence", fontsize=14)

    ax1.plot(history_x, history_y, "b.-", markersize=3, label="Estimated")
    ax1.plot(true_x, true_y, "r*", markersize=15, label="Ground Truth")
    ax1.set_xlabel("Easting (m)")
    ax1.set_ylabel("Northing (m)")
    ax1.legend()
    ax1.set_title("Position Estimate vs Truth")
    ax1.grid(True, alpha=0.3)

    ax2.plot(range(50), unc_history, "b-", linewidth=2)
    ax2.set_xlabel("Observation #")
    ax2.set_ylabel("Position Uncertainty (m)")
    ax2.set_title("Uncertainty Convergence")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "belief_vs_truth.png", dpi=150)
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'belief_vs_truth.png'}")


def plot_roc_curves() -> None:
    """Plot ROC curves for different sensor types."""
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_title("ROC Curves — P(detection) vs P(false alarm)", fontsize=14)

    thresholds = np.linspace(-5, 25, 200)

    for snr_db, label in [(5, "SNR=5 dB"), (10, "SNR=10 dB"), (15, "SNR=15 dB"), (20, "SNR=20 dB")]:
        pds = [DetectionEngine.detection_probability(snr_db, t) for t in thresholds]
        pfas = [DetectionEngine.false_alarm_probability(t) for t in thresholds]
        ax.plot(pfas, pds, linewidth=2, label=label)

    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="Random")
    ax.set_xlabel("P(false alarm)")
    ax.set_ylabel("P(detection)")
    ax.legend()
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal")

    plt.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "roc_curves.png", dpi=150)
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'roc_curves.png'}")


if __name__ == "__main__":
    print("Generating Phase 3 detection visualizations...")
    plot_pd_vs_range()
    plot_belief_vs_truth()
    plot_roc_curves()
    print("Done.")
