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
