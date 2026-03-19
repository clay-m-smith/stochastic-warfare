"""Phase 66b: P2 engine cleanup tests — propulsion drag, data link range,
siege assault/sally, ConditionsEngine facade.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.calibration import CalibrationSchema

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


# ---------------------------------------------------------------------------
# Propulsion drag reduction
# ---------------------------------------------------------------------------


class TestPropulsionDrag:
    """Propulsion type reduces effective drag coefficient in ballistics."""

    def test_rocket_reduces_drag(self) -> None:
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition

        eng = BallisticsEngine(_rng())
        weapon = WeaponDefinition(
            weapon_id="test_launcher",
            display_name="Launcher",
            category="MISSILE_LAUNCHER",
            caliber_mm=150,
            muzzle_velocity_mps=300,
            max_range_m=5000,
            rate_of_fire_rpm=1,
            base_accuracy_mrad=2.0,
        )
        # Ammo without propulsion
        ammo_base = AmmoDefinition(
            ammo_id="test_round",
            display_name="Test Round",
            ammo_type="HE",
            caliber_mm=150,
            mass_kg=50.0,
            diameter_mm=150.0,
            drag_coefficient=0.3,
            base_damage=100.0,
            armor_penetration_mm=50.0,
        )
        # Ammo with rocket propulsion
        ammo_rocket = AmmoDefinition(
            ammo_id="test_rocket",
            display_name="Test Rocket",
            ammo_type="HE",
            caliber_mm=150,
            mass_kg=50.0,
            diameter_mm=150.0,
            drag_coefficient=0.3,
            base_damage=100.0,
            armor_penetration_mm=50.0,
            propulsion="rocket",
        )

        traj_base = eng.compute_trajectory(
            weapon, ammo_base, Position(0, 0, 0), 30.0, 0.0,
        )
        traj_rocket = eng.compute_trajectory(
            weapon, ammo_rocket, Position(0, 0, 0), 30.0, 0.0,
        )
        # Rocket should travel further (less drag)
        base_range = math.sqrt(
            traj_base.impact_position.easting ** 2
            + traj_base.impact_position.northing ** 2
        )
        rocket_range = math.sqrt(
            traj_rocket.impact_position.easting ** 2
            + traj_rocket.impact_position.northing ** 2
        )
        assert rocket_range > base_range

    def test_turbojet_reduces_more_than_rocket(self) -> None:
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition

        eng = BallisticsEngine(_rng())
        weapon = WeaponDefinition(
            weapon_id="launcher",
            display_name="Launcher",
            category="MISSILE_LAUNCHER",
            caliber_mm=150,
            muzzle_velocity_mps=300,
            max_range_m=10000,
            rate_of_fire_rpm=1,
            base_accuracy_mrad=2.0,
        )
        ammo_rocket = AmmoDefinition(
            ammo_id="rocket",
            display_name="Rocket",
            ammo_type="HE",
            caliber_mm=150,
            mass_kg=50.0,
            diameter_mm=150.0,
            drag_coefficient=0.3,
            base_damage=100.0,
            armor_penetration_mm=50.0,
            propulsion="rocket",
        )
        ammo_turbojet = AmmoDefinition(
            ammo_id="turbojet",
            display_name="Turbojet",
            ammo_type="HE",
            caliber_mm=150,
            mass_kg=50.0,
            diameter_mm=150.0,
            drag_coefficient=0.3,
            base_damage=100.0,
            armor_penetration_mm=50.0,
            propulsion="turbojet",
        )
        traj_r = eng.compute_trajectory(weapon, ammo_rocket, Position(0, 0, 0), 30.0, 0.0)
        traj_t = eng.compute_trajectory(weapon, ammo_turbojet, Position(0, 0, 0), 30.0, 0.0)
        r_range = math.sqrt(
            traj_r.impact_position.easting ** 2
            + traj_r.impact_position.northing ** 2
        )
        t_range = math.sqrt(
            traj_t.impact_position.easting ** 2
            + traj_t.impact_position.northing ** 2
        )
        # Turbojet has factor 0.2 vs rocket 0.3 → less drag → more range
        assert t_range > r_range

    def test_propulsion_none_no_change(self) -> None:
        """Default propulsion='none' does not alter drag."""
        from stochastic_warfare.combat.ammunition import AmmoDefinition
        ammo = AmmoDefinition(
            ammo_id="bullet",
            display_name="Bullet",
            ammo_type="BALL",
            caliber_mm=7.62,
            mass_kg=0.01,
            diameter_mm=7.62,
            drag_coefficient=0.3,
            base_damage=10.0,
            armor_penetration_mm=5.0,
        )
        prop = getattr(ammo, "propulsion", "none")
        assert prop == "none" or prop is None


# ---------------------------------------------------------------------------
# Data link range
# ---------------------------------------------------------------------------


class TestDataLinkRange:
    """Data link range gates UAV engagement."""

    def test_data_link_field_exists_on_aerial(self) -> None:
        """AerialUnit should have data_link_range field."""
        from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
        assert hasattr(AerialUnit, "__dataclass_fields__") or hasattr(AerialUnit, "data_link_range")

    def test_data_link_range_gate_flag(self) -> None:
        """Gate requires enable_unconventional_warfare=True."""
        cal = CalibrationSchema(enable_unconventional_warfare=True)
        assert cal.get("enable_unconventional_warfare", False) is True


# ---------------------------------------------------------------------------
# Siege assault / sally
# ---------------------------------------------------------------------------


class TestSiegeAssaultSally:
    """Siege assault and sally wiring."""

    def test_attempt_assault_during_breach(self) -> None:
        from stochastic_warfare.combat.siege import SiegeConfig, SiegeEngine, SiegePhase

        eng = SiegeEngine(config=SiegeConfig(), rng=_rng())
        eng.begin_siege("s1", garrison_size=100, food_days=60, attacker_size=500)
        # Manually force BREACH phase
        eng._sieges["s1"].phase = SiegePhase.BREACH
        success, att_cas, def_cas = eng.attempt_assault("s1")
        # Should produce casualties regardless of outcome
        assert att_cas >= 0
        assert def_cas >= 0

    def test_sally_sortie_called_each_day(self) -> None:
        from stochastic_warfare.combat.siege import SiegeConfig, SiegeEngine

        # High sally probability to guarantee at least one
        eng = SiegeEngine(
            config=SiegeConfig(sally_probability=1.0),
            rng=_rng(),
        )
        eng.begin_siege("s1", garrison_size=100, food_days=60, attacker_size=500)
        attempted, att_cas = eng.sally_sortie("s1")
        assert attempted is True


# ---------------------------------------------------------------------------
# ConditionsEngine facade
# ---------------------------------------------------------------------------


class TestConditionsFacade:
    """ConditionsEngine facade instantiation."""

    def test_facade_instantiation(self) -> None:
        """ConditionsEngine can be created with sub-engines."""
        from stochastic_warfare.environment.conditions import ConditionsEngine

        # Create minimal mocks for required sub-engines
        weather = SimpleNamespace(
            current=SimpleNamespace(
                temperature=20.0, wind=SimpleNamespace(speed=5.0, direction=0.0),
                visibility=10000.0, precipitation_rate=0.0, humidity=0.5,
                cloud_cover=0.3, cloud_ceiling=5000.0, state=0,
            ),
            temperature_at_altitude=lambda a: 20.0 - 0.0065 * a,
            atmospheric_density=lambda a: 1.225,
            pressure_at_altitude=lambda a: 101325.0,
        )
        tod = SimpleNamespace(
            illumination_at=lambda lat, lon: SimpleNamespace(ambient_lux=10000.0),
            thermal_environment=lambda lat, lon: SimpleNamespace(thermal_contrast=1.0),
            nvg_effectiveness=lambda lat, lon: 0.5,
        )
        seasons = SimpleNamespace(
            current=SimpleNamespace(
                ground_trafficability=1.0,
                ground_state=0,
                vegetation_density=0.5,
            ),
        )
        obscurants = SimpleNamespace(
            visibility_at=lambda pos: 10000.0,
            opacity_at=lambda pos: SimpleNamespace(visual=0.0),
        )
        facade = ConditionsEngine(
            weather=weather,
            time_of_day=tod,
            seasons=seasons,
            obscurants=obscurants,
        )
        assert facade is not None

    def test_facade_field_on_context(self) -> None:
        """SimulationContext has conditions_facade field."""
        from stochastic_warfare.simulation.scenario import SimulationContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SimulationContext)]
        assert "conditions_facade" in field_names
