"""SONORA FastAPI Main Application Entrypoint.

Provides the FastAPI ASGI web application serving the modern SONORA single-page app,
mounting REST & SSE API routers, and managing background worker and janitor lifecycles.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import get_job_manager
from app.api.v1.endpoints import router as api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.engine.janitor import JanitorDaemon

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown lifecycles."""
    logger.info("Initializing SONORA application background services...")

    # Ensure storage directories exist
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    settings.COMPLETED_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize JobManager singleton (runs startup orphan reconciliation)
    get_job_manager()

    # Start Janitor cleanup background daemon thread
    janitor = JanitorDaemon(interval_seconds=300)
    janitor.start()
    app.state.janitor = janitor

    yield

    logger.info("Shutting down SONORA application background services...")
    # Stop janitor daemon
    janitor.stop()


app = FastAPI(
    title="SONORA — Modern Music Downloader",
    description="Production-grade, fast, clean, and free music downloading utility.",
    version="3.0.0",
    lifespan=lifespan,
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 Router
app.include_router(api_v1_router)

# Mount Static Assets Directory for SONORA SPA Frontend
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_model=None)
async def read_root() -> Response:
    """Serves the main SONORA Single-Page Web Application."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        from fastapi.responses import FileResponse

        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(
        content={
            "product": "SONORA",
            "message": "SONORA Music Downloader API active. Frontend index.html loading...",
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler ensuring zero unhandled stack trace leakage."""
    logger.error("Unhandled Exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "An unexpected server error occurred. Please try again later.",
        },
    )
