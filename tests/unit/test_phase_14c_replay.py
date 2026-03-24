"""Tests for Phase 14c: battle replay animation."""

from __future__ import annotations


from stochastic_warfare.tools.replay import (
    EngagementFrame,
    ReplayConfig,
    ReplayFrame,
    UnitFrame,
    create_replay,
    extract_replay_frames,
)


# ---------------------------------------------------------------------------
# Frame extraction tests
# ---------------------------------------------------------------------------


class TestExtractReplayFrames:
    """Extract frames from snapshot data."""

    def test_basic_extraction(self) -> None:
        snapshots = [
            {
                "tick": 0,
                "units": [
                    {"unit_id": "b1", "side": "blue", "position": {"easting": 100, "northing": 200}, "active": True},
                    {"unit_id": "r1", "side": "red", "position": {"easting": 500, "northing": 500}, "active": True},
                ],
            },
            {
                "tick": 10,
                "units": [
                    {"unit_id": "b1", "side": "blue", "position": {"easting": 150, "northing": 250}, "active": True},
                    {"unit_id": "r1", "side": "red", "position": {"easting": 500, "northing": 500}, "active": False},
                ],
            },
        ]
        frames = extract_replay_frames(snapshots)
        assert len(frames) == 2
        assert frames[0].tick == 0
        assert len(frames[0].units) == 2
        assert frames[1].units[1].active is False

    def test_positions_match(self) -> None:
        snapshots = [
            {
                "tick": 0,
                "units": [{"unit_id": "b1", "side": "blue", "position": {"easting": 42.0, "northing": 99.0}, "active": True}],
            },
        ]
        frames = extract_replay_frames(snapshots)
        assert frames[0].units[0].x == 42.0
        assert frames[0].units[0].y == 99.0

    def test_engagement_extraction(self) -> None:
        snapshots = [{"tick": 5, "units": []}]
        events = [
            {"tick": 5, "attacker_x": 100, "attacker_y": 200, "target_x": 300, "target_y": 400, "result": "hit"},
        ]
        frames = extract_replay_frames(snapshots, events)
        assert len(frames[0].engagements) == 1
        assert frames[0].engagements[0].result == "hit"

    def test_empty_snapshots(self) -> None:
        frames = extract_replay_frames([])
        assert frames == []

    def test_empty_engagements(self) -> None:
        snapshots = [{"tick": 0, "units": [{"unit_id": "b1", "side": "blue", "position": {"easting": 0, "northing": 0}, "active": True}]}]
        frames = extract_replay_frames(snapshots)
        assert len(frames[0].engagements) == 0

    def test_tick_ordering(self) -> None:
        snapshots = [
            {"tick": 20, "units": []},
            {"tick": 5, "units": []},
            {"tick": 10, "units": []},
        ]
        frames = extract_replay_frames(snapshots)
        assert [f.tick for f in frames] == [5, 10, 20]


# ---------------------------------------------------------------------------
# Animation creation tests
# ---------------------------------------------------------------------------


class TestCreateReplay:
    """Animation generation."""

    def _sample_frames(self) -> list[ReplayFrame]:
        return [
            ReplayFrame(
                tick=0,
                units=[
                    UnitFrame(unit_id="b1", side="blue", x=100, y=200, active=True),
                    UnitFrame(unit_id="r1", side="red", x=500, y=500, active=True),
                ],
            ),
            ReplayFrame(
                tick=1,
                units=[
                    UnitFrame(unit_id="b1", side="blue", x=150, y=250, active=True),
                    UnitFrame(unit_id="r1", side="red", x=500, y=500, active=False),
                ],
                engagements=[
                    EngagementFrame(attacker_x=150, attacker_y=250, target_x=500, target_y=500, result="hit"),
                ],
            ),
        ]

    def test_returns_func_animation(self) -> None:
        from matplotlib.animation import FuncAnimation

        frames = self._sample_frames()
        anim = create_replay(frames)
        assert isinstance(anim, FuncAnimation)

    def test_with_terrain_extent(self) -> None:
        from matplotlib.animation import FuncAnimation

        frames = self._sample_frames()
        anim = create_replay(frames, terrain_extent=(0, 1000, 0, 1000))
        assert isinstance(anim, FuncAnimation)

    def test_config_applied(self) -> None:
        from matplotlib.animation import FuncAnimation

        frames = self._sample_frames()
        config = ReplayConfig(figsize=(8, 6), fps=5)
        anim = create_replay(frames, config=config)
        assert isinstance(anim, FuncAnimation)

    def test_empty_frames(self) -> None:
        from matplotlib.animation import FuncAnimation

        anim = create_replay([])
        assert isinstance(anim, FuncAnimation)
