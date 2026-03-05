"""Campaign scenario configuration, context, and loading.

Defines the pydantic models for campaign scenario YAML files and the
:class:`SimulationContext` that holds all engines and state for an
in-progress simulation run.  :class:`ScenarioLoader` wires domain
modules together from a scenario definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, Field, field_validator

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.terrain.heightmap import Heightmap

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic config models (campaign YAML schema)
# ---------------------------------------------------------------------------


class DepotConfig(BaseModel):
    """Supply depot definition within a scenario."""

    depot_id: str
    position: list[float]  # [easting, northing]
    capacity_tons: float = 1000.0
    throughput_tons_per_hour: float = 50.0

    @field_validator("position")
    @classmethod
    def _two_coords(cls, v: list[float]) -> list[float]:
        if len(v) < 2:
            raise ValueError("position must have at least [easting, northing]")
        return v


class ReinforcementUnitConfig(BaseModel):
    """Single unit entry in a reinforcement schedule."""

    unit_type: str
    count: int = 1
    overrides: dict[str, Any] = {}


class ReinforcementConfig(BaseModel):
    """Scheduled reinforcement arrival."""

    side: str
    arrival_time_s: float
    units: list[ReinforcementUnitConfig]
    position: list[float] = [0.0, 0.0]  # spawn position
    arrival_sigma: float = 0.0  # log-normal sigma for stochastic arrival

    @field_validator("arrival_time_s")
    @classmethod
    def _positive_time(cls, v: float) -> float:
        if v < 0:
            raise ValueError("arrival_time_s must be non-negative")
        return v


class ObjectiveConfig(BaseModel):
    """Campaign objective definition."""

    objective_id: str
    position: list[float]  # [easting, northing]
    radius_m: float = 500.0
    type: str = "territory"  # territory | key_terrain | infrastructure

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        allowed = {"territory", "key_terrain", "infrastructure"}
        if v not in allowed:
            raise ValueError(f"objective type must be one of {allowed}; got {v!r}")
        return v

    @field_validator("radius_m")
    @classmethod
    def _positive_radius(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("radius_m must be positive")
        return v


class VictoryConditionConfig(BaseModel):
    """Campaign victory condition."""

    type: str  # territory_control | force_destroyed | time_expired | morale_collapsed | supply_exhausted
    side: str = ""  # which side wins when condition met (empty = any)
    params: dict[str, Any] = {}

    @field_validator("type")
    @classmethod
    def _known_vc_type(cls, v: str) -> str:
        allowed = {
            "territory_control",
            "force_destroyed",
            "time_expired",
            "morale_collapsed",
            "supply_exhausted",
        }
        if v not in allowed:
            raise ValueError(f"victory condition type must be one of {allowed}; got {v!r}")
        return v


class SideConfig(BaseModel):
    """One side of a campaign — units, AI profile, logistics."""

    side: str
    units: list[dict[str, Any]]  # [{unit_type, count, overrides}]
    experience_level: float = 0.5
    morale_initial: str = "STEADY"
    commander_profile: str = ""  # YAML commander personality ID
    doctrine_template: str = ""  # YAML doctrine template ID
    depots: list[DepotConfig] = []

    @field_validator("experience_level")
    @classmethod
    def _clamp_experience(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"experience_level must be in [0, 1]; got {v}")
        return v


class TickResolutionConfig(BaseModel):
    """Tick duration settings per resolution level."""

    strategic_s: float = 3600.0
    operational_s: float = 300.0
    tactical_s: float = 5.0


class TerrainConfig(BaseModel):
    """Programmatic terrain specification for campaigns."""

    width_m: float
    height_m: float
    cell_size_m: float = 100.0
    base_elevation_m: float = 0.0
    terrain_source: str = "procedural"
    terrain_type: str = "flat_desert"
    features: list[dict[str, Any]] = []
    data_dir: str = "data/terrain_raw"
    cache_dir: str = "data/terrain_cache"

    @field_validator("terrain_source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        allowed = {"procedural", "real"}
        if v not in allowed:
            raise ValueError(f"terrain_source must be one of {allowed}; got {v!r}")
        return v

    @field_validator("terrain_type")
    @classmethod
    def _known_terrain(cls, v: str, info: Any) -> str:
        source = info.data.get("terrain_source", "procedural")
        if source == "real":
            return v  # No constraint when using real terrain
        allowed = {"flat_desert", "open_ocean", "hilly_defense", "trench_warfare"}
        if v not in allowed:
            raise ValueError(f"terrain_type must be one of {allowed}; got {v!r}")
        return v


class CampaignScenarioConfig(BaseModel):
    """Top-level campaign scenario definition loaded from YAML."""

    name: str
    date: str
    duration_hours: float
    latitude: float = 0.0
    longitude: float = 0.0
    era: str = "modern"
    tick_resolution: TickResolutionConfig = TickResolutionConfig()
    weather_conditions: dict[str, Any] = {}
    terrain: TerrainConfig
    sides: list[SideConfig]
    objectives: list[ObjectiveConfig] = []
    victory_conditions: list[VictoryConditionConfig] = []
    reinforcements: list[ReinforcementConfig] = []
    calibration_overrides: dict[str, Any] = {}

    @field_validator("sides")
    @classmethod
    def _at_least_two_sides(cls, v: list[SideConfig]) -> list[SideConfig]:
        if len(v) < 2:
            raise ValueError("campaign requires at least 2 sides")
        return v

    @field_validator("duration_hours")
    @classmethod
    def _positive_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_hours must be positive")
        return v


# ---------------------------------------------------------------------------
# Simulation context — shared state container
# ---------------------------------------------------------------------------


@dataclass
class SimulationContext:
    """Shared state for an in-progress simulation run.

    Holds configuration, core infrastructure, domain engines, and forces.
    Passed to :class:`BattleManager` and :class:`CampaignManager` as the
    single context object for each tick.
    """

    config: CampaignScenarioConfig
    clock: SimulationClock
    rng_manager: RNGManager
    event_bus: EventBus

    # Terrain
    heightmap: Heightmap | None = None
    los_engine: Any = None
    classification: Any = None
    infrastructure_manager: Any = None
    bathymetry: Any = None

    # Forces
    units_by_side: dict[str, list[Unit]] = field(default_factory=dict)
    unit_weapons: dict[str, list[Any]] = field(default_factory=dict)
    unit_sensors: dict[str, list[Any]] = field(default_factory=dict)
    morale_states: dict[str, Any] = field(default_factory=dict)

    # Environment engines
    weather_engine: Any = None
    time_of_day_engine: Any = None
    seasons_engine: Any = None
    sea_state_engine: Any = None
    obscurants_engine: Any = None
    conditions_engine: Any = None

    # Combat
    engagement_engine: Any = None

    # Detection
    fog_of_war: Any = None

    # Movement
    movement_engine: Any = None

    # Morale
    morale_machine: Any = None

    # C2
    command_engine: Any = None
    comms_engine: Any = None
    order_propagation: Any = None
    order_execution: Any = None

    # AI
    ooda_engine: Any = None
    planning_engine: Any = None
    assessor: Any = None
    decision_engine: Any = None
    adaptation_engine: Any = None

    # Aggregation (Phase 13a-7)
    aggregation_engine: Any = None

    # Electronic Warfare (Phase 16)
    ew_engine: Any = None

    # Space & Satellite (Phase 17)
    space_engine: Any = None

    # CBRN (Phase 18)
    cbrn_engine: Any = None

    # Doctrinal AI Schools (Phase 19)
    school_registry: Any = None

    # Era Framework (Phase 20)
    era_config: Any = None

    # WW2 Engine Extensions (Phase 20b)
    naval_gunnery_engine: Any = None
    convoy_engine: Any = None
    strategic_bombing_engine: Any = None

    # WW1 Engine Extensions (Phase 21b)
    trench_engine: Any = None
    barrage_engine: Any = None
    gas_warfare_engine: Any = None

    # Napoleonic Engine Extensions (Phase 22b)
    volley_fire_engine: Any = None
    melee_engine: Any = None
    cavalry_engine: Any = None
    formation_napoleonic_engine: Any = None
    courier_engine: Any = None
    foraging_engine: Any = None

    # Logistics
    consumption_engine: Any = None
    stockpile_manager: Any = None
    supply_network_engine: Any = None
    maintenance_engine: Any = None

    # Loaders (needed for reinforcements)
    unit_loader: Any = None
    weapon_loader: Any = None
    ammo_loader: Any = None
    sensor_loader: Any = None
    sig_loader: Any = None

    # Calibration
    calibration: dict[str, Any] = field(default_factory=dict)

    # ── Helpers ──────────────────────────────────────────────────────

    def all_units(self) -> list[Unit]:
        """Return a flat list of all units across all sides."""
        result: list[Unit] = []
        for units in self.units_by_side.values():
            result.extend(units)
        return result

    def active_units(self, side: str) -> list[Unit]:
        """Return active units for *side*."""
        return [
            u for u in self.units_by_side.get(side, [])
            if u.status == UnitStatus.ACTIVE
        ]

    def side_names(self) -> list[str]:
        """Return sorted side names."""
        return sorted(self.units_by_side.keys())

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture full simulation state for checkpointing."""
        state: dict[str, Any] = {
            "config": self.config.model_dump(),
            "clock": self.clock.get_state(),
            "rng": self.rng_manager.get_state(),
            "units_by_side": {
                side: [u.get_state() for u in units]
                for side, units in self.units_by_side.items()
            },
            "morale_states": {
                uid: (ms.value if hasattr(ms, "value") else ms)
                for uid, ms in self.morale_states.items()
            },
            "calibration": dict(self.calibration),
        }
        # Delegate to engines that have get_state
        engines = [
            ("morale_machine", self.morale_machine),
            ("ooda_engine", self.ooda_engine),
            ("planning_engine", self.planning_engine),
            ("order_execution", self.order_execution),
            ("stockpile_manager", self.stockpile_manager),
            ("fog_of_war", self.fog_of_war),
            ("aggregation_engine", self.aggregation_engine),
            ("space_engine", self.space_engine),
            ("cbrn_engine", self.cbrn_engine),
            ("school_registry", self.school_registry),
            ("trench_engine", self.trench_engine),
            ("barrage_engine", self.barrage_engine),
            ("gas_warfare_engine", self.gas_warfare_engine),
            ("volley_fire_engine", self.volley_fire_engine),
            ("melee_engine", self.melee_engine),
            ("cavalry_engine", self.cavalry_engine),
            ("formation_napoleonic_engine", self.formation_napoleonic_engine),
            ("courier_engine", self.courier_engine),
            ("foraging_engine", self.foraging_engine),
        ]
        for name, eng in engines:
            if eng is not None and hasattr(eng, "get_state"):
                state[name] = eng.get_state()
        # Era config
        if self.era_config is not None and hasattr(self.era_config, "model_dump"):
            state["era_config"] = self.era_config.model_dump()
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore simulation state from checkpoint."""
        self.clock.set_state(state["clock"])
        self.rng_manager.set_state(state["rng"])
        self.calibration = state.get("calibration", {})

        # Restore engine states
        engines = [
            ("morale_machine", self.morale_machine),
            ("ooda_engine", self.ooda_engine),
            ("planning_engine", self.planning_engine),
            ("order_execution", self.order_execution),
            ("stockpile_manager", self.stockpile_manager),
            ("fog_of_war", self.fog_of_war),
            ("aggregation_engine", self.aggregation_engine),
            ("space_engine", self.space_engine),
            ("cbrn_engine", self.cbrn_engine),
            ("school_registry", self.school_registry),
            ("trench_engine", self.trench_engine),
            ("barrage_engine", self.barrage_engine),
            ("gas_warfare_engine", self.gas_warfare_engine),
            ("volley_fire_engine", self.volley_fire_engine),
            ("melee_engine", self.melee_engine),
            ("cavalry_engine", self.cavalry_engine),
            ("formation_napoleonic_engine", self.formation_napoleonic_engine),
            ("courier_engine", self.courier_engine),
            ("foraging_engine", self.foraging_engine),
        ]
        for name, eng in engines:
            if eng is not None and name in state and hasattr(eng, "set_state"):
                eng.set_state(state[name])


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------


def _parse_start_time(date_str: str) -> datetime:
    """Parse ISO date/datetime string into UTC-aware datetime."""
    if "T" in date_str:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    parts = date_str.split("-")
    return datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)


class ScenarioLoader:
    """Load a campaign scenario from YAML and wire all domain engines.

    Parameters
    ----------
    data_dir:
        Root data directory containing ``units/``, ``weapons/``, etc.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    def load(
        self,
        scenario_path: Path,
        seed: int = 42,
    ) -> SimulationContext:
        """Load a campaign scenario and create a fully-wired context.

        Parameters
        ----------
        scenario_path:
            Path to the campaign scenario YAML file.
        seed:
            Master PRNG seed for deterministic replay.
        """
        # 1. Parse config
        with open(scenario_path) as f:
            raw = yaml.safe_load(f)
        config = CampaignScenarioConfig.model_validate(raw)
        logger.info("Loaded campaign %r from %s", config.name, scenario_path)

        # 2. Core infrastructure
        rng_mgr = RNGManager(seed)
        bus = EventBus()
        start_dt = _parse_start_time(config.date)
        clock = SimulationClock(
            start=start_dt,
            tick_duration=timedelta(seconds=config.tick_resolution.strategic_s),
        )

        # 3. Terrain
        self._real_terrain_ctx = None
        heightmap = self._build_terrain(config.terrain, rng_mgr, config)

        # 4. Load YAML data (era-aware)
        from stochastic_warfare.core.era import get_era_config
        era_config = get_era_config(config.era)
        loaders = self._create_loaders(era=config.era)

        # 5. Build forces
        entities_rng = rng_mgr.get_stream(ModuleId.ENTITIES)
        units_by_side, unit_weapons, unit_sensors = self._build_all_forces(
            config, loaders, entities_rng,
        )

        # 6. Morale state tracking
        from stochastic_warfare.morale.state import MoraleState
        morale_states: dict[str, MoraleState] = {}
        for units in units_by_side.values():
            for u in units:
                morale_states[u.entity_id] = MoraleState.STEADY

        # 7. Create domain engines (era-gated)
        disabled = era_config.disabled_modules
        engines = self._create_engines(rng_mgr, bus, heightmap, loaders, config)

        # 8. Assemble context
        real_ctx = self._real_terrain_ctx
        ctx = SimulationContext(
            config=config,
            clock=clock,
            rng_manager=rng_mgr,
            event_bus=bus,
            heightmap=heightmap,
            classification=real_ctx.classification if real_ctx else None,
            infrastructure_manager=real_ctx.infrastructure if real_ctx else None,
            bathymetry=real_ctx.bathymetry if real_ctx else None,
            units_by_side=units_by_side,
            unit_weapons=unit_weapons,
            unit_sensors=unit_sensors,
            morale_states=morale_states,
            calibration=dict(config.calibration_overrides),
            era_config=era_config,
            **engines,
            **loaders,
        )
        return ctx

    # ── Private helpers ──────────────────────────────────────────────

    def _build_terrain(
        self,
        spec: TerrainConfig,
        rng_mgr: RNGManager,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build heightmap from terrain specification."""
        if spec.terrain_source == "real":
            return self._build_real_terrain(spec, config)

        from stochastic_warfare.terrain.heightmap import HeightmapConfig
        from stochastic_warfare.validation.scenario_runner import build_terrain
        from stochastic_warfare.validation.historical_data import TerrainSpec

        terrain_spec = TerrainSpec(
            width_m=spec.width_m,
            height_m=spec.height_m,
            cell_size_m=spec.cell_size_m,
            base_elevation_m=spec.base_elevation_m,
            terrain_type=spec.terrain_type,
            features=spec.features,
        )
        terrain_rng = rng_mgr.get_stream(ModuleId.TERRAIN)
        return build_terrain(terrain_spec, terrain_rng)

    def _build_real_terrain(
        self,
        spec: TerrainConfig,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build terrain from real-world geospatial data."""
        from stochastic_warfare.terrain.data_pipeline import (
            BoundingBox,
            TerrainDataConfig,
            load_real_terrain,
        )
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        lat = config.latitude if config else 0.0
        lon = config.longitude if config else 0.0
        projection = ScenarioProjection(lat, lon)

        # Compute bbox from lat/lon + width/height
        import math
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
        half_h = (spec.height_m / 2) / meters_per_deg_lat
        half_w = (spec.width_m / 2) / meters_per_deg_lon

        bbox = BoundingBox(
            south=lat - half_h,
            west=lon - half_w,
            north=lat + half_h,
            east=lon + half_w,
        )
        tdc = TerrainDataConfig(
            bbox=bbox,
            cell_size_m=spec.cell_size_m,
            data_dir=spec.data_dir,
            cache_dir=spec.cache_dir,
        )

        ctx = load_real_terrain(tdc, projection)

        # Stash extra layers for the SimulationContext to pick up
        self._real_terrain_ctx = ctx
        return ctx.heightmap

    def _create_loaders(self, era: str = "modern") -> dict[str, Any]:
        """Create and initialize all YAML data loaders.

        When *era* is not ``"modern"``, also loads YAML definitions from
        ``data/eras/{era}/`` — era-specific files add to (not replace)
        the base data set.
        """
        from stochastic_warfare.entities.loader import UnitLoader
        from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
        from stochastic_warfare.detection.signatures import SignatureLoader
        from stochastic_warfare.detection.sensors import SensorLoader

        unit_loader = UnitLoader(self._data_dir / "units")
        unit_loader.load_all()

        weapon_loader = WeaponLoader(self._data_dir / "weapons")
        weapon_loader.load_all()

        ammo_loader = AmmoLoader(self._data_dir / "ammunition")
        ammo_loader.load_all()

        sig_loader = SignatureLoader(self._data_dir / "signatures")
        sig_loader.load_all()

        sensor_loader = SensorLoader(self._data_dir / "sensors")
        sensor_loader.load_all()

        # Load era-specific data on top of base data
        if era != "modern":
            era_dir = self._data_dir / "eras" / era
            if era_dir.is_dir():
                era_units = era_dir / "units"
                if era_units.is_dir():
                    era_unit_loader = UnitLoader(era_units)
                    era_unit_loader.load_all()
                    unit_loader._definitions.update(era_unit_loader._definitions)

                era_weapons = era_dir / "weapons"
                if era_weapons.is_dir():
                    era_weapon_loader = WeaponLoader(era_weapons)
                    era_weapon_loader.load_all()
                    weapon_loader._definitions.update(era_weapon_loader._definitions)

                era_ammo = era_dir / "ammunition"
                if era_ammo.is_dir():
                    era_ammo_loader = AmmoLoader(era_ammo)
                    era_ammo_loader.load_all()
                    ammo_loader._definitions.update(era_ammo_loader._definitions)

                era_sigs = era_dir / "signatures"
                if era_sigs.is_dir():
                    era_sig_loader = SignatureLoader(era_sigs)
                    era_sig_loader.load_all()
                    sig_loader._profiles.update(era_sig_loader._profiles)

                era_sensors = era_dir / "sensors"
                if era_sensors.is_dir():
                    era_sensor_loader = SensorLoader(era_sensors)
                    era_sensor_loader.load_all()
                    sensor_loader._definitions.update(era_sensor_loader._definitions)

                logger.info("Loaded era-specific data from %s", era_dir)

        return {
            "unit_loader": unit_loader,
            "weapon_loader": weapon_loader,
            "ammo_loader": ammo_loader,
            "sig_loader": sig_loader,
            "sensor_loader": sensor_loader,
        }

    def _build_all_forces(
        self,
        config: CampaignScenarioConfig,
        loaders: dict[str, Any],
        entities_rng: np.random.Generator,
    ) -> tuple[dict[str, list[Unit]], dict[str, list[Any]], dict[str, list[Any]]]:
        """Build units for all sides and assign weapons/sensors."""
        from stochastic_warfare.validation.scenario_runner import build_forces
        from stochastic_warfare.validation.historical_data import ForceDefinition

        units_by_side: dict[str, list[Unit]] = {}
        cal = config.calibration_overrides

        for i, side_cfg in enumerate(config.sides):
            force_def = ForceDefinition(
                side=side_cfg.side,
                units=side_cfg.units,
                personnel_total=sum(
                    e.get("count", 1) for e in side_cfg.units
                ),
                experience_level=side_cfg.experience_level,
                morale_initial=side_cfg.morale_initial,
            )
            # Determine start positions from calibration or defaults
            prefix = side_cfg.side
            default_x = 100.0 if i == 0 else config.terrain.width_m - 100.0
            default_y = config.terrain.height_m / 2
            start_x = cal.get(f"{prefix}_start_x", default_x)
            start_y = cal.get(f"{prefix}_start_y", default_y)

            units = build_forces(
                force_def,
                loaders["unit_loader"],
                entities_rng,
                start_x=start_x,
                start_y=start_y,
            )
            units_by_side[side_cfg.side] = units

        # Assign weapons and sensors
        all_units = [u for us in units_by_side.values() for u in us]
        from stochastic_warfare.validation.scenario_runner import ScenarioRunner

        unit_weapons = ScenarioRunner._assign_weapons(
            all_units, loaders["weapon_loader"], loaders["ammo_loader"], cal,
        )
        for uid, wpns in unit_weapons.items():
            wpns.sort(key=lambda w: w[0].definition.max_range_m, reverse=True)

        unit_sensors = ScenarioRunner._assign_sensors(
            all_units, loaders["sensor_loader"],
        )

        return units_by_side, unit_weapons, unit_sensors

    def _create_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        heightmap: Heightmap,
        loaders: dict[str, Any],
        config: CampaignScenarioConfig,
    ) -> dict[str, Any]:
        """Create all domain engine instances."""
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        detection_rng = rng_mgr.get_stream(ModuleId.DETECTION)
        morale_rng = rng_mgr.get_stream(ModuleId.MORALE)
        movement_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        logistics_rng = rng_mgr.get_stream(ModuleId.LOGISTICS)

        # Combat stack
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
        from stochastic_warfare.combat.damage import DamageEngine
        from stochastic_warfare.combat.suppression import SuppressionEngine
        from stochastic_warfare.combat.fratricide import FratricideEngine
        from stochastic_warfare.combat.engagement import EngagementEngine

        bal = BallisticsEngine(combat_rng)
        hit_engine = HitProbabilityEngine(bal, combat_rng)
        dmg_engine = DamageEngine(bus, combat_rng)
        sup_engine = SuppressionEngine(bus, combat_rng)
        frat_engine = FratricideEngine(bus, combat_rng)
        engagement_engine = EngagementEngine(
            hit_engine, dmg_engine, sup_engine, frat_engine, bus, combat_rng,
        )

        # LOS engine (built from heightmap, cached per tick)
        from stochastic_warfare.terrain.los import LOSEngine

        los_engine = LOSEngine(heightmap)

        # Detection
        from stochastic_warfare.detection.detection import DetectionEngine
        from stochastic_warfare.detection.fog_of_war import FogOfWarManager

        det_engine = DetectionEngine(
            los_checker=los_engine.check_los,
            rng=detection_rng,
            signature_loader=loaders["sig_loader"],
            sensor_loader=loaders["sensor_loader"],
        )
        fog_of_war = FogOfWarManager(
            detection_engine=det_engine,
            rng=detection_rng,
        )

        # Morale
        from stochastic_warfare.morale.state import MoraleStateMachine
        from stochastic_warfare.validation.scenario_runner import ScenarioRunner as _SR

        cal = config.calibration_overrides
        morale_config = _SR._build_morale_config(cal) if cal else None
        morale_machine = MoraleStateMachine(bus, morale_rng, morale_config)

        # Movement
        from stochastic_warfare.movement.engine import MovementEngine

        movement_engine = MovementEngine(
            heightmap=heightmap,
            rng=movement_rng,
        )

        # C2
        from stochastic_warfare.c2.communications import CommunicationsEngine
        from stochastic_warfare.c2.orders.propagation import OrderPropagationEngine
        from stochastic_warfare.c2.orders.execution import OrderExecutionEngine

        comms_engine = CommunicationsEngine(bus, c2_rng)
        # CommandEngine requires hierarchy/task_org — create minimal stubs
        # for now; full C2 wiring happens in campaign/battle managers
        order_propagation = OrderPropagationEngine(
            comms_engine=comms_engine,
            command_engine=None,
            event_bus=bus,
            rng=c2_rng,
        )
        order_execution = OrderExecutionEngine(
            propagation_engine=order_propagation,
            event_bus=bus,
            rng=c2_rng,
        )

        # AI
        from stochastic_warfare.c2.ai.ooda import OODALoopEngine
        from stochastic_warfare.c2.planning.process import PlanningProcessEngine
        from stochastic_warfare.c2.ai.assessment import SituationAssessor
        from stochastic_warfare.c2.ai.decisions import DecisionEngine
        from stochastic_warfare.c2.ai.adaptation import AdaptationEngine

        ooda_engine = OODALoopEngine(bus, c2_rng)
        planning_engine = PlanningProcessEngine(bus, c2_rng)
        assessor = SituationAssessor(bus, c2_rng)
        decision_engine = DecisionEngine(bus, c2_rng)
        adaptation_engine = AdaptationEngine(bus, c2_rng)

        # Logistics
        from stochastic_warfare.logistics.consumption import ConsumptionEngine
        from stochastic_warfare.logistics.stockpile import StockpileManager
        from stochastic_warfare.logistics.supply_network import SupplyNetworkEngine
        from stochastic_warfare.logistics.maintenance import MaintenanceEngine

        consumption_engine = ConsumptionEngine(bus, logistics_rng)
        stockpile_manager = StockpileManager(bus, logistics_rng)
        supply_network_engine = SupplyNetworkEngine(bus, logistics_rng)
        maintenance_engine = MaintenanceEngine(bus, logistics_rng)

        # Aggregation (Phase 13a-7)
        from stochastic_warfare.simulation.aggregation import (
            AggregationConfig,
            AggregationEngine,
        )

        agg_config = AggregationConfig()
        aggregation_engine = AggregationEngine(
            config=agg_config,
            rng=rng_mgr.get_stream(ModuleId.CORE),
            event_bus=bus,
        )

        return {
            "los_engine": los_engine,
            "engagement_engine": engagement_engine,
            "fog_of_war": fog_of_war,
            "morale_machine": morale_machine,
            "movement_engine": movement_engine,
            "comms_engine": comms_engine,
            "order_propagation": order_propagation,
            "order_execution": order_execution,
            "ooda_engine": ooda_engine,
            "planning_engine": planning_engine,
            "assessor": assessor,
            "decision_engine": decision_engine,
            "adaptation_engine": adaptation_engine,
            "consumption_engine": consumption_engine,
            "stockpile_manager": stockpile_manager,
            "supply_network_engine": supply_network_engine,
            "maintenance_engine": maintenance_engine,
            "aggregation_engine": aggregation_engine,
        }
