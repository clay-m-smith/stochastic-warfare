"""Quick check that all YAML data files load correctly."""
from pathlib import Path
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.combat.ammunition import WeaponLoader, AmmoLoader
from stochastic_warfare.detection.signatures import SignatureLoader
from stochastic_warfare.detection.sensors import SensorLoader

data = Path("data")

ul = UnitLoader(data / "units")
ul.load_all()
print(f"Units loaded: {len(ul.available_types())}")
for t in sorted(ul.available_types()):
    print(f"  {t}")

wl = WeaponLoader(data / "weapons")
wl.load_all()
print(f"Weapons loaded: {len(wl.available_weapons())}")

al = AmmoLoader(data / "ammunition")
al.load_all()
print(f"Ammo loaded: {len(al.available_ammo())}")

sl = SignatureLoader(data / "signatures")
sl.load_all()
print(f"Signatures loaded: {len(sl.available_profiles())}")

snl = SensorLoader(data / "sensors")
snl.load_all()
print(f"Sensors loaded: {len(snl.available_sensors())}")

print("\nAll YAML files loaded successfully!")
