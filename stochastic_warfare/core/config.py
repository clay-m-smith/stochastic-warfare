"""YAML configuration loading with pydantic validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, field_validator

T = TypeVar("T", bound=BaseModel)


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return the raw dict."""
    with open(path) as f:
        return yaml.safe_load(f)


def load_config(path: Path, model: type[T]) -> T:
    """Load a YAML file and validate it against a pydantic model."""
    raw = load_yaml(path)
    return model.model_validate(raw)


class ScenarioConfig(BaseModel):
    """Top-level scenario configuration loaded from YAML."""

    name: str
    start_time: datetime
    duration_hours: float
    master_seed: int
    tick_duration_seconds: float

    @field_validator("start_time")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start_time must include timezone (use Z or +00:00)")
        return v

    @property
    def duration(self) -> timedelta:
        return timedelta(hours=self.duration_hours)

    @property
    def tick_duration(self) -> timedelta:
        return timedelta(seconds=self.tick_duration_seconds)
