#!/usr/bin/env python3
"""
Created on Fri Feb 10 10:57:49 2023

@author: cringwal
         aollagnier

@version: 1.0.1
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import yaml
from datetime import datetime

from src.crawlers.aggregate import *
from src.crawlers.collector_collection import CollectCollection
from src.crawlers.utils import load_all_configs
from src.logging_config import setup_logging, log_section

# Set up logging configuration with environment variable support
# LOG_LEVEL=DEBUG python src/run_collecte.py    # For debugging
# LOG_LEVEL=WARNING python src/run_collecte.py  # For quiet mode
# LOG_COLOR=false python src/run_collecte.py    # Disable colors
setup_logging()

# Define the configuration files to load
config_files = {
    "main_config": "scilex.config.yml",
    "api_config": "api.config.yml",
}
# Load configurations
configs = load_all_configs(config_files)

# Access individual configurations
main_config = configs["main_config"]
api_config = configs["api_config"]

# Extract values from the main configuration
output_dir = main_config["output_dir"]
collect = main_config["collect"]
# aggregate = main_config['aggregate']
years = main_config["years"]
keywords = main_config["keywords"]
apis = main_config["apis"]


# Use the configuration values
if collect:
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

        # saving the config
        with open(os.path.join(output_dir, "config_used.yml"), "w") as f:
            yaml.dump(main_config, f)

    path = output_dir


# Print to check the loaded values
print(f"Output Directory: {output_dir}")
print(f"Collect: {collect}")
# print(f"Aggregate: {aggregate}")
print(f"Years: {years}")
print(f"Keywords: {keywords}")
print(f"APIS: {apis}")


def main():
    """Main function to run collection - required for multiprocessing on macOS/Windows"""
    logger = logging.getLogger(__name__)
    start_time = datetime.now()

    # Log collection start
    log_section(logger, "SciLEx Systematic Review Collection")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Configuration: {len(keywords[0]) if keywords else 0} keywords, {len(years)} years, {len(apis)} APIs")

    colle_col = CollectCollection(main_config, api_config)

    # Check if async should be disabled (default is now ASYNC)
    # Set USE_ASYNC_COLLECTION=false to use legacy sync pipeline
    use_async = os.environ.get('USE_ASYNC_COLLECTION', 'true').lower() != 'false'

    logger.info(f"Pipeline mode: {'ASYNC (optimized)' if use_async else 'SYNC (legacy)'}")

    if use_async:
        asyncio.run(colle_col.run_async_collection())
    else:
        colle_col.create_collects_jobs()

    # Log completion
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    log_section(logger, "Collection Complete")
    logger.info(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f}m)")


async def main_async():
    """Async entry point for collection"""
    logger = logging.getLogger(__name__)
    start_time = datetime.now()

    log_section(logger, "SciLEx Systematic Review Collection (ASYNC)")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    colle_col = CollectCollection(main_config, api_config)
    await colle_col.run_async_collection()

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    log_section(logger, "Collection Complete")
    logger.info(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    # Check for async flag (default is now ASYNC - set to 'false' to disable)
    use_async = os.environ.get('USE_ASYNC_COLLECTION', 'true').lower() != 'false'

    # This guard is required for multiprocessing on macOS/Windows (spawn mode)
    if use_async:
        asyncio.run(main_async())
    else:
        main()
