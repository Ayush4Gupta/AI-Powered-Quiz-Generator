# main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.core.telemetry import init_telemetry
from app.core.rate_limit import RateLimitMiddleware
from app.core.errors import QuizError
from app.api import quizzes, sessions
from app.worker_manager import worker_manager
from app.models.weaviate_schema import ensure_schema_exists
import atexit

def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    log = structlog.get_logger()

    app = FastAPI(
        title=settings.app_name,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc"
    )
    init_telemetry(app)

    # CORS (adjust for prod)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Global error handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_detail = str(exc)
        log.error("unhandled_error",
                path=request.url.path,
                method=request.method,
                error=error_detail)
        
        if isinstance(exc, QuizError):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again later."}
        )

    @app.get("/livez", tags=["System Health"])
    async def liveness():
        return {"status": "alive"}

    @app.get("/readyz", tags=["System Health"])
    async def readiness():
        try:
            worker_healthy = worker_manager.is_healthy()
            return {
                "status": "ready",
                "celery_worker": "healthy" if worker_healthy else "unhealthy",
                "api_prefix": settings.api_prefix
            }
        except Exception as e:
            return {
                "status": "error",
                "celery_worker": "unknown",
                "error": str(e)
            }

    # Initialize Weaviate schema (non-blocking)
    try:
        schema_ready = ensure_schema_exists()
        if schema_ready:
            log.info("weaviate.schema.initialized")
        else:
            log.warning("weaviate.schema.init_failed", message="Schema initialization failed but continuing...")
    except Exception as e:
        log.error("weaviate.schema.error", error=str(e))

    # Start Celery worker automatically
    try:
        worker_manager.start_worker(concurrency=2)  # Start with 2 concurrent workers
        log.info("celery.worker.auto_started")
        
        # Register cleanup on app shutdown
        def cleanup_worker():
            try:
                worker_manager.stop_worker()
                log.info("celery.worker.shutdown_cleanup")
            except Exception as e:
                log.error("celery.worker.shutdown_error", error=str(e))
        
        atexit.register(cleanup_worker)
    except Exception as e:
        log.error("celery.worker.auto_start_failed", error=str(e))
        log.warning("celery.worker.manual_start_required", message="Please start worker manually using start-worker.bat")

    # Add middleware
    app.add_middleware(RateLimitMiddleware)

    # Mount routers with prefix
    app.include_router(quizzes.router, prefix=settings.api_prefix)
    app.include_router(sessions.router, prefix=settings.api_prefix)

    log.info("app.started")
    return app

# Create app instance for uvicorn
app = create_app()

