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
    extra_data = Column(Text, nullable=True)  # JSON

    # Relationships
    job = relationship("Job", back_populates="progress_snapshots")
