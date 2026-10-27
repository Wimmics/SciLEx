"""Entry point of the SciLEx desktop application (``scilex-gui``)."""

import argparse
import logging
import multiprocessing
import os
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)

WINDOW_SIZE = (1280, 800)


def build_root(ctx) -> Callable[[], None]:
    """Return the NiceGUI root function routing between the screens."""
    from nicegui import ui

    from scilex.gui.pages import home, review

    def root() -> None:
        ui.sub_pages(
            {
                "/": home.render,
                "/review/{review_id}": review.render,
                "/review/{review_id}/{step}": review.render,
            },
            data={"ctx": ctx},
        ).classes("w-full")  # flex column with align-items:flex-start would shrink-wrap

    return root


def build_parser() -> argparse.ArgumentParser:
    """Command-line options of ``scilex-gui``."""
    parser = argparse.ArgumentParser(
        prog="scilex-gui", description="SciLEx desktop application"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="check the installation without opening a window, then exit",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="open the UI in a browser tab instead of a native window (debugging)",
    )
    parser.add_argument("--port", type=int, default=None, help="port (browser mode)")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="browser mode: do not open a browser tab (automated UI tests)",
    )
    # Internal: run by the app itself in a child process (see native_window.py).
    parser.add_argument("--probe-native", action="store_true", help=argparse.SUPPRESS)
    return parser


def _use_native_window(args: argparse.Namespace) -> bool:
    """False in browser mode, or when no native window can open on this machine."""
    if args.browser:
        return False
    from scilex.gui.native_window import native_window_problem

    problem = native_window_problem()
    if problem is None:
        return True
    message = f"Cannot open the SciLEx window, opening it in your web browser instead. Reason: {problem}"
    logger.warning(message)
    print(message, file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    """Start the desktop application."""
    # Must come first: in the frozen app every multiprocessing worker
    # re-executes this entry point.
    multiprocessing.freeze_support()
    # A windowed frozen app has no console: give writers somewhere to go.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    args = build_parser().parse_args(argv)

    if args.probe_native:
        from scilex.gui.native_window import run_probe

        return run_probe()

    if args.self_test:
        from scilex.gui.self_test import run_self_test

        return run_self_test()

    from nicegui import app, ui

    from scilex.gui.components.branding import ICON_PATH
    from scilex.gui.services.diagnostics import setup_file_logging
    from scilex.gui.state import AppContext

    log_path = setup_file_logging()
    logger.info("Starting SciLEx GUI (log file: %s)", log_path)
    app.on_exception(lambda exc: logger.error("Unhandled UI error", exc_info=exc))

    native = _use_native_window(args)
    ctx = AppContext(native=native)
    if native:
        # pywebview disables text selection by default: logs could not be copied.
        app.native.window_args["text_select"] = True
    ui.run(
        build_root(ctx),
        title="SciLEx",
        favicon=ICON_PATH,
        native=native,
        window_size=WINDOW_SIZE if native else None,
        port=args.port,
        reload=False,
        show=not native and not args.no_open,
    )
    return 0


# Not "__mp_main__": spawned multiprocessing children import this module
# under that name and must not start a second app.
if __name__ == "__main__":
    sys.exit(main())
