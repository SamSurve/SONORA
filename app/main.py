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
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import get_job_manager
from app.api.v1.endpoints import router as api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.database import ensure_db_initialized
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

    # Initialize database schema upfront before any background worker or request
    ensure_db_initialized(settings.DB_PATH)

    # Initialize JobManager singleton (runs startup orphan reconciliation)
    get_job_manager()

    # Start Janitor cleanup background daemon thread
    janitor = JanitorDaemon(interval_seconds=settings.JANITOR_SWEEP_INTERVAL_SECONDS)
    janitor.start()
    app.state.janitor = janitor

    yield

    logger.info("Shutting down SONORA application background services...")
    # Stop background download workers and cancel pending futures
    get_job_manager().shutdown(wait=True)
    # Stop janitor daemon and wait for active cleanup sweep to finish
    janitor.stop()
    janitor.join(timeout=5.0)


app = FastAPI(
    title="SONORA — Modern Music Downloader",
    description="Production-grade, fast, clean, and free music downloading utility.",
    version="3.0.0",
    lifespan=lifespan,
)

# Configure CORS Middleware with explicit configurable origins
cors_origins = (
    settings.CORS_ORIGINS
    if isinstance(settings.CORS_ORIGINS, list)
    else [s.strip() for s in str(settings.CORS_ORIGINS).split(",") if s.strip()]
)
# Per W3C spec: wildcard origin cannot be combined with credentials
safe_credentials = (
    False if "*" in cors_origins else getattr(settings, "CORS_ALLOW_CREDENTIALS", False)
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=safe_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_robots_headers_middleware(request: Request, call_next: object) -> Response:
    """Injects defense-in-depth security headers and X-Robots-Tag directives on responses."""
    response: Response = await call_next(request)  # type: ignore[misc]

    if settings.ENABLE_SECURITY_HEADERS:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    # Strict noindex on private API endpoints, jobs, and file downloads
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/data/"):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"

    return response


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
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(
        content={
            "product": "SONORA",
            "message": "SONORA Music Downloader API active. Frontend index.html loading...",
        }
    )


@app.get("/healthz", tags=["Observability"])
async def liveness_probe() -> dict[str, str]:
    """Lightweight liveness probe for container orchestrators and load balancers."""
    return {"status": "ok", "app": "SONORA"}


@app.get("/readyz", tags=["Observability"])
async def readiness_probe() -> JSONResponse:
    """Readiness probe verifying database connectivity, storage, and worker health."""
    checks: dict[str, str] = {}
    is_ready = True

    # 1. Database check
    try:
        from app.db.database import get_db_read

        with get_db_read() as conn:
            cursor = conn.execute("SELECT 1;")
            cursor.fetchone()
        checks["database"] = "healthy"
    except Exception as e:
        logger.error("Readiness check database failure: %s", e)
        checks["database"] = "unhealthy"
        is_ready = False

    # 2. Storage check
    try:
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        settings.COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
        probe_file = settings.TEMP_DIR / ".readyz_probe"
        probe_file.write_text("probe", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        checks["storage"] = "healthy"
    except Exception as e:
        logger.error("Readiness check storage failure: %s", e)
        checks["storage"] = "unhealthy"
        is_ready = False

    # 3. Worker pool check
    try:
        manager = get_job_manager()
        checks["worker_pool"] = "healthy" if not manager.worker_pool._shutdown else "shutdown"
    except Exception:
        checks["worker_pool"] = "unknown"

    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        },
    )


@app.get("/robots.txt", response_class=Response, include_in_schema=False)
async def robots_txt() -> Response:
    """Serves robots.txt with clean search engine crawl instructions and sitemap link."""
    base_url = settings.CANONICAL_BASE_URL.rstrip("/")
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /static/\n"
        "Disallow: /api/\n"
        "Disallow: /data/\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/sitemap.xml", response_class=Response, include_in_schema=False)
async def sitemap_xml() -> Response:
    """Serves XML sitemap referencing only public canonical endpoints."""
    base_url = settings.CANONICAL_BASE_URL.rstrip("/")
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{base_url}/</loc>\n"
        "    <changefreq>weekly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/privacy</loc>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/terms</loc>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/privacy", response_model=None, include_in_schema=False)
async def privacy_policy() -> Response:
    """Serves Privacy Policy document or serves index SPA."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(content={"title": "Privacy Policy", "app": "SONORA"})


@app.get("/terms", response_model=None, include_in_schema=False)
async def terms_of_service() -> Response:
    """Serves Terms of Service document or serves index SPA."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(content={"title": "Terms of Service", "app": "SONORA"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Serves the SONORA browser favicon, preventing 404 logging."""
    favicon_path = static_dir / "img" / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=204)


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

