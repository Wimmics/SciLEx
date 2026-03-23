#!/usr/bin/env python3
"""SciLEx collection entry point.

Crawls all configured APIs for papers matching search keywords.
No module-level side effects — safe to import without triggering I/O.
"""

import logging
import os
from datetime import datetime

import yaml

from scilex.config import SciLExConfig
from scilex.config_defaults import DEFAULT_COLLECT_ENABLED, DEFAULT_OUTPUT_DIR
from scilex.crawlers.collector_collection import CollectCollection
from scilex.logging_config import log_section, setup_logging


def main():
    """Run collection — required for multiprocessing on macOS/Windows."""
    # Set up logging (previously at module level)
    setup_logging()

    logger = logging.getLogger(__name__)

    # Load configuration (previously at module level)
    config = SciLExConfig.from_files()
    main_config = config.main
    api_config = config.api

    # Extract values from the main configuration
    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    collect = main_config.get("collect", DEFAULT_COLLECT_ENABLED)
    keywords = main_config["keywords"]
    years = main_config["years"]
    apis = main_config["apis"]

    # Prepare output directory and save config snapshot
    if collect and not os.path.isdir(output_dir):
        os.makedirs(output_dir)
        with open(os.path.join(output_dir, "config_used.yml"), "w") as f:
            yaml.dump(main_config, f)

    # Log loaded values (previously print statements)
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"Collect: {collect}")
    logger.info(f"Years: {years}")
    logger.info(f"Keywords: {keywords}")
    logger.info(f"APIs: {apis}")

    start_time = datetime.now()

    # Log collection start
    log_section(logger, "SciLEx Systematic Review Collection")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(
        f"Configuration: {len(keywords[0]) if keywords else 0} keywords, "
        f"{len(years)} years, {len(apis)} APIs"
    )

    colle_col = CollectCollection(main_config, api_config)
    colle_col.create_collects_jobs()

    # Log completion
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    log_section(logger, "Collection Complete")
    logger.info(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total time: {elapsed:.1f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    # This guard is required for multiprocessing on macOS/Windows (spawn mode)
    main()
