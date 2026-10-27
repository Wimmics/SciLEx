"""Can this machine open the native window? If not, the app uses a browser tab.

On Linux, pywebview needs Qt WebEngine (bundled in the Linux build) or GTK
with its Python bindings (system packages). Even with Qt bundled, Qt can still
abort at startup, e.g. without a display or without the ``libxcb-cursor0``
system library. Such a failure kills the window process after the server has
started, which leaves the user with nothing on screen. So on Linux the app
first opens the GUI toolkit in a short-lived child process (``--probe-native``)
and falls back to the browser when that child fails.
"""

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

PROBE_FLAG = "--probe-native"
PROBE_TIMEOUT_SECONDS = 30


def _probe_qt() -> None:
    # Same imports as pywebview's Qt backend; QtWebEngineWidgets must be
    # imported before the QApplication is created.
    from qtpy import QtWebEngineWidgets  # noqa: F401
    from qtpy.QtWidgets import QApplication

    QApplication([])


def _probe_gtk() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        raise RuntimeError("GTK cannot open the display")


def run_probe() -> int:
    """Body of ``scilex-gui --probe-native``: print the usable backend, exit 0 if any."""
    for name, probe in (("qt", _probe_qt), ("gtk", _probe_gtk)):
        try:
            probe()
        except Exception as exc:
            print(f"{name}: {type(exc).__name__}: {exc}", file=sys.stderr)
        else:
            print(name)
            return 0
    return 1


def _probe_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, PROBE_FLAG]
    return [sys.executable, "-m", "scilex.gui.app", PROBE_FLAG]


def native_window_problem() -> str | None:
    """Return why the native window cannot open here, or None if it can.

    On Linux, also sets ``PYWEBVIEW_GUI`` to the backend that passed the
    probe, so the window process does not try another one first.
    """
    if not sys.platform.startswith("linux"):
        return None  # macOS and Windows ship their own web view
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "no graphical display (DISPLAY and WAYLAND_DISPLAY are not set)"
    try:
        result = subprocess.run(
            _probe_command(),
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"the window toolkit check failed to run ({exc})"
    if result.returncode != 0:
        details = (result.stderr or "").strip()[-2000:]
        return f"no usable window toolkit (Qt or GTK):\n{details}"
    backend = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if backend in ("qt", "gtk"):
        os.environ.setdefault("PYWEBVIEW_GUI", backend)
    return None
