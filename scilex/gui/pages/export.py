"""Export screen: BibTeX, CSV, RDF/Turtle and Zotero for the chosen papers."""

from __future__ import annotations

from nicegui import ui

from scilex.gui.components.errors import show_error
from scilex.gui.components.job_panel import JobPanel
from scilex.gui.services import exports
from scilex.gui.services.jobs import Job, JobConflictError
from scilex.gui.services.workspace import Review, Workspace
from scilex.gui.state import AppContext
from scilex.settings.schema import SettingsError

KIND = "export"

FORMATS = (
    (
        exports.BIBTEX,
        "BibTeX",
        "Reference file for LaTeX, Zotero or JabRef.",
    ),
    (
        exports.CSV,
        "CSV",
        "Spreadsheet table (';' separated) with your screening decision and note.",
    ),
    (
        exports.TURTLE,
        "RDF / Turtle",
        "Knowledge graph of the papers, authors and venues.",
    ),
    (
        exports.ZOTERO,
        "Zotero",
        "Pushes the papers into a Zotero collection named after the review; "
        "papers already there are skipped.",
    ),
)


def zotero_summary(counts: dict[str, int]) -> str:
    """Human-readable result of a Zotero push."""
    return (
        f"{counts.get('success', 0)} pushed, "
        f"{counts.get('skipped', 0)} skipped as duplicates, "
        f"{counts.get('skipped_for_incompatibility', 0)} without usable URL or type, "
        f"{counts.get('failed', 0)} failed."
    )


def render(ctx: AppContext, review: Review) -> None:
    """Draw the Export screen of ``review``."""
    ui.label("Export").classes("text-2xl font-bold")
    ui.label("Choose which papers to export, then a format.").classes("text-gray-500")

    included, total = exports.scope_counts(review)
    options = {
        exports.SCOPE_INCLUDED: f"Included papers only ({included})",
        exports.SCOPE_ALL: f"All papers ({total})",
    }
    scope = ui.radio(
        options, value=exports.SCOPE_INCLUDED if included else exports.SCOPE_ALL
    ).mark("export-scope")
    if not included:
        # A radio cannot disable one option: refuse it and say why.
        ui.label(
            "Included papers only is unavailable: no paper is included yet "
            "(mark papers as included in ③ Screen)."
        ).classes("text-sm text-gray-500")
        scope.on_value_change(
            lambda e: (
                scope.set_value(exports.SCOPE_ALL)
                if e.value == exports.SCOPE_INCLUDED
                else None
            )
        )
    config_error = None
    zotero_ready = False
    try:
        zotero_ready = (
            exports.zotero_settings(Workspace.load_config(review)) is not None
        )
    except (SettingsError, FileNotFoundError) as exc:
        config_error = exc

    buttons = {}
    with ui.column().classes("gap-3 w-full"):
        for fmt, label, text in FORMATS:
            with ui.card().classes("w-full"), ui.row().classes("items-center gap-4"):
                with ui.column().classes("gap-0 w-96"):
                    ui.label(label).classes("font-bold")
                    ui.label(text).classes("text-sm text-gray-500")
                buttons[fmt] = ui.button(f"Export {label}", icon="download").mark(
                    f"export-{fmt}"
                )
                if fmt == exports.ZOTERO and not zotero_ready:
                    ui.label(
                        str(config_error)
                        if config_error
                        else "Zotero user ID and API key are missing."
                    ).classes("text-sm text-negative")
                    ui.link(
                        "Set up API keys",
                        f"/review/{review.id}/keys",
                    ).mark("export-zotero-keys")
                    buttons[fmt].set_enabled(False)

    result_box = ui.column().classes("gap-1 w-full")
    history_box = ui.column().classes("gap-1 w-full")

    def update_buttons(job: Job | None) -> None:
        busy = ctx.runner.active_job() is not None
        for fmt, button in buttons.items():
            if fmt == exports.ZOTERO and not zotero_ready:
                continue
            button.set_enabled(not busy)

    def show_history() -> None:
        history_box.clear()
        with history_box:
            ui.label("Previous exports").classes("font-bold mt-2")
            files = exports.list_exports(review)
            if not files:
                ui.label("No export yet.").classes("text-sm text-gray-500")
            for path in files:
                ui.label(path.name).classes("text-sm")

    def show_result(job: Job) -> None:
        result_box.clear()
        with result_box:
            if job.error or job.result is None:
                ui.label(job.message).classes("text-negative")
            elif isinstance(job.result, dict):
                ui.label(zotero_summary(job.result)).classes("font-bold").mark(
                    "export-result"
                )
            else:
                path = job.result
                ui.label(f"Exported to {path}").classes("font-bold break-all").mark(
                    "export-result"
                )
                ui.button(
                    "Reveal in folder",
                    icon="folder_open",
                    on_click=lambda: exports.reveal_in_folder(path),
                ).props("outline").mark("export-reveal")
        show_history()

    JobPanel(
        ctx,
        review,
        KIND,
        on_change=update_buttons,
        on_finished=show_result,
        show_logs=False,
    )
    show_history()

    def start(fmt: str) -> None:
        chosen = scope.value

        def body(job: Job) -> str:
            job.progress = 10
            if fmt == exports.ZOTERO:
                job.message = "Pushing to Zotero…"
                job.result = exports.push_to_zotero(
                    review, Workspace.load_config(review), chosen
                )
                return zotero_summary(job.result)
            job.message = f"Writing {fmt}…"
            job.result = exports.run_file_export(review, fmt, chosen)
            return f"Exported {job.result.name}"

        try:
            ctx.runner.start_task(review, KIND, body)
        except JobConflictError as exc:
            show_error("Cannot start the export", exc, expected=True)
        except Exception as exc:
            show_error("Cannot start the export", exc)

    for fmt, button in buttons.items():
        button.on_click(lambda fmt=fmt: start(fmt))
