"""Review screen: step sidebar plus the content of the active step."""

from nicegui import ui

from scilex.gui.components.stepper import (
    DEFAULT_STEP,
    NEEDS_RESULTS_HINT,
    STEPS,
    is_enabled,
    render_sidebar,
)
from scilex.gui.pages import collect
from scilex.gui.state import AppContext

# Steps not built yet, with the lot that delivers them.
COMING_SOON = {
    "configure": "lot 1 (for now, edit scilex.yml in the review folder)",
    "keys": "lot 1 (for now, edit ~/.config/scilex/keys.yml)",
    "screen": "lot 3",
    "export": "lot 4",
    "analyses": "lot 5",
}


def render(ctx: AppContext, review_id: str, step: str = DEFAULT_STEP) -> None:
    """Draw review ``review_id`` with ``step`` active."""
    review = ctx.workspace.get(review_id)
    if review is None:
        ui.label("This review is no longer available.").classes("p-6")
        ui.button("Back to my reviews", on_click=lambda: ui.navigate.to("/"))
        return
    if step not in STEPS:
        step = DEFAULT_STEP

    with ui.row().classes("w-full p-4 gap-6 no-wrap items-start"):
        with ui.column().classes("gap-0"):
            ui.label(review.name).classes("text-lg font-bold px-2")
            ui.label(str(review.folder)).classes(
                "text-xs text-gray-500 px-2 pb-2 break-all w-52"
            )
            render_sidebar(review, step)
        with ui.column().classes("grow gap-3"):
            if not is_enabled(STEPS[step], review):
                ui.label(NEEDS_RESULTS_HINT)
            elif step == "collect":
                collect.render(ctx, review)
            else:
                ui.label(STEPS[step].label).classes("text-2xl font-bold")
                ui.label(f"Coming in {COMING_SOON[step]}.").classes("text-gray-500")
