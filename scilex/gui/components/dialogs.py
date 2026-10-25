"""Dialogs built on each click."""

from nicegui import ui


def one_shot_dialog() -> ui.dialog:
    """Return a dialog deleted once closed.

    Dialogs created on each click would otherwise pile up in the page
    (hidden, but kept in memory and sent to the browser).
    """
    dialog = ui.dialog()

    def delete_when_closed(event) -> None:
        if not event.value and not dialog.is_deleted:
            dialog.delete()

    dialog.on_value_change(delete_when_closed)
    return dialog
