"""Unit listing and detail endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from api.config import ApiSettings
from api.dependencies import get_settings
from api.scenarios import scan_units
from api.schemas import UnitDetail, UnitSummary

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=list[UnitSummary])
async def list_units(
    domain: str | None = Query(None),
    era: str | None = Query(None),
    category: str | None = Query(None),
    settings: ApiSettings = Depends(get_settings),
) -> list[UnitSummary]:
    data_dir = Path(settings.data_dir)
    raw = scan_units(data_dir)

    results = []
    for u in raw:
        if domain and u["domain"] != domain:
            continue
        if era and u["era"] != era:
            continue
        if category and u["category"] != category:
            continue
        results.append(UnitSummary(**{k: v for k, v in u.items() if k != "path"}))

    return results


@router.get("/{unit_type}", response_model=UnitDetail)
async def get_unit(unit_type: str, settings: ApiSettings = Depends(get_settings)) -> UnitDetail:
    data_dir = Path(settings.data_dir)
    raw = scan_units(data_dir)

    for u in raw:
        if u["unit_type"] == unit_type:
            import yaml
            with open(u["path"]) as f:
                defn = yaml.safe_load(f)
            return UnitDetail(unit_type=unit_type, definition=defn)

    raise HTTPException(status_code=404, detail=f"Unit '{unit_type}' not found")
