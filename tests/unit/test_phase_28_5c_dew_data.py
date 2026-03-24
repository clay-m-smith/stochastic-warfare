"""Phase 28.5c — DEW YAML data loading tests.

Validates all DEW data files load through their respective loaders
without errors and pass spot-check assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import WeaponLoader, AmmoLoader
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.entities.loader import UnitLoader

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def weapon_loader() -> WeaponLoader:
    loader = WeaponLoader(DATA_DIR / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ammo_loader() -> AmmoLoader:
    loader = AmmoLoader(DATA_DIR / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def unit_loader() -> UnitLoader:
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sensor_loader() -> SensorLoader:
    loader = SensorLoader(DATA_DIR / "sensors")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sig_loader() -> SignatureLoader:
    loader = SignatureLoader(DATA_DIR / "signatures")
    loader.load_all()
    return loader


# ===========================================================================
# DEW Weapons
# ===========================================================================


DEW_WEAPON_IDS = [
    "de_shorad_50kw",
    "helios_60kw",
    "iron_beam_100kw",
    "glws_dazzler",
    "phaser_hpm",
]


class TestDEWWeapons:
    @pytest.mark.parametrize("weapon_id", DEW_WEAPON_IDS)
    def test_weapon_loads(self, weapon_loader: WeaponLoader, weapon_id: str) -> None:
        defn = weapon_loader.get_definition(weapon_id)
        assert defn.weapon_id == weapon_id

    def test_de_shorad_beam_power(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("de_shorad_50kw")
        assert defn.beam_power_kw == 50.0
        assert defn.category == "DIRECTED_ENERGY"
        assert defn.max_range_m == 5000.0

    def test_iron_beam_power(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("iron_beam_100kw")
        assert defn.beam_power_kw == 100.0
        assert defn.beam_wavelength_nm == 1064.0

    def test_helios_ship_mounted(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("helios_60kw")
        assert defn.beam_power_kw == 60.0
        assert defn.max_range_m == 10000.0

    def test_dazzler_low_power(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("glws_dazzler")
        assert defn.beam_power_kw == 0.5
        assert defn.beam_wavelength_nm == 532.0

    def test_phaser_hpm_no_laser(self, weapon_loader: WeaponLoader) -> None:
        defn = weapon_loader.get_definition("phaser_hpm")
        assert defn.beam_power_kw == 0.0
        assert defn.beam_wavelength_nm == 0.0
        assert defn.requires_deployed is True

    def test_all_dew_category(self, weapon_loader: WeaponLoader) -> None:
        for wid in DEW_WEAPON_IDS:
            defn = weapon_loader.get_definition(wid)
            assert defn.category == "DIRECTED_ENERGY", f"{wid} wrong category"


# ===========================================================================
# DEW Ammo
# ===========================================================================


DEW_AMMO_IDS = [
    "dew_50kw_charge",
    "dew_60kw_charge",
    "dew_100kw_charge",
    "dew_dazzler_charge",
    "hpm_pulse",
]


class TestDEWAmmo:
    @pytest.mark.parametrize("ammo_id", DEW_AMMO_IDS)
    def test_ammo_loads(self, ammo_loader: AmmoLoader, ammo_id: str) -> None:
        defn = ammo_loader.get_definition(ammo_id)
        assert defn.ammo_id == ammo_id

    def test_all_directed_energy_type(self, ammo_loader: AmmoLoader) -> None:
        for aid in DEW_AMMO_IDS:
            defn = ammo_loader.get_definition(aid)
            assert defn.ammo_type == "DIRECTED_ENERGY", f"{aid} wrong type"

    def test_all_zero_mass(self, ammo_loader: AmmoLoader) -> None:
        for aid in DEW_AMMO_IDS:
            defn = ammo_loader.get_definition(aid)
            assert defn.mass_kg == 0.0, f"{aid} non-zero mass"

    def test_hpm_pulse_pk(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("hpm_pulse")
        assert defn.pk_at_reference == 0.90

    def test_50kw_charge_pk(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("dew_50kw_charge")
        assert defn.pk_at_reference == 0.85

    def test_dazzler_low_cost(self, ammo_loader: AmmoLoader) -> None:
        defn = ammo_loader.get_definition("dew_dazzler_charge")
        assert defn.unit_cost_factor < 0.1


# ===========================================================================
# DEW Units
# ===========================================================================


DEW_UNIT_IDS = [
    "de_shorad",
    "iron_beam",
    "ddg_helios",
]


class TestDEWUnits:
    @pytest.mark.parametrize("unit_id", DEW_UNIT_IDS)
    def test_unit_loads(self, unit_loader: UnitLoader, unit_id: str) -> None:
        defn = unit_loader.get_definition(unit_id)
        assert defn.unit_type == unit_id

    def test_de_shorad_ad_type(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("de_shorad")
        assert defn.ad_type == "DEW"

    def test_iron_beam_ad_type(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("iron_beam")
        assert defn.ad_type == "DEW"

    def test_ddg_helios_naval(self, unit_loader: UnitLoader) -> None:
        defn = unit_loader.get_definition("ddg_helios")
        assert defn.naval_type == "DESTROYER"


# ===========================================================================
# DEW Signatures
# ===========================================================================


DEW_SIG_IDS = [
    "de_shorad",
    "iron_beam",
    "ddg_helios",
    "phaser_hpm",
    "glws_dazzler",
]


class TestDEWSignatures:
    @pytest.mark.parametrize("profile_id", DEW_SIG_IDS)
    def test_signature_loads(self, sig_loader: SignatureLoader, profile_id: str) -> None:
        defn = sig_loader.get_profile(profile_id)
        assert defn.profile_id == profile_id

    def test_phaser_em_power(self, sig_loader: SignatureLoader) -> None:
        defn = sig_loader.get_profile("phaser_hpm")
        assert defn.electromagnetic.power_dbm >= 55.0

    def test_iron_beam_high_thermal(self, sig_loader: SignatureLoader) -> None:
        defn = sig_loader.get_profile("iron_beam")
        assert defn.thermal.heat_output_kw >= 500.0

    def test_dazzler_low_signature(self, sig_loader: SignatureLoader) -> None:
        defn = sig_loader.get_profile("glws_dazzler")
        assert defn.visual.cross_section_m2 < 1.0


# ===========================================================================
# Cross-References
# ===========================================================================


class TestDEWCrossRef:
    def test_weapon_ammo_refs(self, weapon_loader: WeaponLoader, ammo_loader: AmmoLoader) -> None:
        """All DEW weapon compatible_ammo refs exist in AmmoLoader."""
        for wid in DEW_WEAPON_IDS:
            wdef = weapon_loader.get_definition(wid)
            for ammo_id in wdef.compatible_ammo:
                ammo_loader.get_definition(ammo_id)  # raises KeyError if missing

    def test_unit_signature_refs(self, sig_loader: SignatureLoader) -> None:
        """All DEW unit types have matching signatures."""
        for uid in ["de_shorad", "iron_beam", "ddg_helios"]:
            sig_loader.get_profile(uid)  # raises KeyError if missing

    def test_sensor_count(self, sensor_loader: SensorLoader) -> None:
        """DEW sensors exist."""
        lwr = sensor_loader.get_definition("laser_warning_receiver")
        assert lwr.sensor_id == "laser_warning_receiver"
        brt = sensor_loader.get_definition("beam_riding_tracker")
        assert brt.sensor_id == "beam_riding_tracker"
