"""Screen step: table of papers, detail panel and include / exclude / maybe decisions."""

import contextlib
import json

from nicegui import events, ui

from scilex.constants import doi_to_url
from scilex.gui.components.errors import show_error
from scilex.gui.services.screening import (
    EXCLUDE,
    FILTER_ALL,
    FILTER_UNDECIDED,
    INCLUDE,
    MAYBE,
    ScreeningSession,
)
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext

FILTER_OPTIONS = {
    FILTER_ALL: "All",
    FILTER_UNDECIDED: "Undecided",
    INCLUDE: "Included",
    EXCLUDE: "Excluded",
    MAYBE: "Maybe",
}
DECISION_COLOURS = {INCLUDE: "positive", EXCLUDE: "negative", MAYBE: "warning"}
KEY_DECISIONS = {"i": INCLUDE, "e": EXCLUDE, "m": MAYBE}

COLUMN_DEFS = [
    {
        "field": "title",
        "headerName": "Title",
        "flex": 4,
        "minWidth": 220,
        "tooltipField": "title",
    },
    {
        "field": "year",
        "headerName": "Year",
        "width": 80,
        "filter": "agNumberColumnFilter",
    },
    {"field": "venue", "headerName": "Venue", "flex": 1, "minWidth": 100},
    {
        "field": "score",
        "headerName": "Score",
        "width": 90,
        "filter": "agNumberColumnFilter",
        "sort": "desc",
    },
    {
        "field": "citations",
        "headerName": "Cited",
        "width": 90,
        "filter": "agNumberColumnFilter",
    },
    {
        "field": "decision",
        "headerName": "Decision",
        "width": 110,
        ":cellClassRules": json.dumps(
            {
                "decision-include": "x === 'Include'",
                "decision-exclude": "x === 'Exclude'",
                "decision-maybe": "x === 'Maybe'",
            }
        ),
    },
]

GRID_CSS = """
.decision-include { color: #16a34a; font-weight: 600; }
.decision-exclude { color: #dc2626; font-weight: 600; }
.decision-maybe { color: #d97706; font-weight: 600; }
"""


def render(ctx: AppContext, review: Review) -> None:
    """Draw the Screen step of ``review``."""
    ui.label("Screen").classes("text-2xl font-bold")
    try:
        session = ScreeningSession(review)
    except Exception as exc:
        show_error("Cannot load the results", exc)
        return
    ui.add_css(GRID_CSS)
    ScreenPage(session).build()


class ScreenPage:
    """UI state of the Screen step; all decisions go through the session."""

    def __init__(self, session: ScreeningSession):
        """Bind the page to an in-memory screening session."""
        self.session = session
        self.decision_filter = FILTER_ALL
        self.query = ""
        self.current: str | None = None
        self.order: list[str] = []  # keys in the grid's displayed order

    # -- layout ---------------------------------------------------------

    def build(self) -> None:
        """Create all elements."""
        self.counters = ui.label().classes("text-sm").mark("screen-counters")
        self.progress = ui.linear_progress(show_value=False).classes("w-full")
        with ui.row().classes("items-center gap-4 w-full"):
            ui.select(FILTER_OPTIONS, value=FILTER_ALL, on_change=self.on_filter).props(
                "dense outlined label=Decision"
            ).classes("w-40").mark("decision-filter")
            ui.input(
                placeholder="Search title or abstract",
                on_change=self.on_search,
            ).props("dense outlined clearable debounce=300").classes("grow").mark(
                "text-search"
            )
        ui.label(
            "Shortcuts: I include, E exclude, M maybe, ↑/↓ or K/J previous/next "
            "(disabled while typing in the note)"
        ).classes("text-xs text-gray-500")

        rows = self.session.visible_rows()
        self.order = [row["paper_key"] for row in rows]
        self.grid = (
            ui.aggrid(
                {
                    "columnDefs": COLUMN_DEFS,
                    "rowData": rows,
                    ":getRowId": "(params) => params.data.paper_key",
                    "rowSelection": {
                        "mode": "singleRow",
                        "checkboxes": False,
                        "enableClickSelection": True,
                    },
                    "defaultColDef": {
                        "sortable": True,
                        "filter": True,
                        "resizable": True,
                    },
                    "tooltipShowDelay": 500,
                }
            )
            .classes("w-full")
            .style("height: 380px")
            .mark("screen-grid")
        )
        self.grid.on("selectionChanged", self.on_grid_selection)
        self.grid.on("sortChanged", self.sync_order)
        self.grid.on("filterChanged", self.sync_order)

        self.detail_panel()
        self.orphans_panel()
        ui.keyboard(on_key=self.on_key, repeating=False)
        self.update_counters()
        if self.order:
            self.select(self.order[0])

    @ui.refreshable_method
    def detail_panel(self) -> None:
        """Detail of the current paper with decision buttons and note."""
        if self.current is None:
            ui.label("No paper to show.").classes("text-gray-500")
            return
        detail = self.session.detail(self.current)
        decision = self.session.decision_of(self.current)
        with ui.card().classes("w-full gap-2").mark("detail-panel"):
            ui.label(detail["title"]).classes("text-lg font-bold")
            meta = [str(detail["year"] or ""), detail["venue"], detail["item_type"]]
            ui.label(" · ".join(part for part in meta if part)).classes(
                "text-sm text-gray-600"
            )
            if detail["authors"]:
                ui.label(detail["authors"]).classes("text-sm")
            url = doi_to_url(detail["doi"]) if detail["doi"] else None
            if url:
                ui.link(detail["doi"], url, new_tab=True).classes("text-sm")
            if detail["tags"]:
                ui.label(f"Tags: {detail['tags']}").classes("text-xs text-gray-500")
            ui.label(detail["abstract"] or "No abstract.").classes(
                "text-sm whitespace-pre-wrap max-h-48 overflow-auto"
            )
            with ui.row().classes("items-center gap-2"):
                for label, value, marker in (
                    ("Include (I)", INCLUDE, "decide-include"),
                    ("Exclude (E)", EXCLUDE, "decide-exclude"),
                    ("Maybe (M)", MAYBE, "decide-maybe"),
                ):
                    button = ui.button(
                        label, on_click=lambda _, v=value: self.decide(v)
                    ).props(f"color={DECISION_COLOURS[value]}")
                    if not decision or decision.decision != value:
                        button.props("outline")
                    button.mark(marker)
                ui.button("Clear", on_click=lambda: self.decide(None)).props(
                    "flat"
                ).mark("decide-clear")
            self.note = (
                ui.textarea(
                    "Note (saved with the decision)",
                    value=decision.note if decision else "",
                )
                .props("outlined autogrow")
                .classes("w-full")
                .mark("decision-note")
            )
            self.note.on("blur", self.save_note)

    @ui.refreshable_method
    def orphans_panel(self) -> None:
        """Decisions whose paper is no longer in the results."""
        if not self.session.orphans:
            return
        with (
            ui.expansion(
                f"{len(self.session.orphans)} decision(s) on papers no longer in the results",
                icon="warning",
            )
            .classes("w-full")
            .mark("orphans")
        ):
            for key in list(self.session.orphans):
                decision = self.session.decision_of(key)
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"{key} — {decision.decision}").classes("text-sm")
                    ui.button("Forget", on_click=lambda _, k=key: self.forget(k)).props(
                        "flat dense"
                    )

    # -- state updates --------------------------------------------------

    def update_counters(self) -> None:
        """Refresh the counters line and the progress bar."""
        counts = self.session.counts()
        self.counters.set_text(
            f"Included {counts[INCLUDE]} · Excluded {counts[EXCLUDE]} · "
            f"Maybe {counts[MAYBE]} · Undecided {counts['undecided']}"
        )
        total = counts["total"] or 1
        self.progress.set_value((counts["total"] - counts["undecided"]) / total)

    def select(self, key: str | None) -> None:
        """Make ``key`` the current paper (detail panel and grid selection)."""
        if key is None or key == self.current:
            return
        self.current = key
        self.detail_panel.refresh()
        script = (
            f"const g = getElement({self.grid.id}).api; const n = g.getRowNode({json.dumps(key)});"
            "if (n) { n.setSelected(true); g.ensureNodeVisible(n); }"
        )
        ui.run_javascript(script)

    async def on_grid_selection(self, _: events.GenericEventArguments) -> None:
        """A row was clicked in the grid."""
        row = await self.grid.get_selected_row()
        if row and row["paper_key"] != self.current:
            self.save_note()
            self.current = row["paper_key"]
            self.detail_panel.refresh()

    async def sync_order(self, _: events.GenericEventArguments) -> None:
        """Remember the grid's displayed order (after sort / column filter)."""
        script = (
            f"const ids = []; getElement({self.grid.id}).api"
            ".forEachNodeAfterFilterAndSort((n) => ids.push(n.id)); return ids;"
        )
        with contextlib.suppress(TimeoutError):
            self.order = await ui.run_javascript(script)

    def save_note(self, _=None) -> None:
        """Save the note of the current paper if it has a decision."""
        if self.current is not None and self.session.update_note(
            self.current, self.note.value or ""
        ):
            ui.notify("Note saved", timeout=1000)

    def decide(self, decision: str | None) -> None:
        """Apply ``decision`` to the current paper and go to the next undecided one."""
        key = self.current
        if key is None:
            return
        try:
            row = self.session.decide(key, decision, self.note.value or "")
        except Exception as exc:
            show_error("Cannot save the decision", exc)
            return
        self.update_counters()
        successor = self.session.next_undecided(self.order, key) if decision else None
        hidden = not (
            self.decision_filter == FILTER_ALL
            or self.decision_filter == (decision or FILTER_UNDECIDED)
        )
        if hidden:
            self.grid.run_grid_method(
                "applyTransaction", {"remove": [{"paper_key": key}]}
            )
            self.order = [k for k in self.order if k != key]
        else:
            self.grid.run_row_method(key, "setDataValue", "decision", row["decision"])
        if successor is not None and successor != key:
            self.current = None  # force the detail panel to follow
            self.select(successor)
        else:
            self.detail_panel.refresh()
            if decision and self.session.counts()["undecided"] == 0:
                ui.notify("All papers are screened")

    def forget(self, key: str) -> None:
        """Delete an orphan decision."""
        self.session.forget(key)
        self.orphans_panel.refresh()

    # -- filters and keyboard -------------------------------------------

    def refill(self) -> None:
        """Reload the grid rows from the current filters."""
        rows = self.session.visible_rows(self.decision_filter, self.query)
        self.order = [row["paper_key"] for row in rows]
        self.grid.options["rowData"] = rows
        self.grid.update()
        if self.current not in self.order:
            self.current = None
            self.select(self.order[0] if self.order else None)
            if not self.order:
                self.detail_panel.refresh()

    def on_filter(self, event: events.ValueChangeEventArguments) -> None:
        """Decision filter changed."""
        self.decision_filter = event.value
        self.refill()

    def on_search(self, event: events.ValueChangeEventArguments) -> None:
        """Search text changed."""
        self.query = event.value or ""
        self.refill()

    def move(self, step: int) -> None:
        """Select the previous (-1) or next (+1) paper."""
        if not self.order:
            return
        index = self.order.index(self.current) if self.current in self.order else -1
        target = self.order[min(max(index + step, 0), len(self.order) - 1)]
        self.save_note()
        self.select(target)

    def on_key(self, event: events.KeyEventArguments) -> None:
        """Keyboard shortcuts (the keyboard element ignores text inputs)."""
        if not event.action.keydown:
            return
        key = str(event.key.name).lower()
        if key in KEY_DECISIONS:
            self.decide(KEY_DECISIONS[key])
        elif key in ("arrowdown", "j"):
            self.move(1)
        elif key in ("arrowup", "k"):
            self.move(-1)
