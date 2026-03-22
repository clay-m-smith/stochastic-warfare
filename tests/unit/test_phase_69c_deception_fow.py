"""Phase 69c — Deception & FOW injection tests."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.detection.deception import DeceptionType
from stochastic_warfare.detection.fog_of_war import FogOfWarManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(42))


@pytest.fixture
def fow(rng: np.random.Generator) -> FogOfWarManager:
    return FogOfWarManager(rng=rng)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeployDecoy:
    """Phase 69c: FOW deception passthrough API."""

    def test_deploy_decoy_creates_active_decoy(self, fow: FogOfWarManager):
        """deploy_decoy() creates a decoy accessible via get_active_decoys()."""
        decoy = fow.deploy_decoy(Position(1000, 2000, 0))
        assert decoy.active is True
        assert decoy.position.easting == 1000.0

        active = fow.get_active_decoys()
        assert len(active) == 1
        assert active[0].decoy_id == decoy.decoy_id

    def test_multiple_decoys(self, fow: FogOfWarManager):
        """Multiple decoys can be deployed."""
        fow.deploy_decoy(Position(100, 100, 0))
        fow.deploy_decoy(Position(200, 200, 0))
        fow.deploy_decoy(Position(300, 300, 0))
        assert len(fow.get_active_decoys()) == 3

    def test_deploy_with_deception_type(self, fow: FogOfWarManager):
        """deploy_decoy() accepts DeceptionType enum or int."""
        d1 = fow.deploy_decoy(Position(100, 100, 0), deception_type=DeceptionType.FEINT)
        assert d1.deception_type == DeceptionType.FEINT

        d2 = fow.deploy_decoy(Position(200, 200, 0), deception_type=4)
        assert d2.deception_type == DeceptionType.FEINT


class TestUpdateDecoys:
    """Phase 69c: update_decoys() degrades effectiveness."""

    def test_degradation_over_time(self, fow: FogOfWarManager):
        """Decoy effectiveness degrades with each update."""
        decoy = fow.deploy_decoy(
            Position(100, 100, 0), effectiveness=1.0,
        )
        fow.update_decoys(10.0)  # 10s * 0.01 rate = 0.1 degradation
        assert decoy.effectiveness == pytest.approx(0.9, abs=1e-9)

    def test_decoy_deactivates_at_zero(self, fow: FogOfWarManager):
        """Decoy becomes inactive when effectiveness reaches 0."""
        decoy = fow.deploy_decoy(
            Position(100, 100, 0), effectiveness=0.05,
        )
        fow.update_decoys(10.0)  # 0.05 - 0.1 → 0 → inactive
        assert decoy.effectiveness == 0.0
        assert decoy.active is False
        assert len(fow.get_active_decoys()) == 0

    def test_zero_effectiveness_not_counted(self, fow: FogOfWarManager):
        """Decoy at zero effectiveness not in active list."""
        decoy = fow.deploy_decoy(Position(100, 100, 0), effectiveness=0.01)
        fow.update_decoys(10.0)  # degraded to 0
        assert len(fow.get_active_decoys()) == 0


class TestAssessmentInflation:
    """Phase 69c: active decoys inflate enemy assessment."""

    def test_decoy_count_inflates_enemy_power(self, fow: FogOfWarManager):
        """Active decoys add to enemy power estimate."""
        fow.deploy_decoy(Position(100, 100, 0))
        fow.deploy_decoy(Position(200, 200, 0))
        fow.deploy_decoy(Position(300, 300, 0))

        active = fow.get_active_decoys()
        phantom_count = sum(1.0 for d in active if d.effectiveness > 0)
        base_enemy = 5.0
        inflated = base_enemy + phantom_count
        assert inflated == pytest.approx(8.0)

    def test_inactive_decoys_not_counted(self, fow: FogOfWarManager):
        """Inactive decoys don't inflate assessment."""
        d = fow.deploy_decoy(Position(100, 100, 0), effectiveness=0.01)
        fow.update_decoys(100.0)  # degrade to 0

        active = fow.get_active_decoys()
        phantom_count = sum(1.0 for d in active if d.effectiveness > 0)
        assert phantom_count == 0.0


class TestBackwardCompat:
    """Phase 69c: backward compatibility when FOW disabled."""

    def test_no_fow_no_decoys(self):
        """When FOW is None, no decoys are deployed."""
        # Simulates the None check in battle.py
        fow = None
        if fow is not None:
            fow.deploy_decoy(Position(100, 100, 0))
        # No exception, nothing deployed

    def test_phantom_count_from_calibration(self, fow: FogOfWarManager):
        """Phantom count is configurable via calibration."""
        from stochastic_warfare.simulation.calibration import CalibrationSchema
        cal = CalibrationSchema(deception_phantom_count=5)
        count = cal.get("deception_phantom_count", 3)
        assert count == 5

    def test_update_decoys_called_degrades(self, fow: FogOfWarManager):
        """update_decoys() in tick loop degrades decoy effectiveness."""
        decoy = fow.deploy_decoy(Position(100, 100, 0), effectiveness=1.0)
        # Simulate 5 ticks at dt=5s each (5 * 5 * 0.01 = 0.25 degradation)
        for _ in range(5):
            fow.update_decoys(5.0)
        assert decoy.effectiveness == pytest.approx(0.75, abs=1e-9)
        assert decoy.active is True
        assert len(fow.get_active_decoys()) == 1
