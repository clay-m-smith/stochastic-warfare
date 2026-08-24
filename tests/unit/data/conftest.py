"""Transparent, domain-local fixtures for repository data-catalog tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.entities.loader import UnitLoader
from tests.unit.data.historical_catalog_support import (
    HistoricalEraCatalogs,
    load_historical_era_catalogs,
)


DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@pytest.fixture(scope="module")
def unit_loader() -> UnitLoader:
    """Load the base unit catalog for one consuming test module."""
    loader = UnitLoader(DATA_DIR / "units")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def weapon_loader() -> WeaponLoader:
    """Load the base weapon catalog for one consuming test module."""
    loader = WeaponLoader(DATA_DIR / "weapons")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def ammo_loader() -> AmmoLoader:
    """Load the base ammunition catalog for one consuming test module."""
    loader = AmmoLoader(DATA_DIR / "ammunition")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sensor_loader() -> SensorLoader:
    """Load the base sensor catalog for one consuming test module."""
    loader = SensorLoader(DATA_DIR / "sensors")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def sig_loader() -> SignatureLoader:
    """Load the base signature catalog for one consuming test module."""
    loader = SignatureLoader(DATA_DIR / "signatures")
    loader.load_all()
    return loader


@pytest.fixture(scope="module")
def historical_era_catalogs(request: pytest.FixtureRequest) -> HistoricalEraCatalogs:
    """Load the era explicitly owned by the consuming semantic test module."""
    era_name = getattr(request.module, "HISTORICAL_ERA")
    return load_historical_era_catalogs(era_name)


@pytest.fixture(scope="module")
def era_unit_loader(historical_era_catalogs: HistoricalEraCatalogs) -> UnitLoader:
    return historical_era_catalogs.units


@pytest.fixture(scope="module")
def era_weapon_loader(
    historical_era_catalogs: HistoricalEraCatalogs,
) -> WeaponLoader:
    return historical_era_catalogs.weapons


@pytest.fixture(scope="module")
def era_ammo_loader(historical_era_catalogs: HistoricalEraCatalogs) -> AmmoLoader:
    return historical_era_catalogs.ammunition


@pytest.fixture(scope="module")
def era_sensor_loader(
    historical_era_catalogs: HistoricalEraCatalogs,
) -> SensorLoader:
    return historical_era_catalogs.sensors


@pytest.fixture(scope="module")
def era_sig_loader(
    historical_era_catalogs: HistoricalEraCatalogs,
) -> SignatureLoader:
    return historical_era_catalogs.signatures
