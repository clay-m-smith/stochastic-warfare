"""Scenario listing and detail endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.config import ApiSettings
from api.dependencies import get_settings
from api.scenarios import resolve_scenario, scan_scenarios
from api.schemas import ScenarioDetail, ScenarioSummary, ValidateConfigRequest, ValidateConfigResponse

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _extract_summary(name: str, cfg: dict[str, Any]) -> ScenarioSummary:
    """Build ScenarioSummary from parsed YAML config."""
    raw_sides = cfg.get("sides", [])
    if isinstance(raw_sides, dict):
        sides = list(raw_sides.keys())
    elif isinstance(raw_sides, list):
        sides = [
            s.get("side", "?") if isinstance(s, dict) else str(s)
            for s in raw_sides
        ]
    else:
        sides = []

    terrain_cfg = cfg.get("terrain", {})
    terrain_type = ""
    if isinstance(terrain_cfg, dict):
        terrain_type = terrain_cfg.get("terrain_type", terrain_cfg.get("type", ""))

    return ScenarioSummary(
        name=name,
        display_name=cfg.get("name", name),
        era=cfg.get("era", "modern"),
        duration_hours=cfg.get("duration_hours", 0),
        sides=sides,
        terrain_type=terrain_type,
        has_ew="ew_config" in cfg,
        has_cbrn="cbrn_config" in cfg,
        has_escalation="escalation_config" in cfg,
        has_schools="schools_config" in cfg,
        has_space="space_config" in cfg,
        has_dew="dew_config" in cfg,
    )


@router.get("", response_model=list[ScenarioSummary])
async def list_scenarios(settings: ApiSettings = Depends(get_settings)) -> list[ScenarioSummary]:
    data_dir = Path(settings.data_dir)
    raw = scan_scenarios(data_dir)
    return [_extract_summary(s["name"], s["config"]) for s in raw]


@router.get("/{name}", response_model=ScenarioDetail)
async def get_scenario(name: str, settings: ApiSettings = Depends(get_settings)) -> ScenarioDetail:
    data_dir = Path(settings.data_dir)
    try:
        path = resolve_scenario(name, data_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{name}' not found")

    import yaml
    from stochastic_warfare.tools.serializers import serialize_to_dict

    with open(path) as f:
        config_dict = yaml.safe_load(f)

    # Build force summary from sides (supports list or dict format)
    force_summary: dict[str, Any] = {}
    raw_sides = config_dict.get("sides", [])
    if isinstance(raw_sides, dict):
        for side_name, side_data in raw_sides.items():
            units = side_data.get("units", []) if isinstance(side_data, dict) else []
            force_summary[side_name] = {
                "unit_count": sum(u.get("count", 1) for u in units),
                "unit_types": [u.get("unit_type", "?") for u in units],
            }
    elif isinstance(raw_sides, list):
        for side_cfg in raw_sides:
            if isinstance(side_cfg, dict):
                side_name = side_cfg.get("side", "unknown")
                units = side_cfg.get("units", [])
                force_summary[side_name] = {
                    "unit_count": sum(u.get("count", 1) for u in units),
                    "unit_types": [u.get("unit_type", "?") for u in units],
                }

    return ScenarioDetail(
        name=name,
        config=serialize_to_dict(config_dict),
        force_summary=force_summary,
    )


@router.post("/validate", response_model=ValidateConfigResponse)
async def validate_config(req: ValidateConfigRequest) -> ValidateConfigResponse:
    """Validate a scenario config dict against the campaign schema."""
    from pydantic import ValidationError
    from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

    try:
        CampaignScenarioConfig(**req.config)
        return ValidateConfigResponse(valid=True)
    except ValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidateConfigResponse(valid=False, errors=errors)
    except Exception as exc:
        return ValidateConfigResponse(valid=False, errors=[str(exc)])
