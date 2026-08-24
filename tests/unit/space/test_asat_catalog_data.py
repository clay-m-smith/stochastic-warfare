"""Strict data and reference integrity proofs for Phase 110 space catalogs."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.validate_scenario_data import (
    validate_space_catalogs,
    validate_space_yaml,
)
from stochastic_warfare.space.asat import ASATEngine
from stochastic_warfare.space.catalog import SpaceCatalog
from stochastic_warfare.space.config import (
    ASATAssetConfig,
    ASATOrderConfig,
    ASATWeaponDefinition,
    ConstellationDefinition,
    SpaceConfig,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    load_campaign_scenario_config,
)


DATA_DIR = Path("data")


def _asset(
    *,
    asset_id: str = "red_nudol_1",
    weapon_id: str = "nudol_asat",
    side: str = "red",
    rounds_available: int = 1,
) -> ASATAssetConfig:
    return ASATAssetConfig(
        asset_id=asset_id,
        weapon_id=weapon_id,
        side=side,
        rounds_available=rounds_available,
    )


def _order(
    *,
    order_id: str = "order_1",
    asset_id: str = "red_nudol_1",
    target_satellite_id: str = "keyhole_optical_p0_s0",
    execute_at_s: float = 3600.0,
) -> ASATOrderConfig:
    return ASATOrderConfig(
        order_id=order_id,
        asset_id=asset_id,
        target_satellite_id=target_satellite_id,
        execute_at_s=execute_at_s,
    )


def _config(
    *,
    constellations: list[str] | None = None,
    enable_asat: bool = True,
    assets: list[ASATAssetConfig] | None = None,
    orders: list[ASATOrderConfig] | None = None,
) -> SpaceConfig:
    return SpaceConfig(
        enable_space=True,
        constellation_ids=(
            ["keyhole_optical"]
            if constellations is None
            else constellations
        ),
        enable_asat=enable_asat,
        asat_assets=[_asset()] if assets is None else assets,
        asat_orders=[_order()] if orders is None else orders,
    )


def test_production_space_catalog_has_exact_strict_counts() -> None:
    catalog = SpaceCatalog.load(DATA_DIR)
    assert len(catalog.constellations) == 11
    assert len(catalog.weapons) == 3

    result, stats = validate_space_catalogs()
    assert result.ok
    assert result.errors == []
    assert result.warnings == []
    assert stats.constellations == 11
    assert stats.asat_weapons == 3


@pytest.mark.parametrize(
    ("model", "payload", "message"),
    (
        (
            ConstellationDefinition,
            {
                "constellation_id": "bad",
                "constellation_type": 99,
                "side": "blue",
                "num_satellites": 1,
                "plane_count": 1,
                "sats_per_plane": 1,
                "orbital_elements_template": {
                    "semi_major_axis_m": 6_871_000.0,
                    "eccentricity": 0.0,
                    "inclination_deg": 0.0,
                    "raan_deg": 0.0,
                    "arg_perigee_deg": 0.0,
                    "true_anomaly_deg": 0.0,
                },
            },
            "unknown constellation_type",
        ),
        (
            ConstellationDefinition,
            {
                "constellation_id": "bad",
                "constellation_type": 2,
                "side": "blue",
                "num_satellites": 3,
                "plane_count": 2,
                "sats_per_plane": 2,
                "orbital_elements_template": {
                    "semi_major_axis_m": 6_871_000.0,
                    "eccentricity": 0.0,
                    "inclination_deg": 0.0,
                    "raan_deg": 0.0,
                    "arg_perigee_deg": 0.0,
                    "true_anomaly_deg": 0.0,
                },
            },
            "num_satellites must equal",
        ),
        (
            ASATWeaponDefinition,
            {
                "weapon_id": "bad",
                "asat_type": 0,
                "lethal_radius_m": -1.0,
                "guidance_sigma_m": 1.0,
                "min_altitude_km": 200.0,
                "max_altitude_km": 1000.0,
                "closing_velocity_mps": 8000.0,
                "reload_time_s": 0.0,
                "dazzle_duration_s": 0.0,
                "dazzle_range_km": 0.0,
            },
            "positive lethal radius",
        ),
        (
            ASATWeaponDefinition,
            {
                "weapon_id": "bad",
                "asat_type": True,
                "lethal_radius_m": 1.0,
                "guidance_sigma_m": 1.0,
                "min_altitude_km": 200.0,
                "max_altitude_km": 1000.0,
                "closing_velocity_mps": 8000.0,
                "reload_time_s": 0.0,
                "dazzle_duration_s": 0.0,
                "dazzle_range_km": 0.0,
            },
            "integer enum value",
        ),
    ),
)
def test_strict_definition_semantics(
    model,
    payload: dict,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload)


def test_space_models_reject_unknown_fields_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        SpaceConfig.model_validate(
            {
                "enable_space": True,
                "constellation_ids": ["keyhole_optical"],
                "unexpected": True,
            },
        )
    with pytest.raises(ValidationError, match="constellation_ids"):
        SpaceConfig(
            enable_space=True,
            constellation_ids=["keyhole_optical", "keyhole_optical"],
        )
    with pytest.raises(ValidationError, match="unique asset_id"):
        SpaceConfig(
            enable_space=True,
            constellation_ids=["keyhole_optical"],
            asat_assets=[_asset(), _asset()],
        )
    with pytest.raises(ValidationError, match="unique order_id"):
        SpaceConfig(
            enable_space=True,
            constellation_ids=["keyhole_optical"],
            asat_assets=[_asset()],
            asat_orders=[_order(), _order()],
        )


def test_asat_gate_cardinality_and_disabled_control_contract() -> None:
    with pytest.raises(ValidationError, match="requires at least one"):
        SpaceConfig(
            enable_space=True,
            constellation_ids=["keyhole_optical"],
            enable_asat=True,
        )
    with pytest.raises(ValidationError, match="enable_space=false"):
        SpaceConfig(
            enable_space=False,
            constellation_ids=["keyhole_optical"],
        )

    disabled = _config(enable_asat=False)
    assert disabled.asat_assets == [_asset()]
    assert disabled.asat_orders == [_order()]


def test_catalog_rejects_unknown_friendly_unsupported_and_unreachable() -> None:
    catalog = SpaceCatalog.load(DATA_DIR)
    with pytest.raises(ValueError, match="unknown constellation_id"):
        catalog.resolve(
            _config(constellations=["missing"]),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="friendly satellite"):
        catalog.resolve(
            _config(assets=[_asset(side="blue")]),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="unknown weapon_id"):
        catalog.resolve(
            _config(assets=[_asset(weapon_id="missing_weapon")]),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="unknown selected target_satellite_id"):
        catalog.resolve(
            _config(
                orders=[
                    _order(
                        target_satellite_id="missing_satellite",
                    ),
                ],
            ),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="unknown scenario side"):
        catalog.resolve(
            _config(assets=[_asset(side="undeclared")]),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="unsupported production type"):
        catalog.resolve(
            _config(
                assets=[
                    _asset(
                        weapon_id="ground_laser_dazzle",
                    ),
                ],
            ),
            scenario_sides={"blue", "red"},
        )
    with pytest.raises(ValueError, match="does not intersect"):
        catalog.resolve(
            _config(
                constellations=["gps_navstar"],
                orders=[
                    _order(
                        target_satellite_id="gps_navstar_p0_s0",
                    ),
                ],
            ),
            scenario_sides={"blue", "red"},
        )


def test_space_scenario_rejects_unknown_asset_and_unreachable_schedule() -> None:
    with pytest.raises(ValidationError, match="unknown asset_id"):
        SpaceConfig(
            enable_space=True,
            constellation_ids=["keyhole_optical"],
            asat_assets=[_asset()],
            asat_orders=[_order(asset_id="missing_asset")],
        )

    payload = load_campaign_scenario_config(
        DATA_DIR / "scenarios/space_asat_escalation/scenario.yaml",
    ).model_dump(mode="python")
    payload["space_config"]["asat_orders"][0]["execute_at_s"] = (
        payload["duration_hours"] * 3600.0 + 1.0
    )
    with pytest.raises(ValidationError, match="exceeds scenario duration"):
        CampaignScenarioConfig.model_validate(payload)


@pytest.mark.parametrize(
    "invalid_duration",
    (math.nan, math.inf, True),
)
def test_space_schedule_requires_strict_finite_scenario_duration(
    invalid_duration: float | bool,
) -> None:
    payload = load_campaign_scenario_config(
        DATA_DIR / "scenarios/space_asat_escalation/scenario.yaml",
    ).model_dump(mode="python")
    payload["duration_hours"] = invalid_duration
    with pytest.raises(
        ValidationError,
        match="duration_hours must be a finite positive number",
    ):
        CampaignScenarioConfig.model_validate(payload)


def test_catalog_definitions_require_literal_orbital_and_weapon_fields() -> None:
    constellation = SpaceCatalog.load(DATA_DIR).constellations[
        "keyhole_optical"
    ].model_dump(mode="python")
    constellation["orbital_elements_template"].pop("true_anomaly_deg")
    with pytest.raises(ValidationError, match="true_anomaly_deg"):
        ConstellationDefinition.model_validate(constellation)
    constellation = SpaceCatalog.load(DATA_DIR).constellations[
        "keyhole_optical"
    ].model_dump(mode="python")
    constellation["orbital_elements_template"][
        "semi_major_axis_m"
    ] = 1.0e200
    with pytest.raises(ValidationError, match="supported Earth-orbit envelope"):
        ConstellationDefinition.model_validate(constellation)

    weapon = SpaceCatalog.load(DATA_DIR).weapons["nudol_asat"].model_dump(
        mode="python",
    )
    weapon.pop("reload_time_s")
    with pytest.raises(ValidationError, match="reload_time_s"):
        ASATWeaponDefinition.model_validate(weapon)


def test_rayleigh_probability_saturates_without_overflow() -> None:
    weapon = SpaceCatalog.load(DATA_DIR).weapons[
        "nudol_asat"
    ].model_copy(
        update={
            "lethal_radius_m": 1.0e200,
            "guidance_sigma_m": 1.0,
        },
    )
    assert ASATEngine._compute_kinetic_pk(weapon) == 1.0


def test_space_config_rejects_poisson_means_outside_generator_domain() -> None:
    payload = _config().model_dump(mode="python")
    payload["debris_fragment_mean"] = 1.0e300
    with pytest.raises(ValidationError, match="safe Poisson sampling limit"):
        SpaceConfig.model_validate(payload)


def test_catalog_rejects_duplicate_semantic_ids_across_files(
    tmp_path: Path,
) -> None:
    constellation_dir = tmp_path / "space/constellations"
    weapon_dir = tmp_path / "space/asat_weapons"
    constellation_dir.mkdir(parents=True)
    weapon_dir.mkdir(parents=True)
    constellation_yaml = "\n".join(
        (
            "constellation_id: duplicated",
            "display_name: Duplicate",
            "constellation_type: 2",
            "side: blue",
            "num_satellites: 1",
            "orbital_elements_template:",
            "  semi_major_axis_m: 6871000.0",
            "  eccentricity: 0.0",
            "  inclination_deg: 0.0",
            "  raan_deg: 0.0",
            "  arg_perigee_deg: 0.0",
            "  true_anomaly_deg: 0.0",
            "plane_count: 1",
            "sats_per_plane: 1",
            "sensor_resolution_m: 1.0",
            "sensor_swath_km: 10.0",
            "sensor_type: optical",
            "bandwidth_bps: 0.0",
        ),
    )
    (constellation_dir / "a.yaml").write_text(
        constellation_yaml,
        encoding="utf-8",
    )
    (constellation_dir / "b.yaml").write_text(
        constellation_yaml,
        encoding="utf-8",
    )
    (weapon_dir / "valid.yaml").write_text(
        "\n".join(
            (
                "weapon_id: valid",
                "display_name: Valid",
                "asat_type: 0",
                "lethal_radius_m: 1.0",
                "guidance_sigma_m: 1.0",
                "min_altitude_km: 200.0",
                "max_altitude_km: 1000.0",
                "closing_velocity_mps: 8000.0",
                "reload_time_s: 0.0",
                "dazzle_duration_s: 0.0",
                "dazzle_range_km: 0.0",
            ),
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate constellation_id"):
        SpaceCatalog.load(tmp_path)


def test_two_assets_can_share_one_definition_without_overwrite() -> None:
    catalog = SpaceCatalog.load(DATA_DIR)
    assets = [
        _asset(asset_id="red_nudol_1"),
        _asset(asset_id="red_nudol_2"),
    ]
    orders = [
        _order(order_id="order_1", asset_id="red_nudol_1"),
        _order(
            order_id="order_2",
            asset_id="red_nudol_2",
            target_satellite_id="keyhole_optical_p0_s1",
        ),
    ]
    resolved = catalog.resolve(
        _config(assets=assets, orders=orders),
        scenario_sides={"blue", "red"},
    )
    assert [asset.asset_id for asset in resolved.assets] == [
        "red_nudol_1",
        "red_nudol_2",
    ]
    assert set(resolved.weapon_definitions) == {"nudol_asat"}


def test_single_file_validator_routes_space_files(tmp_path: Path) -> None:
    path = tmp_path / "asat_weapons"
    path.mkdir()
    bad_file = path / "bad.yaml"
    bad_file.write_text(
        "\n".join(
            (
                "weapon_id: duplicate",
                "weapon_id: overwritten",
                "asat_type: 0",
            ),
        ),
        encoding="utf-8",
    )
    result = validate_space_yaml(bad_file)
    assert not result.ok
    assert "duplicate yaml mapping key" in result.errors[0].lower()
