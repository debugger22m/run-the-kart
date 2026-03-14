import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

from .routes import router
from .state import AppState
from .loop import LoopConfig

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

_LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "30"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: initialise shared state and auto-start the autonomous loop.
    Shutdown: gracefully stop the loop.
    """
    state = AppState()
    app.state.app = state

    # Auto-start — no lat/lng needed; centroid is derived from the fleet each cycle.
    config = LoopConfig(interval_seconds=_LOOP_INTERVAL)
    await state.loop.start(config)

    yield

    await state.loop.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Run The Kart — Fleet Management API",
        description="Autonomous food truck fleet management powered by Claude AI agents.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api/v1")
    return app
