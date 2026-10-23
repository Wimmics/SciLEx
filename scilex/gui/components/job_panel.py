"""Status, progress bar and log tail of the latest job of one kind."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from scilex.gui.services.jobs import Job
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext
from scilex.pipeline import jobs as job_states

LOG_LINES_SHOWN = 50
STATUS_LABELS = {
    job_states.PENDING: "Starting…",
    job_states.RUNNING: "Running",
    job_states.CANCELLING: "Cancelling…",
    job_states.COMPLETED: "Completed",
    job_states.FAILED: "Failed",
    job_states.CANCELLED: "Cancelled",
}


class JobPanel:
    """Live view of ``runner.latest_for(review.id, kind)``, refreshed every 0.5 s.

    ``on_change(job)`` is called on every refresh, so the page can enable or
    disable its own buttons; ``on_finished(job)`` once when a job it watched
    reaches a terminal state (e.g. to show the result).
    """

    def __init__(
        self,
        ctx: AppContext,
        review: Review,
        kind: str,
        *,
        on_change: Callable[[Job | None], None] | None = None,
        on_finished: Callable[[Job], None] | None = None,
        show_logs: bool = True,
    ):
        """Draw the panel at the current position of the page."""
        self.ctx, self.review, self.kind = ctx, review, kind
        self.on_change, self.on_finished = on_change, on_finished
        self.status = ui.label().classes("font-bold").mark(f"{kind}-status")
        self.progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
        self.message = ui.label().classes("text-sm")
        self.log_view = (
            ui.log(max_lines=LOG_LINES_SHOWN).classes("w-full h-64 text-xs")
            if show_logs
            else None
        )
        self._tail: list[str] = []
        # Jobs already finished when the page opened are not reported again;
        # any other job is reported once it ends, even if it ended between two
        # ticks (a fast export can start and finish within 0.5 s).
        existing = self.job
        self._reported: set[str] = (
            {existing.id} if existing is not None and not existing.is_active else set()
        )
        self.refresh()
        ui.timer(0.5, self.refresh)

    @property
    def job(self) -> Job | None:
        """Latest job of this kind for the review."""
        return self.ctx.runner.latest_for(self.review.id, self.kind)

    @property
    def busy_elsewhere(self) -> bool:
        """True if another job (any review, any kind) is active."""
        other = self.ctx.runner.active_job()
        return other is not None and other is not self.job

    def refresh(self) -> None:
        """Update the widgets from the job state."""
        job = self.job
        if self.on_change is not None:
            self.on_change(job)
        if job is None:
            self.status.text = "Not run in this session."
            self.progress.set_visibility(False)
            return
        self.progress.set_visibility(True)
        self.status.text = STATUS_LABELS.get(job.status, job.status)
        self.progress.value = job.progress / 100
        self.message.text = job.message
        self._append_new_logs(job)
        if not job.is_active and job.id not in self._reported:
            self._reported.add(job.id)
            if self.on_finished is not None:
                self.on_finished(job)

    def _append_new_logs(self, job: Job) -> None:
        if self.log_view is None:
            return
        # The job trims its log list in place, so compare the tail, not the length.
        tail = job.logs[-LOG_LINES_SHOWN:]
        if tail == self._tail:
            return
        self.log_view.clear()
        for line in tail:
            self.log_view.push(line)
        self._tail = tail
