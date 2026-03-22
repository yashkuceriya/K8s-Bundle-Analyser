import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _configure_logging() -> None:
    """Configure logging format based on LOG_FORMAT env var."""
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    if log_format == "json":
        fmt = '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, stream=sys.stdout, force=True)


_configure_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.persistence import try_init_db
from app.routers import bundles
from app.routers.bundles import _load_all_analyses, _load_all_bundles

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BUNDLES_DIR = DATA_DIR / "bundles"


def _validate_env() -> None:
    """Log warnings for missing optional configuration at startup."""
    checks = {
        "OPENROUTER_API_KEY": "AI analysis and chat features will be disabled",
        "OPENAI_API_KEY": "RAG embeddings will use default model",
        "DATABASE_URL": "Using default database connection; set DATABASE_URL for custom config",
    }
    for var, message in checks.items():
        if not os.getenv(var):
            logger.warning("%-20s not set — %s", var, message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    _validate_env()
    try_init_db()
    BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Data directory ready at %s", DATA_DIR)
    logger.info("Bundles directory ready at %s", BUNDLES_DIR)
    _load_all_bundles()
    _load_all_analyses()
    logger.info("Loaded persisted bundles and analyses")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Support Bundle Analyzer",
    description="Analyze Kubernetes Troubleshoot support bundles with heuristic and AI-powered analysis",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bundles.router)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "service": "support-bundle-analyzer"}


@app.get("/api/health", tags=["System"])
async def api_health_check():
    """API health check for monitoring."""
    return {"status": "ok"}
