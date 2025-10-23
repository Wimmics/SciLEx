# Web GUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a web-based GUI for SciLEx that allows users to configure collections, monitor progress in real-time, and manage results through a browser interface.

**Architecture:** FastAPI backend serves REST API and WebSocket endpoints for real-time updates. React SPA frontend provides interactive configuration, progress monitoring, and results browsing. Backend runs collection jobs in background threads with progress callbacks. SQLite stores job history and logs. Bidirectional sync with existing YAML config files.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic V2, WebSocket, React 18, TypeScript, Vite, Ant Design, SQLite

---

## Phase 1: Backend Foundation

### Task 1: Create Backend Directory Structure

**Files:**
- Create: `src/gui/__init__.py`
- Create: `src/gui/__main__.py`
- Create: `src/gui/backend/__init__.py`
- Create: `src/gui/backend/main.py`
- Create: `src/gui/backend/config.py`
- Create: `src/gui/backend/database.py`

**Step 1: Create basic directory structure**

```bash
mkdir -p src/gui/backend
touch src/gui/__init__.py
touch src/gui/backend/__init__.py
```

**Step 2: Write main entry point**

Create `src/gui/__main__.py`:
```python
"""
SciLEx GUI entry point.
Run with: python -m src.gui
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("SCILEX_GUI_PORT", "8000"))
    host = os.getenv("SCILEX_GUI_HOST", "127.0.0.1")

    print(f"Starting SciLEx GUI on http://{host}:{port}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "src.gui.backend.main:app",
        host=host,
        port=port,
        reload=True
    )
```

**Step 3: Write application configuration**

Create `src/gui/backend/config.py`:
```python
"""Application configuration settings."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # App info
    app_name: str = "SciLEx GUI"
    version: str = "1.0.0"

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent.parent
    config_dir: Path = project_root / "src"
    output_dir: Path = project_root / "output"
    db_path: Path = Path.home() / ".scilex" / "gui.db"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_prefix = "SCILEX_"


settings = Settings()

# Ensure database directory exists
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
```

**Step 4: Write FastAPI app initialization**

Create `src/gui/backend/main.py`:
```python
"""FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

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
```

**Step 5: Test the server starts**

Run: `python -m src.gui`

Expected: Server starts on http://127.0.0.1:8000, visit in browser shows `{"status":"healthy",...}`

**Step 6: Commit**

```bash
git add src/gui/
git commit -m "feat(gui): initialize FastAPI backend structure

- Add entry point (__main__.py)
- Add FastAPI app with health endpoints
- Add configuration with Pydantic settings
- Add CORS middleware for frontend development"
```

---

### Task 2: Set Up Database with SQLAlchemy

**Files:**
- Create: `src/gui/backend/database.py`
- Create: `src/gui/backend/models/__init__.py`
- Create: `src/gui/backend/models/base.py`
- Create: `src/gui/backend/models/job.py`

**Step 1: Write database configuration**

Create `src/gui/backend/database.py`:
```python
"""Database configuration and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .config import settings

# SQLite connection string
DATABASE_URL = f"sqlite:///{settings.db_path}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False  # Set to True for SQL query debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session.
    Use with FastAPI Depends.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from .models.base import Base
    Base.metadata.create_all(bind=engine)
```

**Step 2: Write base model**

Create `src/gui/backend/models/__init__.py`:
```python
"""Database models."""
from .base import Base
from .job import Job, Log, ProgressSnapshot

__all__ = ["Base", "Job", "Log", "ProgressSnapshot"]
```

Create `src/gui/backend/models/base.py`:
```python
"""Base model for all database models."""
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
```

**Step 3: Write Job model**

Create `src/gui/backend/models/job.py`:
```python
"""Job-related database models."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from .base import Base


class Job(Base):
    """Collection job."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # queued/running/completed/failed/cancelled
    config_snapshot = Column(Text, nullable=False)  # JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    papers_found = Column(Integer, default=0)
    duplicates_removed = Column(Integer, default=0)
    citations_fetched = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    output_directory = Column(String, nullable=True)

    # Relationships
    logs = relationship("Log", back_populates="job", cascade="all, delete-orphan")
    progress_snapshots = relationship("ProgressSnapshot", back_populates="job", cascade="all, delete-orphan")


class Log(Base):
    """Job log entry."""

    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    level = Column(String, nullable=False)  # INFO/WARNING/ERROR
    api = Column(String, nullable=True)  # API name or None
    message = Column(Text, nullable=False)

    # Relationships
    job = relationship("Job", back_populates="logs")


class ProgressSnapshot(Base):
    """Job progress snapshot for persistence."""

    __tablename__ = "progress_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    phase = Column(String, nullable=False)  # collection/aggregation/citations/zotero
    api = Column(String, nullable=True)  # API name or None
    current_count = Column(Integer, nullable=True)
    total_count = Column(Integer, nullable=True)
    status = Column(String, nullable=True)  # running/completed/failed
    metadata = Column(Text, nullable=True)  # JSON

    # Relationships
    job = relationship("Job", back_populates="progress_snapshots")
```

**Step 4: Initialize database on startup**

Modify `src/gui/backend/main.py` to add startup event:
```python
from .database import init_db

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()
    print(f"Database initialized at {settings.db_path}")
```

**Step 5: Test database creation**

Run: `python -m src.gui`

Expected: Server starts, prints "Database initialized at...", file created at `~/.scilex/gui.db`

Verify: `ls -lh ~/.scilex/gui.db` shows file exists

**Step 6: Commit**

```bash
git add src/gui/backend/database.py src/gui/backend/models/
git commit -m "feat(gui): add SQLAlchemy database models

- Add database configuration with SQLite
- Add Job, Log, and ProgressSnapshot models
- Add database initialization on startup
- Create database at ~/.scilex/gui.db"
```

---

### Task 3: Create Pydantic Schemas for API Validation

**Files:**
- Create: `src/gui/backend/schemas/__init__.py`
- Create: `src/gui/backend/schemas/config.py`
- Create: `src/gui/backend/schemas/job.py`

**Step 1: Write config schemas**

Create `src/gui/backend/schemas/__init__.py`:
```python
"""Pydantic schemas for API validation."""
from .config import ScilexConfig, APIConfig
from .job import JobCreate, JobResponse, JobDetail, JobStatus

__all__ = [
    "ScilexConfig",
    "APIConfig",
    "JobCreate",
    "JobResponse",
    "JobDetail",
    "JobStatus",
]
```

Create `src/gui/backend/schemas/config.py`:
```python
"""Configuration schemas matching YAML structure."""
from typing import Optional
from pydantic import BaseModel, Field


class ScilexConfig(BaseModel):
    """Schema for scilex.config.yml"""

    # Search parameters
    keywords: list[list[str]] = Field(
        description="Dual keyword groups for search",
        example=[["machine learning", "deep learning"], ["nlp", "natural language"]]
    )
    years: list[int] = Field(
        description="Years to search",
        example=[2020, 2021, 2022, 2023, 2024]
    )
    apis: list[str] = Field(
        description="APIs to use for collection",
        example=["SemanticScholar", "OpenAlex", "IEEE"]
    )
    fields: list[str] = Field(
        default=["title", "abstract"],
        description="Fields to search in"
    )

    # Collection control
    collect: bool = Field(default=True, description="Enable collection phase")
    collect_name: str = Field(default="collection", description="Collection name")
    output_dir: str = Field(default="output", description="Output directory")
    email: Optional[str] = Field(default=None, description="Email for some APIs")

    # Aggregation options
    aggregate_txt_filter: bool = Field(default=True, description="Apply text filters")
    aggregate_get_citations: bool = Field(default=False, description="Fetch citations")
    aggregate_file: str = Field(default="aggregated_data.csv", description="Output filename")

    class Config:
        json_schema_extra = {
            "example": {
                "keywords": [["machine learning"], ["nlp"]],
                "years": [2023, 2024],
                "apis": ["SemanticScholar", "OpenAlex"],
                "fields": ["title", "abstract"],
                "collect": True,
                "collect_name": "ml_nlp_papers",
                "output_dir": "output",
                "aggregate_txt_filter": True,
                "aggregate_get_citations": False,
                "aggregate_file": "aggregated_data.csv"
            }
        }


class APIRateLimits(BaseModel):
    """Rate limits per API (requests per second)."""
    SemanticScholar: float = 1.0
    OpenAlex: float = 10.0
    Arxiv: float = 3.0
    IEEE: float = 10.0
    Elsevier: float = 6.0
    Springer: float = 1.5
    HAL: float = 10.0
    DBLP: float = 10.0
    GoogleScholar: float = 2.0
    Crossref: float = 3.0


class APIConfig(BaseModel):
    """Schema for api.config.yml (API keys masked for security)."""

    # Zotero
    zotero_api_key: Optional[str] = Field(default=None, description="Zotero API key")
    zotero_user_id: Optional[str] = Field(default=None, description="Zotero user ID")
    zotero_collection_id: Optional[str] = Field(default=None, description="Zotero collection ID")

    # API keys
    ieee_api_key: Optional[str] = Field(default=None, description="IEEE API key")
    elsevier_api_key: Optional[str] = Field(default=None, description="Elsevier API key")
    elsevier_inst_token: Optional[str] = Field(default=None, description="Elsevier institutional token")
    springer_api_key: Optional[str] = Field(default=None, description="Springer API key")
    semantic_scholar_api_key: Optional[str] = Field(default=None, description="Semantic Scholar API key")

    # Rate limits
    rate_limits: APIRateLimits = Field(default_factory=APIRateLimits)

    def mask_keys(self) -> "APIConfig":
        """Return copy with API keys masked."""
        masked = self.model_copy()
        for field in ["zotero_api_key", "ieee_api_key", "elsevier_api_key",
                      "elsevier_inst_token", "springer_api_key", "semantic_scholar_api_key"]:
            value = getattr(masked, field)
            if value:
                setattr(masked, field, "***" + value[-4:])
        return masked
```

**Step 2: Write job schemas**

Create `src/gui/backend/schemas/job.py`:
```python
"""Job-related schemas."""
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status enum."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCreate(BaseModel):
    """Schema for creating a new job."""
    name: Optional[str] = Field(default=None, description="Optional job name")
    config_override: Optional[dict] = Field(default=None, description="Optional config override")


class JobResponse(BaseModel):
    """Basic job response."""
    id: str
    name: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    papers_found: int

    class Config:
        from_attributes = True


class LogEntry(BaseModel):
    """Log entry."""
    timestamp: datetime
    level: str
    api: Optional[str]
    message: str

    class Config:
        from_attributes = True


class JobDetail(JobResponse):
    """Detailed job response with logs."""
    config_snapshot: str
    duplicates_removed: int
    citations_fetched: int
    error_message: Optional[str]
    output_directory: Optional[str]
    logs: list[LogEntry] = []

    class Config:
        from_attributes = True
```

**Step 3: Test schemas with example data**

Create a test script `test_schemas.py` in project root:
```python
"""Quick test of Pydantic schemas."""
from src.gui.backend.schemas import ScilexConfig, APIConfig, JobCreate

# Test ScilexConfig
config = ScilexConfig(
    keywords=[["machine learning"], ["nlp"]],
    years=[2023, 2024],
    apis=["SemanticScholar"],
    collect_name="test_collection"
)
print("ScilexConfig:", config.model_dump_json(indent=2))

# Test APIConfig with masking
api_config = APIConfig(
    ieee_api_key="secret_key_12345",
    semantic_scholar_api_key="another_secret_67890"
)
print("\nAPIConfig (masked):", api_config.mask_keys().model_dump_json(indent=2))

# Test JobCreate
job = JobCreate(name="Test Job")
print("\nJobCreate:", job.model_dump_json(indent=2))

print("\n✓ All schemas validated successfully")
```

Run: `python test_schemas.py`

Expected: All schemas print JSON output, ends with "✓ All schemas validated successfully"

**Step 4: Commit**

```bash
git add src/gui/backend/schemas/ test_schemas.py
git commit -m "feat(gui): add Pydantic schemas for validation

- Add ScilexConfig schema matching scilex.config.yml
- Add APIConfig schema with key masking for security
- Add Job schemas (create, response, detail)
- Add test script for schema validation"
```

---

### Task 4: Implement YAML Config Sync Service

**Files:**
- Create: `src/gui/backend/services/__init__.py`
- Create: `src/gui/backend/services/config_sync.py`

**Step 1: Write config sync service**

Create `src/gui/backend/services/__init__.py`:
```python
"""Business logic services."""
from .config_sync import ConfigSyncService

__all__ = ["ConfigSyncService"]
```

Create `src/gui/backend/services/config_sync.py`:
```python
"""Service for bidirectional YAML config synchronization."""
import yaml
from pathlib import Path
from typing import Optional

from ..config import settings
from ..schemas.config import ScilexConfig, APIConfig


class ConfigSyncService:
    """Manages reading/writing YAML configuration files."""

    def __init__(self):
        self.scilex_config_path = settings.config_dir / "scilex.config.yml"
        self.api_config_path = settings.config_dir / "api.config.yml"

    def read_scilex_config(self) -> Optional[ScilexConfig]:
        """Read scilex.config.yml and return validated schema."""
        if not self.scilex_config_path.exists():
            return None

        with open(self.scilex_config_path, 'r') as f:
            data = yaml.safe_load(f)

        return ScilexConfig(**data)

    def write_scilex_config(self, config: ScilexConfig) -> None:
        """Write ScilexConfig to scilex.config.yml atomically."""
        # Convert to dict
        data = config.model_dump(exclude_none=True)

        # Write to temp file first (atomic)
        temp_path = self.scilex_config_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        # Rename (atomic on POSIX)
        temp_path.rename(self.scilex_config_path)

    def read_api_config(self) -> Optional[APIConfig]:
        """Read api.config.yml and return validated schema."""
        if not self.api_config_path.exists():
            return None

        with open(self.api_config_path, 'r') as f:
            data = yaml.safe_load(f)

        return APIConfig(**data)

    def write_api_config(self, config: APIConfig) -> None:
        """Write APIConfig to api.config.yml atomically."""
        # Convert to dict
        data = config.model_dump(exclude_none=True)

        # Write to temp file first (atomic)
        temp_path = self.api_config_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        # Rename (atomic on POSIX)
        temp_path.rename(self.api_config_path)

    def config_exists(self, config_type: str) -> bool:
        """Check if config file exists."""
        if config_type == "scilex":
            return self.scilex_config_path.exists()
        elif config_type == "api":
            return self.api_config_path.exists()
        return False
```

**Step 2: Test config sync service**

Create test script `test_config_sync.py`:
```python
"""Test config sync service."""
from src.gui.backend.services import ConfigSyncService
from src.gui.backend.schemas import ScilexConfig

service = ConfigSyncService()

# Check if configs exist
print(f"scilex.config.yml exists: {service.config_exists('scilex')}")
print(f"api.config.yml exists: {service.config_exists('api')}")

# Try reading scilex config
if service.config_exists('scilex'):
    config = service.read_scilex_config()
    if config:
        print(f"\nRead scilex.config.yml:")
        print(f"  Keywords: {config.keywords}")
        print(f"  Years: {config.years}")
        print(f"  APIs: {config.apis}")
        print(f"  Collection name: {config.collect_name}")
else:
    print("\nNo scilex.config.yml found (expected if not configured yet)")

# Try reading API config
if service.config_exists('api'):
    api_config = service.read_api_config()
    if api_config:
        print(f"\nRead api.config.yml (masked):")
        masked = api_config.mask_keys()
        print(f"  IEEE key: {masked.ieee_api_key}")
        print(f"  Semantic Scholar key: {masked.semantic_scholar_api_key}")
else:
    print("\nNo api.config.yml found (expected if not configured yet)")

print("\n✓ Config sync service test complete")
```

Run: `python test_config_sync.py`

Expected: Prints whether configs exist, reads them if present, shows "✓ Config sync service test complete"

**Step 3: Commit**

```bash
git add src/gui/backend/services/ test_config_sync.py
git commit -m "feat(gui): implement YAML config sync service

- Add ConfigSyncService for bidirectional YAML sync
- Support atomic writes (temp file + rename)
- Add read/write methods for both config files
- Add test script for config service"
```

---

### Task 5: Create Config Management API Endpoints

**Files:**
- Create: `src/gui/backend/api/__init__.py`
- Create: `src/gui/backend/api/config.py`
- Modify: `src/gui/backend/main.py`

**Step 1: Write config API endpoints**

Create `src/gui/backend/api/__init__.py`:
```python
"""API endpoints."""
```

Create `src/gui/backend/api/config.py`:
```python
"""Configuration management endpoints."""
from fastapi import APIRouter, HTTPException

from ..schemas.config import ScilexConfig, APIConfig
from ..services.config_sync import ConfigSyncService

router = APIRouter(prefix="/api/config", tags=["config"])
config_service = ConfigSyncService()


@router.get("/scilex", response_model=ScilexConfig)
async def get_scilex_config():
    """Get current scilex.config.yml"""
    config = config_service.read_scilex_config()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration file not found")
    return config


@router.put("/scilex")
async def update_scilex_config(config: ScilexConfig):
    """Update scilex.config.yml"""
    try:
        config_service.write_scilex_config(config)
        return {"status": "success", "message": "Configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/api", response_model=APIConfig)
async def get_api_config():
    """Get current api.config.yml (with keys masked)"""
    config = config_service.read_api_config()
    if not config:
        raise HTTPException(status_code=404, detail="API configuration file not found")
    return config.mask_keys()


@router.put("/api")
async def update_api_config(config: APIConfig):
    """Update api.config.yml"""
    try:
        config_service.write_api_config(config)
        return {"status": "success", "message": "API configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save API configuration: {str(e)}")


@router.get("/exists")
async def check_configs_exist():
    """Check which config files exist."""
    return {
        "scilex": config_service.config_exists("scilex"),
        "api": config_service.config_exists("api")
    }
```

**Step 2: Register router in main app**

Modify `src/gui/backend/main.py` to include router:
```python
from .api import config as config_api

# Add after app initialization
app.include_router(config_api.router)
```

**Step 3: Test endpoints**

Run server: `python -m src.gui`

Test with curl:
```bash
# Check which configs exist
curl http://localhost:8000/api/config/exists

# Try to get scilex config (may return 404 if not configured)
curl http://localhost:8000/api/config/scilex
```

Expected: `/exists` returns `{"scilex": true/false, "api": true/false}`

**Step 4: Commit**

```bash
git add src/gui/backend/api/
git commit -m "feat(gui): add config management API endpoints

- Add GET /api/config/scilex endpoint
- Add PUT /api/config/scilex endpoint
- Add GET /api/config/api endpoint (masked keys)
- Add PUT /api/config/api endpoint
- Add GET /api/config/exists to check config presence"
```

---

## Phase 2: Job Execution System

### Task 6: Create Job Management Service

**Files:**
- Create: `src/gui/backend/services/job_manager.py`
- Modify: `src/gui/backend/services/__init__.py`

**Step 1: Write job manager service**

Create `src/gui/backend/services/job_manager.py`:
```python
"""Job management service."""
import json
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session

from ..models.job import Job, Log
from ..schemas.job import JobCreate, JobStatus


class JobManager:
    """Manages job lifecycle and database operations."""

    def create_job(self, db: Session, job_data: JobCreate, config_snapshot: dict) -> Job:
        """Create a new job entry."""
        job_id = str(uuid.uuid4())

        job = Job(
            id=job_id,
            name=job_data.name or f"Collection {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            status=JobStatus.QUEUED.value,
            config_snapshot=json.dumps(config_snapshot),
            created_at=datetime.utcnow()
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return job

    def get_job(self, db: Session, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return db.query(Job).filter(Job.id == job_id).first()

    def list_jobs(
        self,
        db: Session,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[Job], int]:
        """List jobs with optional filtering."""
        query = db.query(Job)

        if status:
            query = query.filter(Job.status == status)

        total = query.count()
        jobs = query.order_by(Job.created_at.desc()).limit(limit).offset(offset).all()

        return jobs, total

    def update_job_status(
        self,
        db: Session,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None
    ) -> Optional[Job]:
        """Update job status."""
        job = self.get_job(db, job_id)
        if not job:
            return None

        job.status = status.value

        if status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.utcnow()

        if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = datetime.utcnow()
            if job.started_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                job.duration_seconds = int(duration)

        if error_message:
            job.error_message = error_message

        db.commit()
        db.refresh(job)

        return job

    def add_log(
        self,
        db: Session,
        job_id: str,
        level: str,
        message: str,
        api: Optional[str] = None
    ) -> Log:
        """Add a log entry for a job."""
        log = Log(
            job_id=job_id,
            level=level,
            message=message,
            api=api,
            timestamp=datetime.utcnow()
        )

        db.add(log)
        db.commit()
        db.refresh(log)

        return log

    def update_job_stats(
        self,
        db: Session,
        job_id: str,
        papers_found: Optional[int] = None,
        duplicates_removed: Optional[int] = None,
        citations_fetched: Optional[int] = None,
        output_directory: Optional[str] = None
    ) -> Optional[Job]:
        """Update job statistics."""
        job = self.get_job(db, job_id)
        if not job:
            return None

        if papers_found is not None:
            job.papers_found = papers_found
        if duplicates_removed is not None:
            job.duplicates_removed = duplicates_removed
        if citations_fetched is not None:
            job.citations_fetched = citations_fetched
        if output_directory is not None:
            job.output_directory = output_directory

        db.commit()
        db.refresh(job)

        return job
```

**Step 2: Update services __init__**

Modify `src/gui/backend/services/__init__.py`:
```python
"""Business logic services."""
from .config_sync import ConfigSyncService
from .job_manager import JobManager

__all__ = ["ConfigSyncService", "JobManager"]
```

**Step 3: Create test for job manager**

Create `test_job_manager.py`:
```python
"""Test job manager service."""
from src.gui.backend.database import SessionLocal, init_db
from src.gui.backend.services import JobManager
from src.gui.backend.schemas import JobCreate, JobStatus

# Initialize database
init_db()

# Create session
db = SessionLocal()
manager = JobManager()

# Test 1: Create job
print("Test 1: Creating job...")
job_data = JobCreate(name="Test Collection")
config = {"keywords": [["test"]], "years": [2024], "apis": ["SemanticScholar"]}
job = manager.create_job(db, job_data, config)
print(f"  ✓ Created job: {job.id}, status={job.status}")

# Test 2: Get job
print("\nTest 2: Getting job...")
retrieved_job = manager.get_job(db, job.id)
assert retrieved_job is not None
print(f"  ✓ Retrieved job: {retrieved_job.name}")

# Test 3: Update status
print("\nTest 3: Updating job status...")
manager.update_job_status(db, job.id, JobStatus.RUNNING)
running_job = manager.get_job(db, job.id)
assert running_job.status == JobStatus.RUNNING.value
assert running_job.started_at is not None
print(f"  ✓ Job status: {running_job.status}, started_at={running_job.started_at}")

# Test 4: Add log
print("\nTest 4: Adding log...")
log = manager.add_log(db, job.id, "INFO", "Test log message", api="SemanticScholar")
print(f"  ✓ Added log: {log.message}")

# Test 5: Update stats
print("\nTest 5: Updating statistics...")
manager.update_job_stats(db, job.id, papers_found=150, duplicates_removed=10)
updated_job = manager.get_job(db, job.id)
print(f"  ✓ Stats: papers={updated_job.papers_found}, duplicates={updated_job.duplicates_removed}")

# Test 6: Complete job
print("\nTest 6: Completing job...")
manager.update_job_status(db, job.id, JobStatus.COMPLETED)
completed_job = manager.get_job(db, job.id)
assert completed_job.status == JobStatus.COMPLETED.value
assert completed_job.completed_at is not None
print(f"  ✓ Job completed: duration={completed_job.duration_seconds}s")

# Test 7: List jobs
print("\nTest 7: Listing jobs...")
jobs, total = manager.list_jobs(db, limit=10)
print(f"  ✓ Found {total} total jobs, showing {len(jobs)}")

db.close()
print("\n✓ All job manager tests passed!")
```

Run: `python test_job_manager.py`

Expected: All 7 tests pass, prints "✓ All job manager tests passed!"

**Step 4: Commit**

```bash
git add src/gui/backend/services/job_manager.py test_job_manager.py
git commit -m "feat(gui): implement job manager service

- Add JobManager for job lifecycle management
- Support create, get, list, update operations
- Add job status tracking and timestamps
- Add log entry creation
- Add statistics updates
- Include comprehensive test suite"
```

---

### Task 7: Create Job API Endpoints

**Files:**
- Create: `src/gui/backend/api/jobs.py`
- Modify: `src/gui/backend/main.py`

**Step 1: Write jobs API endpoints**

Create `src/gui/backend/api/jobs.py`:
```python
"""Job management endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.job import JobCreate, JobResponse, JobDetail, JobStatus
from ..services.job_manager import JobManager
from ..services.config_sync import ConfigSyncService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
job_manager = JobManager()
config_service = ConfigSyncService()


@router.post("/start", response_model=dict)
async def start_job(job_data: JobCreate, db: Session = Depends(get_db)):
    """Start a new collection job."""
    # Validate configuration exists
    config = config_service.read_scilex_config()
    if not config:
        raise HTTPException(status_code=400, detail="No configuration found. Please configure collection first.")

    # Create job
    config_snapshot = config.model_dump()
    if job_data.config_override:
        config_snapshot.update(job_data.config_override)

    job = job_manager.create_job(db, job_data, config_snapshot)

    # Add initial log
    job_manager.add_log(db, job.id, "INFO", "Job created and queued")

    # TODO: Actually start the background job
    # For now, just return the job ID

    return {
        "job_id": job.id,
        "status": "queued",
        "message": "Job created successfully"
    }


@router.get("", response_model=dict)
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List jobs with optional filtering."""
    jobs, total = job_manager.list_jobs(db, status=status, limit=limit, offset=offset)

    return {
        "jobs": [JobResponse.model_validate(job) for job in jobs],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get detailed job information."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobDetail.model_validate(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """Cancel a running job."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status: {job.status}")

    # TODO: Actually cancel the running job
    job_manager.update_job_status(db, job_id, JobStatus.CANCELLED)
    job_manager.add_log(db, job_id, "INFO", "Job cancelled by user")

    return {"status": "success", "message": "Job cancelled"}


@router.delete("/{job_id}")
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and all associated logs."""
    job = job_manager.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.delete(job)
    db.commit()

    return {"status": "success", "message": "Job deleted"}
```

**Step 2: Register router**

Modify `src/gui/backend/main.py`:
```python
from .api import config as config_api
from .api import jobs as jobs_api

# Add after existing router
app.include_router(jobs_api.router)
```

**Step 3: Test job endpoints**

Run server: `python -m src.gui`

Test with curl (assuming you have a config file):
```bash
# Start a job
curl -X POST http://localhost:8000/api/jobs/start \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Collection"}'

# List jobs
curl http://localhost:8000/api/jobs

# Get job detail (replace {job_id} with actual ID from previous response)
curl http://localhost:8000/api/jobs/{job_id}
```

Expected: Can create, list, and get job details

**Step 4: Commit**

```bash
git add src/gui/backend/api/jobs.py
git commit -m "feat(gui): add job management API endpoints

- Add POST /api/jobs/start to create jobs
- Add GET /api/jobs to list jobs with filtering
- Add GET /api/jobs/{id} for job details
- Add POST /api/jobs/{id}/cancel to cancel jobs
- Add DELETE /api/jobs/{id} to delete jobs"
```

---

### Task 8: Implement Background Job Runner with Progress Callbacks

**Files:**
- Create: `src/gui/backend/services/job_runner.py`
- Modify: `src/gui/backend/services/__init__.py`

**Step 1: Write job runner service**

Create `src/gui/backend/services/job_runner.py`:
```python
"""Background job execution with progress tracking."""
import threading
import json
from typing import Callable, Optional, Dict, Any
from datetime import datetime

from ..database import SessionLocal
from ..schemas.job import JobStatus
from .job_manager import JobManager


class ProgressCallback:
    """Progress callback handler for collection scripts."""

    def __init__(self, job_id: str, on_progress: Optional[Callable] = None):
        self.job_id = job_id
        self.on_progress = on_progress
        self.db = SessionLocal()
        self.job_manager = JobManager()

    def __call__(self, event_type: str, data: Dict[str, Any]):
        """Handle progress event."""
        # Add log entry
        level = "INFO"
        api = data.get("api")

        if event_type == "job_started":
            message = f"Started {data.get('phase', 'job')}"
        elif event_type == "progress_update":
            current = data.get("current", 0)
            total = data.get("total", 0)
            message = f"Progress: {current}/{total}"
            if "message" in data:
                message = data["message"]
        elif event_type == "phase_complete":
            message = f"Completed {data.get('phase', 'phase')}"
        elif event_type == "job_failed":
            level = "ERROR"
            message = f"Job failed: {data.get('error', 'Unknown error')}"
        else:
            message = json.dumps(data)

        self.job_manager.add_log(self.db, self.job_id, level, message, api=api)

        # Call WebSocket broadcast if provided
        if self.on_progress:
            self.on_progress(self.job_id, event_type, data)

    def close(self):
        """Close database session."""
        self.db.close()


class JobRunner:
    """Manages background job execution."""

    def __init__(self):
        self.active_jobs: Dict[str, threading.Thread] = {}
        self.job_manager = JobManager()

    def start_job(
        self,
        job_id: str,
        config: dict,
        on_progress: Optional[Callable] = None
    ):
        """Start a job in a background thread."""
        if job_id in self.active_jobs:
            raise ValueError(f"Job {job_id} is already running")

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, config, on_progress),
            daemon=True
        )
        thread.start()
        self.active_jobs[job_id] = thread

    def _run_job(self, job_id: str, config: dict, on_progress: Optional[Callable]):
        """Run job in background thread."""
        db = SessionLocal()
        callback = ProgressCallback(job_id, on_progress)

        try:
            # Update status to running
            self.job_manager.update_job_status(db, job_id, JobStatus.RUNNING)

            callback("job_started", {"phase": "collection"})

            # TODO: Import and call actual collection scripts
            # For now, simulate with sleep and fake progress
            import time
            for i in range(5):
                time.sleep(1)
                callback("progress_update", {
                    "api": "SemanticScholar",
                    "current": i + 1,
                    "total": 5,
                    "message": f"Simulating collection step {i + 1}/5"
                })

            callback("phase_complete", {"phase": "collection"})

            # Update final status
            self.job_manager.update_job_status(db, job_id, JobStatus.COMPLETED)
            self.job_manager.update_job_stats(db, job_id, papers_found=100)

        except Exception as e:
            # Handle errors
            self.job_manager.update_job_status(
                db, job_id, JobStatus.FAILED, error_message=str(e)
            )
            callback("job_failed", {"error": str(e)})

        finally:
            callback.close()
            db.close()
            # Remove from active jobs
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]

    def is_job_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        return job_id in self.active_jobs


# Global instance
job_runner = JobRunner()
```

**Step 2: Update services init**

Modify `src/gui/backend/services/__init__.py`:
```python
"""Business logic services."""
from .config_sync import ConfigSyncService
from .job_manager import JobManager
from .job_runner import JobRunner, job_runner

__all__ = ["ConfigSyncService", "JobManager", "JobRunner", "job_runner"]
```

**Step 3: Integrate job runner with jobs API**

Modify `src/gui/backend/api/jobs.py` to actually start jobs:
```python
from ..services.job_runner import job_runner

# In start_job endpoint, after creating the job:
@router.post("/start", response_model=dict)
async def start_job(job_data: JobCreate, db: Session = Depends(get_db)):
    """Start a new collection job."""
    # ... existing validation ...

    job = job_manager.create_job(db, job_data, config_snapshot)
    job_manager.add_log(db, job.id, "INFO", "Job created and queued")

    # Start the background job
    job_runner.start_job(job.id, config_snapshot)

    return {
        "job_id": job.id,
        "status": "queued",
        "message": "Job started successfully"
    }
```

**Step 4: Test job runner**

Create `test_job_runner.py`:
```python
"""Test job runner with simulated collection."""
import time
from src.gui.backend.database import SessionLocal, init_db
from src.gui.backend.services import JobManager, job_runner
from src.gui.backend.schemas import JobCreate

# Initialize
init_db()
db = SessionLocal()
manager = JobManager()

# Create job
print("Creating test job...")
job_data = JobCreate(name="Background Test")
config = {"keywords": [["test"]], "years": [2024], "apis": ["SemanticScholar"]}
job = manager.create_job(db, job_data, config)
print(f"Created job: {job.id}")

# Start job in background
print("\nStarting background job...")
job_runner.start_job(job.id, config)

# Wait and check progress
print("Waiting for job to complete...")
for _ in range(10):
    time.sleep(1)
    job = manager.get_job(db, job.id)
    print(f"  Status: {job.status}, Papers: {job.papers_found}")

    if job.status in ["completed", "failed", "cancelled"]:
        break

# Get logs
print("\nJob logs:")
for log in job.logs[-10:]:
    print(f"  [{log.level}] {log.message}")

print(f"\n✓ Job finished with status: {job.status}")
db.close()
```

Run: `python test_job_runner.py`

Expected: Job runs for ~5 seconds, shows progress updates, completes successfully

**Step 5: Commit**

```bash
git add src/gui/backend/services/job_runner.py test_job_runner.py
git commit -m "feat(gui): implement background job runner

- Add JobRunner for background thread execution
- Add ProgressCallback for progress tracking
- Support callback-based progress reporting
- Add simulated collection for testing
- Integrate with job API endpoints
- Include test for background execution"
```

---

## Phase 3: WebSocket Real-Time Updates

### Task 9: Implement WebSocket Manager and Endpoints

**Files:**
- Create: `src/gui/backend/websocket/__init__.py`
- Create: `src/gui/backend/websocket/manager.py`
- Create: `src/gui/backend/websocket/handlers.py`
- Modify: `src/gui/backend/main.py`

**Step 1: Write WebSocket connection manager**

Create `src/gui/backend/websocket/__init__.py`:
```python
"""WebSocket support for real-time updates."""
from .manager import ConnectionManager, manager

__all__ = ["ConnectionManager", "manager"]
```

Create `src/gui/backend/websocket/manager.py`:
```python
"""WebSocket connection manager."""
import json
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # job_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()

        self.active_connections[job_id].add(websocket)
        print(f"WebSocket connected for job {job_id}")

    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)

            # Clean up empty sets
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

        print(f"WebSocket disconnected for job {job_id}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_job(self, job_id: str, event_type: str, data: dict):
        """Broadcast a message to all connections for a specific job."""
        if job_id not in self.active_connections:
            return

        message = {
            "job_id": job_id,
            "type": event_type,
            "data": data,
            "timestamp": data.get("timestamp", "")
        }

        # Send to all connections for this job
        disconnected = set()
        for connection in self.active_connections[job_id]:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                print(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection, job_id)


# Global instance
manager = ConnectionManager()
```

**Step 2: Write WebSocket endpoint handler**

Create `src/gui/backend/websocket/handlers.py`:
```python
"""WebSocket endpoint handlers."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .manager import manager

router = APIRouter()


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates."""
    await manager.connect(websocket, job_id)

    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()

            # Echo back for now (could handle control commands later)
            await manager.send_personal_message(
                {"type": "ack", "message": f"Received: {data}"},
                websocket
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
```

**Step 3: Register WebSocket endpoint**

Modify `src/gui/backend/main.py`:
```python
from .websocket import handlers as ws_handlers

# Add after existing routers
app.include_router(ws_handlers.router)
```

**Step 4: Integrate WebSocket with job runner**

Modify `src/gui/backend/services/job_runner.py` to add WebSocket broadcast:
```python
from ..websocket.manager import manager
import asyncio

class JobRunner:
    # ... existing code ...

    def start_job(
        self,
        job_id: str,
        config: dict,
        on_progress: Optional[Callable] = None
    ):
        """Start a job in a background thread."""
        if job_id in self.active_jobs:
            raise ValueError(f"Job {job_id} is already running")

        # Create progress callback that broadcasts via WebSocket
        def progress_handler(job_id: str, event_type: str, data: dict):
            # Schedule WebSocket broadcast
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No event loop in this thread, skip WebSocket
                return

            asyncio.run_coroutine_threadsafe(
                manager.broadcast_to_job(job_id, event_type, data),
                loop
            )

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, config, progress_handler),
            daemon=True
        )
        thread.start()
        self.active_jobs[job_id] = thread
```

**Step 5: Test WebSocket connection**

Create a simple test HTML file `test_websocket.html`:
```html
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Test</title>
</head>
<body>
    <h1>WebSocket Test</h1>
    <div id="status">Not connected</div>
    <div id="messages"></div>

    <script>
        // Replace with actual job ID after creating a job
        const jobId = prompt("Enter job ID:");
        const ws = new WebSocket(`ws://localhost:8000/ws/${jobId}`);

        ws.onopen = () => {
            document.getElementById('status').textContent = 'Connected';
            console.log('WebSocket connected');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Received:', data);

            const messagesDiv = document.getElementById('messages');
            const msgDiv = document.createElement('div');
            msgDiv.textContent = `[${data.type}] ${JSON.stringify(data.data)}`;
            messagesDiv.appendChild(msgDiv);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
            document.getElementById('status').textContent = 'Disconnected';
            console.log('WebSocket closed');
        };
    </script>
</body>
</html>
```

Manual test:
1. Start server: `python -m src.gui`
2. Create a job via API: `curl -X POST http://localhost:8000/api/jobs/start -H "Content-Type: application/json" -d '{"name":"WS Test"}'`
3. Note the job_id from response
4. Open `test_websocket.html` in browser, enter job_id
5. Watch messages appear in real-time

**Step 6: Commit**

```bash
git add src/gui/backend/websocket/ test_websocket.html
git commit -m "feat(gui): implement WebSocket for real-time updates

- Add ConnectionManager for WebSocket connections
- Add WebSocket endpoint at /ws/{job_id}
- Integrate WebSocket broadcast with job runner
- Support per-job connection management
- Add HTML test page for WebSocket testing"
```

---

## Phase 4: Frontend Setup

### Task 10: Initialize React Frontend with Vite

**Files:**
- Create: `src/gui/frontend/` directory structure
- Create: `src/gui/frontend/package.json`
- Create: `src/gui/frontend/vite.config.ts`
- Create: `src/gui/frontend/tsconfig.json`

**Step 1: Create frontend directory and package.json**

```bash
mkdir -p src/gui/frontend/src src/gui/frontend/public
cd src/gui/frontend
```

Create `src/gui/frontend/package.json`:
```json
{
  "name": "scilex-gui-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "antd": "^5.23.6",
    "@tanstack/react-query": "^5.62.11",
    "axios": "^1.7.9",
    "recharts": "^2.15.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.18",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.7.3",
    "vite": "^6.0.5"
  }
}
```

**Step 2: Create Vite config**

Create `src/gui/frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

**Step 3: Create TypeScript config**

Create `src/gui/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `src/gui/frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

**Step 4: Create basic HTML entry point**

Create `src/gui/frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SciLEx - Literature Collection GUI</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 5: Create minimal React app**

Create `src/gui/frontend/src/main.tsx`:
```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

Create `src/gui/frontend/src/App.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { Layout, Typography, Space, Card } from 'antd'

const { Header, Content } = Layout
const { Title, Text } = Typography

function App() {
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    fetch('/api/health')
      .then(res => res.json())
      .then(data => setHealth(data))
      .catch(err => console.error('Health check failed:', err))
  }, [])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#001529', padding: '0 50px' }}>
        <Title level={3} style={{ color: 'white', margin: '16px 0' }}>
          SciLEx - Literature Collection GUI
        </Title>
      </Header>
      <Content style={{ padding: '50px' }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Card title="Welcome to SciLEx GUI">
            <Text>
              This is a web-based interface for systematic literature collection.
            </Text>
          </Card>

          <Card title="System Status">
            {health ? (
              <Text type="success">✓ Backend connected: {health.status}</Text>
            ) : (
              <Text type="secondary">Connecting to backend...</Text>
            )}
          </Card>
        </Space>
      </Content>
    </Layout>
  )
}

export default App
```

**Step 6: Install dependencies and test**

```bash
cd src/gui/frontend
npm install
```

Run frontend dev server (in one terminal):
```bash
npm run dev
```

Run backend (in another terminal):
```bash
cd ../../../  # back to project root
python -m src.gui
```

Visit: http://localhost:3000

Expected: React app loads, shows "Backend connected: healthy"

**Step 7: Commit**

```bash
cd ../../..  # back to project root
git add src/gui/frontend/
git commit -m "feat(gui): initialize React frontend with Vite

- Add Vite + React + TypeScript setup
- Add Ant Design for UI components
- Add React Query for API state management
- Configure dev server with API proxy
- Create minimal app with health check
- Add dependencies: React 18, Ant Design 5, TanStack Query"
```

---

This implementation plan is comprehensive but still needs more tasks. Let me know if you want me to continue with:

- Task 11+: Frontend components (Config editor, Progress dashboard, etc.)
- Integration with actual collection scripts
- Production build and deployment
- Additional polish and features

The plan follows TDD principles where applicable, provides exact file paths and code, and breaks work into 2-5 minute tasks with frequent commits.
