"""Phase 13b-1: Numba utils infrastructure tests."""

import pytest

from stochastic_warfare.core.numba_utils import NUMBA_AVAILABLE, optional_jit


class TestOptionalJit:
    def test_decorator_no_args(self):
        """@optional_jit without parentheses returns callable."""
        @optional_jit
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_decorator_with_args(self):
        """@optional_jit(...) with parentheses returns callable."""
        @optional_jit(cache=False)
        def multiply(a, b):
            return a * b

        assert multiply(3, 4) == 12

    def test_numba_available_flag(self):
        """NUMBA_AVAILABLE is a bool."""
        assert isinstance(NUMBA_AVAILABLE, bool)

    def test_decorated_function_preserves_result(self):
        """Decorated function computes correct result."""
        @optional_jit
        def dot(x, y):
            s = 0.0
            for i in range(len(x)):
                s += x[i] * y[i]
            return s

        # Use plain lists (works with or without Numba)
        result = dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
        assert abs(result - 32.0) < 1e-10

    def test_identity_behavior_without_numba(self):
        """Without Numba, decorator should be identity."""
        if NUMBA_AVAILABLE:
            pytest.skip("Numba is installed — cannot test fallback path")

        def raw_func(x):
            return x * 2

        wrapped = optional_jit(raw_func)
        assert wrapped is raw_func
