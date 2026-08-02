"""Phase 109 per-equipment evidence integrity regressions."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation import equipment_mappings
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_RECORDS,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingError,
    ReferenceKind,
    SensorAttachmentMapping,
)

_REVIEWED_OVERRIDE_NAMES = frozenset(
    {
        "AN/BPS-15 Radar",
        "AN/SPS-48E Radar",
        "AN/SPS-49 Air Search Radar",
        "AN/SPS-67 Surface Search Radar",
        "AN/SPY-1D Radar",
        "AN/SPY-6 AMDR",
        "AN/SQQ-89 Sonar",
        "AN/TAS-4 TOW Thermal Sight",
        "Aerial Observer Binoculars",
        "Barr & Stroud Rangefinder",
        "Blue Fox Radar",
        "CITV Commander's Independent Thermal Viewer",
        "CIV Commander's Independent Viewer",
        "Castor Thermal Sight",
        "Commander's Independent Thermal Viewer",
        "Commander's Thermal Viewer",
        "Dragon Eye EO/IR Camera",
        "EL/M-2218S 3D Air Search Radar",
        "EMES 15 Gunner Sight",
        "El-Op Gill Fire Control",
        "El-Op Knight Mark 4 Fire Control",
        "Elbit MARS Thermal Viewer",
        "Essa Thermal Sight",
        "FuMO 29 Radar",
        "FuMO 30 Radar",
        "GM 2 Reflector Gunsight",
        "GPS 2nd-Gen FLIR Gunner's Sight",
        "IBAS Thermal Sight",
        "Javelin CLU Thermal Sight",
        "K-14 Gyroscopic Gunsight",
        "LAV-25 Day/Night Thermal Sight",
        "M1 Panoramic Telescope",
        "M55 Telescope",
        "MMS Mast-Mounted Sight",
        "Mk 13 Fire Control Radar",
        "Mk 37 GFCS with Mk 25 Fire Control Radar",
        "Mk 38 GFCS with Mk 13 Fire Control Radar",
        "No. 22c Mk 1 Telescopic Sight",
        "No. 7 Dial Sight",
        "OEPS-27 IRST",
        "Panoramic Sight",
        "PERI R17A2 Commander Sight",
        "Rblf 36 Panoramic Sight",
        "Revi 16B Reflector Gunsight",
        "ScanEagle EO/IR Gimbal",
        "TADS/PNVS",
        "TOGS II Thermal Sight",
        "TOW Day/Night Thermal Sight",
        "TSh-16 Telescopic Sight",
        "TZF 12a Monocular Sight",
        "TZF 5f Telescope Sight",
        "TZF 9b Binocular Sight",
        "Type 21 Air Search Radar",
        "Type 965 Air Search Radar",
        "Type 967/968 Radar",
        "ZF 3x8 Telescopic Sight",
        "Zeiss Entfernungsmesser Rangefinder",
    }
)

_SOURCE_EVIDENCE_GROUPS = (
    (
        "Publications-Catalog/Eyes-Of-Artillery",
        {"Aerial Observer Binoculars"},
    ),
    (
        "dreadnoughtproject.org/docs/notes/ADM_186_205.php",
        {"Barr & Stroud Rangefinder"},
    ),
    (
        "technische-meilensteine/verteidigungssysteme.html",
        {"Zeiss Entfernungsmesser Rangefinder"},
    ),
    (
        "collectionswa.net.au/items/95201dcb",
        {"No. 7 Dial Sight"},
    ),
    ("awm.gov.au/collection/C311429", {"Panoramic Sight"}),
    ("GOVPUB-W-75e5a1c84782895a30d30d9df6fb19e2", {"M1 Panoramic Telescope"}),
    ("FM17-12.PDF", {"M55 Telescope"}),
    ("ministryforheritage.gi", {"No. 22c Mk 1 Telescopic Sight"}),
    (
        "TME30-451.PDF",
        {
            "Rblf 36 Panoramic Sight",
            "TZF 12a Monocular Sight",
            "TZF 5f Telescope Sight",
            "TZF 9b Binocular Sight",
            "ZF 3x8 Telescopic Sight",
        },
    ),
    ("p4013coll11/id/2089/download", {"TSh-16 Telescopic Sight"}),
    ("Article/2167957/ansps-48g", {"AN/SPS-48E Radar"}),
    ("Article/2167967/ansps-49v", {"AN/SPS-49 Air Search Radar"}),
    ("mda.mil/system/sensors", {"AN/SPY-1D Radar"}),
    ("Article/2166758/air-and-missile-defense-radar", {"AN/SPY-6 AMDR"}),
    ("cmdfence/writev/761/strategy.pdf", {"Type 965 Air Search Radar"}),
    ("10Sep_Gomez_Torres.pdf", {"EL/M-2218S 3D Air Search Radar"}),
    ("A1F4E055696CF5E105257FF8006D441B", {"Type 967/968 Radar"}),
    ("ORD-ONI-9/index.html", {"Type 21 Air Search Radar"}),
    (
        "NSWC-Port-Hueneme/What-We-Do/In-Service-Engineering/Radars",
        {"AN/BPS-15 Radar", "AN/SPS-67 Surface Search Radar"},
    ),
    ("uboat.net/technical/radar", {"FuMO 29 Radar", "FuMO 30 Radar"}),
    (
        "USN.Characteristics.Naval.Fire.Control.Radar.1954-11-12.pdf",
        {
            "Mk 13 Fire Control Radar",
            "Mk 37 GFCS with Mk 25 Fire Control Radar",
            "Mk 38 GFCS with Mk 13 Fire Control Radar",
        },
    ),
    ("spitfirespares.com/gunsites", {"GM 2 Reflector Gunsight"}),
    ("nasm_A19870343000", {"K-14 Gyroscopic Gunsight"}),
    ("nasm_A20140153000", {"Revi 16B Reflector Gunsight"}),
    (
        "history.redstone.army.mil/miss-tow",
        {"AN/TAS-4 TOW Thermal Sight", "TOW Day/Night Thermal Sight"},
    ),
    (
        "atp3_20x15.pdf",
        {
            "CITV Commander's Independent Thermal Viewer",
            "GPS 2nd-Gen FLIR Gunner's Sight",
        },
    ),
    (
        "three_bfv_mishaps_a_common_theme",
        {"CIV Commander's Independent Viewer", "IBAS Thermal Sight"},
    ),
    (
        "un20F2006May292007.pdf",
        {
            "Commander's Independent Thermal Viewer",
            "Commander's Thermal Viewer",
            "El-Op Gill Fire Control",
            "El-Op Knight Mark 4 Fire Control",
        },
    ),
    ("ArmorJanuaryFebruary1991web.pdf", {"Castor Thermal Sight"}),
    ("KNDS_B_Ansicht_LEOPARD2A8_EN.pdf", {"EMES 15 Gunner Sight"}),
    ("ElbitSystems_20F_20120314-1.pdf", {"Elbit MARS Thermal Viewer"}),
    ("Report_InformNapalm.pdf", {"Essa Thermal Sight"}),
    ("history.redstone.army.mil/miss-javelin", {"Javelin CLU Thermal Sight"}),
    (
        "lar-platoon-performs-vehicle-weapons-maintenance",
        {"LAV-25 Day/Night Thermal Sight"},
    ),
    ("DOC20170814113730PPT.pdf", {"PERI R17A2 Commander Sight"}),
    ("October-desider-online-v3.pdf", {"TOGS II Thermal Sight"}),
    ("museum/AOTM/2022/feb_2022", {"MMS Mast-Mounted Sight"}),
    (
        "corpus_christi_army_depot_welcomes_apaches",
        {"TADS/PNVS"},
    ),
    ("dragon-eye-flies-over-mcagcc", {"Dragon Eye EO/IR Camera"}),
    ("Article/2160330/close-range-uas", {"ScanEagle EO/IR Gimbal"}),
    (
        "r%C3%A9aliste%20avionics%20russes.pdf",
        {"OEPS-27 IRST"},
    ),
    ("hansard.parliament.uk/Commons/1992-10-22", {"Blue Fox Radar"}),
    ("Article/2166784/ansqq-89v", {"AN/SQQ-89 Sonar"}),
)


def _sensor_records_by_name() -> dict[str, SensorAttachmentMapping]:
    return {
        record.equipment_name: record
        for record in EQUIPMENT_MAPPING_RECORDS
        if isinstance(record, SensorAttachmentMapping)
    }


def test_reviewed_equipment_source_overrides_are_complete_and_unique() -> None:
    declarations = (
        equipment_mappings
        ._SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_DECLARATIONS
    )

    assert len(declarations) == 57
    assert len(declarations) == len(
        {equipment_name for equipment_name, _source in declarations},
    )
    assert set(equipment_mappings._SENSOR_FUNCTIONAL_SOURCE_OVERRIDES) == (
        _REVIEWED_OVERRIDE_NAMES
    )


def test_equipment_source_index_rejects_duplicates_before_overwrite() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match=(
            "Duplicate synthetic source override "
            "equipment-source declarations"
        ),
    ):
        equipment_mappings._checked_equipment_source_index(
            "synthetic source override",
            (
                ("Duplicate", "https://example.invalid/first"),
                ("Duplicate", "https://example.invalid/second"),
            ),
        )


def test_equipment_source_index_rejects_non_url_evidence() -> None:
    with pytest.raises(
        EquipmentMappingError,
        match="must contain only traceable URLs",
    ):
        equipment_mappings._checked_equipment_source_index(
            "synthetic source override",
            (("Synthetic sensor", "Phase review notes"),),
        )


def test_reviewed_sources_are_wired_to_live_functional_records() -> None:
    records_by_name = _sensor_records_by_name()

    for equipment_name, source in (
        equipment_mappings
        ._SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_DECLARATIONS
    ):
        record = records_by_name[equipment_name]
        assert record.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE
        assert record.source == source
        assert record.source != equipment_mappings._SENSOR_FUNCTIONAL_SOURCES[
            (record.sensor_id, record.modeled_role)
        ]


def test_reviewed_sources_do_not_inherit_unrelated_family_evidence() -> None:
    records_by_name = _sensor_records_by_name()
    obsolete_fragments = {
        "history.army.mil/portals/143/Images/Publications/catalog/10-10.pdf",
        "nationalmuseum.af.mil/Upcoming/Photos/igphoto/2000467864",
        "operational-characteristics-of-radar-classified-by-tactical-application",
        "peosoldier.army.mil/Equipment/Equipment-Portfolio/"
        "Project-Manager-Soldier-Warrior-Portfolio/Thermal-Weapon-Sight",
        "af.mil/About-Us/Fact-Sheets/Display/Article/104582/lantirn",
        "armysbir.army.mil/topics/large-format-color-low-light-level",
        "navsea.navy.mil/Media/News/Article-View/Article/2294777",
        "rtx.com/raytheon/what-we-do/air/mts",
        "navair.navy.mil/news/US-Navy-FA-18-fleet",
        "museeairespace.fr/aller-plus-haut/collections/"
        "dassault-super-etendard-modernise",
        "publicaciones.defensa.gob.es/media/downloadable/files/",
        "nepa.navy.mil/SOTS/At-Sea/US-Navy-Sonar",
    }

    for equipment_name in _REVIEWED_OVERRIDE_NAMES:
        source = records_by_name[equipment_name].source
        assert source is not None
        assert all(fragment not in source for fragment in obsolete_fragments)


def test_reviewed_sources_match_their_equipment_identity_groups() -> None:
    records_by_name = _sensor_records_by_name()
    covered_names: set[str] = set()

    for source_fragment, equipment_names in _SOURCE_EVIDENCE_GROUPS:
        assert not (covered_names & equipment_names)
        covered_names.update(equipment_names)
        for equipment_name in equipment_names:
            source = records_by_name[equipment_name].source
            assert source is not None
            assert source_fragment in source

    assert covered_names == _REVIEWED_OVERRIDE_NAMES


def test_ftp_217_remains_on_the_systems_it_actually_documents() -> None:
    records_by_name = _sensor_records_by_name()
    ftp_217_fragment = (
        "operational-characteristics-of-radar-classified-by-"
        "tactical-application"
    )

    for equipment_name in (
        "SC-2 Air Search Radar",
        "SK Air Search Radar",
        "SK-2 Air Search Radar",
        "SG Surface Search Radar",
        "Mk 37 GFCS with Mk 4 Fire Control Radar",
        "Mk 37 GFCS with Mk 4 Fire Control Radar (x2)",
    ):
        source = records_by_name[equipment_name].source
        assert source is not None
        assert ftp_217_fragment in source
