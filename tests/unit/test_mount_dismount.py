"""Tests for movement/mount_dismount.py."""

from types import SimpleNamespace

from stochastic_warfare.movement.mount_dismount import (
    MountDismountManager,
    MountState,
)


def _make_unit(mounted: bool = True) -> SimpleNamespace:
    return SimpleNamespace(entity_id="u1", mounted=mounted)


class TestTransitionTime:
    def test_dismount(self) -> None:
        mgr = MountDismountManager()
        t = mgr.transition_time(_make_unit(), "dismount")
        assert t == 30.0

    def test_mount(self) -> None:
        mgr = MountDismountManager()
        t = mgr.transition_time(_make_unit(), "mount")
        assert t == 45.0


class TestBeginDismount:
    def test_starts_dismounting(self) -> None:
        mgr = MountDismountManager()
        result = mgr.begin_dismount(_make_unit())
        assert result.new_state == MountState.DISMOUNTING
        assert result.complete is False


class TestBeginMount:
    def test_starts_mounting(self) -> None:
        mgr = MountDismountManager()
        result = mgr.begin_mount(_make_unit(mounted=False))
        assert result.new_state == MountState.MOUNTING
        assert result.complete is False


class TestUpdate:
    def test_no_transition(self) -> None:
        mgr = MountDismountManager()
        u = _make_unit(mounted=True)
        result = mgr.update(u, 10.0)
        assert result.new_state == MountState.MOUNTED
        assert result.complete is True

    def test_dismount_partial(self) -> None:
        mgr = MountDismountManager()
        u = _make_unit(mounted=True)
        mgr.begin_dismount(u)
        result = mgr.update(u, 15.0)
        assert result.new_state == MountState.DISMOUNTING
        assert result.complete is False

    def test_dismount_complete(self) -> None:
        mgr = MountDismountManager()
        u = _make_unit(mounted=True)
        mgr.begin_dismount(u)
        result = mgr.update(u, 35.0)
        assert result.new_state == MountState.DISMOUNTED
        assert result.complete is True

    def test_mount_complete(self) -> None:
        mgr = MountDismountManager()
        u = _make_unit(mounted=False)
        mgr.begin_mount(u)
        result = mgr.update(u, 50.0)
        assert result.new_state == MountState.MOUNTED
        assert result.complete is True


class TestMountDismountState:
    def test_roundtrip(self) -> None:
        mgr = MountDismountManager()
        u = _make_unit()
        mgr.begin_dismount(u)
        mgr.update(u, 10.0)

        state = mgr.get_state()
        restored = MountDismountManager()
        restored.set_state(state)

        assert restored._progress == mgr._progress
