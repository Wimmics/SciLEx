#!/usr/bin/env python3
"""
Created on Fri Feb 10 10:57:49 2023

@author: cringwal
         aollagnier

@version: 1.0.1
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import yaml

from scilex.config_defaults import DEFAULT_COLLECT_ENABLED, DEFAULT_OUTPUT_DIR
from scilex.crawlers.collector_collection import CollectCollection
from scilex.crawlers.utils import load_all_configs, load_yaml_config
from scilex.logging_config import add_file_log_handler, log_section, setup_logging

# Set up logging configuration with environment variable support
# LOG_LEVEL=DEBUG python src/run_collection.py    # For debugging
# LOG_LEVEL=WARNING python src/run_collection.py  # For quiet mode
# LOG_COLOR=false python src/run_collection.py    # Disable colors
setup_logging()


def _resolve_resume_dir(resume_arg, src_dir):
    """
    Resolve the collection directory from a --resume argument.

    Accepts either a full path or a collection name (looked up under output_dir
    from the current scilex.config.yml).
    """
    if os.path.isabs(resume_arg) or os.sep in resume_arg or "/" in resume_arg:
        return resume_arg

    # Name only — find output_dir from the current config
    current_config_path = os.path.join(src_dir, "scilex.config.yml")
    try:
        current_config = load_yaml_config(current_config_path)
        output_dir_base = current_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    except FileNotFoundError:
        output_dir_base = DEFAULT_OUTPUT_DIR

    return os.path.join(output_dir_base, resume_arg)


def _load_main_config(src_dir, resume_arg=None):
    """
    Load main config either from a previous collection (--resume) or from
    the standard scilex.config.yml.

    Returns (main_config, source_description).
    """
    if resume_arg is not None:
        collect_dir = _resolve_resume_dir(resume_arg, src_dir)
        config_path = os.path.join(collect_dir, "config_used.yml")
        if not os.path.isfile(config_path):
            print(f"Error: Cannot find saved config at {config_path}")
            print(
                "Make sure the collection name or path is correct and the collection has been started at least once."
            )
            sys.exit(1)
        main_config = load_yaml_config(config_path)
        return main_config, f"resumed from {config_path}"

    # Normal path: load from scilex.config.yml + optional advanced config
    config_files = {
        "main_config": "scilex.config.yml",
        "api_config": "api.config.yml",
    }
    configs = load_all_configs(config_files)
    main_config = configs["main_config"]

    advanced_config_path = os.path.join(src_dir, "scilex.advanced.yml")
    if os.path.isfile(advanced_config_path):
        with open(advanced_config_path) as f:
            advanced_config = yaml.safe_load(f) or {}
        for key, value in advanced_config.items():
            if key not in main_config:
                main_config[key] = value
            elif key == "quality_filters" and isinstance(value, dict):
                if "quality_filters" not in main_config:
                    main_config["quality_filters"] = {}
                main_config["quality_filters"].update(value)
        logging.info(f"Loaded advanced config from {advanced_config_path}")

    return main_config, "scilex.config.yml"


def main():
    """Main function to run collection - required for multiprocessing on macOS/Windows"""
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

    src_dir = os.path.dirname(os.path.abspath(__file__))
    main_config, config_source = _load_main_config(src_dir, args.resume)

    # Load api config (always from the standard location)
    api_config_path = os.path.join(src_dir, "api.config.yml")
    try:
        api_config = load_yaml_config(api_config_path)
    except FileNotFoundError:
        api_config = {}

    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    collect = main_config.get("collect", DEFAULT_COLLECT_ENABLED)
    years = main_config["years"]
    keywords = main_config["keywords"]
    apis = main_config["apis"]
    collect_name = main_config.get("collect_name", "unknown")

    print(f"Config source  : {config_source}")
    print(f"Output Directory: {output_dir}")
    print(f"Collect: {collect}")
    print(f"Years: {years}")
    print(f"Keywords: {keywords}")
    print(f"APIS: {apis}")

    if collect:
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

    # Resolve collection directory and attach error log file
    dir_collect = os.path.join(output_dir, collect_name)
    os.makedirs(dir_collect, exist_ok=True)
    log_path = os.path.join(dir_collect, "collect_errors.log")
    _file_handler = add_file_log_handler(log_path, level=logging.WARNING)

    # Write session-start separator (directly to file so it's always present)
    run_label = f"resumed: {args.resume}" if args.resume else "new run"
    _sep = "=" * 70
    with open(log_path, "a", encoding="utf-8") as _lf:
        _lf.write(f"\n{_sep}\n")
        _lf.write(
            f"=== SciLEx collect — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            f" ({run_label}) ===\n"
        )
        _lf.write(f"    APIs: {', '.join(apis)}\n")
        _lf.write(f"    Years: {', '.join(str(y) for y in years)}\n")
        _lf.write(f"{_sep}\n")

    start_time = datetime.now()
    log_section(logger, "SciLEx Systematic Review Collection")
    logger.info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Error log: {log_path}")
    logger.info(
        f"Configuration: {len(keywords[0]) if keywords else 0} keywords, {len(years)} years, {len(apis)} APIs"
    )

    try:
        colle_col = CollectCollection(main_config, api_config)
        colle_col.create_collects_jobs()
    finally:
        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()
        with open(log_path, "a", encoding="utf-8") as _lf:
            _lf.write(
                f"=== Run ended — {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
                f" (duration: {elapsed / 60:.1f} min) ===\n\n"
            )
        logging.getLogger().removeHandler(_file_handler)
        _file_handler.close()

    log_section(logger, "Collection Complete")
    logger.info(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total time: {elapsed:.1f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    # This guard is required for multiprocessing on macOS/Windows (spawn mode)
    main()
