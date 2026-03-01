"""Tests for core/config.py — YAML loading and pydantic validation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stochastic_warfare.core.config import ScenarioConfig, load_config, load_yaml

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "scenarios" / "test_scenario"


class TestLoadYaml:
    def test_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "test.yaml"
        p.write_text("key: value\ncount: 3\n")
        data = load_yaml(p)
        assert data == {"key": "value", "count": 3}


class TestScenarioConfig:
    def test_load_fixture(self) -> None:
        cfg = load_config(FIXTURE_DIR / "scenario.yaml", ScenarioConfig)
        assert cfg.name == "Desert Storm Test"
        assert cfg.master_seed == 42
        assert cfg.tick_duration_seconds == 10.0

    def test_start_time_is_utc(self) -> None:
        cfg = load_config(FIXTURE_DIR / "scenario.yaml", ScenarioConfig)
        assert cfg.start_time.tzinfo is not None

    def test_duration_property(self) -> None:
        cfg = load_config(FIXTURE_DIR / "scenario.yaml", ScenarioConfig)
        assert cfg.duration == timedelta(hours=100)

    def test_tick_duration_property(self) -> None:
        cfg = load_config(FIXTURE_DIR / "scenario.yaml", ScenarioConfig)
        assert cfg.tick_duration == timedelta(seconds=10)

    def test_missing_field_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("name: test\n")  # missing required fields
        with pytest.raises(Exception):
            load_config(p, ScenarioConfig)

    def test_naive_start_time_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "naive.yaml"
        p.write_text(
            "name: test\n"
            "start_time: '2000-01-01T00:00:00'\n"
            "duration_hours: 1\n"
            "master_seed: 1\n"
            "tick_duration_seconds: 1\n"
        )
        with pytest.raises(Exception):
            load_config(p, ScenarioConfig)
