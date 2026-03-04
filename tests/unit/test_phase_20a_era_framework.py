"""Phase 20a — Era Framework + WW2 Unit Data tests.

Tests the era enum, EraConfig pydantic model, pre-defined era configs,
disabled module gating, era-aware scenario loading, and WW2 YAML loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stochastic_warfare.core.era import (
    Era,
    EraConfig,
    MODERN_ERA_CONFIG,
    WW2_ERA_CONFIG,
    get_era_config,
    register_era_config,
)

# ---------------------------------------------------------------------------
# 20a-1: Era enum & EraConfig validation
# ---------------------------------------------------------------------------


class TestEraEnum:
    """Era enum membership and string values."""

    def test_modern_value(self) -> None:
        assert Era.MODERN == "modern"

    def test_ww2_value(self) -> None:
        assert Era.WW2 == "ww2"

    def test_ww1_value(self) -> None:
        assert Era.WW1 == "ww1"

    def test_napoleonic_value(self) -> None:
        assert Era.NAPOLEONIC == "napoleonic"

    def test_ancient_medieval_value(self) -> None:
        assert Era.ANCIENT_MEDIEVAL == "ancient_medieval"

    def test_all_eras_count(self) -> None:
        assert len(Era) == 5


class TestEraConfig:
    """EraConfig pydantic model."""

    def test_default_is_modern(self) -> None:
        cfg = EraConfig()
        assert cfg.era == Era.MODERN
        assert cfg.disabled_modules == set()
        assert cfg.available_sensor_types == set()

    def test_custom_disabled_modules(self) -> None:
        cfg = EraConfig(disabled_modules={"ew", "space"})
        assert "ew" in cfg.disabled_modules
        assert "space" in cfg.disabled_modules

    def test_available_sensor_types(self) -> None:
        cfg = EraConfig(available_sensor_types={"VISUAL", "RADAR"})
        assert cfg.available_sensor_types == {"VISUAL", "RADAR"}

    def test_physics_overrides(self) -> None:
        cfg = EraConfig(physics_overrides={"max_mach": 0.8})
        assert cfg.physics_overrides["max_mach"] == 0.8

    def test_tick_resolution_overrides(self) -> None:
        cfg = EraConfig(tick_resolution_overrides={"tactical_s": 10.0})
        assert cfg.tick_resolution_overrides["tactical_s"] == 10.0

    def test_model_dump_roundtrip(self) -> None:
        cfg = WW2_ERA_CONFIG
        data = cfg.model_dump()
        restored = EraConfig.model_validate(data)
        assert restored.era == cfg.era
        assert restored.disabled_modules == cfg.disabled_modules

    def test_era_from_string(self) -> None:
        cfg = EraConfig(era="ww2")
        assert cfg.era == Era.WW2


# ---------------------------------------------------------------------------
# 20a-2: Pre-defined configs
# ---------------------------------------------------------------------------


class TestPreDefinedConfigs:
    """Pre-defined WW2 and MODERN configs."""

    def test_modern_no_disabled(self) -> None:
        assert MODERN_ERA_CONFIG.disabled_modules == set()
        assert MODERN_ERA_CONFIG.era == Era.MODERN

    def test_modern_all_sensors_available(self) -> None:
        assert MODERN_ERA_CONFIG.available_sensor_types == set()

    def test_ww2_disabled_modules(self) -> None:
        expected = {"ew", "space", "cbrn", "gps", "thermal_sights", "data_links", "pgm"}
        assert WW2_ERA_CONFIG.disabled_modules == expected

    def test_ww2_sensor_types(self) -> None:
        expected = {"VISUAL", "RADAR", "PASSIVE_SONAR", "ACTIVE_SONAR"}
        assert WW2_ERA_CONFIG.available_sensor_types == expected

    def test_ww2_era_value(self) -> None:
        assert WW2_ERA_CONFIG.era == Era.WW2


# ---------------------------------------------------------------------------
# 20a-3: get_era_config factory
# ---------------------------------------------------------------------------


class TestGetEraConfig:
    """Factory function for looking up era configs."""

    def test_lookup_modern(self) -> None:
        cfg = get_era_config("modern")
        assert cfg.era == Era.MODERN

    def test_lookup_ww2(self) -> None:
        cfg = get_era_config("ww2")
        assert cfg.era == Era.WW2

    def test_lookup_case_insensitive(self) -> None:
        cfg = get_era_config("WW2")
        assert cfg.era == Era.WW2

    def test_unknown_returns_modern(self) -> None:
        cfg = get_era_config("future_war")
        assert cfg.era == Era.MODERN

    def test_register_custom_era(self) -> None:
        custom = EraConfig(era=Era.WW1, disabled_modules={"space", "ew", "cbrn", "gps"})
        register_era_config("ww1", custom)
        retrieved = get_era_config("ww1")
        assert retrieved.era == Era.WW1
        assert "space" in retrieved.disabled_modules


# ---------------------------------------------------------------------------
# 20a-4: Disabled modules per era
# ---------------------------------------------------------------------------


class TestDisabledModules:
    """Module gating behavior."""

    def test_ew_disabled_in_ww2(self) -> None:
        assert "ew" in WW2_ERA_CONFIG.disabled_modules

    def test_space_disabled_in_ww2(self) -> None:
        assert "space" in WW2_ERA_CONFIG.disabled_modules

    def test_cbrn_disabled_in_ww2(self) -> None:
        assert "cbrn" in WW2_ERA_CONFIG.disabled_modules

    def test_gps_disabled_in_ww2(self) -> None:
        assert "gps" in WW2_ERA_CONFIG.disabled_modules

    def test_thermal_sights_disabled_in_ww2(self) -> None:
        assert "thermal_sights" in WW2_ERA_CONFIG.disabled_modules

    def test_data_links_disabled_in_ww2(self) -> None:
        assert "data_links" in WW2_ERA_CONFIG.disabled_modules

    def test_pgm_disabled_in_ww2(self) -> None:
        assert "pgm" in WW2_ERA_CONFIG.disabled_modules

    def test_nothing_disabled_modern(self) -> None:
        assert len(MODERN_ERA_CONFIG.disabled_modules) == 0


# ---------------------------------------------------------------------------
# 20a-5: CampaignScenarioConfig era field
# ---------------------------------------------------------------------------


class TestScenarioConfigEra:
    """CampaignScenarioConfig has era field."""

    def test_default_era_is_modern(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        cfg = CampaignScenarioConfig(
            name="test",
            date="1944-06-06",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": []},
                {"side": "red", "units": []},
            ],
        )
        assert cfg.era == "modern"

    def test_ww2_era_field(self) -> None:
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        cfg = CampaignScenarioConfig(
            name="Kursk",
            date="1943-07-05",
            duration_hours=8.0,
            era="ww2",
            terrain={"width_m": 12000, "height_m": 8000},
            sides=[
                {"side": "soviet", "units": []},
                {"side": "german", "units": []},
            ],
        )
        assert cfg.era == "ww2"


# ---------------------------------------------------------------------------
# 20a-6: SimulationContext era_config field
# ---------------------------------------------------------------------------


class TestSimulationContextEra:
    """SimulationContext era_config field and state persistence."""

    def _make_ctx(self, era_config: Any = None) -> Any:
        from datetime import datetime, timedelta, timezone

        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
        )

        config = CampaignScenarioConfig(
            name="test",
            date="1944-01-01",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": []},
                {"side": "red", "units": []},
            ],
        )
        clock = SimulationClock(
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tick_duration=timedelta(seconds=10),
        )
        return SimulationContext(
            config=config,
            clock=clock,
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
            era_config=era_config,
        )

    def test_default_era_config_none(self) -> None:
        ctx = self._make_ctx()
        assert ctx.era_config is None

    def test_set_era_config(self) -> None:
        ctx = self._make_ctx(era_config=WW2_ERA_CONFIG)
        assert ctx.era_config.era == Era.WW2

    def test_get_state_includes_era_config(self) -> None:
        ctx = self._make_ctx(era_config=WW2_ERA_CONFIG)
        state = ctx.get_state()
        assert "era_config" in state
        assert state["era_config"]["era"] == "ww2"

    def test_get_state_no_era_config(self) -> None:
        ctx = self._make_ctx()
        state = ctx.get_state()
        assert "era_config" not in state


# ---------------------------------------------------------------------------
# 20a-7: WW2 YAML loading (parametrized)
# ---------------------------------------------------------------------------


_WW2_UNITS = [
    "sherman_m4a3",
    "t34_85",
    "tiger_i",
    "panther",
    "panzer_iv_h",
    "us_rifle_squad_ww2",
    "wehrmacht_rifle_squad",
    "soviet_rifle_squad",
    "bf109g",
    "p51d",
    "spitfire_ix",
    "b17g",
    "type_viic_uboat",
    "fletcher_dd",
    "iowa_bb",
]


@pytest.mark.parametrize("unit_type", _WW2_UNITS)
def test_ww2_unit_yaml_loads(unit_type: str) -> None:
    """Each WW2 unit YAML loads and validates via pydantic."""
    from stochastic_warfare.entities.loader import UnitLoader

    era_dir = Path("data/eras/ww2/units")
    if not era_dir.is_dir():
        pytest.skip("WW2 unit data not found")
    loader = UnitLoader(era_dir)
    loader.load_all()
    assert unit_type in loader.available_types(), f"{unit_type} not found in WW2 data"


# ---------------------------------------------------------------------------
# 20a-8: Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing tests and scenarios must be unaffected."""

    def test_config_without_era_defaults_modern(self) -> None:
        """YAML without 'era:' field defaults to modern."""
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        raw = {
            "name": "legacy_test",
            "date": "2024-01-01",
            "duration_hours": 1.0,
            "terrain": {"width_m": 1000, "height_m": 1000},
            "sides": [
                {"side": "blue", "units": []},
                {"side": "red", "units": []},
            ],
        }
        cfg = CampaignScenarioConfig.model_validate(raw)
        assert cfg.era == "modern"

    def test_era_config_for_modern_has_no_disabled(self) -> None:
        cfg = get_era_config("modern")
        assert cfg.disabled_modules == set()

    def test_simulation_context_ww2_engines_default_none(self) -> None:
        from datetime import datetime, timedelta, timezone
        from stochastic_warfare.core.clock import SimulationClock
        from stochastic_warfare.core.events import EventBus
        from stochastic_warfare.core.rng import RNGManager
        from stochastic_warfare.simulation.scenario import (
            CampaignScenarioConfig,
            SimulationContext,
        )

        config = CampaignScenarioConfig(
            name="test",
            date="2024-01-01",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": []},
                {"side": "red", "units": []},
            ],
        )
        ctx = SimulationContext(
            config=config,
            clock=SimulationClock(
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                tick_duration=timedelta(seconds=10),
            ),
            rng_manager=RNGManager(42),
            event_bus=EventBus(),
        )
        assert ctx.naval_gunnery_engine is None
        assert ctx.convoy_engine is None
        assert ctx.strategic_bombing_engine is None
        assert ctx.era_config is None

    def test_modern_era_identical_behavior(self) -> None:
        """get_era_config('modern') returns config with nothing disabled."""
        cfg = get_era_config("modern")
        assert cfg.era == Era.MODERN
        assert cfg.disabled_modules == set()
        assert cfg.available_sensor_types == set()
        assert cfg.physics_overrides == {}
        assert cfg.tick_resolution_overrides == {}
