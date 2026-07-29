"""Authoritative typed equipment-name registry for production loadouts.

Declarations remain an ordered tuple of immutable records.  Group helpers
reduce repetition without constructing an intermediate dictionary, so the
registry still observes and rejects every duplicate declaration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar

from stochastic_warfare.combat.ammunition import (
    AmmoType,
    GuidanceType,
    WeaponCategory,
)
from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.simulation.loadouts import (
    EquipmentMappingError,
    EquipmentMappingRecord,
    EquipmentMappingRegistry,
    ReferenceKind,
    SensorAttachmentMapping,
    SensorModeledRole,
    SensorNonRuntimeMapping,
    WeaponAttachmentMapping,
    WeaponModeledRole,
    WeaponNonRuntimeMapping,
    WeaponStoreMapping,
    equipment_name_declares_system_count,
    required_domains_for_sensor_role,
    required_domains_for_weapon_role,
)

_PHASE_SOURCE = "Phase 109 military-data review in docs/specs/equipment-mapping.md"
_FunctionalRoleT = TypeVar(
    "_FunctionalRoleT",
    WeaponModeledRole,
    SensorModeledRole,
)


def _checked_name_set(
    label: str,
    declarations: tuple[str, ...],
) -> frozenset[str]:
    """Freeze ordered identity declarations without hiding duplicate names."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in declarations:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise EquipmentMappingError(
            f"Duplicate {label} identity declarations: {duplicates!r}",
        )
    return frozenset(declarations)


def _require_disjoint_name_sets(
    label: str,
    exact: frozenset[str],
    variant: frozenset[str],
) -> None:
    overlap = sorted(exact & variant)
    if overlap:
        raise EquipmentMappingError(
            f"{label.capitalize()} names cannot be both exact and variant: {overlap!r}",
        )


_FUNCTIONAL_SOURCE_DECLARATION_KEYS: dict[
    str,
    list[tuple[str, WeaponModeledRole | SensorModeledRole]],
] = {}


def _checked_functional_source_key(
    label: str,
    target_id: str,
    modeled_role: _FunctionalRoleT,
) -> tuple[str, _FunctionalRoleT]:
    """Observe a source declaration before dictionary insertion can overwrite it."""
    key = (target_id, modeled_role)
    declarations = _FUNCTIONAL_SOURCE_DECLARATION_KEYS.setdefault(label, [])
    if key in declarations:
        raise EquipmentMappingError(
            f"Duplicate {label} functional-source declaration: {target_id!r}/{modeled_role.value!r}",
        )
    declarations.append(key)
    return key


def _checked_equipment_source_index(
    label: str,
    declarations: tuple[tuple[str, str], ...],
) -> Mapping[str, str]:
    """Build an equipment-specific source index without last-write-wins loss."""
    sources: dict[str, str] = {}
    duplicates: list[str] = []
    for equipment_name, source in declarations:
        if (
            not equipment_name
            or equipment_name.strip() != equipment_name
        ):
            raise EquipmentMappingError(
                f"{label.capitalize()} equipment_name must be non-empty and trimmed",
            )
        source_urls = source.split("; ")
        if not source_urls or any(
            not url.startswith(("http://", "https://"))
            for url in source_urls
        ):
            raise EquipmentMappingError(
                f"{label.capitalize()} source for {equipment_name!r} "
                "must contain only traceable URLs",
            )
        if equipment_name in sources:
            if equipment_name not in duplicates:
                duplicates.append(equipment_name)
            continue
        sources[equipment_name] = source
    if duplicates:
        raise EquipmentMappingError(
            f"Duplicate {label} equipment-source declarations: {duplicates!r}",
        )
    return MappingProxyType(sources)


# Exact means the equipment name denotes the cataloged system itself.  Every
# other live reference is deliberately labeled a bounded functional analogue.
_EXACT_WEAPON_EQUIPMENT_DECLARATIONS = (
    "100kW Solid-State Laser",
    "105mm M102 Howitzer (direct-fire mount)",
    "12-Pounder Cannon",
    "16 inch/50 Mk 7 Gun",
    "2A42 30mm Autocannon",
    "2A46M 125mm Smoothbore",
    "2K12 Launcher",
    "2S1 Gvozdika 122mm SP",
    "2S3 Akatsiya 152mm SP",
    "2x S-68 57mm Autocannon",
    "30mm ADEN",
    "3M80 Moskit Launcher",
    "50kW Fiber Laser",
    "533mm Torpedo Tubes x6",
    "6-Pounder Cannon",
    "73mm 2A28 Grom",
    "85mm ZIS-S-53 Gun",
    "88mm KwK 36 L/56 Gun",
    "8.8cm SK L/45 FlaK (x6)",
    "9P135M ATGM Launcher",
    "9M114 Shturm-V Launcher",
    "9K32 Strela-2 MANPADS",
    "AGM-114 Hellfire Launcher",
    "AGM-65 Maverick",
    "AIM-120 AMRAAM",
    "AIM-7M Sparrow",
    "AIM-9L Sidewinder",
    "AIM-9X Sidewinder",
    "AK-47",
    "AK-130 130mm Twin Gun",
    "AM.39 Exocet",
    "AT-4 LAW",
    "Arquebuses",
    "Baker Rifle",
    "Ballistae (x2)",
    "Barak-1 VLS SAM",
    "Barrett M82A1 .50 Rifle",
    "Bayonet",
    "BM-21 Grad 122mm MRL",
    "BRU-36/A Bomb Ejector Rack",
    "Brown Bess Musket",
    "C-802 Noor Launcher",
    "Carl Gustaf M3",
    "Cavalry Saber",
    "Charleville 1777 Musket",
    "Composite Bow",
    "Crossbows",
    "D-10T 100mm Rifled Gun",
    "D-30 122mm Howitzer",
    "FGM-148 Javelin CLU",
    "F1 105mm Rifled Gun",
    "GAU-12 Equalizer 25mm",
    "GAU-8/A Avenger 30mm",
    "Generic Bomb Rack",
    "Gewehr 98 Rifle",
    "Gladii",
    "Gladius",
    "Greek Fire Siphon",
    "HELIOS 60kW Laser",
    "Harpoon Quad Launchers (x2)",
    "Iraqi 82mm 2B14 Mortar",
    "Karabiner 98k Rifle",
    "L7 105mm Rifled Gun",
    "L30A1 120mm Rifled Gun",
    "Lebel Mle 1886 M93 Rifle",
    "Lee-Enfield SMLE Mk III Rifle",
    "Lepanto Galley Bow Gun Battery",
    "Longbow",
    "M121 120mm Mortar",
    "MAU-40/A Bomb Ejector Rack",
    "M16A4 Rifle",
    "M1903 Springfield Rifle",
    "M1918 BAR",
    "M1919A4 .30 Cal Coaxial",
    "M197 20mm Rotary Cannon",
    "M230 Chain Gun 30mm",
    "M249 SAW",
    "M203 40mm Grenade Launcher",
    "M240B GPMG",
    "M242 25mm Chain Gun",
    "M256 120mm Smoothbore",
    "M284 155mm Howitzer",
    "M2HB .50 Cal",
    "NSVT 12.7mm HMG",
    "M4A1 Carbine",
    "M40A1 Sniper Rifle",
    "M61A1 Vulcan 20mm",
    "PKM GPMG",
    "PKT 7.62mm Coaxial",
    "PKT 7.62mm MG",
    "PKT 7.62mm Machine Gun",
    "SGMT 7.62mm Coaxial",
    "MG 08 Machine Gun (x6)",
    "MG 34 Coaxial",
    "MG 34 Hull Mount",
    "MG 151/20 20mm Cannon",
    "MG 42 Light Machine Gun",
    "Mills Bomb No. 5 Grenade",
    "M1 Garand Rifle",
    "Mk 12 20mm Cannon",
    "Mk 15 Phalanx CIWS",
    "Mk 141 Harpoon Quad Launchers (x4)",
    "Mk 153 SMAW",
    "Mk 41 VLS",
    "Mk 45 5-inch Gun",
    "Mosin-Nagant M91/30 Rifle",
    "MP 18 Submachine Gun",
    "MATADOR 90mm Anti-Structure Munition",
    "Oto Melara 76mm/62 Super Rapid",
    "Pila",
    "Pike",
    "Pilum",
    "PPSh-41 Submachine Gun",
    "QF 3-inch AA Gun (x2)",
    "QF 6-pounder 6 cwt Hotchkiss Gun",
    "R-73 AA-11 Archer",
    "R-77 AA-12 Adder",
    "Rh-120 L/55 120mm Smoothbore",
    "RPG-29",
    "RPG-7",
    "RGD-33 Fragmentation Grenade",
    "57mm Maxim-Nordenfelt Gun",
    "Sarissa",
    "Sea Dart SAM",
    "20mm M693 Coaxial",
    "21-inch Torpedo Tubes (x2x2)",
    "21-inch Torpedo Tubes (x4)",
    "30.5cm SK L/50 Gun (5x2 turrets)",
    "4.5 inch Mk 8 Naval Gun",
    "45cm Torpedo Tubes (x4)",
    "50cm Torpedo Tubes (x5)",
    "7.5cm PaK 40 L/46",
    "75mm KwK 40 L/48 Gun",
    "18-pdr Long Guns (upper deck, x30)",
    "18-pdr Long Guns (upper deck, x34)",
    "Carronades 24-pdr (x2)",
    "DEFA 553 30mm Cannon",
    "GSh-23 23mm Cannon",
    "GSh-30-1 30mm Cannon",
    "KPVT 14.5mm HMG",
    "YakB-12.7 Gatling Gun",
    "9-pdr Guns (quarterdeck/forecastle, x16)",
    "9-pdr Long Guns (x18)",
    "SPG-9 73mm Recoilless Rifle",
    "Spathion Sword",
    "SVD Dragunov",
    "Stielhandgranate 24",
    "U-5TS 115mm Smoothbore",
    "10.5cm SK C/32 Deck Gun",
    "2-pdr Pom-Pom",
    "2cm FlaK C/30 AA Gun",
    "3.7cm FlaK M42 AA Gun",
    "75mm KwK 42 L/70 Gun",
    "8.8cm SK C/35 Deck Gun",
    "8.8cm SK L/30 Deck Gun",
    "BL 13.5-inch Mk V Gun (5x2 turrets)",
    "BL 4-inch Mk IX Gun",
    "BL 6-inch Mk VII Gun (x12)",
    "Bofors 40mm Quad Mount (x20)",
    "Bofors 40mm Quad Mount (x8)",
    "Bofors 40mm Twin Mount (x2)",
    "Bofors 40mm Twin Mount (x5)",
    "Browning .303 Machine Gun (x4)",
    "DP-28 Light Machine Gun",
    "DT 7.62mm Coaxial MG",
    "Hedgehog ASW Mortar",
    "Hispano Mk II 20mm Cannon (x2)",
    "M1918A2 BAR",
    "MG 131 13mm Machine Gun (x2)",
    "Oerlikon 20mm (x46)",
    "Oerlikon 20mm (x49)",
    "Oerlikon 20mm (x6)",
    "Oerlikon 20mm (x7)",
    "QF 4-inch Mk III Gun (x16)",
    "QF 4-inch Mk IV Gun (x3)",
    "QF 6-Pounder (57mm) L/50",
    "Type 89 12.7cm AA Gun (8x2)",
    "Type 96 25mm Triple Mount (x12)",
    "Type 97 7.7mm MG (x2)",
    "Chauchat M1915 CSRG Light Machine Gun",
    "15cm SK L/45 Gun (x14)",
    "16-inch/50 Mk 7 Gun (3x3 turrets)",
    "18-inch Torpedo Tubes (x5)",
    "24-pdr Long Guns (middle deck, x34)",
    "24-pdr Long Guns (x26)",
    "32-pdr Long Guns (lower deck, x28)",
    "32-pdr Long Guns (lower deck, x32)",
    "40mm Bofors L/60 Automatic Gun",
    "5-inch/38 Mk 12 Gun (10x2 turrets)",
    "5-inch/38 Mk 12 Gun (4x2 turrets)",
    "5-inch/38 Mk 12 Gun (x5)",
    "5 inch/38 Mk 12 Gun",
    "53.3cm Torpedo Tubes (4 bow, 1 stern)",
    "53.3cm Torpedo Tubes (4 bow, 2 stern)",
    "7.7cm FK 96 n.A. Field Gun (x4)",
    "75mm M3 Gun",
    "AT-3 Sagger ATGM",
    "BGM-71 TOW-2 Launcher",
    "BL 12-inch Mk X Gun (4x2 turrets)",
    "Carronades 32-pdr (x6)",
    "Charleville Musket (personal arms)",
    "Congreve Rocket Launcher Tripod (x4)",
    "Lance (Napoleonic)",
    "Lewis Gun Sponson Mount",
    "LMG 08/15 Spandau MG (x2)",
    "M2 .50 Cal",
    "M2 Browning .50 Cal (x13)",
    "M2 Browning .50 Cal (x6)",
    "M240 7.62mm",
    "M240 7.62mm Coaxial",
    "M240 7.62mm Loader",
    "Mk 15 Torpedo Tubes (2x5)",
    "Mk 48 Torpedo Tubes",
    "QF 18-Pounder Field Gun (x4)",
    "9K52 Luna-M FROG-7 TEL",
    "Type 99 Model 2 20mm Cannon (x2)",
    "Vickers .303 Synchronized MG (x2)",
    "Viking Battle Axes",
)
_EXACT_WEAPON_EQUIPMENT = _checked_name_set(
    "exact weapon",
    _EXACT_WEAPON_EQUIPMENT_DECLARATIONS,
)

_VARIANT_WEAPON_EQUIPMENT_DECLARATIONS = (
    "5P85 TEL",
    "2A46M-5 125mm Smoothbore",
    "9A310 TELAR",
    "AK-74",
    "AKM",
    "AKMS",
    "IMI Negev 5.56mm LMG",
    "Kontarion Spear",
    "M16A2 Rifle",
    "M240C 7.62mm Coaxial",
    "M299 Launchers (x4)",
    "M4A1 SOPMOD",
    "M901 Launching Station",
    "M901 TOW-2 Launcher",
    "M2HB .50 Cal AA Mount",
    "RAM Launcher",
    "Sea Wolf SAM",
    "SMLE Cavalry Carbine",
    "Suppressed M4A1 Rifle",
    "9P163-2 Kornet Launcher",
)
_VARIANT_WEAPON_EQUIPMENT = _checked_name_set(
    "variant weapon",
    _VARIANT_WEAPON_EQUIPMENT_DECLARATIONS,
)

_EXACT_SENSOR_EQUIPMENT_DECLARATIONS = (
    "1S91 Straight Flush Radar",
    "1PN22M1 Gunner Sight",
    "AN/APG-68 Radar",
    "AN/APG-78 Longbow Radar",
    "AN/APQ-94 Radar",
    "AN/PVS-14 NVG",
    "AN/VVS-2 Commander Viewer",
    "AN/AWG-9 Fire Control Radar",
    "J-10A Pulse-Doppler Fire-Control Radar",
    "Ku-band Multi-Function RF Sensor (KuRFS)",
    "Mk 1 Eyeball",
    "Naked Eye Observation",
    "N001 Myech Radar",
    "N019 Sapfir Radar",
    "Starlight Scope",
    "TPN-3-49 Night Sight",
    "Type 271 Surface Search Radar",
)
_EXACT_SENSOR_EQUIPMENT = _checked_name_set(
    "exact sensor",
    _EXACT_SENSOR_EQUIPMENT_DECLARATIONS,
)

_VARIANT_SENSOR_EQUIPMENT_DECLARATIONS = ("AN/PVS-31 NVG",)
_VARIANT_SENSOR_EQUIPMENT = _checked_name_set(
    "variant sensor",
    _VARIANT_SENSOR_EQUIPMENT_DECLARATIONS,
)

_require_disjoint_name_sets(
    "weapon",
    _EXACT_WEAPON_EQUIPMENT,
    _VARIANT_WEAPON_EQUIPMENT,
)
_require_disjoint_name_sets(
    "sensor",
    _EXACT_SENSOR_EQUIPMENT,
    _VARIANT_SENSOR_EQUIPMENT,
)

# Functional analogues are retained only where a traceable system/role source
# supports the bounded runtime behavior.  These sources do not assert identity
# or equal physical performance.
_WEAPON_FUNCTIONAL_SOURCES: Mapping[
    tuple[str, WeaponModeledRole],
    str,
] = MappingProxyType(
    {
        _checked_functional_source_key(
            "weapon",
            "bomb_rack_generic",
            WeaponModeledRole.BOMB_DELIVERY,
        ): (
            "https://www.afgsc.af.mil/News/Article-Display/Article/629758/"
            "upgrade-gives-b-52-more-teeth/; "
            "https://www.8af.af.mil/News/Article-Display/Article/1258892/"
            "b-52-testers-complete-leaflet-bomb-drops/"
        ),
        _checked_functional_source_key(
            "weapon",
            "brown_bess",
            WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        ): (
            "https://collection.nam.ac.uk/detail.php?"
            "acc=1974-03-130-1&page=1&q=searchType%3Dsimple%26"
            "resultsDisplay%3Dlist%26simpleText%3DBritish%2BStandard; "
            "https://www.oeaw.ac.at/fileadmin/Institute/INZ/img/forschung/"
            "Habsburgermonarchie/Napoleon-Tagung_Deutsch_Wagram.pdf; "
            "https://catalog.shm.ru/entity/OBJECT/1657180; "
            "https://collection.nam.ac.uk/detail.php?"
            "acc=1980-12-71--1&page=4&pos=13"
        ),
        _checked_functional_source_key(
            "weapon",
            "depth_charge_mk7",
            WeaponModeledRole.ANTI_SUBMARINE,
        ): (
            "https://www.history.navy.mil/content/history/museums/nmusn/"
            "explore/photography/wwii/wwii-atlantic/battle-of-the-atlantic/"
            "anti-submarine-warfare/k-gun.html/1000"
        ),
        _checked_functional_source_key(
            "weapon",
            "lance_medieval",
            WeaponModeledRole.MELEE,
        ): ("https://www.metmuseum.org/essays/arms-and-armor-common-misconceptions-and-frequently-asked-questions"),
        _checked_functional_source_key(
            "weapon",
            "javelin",
            WeaponModeledRole.ANCIENT_PROJECTILE,
        ): "https://www.britishmuseum.org/collection/object/G_1935-0823-16",
        _checked_functional_source_key(
            "weapon",
            "m224_60mm",
            WeaponModeledRole.MORTAR_FIRE,
        ): "https://www.elbitsystems.com/media/60mm-Mortars-3.pdf",
        _checked_functional_source_key(
            "weapon",
            "m240_762mm",
            WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        ): (
            "https://www.gov.uk/government/uploads/system/uploads/"
            "attachment_data/file/727954/"
            "20180823-Challenger_SI_Castlemartin_Redacted_RT.pdf; "
            "https://www.bundeswehr.de/de/ausruestung-technik-bundeswehr/"
            "ausruestung-bewaffnung/mg3; "
            "https://cpeground.army.mil/Equipment/Equipment-Portfolio/"
            "PM-MBCT-Lethality-Portfolio/M240B-L-H-Medium-Machine-Gun/"
        ),
        _checked_functional_source_key(
            "weapon",
            "m240_762mm",
            WeaponModeledRole.AIR_DEFENSE_GUN,
        ): (
            "https://rdl.train.army.mil/catalog-ws/view/100.ATSC/"
            "2A925153-3068-4A11-8435-F0B7522EFCD7-1470229928173/"
            "atp3_01x8.pdf"
        ),
        _checked_functional_source_key(
            "weapon",
            "m240_762mm",
            WeaponModeledRole.AIRCRAFT_GUN,
        ): (
            "https://www.nationalmuseum.af.mil/Visit/Museum-Exhibits/"
            "Fact-Sheets/Display/Article/196062/"
            "north-american-rockwell-ov-10a-bronco/; "
            "https://cpeground.army.mil/Equipment/Equipment-Portfolio/"
            "PM-MBCT-Lethality-Portfolio/M240B-L-H-Medium-Machine-Gun/"
        ),
        _checked_functional_source_key(
            "weapon",
            "m2hb_50cal",
            WeaponModeledRole.AIRCRAFT_GUN,
        ): ("https://www.army.mil/article/19271/6_6_cavalry_aircrews_field_new_kiowa_warrior_weapons_system"),
        _checked_functional_source_key(
            "weapon",
            "m4_556mm",
            WeaponModeledRole.ASSAULT_RIFLE,
        ): (
            "https://iwi.net/wp-content/uploads/2021/03/"
            "IWI_TAVOR_brochure_2021_EN.pdf; "
            "https://www.peosoldier.army.mil/Equipment/Equipment-Portfolio/"
            "Project-Manager-Soldier-Lethality-Portfolio/M4-M4A1-Carbine/"
        ),
        _checked_functional_source_key(
            "weapon",
            "mills_bomb",
            WeaponModeledRole.HAND_GRENADE,
        ): (
            "https://www.awm.gov.au/collection/C222109; "
            "https://www.iwm.org.uk/history/"
            "voices-of-the-first-world-war-weapons-of-war"
        ),
        _checked_functional_source_key(
            "weapon",
            "rgd33",
            WeaponModeledRole.HAND_GRENADE,
        ): (
            "https://www.saw.usace.army.mil/Portals/59/docs/fuds/"
            "Camp%20Butner/Archives%20Search%20Report%20September%201993.pdf"
        ),
        _checked_functional_source_key(
            "weapon",
            "spear",
            WeaponModeledRole.MELEE,
        ): "https://www.britishmuseum.org/collection/object/E_Af1868-1230-16",
        _checked_functional_source_key(
            "weapon",
            "sword_medieval",
            WeaponModeledRole.MELEE,
        ): (
            "https://collection.nam.ac.uk/detail.php?acc=1964-08-34-5; "
            "https://resources.metmuseum.org/resources/metpublications/pdf/"
            "Islamic_Arms_and_Armor_in_The_Metropolitan_Museum_of_Art.pdf"
        ),
    }
)
_WEAPON_FUNCTIONAL_SOURCE_DECLARATIONS = tuple(
    _FUNCTIONAL_SOURCE_DECLARATION_KEYS["weapon"],
)

_SENSOR_FUNCTIONAL_SOURCES: Mapping[
    tuple[str, SensorModeledRole],
    str,
] = MappingProxyType(
    {
        _checked_functional_source_key(
            "sensor",
            "aaq33_sniper",
            SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        ): ("https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104571/litening-advance-targeting/"),
        _checked_functional_source_key(
            "sensor",
            "active_sonar",
            SensorModeledRole.ACTIVE_SONAR,
        ): "https://www.nepa.navy.mil/SOTS/At-Sea/US-Navy-Sonar/",
        _checked_functional_source_key(
            "sensor",
            "air_search_radar",
            SensorModeledRole.AIR_SEARCH_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "air_search_radar",
            SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "airborne_low_light_tv",
            SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION,
        ): ("https://www.nationalmuseum.af.mil/Visit/Museum-Exhibits/Fact-Sheets/Display/Article/579665/"),
        _checked_functional_source_key(
            "sensor",
            "airborne_maritime_search_radar",
            SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR,
        ): (
            "https://www.museeairespace.fr/aller-plus-haut/collections/"
            "dassault-super-etendard-modernise-sem-64/; "
            "https://publicaciones.defensa.gob.es/media/downloadable/files/"
            "links/r/g/rgm_266_2_marzo_2014.pdf"
        ),
        _checked_functional_source_key(
            "sensor",
            "apg68_radar",
            SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        ): (
            "https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104499/"
            "f-15e-strike-eagle/; "
            "https://www.navair.navy.mil/node/13791; "
            "https://www.navair.navy.mil/node/5066"
        ),
        _checked_functional_source_key(
            "sensor",
            "binoculars_ww1",
            SensorModeledRole.VISUAL_OBSERVATION,
        ): (
            "https://history.army.mil/Portals/143/Images/Publications/"
            "Publication%20By%20Title%20Images/U%20Pdf/"
            "us-army-ww-1917-1919-14.pdf"
        ),
        _checked_functional_source_key(
            "sensor",
            "esm_suite",
            SensorModeledRole.ELECTRONIC_SUPPORT,
        ): (
            "https://www.navsea.navy.mil/Home/Warfare-Centers/NSWC-Crane/"
            "What-We-Do/Technical-Capabilities/Electronic-Warfare-Systems/"
        ),
        _checked_functional_source_key(
            "sensor",
            "ground_air_defense_fire_control_radar",
            SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        ): (
            "https://odin.t2com.army.mil/WEG/Asset/"
            "c7f1be46a22bc9b9aeb8179bbb71aa94; "
            "https://www.govinfo.gov/content/pkg/"
            "GOVPUB-D101-PURL-LPS25699/pdf/"
            "GOVPUB-D101-PURL-LPS25699.pdf"
        ),
        _checked_functional_source_key(
            "sensor",
            "ground_search_radar",
            SensorModeledRole.COASTAL_SURVEILLANCE_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "ground_search_radar",
            SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "ground_search_radar",
            SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "hydrophone_ww1",
            SensorModeledRole.PASSIVE_SONAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/h/"
            "history-bureau-engineering-during-wwi.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "hydrophone_ww2",
            SensorModeledRole.PASSIVE_SONAR,
        ): "https://www.nepa.navy.mil/SOTS/At-Sea/US-Navy-Sonar/",
        _checked_functional_source_key(
            "sensor",
            "low_altitude_air_search_radar",
            SensorModeledRole.AIR_SEARCH_RADAR,
        ): ("https://staging.odin.t2com.army.mil/WEG/Asset/8a47af4e88bf5bf8c7cbf0645a581465"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
        ): (
            "https://www.marines.mil/Portals/1/Publications/"
            "MCWP%203-16.6%20W%20Erratum%20%20Supporting%20Arms%20"
            "Observer%2C%20Spotter%20and%20Controller_2.pdf"
        ),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
        ): ("https://history.redstone.army.mil/miss-tow.html"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
        ): ("https://history.army.mil/Publications/Publications-Catalog/Eyes-Of-Artillery/"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
        ): (
            "https://rdl.train.army.mil/catalog-ws/view/100.ATSC/"
            "2A925153-3068-4A11-8435-F0B7522EFCD7-1470229928173/"
            "atp3_01x8.pdf"
        ),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.GROUND_VISUAL_SIGHT,
        ): "https://www.army.mil/article/4032/see_acquire_and_target",
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball",
            SensorModeledRole.VISUAL_OBSERVATION,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/l/"
            "lookout-manual-1943.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball_ww2",
            SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
        ): ("https://airandspace.si.edu/collection-objects/bombsight-norden-mk-xi-prototype-1923/nasm_A19770939000"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball_ww2",
            SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
        ): ("https://www.nationalmuseum.af.mil/Upcoming/Photos/igphoto/2000467864/"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball_ww2",
            SensorModeledRole.GROUND_VISUAL_SIGHT,
        ): ("https://history.army.mil/portals/143/Images/Publications/catalog/10-10.pdf"),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball_ww2",
            SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/a/"
            "anti-suicide-action-summary.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "mk1_eyeball_ww2",
            SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/m/"
            "manual-of-commands-and-orders-1945.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "naval_gun_fire_control_radar",
            SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/u/"
            "operational-characteristics-of-radar-classified-by-"
            "tactical-application.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "ship_lookout",
            SensorModeledRole.NAVAL_LOOKOUT,
        ): (
            "https://www.history.navy.mil/research/library/"
            "online-reading-room/title-list-alphabetically/l/"
            "lookout-manual-1943.html"
        ),
        _checked_functional_source_key(
            "sensor",
            "surface_navigation_search_radar",
            SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR,
        ): ("https://cgsc.contentdm.oclc.org/digital/api/collection/p4013coll11/id/2091/download"),
        _checked_functional_source_key(
            "sensor",
            "telescope_napoleonic",
            SensorModeledRole.NAVAL_LOOKOUT,
        ): ("https://www.rmg.co.uk/collections/objects/rmgc-object-43698"),
        _checked_functional_source_key(
            "sensor",
            "thermal_sight",
            SensorModeledRole.AIRBORNE_AIR_THERMAL_SEARCH,
        ): (
            "https://www.navair.navy.mil/news/"
            "US-Navy-FA-18-fleet-gets-enhanced-target-tracking-IRST-IOC/"
            "Tue-02042025-0944"
        ),
        _checked_functional_source_key(
            "sensor",
            "thermal_sight",
            SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        ): (
            "https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104582/"
            "lantirn/; "
            "https://armysbir.army.mil/topics/"
            "large-format-color-low-light-level-lll-focal-plane-arrays-fpas/"
        ),
        _checked_functional_source_key(
            "sensor",
            "thermal_sight",
            SensorModeledRole.AIRBORNE_SURFACE_THERMAL_SEARCH,
        ): (
            "https://www.navsea.navy.mil/Media/News/Article-View/Article/2294777/"
            "nswc-crane-airborne-electronic-attack-team-recognized-for-developing-"
            "robust-13m/; "
            "https://www.rtx.com/raytheon/what-we-do/air/mts"
        ),
        _checked_functional_source_key(
            "sensor",
            "thermal_sight",
            SensorModeledRole.GROUND_THERMAL_TARGETING,
        ): (
            "https://www.peosoldier.army.mil/Equipment/"
            "Equipment-Portfolio/Project-Manager-Soldier-Warrior-Portfolio/"
            "Thermal-Weapon-Sight/"
        ),
    }
)
_SENSOR_FUNCTIONAL_SOURCE_DECLARATIONS = tuple(
    _FUNCTIONAL_SOURCE_DECLARATION_KEYS["sensor"],
)

# A family source establishes that a bounded target/role pairing is defensible.
# Where one family serves materially different authored systems, these
# equipment-specific sources establish the identity and actual military role
# of the source item. They do not change or substantiate the modeled cap.
_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_DECLARATIONS: tuple[
    tuple[str, str],
    ...,
] = (
    # WWII ground sights.
    (
        "M1 Panoramic Telescope",
        "https://www.govinfo.gov/app/details/GOVPUB-W-75e5a1c84782895a30d30d9df6fb19e2",
    ),
    (
        "M55 Telescope",
        "https://www.ibiblio.org/hyperwar/USA/ref/FM/PDFs/FM17-12.PDF",
    ),
    (
        "No. 22c Mk 1 Telescopic Sight",
        "https://www.ministryforheritage.gi/heritage-and-antiquities/"
        "6-pdr-bl-7-cwt-mkii-at-macfarlanes-gallery-1314",
    ),
    (
        "Rblf 36 Panoramic Sight",
        "https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TME30-451.PDF",
    ),
    (
        "TSh-16 Telescopic Sight",
        "https://cgsc.contentdm.oclc.org/digital/api/collection/"
        "p4013coll11/id/2089/download",
    ),
    (
        "TZF 12a Monocular Sight",
        "https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TME30-451.PDF",
    ),
    (
        "TZF 5f Telescope Sight",
        "https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TME30-451.PDF",
    ),
    (
        "TZF 9b Binocular Sight",
        "https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TME30-451.PDF",
    ),
    (
        "ZF 3x8 Telescopic Sight",
        "https://www.ibiblio.org/hyperwar/USA/ref/TM/pdfs/TME30-451.PDF",
    ),
    # Shipboard radar families.
    (
        "AN/SPS-48E Radar",
        "https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/"
        "Article/2167957/ansps-48g/; "
        "https://www.secnav.navy.mil/fmc/fmb/Documents/04pres/proc/SCN_BOOK.pdf",
    ),
    (
        "AN/SPS-49 Air Search Radar",
        "https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/"
        "Article/2167967/ansps-49v-radar-set/",
    ),
    (
        "AN/SPY-1D Radar",
        "https://www.mda.mil/system/sensors.html",
    ),
    (
        "AN/SPY-6 AMDR",
        "https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/"
        "Article/2166758/air-and-missile-defense-radar-amdr/",
    ),
    (
        "Type 965 Air Search Radar",
        "https://publications.parliament.uk/pa/cm201011/cmselect/"
        "cmdfence/writev/761/strategy.pdf",
    ),
    (
        "EL/M-2218S 3D Air Search Radar",
        "https://calhoun.nps.edu/bitstream/handle/10945/5158/"
        "10Sep_Gomez_Torres.pdf?sequence=1",
    ),
    (
        "Type 967/968 Radar",
        "https://www2.congreso.gob.pe/sicr/RelatAgenda/"
        "proapro20112016.nsf/ProyectosAprobadosPortal/"
        "A1F4E055696CF5E105257FF8006D441B",
    ),
    (
        "Type 21 Air Search Radar",
        "https://www.ibiblio.org/hyperwar/USN/ref/ORD-ONI-9/index.html",
    ),
    (
        "AN/BPS-15 Radar",
        "https://www.navsea.navy.mil/Home/Warfare-Centers/"
        "NSWC-Port-Hueneme/What-We-Do/In-Service-Engineering/Radars/",
    ),
    (
        "AN/SPS-67 Surface Search Radar",
        "https://www.navsea.navy.mil/Home/Warfare-Centers/"
        "NSWC-Port-Hueneme/What-We-Do/In-Service-Engineering/Radars/",
    ),
    (
        "FuMO 29 Radar",
        "https://uboat.net/technical/radar.htm",
    ),
    (
        "FuMO 30 Radar",
        "https://uboat.net/technical/radar.htm",
    ),
    (
        "Mk 13 Fire Control Radar",
        "https://www.ibiblio.org/hyperwar/NHC/NewPDFs/USN/"
        "USN%20Manuals%20and%20Reports/"
        "USN.Characteristics.Naval.Fire.Control.Radar.1954-11-12.pdf",
    ),
    (
        "Mk 37 GFCS with Mk 25 Fire Control Radar",
        "https://www.ibiblio.org/hyperwar/NHC/NewPDFs/USN/"
        "USN%20Manuals%20and%20Reports/"
        "USN.Characteristics.Naval.Fire.Control.Radar.1954-11-12.pdf",
    ),
    (
        "Mk 38 GFCS with Mk 13 Fire Control Radar",
        "https://www.ibiblio.org/hyperwar/NHC/NewPDFs/USN/"
        "USN%20Manuals%20and%20Reports/"
        "USN.Characteristics.Naval.Fire.Control.Radar.1954-11-12.pdf",
    ),
    # WWII aircraft sights.
    (
        "GM 2 Reflector Gunsight",
        "https://www.spitfirespares.com/gunsites.3.html",
    ),
    (
        "K-14 Gyroscopic Gunsight",
        "https://airandspace.si.edu/collection-objects/"
        "gun-sight-reflecting-k-14b/nasm_A19870343000",
    ),
    (
        "Revi 16B Reflector Gunsight",
        "https://www.si.edu/object/"
        "gun-sight-german-revi-16b%3Anasm_A20140153000",
    ),
    # Ground thermal targeting and independent thermal viewers.
    (
        "AN/TAS-4 TOW Thermal Sight",
        "https://history.redstone.army.mil/miss-tow.html",
    ),
    (
        "CITV Commander's Independent Thermal Viewer",
        "https://rdl.train.army.mil/catalog-ws/view/100.ATSC/"
        "2F4F8430-78F6-459A-A9A5-DFC8E73007E0-1356018579249/"
        "atp3_20x15.pdf",
    ),
    (
        "CIV Commander's Independent Viewer",
        "https://www.army.mil/article/235560/"
        "three_bfv_mishaps_a_common_theme",
    ),
    (
        "Commander's Independent Thermal Viewer",
        "https://elbitsystems.com/media/un20F2006May292007.pdf",
    ),
    (
        "Commander's Thermal Viewer",
        "https://elbitsystems.com/media/un20F2006May292007.pdf",
    ),
    (
        "Castor Thermal Sight",
        "https://www.benning.army.mil/armor/EArmor/content/issues/"
        "1991/JAN_FEB/ArmorJanuaryFebruary1991web.pdf",
    ),
    (
        "EMES 15 Gunner Sight",
        "https://www.knds.de/fileadmin/user_upload/broschueren_2024/"
        "KNDS_B_Ansicht_LEOPARD2A8_EN.pdf",
    ),
    (
        "El-Op Gill Fire Control",
        "https://elbitsystems.com/media/un20F2006May292007.pdf",
    ),
    (
        "El-Op Knight Mark 4 Fire Control",
        "https://elbitsystems.com/media/un20F2006May292007.pdf",
    ),
    (
        "Elbit MARS Thermal Viewer",
        "https://elbitsystems.com/media/ElbitSystems_20F_20120314-1.pdf",
    ),
    (
        "Essa Thermal Sight",
        "https://informnapalm.org/wp-content/uploads/2016/10/"
        "Report_InformNapalm.pdf; "
        "https://rostec.ru/en/media/news/"
        "a-contract-for-supply-of-uralvagonzavod-s-t-90s-tanks-to-india-"
        "marks-it-25th-anniversary/",
    ),
    (
        "GPS 2nd-Gen FLIR Gunner's Sight",
        "https://rdl.train.army.mil/catalog-ws/view/100.ATSC/"
        "2F4F8430-78F6-459A-A9A5-DFC8E73007E0-1356018579249/"
        "atp3_20x15.pdf",
    ),
    (
        "IBAS Thermal Sight",
        "https://www.army.mil/article/235560/"
        "three_bfv_mishaps_a_common_theme",
    ),
    (
        "Javelin CLU Thermal Sight",
        "https://history.redstone.army.mil/miss-javelin.html",
    ),
    (
        "LAV-25 Day/Night Thermal Sight",
        "https://www.marines.mil/News/News-Display/Article/532004/"
        "lar-platoon-performs-vehicle-weapons-maintenance/",
    ),
    (
        "PERI R17A2 Commander Sight",
        "https://contrataciondelestado.es/wps/wcm/connect/"
        "42fe2056-abfc-4d4d-a162-e42643421a35/"
        "DOC20170814113730PPT.pdf?MOD=AJPERES; "
        "https://www.knds.de/fileadmin/user_upload/broschueren_2024/"
        "KNDS_B_Ansicht_LEOPARD2A8_EN.pdf",
    ),
    (
        "TOW Day/Night Thermal Sight",
        "https://history.redstone.army.mil/miss-tow.html",
    ),
    (
        "TOGS II Thermal Sight",
        "https://assets.publishing.service.gov.uk/media/"
        "5d97544440f0b668597085f5/October-desider-online-v3.pdf; "
        "https://www.army.mod.uk/learn-and-explore/equipment/"
        "combat-vehicles/challenger-2/",
    ),
    # Aircraft EO/IR systems whose names are unrelated to the old family pages.
    (
        "MMS Mast-Mounted Sight",
        "https://transportation.army.mil/museum/AOTM/2022/feb_2022.html",
    ),
    (
        "TADS/PNVS",
        "https://www.army.mil/article/17662/"
        "corpus_christi_army_depot_welcomes_apaches_new_sighting_and_targeting_system",
    ),
    (
        "Dragon Eye EO/IR Camera",
        "https://www.hqmc.marines.mil/News/Article/Article/551707/"
        "dragon-eye-flies-over-mcagcc/",
    ),
    (
        "ScanEagle EO/IR Gimbal",
        "https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/"
        "Article/2160330/close-range-uas/",
    ),
    (
        "OEPS-27 IRST",
        "https://server.3rd-wing.net/public/tiengo/Doc/"
        "r%C3%A9aliste%20avionics%20russes.pdf",
    ),
    (
        "Blue Fox Radar",
        "https://hansard.parliament.uk/Commons/1992-10-22/debates/"
        "db214b0f-3ae4-47da-9a2b-d04712dc1df8/CommonsChamber; "
        "https://www.iwm.org.uk/collections/item/object/80032738",
    ),
    (
        "AN/SQQ-89 Sonar",
        "https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/"
        "Article/2166784/ansqq-89v-undersea-warfare-anti-submarine-"
        "warfare-combat-system/",
    ),
)
_SENSOR_FUNCTIONAL_SOURCE_OVERRIDES = _checked_equipment_source_index(
    "sensor functional-source override",
    _SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_DECLARATIONS,
)


@dataclass(frozen=True, slots=True)
class _WeaponSystemCountDeclaration:
    """Reviewed physical-system count represented by one authored item."""

    equipment_name: str
    source_system_count: int
    target_system_count: int = 1

    def __post_init__(self) -> None:
        if not self.equipment_name or self.equipment_name.strip() != self.equipment_name:
            raise EquipmentMappingError(
                "System-count equipment_name must be non-empty and trimmed",
            )
        for value, label in (
            (self.source_system_count, "source_system_count"),
            (self.target_system_count, "target_system_count"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise EquipmentMappingError(
                    f"{label} must be a positive non-bool integer",
                )
        if self.source_system_count % self.target_system_count != 0:
            raise EquipmentMappingError(
                f"source_system_count {self.source_system_count} must be exactly "
                f"divisible by target_system_count {self.target_system_count}",
            )


def _checked_weapon_system_count_index(
    declarations: tuple[_WeaponSystemCountDeclaration, ...],
) -> Mapping[str, _WeaponSystemCountDeclaration]:
    """Index reviewed counts only after every duplicate is observable."""
    seen: dict[str, int] = {}
    for index, declaration in enumerate(declarations):
        if not isinstance(declaration, _WeaponSystemCountDeclaration):
            raise TypeError(
                "Weapon system-count declarations must use the typed record, "
                f"got {type(declaration).__name__} at index {index}",
            )
        if declaration.equipment_name in seen:
            raise EquipmentMappingError(
                "Duplicate weapon system-count declaration for "
                f"{declaration.equipment_name!r} at indexes "
                f"{seen[declaration.equipment_name]} and {index}",
            )
        seen[declaration.equipment_name] = index
    return MappingProxyType({
        declaration.equipment_name: declaration
        for declaration in declarations
    })


# These are physical effectors represented by one authored equipment row.
# The initial syntax audit found 60 multiplicity-bearing attachment names; the
# two U-boat rows using prose ("4 bow, 1/2 stern") were then added so textual
# count encodings cannot silently collapse either.
#
# Most target definitions describe one effector.  Four targets already encode
# a complete aggregate launcher in their catalog definition: the 16-rail M299,
# 8-rail Harpoon pair, 16-rail Mk 141 battery, and 10-tube Mk 15 mount.  Their
# target_system_count equals the source count, making the runtime multiplier
# exactly one and preventing double scaling of already-aggregate cadence and
# magazine values.
_WEAPON_SYSTEM_COUNT_DECLARATIONS = (
    _WeaponSystemCountDeclaration(
        "30.5cm SK L/50 Gun (5x2 turrets)",
        10,
    ),
    _WeaponSystemCountDeclaration(
        "BL 12-inch Mk X Gun (4x2 turrets)",
        8,
    ),
    _WeaponSystemCountDeclaration(
        "BL 13.5-inch Mk V Gun (5x2 turrets)",
        10,
    ),
    _WeaponSystemCountDeclaration("15cm SK L/45 Gun (x14)", 14),
    _WeaponSystemCountDeclaration("QF 4-inch Mk III Gun (x16)", 16),
    _WeaponSystemCountDeclaration("BL 6-inch Mk VII Gun (x12)", 12),
    _WeaponSystemCountDeclaration("QF 4-inch Mk IV Gun (x3)", 3),
    _WeaponSystemCountDeclaration("8.8cm SK L/45 FlaK (x6)", 6),
    _WeaponSystemCountDeclaration(
        "16-inch/50 Mk 7 Gun (3x3 turrets)",
        9,
    ),
    _WeaponSystemCountDeclaration("18-inch Torpedo Tubes (x5)", 5),
    _WeaponSystemCountDeclaration("21-inch Torpedo Tubes (x2x2)", 4),
    _WeaponSystemCountDeclaration("21-inch Torpedo Tubes (x4)", 4),
    _WeaponSystemCountDeclaration("45cm Torpedo Tubes (x4)", 4),
    _WeaponSystemCountDeclaration("50cm Torpedo Tubes (x5)", 5),
    _WeaponSystemCountDeclaration("QF 18-Pounder Field Gun (x4)", 4),
    _WeaponSystemCountDeclaration("QF 3-inch AA Gun (x2)", 2),
    _WeaponSystemCountDeclaration(
        "18-pdr Long Guns (upper deck, x30)",
        30,
    ),
    _WeaponSystemCountDeclaration(
        "18-pdr Long Guns (upper deck, x34)",
        34,
    ),
    _WeaponSystemCountDeclaration(
        "24-pdr Long Guns (middle deck, x34)",
        34,
    ),
    _WeaponSystemCountDeclaration("24-pdr Long Guns (x26)", 26),
    _WeaponSystemCountDeclaration(
        "32-pdr Long Guns (lower deck, x28)",
        28,
    ),
    _WeaponSystemCountDeclaration(
        "32-pdr Long Guns (lower deck, x32)",
        32,
    ),
    _WeaponSystemCountDeclaration(
        "5-inch/38 Mk 12 Gun (10x2 turrets)",
        20,
    ),
    _WeaponSystemCountDeclaration(
        "5-inch/38 Mk 12 Gun (4x2 turrets)",
        8,
    ),
    _WeaponSystemCountDeclaration("5-inch/38 Mk 12 Gun (x5)", 5),
    _WeaponSystemCountDeclaration("Type 89 12.7cm AA Gun (8x2)", 16),
    _WeaponSystemCountDeclaration(
        "9-pdr Guns (quarterdeck/forecastle, x16)",
        16,
    ),
    _WeaponSystemCountDeclaration("9-pdr Long Guns (x18)", 18),
    _WeaponSystemCountDeclaration(
        "7.7cm FK 96 n.A. Field Gun (x4)",
        4,
    ),
    _WeaponSystemCountDeclaration("Ballistae (x2)", 2),
    _WeaponSystemCountDeclaration("Carronades 24-pdr (x2)", 2),
    _WeaponSystemCountDeclaration("Carronades 32-pdr (x6)", 6),
    _WeaponSystemCountDeclaration(
        "Congreve Rocket Launcher Tripod (x4)",
        4,
    ),
    _WeaponSystemCountDeclaration(
        "LMG 08/15 Spandau MG (x2)",
        2,
    ),
    _WeaponSystemCountDeclaration(
        "Browning .303 Machine Gun (x4)",
        4,
    ),
    _WeaponSystemCountDeclaration(
        "M2 Browning .50 Cal (x13)",
        13,
    ),
    _WeaponSystemCountDeclaration(
        "M2 Browning .50 Cal (x6)",
        6,
    ),
    _WeaponSystemCountDeclaration("MG 08 Machine Gun (x6)", 6),
    _WeaponSystemCountDeclaration(
        "Hispano Mk II 20mm Cannon (x2)",
        2,
    ),
    _WeaponSystemCountDeclaration(
        "MG 131 13mm Machine Gun (x2)",
        2,
    ),
    _WeaponSystemCountDeclaration(
        "Mk 15 Torpedo Tubes (2x5)",
        10,
        10,
    ),
    _WeaponSystemCountDeclaration("533mm Torpedo Tubes x6", 6),
    _WeaponSystemCountDeclaration(
        "Harpoon Quad Launchers (x2)",
        8,
        8,
    ),
    _WeaponSystemCountDeclaration(
        "Mk 141 Harpoon Quad Launchers (x4)",
        16,
        16,
    ),
    _WeaponSystemCountDeclaration("2x S-68 57mm Autocannon", 2),
    _WeaponSystemCountDeclaration(
        "Type 99 Model 2 20mm Cannon (x2)",
        2,
    ),
    _WeaponSystemCountDeclaration("Type 97 7.7mm MG (x2)", 2),
    _WeaponSystemCountDeclaration(
        "Bofors 40mm Quad Mount (x20)",
        80,
    ),
    _WeaponSystemCountDeclaration(
        "Bofors 40mm Quad Mount (x8)",
        32,
    ),
    _WeaponSystemCountDeclaration(
        "Bofors 40mm Twin Mount (x2)",
        4,
    ),
    _WeaponSystemCountDeclaration(
        "Bofors 40mm Twin Mount (x5)",
        10,
    ),
    _WeaponSystemCountDeclaration("Oerlikon 20mm (x46)", 46),
    _WeaponSystemCountDeclaration("Oerlikon 20mm (x49)", 49),
    _WeaponSystemCountDeclaration("Oerlikon 20mm (x6)", 6),
    _WeaponSystemCountDeclaration("Oerlikon 20mm (x7)", 7),
    _WeaponSystemCountDeclaration(
        "Type 96 25mm Triple Mount (x12)",
        36,
    ),
    _WeaponSystemCountDeclaration(
        "Vickers .303 Synchronized MG (x2)",
        2,
    ),
    _WeaponSystemCountDeclaration(
        "M299 Launchers (x4)",
        16,
        16,
    ),
    _WeaponSystemCountDeclaration(
        "Depth Charge Rails and Throwers (x4)",
        4,
    ),
    _WeaponSystemCountDeclaration(
        "M60 7.62mm MG (sponson x4)",
        4,
    ),
    _WeaponSystemCountDeclaration(
        "53.3cm Torpedo Tubes (4 bow, 1 stern)",
        5,
    ),
    _WeaponSystemCountDeclaration(
        "53.3cm Torpedo Tubes (4 bow, 2 stern)",
        6,
    ),
)
_WEAPON_SYSTEM_COUNT_INDEX = _checked_weapon_system_count_index(
    _WEAPON_SYSTEM_COUNT_DECLARATIONS,
)


def _weapon_records(
    weapon_id: str,
    category: WeaponCategory,
    modeled_role: WeaponModeledRole,
    *equipment_names: str,
    required_ammo_types: tuple[AmmoType, ...] = (),
    allowed_ammo_ids: tuple[str, ...] = (),
    required_target_domains: tuple[Domain, ...] | None = None,
    expected_caliber_mm: float | None = None,
    expected_guidance: GuidanceType | None = None,
) -> tuple[WeaponAttachmentMapping, ...]:
    records: list[WeaponAttachmentMapping] = []
    for equipment_name in equipment_names:
        count_declaration = _WEAPON_SYSTEM_COUNT_INDEX.get(equipment_name)
        if (
            equipment_name_declares_system_count(equipment_name)
            and count_declaration is None
        ):
            raise EquipmentMappingError(
                "Count-bearing weapon equipment lacks an explicit reviewed "
                f"system-count declaration: {equipment_name!r}",
            )
        exact = equipment_name in _EXACT_WEAPON_EQUIPMENT
        variant = equipment_name in _VARIANT_WEAPON_EQUIPMENT
        functional = not exact and not variant
        functional_source = _WEAPON_FUNCTIONAL_SOURCES.get(
            (weapon_id, modeled_role),
        )
        if functional and functional_source is None:
            raise EquipmentMappingError(
                "Functional weapon analogue has no traceable family source: "
                f"{equipment_name!r} -> {weapon_id!r}/{modeled_role.value!r}",
            )
        constraint_labels: list[str] = []
        if required_ammo_types:
            constraint_labels.append(
                f"ammunition types {[ammo_type.name for ammo_type in required_ammo_types]}",
            )
        if allowed_ammo_ids:
            constraint_labels.append(
                f"ammunition IDs {list(allowed_ammo_ids)}",
            )
        if expected_caliber_mm is not None:
            constraint_labels.append(
                f"caliber {expected_caliber_mm:g} mm",
            )
        if expected_guidance is not None:
            constraint_labels.append(
                f"guidance {expected_guidance.name}",
            )
        records.append(
            WeaponAttachmentMapping(
                equipment_name=equipment_name,
                weapon_id=weapon_id,
                expected_weapon_category=category,
                modeled_role=modeled_role,
                reference_kind=(
                    ReferenceKind.EXACT
                    if exact
                    else (ReferenceKind.VARIANT if variant else ReferenceKind.FUNCTIONAL_ANALOGUE)
                ),
                allowed_target_ids=(() if exact or variant else (weapon_id,)),
                rationale=(
                    None
                    if exact or variant
                    else (
                        f"{equipment_name!r} is bounded to the typed "
                        f"{modeled_role.value!r} behavior of target "
                        f"{weapon_id!r}. Runtime preflight validates "
                        f"{', '.join(constraint_labels)} and the role's target "
                        "domains; identity and equal physical performance are "
                        "not asserted."
                    )
                ),
                source=(None if exact or variant else functional_source),
                required_target_domains=required_domains_for_weapon_role(
                    modeled_role,
                )
                if required_target_domains is None
                else required_target_domains,
                required_ammo_types=required_ammo_types,
                allowed_ammo_ids=allowed_ammo_ids,
                expected_caliber_mm=expected_caliber_mm,
                expected_guidance=expected_guidance,
                source_system_count=(
                    count_declaration.source_system_count
                    if count_declaration is not None
                    else 1
                ),
                target_system_count=(
                    count_declaration.target_system_count
                    if count_declaration is not None
                    else 1
                ),
            )
        )
    return tuple(records)


def _sensor_records(
    sensor_id: str,
    sensor_type: SensorType,
    signature_domain: SignatureDomain,
    modeled_role: SensorModeledRole,
    *equipment_names: str,
    modeled_max_range_m: float,
    modeled_fov_deg: float,
) -> tuple[SensorAttachmentMapping, ...]:
    records: list[SensorAttachmentMapping] = []
    for equipment_name in equipment_names:
        exact = equipment_name in _EXACT_SENSOR_EQUIPMENT
        variant = equipment_name in _VARIANT_SENSOR_EQUIPMENT
        functional = not exact and not variant
        family_source = _SENSOR_FUNCTIONAL_SOURCES.get(
            (sensor_id, modeled_role),
        )
        functional_source = _SENSOR_FUNCTIONAL_SOURCE_OVERRIDES.get(
            equipment_name,
            family_source,
        )
        if functional and functional_source is None:
            raise EquipmentMappingError(
                "Functional sensor analogue has no traceable family source: "
                f"{equipment_name!r} -> {sensor_id!r}/{modeled_role.value!r}",
            )
        records.append(
            SensorAttachmentMapping(
                equipment_name=equipment_name,
                sensor_id=sensor_id,
                expected_sensor_type=sensor_type,
                expected_signature_domain=signature_domain,
                modeled_role=modeled_role,
                required_target_domains=required_domains_for_sensor_role(
                    modeled_role,
                ),
                modeled_max_range_m=modeled_max_range_m,
                modeled_fov_deg=modeled_fov_deg,
                reference_kind=(
                    ReferenceKind.EXACT
                    if exact
                    else (ReferenceKind.VARIANT if variant else ReferenceKind.FUNCTIONAL_ANALOGUE)
                ),
                allowed_target_ids=((sensor_id,) if not exact and not variant else ()),
                rationale=(
                    None
                    if exact or variant
                    else (
                        f"{equipment_name!r} is bounded to the typed "
                        f"{modeled_role.value!r} behavior of target "
                        f"{sensor_id!r}. Runtime preflight validates "
                        f"{sensor_type.name}/{signature_domain.name}, the "
                        "role's target domains, and a "
                        f"{modeled_max_range_m:g} m/{modeled_fov_deg:g}-degree "
                        "modeled cap. That cap is not asserted as a "
                        "source-measured historical value; identity and equal "
                        "physical performance are not asserted."
                    )
                ),
                source=(None if exact or variant else functional_source),
            )
        )
    return tuple(records)


EQUIPMENT_MAPPING_RECORDS: tuple[EquipmentMappingRecord, ...] = (
    *_weapon_records(
        "sk_l50_305mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "30.5cm SK L/50 Gun (5x2 turrets)",
        required_ammo_types=(AmmoType.AP, AmmoType.HE),
        allowed_ammo_ids=(
            "305mm_psgr_l3_4_apc",
            "305mm_spgr_l3_8_he",
        ),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=305.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "12in_bl_mk_x",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "BL 12-inch Mk X Gun (4x2 turrets)",
    ),
    *_weapon_records(
        "bl_13_5in_mk_v",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "BL 13.5-inch Mk V Gun (5x2 turrets)",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("13_5in_apc_mk_ia",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=343.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "12pdr_cannon",
        WeaponCategory.ARTILLERY,
        WeaponModeledRole.FIELD_ARTILLERY,
        "12-Pounder Cannon",
    ),
    *_weapon_records(
        "15cm_sk_l45",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "15cm SK L/45 Gun (x14)",
    ),
    *_weapon_records(
        "sk_l30_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "8.8cm SK L/30 Deck Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("88mm_c07_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=88.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "qf_4in_mk_iii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "QF 4-inch Mk III Gun (x16)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("4in_mk_iii_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=101.6,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bl_6in_mk_vii",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "BL 6-inch Mk VII Gun (x12)",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("6in_mk_vii_cpc",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=152.4,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "qf_4in_mk_iv",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "QF 4-inch Mk IV Gun (x3)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("4in_mk_iv_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=101.6,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "88mm_sk_l45_flak",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "8.8cm SK L/45 FlaK (x6)",
        required_ammo_types=(AmmoType.HE,),
        expected_caliber_mm=88.0,
    ),
    *_weapon_records(
        "qf_6pdr_6cwt",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "QF 6-pounder 6 cwt Hotchkiss Gun",
        expected_caliber_mm=57.0,
    ),
    *_weapon_records(
        "16in50_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "16 inch/50 Mk 7 Gun",
        "16-inch/50 Mk 7 Gun (3x3 turrets)",
    ),
    *_weapon_records(
        "18in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "18-inch Torpedo Tubes (x5)",
    ),
    *_weapon_records(
        "british_21in_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "21-inch Torpedo Tubes (x2x2)",
        "21-inch Torpedo Tubes (x4)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("british_21in_mk_ii_warhead",),
        required_target_domains=(Domain.NAVAL, Domain.SUBMARINE),
        expected_caliber_mm=533.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "c06d_45cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "45cm Torpedo Tubes (x4)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("c06d_45cm_warhead",),
        required_target_domains=(Domain.NAVAL, Domain.SUBMARINE),
        expected_caliber_mm=450.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "g7_50cm_torpedo_ww1",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "50cm Torpedo Tubes (x5)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("g7_50cm_warhead",),
        required_target_domains=(Domain.NAVAL, Domain.SUBMARINE),
        expected_caliber_mm=500.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "18pdr_field_gun",
        WeaponCategory.CANNON,
        WeaponModeledRole.FIELD_ARTILLERY,
        "QF 18-Pounder Field Gun (x4)",
    ),
    *_weapon_records(
        "maxim_nordenfelt_57mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "57mm Maxim-Nordenfelt Gun",
        expected_caliber_mm=57.0,
    ),
    *_weapon_records(
        "qf_3in_20cwt_aa",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "QF 3-inch AA Gun (x2)",
        required_ammo_types=(AmmoType.HE,),
        expected_caliber_mm=76.2,
    ),
    *_weapon_records(
        "18pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "18-pdr Long Guns (upper deck, x30)",
        "18-pdr Long Guns (upper deck, x34)",
        required_ammo_types=(AmmoType.AP, AmmoType.SHRAPNEL),
        allowed_ammo_ids=("round_shot_18pdr", "grape_shot_18pdr"),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=134.4,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "24pdr_cannon",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "24-pdr Long Guns (middle deck, x34)",
        "24-pdr Long Guns (x26)",
    ),
    *_weapon_records(
        "2a28_grom_73mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "73mm 2A28 Grom",
    ),
    *_weapon_records(
        "2a42_30mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "2A42 30mm Autocannon",
    ),
    *_weapon_records(
        "2a46m_125mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "2A46M 125mm Smoothbore",
        "2A46M-5 125mm Smoothbore",
    ),
    *_weapon_records(
        "2s1_gvozdika",
        WeaponCategory.HOWITZER,
        WeaponModeledRole.FIELD_ARTILLERY,
        "2S1 Gvozdika 122mm SP",
    ),
    *_weapon_records(
        "2s3_akatsiya",
        WeaponCategory.HOWITZER,
        WeaponModeledRole.FIELD_ARTILLERY,
        "2S3 Akatsiya 152mm SP",
    ),
    *_weapon_records(
        "32pdr_cannon",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "32-pdr Long Guns (lower deck, x28)",
        "32-pdr Long Guns (lower deck, x32)",
    ),
    *_weapon_records(
        "5in38_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "5-inch/38 Mk 12 Gun (10x2 turrets)",
        "5-inch/38 Mk 12 Gun (4x2 turrets)",
        "5-inch/38 Mk 12 Gun (x5)",
    ),
    *_weapon_records(
        "sk_c32_105mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "10.5cm SK C/32 Deck Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("105mm_c32_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=105.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "sk_c35_88mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "8.8cm SK C/35 Deck Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("88mm_c35_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=88.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bl_4in_mk_ix",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "BL 4-inch Mk IX Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("4in_mk_ix_he",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=101.6,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "type89_127mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Type 89 12.7cm AA Gun (8x2)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("type89_127mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=127.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "6pdr_cannon",
        WeaponCategory.ARTILLERY,
        WeaponModeledRole.FIELD_ARTILLERY,
        "6-Pounder Cannon",
    ),
    *_weapon_records(
        "9pdr_naval",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "9-pdr Guns (quarterdeck/forecastle, x16)",
        "9-pdr Long Guns (x18)",
        expected_caliber_mm=101.6,
    ),
    *_weapon_records(
        "pak40_l46_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "7.5cm PaK 40 L/46",
        required_ammo_types=(AmmoType.AP, AmmoType.HE),
        allowed_ammo_ids=(
            "75mm_pzgr39_pak40_apcbc",
            "75mm_sprgr34_pak40_he",
        ),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=75.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "kwk40_l48_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "75mm KwK 40 L/48 Gun",
        required_ammo_types=(AmmoType.AP, AmmoType.HE),
        allowed_ammo_ids=(
            "75mm_pzgr39_kwk40_apcbc",
            "75mm_sprgr34_kwk40_he",
        ),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=75.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "75mm_m3",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "75mm M3 Gun",
    ),
    *_weapon_records(
        "qf_6pdr_l50",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "QF 6-Pounder (57mm) L/50",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("57mm_apcbc_mk9t",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=57.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "77mm_fk96",
        WeaponCategory.CANNON,
        WeaponModeledRole.FIELD_ARTILLERY,
        "7.7cm FK 96 n.A. Field Gun (x4)",
    ),
    *_weapon_records(
        "85mm_zis_s53",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "85mm ZIS-S-53 Gun",
    ),
    *_weapon_records(
        "88mm_kwk36",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "88mm KwK 36 L/56 Gun",
    ),
    *_weapon_records(
        "kwk42_75mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "75mm KwK 42 L/70 Gun",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("75mm_pzgr39_42_apcbc",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=75.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "ac130_105mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "105mm M102 Howitzer (direct-fire mount)",
    ),
    *_weapon_records(
        "ac130_40mm_bofors",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "40mm Bofors L/60 Automatic Gun",
    ),
    *_weapon_records(
        "agm114_hellfire",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE,
        "AGM-114 Hellfire Launcher",
        "M299 Launchers (x4)",
    ),
    *_weapon_records(
        "shturm_v_9m114",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE,
        "9M114 Shturm-V Launcher",
        required_ammo_types=(AmmoType.HEAT,),
        allowed_ammo_ids=("9m114_shturm",),
        expected_caliber_mm=130.0,
        expected_guidance=GuidanceType.COMMAND,
    ),
    *_weapon_records(
        "agm65_maverick",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_GROUND_MISSILE,
        "AGM-65 Maverick",
    ),
    *_weapon_records(
        "aim120_amraam",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "AIM-120 AMRAAM",
    ),
    *_weapon_records(
        "aim7m_sparrow",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "AIM-7M Sparrow",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("aim7m_sparrow",),
        expected_caliber_mm=200.0,
        expected_guidance=GuidanceType.RADAR_SEMI,
    ),
    *_weapon_records(
        "aim9x_sidewinder",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "AIM-9X Sidewinder",
    ),
    *_weapon_records(
        "aim9l_sidewinder",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "AIM-9L Sidewinder",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("aim9l_sidewinder",),
        expected_caliber_mm=130.0,
        expected_guidance=GuidanceType.IR,
    ),
    *_weapon_records(
        "ak47",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.ASSAULT_RIFLE,
        "AK-47",
        "AKM",
        "AKMS",
    ),
    *_weapon_records(
        "ak74_545mm",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ASSAULT_RIFLE,
        "AK-74",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("545x39_ball",),
        expected_caliber_mm=5.45,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "svd_dragunov",
        WeaponCategory.RIFLE,
        WeaponModeledRole.SNIPER_RIFLE,
        "SVD Dragunov",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=7.62,
    ),
    *_weapon_records(
        "am39_exocet",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "AM.39 Exocet",
    ),
    *_weapon_records(
        "9p135m_konkurs",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "9P135M ATGM Launcher",
        required_ammo_types=(AmmoType.HEAT,),
        allowed_ammo_ids=("9m113_konkurs",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=135.0,
        expected_guidance=GuidanceType.WIRE,
    ),
    *_weapon_records(
        "at3_sagger",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "AT-3 Sagger ATGM",
    ),
    *_weapon_records(
        "at4_law",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "AT-4 LAW",
    ),
    *_weapon_records(
        "carl_gustaf_m3",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "Carl Gustaf M3",
        required_ammo_types=(AmmoType.HEAT,),
        allowed_ammo_ids=("carl_gustaf_heat551",),
        expected_caliber_mm=84.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "baker_rifle",
        WeaponCategory.RIFLE,
        WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        "Baker Rifle",
    ),
    *_weapon_records(
        "ballista",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Ballistae (x2)",
        required_target_domains=(Domain.NAVAL,),
    ),
    *_weapon_records(
        "lepanto_galley_bow_battery",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "Lepanto Galley Bow Gun Battery",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("lepanto_galley_roundshot",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "barak1_sam",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "Barak-1 VLS SAM",
    ),
    *_weapon_records(
        "bayonet",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Bayonet",
    ),
    *_weapon_records(
        "bm21_grad",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ROCKET_ARTILLERY,
        "BM-21 Grad 122mm MRL",
    ),
    *_weapon_records(
        "bomb_rack_generic",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.BOMB_DELIVERY,
        "CSRL Rotary Launcher",
        allowed_ammo_ids=("gbu31_jdam",),
        required_ammo_types=(AmmoType.GUIDED,),
    ),
    *_weapon_records(
        "bomb_rack_generic",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.BOMB_DELIVERY,
        "Generic Bomb Rack",
        allowed_ammo_ids=("mk82_500lb",),
        required_ammo_types=(AmmoType.HE,),
    ),
    *_weapon_records(
        "mau40a_bomb_ejector_rack",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.BOMB_DELIVERY,
        "MAU-40/A Bomb Ejector Rack",
        required_ammo_types=(AmmoType.CLUSTER,),
        allowed_ammo_ids=("mk20_rockeye",),
    ),
    *_weapon_records(
        "bru36a_bomb_ejector_rack",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.BOMB_DELIVERY,
        "BRU-36/A Bomb Ejector Rack",
        required_ammo_types=(AmmoType.CLUSTER,),
        allowed_ammo_ids=("mk20_rockeye",),
    ),
    *_weapon_records(
        "brown_bess",
        WeaponCategory.RIFLE,
        WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        "Austrian M1798 Infantry Musket",
        "Brown Bess Musket",
        "Musketoon",
        "Musketoon (Dragoon)",
        "Muskets (personal arms)",
        "Tula Musket M1808",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("musket_ball_75",),
        expected_caliber_mm=19.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "c802_noor",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "C-802 Noor Launcher",
    ),
    *_weapon_records(
        "carronade_24pdr",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "Carronades 24-pdr (x2)",
        required_ammo_types=(AmmoType.AP, AmmoType.SHRAPNEL),
        allowed_ammo_ids=(
            "round_shot_24pdr_carronade",
            "grape_shot_24pdr_carronade",
        ),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=144.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "carronade_32pdr",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "Carronades 32-pdr (x6)",
    ),
    *_weapon_records(
        "cavalry_saber",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Cavalry Saber",
    ),
    *_weapon_records(
        "charleville_1777",
        WeaponCategory.RIFLE,
        WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        "Charleville 1777 Musket",
        "Charleville Musket (personal arms)",
    ),
    *_weapon_records(
        "congreve_rocket",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ROCKET_ARTILLERY,
        "Congreve Rocket Launcher Tripod (x4)",
    ),
    *_weapon_records(
        "arquebus",
        WeaponCategory.RIFLE,
        WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        "Arquebuses",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("arquebus_ball",),
        required_target_domains=(Domain.NAVAL,),
        expected_caliber_mm=15.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "crossbow",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Crossbows",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("bolt_crossbow",),
        required_target_domains=(Domain.NAVAL,),
        expected_caliber_mm=15.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "d10t_100mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "D-10T 100mm Rifled Gun",
    ),
    *_weapon_records(
        "d30_122mm",
        WeaponCategory.HOWITZER,
        WeaponModeledRole.FIELD_ARTILLERY,
        "D-30 122mm Howitzer",
    ),
    *_weapon_records(
        "de_shorad_50kw",
        WeaponCategory.DIRECTED_ENERGY,
        WeaponModeledRole.DIRECTED_ENERGY,
        "50kW Fiber Laser",
    ),
    *_weapon_records(
        "depth_charge_mk7",
        WeaponCategory.DEPTH_CHARGE,
        WeaponModeledRole.ANTI_SUBMARINE,
        "Depth Charge Racks and K-Guns",
        "Depth Charge Rails and Throwers (x4)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("mk7_depth_charge",),
        expected_caliber_mm=457.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "hedgehog_mk10",
        WeaponCategory.DEPTH_CHARGE,
        WeaponModeledRole.ANTI_SUBMARINE,
        "Hedgehog ASW Mortar",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("hedgehog_mk10_projectile",),
        required_target_domains=(Domain.SUBMARINE,),
        expected_caliber_mm=182.88,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "rim116_ram",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "RAM Launcher",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("rim116_block1a",),
        expected_caliber_mm=127.0,
        expected_guidance=GuidanceType.COMBINED,
    ),
    *_weapon_records(
        "frog7_launcher",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ROCKET_ARTILLERY,
        "9K52 Luna-M FROG-7 TEL",
    ),
    *_weapon_records(
        "g7e_torpedo",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "53.3cm Torpedo Tubes (4 bow, 1 stern)",
        "53.3cm Torpedo Tubes (4 bow, 2 stern)",
    ),
    *_weapon_records(
        "gau12_25mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "GAU-12 Equalizer 25mm",
    ),
    *_weapon_records(
        "gau8_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "GAU-8/A Avenger 30mm",
    ),
    *_weapon_records(
        "aden_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "30mm ADEN",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("30x113b_aden_hei",),
        expected_caliber_mm=30.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m230_chain_gun",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M230 Chain Gun 30mm",
        required_ammo_types=(AmmoType.HEAT,),
        allowed_ammo_ids=("30x113_m789_hedp",),
        expected_caliber_mm=30.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "gewehr_98",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "Gewehr 98 Rifle",
    ),
    *_weapon_records(
        "gladius",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Gladius",
        "Gladii",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("sword_strike",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "spathion_sword",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Spathion Sword",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("sword_strike",),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "greek_fire_siphon",
        WeaponCategory.CANNON,
        WeaponModeledRole.INCENDIARY_PROJECTOR,
        "Greek Fire Siphon",
        required_target_domains=(Domain.NAVAL,),
    ),
    *_weapon_records(
        "helios_60kw",
        WeaponCategory.DIRECTED_ENERGY,
        WeaponModeledRole.DIRECTED_ENERGY,
        "HELIOS 60kW Laser",
    ),
    *_weapon_records(
        "iron_beam_100kw",
        WeaponCategory.DIRECTED_ENERGY,
        WeaponModeledRole.DIRECTED_ENERGY,
        "100kW Solid-State Laser",
    ),
    *_weapon_records(
        "javelin_clm",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "FGM-148 Javelin CLU",
    ),
    *_weapon_records(
        "kar98k",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "Karabiner 98k Rifle",
    ),
    *_weapon_records(
        "kornet_9m133",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "9P163-2 Kornet Launcher",
    ),
    *_weapon_records(
        "cn105_f1_105mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "F1 105mm Rifled Gun",
        required_ammo_types=(AmmoType.HEAT,),
        allowed_ammo_ids=("occ_105_f1_heat",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=105.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "l7_105mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "L7 105mm Rifled Gun",
    ),
    *_weapon_records(
        "lance",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Lance (Napoleonic)",
    ),
    *_weapon_records(
        "lance_medieval",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Kontarion Lance",
        "Lance (Ancient)",
        "Lance (Medieval)",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("lance_thrust",),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "lebel_m1886_m93",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "Lebel Mle 1886 M93 Rifle",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("8x50r_lebel_balle_d",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=8.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "lee_enfield",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "Lee-Enfield SMLE Mk III Rifle",
        "SMLE Cavalry Carbine",
    ),
    *_weapon_records(
        "chauchat_m1915",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "Chauchat M1915 CSRG Light Machine Gun",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("8x50r_lebel_balle_d",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=8.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "lewis_gun",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "Lewis Gun Sponson Mount",
    ),
    *_weapon_records(
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "M1918 BAR",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("30_06_m1906_ball",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mp18",
        WeaponCategory.SUBMACHINE_GUN,
        WeaponModeledRole.SUBMACHINE_GUN,
        "MP 18 Submachine Gun",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=9.0,
    ),
    *_weapon_records(
        "lmg08_spandau",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.AIRCRAFT_GUN,
        "LMG 08/15 Spandau MG (x2)",
    ),
    *_weapon_records(
        "longbow",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Longbow",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("arrow_longbow",),
        expected_caliber_mm=12.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "composite_bow",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Composite Bow",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("composite_arrow",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=10.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "javelin",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Byzantine Marine Javelins",
        "Greek Marine Javelins",
        "Viking Javelins",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("javelin_throw",),
        required_target_domains=(Domain.NAVAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m121_120mm_mortar",
        WeaponCategory.MORTAR,
        WeaponModeledRole.MORTAR_FIRE,
        "M121 120mm Mortar",
    ),
    *_weapon_records(
        "yakb_127mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "YakB-12.7 Gatling Gun",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("yakb_12_7x108_api",),
        expected_caliber_mm=12.7,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m16a4",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.ASSAULT_RIFLE,
        "M16A4 Rifle",
    ),
    *_weapon_records(
        "m197_20mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M197 20mm Rotary Cannon",
    ),
    *_weapon_records(
        "m224_60mm",
        WeaponCategory.MORTAR,
        WeaponModeledRole.MORTAR_FIRE,
        "Soltam 60mm Internal Mortar",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("m720_60mm_he",),
        expected_caliber_mm=60.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m240_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "L94A1 7.62mm Chain Gun",
        "M240 7.62mm",
        "M240 7.62mm Coaxial",
        "M240 7.62mm Loader",
        "M240B GPMG",
        "M240C 7.62mm Coaxial",
        "MG3 7.62mm Coaxial",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "negev_ng5_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "IMI Negev 5.56mm LMG",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("556_ss109_ball",),
        expected_caliber_mm=5.56,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m249_saw",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "M249 SAW",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("556_m855a1_linked",),
        expected_caliber_mm=5.56,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "pkm_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "PKM GPMG",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762x54r_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "pkt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "PKT 7.62mm Coaxial",
        "PKT 7.62mm MG",
        "PKT 7.62mm Machine Gun",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762x54r_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "sgmt_762x54r",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "SGMT 7.62mm Coaxial",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762x54r_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m240_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.AIR_DEFENSE_GUN,
        "7.62mm AA Machine Gun",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m240_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M60 7.62mm MG (sponson x4)",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762_ball",),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m242_bushmaster",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "M242 25mm Chain Gun",
    ),
    *_weapon_records(
        "m693_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "20mm M693 Coaxial",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("20x139_m693_hei",),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "2b14_82mm_mortar",
        WeaponCategory.MORTAR,
        WeaponModeledRole.MORTAR_FIRE,
        "Iraqi 82mm 2B14 Mortar",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("o832du_82mm_he",),
        expected_caliber_mm=82.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m256_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "M256 120mm Smoothbore",
    ),
    *_weapon_records(
        "l30a1_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "L30A1 120mm Rifled Gun",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("l27a1_charm3_apfsds",),
        expected_caliber_mm=120.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "rh120_l55_120mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "Rh-120 L/55 120mm Smoothbore",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("dm53_apfsds",),
        expected_caliber_mm=120.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m284_155mm",
        WeaponCategory.HOWITZER,
        WeaponModeledRole.FIELD_ARTILLERY,
        "M284 155mm Howitzer",
    ),
    *_weapon_records(
        "browning_303_mk_ii",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Browning .303 Machine Gun (x4)",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("303_mk_vii_ball",),
        required_target_domains=(Domain.GROUND, Domain.AERIAL),
        expected_caliber_mm=7.7,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m2_50cal_ww2",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M2 Browning .50 Cal (x13)",
        "M2 Browning .50 Cal (x6)",
    ),
    *_weapon_records(
        "m1919a4_30cal",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "M1919A4 .30 Cal Coaxial",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=7.62,
    ),
    *_weapon_records(
        "nsvt_127mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        "NSVT 12.7mm HMG",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("12_7x108_api",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=12.7,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m2hb_50cal",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        "M2 .50 Cal",
        "M2HB .50 Cal",
    ),
    *_weapon_records(
        "kpvt_145mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.HEAVY_MACHINE_GUN,
        "KPVT 14.5mm HMG",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("145x114_bzt561sm",),
        expected_caliber_mm=14.5,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m2hb_50cal",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M296 .50 Cal MG",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("50bmg_m2_ap",),
        expected_caliber_mm=12.7,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m2hb_50cal",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.AIR_DEFENSE_GUN,
        "M2HB .50 Cal AA Mount",
        required_ammo_types=(AmmoType.AP,),
        expected_caliber_mm=12.7,
    ),
    *_weapon_records(
        "m82a1_sasr",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANTI_MATERIEL_RIFLE,
        "Barrett M82A1 .50 Rifle",
        required_ammo_types=(AmmoType.AP,),
        expected_caliber_mm=12.7,
    ),
    *_weapon_records(
        "m4_556mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.ASSAULT_RIFLE,
        "M16A2 Rifle",
        "M4A1 Carbine",
        "M4A1 SOPMOD",
        "Suppressed M4A1 Rifle",
        "Tavor TAR-21 CTAR",
        "Tavor TAR-21 Rifle",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("556_ball",),
        expected_caliber_mm=5.56,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m1903_springfield",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "M1903 Springfield Rifle",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=7.62,
    ),
    *_weapon_records(
        "m1_garand",
        WeaponCategory.RIFLE,
        WeaponModeledRole.SEMI_AUTOMATIC_RIFLE,
        "M1 Garand Rifle",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=7.62,
    ),
    *_weapon_records(
        "m40a1_sniper",
        WeaponCategory.RIFLE,
        WeaponModeledRole.SNIPER_RIFLE,
        "M40A1 Sniper Rifle",
        required_ammo_types=(AmmoType.BALL,),
        expected_caliber_mm=7.62,
    ),
    *_weapon_records(
        "m61a1_vulcan",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "M61A1 Vulcan 20mm",
    ),
    *_weapon_records(
        "defa553_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "DEFA 553 30mm Cannon",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("30x113b_defa_hei",),
        expected_caliber_mm=30.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "gsh23_23mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "GSh-23 23mm Cannon",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("23x115_hei",),
        expected_caliber_mm=23.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "gsh30_1_30mm",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "GSh-30-1 30mm Cannon",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("30x165_gsh_ap_t",),
        expected_caliber_mm=30.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "maxim_mg08",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "MG 08 Machine Gun (x6)",
    ),
    *_weapon_records(
        "hispano_mk_ii_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Hispano Mk II 20mm Cannon (x2)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("20mm_hispano_mk_ii_he",),
        required_target_domains=(Domain.GROUND, Domain.AERIAL),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mg151_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "MG 151/20 20mm Cannon",
    ),
    *_weapon_records(
        "mg34_792mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "MG 34 Coaxial",
        "MG 34 Hull Mount",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("792mm_sst_ap",),
        expected_caliber_mm=7.92,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mg42",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "MG 42 Light Machine Gun",
        required_ammo_types=(AmmoType.AP,),
        allowed_ammo_ids=("792mm_sst_ap",),
        expected_caliber_mm=7.92,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "dp28_lmg",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "DP-28 Light Machine Gun",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762x54r_l_ball_ww2",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "dt_762mm",
        WeaponCategory.MACHINE_GUN,
        WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN,
        "DT 7.62mm Coaxial MG",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("762x54r_l_ball_ww2",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "m1918a2_bar",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.LIGHT_MACHINE_GUN,
        "M1918A2 BAR",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("30_06_m2_ball",),
        required_target_domains=(Domain.GROUND,),
        expected_caliber_mm=7.62,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mg131_13mm",
        WeaponCategory.HEAVY_MG,
        WeaponModeledRole.AIRCRAFT_GUN,
        "MG 131 13mm Machine Gun (x2)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("13mm_mg131_he",),
        required_target_domains=(Domain.GROUND, Domain.AERIAL),
        expected_caliber_mm=13.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mills_bomb",
        WeaponCategory.GRENADE,
        WeaponModeledRole.HAND_GRENADE,
        "F1 Grenade",
        "Mills Bomb No. 5 Grenade",
        "Mk II Grenade",
        "Stielhandgranate M1917 Grenade",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("mills_bomb_frag",),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mim104_pac3",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "M901 Launching Station",
    ),
    *_weapon_records(
        "s300pmu_5p85",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "5P85 TEL",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("48n6_sam",),
        expected_caliber_mm=500.0,
        expected_guidance=GuidanceType.COMBINED,
    ),
    *_weapon_records(
        "buk_m1_9a310",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "9A310 TELAR",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("9m38m1_sam",),
        expected_caliber_mm=400.0,
        expected_guidance=GuidanceType.RADAR_SEMI,
    ),
    *_weapon_records(
        "mk12_20mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Mk 12 20mm Cannon",
    ),
    *_weapon_records(
        "mk15_torpedo_tubes",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "Mk 15 Torpedo Tubes (2x5)",
        required_ammo_types=(AmmoType.TORPEDO,),
        allowed_ammo_ids=("mk15_torpedo_warhead",),
        required_target_domains=(Domain.NAVAL,),
        expected_caliber_mm=533.4,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mk153_smaw",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "Mk 153 SMAW",
    ),
    *_weapon_records(
        "mk15_phalanx",
        WeaponCategory.CIWS,
        WeaponModeledRole.CLOSE_IN_DEFENSE,
        "Mk 15 Phalanx CIWS",
    ),
    *_weapon_records(
        "m203_40mm",
        WeaponCategory.GRENADE,
        WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER,
        "M203 40mm Grenade Launcher",
        required_ammo_types=(AmmoType.HEAT,),
        expected_caliber_mm=40.0,
    ),
    *_weapon_records(
        "mk38_5in38",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "5 inch/38 Mk 12 Gun",
    ),
    *_weapon_records(
        "mk41_vls",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.MULTI_ROLE_VLS,
        "Mk 41 VLS",
    ),
    *_weapon_records(
        "mk45_5inch",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "Mk 45 5-inch Gun",
    ),
    *_weapon_records(
        "ak130_130mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "AK-130 130mm Twin Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("ak130_he_frag",),
        expected_caliber_mm=130.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mk8_45in",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "4.5 inch Mk 8 Naval Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("45in_mk8_n20_he",),
        expected_caliber_mm=114.3,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "mk48_adcap",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "Mk 48 Torpedo Tubes",
    ),
    *_weapon_records(
        "project636_533mm_torpedo_tube",
        WeaponCategory.TORPEDO_TUBE,
        WeaponModeledRole.TORPEDO,
        "533mm Torpedo Tubes x6",
        required_ammo_types=(AmmoType.TORPEDO,),
        allowed_ammo_ids=("ugst_torpedo",),
        expected_caliber_mm=533.0,
        expected_guidance=GuidanceType.COMBINED,
    ),
    *_weapon_records(
        "mosin_nagant",
        WeaponCategory.RIFLE,
        WeaponModeledRole.BOLT_ACTION_RIFLE,
        "Mosin-Nagant M91/30 Rifle",
    ),
    *_weapon_records(
        "oto_melara_76mm",
        WeaponCategory.NAVAL_GUN,
        WeaponModeledRole.NAVAL_GUNFIRE,
        "Oto Melara 76mm/62 Super Rapid",
    ),
    *_weapon_records(
        "pike",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Pike",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("pike_thrust",),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "spear",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Kontarion Spear",
        "Viking Spears",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("spear_thrust",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "pilum",
        WeaponCategory.RIFLE,
        WeaponModeledRole.ANCIENT_PROJECTILE,
        "Pilum",
        "Pila",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("pilum_javelin",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=25.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "ppsh41",
        WeaponCategory.SUBMACHINE_GUN,
        WeaponModeledRole.SUBMACHINE_GUN,
        "PPSh-41 Submachine Gun",
    ),
    *_weapon_records(
        "r73",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "R-73 AA-11 Archer",
    ),
    *_weapon_records(
        "r77",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_TO_AIR_MISSILE,
        "R-77 AA-12 Adder",
    ),
    *_weapon_records(
        "rgd33",
        WeaponCategory.GRENADE,
        WeaponModeledRole.HAND_GRENADE,
        "Mk 2 Fragmentation Grenade",
        "RGD-33 Fragmentation Grenade",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("rgd33_charge",),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "harpoon_quad_launchers_x2",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "Harpoon Quad Launchers (x2)",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("rgm84_harpoon",),
        expected_caliber_mm=343.0,
        expected_guidance=GuidanceType.RADAR_ACTIVE,
    ),
    *_weapon_records(
        "mk141_harpoon_launchers_x4",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "Mk 141 Harpoon Quad Launchers (x4)",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("rgm84_harpoon",),
        expected_caliber_mm=343.0,
        expected_guidance=GuidanceType.RADAR_ACTIVE,
    ),
    *_weapon_records(
        "3m80_moskit",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_SHIP_MISSILE,
        "3M80 Moskit Launcher",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("3m80_moskit",),
        expected_caliber_mm=760.0,
        expected_guidance=GuidanceType.COMBINED,
    ),
    *_weapon_records(
        "rpg29_vampir",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "RPG-29",
    ),
    *_weapon_records(
        "rpg7",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "RPG-7",
    ),
    *_weapon_records(
        "matador_90mm",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "MATADOR 90mm Anti-Structure Munition",
        required_ammo_types=(AmmoType.HEAT,),
        expected_caliber_mm=90.0,
    ),
    *_weapon_records(
        "s68_57mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.AIR_DEFENSE_GUN,
        "2x S-68 57mm Autocannon",
    ),
    *_weapon_records(
        "sa6_3m9",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "2K12 Launcher",
    ),
    *_weapon_records(
        "sa7_strela2",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "9K32 Strela-2 MANPADS",
    ),
    *_weapon_records(
        "sarissa",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Sarissa",
    ),
    *_weapon_records(
        "sea_dart",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "Sea Dart SAM",
    ),
    *_weapon_records(
        "sea_wolf_sam",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.AIR_DEFENSE_MISSILE,
        "Sea Wolf SAM",
        required_ammo_types=(AmmoType.MISSILE,),
        allowed_ammo_ids=("sea_wolf_gws25",),
        expected_caliber_mm=180.0,
        expected_guidance=GuidanceType.COMMAND,
    ),
    *_weapon_records(
        "spg9_73mm",
        WeaponCategory.ROCKET_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "SPG-9 73mm Recoilless Rifle",
    ),
    *_weapon_records(
        "stielhandgranate",
        WeaponCategory.GRENADE,
        WeaponModeledRole.HAND_GRENADE,
        "Stielhandgranate 24",
    ),
    *_weapon_records(
        "sword_medieval",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Byzantine Marine Swords",
        "Crew Swords",
        "Greek Marine Swords",
        "Personal Weapons (Swords)",
        "Saif Sword",
        "Sword (Medieval)",
        "Viking Swords",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("sword_strike",),
        required_target_domains=(Domain.GROUND, Domain.NAVAL),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "viking_battle_axe",
        WeaponCategory.MELEE,
        WeaponModeledRole.MELEE,
        "Viking Battle Axes",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("axe_strike",),
        required_target_domains=(Domain.NAVAL,),
        expected_caliber_mm=0.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "tow2_atgm",
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponModeledRole.ANTI_ARMOR,
        "BGM-71 TOW-2 Launcher",
        "M901 TOW-2 Launcher",
    ),
    *_weapon_records(
        "type99_20mm",
        WeaponCategory.AUTOCANNON,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Type 99 Model 2 20mm Cannon (x2)",
    ),
    *_weapon_records(
        "type97_77mm_aircraft_mg",
        WeaponCategory.AIRCRAFT_GUN,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Type 97 7.7mm MG (x2)",
        required_ammo_types=(AmmoType.BALL,),
        allowed_ammo_ids=("77x56r_type97_ball",),
        required_target_domains=(Domain.GROUND, Domain.AERIAL),
        expected_caliber_mm=7.7,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "qf_2pdr_mk_viii",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "2-pdr Pom-Pom",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("2pdr_pompom_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=40.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "flak_c30_20mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "2cm FlaK C/30 AA Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("20mm_c30_hei",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "flak_m42_37mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "3.7cm FlaK M42 AA Gun",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("37mm_m42_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=37.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Bofors 40mm Quad Mount (x20)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("bofors_40mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=40.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Bofors 40mm Quad Mount (x8)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("bofors_40mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=40.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Bofors 40mm Twin Mount (x2)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("bofors_40mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=40.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "bofors_40mm_l60",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Bofors 40mm Twin Mount (x5)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("bofors_40mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=40.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Oerlikon 20mm (x46)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("oerlikon_20mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Oerlikon 20mm (x49)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("oerlikon_20mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Oerlikon 20mm (x6)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("oerlikon_20mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "oerlikon_20mm_mk4",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Oerlikon 20mm (x7)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("oerlikon_20mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=20.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "type96_25mm",
        WeaponCategory.AAA,
        WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN,
        "Type 96 25mm Triple Mount (x12)",
        required_ammo_types=(AmmoType.HE,),
        allowed_ammo_ids=("type96_25mm_he",),
        required_target_domains=(Domain.AERIAL,),
        expected_caliber_mm=25.0,
        expected_guidance=GuidanceType.NONE,
    ),
    *_weapon_records(
        "u5ts_115mm",
        WeaponCategory.CANNON,
        WeaponModeledRole.GROUND_DIRECT_FIRE,
        "U-5TS 115mm Smoothbore",
    ),
    *_weapon_records(
        "vickers_303",
        WeaponCategory.LIGHT_MG,
        WeaponModeledRole.AIRCRAFT_GUN,
        "Vickers .303 Synchronized MG (x2)",
    ),
    # Separately authored stores link to one same-unit attachment and never
    # construct a second launcher or independently credit another magazine.
    WeaponStoreMapping(
        equipment_name="Mk 20 Rockeye II CBU",
        ammo_id="mk20_rockeye",
        compatible_weapon_ids=(
            "bru36a_bomb_ejector_rack",
            "mau40a_bomb_ejector_rack",
        ),
        expected_ammo_type=AmmoType.CLUSTER,
    ),
    WeaponStoreMapping(
        equipment_name="Javelin Missile Round",
        ammo_id="javelin_warhead",
        compatible_weapon_ids=("javelin_clm",),
        expected_ammo_type=AmmoType.MISSILE,
    ),
    WeaponStoreMapping(
        equipment_name="9M133 Missile",
        ammo_id="kornet_warhead",
        compatible_weapon_ids=("kornet_9m133",),
        expected_ammo_type=AmmoType.MISSILE,
    ),
    WeaponStoreMapping(
        equipment_name="SA-7 Missile Round",
        ammo_id="sa7_warhead",
        compatible_weapon_ids=("sa7_strela2",),
        expected_ammo_type=AmmoType.MISSILE,
    ),
    WeaponStoreMapping(
        equipment_name="TOW-2 ATGM",
        ammo_id="tow2_warhead",
        compatible_weapon_ids=("tow2_atgm",),
        expected_ammo_type=AmmoType.HEAT,
    ),
    WeaponStoreMapping(
        equipment_name="G7e/T3 Torpedoes (x14)",
        ammo_id="g7e_warhead",
        compatible_weapon_ids=("g7e_torpedo",),
        expected_ammo_type=AmmoType.HE,
    ),
    WeaponStoreMapping(
        equipment_name="G7e/T3 Torpedoes (x22)",
        ammo_id="g7e_warhead",
        compatible_weapon_ids=("g7e_torpedo",),
        expected_ammo_type=AmmoType.HE,
    ),
    WeaponStoreMapping(
        equipment_name="Harpoon Block 1C ASCM (x8)",
        ammo_id="rgm84_harpoon",
        compatible_weapon_ids=("harpoon_quad_launchers_x2",),
        reference_kind=ReferenceKind.VARIANT,
        expected_ammo_type=AmmoType.MISSILE,
    ),
    WeaponStoreMapping(
        equipment_name="RGM-84 Harpoon Missiles (x16)",
        ammo_id="rgm84_harpoon",
        compatible_weapon_ids=("mk141_harpoon_launchers_x4",),
        expected_ammo_type=AmmoType.MISSILE,
    ),
    # Authored weapons with no honest live analogue remain transparent
    # non-runtime outcomes instead of acquiring an unrelated capability.
    *(
        WeaponNonRuntimeMapping(
            equipment_name=name,
            reason=reason,
            source=_PHASE_SOURCE,
        )
        for name, reason in (
            (
                "127mm Zuni Rocket Pod",
                "No cataloged Zuni launcher/ammunition interface exists.",
            ),
            (
                "5-inch HVAR Rockets",
                "No cataloged HVAR launcher/ammunition interface exists.",
            ),
            (
                "M260 2.75-inch Rocket Pod",
                "No cataloged 2.75-inch rocket-pod interface exists.",
            ),
            (
                "Depth Charges (x4)",
                "The WWI catalog has no depth-charge runtime definition.",
            ),
            (
                "Pattern 1908 Cavalry Sabre",
                "The WWI catalog has no live melee-weapon definition.",
            ),
            (
                "15cm sFH 18 Howitzer (x4)",
                "The WW2 catalog has no era-compatible 150 mm howitzer ammunition.",
            ),
            (
                "M2A1 105mm Howitzer (x4)",
                "The WW2 catalog has no era-compatible 105 mm howitzer ammunition.",
            ),
            (
                "Bronze Ram Prow",
                "Collision and naval-ram execution is not modeled as live ammunition.",
            ),
            (
                "Ram Prow",
                "Collision and naval-ram execution is not modeled as live ammunition.",
            ),
            (
                "Mk 143 Armored Box Launcher (Tomahawk)",
                "The cataloged strategic missile has no live magazine authority.",
            ),
            (
                "Luger P08 Pistol",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "M1911A1 .45 Pistol",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "Ruby M1914 Pistol",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "TT-33 Pistol",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "Walther P38 Pistol",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "Webley Mk V Revolver",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
            (
                "Webley Mk VI Revolver",
                "Individual sidearms are outside the current section-scale live loadout.",
            ),
        )
    ),
    *_sensor_records(
        "1s91_straight_flush",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        "1S91 Straight Flush Radar",
        modeled_max_range_m=75_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "aaq33_sniper",
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        "AN/AAQ-28 LITENING Targeting Pod",
        modeled_max_range_m=55_000.0,
        modeled_fov_deg=4.0,
    ),
    *_sensor_records(
        "active_sonar",
        SensorType.ACTIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        SensorModeledRole.ACTIVE_SONAR,
        "AN/BQQ-5 Sonar",
        "AN/SQQ-89 Sonar",
        "EDO 796 Hull Sonar",
        "MGK-335 Sonar",
        "MGK-400 Rubikon Sonar",
        "Type 184 Hull Sonar",
        "Type 2016 Hull Sonar",
        modeled_max_range_m=20_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "active_sonar",
        SensorType.ACTIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        SensorModeledRole.ACTIVE_SONAR,
        "QC/JK Sonar",
        "Type 123A ASDIC (Sonar)",
        modeled_max_range_m=2_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIR_SEARCH_RADAR,
        "AN/SPS-48E Radar",
        "AN/SPS-49 Air Search Radar",
        "AN/SPY-1D Radar",
        "AN/SPY-6 AMDR",
        "Type 965 Air Search Radar",
        modeled_max_range_m=400_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIR_SEARCH_RADAR,
        "EL/M-2218S 3D Air Search Radar",
        modeled_max_range_m=120_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIR_SEARCH_RADAR,
        "Type 967/968 Radar",
        modeled_max_range_m=100_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR,
        "SC-2 Air Search Radar",
        modeled_max_range_m=120_701.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR,
        "SK Air Search Radar",
        "SK-2 Air Search Radar",
        modeled_max_range_m=160_934.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIR_SEARCH_RADAR,
        "Type 21 Air Search Radar",
        modeled_max_range_m=100_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "airborne_maritime_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR,
        "Blue Fox Radar",
        modeled_max_range_m=46_300.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "airborne_maritime_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR,
        "Agave Maritime Search Radar",
        modeled_max_range_m=55_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "surface_navigation_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR,
        "MRK-50 Albatros Surface Navigation/Search Radar",
        modeled_max_range_m=20_372.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "apg68_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        "AN/APG-68 Radar",
        modeled_max_range_m=296_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "apg68_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        "AN/APG-70 Radar",
        modeled_max_range_m=128_748.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "apg68_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
        "AN/APG-73 Radar",
        "AN/APG-79 AESA Radar",
        modeled_max_range_m=150_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "awg9_fire_control_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        "AN/AWG-9 Fire Control Radar",
        modeled_max_range_m=185_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "j10a_pulse_doppler_fcr",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        "J-10A Pulse-Doppler Fire-Control Radar",
        modeled_max_range_m=100_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "n001_myech_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        "N001 Myech Radar",
        modeled_max_range_m=100_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "n019_sapfir_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
        "N019 Sapfir Radar",
        modeled_max_range_m=70_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "apg78_longbow_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
        "AN/APG-78 Longbow Radar",
        modeled_max_range_m=8_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "apq94_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
        "AN/APQ-94 Radar",
        modeled_max_range_m=30_000.0,
        modeled_fov_deg=60.0,
    ),
    *_sensor_records(
        "binoculars_ww1",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.VISUAL_OBSERVATION,
        "Barr & Stroud Rangefinder",
        "Field Binoculars",
        "No. 7 Dial Sight",
        "Panoramic Sight",
        "Zeiss Entfernungsmesser Rangefinder",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "esm_suite",
        SensorType.ESM,
        SignatureDomain.ELECTROMAGNETIC,
        SensorModeledRole.ELECTRONIC_SUPPORT,
        "AN/ALQ-218 EW Receiver",
        "AN/SLQ-32 EW Suite",
        "AN/SLQ-32(V)3 EW Suite",
        "Elisra NS-9003/9005 ESM",
        "WLR-8 ESM",
        modeled_max_range_m=200_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR,
        "AN/BPS-15 Radar",
        modeled_max_range_m=30_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
        "AN/SPS-67 Surface Search Radar",
        modeled_max_range_m=60_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.COASTAL_SURVEILLANCE_RADAR,
        "Coastal Surveillance Radar",
        modeled_max_range_m=60_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
        "FuMO 29 Radar",
        "FuMO 30 Radar",
        modeled_max_range_m=15_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
        "SG Surface Search Radar",
        modeled_max_range_m=24_140.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "ground_air_defense_fire_control_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        "30N6E Flap Lid Engagement Radar",
        "9S35 Fire Dome Fire Control Radar",
        "AN/MPQ-53 Patriot Multifunction Radar",
        "EL/M-2084 Multi-Mission Radar",
        modeled_max_range_m=60_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "low_altitude_air_search_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.AIR_SEARCH_RADAR,
        "76N6E Clam Shell Low-Altitude Radar",
        modeled_max_range_m=60_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "kurfs_fire_control_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
        "Ku-band Multi-Function RF Sensor (KuRFS)",
        modeled_max_range_m=10_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "naval_gun_fire_control_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
        "Mk 13 Fire Control Radar",
        "Mk 37 GFCS with Mk 4 Fire Control Radar",
        "Mk 37 GFCS with Mk 4 Fire Control Radar (x2)",
        "Mk 37 GFCS with Mk 25 Fire Control Radar",
        "Mk 38 GFCS with Mk 13 Fire Control Radar",
        modeled_max_range_m=32_004.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "hydrophone_ww2",
        SensorType.PASSIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        SensorModeledRole.PASSIVE_SONAR,
        "GHG Passive Hydrophone Array",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "hydrophone_ww1",
        SensorType.PASSIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        SensorModeledRole.PASSIVE_SONAR,
        "Passive Hydrophone",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.VISUAL_OBSERVATION,
        "Field Binoculars (Modern)",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.VISUAL_OBSERVATION,
        "Mk 1 Eyeball",
        "Naked Eye Observation",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
        "ARBS TV/Laser Spot Tracker",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=20.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
        "M65 TOW Sight",
        modeled_max_range_m=3_750.0,
        modeled_fov_deg=20.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
        "Aerial Observer Binoculars",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=120.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_VISUAL_SIGHT,
        "BPK-2-42 Sight",
        "TNPO-170A Driver Periscope",
        "TSh2B-32P Gunner Sight",
        "TSh2B-41U Gunner Sight",
        "Urdan Cupola Sight",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
        "Optical Reflex Gun Sight",
        modeled_max_range_m=2_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball_ww2",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
        "GM 2 Reflector Gunsight",
        "K-14 Gyroscopic Gunsight",
        "Revi 16B Reflector Gunsight",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball_ww2",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_VISUAL_SIGHT,
        "M1 Panoramic Telescope",
        "M55 Telescope",
        "No. 22c Mk 1 Telescopic Sight",
        "Rblf 36 Panoramic Sight",
        "TSh-16 Telescopic Sight",
        "TZF 12a Monocular Sight",
        "TZF 5f Telescope Sight",
        "TZF 9b Binocular Sight",
        "ZF 3x8 Telescopic Sight",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball_ww2",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT,
        "Norden M-9B Bombsight",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=10.0,
    ),
    *_sensor_records(
        "mk1_eyeball_ww2",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
        "Mk 38 Optical Fire Control Director (x2)",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "mk1_eyeball_ww2",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
        "Type 94 High-Angle Optical Director",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=30.0,
    ),
    *_sensor_records(
        "airborne_low_light_tv",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION,
        "ALLTV All-Light-Level TV",
        "AN/AVQ-19 Low-Light-Level TV",
        modeled_max_range_m=3_000.0,
        modeled_fov_deg=40.0,
    ),
    *_sensor_records(
        "1pn22m1_gunner_sight",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_NIGHT_SIGHT,
        "1PN22M1 Gunner Sight",
        modeled_max_range_m=400.0,
        modeled_fov_deg=6.0,
    ),
    *_sensor_records(
        "active_ir_sight",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_ACTIVE_IR_SIGHT,
        "TPN-3-49 Night Sight",
        modeled_max_range_m=800.0,
        modeled_fov_deg=6.0,
    ),
    *_sensor_records(
        "vvs2_commander_viewer",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.GROUND_NIGHT_SIGHT,
        "AN/VVS-2 Commander Viewer",
        modeled_max_range_m=1_000.0,
        modeled_fov_deg=10.0,
    ),
    *_sensor_records(
        "nvg",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.INDIVIDUAL_NIGHT_VISION,
        "AN/PVS-14 NVG",
        "AN/PVS-31 NVG",
        modeled_max_range_m=150.0,
        modeled_fov_deg=40.0,
    ),
    *_sensor_records(
        "starlight_scope",
        SensorType.NVG,
        SignatureDomain.VISUAL,
        SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION,
        "Starlight Scope",
        modeled_max_range_m=500.0,
        modeled_fov_deg=12.0,
    ),
    *_sensor_records(
        "ship_lookout",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.NAVAL_LOOKOUT,
        "Lookout Mast",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=360.0,
    ),
    *_sensor_records(
        "telescope_napoleonic",
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        SensorModeledRole.NAVAL_LOOKOUT,
        "Lookout Masthead",
        modeled_max_range_m=5_000.0,
        modeled_fov_deg=5.0,
    ),
    *_sensor_records(
        "thermal_sight",
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
        "AN/AAQ-14 LANTIRN Targeting Pod",
        "AN/AAQ-17 FLIR",
        "MMS Mast-Mounted Sight",
        "TADS/PNVS",
        modeled_max_range_m=4_000.0,
        modeled_fov_deg=40.0,
    ),
    *_sensor_records(
        "thermal_sight",
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        SensorModeledRole.GROUND_THERMAL_TARGETING,
        "AN/TAS-4 TOW Thermal Sight",
        "CITV Commander's Independent Thermal Viewer",
        "CIV Commander's Independent Viewer",
        "Commander's Independent Thermal Viewer",
        "Commander's Thermal Viewer",
        "Castor Thermal Sight",
        "EMES 15 Gunner Sight",
        "El-Op Gill Fire Control",
        "El-Op Knight Mark 4 Fire Control",
        "Elbit MARS Thermal Viewer",
        "Essa Thermal Sight",
        "GPS 2nd-Gen FLIR Gunner's Sight",
        "IBAS Thermal Sight",
        "Javelin CLU Thermal Sight",
        "LAV-25 Day/Night Thermal Sight",
        "PERI R17A2 Commander Sight",
        "TOW Day/Night Thermal Sight",
        "TOGS II Thermal Sight",
        modeled_max_range_m=4_000.0,
        modeled_fov_deg=40.0,
    ),
    *_sensor_records(
        "thermal_sight",
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        SensorModeledRole.AIRBORNE_SURFACE_THERMAL_SEARCH,
        "AN/DAS-1 EO/IR",
        "Dragon Eye EO/IR Camera",
        "MTS-B Targeting System",
        "ScanEagle EO/IR Gimbal",
        modeled_max_range_m=4_000.0,
        modeled_fov_deg=40.0,
    ),
    *_sensor_records(
        "thermal_sight",
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        SensorModeledRole.AIRBORNE_AIR_THERMAL_SEARCH,
        "OEPS-27 IRST",
        modeled_max_range_m=4_000.0,
        modeled_fov_deg=40.0,
    ),
    *(
        SensorNonRuntimeMapping(
            equipment_name=name,
            reason=(
                "Radar-warning alerting and identification are not connected "
                "to the production detection/target-sharing interface; no "
                "ship-scale ESM proxy is constructed."
            ),
            source=_PHASE_SOURCE,
        )
        for name in (
            "AN/ALR-46 RWR",
            "AN/ALR-56C RWR",
            "AN/ALR-56M RWR",
            "AN/ALR-67 RWR",
            "AN/ALR-69 RWR",
            "AN/APR-39 Radar Warning Receiver",
            "RKL800 RWR",
            "SPO-15 Beryoza RWR",
        )
    ),
    *(
        SensorNonRuntimeMapping(
            equipment_name=name,
            reason=(
                "This dedicated weapon-control channel is not attached as a "
                "generic search sensor: the current production detection "
                "interface cannot require cueing, track handoff, or a "
                "weapon-specific illumination state without overgranting "
                "independent surveillance capability."
            ),
            source=_PHASE_SOURCE,
        )
        for name in (
            "Type 909 Fire Control Radar",
            "EL/M-2221 STGR Fire Control Radar",
            "MR-184M Lev Fire Control Radar",
            "Type 910 Fire Control Radar",
        )
    ),
    SensorNonRuntimeMapping(
        equipment_name="AN/ASQ-176 OAS",
        reason=(
            "The offensive avionics system's navigation and weapon-delivery "
            "functions are outside the production target-detection boundary; "
            "it is not a thermal sensor and no independent search attachment "
            "is constructed."
        ),
        source=(
            "https://static.e-publishing.af.mil/production/1/minotafb/"
            "publication/afi21-101_afgscsup_minotafbsup/"
            "afi21-101_afgscsup_minotafbsup.pdf"
        ),
    ),
    SensorNonRuntimeMapping(
        equipment_name="Raduga-Sh Sight",
        reason=(
            "The Raduga-Sh is a weapon-guidance/aiming channel for the "
            "Shturm-V system; the production detection boundary cannot model "
            "its guidance coupling without granting an unrelated independent "
            "bombsight/search capability."
        ),
        source=("https://odin.t2com.army.mil/WEG/Asset/JRTC_VISMOD%3A_Mi-24_%28Hind%29_Attack_Helicopter"),
    ),
    SensorNonRuntimeMapping(
        equipment_name="AN/APQ-180 Strike Radar",
        reason=(
            "The APQ-180's ground-attack navigation, mapping, and fire-control "
            "functions do not fit the current generic detection interface; "
            "attaching a search-radar analogue would create an unsupported "
            "independent target-detection capability."
        ),
        source=_PHASE_SOURCE,
    ),
    *_sensor_records(
        "type271_naval_radar",
        SensorType.RADAR,
        SignatureDomain.RADAR,
        SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR,
        "Type 271 Surface Search Radar",
        modeled_max_range_m=15_000.0,
        modeled_fov_deg=360.0,
    ),
)

_DECLARED_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES = set(
    _SENSOR_FUNCTIONAL_SOURCE_OVERRIDES,
)
_LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_RECORDS = {
    record.equipment_name: record
    for record in EQUIPMENT_MAPPING_RECORDS
    if (
        isinstance(record, SensorAttachmentMapping)
        and record.equipment_name
        in _DECLARED_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES
    )
}
_LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES = set(
    _LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_RECORDS,
)
if (
    _DECLARED_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES
    != _LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES
):
    raise EquipmentMappingError(
        "Sensor functional-source overrides and live attachment records differ: "
        f"missing mappings={sorted(_DECLARED_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES - _LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES)!r}, "
        f"undeclared mappings={sorted(_LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES - _DECLARED_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES)!r}",
    )
_INVALID_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES = sorted(
    equipment_name
    for equipment_name, record
    in _LIVE_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_RECORDS.items()
    if (
        record.reference_kind is not ReferenceKind.FUNCTIONAL_ANALOGUE
        or record.source
        != _SENSOR_FUNCTIONAL_SOURCE_OVERRIDES[equipment_name]
    )
)
if _INVALID_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES:
    raise EquipmentMappingError(
        "Sensor functional-source overrides are not wired to matching "
        "functional-analogue records: "
        f"{_INVALID_SENSOR_FUNCTIONAL_SOURCE_OVERRIDE_NAMES!r}",
    )

_DECLARED_SYSTEM_COUNT_NAMES = set(_WEAPON_SYSTEM_COUNT_INDEX)
_MAPPED_SYSTEM_COUNT_NAMES = {
    record.equipment_name
    for record in EQUIPMENT_MAPPING_RECORDS
    if (
        isinstance(record, WeaponAttachmentMapping)
        and record.source_system_count > 1
    )
}
if _DECLARED_SYSTEM_COUNT_NAMES != _MAPPED_SYSTEM_COUNT_NAMES:
    raise EquipmentMappingError(
        "Weapon system-count declarations and live attachment records differ: "
        f"missing mappings={sorted(_DECLARED_SYSTEM_COUNT_NAMES - _MAPPED_SYSTEM_COUNT_NAMES)!r}, "
        f"undeclared mappings={sorted(_MAPPED_SYSTEM_COUNT_NAMES - _DECLARED_SYSTEM_COUNT_NAMES)!r}",
    )

EQUIPMENT_MAPPING_REGISTRY = EquipmentMappingRegistry(
    EQUIPMENT_MAPPING_RECORDS,
)

__all__ = [
    "EQUIPMENT_MAPPING_RECORDS",
    "EQUIPMENT_MAPPING_REGISTRY",
]
