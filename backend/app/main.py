import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import bundles
from app.routers.bundles import _load_all_bundles, _load_all_analyses

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BUNDLES_DIR = DATA_DIR / "bundles"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "service": "support-bundle-analyzer"}

