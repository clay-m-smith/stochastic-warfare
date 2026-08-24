"""Typed, explicit loader bundle for historical-era catalog tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
from stochastic_warfare.detection.sensors import SensorLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.entities.loader import UnitLoader


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ERA_DATA_DIR = DATA_DIR / "eras"


@dataclass(frozen=True)
class HistoricalEraCatalogs:
    """The five merged catalogs exercised by each historical-era test module."""

    units: UnitLoader
    weapons: WeaponLoader
    ammunition: AmmoLoader
    sensors: SensorLoader
    signatures: SignatureLoader


def load_historical_era_catalogs(era_name: str) -> HistoricalEraCatalogs:
    """Load base catalogs overlaid by one explicit historical-era directory."""
    era_dir = ERA_DATA_DIR / era_name

    units = UnitLoader(DATA_DIR / "units")
    units.load_all()
    era_units = UnitLoader(era_dir / "units")
    era_units.load_all()
    units._definitions.update(era_units._definitions)

    weapons = WeaponLoader(DATA_DIR / "weapons")
    weapons.load_all()
    era_weapons = WeaponLoader(era_dir / "weapons")
    era_weapons.load_all()
    weapons._definitions.update(era_weapons._definitions)

    ammunition = AmmoLoader(DATA_DIR / "ammunition")
    ammunition.load_all()
    era_ammunition = AmmoLoader(era_dir / "ammunition")
    era_ammunition.load_all()
    ammunition._definitions.update(era_ammunition._definitions)

    sensors = SensorLoader(DATA_DIR / "sensors")
    sensors.load_all()
    era_sensors = SensorLoader(era_dir / "sensors")
    era_sensors.load_all()
    sensors._definitions.update(era_sensors._definitions)

    signatures = SignatureLoader(DATA_DIR / "signatures")
    signatures.load_all()
    era_signatures = SignatureLoader(era_dir / "signatures")
    era_signatures.load_all()
    signatures._profiles.update(era_signatures._profiles)

    return HistoricalEraCatalogs(
        units=units,
        weapons=weapons,
        ammunition=ammunition,
        sensors=sensors,
        signatures=signatures,
    )
