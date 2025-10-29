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

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,  # Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log message format
    datefmt="%Y-%m-%d %H:%M:%S",  # Date format
)

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
    # Log the overall process with timestamps
    logging.info(f"Systematic review search started at {datetime.now()}")
    logging.info("================BEGIN Systematic Review Search================")

    colle_col = CollectCollection(main_config, api_config)

    # Check if async should be disabled (default is now ASYNC)
    # Set USE_ASYNC_COLLECTION=false to use legacy sync pipeline
    use_async = os.environ.get('USE_ASYNC_COLLECTION', 'true').lower() != 'false'

    if use_async:
        logging.info("Using ASYNC collection pipeline (Phase 1 optimization)")
        asyncio.run(colle_col.run_async_collection())
    else:
        logging.info("Using SYNC collection pipeline (legacy - set USE_ASYNC_COLLECTION=false)")
        colle_col.create_collects_jobs()

    logging.info("================END Systematic Review Search================")
    logging.info(f"Systematic review search ended at {datetime.now()}")


async def main_async():
    """Async entry point for collection"""
    logging.info(f"Systematic review search started at {datetime.now()}")
    logging.info("================BEGIN Systematic Review Search (ASYNC)================")

    colle_col = CollectCollection(main_config, api_config)
    await colle_col.run_async_collection()

    logging.info("================END Systematic Review Search (ASYNC)================")
    logging.info(f"Systematic review search ended at {datetime.now()}")


if __name__ == "__main__":
    # Check for async flag (default is now ASYNC - set to 'false' to disable)
    use_async = os.environ.get('USE_ASYNC_COLLECTION', 'true').lower() != 'false'

    # This guard is required for multiprocessing on macOS/Windows (spawn mode)
    if use_async:
        asyncio.run(main_async())
    else:
        main()
