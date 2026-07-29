"""Production-path behavioral proofs for Phase 109 equipment integrity."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.detection.signatures import (
    RadarSignature,
    SignatureProfile,
)
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.entities.loader import UnitLoader
from stochastic_warfare.simulation.campaign import CampaignConfig
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.engine import EngineConfig, SimulationEngine
from stochastic_warfare.simulation.loadouts import (
    ReferenceKind,
    ResolutionDisposition,
    SensorModeledRole,
    WeaponAttachment,
)
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.scenario import ScenarioLoader


DATA_DIR = Path("data")


def _load(name: str, seed: int = 109):
    return ScenarioLoader(DATA_DIR).load(
        DATA_DIR / "scenarios" / name / "scenario.yaml",
        seed=seed,
    )


def _load_path(path: Path, seed: int = 109):
    return ScenarioLoader(DATA_DIR).load(path, seed=seed)


def _unit_of_type(ctx, unit_type: str):
    return next(unit for unit in ctx.all_units() if unit.unit_type == unit_type)


def test_corrected_production_loadouts_and_store_topology() -> None:
    debecka = _load("debecka_pass")
    b52 = _unit_of_type(debecka, "b52h")
    b52_attachments = debecka.unit_weapons[b52.entity_id]
    assert [item.weapon.weapon_id for item in b52_attachments] == [
        "bomb_rack_generic",
    ]
    assert all(isinstance(item, WeaponAttachment) for item in b52_attachments)
    bomb_rack = b52_attachments[0]
    assert bomb_rack.source_equipment.name == "CSRL Rotary Launcher"
    assert bomb_rack.source_equipment is bomb_rack.weapon.equipment
    assert "fim92_stinger" not in {item.weapon.weapon_id for item in b52_attachments}
    assert [ammo.ammo_id for ammo in bomb_rack.ammunition] == ["gbu31_jdam"]
    assert bomb_rack.weapon.definition.compatible_ammo == ["gbu31_jdam"]
    assert bomb_rack.weapon.ammo_state.rounds_by_type == {"gbu31_jdam": 5}
    ammo_id = bomb_rack.ammunition[0].ammo_id
    before = bomb_rack.weapon.ammo_state.available(ammo_id)
    assert bomb_rack.weapon.fire(ammo_id)
    assert bomb_rack.weapon.ammo_state.available(ammo_id) == before - 1

    falklands = _load_path(
        DATA_DIR / "scenarios/falklands_san_carlos/scenario.yaml",
    )
    skyhawk = _unit_of_type(falklands, "a4_skyhawk")
    skyhawk_rack = next(
        attachment
        for attachment in falklands.unit_weapons[skyhawk.entity_id]
        if attachment.source_equipment.name == "Generic Bomb Rack"
    )
    assert [ammo.ammo_id for ammo in skyhawk_rack.ammunition] == ["mk82_500lb"]
    assert skyhawk_rack.weapon.ammo_state.rounds_by_type == {"mk82_500lb": 5}

    khafji = _load("khafji")
    for unit_type, rack_name, rack_id in (
        ("a10a", "MAU-40/A Bomb Ejector Rack", "mau40a_bomb_ejector_rack"),
        ("av8b", "BRU-36/A Bomb Ejector Rack", "bru36a_bomb_ejector_rack"),
    ):
        aircraft = _unit_of_type(khafji, unit_type)
        rockeye_rack = next(
            attachment
            for attachment in khafji.unit_weapons[aircraft.entity_id]
            if attachment.source_equipment.name == rack_name
        )
        assert rockeye_rack.weapon.weapon_id == rack_id
        assert [ammo.ammo_id for ammo in rockeye_rack.ammunition] == [
            "mk20_rockeye",
        ]
        assert rockeye_rack.weapon.definition.compatible_ammo == [
            "mk20_rockeye",
        ]
        assert rockeye_rack.weapon.ammo_state.rounds_by_type == {
            "mk20_rockeye": 1,
        }
        rockeye_store = next(
            resolution
            for resolution in khafji.equipment_resolutions[aircraft.entity_id]
            if resolution.source_equipment.name == "Mk 20 Rockeye II CBU"
        )
        assert rockeye_store.disposition is ResolutionDisposition.STORE
        assert rockeye_store.target_id == "mk20_rockeye"
        assert rockeye_store.attached_to_target_id == rack_id
        before = rockeye_rack.weapon.ammo_state.available("mk20_rockeye")
        assert rockeye_rack.weapon.fire("mk20_rockeye")
        assert rockeye_rack.weapon.ammo_state.available("mk20_rockeye") == before - 1

    korean = _load("korean_peninsula")
    patriot = _unit_of_type(korean, "patriot")
    assert [item.weapon.weapon_id for item in korean.unit_weapons[patriot.entity_id]] == ["mim104_pac3"]

    bradley = _unit_of_type(korean, "m3a2_bradley")
    bradley_weapons = korean.unit_weapons[bradley.entity_id]
    assert sum(item.weapon.weapon_id == "tow2_atgm" for item in bradley_weapons) == 1
    tow_store = next(
        resolution
        for resolution in korean.equipment_resolutions[bradley.entity_id]
        if resolution.source_equipment.name == "TOW-2 ATGM"
    )
    assert tow_store.disposition is ResolutionDisposition.STORE
    assert tow_store.target_id == "tow2_warhead"
    assert tow_store.attached_to_target_id == "tow2_atgm"

    fallujah = _load("fallujah_phase_line_fran")
    cavalry = _unit_of_type(fallujah, "us_army_infantry_cav")
    assert sum(item.weapon.weapon_id == "javelin_clm" for item in fallujah.unit_weapons[cavalry.entity_id]) == 1
    javelin_store = next(
        resolution
        for resolution in fallujah.equipment_resolutions[cavalry.entity_id]
        if resolution.source_equipment.name == "Javelin Missile Round"
    )
    assert javelin_store.disposition is ResolutionDisposition.STORE
    assert javelin_store.attached_to_target_id == "javelin_clm"


@pytest.mark.parametrize(
    (
        "scenario_path",
        "unit_type",
        "launcher_name",
        "launcher_id",
        "store_name",
        "capacity",
    ),
    (
        (
            DATA_DIR / "scenarios/ins_hanit_2006/scenario.yaml",
            "idf_saar5",
            "Harpoon Quad Launchers (x2)",
            "harpoon_quad_launchers_x2",
            "Harpoon Block 1C ASCM (x8)",
            8,
        ),
        (
            DATA_DIR / "scenarios/khafji/scenario.yaml",
            "iowa_bb",
            "Mk 141 Harpoon Quad Launchers (x4)",
            "mk141_harpoon_launchers_x4",
            "RGM-84 Harpoon Missiles (x16)",
            16,
        ),
    ),
)
def test_harpoon_authored_launcher_and_store_topology_reaches_runtime(
    scenario_path: Path,
    unit_type: str,
    launcher_name: str,
    launcher_id: str,
    store_name: str,
    capacity: int,
) -> None:
    ctx = _load_path(scenario_path)
    unit = _unit_of_type(ctx, unit_type)
    attachment = next(item for item in ctx.unit_weapons[unit.entity_id] if item.source_equipment.name == launcher_name)

    assert attachment.weapon.weapon_id == launcher_id
    assert attachment.weapon.definition.magazine_capacity == capacity
    assert attachment.weapon.ammo_state.rounds_by_type == {
        "rgm84_harpoon": capacity,
    }
    store = next(item for item in ctx.equipment_resolutions[unit.entity_id] if item.source_equipment.name == store_name)
    assert store.disposition is ResolutionDisposition.STORE
    assert store.target_id == "rgm84_harpoon"
    assert store.attached_to_target_id == launcher_id
    assert attachment.weapon.fire("rgm84_harpoon")
    assert attachment.weapon.ammo_state.available("rgm84_harpoon") == capacity - 1


def test_m299_aggregate_preserves_four_launchers_and_sixteen_rails() -> None:
    ctx = _load_path(DATA_DIR / "scenarios/benchmark_brigade/scenario.yaml")
    apache = _unit_of_type(ctx, "ah64d")
    attachments = [
        item for item in ctx.unit_weapons[apache.entity_id] if item.source_equipment.name == "M299 Launchers (x4)"
    ]

    assert len(attachments) == 1
    launcher = attachments[0]
    assert launcher.weapon.weapon_id == "agm114_hellfire"
    assert launcher.weapon.definition.magazine_capacity == 16
    assert launcher.weapon.ammo_state.available("agm114_hellfire") == 16
    assert launcher.weapon.fire("agm114_hellfire")
    assert launcher.weapon.ammo_state.available("agm114_hellfire") == 15


def test_salamis_separates_javelin_and_sword_runtime_weapons() -> None:
    ctx = _load_path(
        DATA_DIR / "eras/ancient_medieval/scenarios/salamis/scenario.yaml",
    )
    trireme = _unit_of_type(ctx, "greek_trireme")
    attachments = {item.source_equipment.name: item for item in ctx.unit_weapons[trireme.entity_id]}

    javelin = attachments["Greek Marine Javelins"]
    sword = attachments["Greek Marine Swords"]
    assert javelin.weapon.weapon_id == "javelin"
    assert sword.weapon.weapon_id == "sword_medieval"
    assert javelin.weapon.weapon_id != sword.weapon.weapon_id
    assert {ammo.ammo_id for ammo in javelin.ammunition} == {"javelin_throw"}
    assert {ammo.ammo_id for ammo in sword.ammunition} == {"sword_strike"}


@pytest.mark.parametrize(
    (
        "scenario_path",
        "unit_type",
        "equipment_name",
        "target_id",
        "modeled_role",
    ),
    (
        (
            DATA_DIR / "scenarios/falklands_naval/scenario.yaml",
            "super_etendard",
            "Agave Maritime Search Radar",
            "airborne_maritime_search_radar",
            SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR,
        ),
        (
            DATA_DIR / "scenarios/taiwan_strait/scenario.yaml",
            "kilo636",
            "MRK-50 Albatros Surface Navigation/Search Radar",
            "surface_navigation_search_radar",
            SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR,
        ),
        (
            DATA_DIR / "scenarios/benchmark_brigade/scenario.yaml",
            "de_shorad",
            "Ku-band Multi-Function RF Sensor (KuRFS)",
            "kurfs_fire_control_radar",
            SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        ),
        (
            DATA_DIR / "eras/ww2/scenarios/midway/scenario.yaml",
            "shokaku_cv",
            "Type 94 High-Angle Optical Director",
            "mk1_eyeball_ww2",
            SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
        ),
    ),
)
def test_role_correct_sensor_resolutions_reach_production_loadouts(
    scenario_path: Path,
    unit_type: str,
    equipment_name: str,
    target_id: str,
    modeled_role: SensorModeledRole,
) -> None:
    ctx = _load_path(scenario_path)
    unit = _unit_of_type(ctx, unit_type)
    resolution = next(
        item for item in ctx.equipment_resolutions[unit.entity_id] if item.source_equipment.name == equipment_name
    )

    assert resolution.disposition is ResolutionDisposition.ATTACHMENT
    assert resolution.target_id == target_id
    assert resolution.modeled_role is modeled_role
    sensor = next(item for item in ctx.unit_sensors[unit.entity_id] if item.equipment is resolution.source_equipment)
    assert sensor.sensor_id == target_id


@pytest.mark.parametrize(
    ("scenario_name", "unit_type", "equipment_name", "sensor_id"),
    (
        (
            "debecka_pass",
            "f14b",
            "AN/AWG-9 Fire Control Radar",
            "awg9_fire_control_radar",
        ),
        (
            "taiwan_strait",
            "j10a",
            "J-10A Pulse-Doppler Fire-Control Radar",
            "j10a_pulse_doppler_fcr",
        ),
        (
            "suwalki_gap",
            "su27s",
            "N001 Myech Radar",
            "n001_myech_radar",
        ),
        (
            "benchmark_battalion",
            "mig29a",
            "N019 Sapfir Radar",
            "n019_sapfir_radar",
        ),
    ),
)
def test_aircraft_fire_control_radars_use_exact_production_definitions(
    scenario_name: str,
    unit_type: str,
    equipment_name: str,
    sensor_id: str,
) -> None:
    ctx = _load(scenario_name)
    unit = _unit_of_type(ctx, unit_type)
    resolution = next(
        item
        for item in ctx.equipment_resolutions[unit.entity_id]
        if item.source_equipment.name == equipment_name
    )
    sensor = next(
        item
        for item in ctx.unit_sensors[unit.entity_id]
        if item.equipment is resolution.source_equipment
    )

    assert resolution.reference_kind is ReferenceKind.EXACT
    assert resolution.target_id == sensor_id
    assert sensor.sensor_id == sensor_id
    assert sensor.definition.target_domains == [Domain.AERIAL.name]


def test_navigation_and_designation_utilities_create_no_live_sensor() -> None:
    ctx = _load("khafji")
    for unit_type, equipment_name in (
        ("f15e", "AN/AAQ-13 LANTIRN Navigation Pod"),
        ("us_marine_recon_team", "AN/PAQ-3 MULE Laser Designator"),
    ):
        unit = _unit_of_type(ctx, unit_type)
        equipment = next(item for item in unit.equipment if item.name == equipment_name)
        assert equipment.category is EquipmentCategory.UTILITY
        assert all(sensor.equipment is not equipment for sensor in ctx.unit_sensors[unit.entity_id])
        assert all(
            resolution.source_equipment is not equipment for resolution in ctx.equipment_resolutions[unit.entity_id]
        )

    b17 = UnitLoader(DATA_DIR / "eras/ww2/units").load_definition(
        DATA_DIR / "eras/ww2/units/air/b17g.yaml",
    )
    aps15 = next(item for item in b17.equipment if item.name == "AN/APS-15 H2X Radar")
    assert aps15.category == "UTILITY"
    assert (
        EQUIPMENT_MAPPING_REGISTRY.get(
            EquipmentCategory.SENSOR,
            aps15.name,
        )
        is None
    )


def test_m4_fire_control_instrument_is_not_a_duplicate_live_sensor(
    tmp_path: Path,
) -> None:
    """Production loading retains the battery's real panoramic telescope."""
    unit_path = DATA_DIR / "eras/ww2/units/artillery/m1_105mm_battery.yaml"
    definition = UnitLoader(DATA_DIR / "eras/ww2/units").load_definition(
        unit_path,
    )
    equipment_categories = {item.name: item.category for item in definition.equipment}
    assert equipment_categories["M1 Panoramic Telescope"] == "SENSOR"
    assert equipment_categories["M4 Fire Control Instrument"] == "UTILITY"
    assert (
        EQUIPMENT_MAPPING_REGISTRY.get(
            EquipmentCategory.SENSOR,
            "M4 Fire Control Instrument",
        )
        is None
    )

    template_path = DATA_DIR / "eras/ww2/scenarios/kursk/scenario.yaml"
    scenario_data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    scenario_data["sides"][0]["units"] = [
        {"unit_type": "m1_105mm_battery", "count": 1},
    ]
    scenario_data["sides"][1]["units"] = [
        {"unit_type": "tiger_i", "count": 1},
    ]
    scenario_path = tmp_path / "m1-battery-production-load.yaml"
    scenario_path.write_text(
        yaml.safe_dump(scenario_data, sort_keys=False),
        encoding="utf-8",
    )

    ctx = _load_path(scenario_path)
    battery = _unit_of_type(ctx, "m1_105mm_battery")
    assert [sensor.equipment.name for sensor in ctx.unit_sensors[battery.entity_id]] == ["M1 Panoramic Telescope"]
    assert [
        resolution.source_equipment.name
        for resolution in ctx.equipment_resolutions[battery.entity_id]
        if resolution.disposition is ResolutionDisposition.ATTACHMENT
        and resolution.source_equipment.category is EquipmentCategory.SENSOR
    ] == ["M1 Panoramic Telescope"]


def test_sa6_mapped_radar_changes_production_detection_outcome() -> None:
    ctx = _load("bekaa_valley_1982")
    sa6 = _unit_of_type(ctx, "sa6_gainful")
    sensors = ctx.unit_sensors[sa6.entity_id]
    assert [sensor.sensor_id for sensor in sensors] == [
        "1s91_straight_flush",
    ]
    sensor = sensors[0]
    aerial_target = _unit_of_type(ctx, "f16c")
    assert sensor.equipment is next(
        equipment for equipment in sa6.equipment if equipment.name == "1S91 Straight Flush Radar"
    )

    target_signature = SignatureProfile(
        profile_id="phase109-air-target",
        unit_type="phase109-air-target",
        radar=RadarSignature(
            rcs_frontal_m2=10.0,
            rcs_side_m2=10.0,
            rcs_rear_m2=10.0,
        ),
    )
    in_range = ctx.detection_engine.check_detection(
        Position(0.0, 0.0, 0.0),
        Position(10_000.0, 0.0, 100.0),
        sensor,
        target_signature,
        target_unit=aerial_target,
        target_id="phase109-air-target",
    )
    out_of_range = ctx.detection_engine.check_detection(
        Position(0.0, 0.0, 0.0),
        Position(76_000.0, 0.0, 100.0),
        sensor,
        target_signature,
        target_unit=aerial_target,
        target_id="phase109-air-target",
    )

    assert in_range.detected is True
    assert in_range.probability == pytest.approx(1.0)
    assert out_of_range.detected is False
    assert out_of_range.probability == 0.0


def test_combined_air_surface_search_mapping_accepts_both_domains() -> None:
    ctx = _load_path(DATA_DIR / "eras/ww2/scenarios/midway/scenario.yaml")
    fletcher = _unit_of_type(ctx, "fletcher_dd")
    sensor = next(
        sensor for sensor in ctx.unit_sensors[fletcher.entity_id] if sensor.equipment.name == "SC-2 Air Search Radar"
    )
    naval_target = _unit_of_type(ctx, "shokaku_cv")
    aerial_target = _unit_of_type(ctx, "a6m_zero")
    signature = SignatureProfile(
        profile_id="phase109-large-radar-target",
        unit_type="phase109-large-radar-target",
        radar=RadarSignature(
            rcs_frontal_m2=1_000_000.0,
            rcs_side_m2=1_000_000.0,
            rcs_rear_m2=1_000_000.0,
        ),
    )

    accepted_naval = ctx.detection_engine.check_detection(
        Position(0.0, 0.0, 0.0),
        Position(1_000.0, 0.0, 100.0),
        sensor,
        signature,
        target_unit=naval_target,
        target_id=naval_target.entity_id,
    )
    accepted = ctx.detection_engine.check_detection(
        Position(0.0, 0.0, 0.0),
        Position(1_000.0, 0.0, 100.0),
        sensor,
        signature,
        target_unit=aerial_target,
        target_id=aerial_target.entity_id,
    )

    assert sensor.definition.target_domains == [
        "AERIAL",
        "NAVAL",
        "AMPHIBIOUS",
    ]
    assert accepted_naval.detected is True
    assert accepted_naval.probability == pytest.approx(1.0)
    assert accepted.detected is True
    assert accepted.probability == pytest.approx(1.0)


def test_removed_ea18g_jammer_proxy_cannot_emit_weapon_engagements() -> None:
    ctx = _load("suwalki_gap", seed=42)
    ea18g_units = [unit for unit in ctx.all_units() if unit.unit_type == "ea18g"]
    assert ea18g_units
    for unit in ea18g_units:
        assert ctx.unit_weapons[unit.entity_id] == ()
        jammer = next(equipment for equipment in unit.equipment if equipment.name == "AN/ALQ-99 Jamming Pods")
        assert jammer.category is EquipmentCategory.UTILITY

    recorder = SimulationRecorder(ctx.event_bus)
    result = SimulationEngine(ctx, recorder=recorder).run()
    engagement_events = recorder.events_of_type("EngagementEvent")
    air_events = recorder.events_of_type("AirEngagementEvent")
    ea18g_ids = {unit.entity_id for unit in ea18g_units}

    assert result.ticks_executed > 0
    assert engagement_events or air_events
    assert not any(event.data.get("attacker_id") in ea18g_ids for event in [*engagement_events, *air_events])


def test_reinforcements_use_the_retained_production_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _load("test_campaign_reinforce")
    builder = ctx.loadout_builder
    assert builder is not None
    builder_type = type(builder)
    original_build = builder_type.build
    build_calls: list[tuple[str, ...]] = []

    def record_build(self, units):
        assert self is builder
        build_calls.append(tuple(unit.entity_id for unit in units))
        return original_build(self, units)

    monkeypatch.setattr(builder_type, "build", record_build)
    initial_ids = {unit.entity_id for unit in ctx.all_units()}
    engine = SimulationEngine(
        ctx,
        config=EngineConfig(resolution_closing_range_mult=0.0),
        campaign_config=CampaignConfig(
            engagement_detection_range_m=1_000.0,
            enable_strategic_movement=False,
            enable_maintenance=False,
            enable_supply_network=False,
        ),
    )

    engine.step()

    arrived = [unit for unit in ctx.all_units() if unit.entity_id not in initial_ids]
    assert ctx.loadout_builder is builder
    assert len(arrived) == 2
    assert build_calls == [tuple(unit.entity_id for unit in arrived)]
    for unit in arrived:
        assert ctx.unit_weapons[unit.entity_id]
        assert ctx.unit_sensors[unit.entity_id]
        assert ctx.equipment_resolutions[unit.entity_id]
        for attachment in ctx.unit_weapons[unit.entity_id]:
            assert attachment.source_equipment is attachment.weapon.equipment
            assert attachment.source_equipment in unit.equipment


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("fingerprint", "loadout-builder fingerprint"),
        ("topology", "loadout resolution topology"),
        ("equipment_id", "equipment identity/order topology"),
        ("equipment_order", "effective authored topology"),
        ("equipment_name", "effective authored topology"),
        ("equipment_category", "effective authored topology"),
        ("unit_type", "outside this builder's reachable envelope"),
        ("domain", "runtime domain"),
    ),
)
def test_checkpoint_rejects_changed_loadout_contract_atomically(
    mutation: str,
    expected: str,
) -> None:
    ctx = _load("test_campaign")
    engine = SimulationEngine(ctx)
    before = engine.checkpoint()
    invalid = copy.deepcopy(engine.get_state())

    if mutation == "fingerprint":
        invalid["context"]["loadout_builder_fingerprint"] = "0" * 64
    elif mutation == "topology":
        unit_id = next(iter(invalid["context"]["loadout_topology"]))
        invalid["context"]["loadout_topology"][unit_id][0]["target_id"] = "phase109-wrong-target"
    else:
        unit = next(
            unit
            for units in invalid["context"]["units_by_side"].values()
            for unit in units
            if len(unit["equipment"]) >= 2
        )
        if mutation == "equipment_id":
            unit["equipment"][0]["equipment_id"] = "phase109-wrong-equipment"
        elif mutation == "equipment_order":
            unit["equipment"][0], unit["equipment"][1] = (
                unit["equipment"][1],
                unit["equipment"][0],
            )
        elif mutation == "equipment_name":
            unit["equipment"][0]["name"] = "Phase 109 wrong equipment"
        elif mutation == "equipment_category":
            unit["equipment"][0]["category"] = int(
                EquipmentCategory.SENSOR,
            )
        elif mutation == "unit_type":
            unit["unit_type"] = "phase109-wrong-unit-type"
        elif mutation == "domain":
            unit["domain"] = 1
        else:  # pragma: no cover - parametrization is exhaustive
            raise AssertionError(mutation)

    with pytest.raises(ValueError, match=expected):
        engine.set_state(invalid)

    assert engine.checkpoint() == before


def test_fresh_restore_preserves_typed_loadout_and_exact_continuation() -> None:
    control_ctx = _load("test_campaign", seed=10_909)
    control = SimulationEngine(control_ctx)
    unit_id, attachment = next(
        (entity_id, attachments[0]) for entity_id, attachments in control_ctx.unit_weapons.items() if attachments
    )
    ammo_id = attachment.ammunition[0].ammo_id
    assert attachment.weapon.fire(ammo_id)
    checkpoint = control.checkpoint()

    resumed_ctx = _load("test_campaign", seed=10_909)
    resumed = SimulationEngine(resumed_ctx)
    resumed.restore(checkpoint)
    resumed_attachment = resumed_ctx.unit_weapons[unit_id][0]
    resumed_unit = next(unit for unit in resumed_ctx.all_units() if unit.entity_id == unit_id)

    assert isinstance(resumed_attachment, WeaponAttachment)
    assert resumed_attachment.weapon.get_state() == attachment.weapon.get_state()
    assert resumed_attachment.source_equipment is resumed_attachment.weapon.equipment
    assert resumed_attachment.source_equipment in resumed_unit.equipment
    for resolution in resumed_ctx.equipment_resolutions[unit_id]:
        assert (
            resolution.source_equipment
            is resumed_unit.equipment[resolution.source_equipment_index]
        )
    assert resumed_ctx.get_state()["loadout_topology"] == control_ctx.get_state()["loadout_topology"]
    assert resumed_ctx.loadout_builder is not control_ctx.loadout_builder
    assert resumed_ctx.loadout_builder.fingerprint() == control_ctx.loadout_builder.fingerprint()

    control.step()
    resumed.step()
    assert resumed.checkpoint() == control.checkpoint()
