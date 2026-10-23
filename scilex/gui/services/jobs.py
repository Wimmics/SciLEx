"""Background pipeline jobs for the desktop GUI (collection then aggregation).

A job runs in its own thread; the UI polls :class:`Job` fields with a timer.
Only one job may be active in the whole app: log capture accepts the
collector's anonymous threads, which is only correct for a single job.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from scilex.config import SciLExConfig
from scilex.gui.services.workspace import Review
from scilex.pipeline import jobs as job_states
from scilex.pipeline.jobs import LogLinesHandler, WorkerThreadFilter

logger = logging.getLogger(__name__)

# Share of the progress bar given to each pipeline stage.
COLLECT_RANGE = (0, 70)
AGGREGATE_RANGE = (70, 100)


class JobConflictError(RuntimeError):
    """Raised when a job is started while another one is still active."""


@dataclass
class Job:
    """State of one pipeline run, read by the UI."""

    id: str
    review_id: str
    status: str = job_states.PENDING
    phase: str = "pending"
    progress: int = 0
    message: str = ""
    logs: list[str] = field(default_factory=list)
    api_stats: dict = field(default_factory=dict)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    thread_ids: set[int] = field(default_factory=set, repr=False)

    @property
    def is_active(self) -> bool:
        """True while the job is pending, running or cancelling."""
        return self.status in job_states.ACTIVE_STATUSES


def _default_run_collection(*args, **kwargs):
    from scilex.pipeline.orchestrator import run_collection

    return run_collection(*args, **kwargs)


def _default_run_aggregation(*args, **kwargs):
    from scilex.pipeline.orchestrator import run_aggregation

    return run_aggregation(*args, **kwargs)


def _scale(value: float, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return low + int(max(0.0, min(1.0, value)) * (high - low))


class JobRunner:
    """Start, track and cancel pipeline jobs, one at a time."""

    def __init__(
        self,
        run_collection: Callable = _default_run_collection,
        run_aggregation: Callable = _default_run_aggregation,
    ):
        """Create a runner; pipeline functions are injectable for tests."""
        self._run_collection = run_collection
        self._run_aggregation = run_aggregation
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        """Return the job with this id, or None."""
        return self._jobs.get(job_id)

    def active_job(self) -> Job | None:
        """Return the job currently active in the app, if any."""
        return next((job for job in self._jobs.values() if job.is_active), None)

    def latest_for(self, review_id: str) -> Job | None:
        """Return the most recent job of a review, if any."""
        jobs = [job for job in self._jobs.values() if job.review_id == review_id]
        return max(jobs, key=lambda job: job.started_at, default=None)

    def start_pipeline(
        self, review: Review, config: SciLExConfig, *, skip_citations: bool = False
    ) -> Job:
        """Run collection then aggregation for ``review`` in a background thread.

        Raises:
            JobConflictError: If another job is still active.
        """
        with self._lock:
            if self.active_job() is not None:
                raise JobConflictError("A pipeline is already running")
            job = Job(id=uuid.uuid4().hex[:12], review_id=review.id)
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run,
            args=(job, config, skip_citations),
            name=f"scilex-job-{job.id}",
            daemon=True,
        )
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        """Request cancellation; returns False if the job is not active.

        Collection stops at the next query; aggregation cannot be interrupted,
        so a job cancelled during aggregation ends as cancelled once it returns.
        """
        job = self._jobs.get(job_id)
        if job is None or not self._set_status(job, job_states.CANCELLING):
            return False
        job.cancel_event.set()
        job.message = "Cancelling…"
        return True

    def _set_status(self, job: Job, status: str) -> bool:
        with self._lock:
            if not job_states.transition_allowed(job.status, status):
                return False
            job.status = status
            return True

    def _finish(self, job: Job, status: str, message: str) -> None:
        if self._set_status(job, status):
            job.message = message
            job.phase = status
            if status == job_states.COMPLETED:
                job.progress = 100
        job.finished_at = datetime.now()

    def _cancelled(self, job: Job) -> bool:
        if not job.cancel_event.is_set():
            return False
        self._finish(job, job_states.CANCELLED, "Cancelled.")
        return True

    def _run(self, job: Job, config: SciLExConfig, skip_citations: bool) -> None:
        job.thread_ids.add(threading.get_ident())
        handler = LogLinesHandler(job.logs)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )
        handler.addFilter(WorkerThreadFilter(job.thread_ids))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            self._set_status(job, job_states.RUNNING)
            if self._cancelled(job):
                return
            self._collect(job, config)
            if self._cancelled(job):
                return
            self._aggregate(job, config, skip_citations)
            if self._cancelled(job):
                return
            self._finish(job, job_states.COMPLETED, "Pipeline completed.")
        except Exception as exc:
            logger.exception("Pipeline job %s failed", job.id)
            job.error = str(exc)
            self._finish(job, job_states.FAILED, f"Error: {exc}")
        finally:
            root_logger.removeHandler(handler)

    def _collect(self, job: Job, config: SciLExConfig) -> None:
        job.phase = "collecting"
        job.progress = COLLECT_RANGE[0]
        job.message = "Collecting papers…"

        def on_progress(api_stats, completed, total):
            job.progress = _scale(completed / max(total, 1), COLLECT_RANGE)
            job.message = f"Collecting papers… {completed}/{total} queries done"
            job.api_stats = {api: dict(stats) for api, stats in api_stats.items()}

        self._run_collection(
            config, progress_callback=on_progress, cancel_event=job.cancel_event
        )

    def _aggregate(self, job: Job, config: SciLExConfig, skip_citations: bool) -> None:
        from scilex.pipeline.orchestrator import AggregationOptions

        job.phase = "aggregating"
        job.progress = AGGREGATE_RANGE[0]
        job.message = "Aggregating results…"

        def on_progress(phase, percent, message):
            job.progress = _scale(percent / 100, AGGREGATE_RANGE)
            job.message = message

        self._run_aggregation(
            config, AggregationOptions(skip_citations=skip_citations), on_progress
        )
