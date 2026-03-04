"""Optional Numba JIT infrastructure.

Provides :func:`optional_jit`, a decorator that applies Numba's ``@njit``
when Numba is installed (via the ``perf`` optional dependency group) and
acts as an identity decorator otherwise.  This lets performance-critical
inner loops be JIT-compiled on systems with Numba without making it a
hard requirement.
"""

from __future__ import annotations

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):  # type: ignore[misc]
        """Fallback no-op decorator when Numba is not installed."""
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator


def optional_jit(func=None, *, nopython: bool = True, cache: bool = True):
    """JIT-compile with Numba if available, otherwise identity decorator.

    Can be used with or without arguments::

        @optional_jit
        def kernel(x, y): ...

        @optional_jit(cache=False)
        def another_kernel(x, y): ...
    """
    if func is not None:
        # Called as @optional_jit (no parentheses)
        return njit(nopython=nopython, cache=cache)(func) if NUMBA_AVAILABLE else func

    # Called as @optional_jit(...) (with parentheses)
    def decorator(f):
        return njit(nopython=nopython, cache=cache)(f) if NUMBA_AVAILABLE else f
    return decorator
