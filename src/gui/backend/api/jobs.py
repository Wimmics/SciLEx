"""Job management endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.job import JobCreate, JobResponse, JobDetail, JobStatus
from ..services.job_manager import JobManager
from ..services.config_sync import ConfigSyncService
from ..services.job_runner import job_runner

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

    # Start the background job
    try:
        job_runner.start_job(job.id, config_snapshot)
    except Exception as e:
        job_manager.update_job_status(db, job.id, JobStatus.FAILED, error_message=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start job: {str(e)}")

    return {
        "job_id": job.id,
        "status": "queued",
        "message": "Job started successfully"
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
