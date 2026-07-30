"""Strict public scenario-name namespace."""

from __future__ import annotations

import re
from typing import Any


_SCENARIO_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,254}")


def validate_scenario_name(value: Any) -> str:
    """Require one exact, path-free scenario directory identifier."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or _SCENARIO_NAME.fullmatch(value) is None
    ):
        raise ValueError(
            "scenario must be a non-empty trimmed string containing one "
            "lowercase directory identifier using only a-z, 0-9, '_' or '-'",
        )
    return value
