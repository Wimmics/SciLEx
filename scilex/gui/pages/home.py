"""Home screen: the reviews known to the app."""

from collections.abc import Callable
from pathlib import Path

from nicegui import app, ui

from scilex.gui.components.dialogs import one_shot_dialog
from scilex.gui.components.errors import show_error
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext
from scilex.init_templates import list_templates
from scilex.settings.schema import SettingsError

# Errors caused by the user's input or files, shown without a diagnostic report.
EXPECTED_ERRORS = (OSError, SettingsError)  # missing, existing, unwritable files
NO_TEMPLATE = "(blank)"
CARDS_POLL_SECONDS = 2.0


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

        shown: list[tuple] = [()]

        @ui.refreshable
        def cards() -> None:
            reviews = ctx.workspace.list_reviews()
            shown[0] = _cards_state(ctx, reviews)
            if not reviews:
                ui.label(
                    "No review yet. Create one, or open a folder that already "
                    "contains a scilex.yml."
                ).classes("text-gray-500")
            with ui.row().classes("w-full gap-4"):
                for review in reviews:
                    _review_card(ctx, review, cards.refresh)

        cards()

        def refresh_if_changed() -> None:
            # A running job, new results or an edited scilex.yml change a card.
            if _cards_state(ctx, ctx.workspace.list_reviews()) != shown[0]:
                cards.refresh()

        ui.timer(CARDS_POLL_SECONDS, refresh_if_changed)


def _cards_state(ctx: AppContext, reviews: list[Review]) -> tuple:
    """What the cards show, to redraw them only when it changes."""
    state = []
    for review in reviews:
        job = ctx.runner.latest_for(review.id)
        running = job.message if job is not None and job.is_active else None
        state.append((review, review.error, review.has_results, running))
    return tuple(state)


def _review_card(
    ctx: AppContext, review: Review, on_forget: Callable[[], None]
) -> None:
    job = ctx.runner.latest_for(review.id)
    with (
        ui.card()
        .classes("w-72 cursor-pointer")
        .on("click", lambda: ui.navigate.to(f"/review/{review.id}"))
        .mark(f"review-{review.id}")
    ):
        with ui.row().classes("w-full items-start no-wrap gap-1"):
            ui.label(review.name).classes(
                "text-lg font-bold grow min-w-0 break-words"
            ).style("overflow-wrap: anywhere").tooltip(review.name)
            _card_menu(ctx, review, on_forget)
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


def _card_menu(ctx: AppContext, review: Review, on_forget: Callable[[], None]) -> None:
    """Small menu (⋮) of a card: forget the review or copy its folder path."""

    def forget() -> None:
        ctx.workspace.forget_review(review.folder)
        confirm.close()
        on_forget()

    with ui.dialog() as confirm, ui.card():
        ui.label(f"Remove '{review.name}' from the list?").classes("font-bold")
        ui.label(
            "The files stay on disk; you can add the folder back with 'Open a folder'."
        ).classes("text-sm")
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=confirm.close).props("flat")
            ui.button("Remove", on_click=forget).props("color=negative").mark(
                f"forget-confirm-{review.id}"
            )

    def copy_path() -> None:
        ui.clipboard.write(str(review.folder))
        ui.notify("Folder path copied")

    # The card navigates on click: the menu button must not trigger it.
    with (
        ui.button(icon="more_vert")
        .props("flat dense round")
        .on("click.stop")
        .mark(f"forget-{review.id}"),
        ui.menu(),
    ):
        ui.menu_item("Remove from list", on_click=confirm.open).mark(
            f"forget-item-{review.id}"
        )
        ui.menu_item("Show folder path", on_click=copy_path)


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
    with one_shot_dialog() as dialog, ui.card().classes("w-[32rem]"):
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
    with one_shot_dialog() as dialog, ui.card().classes("w-[32rem]"):
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
