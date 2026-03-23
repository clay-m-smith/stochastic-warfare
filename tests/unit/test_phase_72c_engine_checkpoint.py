"""Phase 72c — Verify SimulationEngine checkpoint/restore uses NumpyEncoder.

Tests ensure:
1. checkpoint() serializes numpy arrays properly (not as strings)
2. restore() deserializes numpy arrays correctly
3. _last_ato_day is included in get_state/set_state
"""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest


class TestNumpyEncoderUsage:
    """checkpoint() uses NumpyEncoder, not default=str."""

    def test_checkpoint_source_uses_numpy_encoder(self):
        """Structural: checkpoint() uses NumpyEncoder, not default=str."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        src = inspect.getsource(SimulationEngine.checkpoint)
        assert "NumpyEncoder" in src, "checkpoint() must use NumpyEncoder"
        assert "default=str" not in src, "checkpoint() must not use default=str"

    def test_restore_source_uses_object_hook(self):
        """Structural: restore() uses _numpy_object_hook."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        src = inspect.getsource(SimulationEngine.restore)
        assert "_numpy_object_hook" in src, "restore() must use _numpy_object_hook"

    def test_numpy_encoder_roundtrip(self):
        """NumpyEncoder → _numpy_object_hook round-trips numpy arrays."""
        from stochastic_warfare.core.checkpoint import NumpyEncoder, _numpy_object_hook

        arr = np.array([1.0, 2.0, 3.0])
        data = {"test_array": arr, "scalar": np.float64(42.0)}

        encoded = json.dumps(data, cls=NumpyEncoder)
        decoded = json.loads(encoded, object_hook=_numpy_object_hook)

        np.testing.assert_array_equal(decoded["test_array"], arr)

    def test_default_str_corrupts_numpy(self):
        """Demonstrate that default=str silently corrupts numpy arrays."""
        arr = np.array([1.0, 2.0, 3.0])
        data = {"arr": arr}
        encoded = json.dumps(data, default=str)
        decoded = json.loads(encoded)
        # default=str produces something like "[1. 2. 3.]" — a string, not a list
        assert isinstance(decoded["arr"], str), "default=str converts arrays to strings"


class TestLastAtoDayState:
    """_last_ato_day is properly initialized and checkpointed."""

    def test_last_ato_day_in_get_state_source(self):
        """Structural: get_state includes last_ato_day."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        src = inspect.getsource(SimulationEngine.get_state)
        assert "last_ato_day" in src

    def test_last_ato_day_in_set_state_source(self):
        """Structural: set_state restores last_ato_day."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        src = inspect.getsource(SimulationEngine.set_state)
        assert "last_ato_day" in src

    def test_no_hasattr_pattern(self):
        """The hasattr('_last_ato_day') pattern is removed."""
        from stochastic_warfare.simulation import engine as mod
        src = inspect.getsource(mod)
        assert 'hasattr(self, "_last_ato_day")' not in src, (
            "_last_ato_day must use proper init, not hasattr guard"
        )

    def test_last_ato_day_init(self):
        """_last_ato_day is initialized in __init__ source."""
        from stochastic_warfare.simulation.engine import SimulationEngine
        src = inspect.getsource(SimulationEngine.__init__)
        assert "_last_ato_day" in src, (
            "_last_ato_day must be initialized in __init__"
        )
