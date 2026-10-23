"""Entry point of the SciLEx desktop application (``scilex-gui``)."""

import argparse
import logging
import multiprocessing
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
        )

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the desktop application."""
    # Must come first: in the frozen app every multiprocessing worker
    # re-executes this entry point.
    multiprocessing.freeze_support()
    args = build_parser().parse_args(argv)

    if args.self_test:
        from scilex.gui.self_test import run_self_test

        return run_self_test()

    from nicegui import app, ui

    from scilex.gui.services.diagnostics import setup_file_logging
    from scilex.gui.state import AppContext

    log_path = setup_file_logging()
    logger.info("Starting SciLEx GUI (log file: %s)", log_path)
    app.on_exception(lambda exc: logger.error("Unhandled UI error", exc_info=exc))

    native = not args.browser
    ctx = AppContext(native=native)
    ui.run(
        build_root(ctx),
        title="SciLEx",
        native=native,
        window_size=WINDOW_SIZE if native else None,
        port=args.port,
        reload=False,
        show=not native,
    )
    return 0


# Not "__mp_main__": spawned multiprocessing children import this module
# under that name and must not start a second app.
if __name__ == "__main__":
    sys.exit(main())
