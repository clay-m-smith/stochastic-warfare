"""Tests for stochastic_warfare.c2.ai.doctrine — doctrine templates + YAML loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import TS  # noqa: F401 — shared timestamp constant

from stochastic_warfare.c2.ai.doctrine import (
    DoctrineCategory,
    DoctrineEngine,
    DoctrineTemplate,
    DoctrineTemplateLoader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_YAML = """\
doctrine_id: test_attack
display_name: "Test Attack"
category: OFFENSIVE
faction: generic
description: "A test offensive doctrine"
min_echelon: 5
max_echelon: 10
applicable_domains: ["LAND"]
phases: ["SHAPE", "DECIDE"]
force_ratios:
  main_effort: 0.7
  reserve: 0.3
actions: ["attack", "suppress", "exploit"]
priorities: ["firepower", "maneuver", "protection"]
risk_tolerance: moderate
tempo: high
"""

_SAMPLE_DEFENSE_YAML = """\
doctrine_id: test_defense
display_name: "Test Defense"
category: DEFENSIVE
faction: generic
description: "A test defensive doctrine"
min_echelon: 4
max_echelon: 9
applicable_domains: ["LAND", "SEA"]
phases: ["PREPARE", "DEFEND"]
force_ratios:
  main: 0.6
  reserve: 0.4
actions: ["defend", "counterattack", "block"]
priorities: ["protection", "firepower"]
risk_tolerance: low
tempo: slow
"""


def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    """Write YAML content to a file under *tmp_path* and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


def _make_loader_with_samples(tmp_path: Path) -> DoctrineTemplateLoader:
    """Create a loader with two sample YAML files."""
    _write_yaml(tmp_path, "attack.yaml", _SAMPLE_YAML)
    _write_yaml(tmp_path, "defense.yaml", _SAMPLE_DEFENSE_YAML)
    loader = DoctrineTemplateLoader(data_dir=tmp_path)
    loader.load_all()
    return loader


# ---------------------------------------------------------------------------
# DoctrineCategory enum
# ---------------------------------------------------------------------------


class TestDoctrineCategory:
    def test_enum_values(self) -> None:
        assert DoctrineCategory.OFFENSIVE == 0
        assert DoctrineCategory.DEFENSIVE == 1
        assert DoctrineCategory.RETROGRADE == 2
        assert DoctrineCategory.STABILITY == 3
        assert DoctrineCategory.ENABLING == 4

    def test_enum_count(self) -> None:
        assert len(DoctrineCategory) == 5

    def test_enum_names(self) -> None:
        names = {c.name for c in DoctrineCategory}
        assert names == {"OFFENSIVE", "DEFENSIVE", "RETROGRADE", "STABILITY", "ENABLING"}


# ---------------------------------------------------------------------------
# DoctrineTemplate pydantic model
# ---------------------------------------------------------------------------


class TestDoctrineTemplate:
    def test_validate_from_dict(self) -> None:
        data = {
            "doctrine_id": "test_1",
            "display_name": "Test",
            "category": "OFFENSIVE",
            "faction": "generic",
            "description": "desc",
            "min_echelon": 5,
            "max_echelon": 10,
            "applicable_domains": ["LAND"],
            "phases": ["A", "B"],
            "force_ratios": {"main": 0.7, "reserve": 0.3},
            "actions": ["attack"],
            "priorities": ["firepower"],
            "risk_tolerance": "moderate",
            "tempo": "high",
        }
        tmpl = DoctrineTemplate.model_validate(data)
        assert tmpl.doctrine_id == "test_1"
        assert tmpl.min_echelon == 5
        assert tmpl.max_echelon == 10
        assert tmpl.applicable_domains == ["LAND"]

    def test_category_enum_property(self) -> None:
        data = {
            "doctrine_id": "t",
            "display_name": "T",
            "category": "RETROGRADE",
            "faction": "generic",
            "description": "d",
            "min_echelon": 4,
            "max_echelon": 10,
            "applicable_domains": ["LAND"],
            "phases": [],
            "force_ratios": {},
            "actions": [],
            "priorities": [],
            "risk_tolerance": "low",
            "tempo": "slow",
        }
        tmpl = DoctrineTemplate.model_validate(data)
        assert tmpl.category_enum == DoctrineCategory.RETROGRADE

    def test_invalid_category_raises(self) -> None:
        data = {
            "doctrine_id": "t",
            "display_name": "T",
            "category": "NONEXISTENT",
            "faction": "generic",
            "description": "d",
            "min_echelon": 4,
            "max_echelon": 10,
            "applicable_domains": ["LAND"],
            "phases": [],
            "force_ratios": {},
            "actions": [],
            "priorities": [],
            "risk_tolerance": "low",
            "tempo": "slow",
        }
        tmpl = DoctrineTemplate.model_validate(data)
        with pytest.raises(KeyError):
            _ = tmpl.category_enum

    def test_force_ratios_are_dict(self) -> None:
        data = {
            "doctrine_id": "t",
            "display_name": "T",
            "category": "OFFENSIVE",
            "faction": "us",
            "description": "d",
            "min_echelon": 5,
            "max_echelon": 10,
            "applicable_domains": ["LAND"],
            "phases": ["A"],
            "force_ratios": {"main_effort": 0.6, "supporting": 0.25, "reserve": 0.15},
            "actions": ["attack"],
            "priorities": ["firepower"],
            "risk_tolerance": "moderate",
            "tempo": "moderate",
        }
        tmpl = DoctrineTemplate.model_validate(data)
        assert abs(sum(tmpl.force_ratios.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# DoctrineTemplateLoader
# ---------------------------------------------------------------------------


class TestDoctrineTemplateLoader:
    def test_load_single_definition(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "attack.yaml", _SAMPLE_YAML)
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        defn = loader.load_definition(p)
        assert defn.doctrine_id == "test_attack"
        assert defn.category == "OFFENSIVE"

    def test_load_all(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "a.yaml", _SAMPLE_YAML)
        _write_yaml(tmp_path, "b.yaml", _SAMPLE_DEFENSE_YAML)
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        loader.load_all()
        assert len(loader.all_definitions()) == 2

    def test_get_definition(self, tmp_path: Path) -> None:
        p = _write_yaml(tmp_path, "attack.yaml", _SAMPLE_YAML)
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        loader.load_definition(p)
        got = loader.get_definition("test_attack")
        assert got.doctrine_id == "test_attack"

    def test_get_definition_missing_raises(self, tmp_path: Path) -> None:
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")

    def test_all_definitions_sorted(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "b.yaml", _SAMPLE_DEFENSE_YAML)
        _write_yaml(tmp_path, "a.yaml", _SAMPLE_YAML)
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        loader.load_all()
        ids = [d.doctrine_id for d in loader.all_definitions()]
        assert ids == sorted(ids)

    def test_load_all_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        _write_yaml(sub, "attack.yaml", _SAMPLE_YAML)
        loader = DoctrineTemplateLoader(data_dir=tmp_path)
        loader.load_all()
        assert len(loader.all_definitions()) == 1


# ---------------------------------------------------------------------------
# Real YAML data files
# ---------------------------------------------------------------------------


class TestRealYamlFiles:
    """Load all 10 real YAML files from data/doctrine/."""

    @pytest.fixture
    def real_loader(self) -> DoctrineTemplateLoader:
        loader = DoctrineTemplateLoader()  # default data dir
        loader.load_all()
        return loader

    def test_all_ten_files_loaded(self, real_loader: DoctrineTemplateLoader) -> None:
        assert len(real_loader.all_definitions()) == 10

    def test_us_attack_deliberate(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("us_attack_deliberate")
        assert d.faction == "us"
        assert d.category_enum == DoctrineCategory.OFFENSIVE
        assert d.min_echelon == 5
        assert d.max_echelon == 10
        assert "attack" in d.actions

    def test_us_defend_area(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("us_defend_area")
        assert d.category_enum == DoctrineCategory.DEFENSIVE
        assert "defend" in d.actions

    def test_us_movement_to_contact(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("us_movement_to_contact")
        assert d.category_enum == DoctrineCategory.OFFENSIVE
        assert d.min_echelon == 4  # Platoon level

    def test_russian_deep_operations(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("russian_deep_operations")
        assert d.faction == "russian"
        assert d.risk_tolerance == "high"
        assert d.tempo == "high"

    def test_russian_defense_in_depth(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("russian_defense_in_depth")
        assert d.category_enum == DoctrineCategory.DEFENSIVE
        assert d.min_echelon == 6  # Battalion

    def test_nato_collective_defense(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("nato_collective_defense")
        assert d.faction == "nato"
        assert "SEA" in d.applicable_domains
        assert "AIR" in d.applicable_domains

    def test_generic_delay(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("generic_delay")
        assert d.category_enum == DoctrineCategory.RETROGRADE

    def test_generic_retrograde(self, real_loader: DoctrineTemplateLoader) -> None:
        d = real_loader.get_definition("generic_retrograde")
        assert d.category_enum == DoctrineCategory.RETROGRADE
        assert "withdraw" in d.actions

    def test_all_force_ratios_sum_to_one(self, real_loader: DoctrineTemplateLoader) -> None:
        for defn in real_loader.all_definitions():
            total = sum(defn.force_ratios.values())
            assert abs(total - 1.0) < 1e-9, (
                f"{defn.doctrine_id} force_ratios sum to {total}"
            )

    def test_all_have_nonempty_phases(self, real_loader: DoctrineTemplateLoader) -> None:
        for defn in real_loader.all_definitions():
            assert len(defn.phases) > 0, f"{defn.doctrine_id} has empty phases"


# ---------------------------------------------------------------------------
# DoctrineEngine
# ---------------------------------------------------------------------------


class TestDoctrineEngine:
    @pytest.fixture
    def engine(self, tmp_path: Path) -> DoctrineEngine:
        loader = _make_loader_with_samples(tmp_path)
        return DoctrineEngine(loader)

    # -- get_applicable_doctrine --

    def test_preferred_id_returned_when_valid(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5, domain="LAND")
        assert result is not None
        assert result.doctrine_id == "test_attack"

    def test_preferred_id_skipped_when_echelon_out_of_range(self, engine: DoctrineEngine) -> None:
        # test_attack requires min_echelon=5; echelon=3 should fail
        result = engine.get_applicable_doctrine("test_attack", echelon=3, domain="LAND")
        # Falls back — test_defense has min_echelon=4 so echelon=3 also fails
        assert result is None

    def test_preferred_id_skipped_when_domain_mismatches(self, engine: DoctrineEngine) -> None:
        # test_attack is LAND only
        result = engine.get_applicable_doctrine("test_attack", echelon=5, domain="AIR")
        # Falls back to test_defense which is LAND+SEA — also no AIR
        assert result is None

    def test_fallback_when_preferred_not_found(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("nonexistent", echelon=5, domain="LAND")
        assert result is not None
        # Should pick first matching (alphabetical): test_attack
        assert result.doctrine_id == "test_attack"

    def test_fallback_when_preferred_is_none(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine(None, echelon=5, domain="LAND")
        assert result is not None

    def test_echelon_filtering(self, engine: DoctrineEngine) -> None:
        # echelon=4: test_attack requires 5+, test_defense accepts 4-9
        result = engine.get_applicable_doctrine(None, echelon=4, domain="LAND")
        assert result is not None
        assert result.doctrine_id == "test_defense"

    def test_domain_filtering_sea(self, engine: DoctrineEngine) -> None:
        # Only test_defense has SEA domain
        result = engine.get_applicable_doctrine(None, echelon=5, domain="SEA")
        assert result is not None
        assert result.doctrine_id == "test_defense"

    def test_returns_none_when_nothing_matches(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine(None, echelon=1, domain="LAND")
        assert result is None

    def test_echelon_above_max_rejected(self, engine: DoctrineEngine) -> None:
        # Both templates max at 9 or 10
        result = engine.get_applicable_doctrine(None, echelon=13, domain="LAND")
        assert result is None

    # -- filter_actions --

    def test_filter_actions_keeps_matching(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        # actions = ["attack", "suppress", "exploit"]
        names = ["attack", "defend", "suppress", "withdraw"]
        indices = [0, 1, 2, 3]
        kept = engine.filter_actions(result, indices, names)
        assert kept == [0, 2]  # "attack" and "suppress"

    def test_filter_actions_removes_all_non_matching(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        names = ["defend", "withdraw", "screen"]
        indices = [0, 1, 2]
        kept = engine.filter_actions(result, indices, names)
        assert kept == []

    def test_filter_actions_empty_candidates(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        kept = engine.filter_actions(result, [], ["attack"])
        assert kept == []

    # -- get_force_allocation --

    def test_get_force_allocation(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        alloc = engine.get_force_allocation(result)
        assert alloc == {"main_effort": 0.7, "reserve": 0.3}

    def test_get_force_allocation_is_copy(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        alloc = engine.get_force_allocation(result)
        alloc["main_effort"] = 0.0  # mutate copy
        # Original should be unchanged
        assert result.force_ratios["main_effort"] == 0.7

    # -- get_priority_actions --

    def test_get_priority_actions_default_n(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        prios = engine.get_priority_actions(result)
        assert prios == ["firepower", "maneuver", "protection"]

    def test_get_priority_actions_n_1(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_attack", echelon=5)
        assert result is not None
        prios = engine.get_priority_actions(result, n=1)
        assert prios == ["firepower"]

    def test_get_priority_actions_n_exceeds_list(self, engine: DoctrineEngine) -> None:
        result = engine.get_applicable_doctrine("test_defense", echelon=5)
        assert result is not None
        # test_defense has 2 priorities; asking for 5 should return all 2
        prios = engine.get_priority_actions(result, n=5)
        assert prios == ["protection", "firepower"]
