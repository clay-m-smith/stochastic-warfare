"""Tests for scenario listing and detail endpoints."""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest

from api.config import ApiSettings
from api.main import create_app
from api.routers import scenarios as scenario_router
from api.scenarios import invalidate_cache

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def test_list_scenarios_returns_list(client):
    resp = await client.get("/api/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 41


async def test_list_scenarios_has_required_fields(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    for s in data:
        assert "name" in s
        assert "display_name" in s
        assert "era" in s
        assert "sides" in s


async def test_list_scenarios_includes_base_scenario(client):
    resp = await client.get("/api/scenarios")
    names = [s["name"] for s in resp.json()]
    assert "73_easting" in names
    assert "golan_heights" in names
    assert "test_scenario" in names


async def test_list_scenarios_includes_era_scenarios(client):
    resp = await client.get("/api/scenarios")
    names = [s["name"] for s in resp.json()]
    assert "midway" in names
    assert "waterloo" in names
    assert "jutland" in names
    assert "salamis" in names


async def test_get_scenario_by_name(client):
    resp = await client.get("/api/scenarios/73_easting")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "73_easting"
    assert "config" in data
    assert "force_summary" in data


async def test_historical_claim_status_is_typed_and_conservative(client):
    listing = await client.get("/api/scenarios")
    assert listing.status_code == 200
    listed = next(scenario for scenario in listing.json() if scenario["name"] == "73_easting")
    detail = await client.get("/api/scenarios/73_easting")
    assert detail.status_code == 200
    detailed = detail.json()

    assert listed["historical_validation"] == detailed["historical_validation"]
    validation = detailed["historical_validation"]
    assert validation["aggregate_disposition"] == "unsupported"
    assert validation["current_engine_regression_evidence"] is True
    assert validation["accepted_claim_ids"] == []
    assert validation["claims"]
    assert all(
        set(claim)
        == {
            "claim_id",
            "disposition",
            "reason_codes",
            "limitation",
            "intended_use",
            "metric_scope",
            "event_scope",
            "current_engine_regression_evidence",
            "accepted_study_id",
            "accepted_artifact_path",
        }
        for claim in validation["claims"]
    )
    claim = next(
        claim for claim in validation["claims"] if claim["claim_id"] == "scenario.73_easting.documented_outcomes"
    )
    assert claim["current_engine_regression_evidence"] is True
    assert len(validation["ledger_sha256"]) == 64


async def test_missing_historical_claim_identity_is_unsupported(client):
    response = await client.get("/api/scenarios/test_scenario")
    assert response.status_code == 200

    validation = response.json()["historical_validation"]
    assert validation["aggregate_disposition"] == "unsupported"
    assert validation["accepted_claim_ids"] == []
    assert validation["current_engine_regression_evidence"] is False
    assert validation["claims"][0]["reason_codes"] == [
        "missing_ledger_identity",
    ]
    assert validation["claims"][0]["current_engine_regression_evidence"] is False
    assert "No inventoried claim" in validation["claims"][0]["limitation"]


async def test_external_catalog_symlink_does_not_inherit_canonical_claim(
    tmp_path: Path,
) -> None:
    external_data = tmp_path / "renamed-catalog"
    source = Path("data/scenarios/73_easting").resolve()
    destination = external_data / "scenarios/73_easting"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(source, target_is_directory=True)
    settings = ApiSettings(
        db_path=":memory:",
        data_dir=str(external_data),
    )
    app = create_app(settings)
    invalidate_cache()
    scenario_router._load_historical_claim_ledger.cache_clear()

    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                listing_response = await client.get("/api/scenarios")
                detail_response = await client.get("/api/scenarios/73_easting")
    finally:
        invalidate_cache()
        scenario_router._load_historical_claim_ledger.cache_clear()

    assert listing_response.status_code == 200
    assert detail_response.status_code == 200
    listed = next(scenario for scenario in listing_response.json() if scenario["name"] == "73_easting")[
        "historical_validation"
    ]
    detailed = detail_response.json()["historical_validation"]
    assert listed == detailed
    assert detailed["aggregate_disposition"] == "unsupported"
    assert detailed["current_engine_regression_evidence"] is False
    assert detailed["accepted_claim_ids"] == []
    assert len(detailed["claims"]) == 1
    assert detailed["claims"][0]["claim_id"].startswith(
        "synthetic.unsupported.",
    )
    assert detailed["claims"][0]["reason_codes"] == [
        "missing_ledger_identity",
    ]
    assert detailed["claims"][0]["current_engine_regression_evidence"] is False
    assert "scenario.73_easting.documented_outcomes" not in detail_response.text
    assert str(tmp_path) not in listing_response.text
    assert str(tmp_path) not in detail_response.text


async def test_detail_does_not_publish_legacy_outcomes_as_configuration(client):
    response = await client.get("/api/scenarios/73_easting")
    data = response.json()

    assert "documented_outcomes" not in data["config"]
    assert "sources" not in data["config"]
    assert "sides" in data["config"]


async def test_get_scenario_era(client):
    resp = await client.get("/api/scenarios/midway")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "midway"
    assert "config" in data


async def test_get_scenario_config_has_sides(client):
    # Use test_campaign which has standard sides format
    resp = await client.get("/api/scenarios/test_campaign")
    data = resp.json()
    assert "sides" in data["config"]
    assert len(data["config"]["sides"]) >= 2


async def test_get_scenario_force_summary(client):
    resp = await client.get("/api/scenarios/test_campaign")
    data = resp.json()
    fs = data["force_summary"]
    assert len(fs) >= 2
    for side, info in fs.items():
        assert "unit_count" in info
        assert "unit_types" in info


async def test_get_scenario_not_found(client):
    resp = await client.get("/api/scenarios/nonexistent_scenario_xyz")
    assert resp.status_code == 404


async def test_scenario_resolver_rejects_path_aliases() -> None:
    from api.scenarios import resolve_scenario

    for name in (
        "../eras/napoleonic/scenarios/austerlitz",
        "test_campaign/scenario.yaml",
        r"..\eras\napoleonic\scenarios\austerlitz",
    ):
        with pytest.raises(
            ValueError,
            match="one lowercase directory identifier",
        ):
            resolve_scenario(name, Path("data"))


async def test_scenarios_have_era_field(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    eras = {s["era"] for s in data}
    assert "modern" in eras or "" in eras


async def test_scenario_detail_config_serializable(client):
    resp = await client.get("/api/scenarios/test_scenario")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["config"], dict)


async def test_scenario_ew_cbrn_flags(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    # At least one scenario should have EW or CBRN
    has_ew = any(s.get("has_ew") for s in data)
    has_cbrn = any(s.get("has_cbrn") for s in data)
    assert has_ew or has_cbrn


async def test_list_scenarios_classifies_live_optional_subsystem_configs(client):
    response = await client.get("/api/scenarios")
    assert response.status_code == 200
    scenarios = {scenario["name"]: scenario for scenario in response.json()}

    assert {name for name, scenario in scenarios.items() if scenario["has_schools"]} == set()
    assert {name for name, scenario in scenarios.items() if scenario["has_dew"]} == {
        "taiwan_strait",
    }
    assert {name for name, scenario in scenarios.items() if scenario["has_space"]} == {
        "korean_peninsula",
        "space_asat_escalation",
        "space_isr_gap",
        "taiwan_strait",
    }


async def test_list_scenarios_no_duplicates(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()
    names = [s["name"] for s in data]
    assert len(names) == len(set(names))
