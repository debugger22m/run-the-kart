import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

from .routes import router
from .state import AppState

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared state on startup; clean up on shutdown."""
    app.state.app = AppState()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Run The Kart — Fleet Management API",
        description="Autonomous food truck fleet management powered by Claude AI agents.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api/v1")
    return app
