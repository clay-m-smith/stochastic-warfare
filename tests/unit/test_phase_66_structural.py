"""Phase 66 structural verification — source-level string assertions."""

from __future__ import annotations

from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "stochastic_warfare"


def _read(rel_path: str) -> str:
    return (_SRC / rel_path).read_text(encoding="utf-8")


class TestPhase66Structural:
    """Source-level assertions: Phase 66 wiring exists in the right files."""

    def test_battle_has_unconventional_engine(self) -> None:
        src = _read("simulation/battle.py")
        assert "unconventional_engine" in src

    def test_battle_has_check_ied_detection(self) -> None:
        src = _read("simulation/battle.py")
        assert "check_ied_detection" in src

    def test_battle_has_evaluate_human_shield(self) -> None:
        src = _read("simulation/battle.py")
        assert "evaluate_human_shield" in src

    def test_engine_has_update_mine_persistence(self) -> None:
        src = _read("simulation/engine.py")
        assert "update_mine_persistence" in src

    def test_campaign_has_attempt_assault(self) -> None:
        src = _read("simulation/campaign.py")
        assert "attempt_assault" in src

    def test_calibration_has_enable_unconventional_warfare(self) -> None:
        src = _read("simulation/calibration.py")
        assert "enable_unconventional_warfare" in src
