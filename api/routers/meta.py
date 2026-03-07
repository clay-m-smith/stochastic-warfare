"""Meta/health endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from api import __version__
from api.config import ApiSettings
from api.dependencies import get_settings
from api.scenarios import scan_scenarios, scan_units
from api.schemas import EraInfo, HealthResponse

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
