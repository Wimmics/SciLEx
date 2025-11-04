#!/usr/bin/env python3
"""
Script to push aggregated papers to Zotero collection.

This script reads aggregated paper data and pushes it to a specified
Zotero collection, handling duplicates and creating the collection if needed.
"""

import logging
import os
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from src.constants import is_valid
from src.crawlers.utils import load_all_configs
from src.Zotero.zotero_api import ZoteroAPI, prepare_zotero_item

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_aggregated_data(config: dict) -> pd.DataFrame:
    """
    Load aggregated paper data from CSV file.

    Args:
        config: Main configuration dictionary with output_dir, collect_name, aggregate_file

    Returns:
        DataFrame containing aggregated paper data
    """
    dir_collect = os.path.join(config["output_dir"], config["collect_name"])
    aggr_file = config["aggregate_file"]
    file_path = dir_collect + aggr_file

    logging.info(f"Loading data from: {file_path}")
    data = pd.read_csv(file_path, delimiter="\t")
    logging.info(f"Loaded {len(data)} papers")

    return data


def push_new_items_to_zotero(
    data: pd.DataFrame,
    zotero_api: ZoteroAPI,
    collection_key: str,
    existing_urls: list[str],
) -> dict[str, int]:
    """
    Push new items to Zotero collection.

    Args:
        data: DataFrame containing paper metadata
        zotero_api: ZoteroAPI client instance
        collection_key: Key of the target collection
        existing_urls: List of URLs already in the collection

    Returns:
        Dictionary with counts: {"success": n, "failed": m, "skipped": k}
    """
    results = {"success": 0, "failed": 0, "skipped": 0}
    templates_cache = {}

    logging.info("Processing papers for upload...")

    for _index, row in data.iterrows():
        # Prepare Zotero item from row
        item = prepare_zotero_item(row, collection_key, templates_cache)

        if item is None:
            results["skipped"] += 1
            continue

        # Check for duplicate URL
        item_url = item.get("url")
        if not is_valid(item_url):
            logging.warning(f"Skipping paper without valid URL: {row.get('title', 'Unknown')}")
            results["skipped"] += 1
            continue

        if item_url in existing_urls:
            logging.debug(f"Skipping duplicate URL: {item_url}")
            results["skipped"] += 1
            continue

        # Post the item
        if zotero_api.post_item(item):
            results["success"] += 1
        else:
            results["failed"] += 1

    return results


def main():
    """Main execution function."""
    logging.info(f"Zotero push process started at {datetime.now()}")
    logging.info("=" * 60)

    # Load configurations
    config_files = {
        "main_config": "scilex.config.yml",
        "api_config": "api.config.yml",
    }
    configs = load_all_configs(config_files)
    main_config = configs["main_config"]
    api_config = configs["api_config"]

    # Extract Zotero configuration
    user_id = api_config["Zotero"]["user_id"]
    user_role = api_config["Zotero"]["user_mode"]
    api_key = api_config["Zotero"]["api_key"]
    collection_name = main_config.get("collect_name", "new_models")

    # Initialize Zotero API client
    logging.info(f"Initializing Zotero API client for {user_role} {user_id}")
    zotero_api = ZoteroAPI(user_id, user_role, api_key)

    # Get or create collection
    logging.info(f"Looking for collection: '{collection_name}'")
    collection = zotero_api.get_or_create_collection(collection_name)

    if not collection:
        logging.error(f"Failed to get or create collection '{collection_name}'")
        return

    collection_key = collection["data"]["key"]
    logging.info(f"Using collection key: {collection_key}")

    # Get existing URLs to avoid duplicates
    logging.info("Fetching existing items in collection...")
    existing_urls = zotero_api.get_existing_item_urls(collection_key)
    logging.info(f"Found {len(existing_urls)} existing items")

    # Load aggregated data
    data = load_aggregated_data(main_config)

    # Push new items
    logging.info("=" * 60)
    logging.info("Starting upload of new papers...")
    results = push_new_items_to_zotero(data, zotero_api, collection_key, existing_urls)

    # Log summary
    logging.info("=" * 60)
    logging.info("Upload complete!")
    logging.info(f"✅ Successfully uploaded: {results['success']} papers")
    logging.info(f"❌ Failed to upload: {results['failed']} papers")
    logging.info(f"⏭️  Skipped (duplicates/invalid): {results['skipped']} papers")
    logging.info(f"Process completed at {datetime.now()}")


if __name__ == "__main__":
    main()
