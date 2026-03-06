"""FastAPI application factory and entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import __version__
from api.config import ApiSettings
from api.database import Database
from api.dependencies import get_settings
from api.routers import analysis, meta, runs, scenarios, units


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage database and run manager lifecycle."""
    from api.run_manager import RunManager

    settings = get_settings()
    db = Database(settings.db_path)
    await db.initialize()
    app.state.db = db
    app.state.run_manager = RunManager(
        db,
        data_dir=settings.data_dir,
        max_concurrent=settings.max_concurrent_runs,
        max_stored_events=settings.max_stored_events,
        default_max_ticks=settings.default_max_ticks,
    )
    yield
    await db.close()


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="Stochastic Warfare API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router, prefix="/api")
    app.include_router(scenarios.router, prefix="/api")
    app.include_router(units.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")

    return app


# Default app instance for uvicorn
app = create_app()


def run() -> None:
    """Entry point for the stochastic-warfare-api script."""
    import uvicorn

    settings = get_settings()
    uvicorn.run("api.main:app", host=settings.host, port=settings.port, reload=False)
