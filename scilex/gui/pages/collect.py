"""Collect screen: run collection + aggregation and follow its progress."""

from nicegui import ui

from scilex.gui.components.errors import show_error
from scilex.gui.services.jobs import Job, JobConflictError
from scilex.gui.services.workspace import Review, Workspace
from scilex.gui.state import AppContext
from scilex.pipeline import jobs as job_states
from scilex.settings.schema import SettingsError

LOG_LINES_SHOWN = 50
STATUS_LABELS = {
    job_states.PENDING: "Starting…",
    job_states.RUNNING: "Running",
    job_states.CANCELLING: "Cancelling…",
    job_states.COMPLETED: "Completed",
    job_states.FAILED: "Failed",
    job_states.CANCELLED: "Cancelled",
}


def render(ctx: AppContext, review: Review) -> None:
    """Draw the Collect screen of ``review``."""
    ui.label("Collect").classes("text-2xl font-bold")
    ui.label(
        "Query the APIs listed in scilex.yml, then deduplicate, filter and rank "
        "the papers."
    ).classes("text-gray-500")

    with ui.row().classes("items-center gap-4"):
        skip_citations = ui.checkbox("Skip citation counts (faster)").mark(
            "skip-citations"
        )
        run_button = ui.button("Run", icon="play_arrow").mark("run")
        cancel_button = (
            ui.button("Cancel", icon="stop")
            .props("outline color=negative")
            .mark("cancel")
        )

    status = ui.label().classes("font-bold").mark("job-status")
    progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
    message = ui.label().classes("text-sm")
    log_view = ui.log(max_lines=LOG_LINES_SHOWN).classes("w-full h-64 text-xs")
    shown: dict[str, list[str]] = {"tail": []}

    def refresh() -> None:
        job = ctx.runner.latest_for(review.id)
        other = ctx.runner.active_job()
        busy_elsewhere = other is not None and other.review_id != review.id
        running = job is not None and job.is_active
        run_button.set_enabled(not running and not busy_elsewhere)
        run_button.tooltip("Another review is running" if busy_elsewhere else "")
        cancel_button.set_visibility(running)
        if job is None:
            status.text = "Not run in this session."
            progress.set_visibility(False)
            return
        progress.set_visibility(True)
        status.text = STATUS_LABELS.get(job.status, job.status)
        progress.value = job.progress / 100
        message.text = job.message
        _append_new_logs(job)

    def _append_new_logs(job: Job) -> None:
        # The job trims its log list in place, so compare the tail, not the length.
        tail = job.logs[-LOG_LINES_SHOWN:]
        if tail == shown["tail"]:
            return
        log_view.clear()
        for line in tail:
            log_view.push(line)
        shown["tail"] = tail

    def run() -> None:
        try:
            config = Workspace.load_config(review)
            ctx.runner.start_pipeline(
                review, config, skip_citations=skip_citations.value
            )
        except (SettingsError, FileNotFoundError, JobConflictError) as exc:
            show_error("Cannot start the collection", exc, expected=True)
        except Exception as exc:
            show_error("Cannot start the collection", exc)
        refresh()

    def cancel() -> None:
        job = ctx.runner.latest_for(review.id)
        if job is not None:
            ctx.runner.cancel(job.id)
        refresh()

    run_button.on_click(run)
    cancel_button.on_click(cancel)
    refresh()
    ui.timer(0.5, refresh)
