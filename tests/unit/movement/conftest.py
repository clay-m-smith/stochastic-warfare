"""Shared fixtures and factory functions for movement domain unit tests."""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# RNG helper
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    """Create a deterministic PRNG."""
    return np.random.Generator(np.random.PCG64(seed))
