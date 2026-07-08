from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (
    routes_alerts,
    routes_health,
    routes_orders,
    routes_screener,
    routes_specs,
    routes_strategies,
)
from .config import get_settings
from .db.session import init_db
from .ibkr.client import IBClient
from .ibkr.errors import DataUnavailable, IBKRUnavailable
from .screener.engine import ScreenerEngine
from .scheduler.runner import build_scheduler
from .strategies.registry import build_registry

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    init_db(settings)
    from .specs.seed import seed_default_specs

    seed_default_specs()
    client = IBClient(settings)
    registry = build_registry(settings)
    engine = ScreenerEngine(client, registry, settings)
    app.state.ib = client
    app.state.registry = registry
    app.state.engine = engine
    client.start()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler(engine, settings)
        scheduler.start()
        log.info("scheduler started (EOD arming scan + intraday confirmation poll)")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await client.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VIX Screener Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(IBKRUnavailable)
    async def ibkr_unavailable(_: Request, exc: IBKRUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(DataUnavailable)
    async def data_unavailable(_: Request, exc: DataUnavailable) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    prefix = "/api/v1"
    app.include_router(routes_health.router, prefix=prefix)
    app.include_router(routes_strategies.router, prefix=prefix)
    app.include_router(routes_screener.router, prefix=prefix)
    app.include_router(routes_orders.router, prefix=prefix)
    app.include_router(routes_alerts.router, prefix=prefix)
    app.include_router(routes_specs.router, prefix=prefix)
    return app


app = create_app()
