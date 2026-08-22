"""Phase 72c JSON serialization guard.

Production checkpoint encoding, strict decoding, atomic restoration, and
continuation are covered by the checkpoint and Phase 118 decoder suites.
"""

from __future__ import annotations

import json

import numpy as np


class TestNumpyEncoderUsage:
    """Demonstrate why generic string fallback is not a checkpoint codec."""

    def test_default_str_corrupts_numpy(self):
        """Demonstrate that default=str silently corrupts numpy arrays."""
        arr = np.array([1.0, 2.0, 3.0])
        data = {"arr": arr}
        encoded = json.dumps(data, default=str)
        decoded = json.loads(encoded)
        # default=str produces something like "[1. 2. 3.]" — a string, not a list
        assert isinstance(decoded["arr"], str), "default=str converts arrays to strings"
