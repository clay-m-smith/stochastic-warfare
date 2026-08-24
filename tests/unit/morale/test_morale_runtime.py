"""Unit tests for the authoritative morale runtime boundary."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.events import (
    MoraleStateChangeEvent,
    RallyEvent,
    SurrenderEvent,
)
from stochastic_warfare.morale.rout import RoutConfig, RoutEngine, RoutState
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
    MoraleStateRecord,
)
from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleTransitionCause,
)

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _unit(
    unit_id: str,
    *,
    status: UnitStatus = UnitStatus.ACTIVE,
) -> Unit:
    return Unit(
        entity_id=unit_id,
        position=Position(0.0, 0.0),
        status=status,
    )


def _runtime(
    states: dict[str, MoraleState],
    *,
    seed: int = 0,
    config: MoraleConfig | None = None,
    rout_config: RoutConfig | None = None,
) -> tuple[MoraleRuntime, EventBus, dict[str, Unit]]:
    bus = EventBus()
    rng = np.random.default_rng(seed)
    rout = RoutEngine(bus, rng, rout_config)
    runtime = MoraleRuntime(bus, rng, config, rout_engine=rout)
    units = {
        unit_id: _unit(
            unit_id,
            status=(
                UnitStatus.ROUTING
                if state is MoraleState.ROUTED
                else UnitStatus.SURRENDERED
                if state is MoraleState.SURRENDERED
                else UnitStatus.ACTIVE
            ),
        )
        for unit_id, state in states.items()
    }
    runtime.register_units(
        tuple(
            MoraleRegistration(unit_id, state)
            for unit_id, state in states.items()
        ),
        units,
    )
    return runtime, bus, units


class TestMoraleStateRecord:
    def test_is_immutable_and_validates_generation_semantics(self) -> None:
        record = MoraleStateRecord(MoraleState.STEADY)
        with pytest.raises(FrozenInstanceError):
            record.current_state = MoraleState.SHAKEN  # type: ignore[misc]
        with pytest.raises(ValueError, match="positive generation"):
            MoraleStateRecord(MoraleState.STEADY, generation=1)
        with pytest.raises(ValueError, match="cannot exceed"):
            MoraleStateRecord(
                MoraleState.SHAKEN,
                last_transition_time_s=2.0,
                last_check_time_s=1.0,
                generation=1,
            )


class TestRegistrationAndViews:
    def test_views_are_stable_read_only_and_share_one_generator(self) -> None:
        runtime, _bus, _units = _runtime({"u1": MoraleState.STEADY})
        states = runtime.states
        records = runtime.records
        assert states is runtime.states
        assert records is runtime.records
        assert runtime.rng is runtime.rout_engine.rng
        assert runtime.rng is runtime._machine.rng
        assert runtime._machine.config is runtime.config
        with pytest.raises(TypeError):
            states["u1"] = MoraleState.BROKEN  # type: ignore[index]
        with pytest.raises(FrozenInstanceError):
            records["u1"].generation = 2  # type: ignore[misc]

    def test_duplicate_batch_fails_before_mutation(self) -> None:
        runtime, _bus, _units = _runtime({})
        unit = _unit("u1")
        with pytest.raises(ValueError, match="Duplicate"):
            runtime.register_units(
                (
                    MoraleRegistration("u1", MoraleState.STEADY),
                    MoraleRegistration("u1", MoraleState.SHAKEN),
                ),
                {"u1": unit},
            )
        assert dict(runtime.states) == {}

    def test_late_registration_failure_rolls_back_committed_prefix(self) -> None:
        runtime, _bus, _units = _runtime({})

        class FailSecondWrite(dict[str, MoraleStateRecord]):
            writes = 0

            def __setitem__(
                self,
                key: str,
                value: MoraleStateRecord,
            ) -> None:
                self.writes += 1
                if self.writes == 2:
                    raise RuntimeError("injected late registration failure")
                super().__setitem__(key, value)

        runtime._store._active = FailSecondWrite()
        units = {"a": _unit("a"), "b": _unit("b")}
        with pytest.raises(RuntimeError, match="injected late"):
            runtime.register_units(
                (
                    MoraleRegistration("a", MoraleState.STEADY),
                    MoraleRegistration("b", MoraleState.SHAKEN),
                ),
                units,
            )
        assert dict(runtime.states) == {}
        assert runtime._units == {}

    def test_unit_binding_write_failure_rolls_back_active_record(self) -> None:
        runtime, _bus, _units = _runtime({})

        class FailUnitWrite(dict[str, Unit]):
            def __setitem__(self, key: str, value: Unit) -> None:
                raise RuntimeError("injected unit binding failure")

        runtime._units = FailUnitWrite()
        unit = _unit("u1")
        with pytest.raises(RuntimeError, match="unit binding failure"):
            runtime.register_units(
                (MoraleRegistration("u1", MoraleState.STEADY),),
                {"u1": unit},
            )
        assert dict(runtime.states) == {}
        assert runtime._units == {}


class TestRuntimeTransitions:
    def test_legacy_surrender_bypass_rejects_without_owner_mutation(
        self,
    ) -> None:
        runtime, bus, units = _runtime({"u1": MoraleState.ROUTED})
        runtime.rout_engine.initiate_rout("u1", threat_direction_rad=0.0)
        before_record = runtime.record_for("u1")
        before_status = units["u1"].status
        before_routes = copy.deepcopy(runtime.rout_engine._active_routs)
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)
        surrender_events: list[SurrenderEvent] = []
        bus.subscribe(SurrenderEvent, surrender_events.append)

        with pytest.raises(RuntimeError, match="authoritative morale"):
            runtime.rout_engine.process_surrender(
                "u1",
                personnel_count=100,
                capturing_side="red",
            )

        assert runtime.record_for("u1") == before_record
        assert units["u1"].status is before_status
        assert runtime.rout_engine._active_routs == before_routes
        assert runtime.rng.bit_generator.state == before_rng
        assert surrender_events == []

    def test_stochastic_surrender_commits_owner_status_route_and_event(
        self,
    ) -> None:
        runtime, bus, units = _runtime(
            {"u1": MoraleState.ROUTED},
            config=MoraleConfig(
                base_degrade_rate=0.8,
                base_recover_rate=0.0,
                leadership_weight=0.0,
                cohesion_weight=0.0,
                force_ratio_weight=0.0,
                use_continuous_time=False,
            ),
        )
        runtime.rout_engine._active_routs["u1"] = RoutState(
            unit_id="u1",
            direction_rad=1.0,
            speed_factor=1.5,
        )
        observed: list[tuple[MoraleState, UnitStatus, MoraleStateChangeEvent]] = []
        bus.subscribe(
            MoraleStateChangeEvent,
            lambda event: observed.append(
                (runtime.states["u1"], units["u1"].status, event),
            ),
        )

        result = runtime.check_transition(
            "u1",
            1.0,
            1.0,
            False,
            0.0,
            0.1,
            timestamp=_TS,
            current_time_s=5.0,
        )

        assert result is MoraleState.SURRENDERED
        assert runtime.states["u1"] is MoraleState.SURRENDERED
        assert units["u1"].status is UnitStatus.SURRENDERED
        assert "u1" not in runtime.rout_engine._active_routs
        assert len(observed) == 1
        assert observed[0][:2] == (
            MoraleState.SURRENDERED,
            UnitStatus.SURRENDERED,
        )
        assert observed[0][2].cause is MoraleTransitionCause.STOCHASTIC
        assert observed[0][2].logical_time_s == 5.0

    def test_no_change_check_consumes_one_draw_and_advances_record(self) -> None:
        config = MoraleConfig(
            base_degrade_rate=0.0,
            casualty_weight=0.0,
            suppression_weight=0.0,
        )
        runtime, bus, _units = _runtime(
            {"u1": MoraleState.STEADY},
            config=config,
        )
        received: list[MoraleStateChangeEvent] = []
        bus.subscribe(MoraleStateChangeEvent, received.append)
        expected = np.random.default_rng(0)
        expected.random()
        result = runtime.check_transition(
            "u1",
            0.0,
            0.0,
            True,
            1.0,
            5.0,
            timestamp=_TS,
            current_time_s=10.0,
        )
        record = runtime.record_for("u1")
        assert result is MoraleState.STEADY
        assert record == MoraleStateRecord(
            MoraleState.STEADY,
            last_check_time_s=10.0,
            generation=1,
        )
        assert runtime.rng.bit_generator.state == expected.bit_generator.state
        assert received == []

    def test_state_change_commits_status_then_caused_event(self) -> None:
        runtime, bus, units = _runtime(
            {"u1": MoraleState.STEADY},
            config=MoraleConfig(base_degrade_rate=0.8),
        )
        observed: list[tuple[UnitStatus, MoraleStateChangeEvent]] = []
        bus.subscribe(
            MoraleStateChangeEvent,
            lambda event: observed.append((units["u1"].status, event)),
        )
        result = runtime.check_transition(
            "u1",
            1.0,
            1.0,
            False,
            0.0,
            0.1,
            timestamp=_TS,
            current_time_s=5.0,
        )
        assert result is MoraleState.SHAKEN
        assert observed[0][0] is UnitStatus.ACTIVE
        assert observed[0][1].cause is MoraleTransitionCause.STOCHASTIC
        assert observed[0][1].logical_time_s == 5.0

    def test_pre_notification_event_failure_rewinds_state_status_and_rng(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime, _bus, units = _runtime(
            {"u1": MoraleState.STEADY},
            config=MoraleConfig(base_degrade_rate=0.8),
        )
        before_record = runtime.record_for("u1")
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)

        def fail_event(*_args: object, **_kwargs: object) -> MoraleStateChangeEvent:
            raise RuntimeError("injected event construction failure")

        monkeypatch.setattr(runtime, "_transition_event", fail_event)
        with pytest.raises(RuntimeError, match="injected"):
            runtime.check_transition(
                "u1",
                1.0,
                1.0,
                False,
                0.0,
                0.1,
                timestamp=_TS,
                current_time_s=5.0,
            )
        assert runtime.record_for("u1") == before_record
        assert units["u1"].status is UnitStatus.ACTIVE
        assert runtime.rng.bit_generator.state == before_rng

    def test_melee_force_arms_cooldown_without_draw(self) -> None:
        runtime, _bus, units = _runtime({"u1": MoraleState.SHAKEN})
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)
        runtime.force_transition(
            "u1",
            MoraleState.ROUTED,
            cause=MoraleTransitionCause.MELEE_ROUT,
            timestamp=_TS,
            current_time_s=2.0,
        )
        assert units["u1"].status is UnitStatus.ROUTING
        assert runtime.record_for("u1").generation == 1
        assert runtime.rng.bit_generator.state == before_rng
        assert runtime.check_transition(
            "u1",
            1.0,
            1.0,
            False,
            0.0,
            0.1,
            timestamp=_TS,
            current_time_s=3.0,
        ) is MoraleState.ROUTED
        assert runtime.rng.bit_generator.state == before_rng

    def test_subscriber_failure_leaves_forced_transition_committed(self) -> None:
        runtime, bus, units = _runtime({"u1": MoraleState.BROKEN})

        def fail_after_observing(_event: MoraleStateChangeEvent) -> None:
            assert runtime.states["u1"] is MoraleState.ROUTED
            assert units["u1"].status is UnitStatus.ROUTING
            raise RuntimeError("subscriber failed")

        bus.subscribe(MoraleStateChangeEvent, fail_after_observing)
        with pytest.raises(ExceptionGroup, match="subscriber failures"):
            runtime.force_transition(
                "u1",
                MoraleState.ROUTED,
                cause=MoraleTransitionCause.MELEE_ROUT,
                timestamp=_TS,
                current_time_s=2.0,
            )
        assert runtime.states["u1"] is MoraleState.ROUTED
        assert units["u1"].status is UnitStatus.ROUTING


class TestRallyAndCascade:
    def test_successful_rally_commits_before_ordered_events(self) -> None:
        runtime, bus, units = _runtime(
            {"u1": MoraleState.ROUTED},
            rout_config=RoutConfig(rally_base_chance=0.99),
        )
        observed: list[tuple[type[Event], MoraleState, UnitStatus]] = []
        bus.subscribe(
            Event,
            lambda event: observed.append(
                (type(event), runtime.states["u1"], units["u1"].status),
            ),
        )
        assert runtime.check_rally(
            "u1",
            5,
            True,
            timestamp=_TS,
            current_time_s=10.0,
        )
        assert observed == [
            (MoraleStateChangeEvent, MoraleState.SHAKEN, UnitStatus.ACTIVE),
            (RallyEvent, MoraleState.SHAKEN, UnitStatus.ACTIVE),
        ]

    def test_rally_pre_notification_failure_rewinds_draw_and_semantics(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime, _bus, units = _runtime(
            {"u1": MoraleState.ROUTED},
            rout_config=RoutConfig(rally_base_chance=0.99),
        )
        before = runtime.record_for("u1")
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)

        def fail_event(*_args: object, **_kwargs: object) -> MoraleStateChangeEvent:
            raise RuntimeError("injected rally preparation failure")

        monkeypatch.setattr(runtime, "_transition_event", fail_event)
        with pytest.raises(RuntimeError, match="injected rally"):
            runtime.check_rally(
                "u1",
                5,
                True,
                timestamp=_TS,
                current_time_s=10.0,
            )
        assert runtime.record_for("u1") == before
        assert units["u1"].status is UnitStatus.ROUTING
        assert runtime.rng.bit_generator.state == before_rng

    def test_cascade_draw_budget_and_candidate_event_order(self) -> None:
        runtime, bus, units = _runtime(
            {
                "source": MoraleState.ROUTED,
                "b": MoraleState.BROKEN,
                "a": MoraleState.SHAKEN,
                "steady": MoraleState.STEADY,
                "far": MoraleState.BROKEN,
            },
            rout_config=RoutConfig(
                cascade_base_chance=1.0,
                cascade_shaken_susceptibility=2.0,
                cascade_broken_susceptibility=2.0,
            ),
        )
        event_ids: list[str] = []
        bus.subscribe(MoraleStateChangeEvent, lambda event: event_ids.append(event.unit_id))
        expected = np.random.default_rng(0)
        expected.random(2)
        selected = runtime.rout_cascade(
            "source",
            {
                "source": 0.0,
                "b": 100.0,
                "a": 100.0,
                "steady": 100.0,
                "far": 501.0,
            },
            timestamp=_TS,
            current_time_s=20.0,
        )
        assert selected == ("a", "b")
        assert event_ids == ["a", "b"]
        assert runtime.rng.bit_generator.state == expected.bit_generator.state
        assert units["a"].status is units["b"].status is UnitStatus.ROUTING

    def test_cascade_preparation_failure_rewinds_all_draws_and_semantics(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime, _bus, units = _runtime(
            {
                "source": MoraleState.ROUTED,
                "a": MoraleState.SHAKEN,
                "b": MoraleState.BROKEN,
            },
            rout_config=RoutConfig(
                cascade_base_chance=1.0,
                cascade_shaken_susceptibility=2.0,
                cascade_broken_susceptibility=2.0,
            ),
        )
        before_records = dict(runtime.records)
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)
        calls = 0
        real = runtime._transition_event

        def fail_second(*args: object, **kwargs: object) -> MoraleStateChangeEvent:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected cascade preparation failure")
            return real(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(runtime, "_transition_event", fail_second)
        with pytest.raises(RuntimeError, match="injected cascade"):
            runtime.rout_cascade(
                "source",
                {"a": 100.0, "b": 100.0},
                timestamp=_TS,
                current_time_s=20.0,
            )
        assert dict(runtime.records) == before_records
        assert units["a"].status is units["b"].status is UnitStatus.ACTIVE
        assert runtime.rng.bit_generator.state == before_rng

    def test_terminal_cascade_candidate_rejects_before_draw(self) -> None:
        runtime, _bus, units = _runtime(
            {
                "source": MoraleState.ROUTED,
                "candidate": MoraleState.SHAKEN,
            },
        )
        units["candidate"].status = UnitStatus.DESTROYED
        before_rng = copy.deepcopy(runtime.rng.bit_generator.state)
        with pytest.raises(ValueError, match="Terminal cascade candidate"):
            runtime.rout_cascade(
                "source",
                {"candidate": 100.0},
                timestamp=_TS,
                current_time_s=20.0,
            )
        assert runtime.states["candidate"] is MoraleState.SHAKEN
        assert units["candidate"].status is UnitStatus.DESTROYED
        assert runtime.rng.bit_generator.state == before_rng

    def test_cascade_collects_failures_and_offers_every_ordered_event(self) -> None:
        runtime, bus, units = _runtime(
            {
                "source": MoraleState.ROUTED,
                "a": MoraleState.SHAKEN,
                "b": MoraleState.BROKEN,
            },
            rout_config=RoutConfig(
                cascade_base_chance=1.0,
                cascade_shaken_susceptibility=2.0,
                cascade_broken_susceptibility=2.0,
            ),
        )
        offered: list[str] = []

        def observe_and_fail(event: MoraleStateChangeEvent) -> None:
            offered.append(event.unit_id)
            assert runtime.states[event.unit_id] is MoraleState.ROUTED
            raise RuntimeError(event.unit_id)

        bus.subscribe(MoraleStateChangeEvent, observe_and_fail)
        with pytest.raises(ExceptionGroup) as exc_info:
            runtime.rout_cascade(
                "source",
                {"b": 100.0, "a": 100.0},
                timestamp=_TS,
                current_time_s=20.0,
            )
        assert offered == ["a", "b"]
        assert len(exc_info.value.exceptions) == 2
        assert units["a"].status is units["b"].status is UnitStatus.ROUTING


class TestRuntimeState:
    def test_state_has_no_rng_and_commit_preserves_view_identity(self) -> None:
        runtime, _bus, units = _runtime({"u1": MoraleState.STEADY})
        states_view = runtime.states
        records_view = runtime.records
        state = runtime.get_state()
        assert set(state) == {"active_records", "suspended_archives"}
        runtime.set_state(
            state,
            expected_units=units,
            elapsed_time_s=0.0,
        )
        assert runtime.states is states_view
        assert runtime.records is records_view

    def test_commit_revalidates_substituted_unit_before_mutation(self) -> None:
        runtime, _bus, units = _runtime({"u1": MoraleState.STEADY})
        before = runtime.get_state()
        plan = runtime.stage_state(
            before,
            expected_units=units,
            elapsed_time_s=0.0,
        )
        substitute = _unit("u1", status=UnitStatus.ROUTING)

        with pytest.raises(ValueError, match="morale/status disagree"):
            runtime.commit_state(
                plan,
                units={"u1": substitute},
                elapsed_time_s=0.0,
                aggregate_constituents={},
                suspended_statuses={},
            )

        assert runtime.get_state() == before
        runtime.validate_bindings(units)

    def test_commit_rejects_forged_duplicate_records_atomically(self) -> None:
        runtime, _bus, units = _runtime({"u1": MoraleState.STEADY})
        before = runtime.get_state()
        plan = runtime.stage_state(
            before,
            expected_units=units,
            elapsed_time_s=0.0,
        )
        forged = replace(
            plan,
            active_records=(
                ("u1", MoraleStateRecord(MoraleState.STEADY)),
                ("u1", MoraleStateRecord(MoraleState.SHAKEN)),
            ),
        )

        with pytest.raises(ValueError, match="canonical unique"):
            runtime.commit_state(
                forged,
                units=units,
                elapsed_time_s=0.0,
                aggregate_constituents={},
                suspended_statuses={},
            )

        assert runtime.get_state() == before
        runtime.validate_bindings(units)

    def test_rejects_noncanonical_archive_baseline(self) -> None:
        runtime, _bus, _units = _runtime({})
        proxy = _unit("agg")
        steady = {
            "current_state": 0,
            "last_transition_time_s": None,
            "last_check_time_s": None,
            "generation": 0,
        }
        shaken = {**steady, "current_state": 1}
        state = {
            "active_records": {"agg": shaken},
            "suspended_archives": {
                "agg": {
                    "proxy_baseline": steady,
                    "constituent_records": {
                        "a": steady,
                        "b": shaken,
                    },
                },
            },
        }
        with pytest.raises(ValueError, match="canonical"):
            runtime.stage_state(
                state,
                expected_units={"agg": proxy},
                elapsed_time_s=0.0,
                aggregate_constituents={"agg": ("a", "b")},
            )


class TestAggregationTransactions:
    def test_prepare_rejects_terminal_proxy_without_mutation(self) -> None:
        runtime, _bus, _units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.STEADY,
        })
        proxy = _unit("agg", status=UnitStatus.DESTROYED)
        before = runtime.get_state()

        with pytest.raises(ValueError, match="active aggregate proxy"):
            runtime.prepare_aggregation("agg", ("a", "b"), proxy)

        assert runtime.get_state() == before
        assert proxy.status is UnitStatus.DESTROYED

    def test_prepare_disaggregation_rejects_terminal_restored_unit(
        self,
    ) -> None:
        runtime, _bus, _units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.SHAKEN,
        })
        proxy = _unit("agg")
        runtime.commit_aggregation(
            runtime.prepare_aggregation("agg", ("a", "b"), proxy),
        )
        restored = {
            "a": _unit("a", status=UnitStatus.DESTROYED),
            "b": _unit("b"),
        }
        before = runtime.get_state()

        with pytest.raises(ValueError, match="active restored unit"):
            runtime.prepare_disaggregation("agg", restored)

        assert runtime.get_state() == before
        assert restored["a"].status is UnitStatus.DESTROYED

    def test_prepare_disaggregation_rejects_terminal_proxy(self) -> None:
        runtime, _bus, _units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.SHAKEN,
        })
        proxy = _unit("agg")
        runtime.commit_aggregation(
            runtime.prepare_aggregation("agg", ("a", "b"), proxy),
        )
        proxy.status = UnitStatus.DESTROYED
        before = runtime.get_state()
        restored = {"a": _unit("a"), "b": _unit("b")}

        with pytest.raises(ValueError, match="proxy status"):
            runtime.prepare_disaggregation("agg", restored)

        assert runtime.get_state() == before
        assert proxy.status is UnitStatus.DESTROYED

    def test_commit_rejects_forged_proxy_archive_disagreement_atomically(
        self,
    ) -> None:
        runtime, _bus, _units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.SHAKEN,
        })
        proxy = _unit("agg")
        plan = runtime.prepare_aggregation("agg", ("a", "b"), proxy)
        forged = replace(
            plan,
            proxy_record=MoraleStateRecord(MoraleState.SURRENDERED),
        )
        before = runtime.get_state()

        with pytest.raises(ValueError, match="self-consistent"):
            runtime.commit_aggregation(forged)

        assert runtime.get_state() == before
        assert proxy.status is UnitStatus.ACTIVE

    def test_commit_revalidates_constituent_status_before_mutation(self) -> None:
        runtime, _bus, units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.SHAKEN,
        })
        proxy = _unit("agg")
        plan = runtime.prepare_aggregation("agg", ("a", "b"), proxy)
        before = runtime.get_state()
        units["a"].status = UnitStatus.ROUTING

        with pytest.raises(ValueError, match="aggregation plan is stale"):
            runtime.commit_aggregation(plan)

        assert runtime.get_state() == before
        assert set(runtime.states) == {"a", "b"}
        assert "agg" not in runtime.states

    def test_commit_revalidates_restored_unit_after_disaggregation_plan(
        self,
    ) -> None:
        runtime, _bus, _units = _runtime({
            "a": MoraleState.STEADY,
            "b": MoraleState.SHAKEN,
        })
        proxy = _unit("agg")
        aggregate_plan = runtime.prepare_aggregation(
            "agg",
            ("a", "b"),
            proxy,
        )
        runtime.commit_aggregation(aggregate_plan)
        restored = {"a": _unit("a"), "b": _unit("b")}
        plan = runtime.prepare_disaggregation("agg", restored)
        before = runtime.get_state()
        restored["a"].entity_id = "substituted"

        with pytest.raises(ValueError, match="disaggregation plan is stale"):
            runtime.commit_disaggregation(plan)

        assert runtime.get_state() == before
        assert set(runtime.states) == {"agg"}
