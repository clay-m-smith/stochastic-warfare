"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Mapping

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from api import __version__
from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_default_settings
from api.routers import analysis, analytics, meta, runs, scenarios, units

logger = logging.getLogger(__name__)


async def request_validation_error_response(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return serializable validation errors even for non-finite input."""
    errors: list[dict[str, Any]] = []
    for raw_error in exc.errors():
        error = {key: value for key, value in raw_error.items() if key != "input"}
        context = error.get("ctx")
        if isinstance(context, Mapping):
            error["ctx"] = {key: str(value) for key, value in context.items()}
        errors.append(error)
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors)},
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage database and run manager lifecycle."""
    from api.run_manager import RunManager

    settings: ApiSettings = app.state.settings
    paths = app.state.application_paths
    paths.prepare_output_directories()
    db = Database(os.fspath(paths.database_path))
    manager: RunManager | None = None
    try:
        await db.initialize()
        app.state.db = db
        manager = RunManager(
            db,
            data_dir=paths.catalog_root,
            max_concurrent=settings.max_concurrent_runs,
            max_stored_events=settings.max_stored_events,
            default_max_ticks=settings.default_max_ticks,
        )
        app.state.run_manager = manager
        yield
    finally:
        # Graceful shutdown must finish terminal persistence before DB close.
        try:
            if manager is not None:
                logger.info(
                    "Shutting down: cancelling %d active tasks",
                    len(manager._tasks),
                )
                await manager.shutdown(timeout=5.0)
        finally:
            await db.close()


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if settings is None:
        settings = get_default_settings()
    paths = settings.application_paths()
    # Retain the established settings surface as an absolute compatibility
    # view while ApplicationPaths remains the single resolver/owner.
    resolved_settings = settings.model_copy(
        update={
            "data_dir": str(paths.catalog_root),
            "db_path": os.fspath(paths.database_path),
            "frontend_dir": (
                str(paths.frontend_bundle)
                if paths.frontend_bundle is not None
                else None
            ),
            "artifact_dir": str(paths.artifact_root),
        },
    )

    app = FastAPI(
        title="Stochastic Warfare API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.application_paths = paths
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_response,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router, prefix="/api")
    app.include_router(scenarios.router, prefix="/api")
    app.include_router(units.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(analytics.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")

    # Serve built frontend if available (Phase 39c)
    frontend_dist = paths.frontend_bundle
    if frontend_dist is not None:
        from fastapi.staticfiles import StaticFiles

        index_html = frontend_dist / "index.html"

        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index_html)

    return app


# Default app instance for uvicorn
app = create_app()


def run() -> None:
    """Entry point for the stochastic-warfare-api script."""
    import uvicorn

    settings = get_default_settings()
    uvicorn.run("api.main:app", host=settings.host, port=settings.port, reload=False)
