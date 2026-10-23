"""Collect screen: run collection + aggregation and follow its progress."""

from nicegui import ui

from scilex.gui.components.errors import show_error
from scilex.gui.components.job_panel import JobPanel
from scilex.gui.services.collect_summary import (
    api_rows,
    detect_resume,
    load_summary,
    phase_steps,
    preflight_line,
)
from scilex.gui.services.jobs import PIPELINE, Job, JobConflictError
from scilex.gui.services.workspace import Review, Workspace
from scilex.gui.state import AppContext
from scilex.pipeline import jobs as job_states
from scilex.settings.schema import SettingsError
from scilex.since_utils import parse_since

STATE_ICONS = {
    "waiting": "hourglass_empty",
    "running": "sync",
    "done": "check_circle",
    "partial": "warning",
    "failed": "error",
}
STEP_ICONS = {
    "done": "check_circle",
    "current": "autorenew",
    "pending": "radio_button_unchecked",
}


def _show_report(title: str, path) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[48rem] max-w-full"):
        ui.label(title).classes("text-lg font-bold")
        with ui.scroll_area().classes("w-full h-96"):
            ui.markdown(path.read_text(encoding="utf-8"))
        ui.button("Close", on_click=dialog.close)
    dialog.open()


def render(ctx: AppContext, review: Review) -> None:
    """Draw the Collect screen of ``review``."""
    ui.label("Collect").classes("text-2xl font-bold")
    ui.label(
        "Query the APIs listed in scilex.yml, then deduplicate, filter and rank "
        "the papers."
    ).classes("text-gray-500")

    # Pre-flight: validate scilex.yml before offering to run.
    with ui.column().classes("gap-1"):
        try:
            preflight_text = preflight_line(Workspace.load_config(review))
            ui.label(preflight_text).classes("text-sm").mark("preflight")
        except (SettingsError, FileNotFoundError) as exc:
            ui.label(str(exc)).classes("text-negative whitespace-pre-wrap").mark(
                "preflight-error"
            )
            ui.button(
                "Fix in ① Configure",
                icon="tune",
                on_click=lambda: ui.navigate.to(f"/review/{review.id}/configure"),
            ).props("outline").mark("fix-config")
        except Exception as exc:
            show_error("Cannot read the configuration", exc)

    with ui.row().classes("items-center gap-4"):
        skip_citations = ui.checkbox("Skip citation counts (faster)").mark(
            "skip-citations"
        )
        since_input = (
            ui.input("Only papers since", placeholder="YYYY-MM-DD")
            .props("dense clearable")
            .mark("since")
        )
    with ui.row().classes("items-center gap-4"):
        run_button = ui.button("Run", icon="play_arrow").mark("run")
        with run_button:
            busy_tooltip = ui.tooltip("Another job is running")
        resume_button = (
            ui.button("Resume interrupted collection", icon="replay")
            .props("outline")
            .mark("resume")
        )
        cancel_button = (
            ui.button("Cancel", icon="stop")
            .props("outline color=negative")
            .mark("cancel")
        )
    resume_hint = ui.label().classes("text-sm text-gray-500")

    def update_buttons(job: Job | None) -> None:
        running = job is not None and job.is_active
        busy_elsewhere = not running and ctx.runner.active_job() is not None
        run_button.set_enabled(not running and not busy_elsewhere)
        # One tooltip, shown or hidden: calling .tooltip() here would add a new one every tick.
        busy_tooltip.set_visibility(busy_elsewhere)
        cancel_button.set_visibility(running)
        resume_info = None if running else detect_resume(review.collection_dir)
        resume_button.set_visibility(resume_info is not None)
        resume_button.set_enabled(not busy_elsewhere)
        resume_hint.set_visibility(resume_info is not None)
        if resume_info is not None:
            resume_hint.text = (
                f"The last collection stopped at {resume_info.done}/"
                f"{resume_info.total} queries; resuming skips the finished ones."
            )

    panel = JobPanel(
        ctx,
        review,
        PIPELINE,
        on_change=update_buttons,
    )
    refresh = panel.refresh

    # --- live details: API table and aggregation phases -------------------
    api_container = ui.column().classes("w-full gap-1")
    phase_container = ui.column().classes("gap-0")
    shown: dict = {}

    def update_details(job: Job | None) -> None:
        if job is None:
            return
        rows = api_rows(job.api_stats, job.logs, job.status, job.is_active)
        if shown.get("rows") != (job.id, rows):
            shown["rows"] = (job.id, rows)
            api_container.clear()
            if rows:
                with api_container:
                    ui.table(
                        columns=[
                            {
                                "name": "api",
                                "label": "API",
                                "field": "api",
                                "align": "left",
                            },
                            {"name": "queries", "label": "Queries", "field": "queries"},
                            {"name": "papers", "label": "Papers", "field": "papers"},
                            {"name": "errors", "label": "Errors", "field": "errors"},
                            {
                                "name": "state",
                                "label": "State",
                                "field": "state",
                                "align": "left",
                            },
                        ],
                        rows=[
                            {
                                "api": row.api,
                                "queries": f"{row.queries_done}/{row.queries_total}",
                                "papers": row.papers,
                                "errors": row.errors,
                                "state": row.state
                                + (f": {row.reason}" if row.reason else ""),
                            }
                            for row in rows
                        ],
                        row_key="api",
                    ).props("dense flat").classes("w-full").mark("api-table")
        if not job.is_active and shown.get("finished") != job.id:
            shown["finished"] = job.id
            show_failure.refresh()
            show_summary.refresh()
        aggregating = job.phase == "aggregating" or job.aggregation_phase is not None
        finished = job.status == job_states.COMPLETED
        steps = (
            phase_steps(job.aggregation_phase, finished)
            if aggregating or finished
            else []
        )
        if shown.get("steps") != (job.id, steps):
            shown["steps"] = (job.id, steps)
            phase_container.clear()
            with phase_container:
                for label, state in steps:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(STEP_ICONS[state])
                        ui.label(label).classes("text-sm")

    # --- failure and completion summary ------------------------------------
    @ui.refreshable
    def show_failure() -> None:
        job = panel.job
        if job is None or job.status != job_states.FAILED:
            return
        ui.label(f"Error: {job.error}").classes("text-negative whitespace-pre-wrap")
        ui.button(
            "Copy log",
            icon="content_copy",
            on_click=lambda: (
                ui.clipboard.write("\n".join(job.logs)),
                ui.notify("Log copied"),
            ),
        ).props("outline").mark("copy-log")

    @ui.refreshable
    def show_summary() -> None:
        summary = load_summary(review.collection_dir)
        if summary is None:
            return
        ui.label("Last results").classes("text-lg font-bold")
        with ui.row().classes("gap-6").mark("summary"):
            for label, value in (
                ("Collected", summary.collected),
                ("After deduplication", summary.after_dedup),
                ("Kept", summary.kept),
            ):
                with ui.column().classes("gap-0"):
                    ui.label("-" if value is None else f"{value:,}").classes("text-xl")
                    ui.label(label).classes("text-xs text-gray-500")
        with ui.row():
            if summary.prisma_report:
                ui.button(
                    "PRISMA report",
                    icon="description",
                    on_click=lambda: _show_report(
                        "PRISMA report", summary.prisma_report
                    ),
                ).props("outline").mark("prisma-report")
            if summary.aggregation_report:
                ui.button(
                    "Aggregation report",
                    icon="description",
                    on_click=lambda: _show_report(
                        "Aggregation report", summary.aggregation_report
                    ),
                ).props("outline").mark("aggregation-report")

    show_failure()
    show_summary()
    # Details are drawn after the panel, so hook them in once they exist.
    panel.on_change = lambda job: (update_buttons(job), update_details(job))
    panel.refresh()

    def start(*, resume: bool) -> None:
        since = (since_input.value or "").strip() or None
        try:
            if since:
                parse_since(since)
        except ValueError as exc:
            show_error(
                "Invalid date", ValueError(f"Use YYYY-MM-DD ({exc})"), expected=True
            )
            return
        try:
            config = Workspace.load_config(review)
            ctx.runner.start_pipeline(
                review,
                config,
                skip_citations=skip_citations.value,
                since=since,
                resume=resume,
            )
        except (SettingsError, FileNotFoundError, JobConflictError) as exc:
            show_error("Cannot start the collection", exc, expected=True)
        except Exception as exc:
            show_error("Cannot start the collection", exc)
        show_failure.refresh()
        refresh()

    def cancel() -> None:
        job = panel.job
        if job is not None:
            ctx.runner.cancel(job.id)
        refresh()

    run_button.on_click(lambda: start(resume=False))
    resume_button.on_click(lambda: start(resume=True))
    cancel_button.on_click(cancel)
