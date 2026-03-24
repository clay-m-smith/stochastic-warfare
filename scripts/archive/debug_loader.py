"""Debug UnitLoader."""
import logging
logging.basicConfig(level=logging.DEBUG)

from pathlib import Path
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position

# Load ALL units
ul = UnitLoader(Path("data/units"))
ul.load_all()
print(f"Types: {sorted(ul.available_types())}")

# Try creating m3a2_bradley
rng = RNGManager(42).get_stream(ModuleId.ENTITIES)
try:
    u = ul.create_unit("m3a2_bradley", "test", Position(0, 0), "blue", rng)
    print(f"Created: {u.entity_id} {u.unit_type}")
except Exception as e:
    print(f"Error creating m3a2_bradley: {e}")

# Try bmp1
try:
    u = ul.create_unit("bmp1", "test2", Position(0, 0), "red", rng)
    print(f"Created: {u.entity_id} {u.unit_type}")
except Exception as e:
    print(f"Error creating bmp1: {e}")
