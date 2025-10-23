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
