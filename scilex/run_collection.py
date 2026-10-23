#!/usr/bin/env python3
"""SciLEx collection entry point.

Crawls all configured APIs for papers matching search keywords.
No module-level side effects — safe to import without triggering I/O.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from scilex.config import SciLExConfig
from scilex.config_defaults import DEFAULT_COLLECT_ENABLED, DEFAULT_OUTPUT_DIR
from scilex.logging_config import log_section, setup_logging
from scilex.pipeline.orchestrator import run_collection


def main():
    """Run collection — required for multiprocessing on macOS/Windows."""
    setup_logging()

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="SciLEx paper collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Start a new collection using scilex.config.yml\n"
            "  python -m scilex collect\n\n"
            "  # Resume a previous collection by name\n"
            "  python -m scilex collect --resume CulturalHeritageAItools\n\n"
            "  # Resume a previous collection by full path\n"
            "  python -m scilex collect --resume C:\\output\\CulturalHeritageAItools\n"
        ),
    )
    parser.add_argument(
        "--resume",
        metavar="COLLECT",
        help=(
            "Resume a previous collection. Accepts a collection name (looked up "
            "under output_dir) or a full path to the collection directory. "
            "The saved config_used.yml is loaded automatically."
        ),
    )
    args = parser.parse_args()

    # Load configuration (from a previous collection when resuming)
    try:
        config = SciLExConfig.from_collection(args.resume)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    main_config = config.main

    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    collect = main_config.get("collect", DEFAULT_COLLECT_ENABLED)
    years = main_config["years"]
    keywords = main_config["keywords"]
    apis = main_config["apis"]

    config_source = "scilex.config.yml" if args.resume is None else "resumed collection"
    print(f"Config source  : {config_source}")
    print(f"Output Directory: {output_dir}")
    print(f"Collect: {collect}")
    print(f"Years: {years}")
    print(f"Keywords: {keywords}")
    print(f"APIS: {apis}")

    if collect and not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    start_time = datetime.now()
    log_section(logger, "SciLEx Systematic Review Collection")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(
        f"Configuration: {len(keywords[0]) if keywords else 0} keywords, "
        f"{len(years)} years, {len(apis)} APIs"
    )

    run_label = f"resumed: {args.resume}" if args.resume else "new run"
    run_collection(config, run_label=run_label)

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    log_section(logger, "Collection Complete")
    logger.info(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total time: {elapsed:.1f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    # This guard is required for multiprocessing on macOS/Windows (spawn mode)
    main()
