"""Command-line helpers: shared ``--config/--keys`` options and ``scilex config``."""

import argparse
import os


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--config`` and ``--keys`` options to ``parser``."""
    group = parser.add_argument_group("configuration files")
    group.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to scilex.yml (default: $SCILEX_CONFIG, then ./scilex.yml)",
    )
    group.add_argument(
        "--keys",
        metavar="PATH",
        default=None,
        help="Path to keys.yml (default: $SCILEX_KEYS, then ~/.config/scilex/keys.yml)",
    )


def apply_config_arguments(args: argparse.Namespace) -> None:
    """Publish ``--config`` / ``--keys`` through ``SCILEX_CONFIG`` / ``SCILEX_KEYS``.

    Every configuration loader reads these variables, so one assignment here
    reaches all of them (including code running in worker threads).
    """
    if getattr(args, "config", None):
        os.environ["SCILEX_CONFIG"] = str(args.config)
    if getattr(args, "keys", None):
        os.environ["SCILEX_KEYS"] = str(args.keys)
