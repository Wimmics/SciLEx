"""Collect screen: run collection + aggregation and follow its progress."""

from nicegui import ui

from scilex.gui.components.errors import show_error
from scilex.gui.components.job_panel import JobPanel
from scilex.gui.services.jobs import PIPELINE, Job, JobConflictError
from scilex.gui.services.workspace import Review, Workspace
from scilex.gui.state import AppContext
from scilex.settings.schema import SettingsError


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
        with run_button:
            busy_tooltip = ui.tooltip("Another job is running")
        cancel_button = (
            ui.button("Cancel", icon="stop")
            .props("outline color=negative")
            .mark("cancel")
        )

    def update_buttons(job: Job | None) -> None:
        running = job is not None and job.is_active
        busy_elsewhere = not running and ctx.runner.active_job() is not None
        run_button.set_enabled(not running and not busy_elsewhere)
        # One tooltip, shown or hidden: calling .tooltip() here would add a new one every tick.
        busy_tooltip.set_visibility(busy_elsewhere)
        cancel_button.set_visibility(running)

    panel = JobPanel(ctx, review, PIPELINE, on_change=update_buttons)
    refresh = panel.refresh

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
        job = panel.job
        if job is not None:
            ctx.runner.cancel(job.id)
        refresh()

    run_button.on_click(run)
    cancel_button.on_click(cancel)
