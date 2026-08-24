"""Shared pytest fixtures for the stochastic-warfare test suite.

Provides commonly-needed test primitives: RNG generators, EventBus,
SimulationClock, timestamp constants, and Position helpers.

Existing test files define their own local helpers (``_rng()``, ``_TS``,
``_make_engine()``).  These fixtures are designed for use by **new** test
files — they do not replace existing helpers.

Usage in a test file::

    def test_something(rng, event_bus):
        engine = SomeEngine(event_bus, rng)
        ...
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

# ---------------------------------------------------------------------------
# Common constants (importable, not fixtures)
# ---------------------------------------------------------------------------

#: Frozen reference timestamp used across tests.
TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

#: Common position constants.
POS_ORIGIN = Position(0.0, 0.0, 0.0)
POS_1KM_EAST = Position(1000.0, 0.0, 0.0)
POS_5KM = Position(5000.0, 5000.0, 0.0)

#: Default seed for deterministic tests.
DEFAULT_SEED = 42

_EVIDENCE_CLASSIFICATIONS = frozenset(
    {
        "behavioral_oracle",
        "helper_assertion",
        "invariant_only",
        "structural_only",
    },
)


def pytest_configure(config: pytest.Config) -> None:
    """Register the source-local evidence marker before strict collection."""

    config.addinivalue_line(
        "markers",
        "test_evidence(classification): reviewed source-local evidence classification",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Map the nearest reviewed structural annotation to pytest's marker."""
    for item in items:
        effective: str | None = None
        seen_scopes: set[int] = set()
        for node, marker in item.iter_markers_with_node("test_evidence"):
            if (
                len(marker.args) != 1
                or marker.kwargs
                or not isinstance(marker.args[0], str)
                or not marker.args[0].strip()
                or marker.args[0] != marker.args[0].strip()
                or marker.args[0] not in _EVIDENCE_CLASSIFICATIONS
            ):
                raise pytest.UsageError(
                    f"invalid source-local test_evidence marker on {item.nodeid}",
                )
            scope_identity = id(node)
            if scope_identity in seen_scopes:
                raise pytest.UsageError(
                    f"conflicting source-local test_evidence markers on {item.nodeid}",
                )
            seen_scopes.add(scope_identity)
            if effective is None:
                effective = marker.args[0]
        if effective == "structural_only":
            item.add_marker(pytest.mark.structural)


# ---------------------------------------------------------------------------
# Fixtures — fresh instance per test
# ---------------------------------------------------------------------------


@pytest.fixture
def rng() -> np.random.Generator:
    """Deterministic numpy RNG seeded at 42."""
    return np.random.Generator(np.random.PCG64(DEFAULT_SEED))


@pytest.fixture
def event_bus() -> EventBus:
    """Fresh EventBus instance."""
    return EventBus()


# ---------------------------------------------------------------------------
# Parameterized fixtures
# ---------------------------------------------------------------------------


def make_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    """Create a deterministic RNG with the given seed.

    Use this helper when a fixture isn't flexible enough (e.g., you
    need multiple RNGs with different seeds in one test).
    """
    return np.random.Generator(np.random.PCG64(seed))


def make_clock(
    start: datetime = TS,
    tick_s: float = 10.0,
    elapsed_s: float = 0.0,
) -> SimulationClock:
    """Create a SimulationClock, optionally pre-advanced."""
    clock = SimulationClock(
        start=start,
        tick_duration=timedelta(seconds=tick_s),
    )
    ticks = int(elapsed_s / tick_s)
    for _ in range(ticks):
        clock.advance()
    return clock


def bind_test_era_runtime(
    context: Any,
    *,
    era: str = "modern",
    selected_registry_id: str | None = None,
    strategic_s: float = 3600.0,
    operational_s: float = 300.0,
    tactical_s: float = 5.0,
    tick_duration_seconds: float | None = None,
) -> Any:
    """Attach a typed, internally consistent era contract to a test context.

    Minimal ``SimpleNamespace`` battle contexts do not run the production
    ``SimulationContext`` constructor, while checkpoint tests sometimes build
    a ``SimulationContext`` with ``object.__new__``.  This helper gives both
    forms the same immutable era contract and captured identity used by the
    production boundary.  Namespace contexts receive a small integrity check;
    real ``SimulationContext`` instances retain their production validator.
    """
    from stochastic_warfare.core.era import Era, EraConfig
    from stochastic_warfare.simulation.era_runtime import (
        EraExecutionHorizonSource,
        EraRuntimeContract,
        EraRuntimeSource,
    )

    era_config = EraConfig(era=Era(era))
    source = EraRuntimeSource(
        selected_registry_id=selected_registry_id or era,
        strategic_s=strategic_s,
        operational_s=operational_s,
        tactical_s=tactical_s,
        tick_duration_seconds=tick_duration_seconds,
    )
    contract = EraRuntimeContract.resolve(
        era_config=era_config,
        **source.model_dump(mode="python"),
    )
    object.__setattr__(context, "era_config", era_config)
    object.__setattr__(context, "era_runtime_contract", contract)
    object.__setattr__(
        context,
        "_era_config_identity_json",
        era_config.model_dump_json(),
    )
    object.__setattr__(
        context,
        "_era_runtime_source_identity_json",
        source.model_dump_json(),
    )
    config = getattr(context, "config", None)
    if config is not None and hasattr(config, "date") and hasattr(config, "duration_hours"):
        object.__setattr__(
            context,
            "_era_execution_horizon_identity_json",
            EraExecutionHorizonSource(
                date=config.date,
                duration_hours=config.duration_hours,
            ).model_dump_json(),
        )

    if not callable(
        getattr(type(context), "validate_era_runtime_bindings", None),
    ):

        def validate_era_runtime_bindings() -> None:
            current = context.era_runtime_contract
            if not isinstance(current, EraRuntimeContract) or current != contract:
                raise RuntimeError("Test context era runtime binding changed")

        context.validate_era_runtime_bindings = validate_era_runtime_bindings
    return context


def make_versionless_legacy_morale_checkpoint(
    checkpoint: dict,
) -> dict:
    """Convert format 118 into the bounded pre-113 morale envelope."""
    legacy = copy.deepcopy(checkpoint)
    assert legacy.pop("checkpoint_version") == 118
    context = legacy["context"]
    context["rng"].pop("indexed_fow")
    context.pop("targeting_default_visibility_m")
    context.pop("tactical_targeting")
    context.pop("era_runtime_contract")
    planning_state = context.get("planning_engine")
    if isinstance(planning_state, dict):
        planning_state.pop("checkpoint_schema", None)
    fog_state = context.get("fog_of_war")
    if fog_state is not None:
        assert fog_state.pop("current_detection_witnesses") == {}
        assert fog_state.pop("observer_track_supports") == []
        assert fog_state.pop("scan_counts") == {}
        fog_state.pop("cadence")
    battle_state = legacy.get("battle")
    if battle_state is not None:
        battle_state.pop("deferred_ooda_schema")
        battle_state.pop("performance_execution_receipt")
        battle_state.pop("fow_observer_unit_ids")
    runtime_state = context.pop("morale_runtime")
    assert runtime_state["suspended_archives"] == {}
    active_records = runtime_state["active_records"]
    # Checkpoints serialize RNG stream identities by their stable schema value.
    morale_rng_state = copy.deepcopy(context["rng"]["streams"]["morale"])
    context["morale_states"] = {unit_id: record["current_state"] for unit_id, record in active_records.items()}
    context["morale_machine"] = {
        "unit_states": {
            unit_id: {
                "current_state": record["current_state"],
                "transition_cooldown_s": 0.0,
                "last_transition_time": (
                    -1e9 if record["last_transition_time_s"] is None else record["last_transition_time_s"]
                ),
            }
            for unit_id, record in active_records.items()
        },
        "rng_state": copy.deepcopy(morale_rng_state),
    }
    rout_state = context.get("rout_engine")
    if isinstance(rout_state, dict):
        rout_state["rng_state"] = copy.deepcopy(morale_rng_state)
    return legacy
