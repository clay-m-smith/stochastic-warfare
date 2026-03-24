"""Unit tests for GasWarfareEngine — wind checks, delivery, MOPP mapping."""

from __future__ import annotations


from stochastic_warfare.combat.gas_warfare import (
    GasMaskType,
    GasWarfareConfig,
    GasWarfareEngine,
)

from .conftest import _rng


def _make_engine(seed: int = 42, **cfg_kwargs) -> GasWarfareEngine:
    config = GasWarfareConfig(**cfg_kwargs) if cfg_kwargs else None
    return GasWarfareEngine(config=config, rng=_rng(seed))


# ---------------------------------------------------------------------------
# Wind favorable checks
# ---------------------------------------------------------------------------


class TestWindFavorable:
    """Wind direction and speed checks for cylinder release."""

    def test_favorable_wind(self):
        """Wind FROM south (180) -> gas travels north (0) -> target at north (0) is favorable."""
        eng = _make_engine()
        assert eng.check_wind_favorable(
            wind_speed_mps=3.0,
            wind_dir_deg=180.0,
            target_bearing_deg=0.0,
        ) is True

    def test_unfavorable_wind_direction(self):
        """Wind FROM north (0) -> gas travels south (180) -> target at north (0) is unfavorable."""
        eng = _make_engine()
        assert eng.check_wind_favorable(
            wind_speed_mps=3.0,
            wind_dir_deg=0.0,
            target_bearing_deg=0.0,
        ) is False

    def test_wind_too_slow(self):
        """Below minimum wind speed, release is unfavorable."""
        eng = _make_engine(min_wind_speed_mps=1.0)
        assert eng.check_wind_favorable(
            wind_speed_mps=0.5,
            wind_dir_deg=180.0,
            target_bearing_deg=0.0,
        ) is False

    def test_wind_too_fast(self):
        """Above maximum wind speed, release is unfavorable."""
        eng = _make_engine(max_wind_speed_mps=6.0)
        assert eng.check_wind_favorable(
            wind_speed_mps=10.0,
            wind_dir_deg=180.0,
            target_bearing_deg=0.0,
        ) is False

    def test_wind_at_max_angle_boundary(self):
        """Wind at exactly max_wind_angle_deg is still favorable."""
        eng = _make_engine(max_wind_angle_deg=60.0)
        # Wind FROM 180 -> gas goes 0. Target at 60 degrees offset.
        result = eng.check_wind_favorable(
            wind_speed_mps=3.0,
            wind_dir_deg=180.0,
            target_bearing_deg=60.0,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Delivery methods (without CBRN engine)
# ---------------------------------------------------------------------------


class TestDeliveryNoCBRN:
    """Delivery methods safely skip without a CBRN engine."""

    def test_cylinder_release_no_cbrn(self):
        eng = _make_engine()
        puff_ids = eng.execute_cylinder_release(
            agent_id="chlorine",
            front_start=(0.0, 0.0),
            front_end=(100.0, 0.0),
            wind_speed_mps=3.0,
        )
        assert isinstance(puff_ids, list)
        assert len(puff_ids) == 0

    def test_gas_bombardment_no_cbrn(self):
        eng = _make_engine()
        puff_ids = eng.execute_gas_bombardment(
            agent_id="phosgene",
            target_easting=1000.0,
            target_northing=2000.0,
            num_shells=20,
        )
        assert isinstance(puff_ids, list)
        assert len(puff_ids) == 0


# ---------------------------------------------------------------------------
# Gas mask -> MOPP mapping
# ---------------------------------------------------------------------------


class TestGasMaskMOPP:
    """Gas mask type maps to correct MOPP level."""

    def test_sbr_mopp_3(self):
        eng = _make_engine()
        mopp = eng.set_unit_gas_mask("u1", GasMaskType.SMALL_BOX_RESPIRATOR)
        assert mopp == 3

    def test_ph_helmet_mopp_2(self):
        eng = _make_engine()
        mopp = eng.set_unit_gas_mask("u1", GasMaskType.PH_HELMET)
        assert mopp == 2

    def test_improvised_cloth_mopp_1(self):
        eng = _make_engine()
        mopp = eng.set_unit_gas_mask("u1", GasMaskType.IMPROVISED_CLOTH)
        assert mopp == 1

    def test_no_mask_mopp_0(self):
        eng = _make_engine()
        mopp = eng.get_unit_mopp_level("unmasked_unit")
        assert mopp == 0

    def test_get_unit_mopp_level_after_set(self):
        eng = _make_engine()
        eng.set_unit_gas_mask("u1", GasMaskType.PH_HELMET)
        assert eng.get_unit_mopp_level("u1") == 2


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestGasWarfareStateRoundtrip:
    """State persistence."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=55)
        eng.set_unit_gas_mask("u1", GasMaskType.SMALL_BOX_RESPIRATOR)
        eng.set_unit_gas_mask("u2", GasMaskType.PH_HELMET)
        state = eng.get_state()

        eng2 = _make_engine(seed=1)
        eng2.set_state(state)
        assert eng2.get_unit_mopp_level("u1") == 3
        assert eng2.get_unit_mopp_level("u2") == 2
