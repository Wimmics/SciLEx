"""Home screen: the reviews known to the app."""

from pathlib import Path

from nicegui import app, ui

from scilex.gui.components.errors import show_error
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext
from scilex.init_templates import list_templates
from scilex.settings.schema import SettingsError

# Errors caused by the user's input or files, shown without a diagnostic report.
EXPECTED_ERRORS = (OSError, SettingsError)  # missing, existing, unwritable files
NO_TEMPLATE = "(blank)"


async def pick_folder(ctx: AppContext) -> str | None:
    """Ask for a folder with the native dialog; None in browser mode or if cancelled."""
    if not ctx.native:
        return None
    import webview

    selection = await app.native.main_window.create_file_dialog(
        webview.FileDialog.FOLDER
    )
    return selection[0] if selection else None


def render(ctx: AppContext) -> None:
    """Draw the home screen."""
    reviews = ctx.workspace.list_reviews()
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
        with ui.row().classes("w-full items-center"):
            ui.label("My reviews").classes("text-2xl font-bold")
            ui.space()
            ui.button(
                "New review", icon="add", on_click=lambda: new_review_dialog(ctx)
            ).mark("new-review")
            ui.button(
                "Open a folder",
                icon="folder_open",
                on_click=lambda: open_review_dialog(ctx),
            ).props("outline").mark("open-review")
        if not reviews:
            ui.label(
                "No review yet. Create one, or open a folder that already "
                "contains a scilex.yml."
            ).classes("text-gray-500")
        with ui.row().classes("w-full gap-4"):
            for review in reviews:
                _review_card(ctx, review)


def _review_card(ctx: AppContext, review: Review) -> None:
    job = ctx.runner.latest_for(review.id)
    with (
        ui.card()
        .classes("w-72 cursor-pointer")
        .on("click", lambda: ui.navigate.to(f"/review/{review.id}"))
        .mark(f"review-{review.id}")
    ):
        ui.label(review.name).classes("text-lg font-bold")
        ui.label(str(review.folder)).classes("text-xs text-gray-500 break-all")
        if review.error:
            ui.label("scilex.yml is invalid: open to fix it").classes(
                "text-sm text-negative"
            )
        elif job is not None and job.is_active:
            ui.label(f"Running: {job.message}").classes("text-sm text-primary")
        elif review.has_results:
            ui.label("Results available").classes("text-sm text-positive")
        else:
            ui.label("Not collected yet").classes("text-sm text-gray-500")


def _folder_input(ctx: AppContext, label: str) -> ui.input:
    with ui.row().classes("w-full items-center no-wrap"):
        folder = ui.input(label).classes("grow").mark("folder")
        if ctx.native:

            async def browse() -> None:
                chosen = await pick_folder(ctx)
                if chosen:
                    folder.value = chosen

            ui.button(icon="folder", on_click=browse).props("flat").tooltip("Browse…")
    return folder


def new_review_dialog(ctx: AppContext) -> None:
    """Ask for a folder, a name and a template, then create the review."""
    with ui.dialog() as dialog, ui.card().classes("w-[32rem]"):
        ui.label("New review").classes("text-lg font-bold")
        folder = _folder_input(ctx, "Folder (created if needed)")
        folder.props(
            'hint="Relative paths start at your home folder, e.g. Documents/reviews/rag"'
        )
        name = (
            ui.input("Name", placeholder="e.g. rag_knowledge_graphs")
            .classes("w-full")
            .mark("name")
        )
        template = ui.select(
            [NO_TEMPLATE, *list_templates()], value=NO_TEMPLATE, label="Template"
        ).classes("w-full")

        def create() -> None:
            if not folder.value or not name.value:
                ui.notify("Folder and name are required", type="warning")
                return
            try:
                review = ctx.workspace.create_review(
                    Path(folder.value),
                    name=name.value.strip(),
                    template=None if template.value == NO_TEMPLATE else template.value,
                )
            except EXPECTED_ERRORS as exc:
                show_error("Cannot create the review", exc, expected=True)
                return
            except Exception as exc:
                show_error("Cannot create the review", exc)
                return
            dialog.close()
            ui.navigate.to(f"/review/{review.id}/configure")

        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Create", on_click=create).mark("create")
    dialog.open()


def open_review_dialog(ctx: AppContext) -> None:
    """Register an existing folder holding a scilex.yml."""
    with ui.dialog() as dialog, ui.card().classes("w-[32rem]"):
        ui.label("Open a review folder").classes("text-lg font-bold")
        folder = _folder_input(ctx, "Folder containing scilex.yml")

        def open_folder() -> None:
            if not folder.value:
                ui.notify("Choose a folder", type="warning")
                return
            try:
                review = ctx.workspace.open_review(Path(folder.value))
            except EXPECTED_ERRORS as exc:
                show_error("Cannot open this folder", exc, expected=True)
                return
            except Exception as exc:
                show_error("Cannot open this folder", exc)
                return
            dialog.close()
            ui.navigate.to(f"/review/{review.id}")

        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Open", on_click=open_folder).mark("open")
    dialog.open()
