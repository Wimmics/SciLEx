#!/usr/bin/env python3
"""
Created on Fri Feb 10 10:57:49 2023

@author: cringwal
         aollagnier

@version: 1.0.1
"""

import logging
import os
from datetime import datetime

import yaml

from scilex.config_defaults import DEFAULT_COLLECT_ENABLED, DEFAULT_OUTPUT_DIR
from scilex.crawlers.collector_collection import CollectCollection
from scilex.crawlers.utils import load_all_configs
from scilex.logging_config import log_section, setup_logging

# Set up logging configuration with environment variable support
# LOG_LEVEL=DEBUG python src/run_collection.py    # For debugging
# LOG_LEVEL=WARNING python src/run_collection.py  # For quiet mode
# LOG_COLOR=false python src/run_collection.py    # Disable colors
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

# Load optional advanced config if it exists (from src/ directory)
src_dir = os.path.dirname(os.path.abspath(__file__))
advanced_config_path = os.path.join(src_dir, "scilex.advanced.yml")
if os.path.isfile(advanced_config_path):
    with open(advanced_config_path) as f:
        advanced_config = yaml.safe_load(f) or {}
        # Merge advanced settings
        for key, value in advanced_config.items():
            if key not in main_config:
                main_config[key] = value
            elif key == "quality_filters" and isinstance(value, dict):
                # Merge quality_filters specifically
                if "quality_filters" not in main_config:
                    main_config["quality_filters"] = {}
                main_config["quality_filters"].update(value)
        logging.info(f"Loaded advanced config from {advanced_config_path}")

# Extract values from the main configuration
output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
collect = main_config.get("collect", DEFAULT_COLLECT_ENABLED)
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
    logger.info(
        f"Configuration: {len(keywords[0]) if keywords else 0} keywords, {len(years)} years, {len(apis)} APIs"
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
