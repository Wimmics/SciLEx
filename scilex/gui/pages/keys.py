"""API keys screen: edit the global keys.yml without opening it."""

from nicegui import run, ui

from scilex.gui.components.errors import show_error
from scilex.gui.services import keys_editor as editor
from scilex.gui.services.workspace import Review
from scilex.gui.state import AppContext


def _show_result(label: ui.label, ok: bool, message: str) -> None:
    label.set_text(("✓ " if ok else "✗ ") + message)
    label.classes(replace="text-sm " + ("text-positive" if ok else "text-negative"))


class _KeyRows:
    """The editable list of keys of one API (password inputs, add/remove)."""

    def __init__(self, api: str, initial: list[str]):
        self.api = api
        self.inputs: list[ui.input] = []
        self.container = ui.column().classes("w-full gap-1")
        for key in initial or [""]:
            self.add(key)

    def add(self, value: str = "") -> None:
        first = not self.inputs
        with self.container, ui.row().classes("w-full items-center no-wrap") as row:
            field = ui.input(
                "Key" if first else "Additional key",
                value=value,
                password=True,
                password_toggle_button=True,
            ).classes("grow")
            field.mark(
                f"key-{self.api}" if first else f"key-{self.api}-{len(self.inputs)}"
            )
            ui.button(icon="delete", on_click=lambda: self._remove(field, row)).props(
                "flat round dense"
            )
        self.inputs.append(field)

    def _remove(self, field: ui.input, row: ui.row) -> None:
        if len(self.inputs) == 1:
            field.set_value("")
            return
        self.inputs.remove(field)
        self.container.remove(row)

    def values(self) -> list[str]:
        return [field.value or "" for field in self.inputs]


def render(ctx: AppContext, review: Review) -> None:
    """Draw the API keys screen."""
    try:
        data = editor.load_keys()
        load_error = None
    except Exception as exc:
        data, load_error = {}, exc
    overrides = editor.env_overrides()

    ui.label("API keys").classes("text-2xl font-bold")
    ui.label(
        "Keys are global: they are shared by all your reviews and stored in one file."
    ).classes("text-gray-500")
    ui.label(f"File: {editor.keys_path()}").classes("text-sm font-mono")
    if load_error is not None:
        ui.label(f"The keys file could not be read: {load_error}").classes(
            "text-negative"
        )

    rows: dict[str, _KeyRows] = {}

    async def test_api(spec: editor.ApiSpec, result: ui.label) -> None:
        keys = [key for key in rows[spec.name].values() if key.strip()]
        if not keys:
            _show_result(result, False, "Enter a key first.")
            return
        result.set_text("Testing…")
        outcomes = [await run.io_bound(editor.check_key, spec.name, k) for k in keys]
        accepted = sum(ok for ok, _ in outcomes)
        message = (
            outcomes[0][1]
            if len(outcomes) == 1
            else f"{accepted}/{len(outcomes)} keys accepted."
        )
        _show_result(result, accepted == len(outcomes), message)

    for spec in editor.API_SPECS:
        env_name = overrides.get(f"{spec.name}.{spec.field}")
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.label(spec.label).classes("text-lg font-bold")
                ui.badge("required" if spec.required else "optional").props(
                    "color=negative" if spec.required else "color=grey"
                )
                ui.link("Get a key", spec.help_url, new_tab=True).classes("text-sm")
            ui.label(spec.note).classes("text-gray-500 text-sm")
            if env_name:
                ui.label(
                    f"Overridden by the environment variable {env_name}: the "
                    "value saved here is ignored while it is set."
                ).classes("text-warning text-sm").mark(f"env-{spec.name}")
            key_rows = rows[spec.name] = _KeyRows(
                spec.name,
                editor.get_keys_list(data.get(spec.name), spec.field),
            )
            with ui.row().classes("items-center gap-2"):
                ui.button("Add another key", icon="add", on_click=key_rows.add).props(
                    "flat dense"
                )
                if spec.testable:
                    result = ui.label("").classes("text-sm")
                    ui.button(
                        "Test",
                        icon="network_check",
                        on_click=lambda _=None, s=spec, r=result: test_api(s, r),
                    ).props("outline dense").mark(f"key-test-{spec.name}")

    zotero = data.get("Zotero") or {}
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-2"):
            ui.label("Zotero").classes("text-lg font-bold")
            ui.badge("optional").props("color=grey")
            ui.link("Get a key", editor.ZOTERO_HELP_URL, new_tab=True).classes(
                "text-sm"
            )
        ui.label("Needed only to push the results to a Zotero library.").classes(
            "text-gray-500 text-sm"
        )
        zotero_key = (
            ui.input(
                "API key",
                value=str(zotero.get("api_key") or ""),
                password=True,
                password_toggle_button=True,
            )
            .classes("w-full")
            .mark("key-Zotero")
        )
        zotero_id = (
            ui.input("Library id", value=str(zotero.get("user_id") or ""))
            .classes("w-full")
            .mark("zotero-user-id")
        )
        zotero_mode = ui.select(
            ["user", "group"],
            label="Library type",
            value=zotero.get("user_mode") or "user",
        ).mark("zotero-user-mode")
        zotero_result = ui.label("").classes("text-sm")

        async def test_zotero() -> None:
            outcome = await run.io_bound(
                editor.check_zotero,
                zotero_key.value or "",
                zotero_id.value or "",
                zotero_mode.value,
            )
            _show_result(zotero_result, *outcome)

        ui.button("Test", icon="network_check", on_click=test_zotero).props(
            "outline dense"
        ).mark("key-test-Zotero")

    email_inputs: dict[str, ui.input] = {}
    with ui.card().classes("w-full"):
        ui.label("Contact e-mail").classes("text-lg font-bold")
        for block_name, (field_name, note) in editor.EMAIL_BLOCKS.items():
            email_inputs[block_name] = (
                ui.input(
                    f"{block_name} ({note})",
                    value=str((data.get(block_name) or {}).get(field_name) or ""),
                )
                .classes("w-full")
                .mark(f"key-{block_name}")
            )

    with ui.expansion("Advanced: rate limits", icon="tune").classes("w-full"):
        ui.label(
            "Requests per second, per API. Leave empty to keep the defaults."
        ).classes("text-gray-500 text-sm")
        limit_inputs = {
            name: ui.number(name, value=value, min=0.01)
            for name, value in sorted((data.get("rate_limits") or {}).items())
        }
        new_api = ui.input("Add an API name (e.g. SemanticScholar)")
        new_value = ui.number("Requests per second", min=0.01)

    def collect_edits() -> dict:
        updated = dict(data)
        for spec in editor.API_SPECS:
            editor.set_keys_list(
                updated, spec.name, rows[spec.name].values(), spec.field
            )
        zotero_block = dict(updated.get("Zotero") or {})
        for field_name, widget in (("api_key", zotero_key), ("user_id", zotero_id)):
            text = (widget.value or "").strip()
            if text:
                zotero_block[field_name] = text
            else:
                zotero_block.pop(field_name, None)
        if zotero_block:
            zotero_block["user_mode"] = zotero_mode.value or "user"
            updated["Zotero"] = zotero_block
        else:
            updated.pop("Zotero", None)
        for block_name, (field_name, _) in editor.EMAIL_BLOCKS.items():
            editor.set_keys_list(
                updated, block_name, [email_inputs[block_name].value or ""], field_name
            )
        limits = {n: w.value for n, w in limit_inputs.items() if w.value}
        if (new_api.value or "").strip() and new_value.value:
            limits[new_api.value.strip()] = new_value.value
        if limits:
            updated["rate_limits"] = limits
        else:
            updated.pop("rate_limits", None)
        return updated

    def save() -> None:
        try:
            updated = collect_edits()
            path = editor.save_keys(updated)
        except ValueError as exc:
            show_error("Invalid keys", exc, expected=True)
            return
        except Exception as exc:
            show_error("Cannot save the keys", exc)
            return
        data.clear()
        data.update(updated)
        ui.notify(f"Keys saved to {path}", type="positive")

    ui.button("Save", icon="save", on_click=save).mark("keys-save")
