"""Tests for commander personality engine (c2.ai.commander).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from stochastic_warfare.c2.ai.commander import (
    CommanderConfig,
    CommanderEngine,
    CommanderPersonality,
    CommanderProfileLoader,
)
from tests.conftest import DEFAULT_SEED, make_rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFILE_DATA = {
    "profile_id": "test_profile",
    "display_name": "Test Commander",
    "description": "A test personality",
    "aggression": 0.6,
    "caution": 0.4,
    "flexibility": 0.5,
    "initiative": 0.7,
    "experience": 0.8,
}


def _write_yaml(path: Path, data: dict) -> Path:
    """Write a YAML file and return its path."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f)
    return path


def _make_engine(
    loader: CommanderProfileLoader,
    seed: int = DEFAULT_SEED,
    config: CommanderConfig | None = None,
) -> CommanderEngine:
    rng = make_rng(seed)
    return CommanderEngine(loader, rng, config)


# ---------------------------------------------------------------------------
# CommanderPersonality pydantic model
# ---------------------------------------------------------------------------


class TestCommanderPersonality:
    """Pydantic model validation and defaults."""

    def test_valid_profile(self) -> None:
        p = CommanderPersonality(**_PROFILE_DATA)
        assert p.profile_id == "test_profile"
        assert p.aggression == 0.6
        assert p.experience == 0.8

    def test_defaults(self) -> None:
        p = CommanderPersonality(**_PROFILE_DATA)
        assert p.preferred_doctrine is None
        assert p.stress_tolerance == 0.5
        assert p.decision_speed == 0.5
        assert p.risk_acceptance == 0.5

    def test_preferred_doctrine_set(self) -> None:
        data = {**_PROFILE_DATA, "preferred_doctrine": "us_attack_deliberate"}
        p = CommanderPersonality(**data)
        assert p.preferred_doctrine == "us_attack_deliberate"

    def test_aggression_out_of_range_high(self) -> None:
        data = {**_PROFILE_DATA, "aggression": 1.5}
        with pytest.raises(ValidationError):
            CommanderPersonality(**data)

    def test_aggression_out_of_range_low(self) -> None:
        data = {**_PROFILE_DATA, "aggression": -0.1}
        with pytest.raises(ValidationError):
            CommanderPersonality(**data)

    def test_experience_boundary_zero(self) -> None:
        data = {**_PROFILE_DATA, "experience": 0.0}
        p = CommanderPersonality(**data)
        assert p.experience == 0.0

    def test_experience_boundary_one(self) -> None:
        data = {**_PROFILE_DATA, "experience": 1.0}
        p = CommanderPersonality(**data)
        assert p.experience == 1.0

    def test_all_high_traits(self) -> None:
        data = {
            **_PROFILE_DATA,
            "aggression": 1.0,
            "caution": 1.0,
            "flexibility": 1.0,
            "initiative": 1.0,
            "experience": 1.0,
            "stress_tolerance": 1.0,
            "decision_speed": 1.0,
            "risk_acceptance": 1.0,
        }
        p = CommanderPersonality(**data)
        assert p.aggression == 1.0
        assert p.decision_speed == 1.0

    def test_all_low_traits(self) -> None:
        data = {
            **_PROFILE_DATA,
            "aggression": 0.0,
            "caution": 0.0,
            "flexibility": 0.0,
            "initiative": 0.0,
            "experience": 0.0,
            "stress_tolerance": 0.0,
            "decision_speed": 0.0,
            "risk_acceptance": 0.0,
        }
        p = CommanderPersonality(**data)
        assert p.aggression == 0.0
        assert p.decision_speed == 0.0


# ---------------------------------------------------------------------------
# CommanderConfig
# ---------------------------------------------------------------------------


class TestCommanderConfig:
    def test_defaults(self) -> None:
        c = CommanderConfig()
        assert c.ooda_speed_base_mult == 1.0
        assert c.noise_sigma == 0.1
        assert c.risk_threshold_base == 0.3


# ---------------------------------------------------------------------------
# CommanderProfileLoader
# ---------------------------------------------------------------------------


class TestCommanderProfileLoader:
    def test_load_definition_from_file(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        _write_yaml(yaml_path, _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        defn = loader.load_definition(yaml_path)
        assert defn.profile_id == "test_profile"
        assert defn.aggression == 0.6

    def test_load_all(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "a.yaml", {**_PROFILE_DATA, "profile_id": "alpha"})
        _write_yaml(tmp_path / "b.yaml", {**_PROFILE_DATA, "profile_id": "bravo"})
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        assert sorted(loader.available_profiles()) == ["alpha", "bravo"]

    def test_get_definition(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        _write_yaml(yaml_path, _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_definition(yaml_path)
        defn = loader.get_definition("test_profile")
        assert defn.display_name == "Test Commander"

    def test_get_definition_missing_raises(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")

    def test_available_profiles_empty(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        assert loader.available_profiles() == []

    def test_load_all_real_yaml_files(self) -> None:
        """Load all 6 real YAML files from data/commander_profiles/."""
        loader = CommanderProfileLoader()
        loader.load_all()
        expected = {
            "aggressive_armor",
            "air_superiority",
            "balanced_default",
            "cautious_infantry",
            "desperate_defender",
            "insurgent_leader",
            "naval_surface",
            "pmc_operator",
            "ruthless_authoritarian",
            "sof_operator",
        }
        assert expected.issubset(set(loader.available_profiles()))

    def test_real_profiles_have_valid_ranges(self) -> None:
        """Every real profile has all traits within [0, 1]."""
        loader = CommanderProfileLoader()
        loader.load_all()
        for pid in loader.available_profiles():
            p = loader.get_definition(pid)
            for trait in [
                "aggression", "caution", "flexibility", "initiative",
                "experience", "stress_tolerance", "decision_speed",
                "risk_acceptance",
            ]:
                val = getattr(p, trait)
                assert 0.0 <= val <= 1.0, f"{pid}.{trait}={val} out of range"


# ---------------------------------------------------------------------------
# CommanderEngine
# ---------------------------------------------------------------------------


class TestCommanderEngine:
    def test_assign_and_get_personality(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("unit_1", "test_profile")
        p = engine.get_personality("unit_1")
        assert p is not None
        assert p.profile_id == "test_profile"

    def test_get_personality_unknown_unit(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        assert engine.get_personality("no_such_unit") is None

    def test_assign_unknown_profile_raises(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        with pytest.raises(KeyError):
            engine.assign_personality("unit_1", "nonexistent_profile")

    def test_multiple_commanders_no_interference(self, tmp_path: Path) -> None:
        data_a = {**_PROFILE_DATA, "profile_id": "alpha", "aggression": 0.9}
        data_b = {**_PROFILE_DATA, "profile_id": "bravo", "aggression": 0.1}
        _write_yaml(tmp_path / "a.yaml", data_a)
        _write_yaml(tmp_path / "b.yaml", data_b)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("unit_a", "alpha")
        engine.assign_personality("unit_b", "bravo")
        pa = engine.get_personality("unit_a")
        pb = engine.get_personality("unit_b")
        assert pa is not None and pb is not None
        assert pa.aggression == 0.9
        assert pb.aggression == 0.1


class TestOodaSpeedMultiplier:
    def test_aggressive_experienced_fast(self, tmp_path: Path) -> None:
        """Aggressive + experienced commander -> low multiplier (fast OODA)."""
        data = {**_PROFILE_DATA, "decision_speed": 0.9, "experience": 0.9}
        _write_yaml(tmp_path / "fast.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("fast_cdr", "test_profile")
        mult = engine.get_ooda_speed_multiplier("fast_cdr")
        # denominator = 0.5 + 0.5*(0.9 + 0.9*0.3) = 0.5 + 0.5*1.17 = 1.085
        # mult = 1.0 / 1.085 ~ 0.922
        assert mult < 1.0

    def test_cautious_green_slow(self, tmp_path: Path) -> None:
        """Cautious + inexperienced commander -> high multiplier (slow OODA)."""
        data = {**_PROFILE_DATA, "decision_speed": 0.1, "experience": 0.1}
        _write_yaml(tmp_path / "slow.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("slow_cdr", "test_profile")
        mult = engine.get_ooda_speed_multiplier("slow_cdr")
        # denominator = 0.5 + 0.5*(0.1 + 0.1*0.3) = 0.5 + 0.5*0.13 = 0.565
        # mult = 1.0 / 0.565 ~ 1.770
        assert mult > 1.0

    def test_unassigned_returns_base(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        assert engine.get_ooda_speed_multiplier("nobody") == 1.0

    def test_custom_base_mult(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        config = CommanderConfig(ooda_speed_base_mult=2.0)
        engine = _make_engine(loader, config=config)
        engine.assign_personality("u", "test_profile")
        mult = engine.get_ooda_speed_multiplier("u")
        # denominator = 0.5 + 0.5*(0.5 + 0.8*0.3) = 0.5 + 0.5*0.74 = 0.87
        # mult = 2.0 / 0.87 ~ 2.299
        assert mult > 2.0


class TestDecisionNoise:
    def test_noise_changes_scores(self, tmp_path: Path) -> None:
        data = {**_PROFILE_DATA, "experience": 0.5}
        _write_yaml(tmp_path / "p.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        scores = {"attack": 1.0, "defend": 0.5, "withdraw": 0.2}
        noised = engine.apply_decision_noise("u", scores)
        # With sigma = 0.1 * (1 - 0.5) = 0.05, noise should be small but present
        assert noised != scores

    def test_high_experience_less_noise(self, tmp_path: Path) -> None:
        """Higher experience = smaller noise magnitude."""
        data_vet = {**_PROFILE_DATA, "profile_id": "veteran", "experience": 0.95}
        data_green = {**_PROFILE_DATA, "profile_id": "green", "experience": 0.1}
        _write_yaml(tmp_path / "v.yaml", data_vet)
        _write_yaml(tmp_path / "g.yaml", data_green)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()

        scores = {"attack": 1.0, "defend": 0.5, "withdraw": 0.2}
        total_vet_delta = 0.0
        total_green_delta = 0.0
        n_runs = 200

        for seed in range(n_runs):
            eng = _make_engine(loader, seed=seed)
            eng.assign_personality("vet", "veteran")
            eng.assign_personality("grn", "green")
            nv = eng.apply_decision_noise("vet", scores)
            ng = eng.apply_decision_noise("grn", scores)
            total_vet_delta += sum(abs(nv[k] - scores[k]) for k in scores)
            total_green_delta += sum(abs(ng[k] - scores[k]) for k in scores)

        assert total_vet_delta < total_green_delta

    def test_preserves_keys(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        scores = {"attack": 1.0, "defend": 0.5, "withdraw": 0.2}
        noised = engine.apply_decision_noise("u", scores)
        assert set(noised.keys()) == set(scores.keys())

    def test_deterministic_with_same_seed(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        scores = {"attack": 1.0, "defend": 0.5}
        e1 = _make_engine(loader, seed=99)
        e1.assign_personality("u", "test_profile")
        r1 = e1.apply_decision_noise("u", scores)
        e2 = _make_engine(loader, seed=99)
        e2.assign_personality("u", "test_profile")
        r2 = e2.apply_decision_noise("u", scores)
        assert r1 == r2

    def test_unassigned_returns_copy(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        scores = {"attack": 1.0}
        noised = engine.apply_decision_noise("nobody", scores)
        assert noised == scores
        assert noised is not scores


class TestRiskThreshold:
    def test_cautious_higher_threshold(self, tmp_path: Path) -> None:
        data = {**_PROFILE_DATA, "caution": 0.9, "aggression": 0.1}
        _write_yaml(tmp_path / "caut.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        t = engine.get_risk_threshold("u")
        # base=0.3 * (1.0 + 0.9 - 0.1) = 0.3 * 1.8 = 0.54
        assert t == pytest.approx(0.54)
        assert t > 0.3  # higher than base

    def test_aggressive_lower_threshold(self, tmp_path: Path) -> None:
        data = {**_PROFILE_DATA, "caution": 0.1, "aggression": 0.9}
        _write_yaml(tmp_path / "agg.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        t = engine.get_risk_threshold("u")
        # base=0.3 * (1.0 + 0.1 - 0.9) = 0.3 * 0.2 = 0.06
        assert t == pytest.approx(0.06)
        assert t < 0.3  # lower than base

    def test_with_custom_base(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        t = engine.get_risk_threshold("u", base=0.5)
        # 0.5 * (1.0 + 0.4 - 0.6) = 0.5 * 0.8 = 0.4
        assert t == pytest.approx(0.4)

    def test_unassigned_returns_base(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        assert engine.get_risk_threshold("nobody") == 0.3
        assert engine.get_risk_threshold("nobody", base=0.7) == 0.7


class TestPreferredDoctrine:
    def test_returns_doctrine_id(self, tmp_path: Path) -> None:
        data = {**_PROFILE_DATA, "preferred_doctrine": "us_attack_deliberate"}
        _write_yaml(tmp_path / "p.yaml", data)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        assert engine.get_preferred_doctrine("u") == "us_attack_deliberate"

    def test_returns_none_when_no_preference(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u", "test_profile")
        assert engine.get_preferred_doctrine("u") is None

    def test_returns_none_for_unassigned(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        assert engine.get_preferred_doctrine("nobody") is None


class TestStateProtocol:
    def test_get_set_roundtrip(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("u1", "test_profile")
        engine.assign_personality("u2", "test_profile")

        state = engine.get_state()

        engine2 = _make_engine(loader, seed=99)
        engine2.set_state(state)
        assert engine2.get_personality("u1") is not None
        assert engine2.get_personality("u1").profile_id == "test_profile"
        assert engine2.get_personality("u2") is not None

    def test_state_is_dict(self, tmp_path: Path) -> None:
        loader = CommanderProfileLoader(data_dir=tmp_path)
        engine = _make_engine(loader)
        state = engine.get_state()
        assert isinstance(state, dict)
        assert "assignments" in state

    def test_set_state_replaces(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "p.yaml", _PROFILE_DATA)
        loader = CommanderProfileLoader(data_dir=tmp_path)
        loader.load_all()
        engine = _make_engine(loader)
        engine.assign_personality("old_unit", "test_profile")
        engine.set_state({"assignments": {"new_unit": "test_profile"}})
        assert engine.get_personality("old_unit") is None
        assert engine.get_personality("new_unit") is not None
