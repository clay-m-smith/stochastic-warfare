"""Clone-safe non-owning bindings for authoritative runtime failure policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from weakref import WeakMethod

RuntimeFailureHandler = Callable[[str, str, Exception], bool]


class RuntimeFailurePolicyBinding:
    """Hold one bound failure handler without owning or checkpointing it.

    Legacy checkpoint preflight deep-copies complete owner graphs.  The
    binding is immutable runtime wiring rather than owner state, so isolated
    clones safely share this weak reference instead of trying to pickle the
    underlying :class:`weakref.WeakMethod`.
    """

    __slots__ = ("_weak_method",)

    def __init__(self, handler: RuntimeFailureHandler) -> None:
        if not callable(handler):
            raise TypeError("runtime failure handler must be callable")
        try:
            self._weak_method = WeakMethod(handler)
        except TypeError as exc:
            raise TypeError(
                "runtime failure handler must be a bound method",
            ) from exc

    def resolve(self) -> RuntimeFailureHandler | None:
        """Return the live handler, or ``None`` after its owner is gone."""
        return cast(RuntimeFailureHandler | None, self._weak_method())

    def __deepcopy__(
        self,
        memo: dict[int, object],
    ) -> RuntimeFailurePolicyBinding:
        """Keep non-checkpoint runtime wiring out of isolated owner state."""
        memo[id(self)] = self
        return self
