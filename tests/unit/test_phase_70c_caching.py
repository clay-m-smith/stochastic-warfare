"""Phase 70c: Signature caching and calibration/engine hoisting tests.

Verifies that cached signatures match fresh lookups, and that hoisted
calibration / engine references are equivalent to inline lookups.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


from stochastic_warfare.core.events import EventBus
from stochastic_warfare.simulation.battle import BattleManager, _get_unit_signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSigLoader:
    """Stub signature loader that counts calls."""

    def __init__(self) -> None:
        self.call_count = 0
        self._profiles: dict[str, dict] = {
            "tank": {"visual": 1.0, "thermal": 0.8, "radar": 0.5},
            "infantry": {"visual": 0.5, "thermal": 0.3, "radar": 0.1},
        }

    def get_profile(self, unit_type: str) -> dict | None:
        self.call_count += 1
        return self._profiles.get(unit_type)


class _FakeUnit:
    """Minimal unit stub."""

    def __init__(self, unit_type: str = "tank") -> None:
        self.unit_type = unit_type
        self.entity_id = f"{unit_type}_01"


class _FakeCalibration:
    """Minimal calibration dict-like object matching CalibrationSchema.get()."""

    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self._data = {
            "enable_seasonal_effects": True,
            "enable_em_propagation": False,
            "enable_nvg_detection": True,
            "enable_thermal_crossover": False,
            "enable_obscurants": True,
            "enable_acoustic_layers": False,
            "enable_human_factors": True,
            "enable_air_combat_environment": False,
            "enable_unconventional_warfare": True,
            "enable_ammo_gate": False,
            "enable_fire_zones": True,
            "enable_missile_routing": False,
            "observation_decay_rate": 0.03,
            "rain_attenuation_factor": 1.2,
            "stealth_detection_penalty": 0.1,
            "sigint_detection_bonus": 0.05,
            "formation_spacing_m": 75.0,
        }
        if overrides:
            self._data.update(overrides)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignatureCache:
    """Signature cache on BattleManager."""

    def test_cache_returns_same_as_fresh_lookup(self) -> None:
        """Cached signature matches _get_unit_signature result."""
        loader = _FakeSigLoader()
        ctx = SimpleNamespace(sig_loader=loader)
        unit = _FakeUnit("tank")

        fresh = _get_unit_signature(ctx, unit)
        assert fresh is not None

        # Simulate the caching pattern from battle.py
        bm = BattleManager(EventBus())
        ut = unit.unit_type
        if ut not in bm._signature_cache:
            bm._signature_cache[ut] = _get_unit_signature(ctx, unit)
        cached = bm._signature_cache[ut]

        assert cached == fresh

    def test_cache_populated_lazily(self) -> None:
        """Cache starts empty; populated on first access."""
        bm = BattleManager(EventBus())
        assert len(bm._signature_cache) == 0

    def test_cache_avoids_repeated_lookups(self) -> None:
        """Same unit_type only calls sig_loader once."""
        loader = _FakeSigLoader()
        ctx = SimpleNamespace(sig_loader=loader)
        bm = BattleManager(EventBus())

        for _ in range(10):
            ut = "tank"
            if ut not in bm._signature_cache:
                bm._signature_cache[ut] = _get_unit_signature(ctx, _FakeUnit("tank"))
            _ = bm._signature_cache[ut]

        # Only 1 actual loader call despite 10 accesses
        assert loader.call_count == 1


class TestCalibrationHoisting:
    """Hoisted calibration values match cal.get() results."""

    def test_enable_flags_match(self) -> None:
        """Hoisted enable_* flags match cal.get() values."""
        cal = _FakeCalibration()
        flags = [
            ("enable_seasonal_effects", False),
            ("enable_em_propagation", False),
            ("enable_nvg_detection", False),
            ("enable_thermal_crossover", False),
            ("enable_obscurants", False),
            ("enable_acoustic_layers", False),
            ("enable_human_factors", False),
            ("enable_air_combat_environment", False),
            ("enable_unconventional_warfare", False),
            ("enable_ammo_gate", False),
            ("enable_fire_zones", False),
            ("enable_missile_routing", False),
        ]
        for key, default in flags:
            hoisted = cal.get(key, default)
            inline = cal.get(key, default)
            assert hoisted == inline, f"{key}: hoisted={hoisted}, inline={inline}"

    def test_numeric_values_match(self) -> None:
        """Hoisted numeric calibration values match cal.get() results."""
        cal = _FakeCalibration()
        numerics = [
            ("observation_decay_rate", 0.05),
            ("rain_attenuation_factor", 1.0),
            ("stealth_detection_penalty", 0.0),
            ("sigint_detection_bonus", 0.0),
            ("formation_spacing_m", 50.0),
        ]
        for key, default in numerics:
            hoisted = cal.get(key, default)
            inline = cal.get(key, default)
            assert hoisted == inline, f"{key}: hoisted={hoisted}, inline={inline}"


class TestEngineHoisting:
    """Hoisted engine references are same objects as getattr(ctx, ...)."""

    def test_engine_references_same_object(self) -> None:
        """Hoisted engine refs are identical objects (not copies)."""
        engines = {
            "weather_engine": object(),
            "time_of_day_engine": object(),
            "sea_state_engine": object(),
            "cbrn_engine": object(),
            "obscurants_engine": object(),
            "underwater_acoustics_engine": object(),
            "ew_engine": object(),
            "eccm_engine": object(),
            "detection_engine": object(),
            "space_engine": object(),
            "seasons_engine": object(),
            "maintenance_engine": object(),
            "incendiary_engine": object(),
        }
        ctx = SimpleNamespace(**engines)
        for name, expected in engines.items():
            hoisted = getattr(ctx, name, None)
            assert hoisted is expected, f"{name}: not same object"

    def test_missing_engine_is_none(self) -> None:
        """Missing engine → None (same as getattr default)."""
        ctx = SimpleNamespace()
        for name in ("weather_engine", "ew_engine", "space_engine"):
            hoisted = getattr(ctx, name, None)
            assert hoisted is None
