"""Phase 84c: production engagement candidate-culling contracts."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager
from tests.unit.simulation._battle_feature_harness import (
    RecordingEngagementEngine,
    execute_engagement_side,
    make_context,
    make_unit,
    make_weapon,
)


def _route_ids(
    target_distances: tuple[float, ...],
    *,
    max_range_m: float = 3_000.0,
    mode: str = "closest",
) -> list[str]:
    attacker = make_unit("attacker", "blue", 0.0)
    targets = [
        make_unit(f"target-{index}", "red", distance)
        for index, distance in enumerate(target_distances)
    ]
    weapon, ammunition = make_weapon(max_range_m=max_range_m)
    recorder = RecordingEngagementEngine()
    context = make_context(
        {"blue": [attacker], "red": targets},
        unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
        calibration={
            "target_selection_mode": mode,
            "visibility_m": max(max_range_m, 1.0),
        },
        engagement_engine=recorder,
    )

    execute_engagement_side(
        BattleManager(EventBus()),
        context,
        "blue",
        targets,
    )
    return [call["target_id"] for call in recorder.calls]


class TestEngagementCulling:
    """Candidate filtering is observed through the live engagement executor."""

    @pytest.mark.parametrize(
        ("distance", "expected"),
        [
            (3_000.0, ["target-0"]),
            (np.nextafter(3_000.0, np.inf), []),
        ],
    )
    def test_weapon_range_is_closed_at_the_production_boundary(
        self,
        distance: float,
        expected: list[str],
    ) -> None:
        assert _route_ids((distance,)) == expected

    def test_unreachable_high_value_target_cannot_starve_a_live_candidate(
        self,
    ) -> None:
        attacker = make_unit("attacker", "blue", 0.0)
        reachable = make_unit("reachable", "red", 1_000.0)
        unreachable_hq = make_unit("unreachable-hq", "red", 5_000.0)
        object.__setattr__(
            unreachable_hq,
            "support_type",
            SimpleNamespace(name="HQ"),
        )
        weapon, ammunition = make_weapon(max_range_m=3_000.0)
        recorder = RecordingEngagementEngine()
        context = make_context(
            {"blue": [attacker], "red": [reachable, unreachable_hq]},
            unit_weapons={attacker.entity_id: [(weapon, ammunition)]},
            calibration={"visibility_m": 6_000.0},
            engagement_engine=recorder,
        )

        execute_engagement_side(
            BattleManager(EventBus()),
            context,
            "blue",
            [reachable, unreachable_hq],
        )

        assert [call["target_id"] for call in recorder.calls] == ["reachable"]

    @pytest.mark.parametrize(
        "distances",
        [(2_000.0, 500.0, 1_000.0), (1_000.0, 500.0, 2_000.0)],
    )
    def test_closest_selection_is_stable_across_candidate_order(
        self,
        distances: tuple[float, ...],
    ) -> None:
        selected = _route_ids(distances)
        selected_distance = distances[int(selected[0].removeprefix("target-"))]
        assert selected_distance == 500.0

    def test_each_side_uses_its_own_live_enemy_topology(self) -> None:
        blue = make_unit("blue", "blue", 0.0)
        red = make_unit("red", "red", 500.0)
        blue_weapon, blue_ammunition = make_weapon(weapon_id="blue-gun")
        red_weapon, red_ammunition = make_weapon(weapon_id="red-gun")
        recorder = RecordingEngagementEngine()
        context = make_context(
            {"blue": [blue], "red": [red]},
            unit_weapons={
                blue.entity_id: [(blue_weapon, blue_ammunition)],
                red.entity_id: [(red_weapon, red_ammunition)],
            },
            calibration={"visibility_m": 1_000.0},
            engagement_engine=recorder,
        )
        manager = BattleManager(EventBus())

        execute_engagement_side(manager, context, "blue", [red])
        execute_engagement_side(manager, context, "red", [blue])

        assert [call["target_id"] for call in recorder.calls] == ["red", "blue"]

    def test_attacker_without_live_weapons_never_routes_an_engagement(self) -> None:
        attacker = make_unit("attacker", "blue", 0.0)
        target = make_unit("target", "red", 500.0)
        recorder = RecordingEngagementEngine()
        context = make_context(
            {"blue": [attacker], "red": [target]},
            unit_weapons={attacker.entity_id: []},
            calibration={"visibility_m": 1_000.0},
            engagement_engine=recorder,
        )

        engagements = execute_engagement_side(
            BattleManager(EventBus()),
            context,
            "blue",
            [target],
        )

        assert engagements == []
        assert recorder.calls == []
