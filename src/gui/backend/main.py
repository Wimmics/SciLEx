"""FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .api import config as config_api
from .api import jobs as jobs_api

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Web GUI for SciLEx literature collection"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(config_api.router)
app.include_router(jobs_api.router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()
    print(f"Database initialized at {settings.db_path}")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.version
    }


@app.get("/api/health")
async def health():
    """API health check."""
    return {"status": "healthy"}
