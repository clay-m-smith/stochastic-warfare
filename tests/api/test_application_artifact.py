"""API-extra proof against an installed no-Git wheel."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

from tests.artifact_support import (
    BuiltArtifacts,
    run_command,
)

pytest_plugins = ("tests.artifact_support",)


def test_installed_api_extra_uses_packaged_resources(
    built_artifacts: BuiltArtifacts,
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    site = tmp_path / "api-site"
    environment = dict(os.environ)
    environment["UV_OFFLINE"] = "1"
    run_command(
        [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--offline",
            "--no-deps",
            "--target",
            os.fspath(site),
            os.fspath(built_artifacts.wheel),
        ],
        cwd=tmp_path,
        environment=environment,
    )
    environment.update(
        {
            "PYTHONPATH": os.fspath(site),
            "XDG_STATE_HOME": os.fspath(tmp_path / "api-state"),
        },
    )
    result = run_command(
        [
            sys.executable,
            "-c",
            (
                "import asyncio\n"
                "import json\n"
                "from httpx import ASGITransport, AsyncClient\n"
                "from api.config import ApiSettings\n"
                "from api.main import create_app\n"
                "async def probe():\n"
                " app=create_app(ApiSettings(db_path=':memory:'))\n"
                " async with app.router.lifespan_context(app):\n"
                "  async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:\n"
                "   listing=await client.get('/api/scenarios')\n"
                "   detail=await client.get('/api/scenarios/73_easting')\n"
                "   health=await client.get('/api/health')\n"
                " print(json.dumps({'mode':app.state.application_paths.mode.value,'list':listing.status_code,'detail':detail.status_code,'health':health.status_code,'count':len(listing.json())}))\n"
                "asyncio.run(probe())"
            ),
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert json.loads(result.stdout) == {
        "mode": "package",
        "list": 200,
        "detail": 200,
        "health": 200,
        "count": 52,
    }
