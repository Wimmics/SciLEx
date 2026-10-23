"""Configure screen: edit the review's ``scilex.yml`` through a form."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import yaml
from nicegui import ui
from pydantic import BaseModel

from scilex.gui.components.errors import show_error
from scilex.gui.services import config_editor as editor
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext
from scilex.settings.presets import PRESETS
from scilex.settings.schema import ScilexSettings, SettingsError

NONE_CHOICE = ""  # select value standing for "no value"


def _label_of(name: str) -> str:
    return name.replace("_", " ").capitalize()


def render(ctx: AppContext, review: Review) -> None:
    """Draw the Configure screen of ``review``."""
    ui.label("Configure").classes("text-2xl font-bold")
    try:
        data = editor.load_editable(review)
        known_origins = editor.origins(review)
    except (SettingsError, FileNotFoundError) as exc:
        show_error("Cannot read scilex.yml", exc, expected=True)
        ui.label(str(exc)).classes("text-negative whitespace-pre-wrap")
        return
    ui.label(
        "Edit the settings of this review. Saving rewrites scilex.yml: only the "
        "values that differ from the defaults are written, and comments in the "
        "file are not kept."
    ).classes("text-gray-500")

    error_labels: dict[str, ui.label] = {}

    # -- state access ------------------------------------------------------
    def get(path: tuple[str, ...]) -> Any:
        node: Any = data
        for key in path:
            node = node[key]
        return node

    def put(path: tuple[str, ...], value: Any) -> None:
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        revalidate()

    def error_slot(path: tuple[str, ...]) -> None:
        dotted = ".".join(path)
        label = ui.label().classes("text-negative text-xs").mark(f"error-{dotted}")
        label.set_visibility(False)
        error_labels[dotted] = label

    def caption(path: tuple[str, ...], label: str) -> None:
        """Label of a field with its help tooltip and origin badge."""
        dotted = ".".join(path)
        with ui.row().classes("items-center gap-2"):
            ui.label(label).classes("text-sm font-medium")
            origin = editor.origin_of(dotted, known_origins)
            if origin != "default":
                ui.badge("from preset" if origin == "preset" else "from file").props(
                    "outline"
                ).classes("text-xs").mark(f"origin-{dotted}")
            help_text = editor.FIELD_HELP.get(dotted)
            if help_text:
                with ui.icon("help_outline", size="xs").classes("text-gray-500"):
                    ui.tooltip(help_text).classes("text-sm")

    # -- reusable widgets --------------------------------------------------
    def chips_editor(
        values: list, on_change: Callable[[list], None], marker: str, hint: str
    ) -> None:
        """Editable list of terms shown as removable chips."""

        @ui.refreshable
        def chips() -> None:
            with ui.row().classes("items-center gap-1"):
                for index, value in enumerate(values):

                    def remove(event, position=index) -> None:
                        if not event.value:
                            del values[position]
                            on_change(values)
                            chips.refresh()

                    ui.chip(str(value), removable=True, on_value_change=remove).mark(
                        f"chip-{marker}-{index}"
                    )

        chips()

        def add() -> None:
            text = entry.value.strip()
            if text and text not in values:
                values.append(text)
                on_change(values)
                chips.refresh()
            entry.set_value("")

        with ui.row().classes("items-center gap-2"):
            entry = (
                ui.input(placeholder=hint)
                .props("dense outlined")
                .mark(f"input-{marker}")
            )
            entry.on("keydown.enter", add)
            ui.button(icon="add", on_click=add).props("flat dense round").mark(
                f"add-{marker}"
            )

    def number_input(path: tuple[str, ...], spec: editor.FieldSpec, label: str) -> None:
        def changed(event) -> None:
            value = event.value
            if value is not None and spec.kind == "int" and float(value).is_integer():
                value = int(value)
            put(path, value)

        ui.number(label, value=get(path), on_change=changed).props(
            "dense outlined clearable" if spec.nullable else "dense outlined"
        ).classes("w-64").mark(f"field-{'.'.join(path)}")

    def text_input(path: tuple[str, ...], spec: editor.FieldSpec, label: str) -> None:
        def changed(event) -> None:
            value = event.value
            put(path, (value or None) if spec.nullable else (value or ""))

        ui.input(label, value=get(path) or "", on_change=changed).props(
            "dense outlined"
        ).classes("w-96").mark(f"field-{'.'.join(path)}")

    def choice_input(path: tuple[str, ...], spec: editor.FieldSpec, label: str) -> None:
        options = {option: option for option in spec.options}
        if spec.nullable:
            options = {NONE_CHOICE: "(none)", **options}
        current = get(path)

        def changed(event) -> None:
            put(path, None if event.value == NONE_CHOICE else event.value)

        ui.select(
            options,
            label=label,
            value=NONE_CHOICE if current is None else current,
            on_change=changed,
        ).props("dense outlined").classes("w-64").mark(f"field-{'.'.join(path)}")

    def multichoice_input(
        path: tuple[str, ...], spec: editor.FieldSpec, label: str
    ) -> None:
        ui.select(
            list(spec.options),
            label=label,
            value=list(get(path) or []),
            multiple=True,
            on_change=lambda event: put(path, list(event.value)),
        ).props("dense outlined use-chips").classes("w-96").mark(
            f"field-{'.'.join(path)}"
        )

    def intlist_input(
        path: tuple[str, ...], spec: editor.FieldSpec, label: str
    ) -> None:
        def changed(event) -> None:
            parts = [
                part.strip() for part in (event.value or "").split(",") if part.strip()
            ]
            try:
                put(path, [int(part) for part in parts])
            except ValueError:
                put(path, parts)  # shown as a validation error

        ui.input(
            label + " (comma separated)",
            value=", ".join(str(v) for v in get(path) or []),
            on_change=changed,
        ).props("dense outlined").classes("w-64").mark(f"field-{'.'.join(path)}")

    def strlist_input(
        path: tuple[str, ...], spec: editor.FieldSpec, label: str
    ) -> None:
        values = list(get(path) or [])

        def changed(items: list) -> None:
            put(path, (list(items) or None) if spec.nullable else list(items))

        chips_editor(values, changed, ".".join(path), "Add an item")

    def floatmap_input(
        path: tuple[str, ...], spec: editor.FieldSpec, label: str
    ) -> None:
        with ui.row().classes("gap-3"):
            for key in list(get(path)):
                ui.number(
                    key,
                    value=get(path)[key],
                    on_change=lambda event, key=key: put((*path, key), event.value),
                ).props("dense outlined").classes("w-40").mark(
                    f"field-{'.'.join(path)}.{key}"
                )

    def yaml_input(path: tuple[str, ...], spec: editor.FieldSpec, label: str) -> None:
        current = get(path)
        text = "" if current in (None, {}) else yaml.safe_dump(current).strip()

        def changed(event) -> None:
            raw = (event.value or "").strip()
            if not raw:
                put(path, None if spec.nullable else {})
                return
            try:
                put(path, yaml.safe_load(raw))
            except yaml.YAMLError:
                put(path, raw)  # reported as "not a valid mapping"

        ui.textarea(label + " (YAML)", value=text, on_change=changed).props(
            "dense outlined"
        ).classes("w-96").mark(f"field-{'.'.join(path)}")

    def bool_input(path: tuple[str, ...], spec: editor.FieldSpec, label: str) -> None:
        ui.switch(
            label, value=bool(get(path)), on_change=lambda event: put(path, event.value)
        ).mark(f"field-{'.'.join(path)}")

    builders = {
        "bool": bool_input,
        "int": number_input,
        "float": number_input,
        "str": text_input,
        "choice": choice_input,
        "multichoice": multichoice_input,
        "intlist": intlist_input,
        "strlist": strlist_input,
        "floatmap": floatmap_input,
        "yaml": yaml_input,
    }

    def generic_field(path: tuple[str, ...], annotation: Any) -> None:
        spec = editor.describe_field(annotation)
        label = _label_of(path[-1])
        with ui.column().classes("gap-0"):
            if spec.kind != "bool":
                caption(path, label)
            builders[spec.kind](path, spec, label)
            error_slot(path)
            if spec.kind == "bool":
                help_text = editor.FIELD_HELP.get(".".join(path))
                if help_text:
                    ui.label(help_text).classes("text-xs text-gray-500")

    def model_fields(model: type[BaseModel], prefix: tuple[str, ...]) -> None:
        for name, field in model.model_fields.items():
            path = (*prefix, name)
            core, _ = editor._unwrap(field.annotation)
            if isinstance(core, type) and issubclass(core, BaseModel):
                ui.label(_label_of(name)).classes("font-bold mt-2")
                with ui.column().classes("pl-4 gap-2 border-l-2"):
                    model_fields(core, path)
            else:
                generic_field(path, field.annotation)

    # -- Search section ------------------------------------------------------
    with ui.card().classes("w-full gap-3").mark("section-search"):
        ui.label("Search").classes("text-xl font-bold")

        ui.input(
            "Review name",
            value=data["name"],
            on_change=lambda event: put(("name",), event.value),
        ).props("dense outlined").classes("w-96").mark("config-name")
        error_slot(("name",))

        # Keyword groups
        ui.label("Keywords").classes("font-bold mt-2")
        rule_label = ui.label().classes("text-sm text-gray-600").mark("keyword-rule")

        @ui.refreshable
        def keyword_groups() -> None:
            groups = get(("search", "keywords"))
            rule_label.set_text(
                "A paper is kept if it contains at least one term of group 1 AND "
                "at least one term of group 2."
                if len(groups) > 1
                else "A paper is kept if it contains at least one of these terms. "
                "Add a second group to require two topics at once."
            )
            for index in range(len(groups)):
                if index:
                    ui.label("AND").classes("font-bold text-primary")
                with (
                    ui.card()
                    .props("flat bordered")
                    .classes("w-full")
                    .mark(f"keyword-group-{index}")
                ):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(f"Group {index + 1}: any of these terms").classes(
                            "text-sm font-medium"
                        )
                        if len(groups) > 1:
                            ui.button(
                                "Remove group",
                                icon="delete",
                                on_click=lambda position=index: remove_group(position),
                            ).props("flat dense color=negative").mark(
                                f"remove-group-{index}"
                            )
                    chips_editor(
                        groups[index],
                        lambda _items: put(("search", "keywords"), groups),
                        f"keyword-{index}",
                        "Type a term, press Enter",
                    )
            if len(groups) < editor.MAX_KEYWORD_GROUPS:
                ui.button(
                    "Add a second group (AND)", icon="add", on_click=lambda: add_group()
                ).props("outline dense").mark("add-group")

        def add_group() -> None:
            get(("search", "keywords")).append([])
            put(("search", "keywords"), get(("search", "keywords")))
            keyword_groups.refresh()

        def remove_group(position: int) -> None:
            del get(("search", "keywords"))[position]
            put(("search", "keywords"), get(("search", "keywords")))
            keyword_groups.refresh()

        keyword_groups()
        error_slot(("search", "keywords"))

        # Years
        ui.label("Years").classes("font-bold mt-2")
        years = get(("search", "years"))
        as_range = editor.years_as_range(years)
        year_state = {"mode": "range" if as_range or not years else "list"}
        today_year = date.today().year
        start_end = list(as_range or (today_year - 2, today_year))

        def update_range() -> None:
            first, last = start_end
            if first is None or last is None:
                put(("search", "years"), [])
            elif first <= last:
                put(("search", "years"), list(range(int(first), int(last) + 1)))
            else:
                put(("search", "years"), f"{int(first)}-{int(last)}")

        def update_list(event) -> None:
            parts = [p.strip() for p in (event.value or "").split(",") if p.strip()]
            try:
                put(("search", "years"), [int(p) for p in parts])
            except ValueError:
                put(("search", "years"), parts)

        mode_toggle = ui.toggle(
            {"range": "Range", "list": "Specific years"}, value=year_state["mode"]
        ).mark("years-mode")
        with ui.row().classes("items-center gap-3") as range_row:
            ui.number(
                "From",
                value=start_end[0],
                precision=0,
                on_change=lambda e: (start_end.__setitem__(0, e.value), update_range()),
            ).props("dense outlined").classes("w-32").mark("years-start")
            ui.number(
                "To",
                value=start_end[1],
                precision=0,
                on_change=lambda e: (start_end.__setitem__(1, e.value), update_range()),
            ).props("dense outlined").classes("w-32").mark("years-end")
        list_input = (
            ui.input(
                "Years (comma separated)",
                value=", ".join(str(y) for y in years)
                if isinstance(years, list)
                else "",
                on_change=update_list,
            )
            .props("dense outlined")
            .classes("w-96")
            .mark("years-list")
        )

        def switch_mode(event=None) -> None:
            is_range = mode_toggle.value == "range"
            range_row.set_visibility(is_range)
            list_input.set_visibility(not is_range)
            if is_range:
                update_range()
            else:
                update_list(type("E", (), {"value": list_input.value})())

        mode_toggle.on_value_change(switch_mode)
        range_row.set_visibility(year_state["mode"] == "range")
        list_input.set_visibility(year_state["mode"] == "list")
        error_slot(("search", "years"))

        # APIs
        ui.label("Sources (APIs)").classes("font-bold mt-2")
        selected_apis = set(get(("search", "apis")))

        def toggle_api(name: str, checked: bool) -> None:
            (selected_apis.add if checked else selected_apis.discard)(name)
            put(
                ("search", "apis"),
                [api for api in editor.API_NAMES if api in selected_apis],
            )

        with ui.row().classes("gap-x-4"):
            for api_name in editor.API_NAMES:
                ui.checkbox(
                    api_name,
                    value=api_name in selected_apis,
                    on_change=lambda event, api_name=api_name: toggle_api(
                        api_name, event.value
                    ),
                ).mark(f"api-{api_name}")
        error_slot(("search", "apis"))

        # Other search fields
        for name in (
            "max_articles_per_query",
            "bonus_keywords",
            "semantic_scholar_mode",
            "since",
        ):
            generic_field(
                ("search", name),
                ScilexSettings.model_fields["search"]
                .annotation.model_fields[name]
                .annotation,
            )

    # -- Other sections ---------------------------------------------------------
    with (
        ui.expansion("General", icon="folder")
        .classes("w-full")
        .props("popup")
        .mark("section-general")
    ):
        generic_field(("output_dir",), str)
        ui.select(
            {NONE_CHOICE: "(none)", **{name: name for name in PRESETS}},
            label="Preset",
            value=data.get("preset") or NONE_CHOICE,
            on_change=lambda event: put(
                ("preset",), None if event.value == NONE_CHOICE else event.value
            ),
        ).props("dense outlined").classes("w-64").mark("field-preset")
        ui.label(editor.FIELD_HELP["preset"]).classes("text-xs text-gray-500")
        error_slot(("preset",))

    for section_name, section_model in editor.sections():
        with (
            ui.expansion(_label_of(section_name))
            .classes("w-full")
            .props("popup")
            .mark(f"section-{section_name}")
        ):
            model_fields(section_model, (section_name,))
            error_slot((section_name,))

    # -- Validation summary and actions ------------------------------------------
    with ui.card().classes("w-full gap-1"):

        @ui.refreshable
        def summary(problems: list[tuple[str, str]]) -> None:
            if not problems:
                ui.label("No problem found.").classes("text-positive").mark(
                    "config-valid"
                )
            for path, message in problems:
                ui.label(f"{path}: {message}").classes("text-negative text-sm").mark(
                    "config-error"
                )

        summary([])

        with ui.row().classes("items-center gap-3"):
            save_button = ui.button("Save", icon="save").mark("config-save")
            ui.button(
                "Go to ② Collect",
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to(f"/review/{review.id}/collect"),
            ).props("outline").mark("config-next")

    def revalidate() -> None:
        problems = editor.validate(data)
        save_button.set_enabled(not problems)
        summary.refresh(problems)
        for dotted, label in error_labels.items():
            messages = [
                message
                for path, message in problems
                if path == dotted or path.startswith(f"{dotted}.")
            ]
            label.set_text("; ".join(messages))
            label.set_visibility(bool(messages))

    def save() -> None:
        try:
            editor.save(review, data)
        except SettingsError as exc:
            show_error("Cannot save scilex.yml", exc, expected=True)
            return
        except OSError as exc:
            show_error("Cannot save scilex.yml", exc)
            return
        ui.notify(f"Saved {review.config_path.name}", type="positive")

    save_button.on_click(save)
    revalidate()
