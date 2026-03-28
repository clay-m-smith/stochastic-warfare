"""Meta/health endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api import __version__
from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_db, get_settings
from api.scenarios import scan_scenarios, scan_units
from api.schemas import (
    CommanderInfo,
    EraInfo,
    HealthLiveResponse,
    HealthReadyResponse,
    HealthResponse,
    SchoolInfo,
    WeaponDetail,
    WeaponSummary,
)

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: ApiSettings = Depends(get_settings)) -> HealthResponse:
    data_dir = Path(settings.data_dir)
    scenarios = scan_scenarios(data_dir)
    units = scan_units(data_dir)
    return HealthResponse(
        status="ok",
        version=__version__,
        scenario_count=len(scenarios),
        unit_count=len(units),
    )


@router.get("/health/live", response_model=HealthLiveResponse)
async def health_live() -> HealthLiveResponse:
    """Liveness probe — instant 200, no external checks."""
    return HealthLiveResponse(status="ok")


@router.get("/health/ready", response_model=HealthReadyResponse)
async def health_ready(
    settings: ApiSettings = Depends(get_settings),
    db: Database = Depends(get_db),
) -> HealthReadyResponse:
    """Readiness probe — DB connectivity + cached scenario/unit counts."""
    db_ok = False
    try:
        await db.conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass
    scenarios = scan_scenarios(Path(settings.data_dir))
    units = scan_units(Path(settings.data_dir))
    return HealthReadyResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        scenario_count=len(scenarios),
        unit_count=len(units),
        db_connected=db_ok,
    )


@router.get("/meta/eras", response_model=list[EraInfo])
async def list_eras() -> list[EraInfo]:
    from stochastic_warfare.core.era import Era, get_era_config

    results = []
    for era in Era:
        cfg = get_era_config(era.value)
        results.append(EraInfo(
            name=era.name,
            value=era.value,
            disabled_modules=sorted(cfg.disabled_modules),
        ))
    return results


@router.get("/meta/doctrines", response_model=list[dict])
async def list_doctrines(settings: ApiSettings = Depends(get_settings)) -> list[dict]:
    import yaml

    data_dir = Path(settings.data_dir)
    doctrine_dir = data_dir / "doctrine"
    results: list[dict] = []
    if doctrine_dir.exists():
        for sub in sorted(doctrine_dir.iterdir()):
            if sub.is_dir():
                for yaml_file in sorted(sub.glob("*.yaml")):
                    try:
                        with open(yaml_file) as f:
                            cfg = yaml.safe_load(f)
                        results.append({
                            "name": yaml_file.stem,
                            "category": sub.name,
                            "display_name": cfg.get("name", yaml_file.stem) if isinstance(cfg, dict) else yaml_file.stem,
                        })
                    except Exception:
                        results.append({"name": yaml_file.stem, "category": sub.name})
    return results


@router.get("/meta/terrain-types", response_model=list[str])
async def list_terrain_types() -> list[str]:
    from stochastic_warfare.terrain.classification import LandCover

    return [member.name for member in LandCover]


# ---------------------------------------------------------------------------
# Phase 92: Schools, Commanders, Weapons metadata
# ---------------------------------------------------------------------------


@router.get("/meta/schools", response_model=list[SchoolInfo])
async def list_schools(settings: ApiSettings = Depends(get_settings)) -> list[SchoolInfo]:
    import yaml

    data_dir = Path(settings.data_dir)
    schools_dir = data_dir / "schools"
    results: list[SchoolInfo] = []
    if schools_dir.exists():
        for yaml_file in sorted(schools_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    cfg = yaml.safe_load(f)
                if not isinstance(cfg, dict):
                    continue
                results.append(SchoolInfo(
                    school_id=cfg.get("school_id", yaml_file.stem),
                    display_name=cfg.get("display_name", yaml_file.stem),
                    description=cfg.get("description", ""),
                    ooda_multiplier=float(cfg.get("ooda_multiplier", 1.0)),
                    risk_tolerance=str(cfg.get("risk_tolerance", "")),
                ))
            except Exception:
                results.append(SchoolInfo(school_id=yaml_file.stem))
    return results


@router.get("/meta/commanders", response_model=list[CommanderInfo])
async def list_commanders(settings: ApiSettings = Depends(get_settings)) -> list[CommanderInfo]:
    import yaml

    data_dir = Path(settings.data_dir)
    cmd_dir = data_dir / "commander_profiles"
    results: list[CommanderInfo] = []
    if cmd_dir.exists():
        for yaml_file in sorted(cmd_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    cfg = yaml.safe_load(f)
                if not isinstance(cfg, dict):
                    continue
                # Extract numeric traits
                traits: dict[str, float] = {}
                for key in ("aggression", "caution", "flexibility", "initiative",
                            "experience", "stress_tolerance", "decision_speed",
                            "risk_acceptance"):
                    val = cfg.get(key)
                    if val is not None:
                        traits[key] = float(val)
                results.append(CommanderInfo(
                    profile_id=cfg.get("profile_id", yaml_file.stem),
                    display_name=cfg.get("display_name", yaml_file.stem),
                    description=cfg.get("description", ""),
                    traits=traits,
                ))
            except Exception:
                results.append(CommanderInfo(profile_id=yaml_file.stem))
    return results


@router.get("/meta/weapons", response_model=list[WeaponSummary])
async def list_weapons(settings: ApiSettings = Depends(get_settings)) -> list[WeaponSummary]:
    import yaml

    data_dir = Path(settings.data_dir)
    results: list[WeaponSummary] = []
    # Scan both base weapons and era-specific weapons
    weapon_dirs = [data_dir / "weapons"]
    eras_dir = data_dir / "eras"
    if eras_dir.exists():
        for era in sorted(eras_dir.iterdir()):
            wpn = era / "weapons"
            if wpn.exists():
                weapon_dirs.append(wpn)
    for wdir in weapon_dirs:
        if not wdir.exists():
            continue
        for yaml_file in sorted(wdir.rglob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    cfg = yaml.safe_load(f)
                if not isinstance(cfg, dict):
                    continue
                results.append(WeaponSummary(
                    weapon_id=cfg.get("weapon_id", yaml_file.stem),
                    display_name=cfg.get("display_name", cfg.get("name", yaml_file.stem)),
                    category=cfg.get("category", yaml_file.parent.name),
                    max_range_m=float(cfg.get("max_range_m", 0)),
                    caliber_mm=float(cfg.get("caliber_mm", 0)),
                ))
            except Exception:
                results.append(WeaponSummary(weapon_id=yaml_file.stem))
    return results


@router.get("/meta/weapons/{weapon_id}", response_model=WeaponDetail)
async def get_weapon(
    weapon_id: str,
    settings: ApiSettings = Depends(get_settings),
) -> WeaponDetail:
    import yaml

    data_dir = Path(settings.data_dir)
    # Search both base and era weapon dirs
    search_dirs = [data_dir / "weapons"]
    eras_dir = data_dir / "eras"
    if eras_dir.exists():
        for era in sorted(eras_dir.iterdir()):
            wpn = era / "weapons"
            if wpn.exists():
                search_dirs.append(wpn)
    for wdir in search_dirs:
        if not wdir.exists():
            continue
        for yaml_file in wdir.rglob("*.yaml"):
            if yaml_file.stem == weapon_id:
                with open(yaml_file) as f:
                    cfg = yaml.safe_load(f)
                return WeaponDetail(
                    weapon_id=weapon_id,
                    definition=cfg if isinstance(cfg, dict) else {},
                )
    raise HTTPException(status_code=404, detail=f"Weapon '{weapon_id}' not found")
