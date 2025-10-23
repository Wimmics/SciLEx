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
