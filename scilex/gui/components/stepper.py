"""Sidebar listing the pipeline steps of a review."""

from dataclasses import dataclass

from nicegui import ui

from scilex.gui.services.workspace import Review


@dataclass(frozen=True)
class Step:
    """One entry of the sidebar."""

    key: str
    label: str
    icon: str
    needs_results: bool = False


PIPELINE_STEPS = (
    Step("configure", "① Configure", "tune"),
    Step("collect", "② Collect", "travel_explore"),
    Step("screen", "③ Screen", "fact_check", needs_results=True),
    Step("export", "④ Export", "ios_share", needs_results=True),
    Step("analyses", "⑤ Analyses", "insights", needs_results=True),
)
EXTRA_STEPS = (Step("keys", "API keys", "key"),)
STEPS = {step.key: step for step in (*PIPELINE_STEPS, *EXTRA_STEPS)}
DEFAULT_STEP = "collect"
NEEDS_RESULTS_HINT = "Available once a collection has been aggregated (step ②)."


def is_enabled(step: Step, review: Review) -> bool:
    """Return True if ``step`` can be opened for ``review``."""
    return review.has_results or not step.needs_results


def render_sidebar(review: Review, active: str) -> None:
    """Draw the steps of ``review``, highlighting ``active``."""
    with ui.column().classes("w-52 gap-1 shrink-0"):
        for step in PIPELINE_STEPS:
            _step_button(review, step, active)
        ui.separator()
        for step in EXTRA_STEPS:
            _step_button(review, step, active)
        ui.button(
            "My reviews", icon="folder_open", on_click=lambda: ui.navigate.to("/")
        ).props("flat align=left no-caps").classes("w-full")


def _step_button(review: Review, step: Step, active: str) -> None:
    button = ui.button(
        step.label,
        icon=step.icon,
        on_click=lambda: ui.navigate.to(f"/review/{review.id}/{step.key}"),
    ).props("align=left no-caps" + ("" if step.key == active else " flat"))
    button.classes("w-full").mark(f"step-{step.key}")
    if not is_enabled(step, review):
        button.disable()
        button.tooltip(NEEDS_RESULTS_HINT)
