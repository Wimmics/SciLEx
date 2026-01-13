#!/usr/bin/env python3
"""
Script to push aggregated papers to Zotero collection.

This script reads aggregated paper data and pushes it to a specified
Zotero collection, handling duplicates and creating the collection if needed.
"""

import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from tqdm import tqdm

from src.config_defaults import DEFAULT_AGGREGATED_FILENAME, DEFAULT_OUTPUT_DIR
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
                (uses defaults from config_defaults.py if not specified)

    Returns:
        DataFrame containing aggregated paper data
    """
    output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    aggregate_file = config.get("aggregate_file", DEFAULT_AGGREGATED_FILENAME)
    dir_collect = os.path.join(output_dir, config["collect_name"])
    file_path = os.path.join(dir_collect, aggregate_file)

    logging.info(f"Loading data from: {file_path}")

    # Try different delimiters - aggregated files can use either ; or \t
    for delimiter in [";", "\t", ","]:
        try:
            data = pd.read_csv(file_path, delimiter=delimiter)
            # Verify we got valid data by checking for expected columns
            if "itemType" in data.columns and "title" in data.columns:
                logging.info(f"Loaded {len(data)} papers (delimiter: '{delimiter}')")
                return data
        except Exception as e:
            logging.debug(f"Failed to load with delimiter '{delimiter}': {e}")
            continue

    # If all delimiters fail, raise an error
    raise ValueError(
        f"Could not load CSV file with any delimiter (tried: ';', '\\t', ','). "
        f"File: {file_path}"
    )


def prefetch_templates(data: pd.DataFrame) -> dict[str, dict]:
    """
    Pre-fetch all unique item type templates before processing.

    This avoids blocking HTTP calls during the main processing loop
    and ensures we only fetch each template once.

    Args:
        data: DataFrame containing paper metadata with 'itemType' column

    Returns:
        Dictionary mapping item types to their Zotero templates
    """
    import requests

    unique_types = data["itemType"].dropna().unique()
    templates = {}

    logging.info(f"Pre-fetching {len(unique_types)} item type templates...")

    for item_type in unique_types:
        # Handle special case mapping
        if item_type == "bookSection":
            item_type = "journalArticle"

        # Fetch template directly from public Zotero API (no auth needed)
        try:
            response = requests.get(
                f"https://api.zotero.org/items/new?itemType={item_type}", timeout=30
            )
            response.raise_for_status()
            templates[item_type] = response.json()
            logging.debug(f"Fetched template for: {item_type}")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch template for {item_type}: {e}")

    logging.info(f"Successfully pre-fetched {len(templates)} templates")
    return templates


def push_new_items_to_zotero(
    data: pd.DataFrame,
    zotero_api: ZoteroAPI,
    collection_key: str,
    existing_urls: set,
    templates_cache: dict[str, dict],
    config: dict,
) -> dict[str, int]:
    """
    Push new items to Zotero collection using bulk upload.

    Args:
        data: DataFrame containing paper metadata
        zotero_api: ZoteroAPI client instance
        collection_key: Key of the target collection
        existing_urls: Set of URLs already in the collection (for O(1) lookups)
        templates_cache: Pre-fetched item type templates

    Returns:
        Dictionary with counts: {"success": n, "failed": m, "skipped": k, "skipped_for_incompatibility": j}
    """
    output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    dir_collect = os.path.join(output_dir, config["collect_name"])
    results = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "skipped_for_incompatibility": 0,
    }
    invalid_items = []
    items_to_upload = []

    logging.info("Processing papers for upload...")

    # Use itertuples for faster iteration (5-10x faster than iterrows)
    for row in tqdm(
        data.itertuples(index=False), total=len(data), desc="Preparing items"
    ):
        # Prepare Zotero item from row
        item = prepare_zotero_item(row, collection_key, templates_cache)

        if item is None:
            results["skipped_for_incompatibility"] += 1
            invalid_items.append(row)
            continue

        # Check for duplicate URL
        item_url = item.get("url")
        if not is_valid(item_url):
            title = (
                getattr(row, "title", "Unknown") if hasattr(row, "title") else "Unknown"
            )
            logging.warning(f"Skipping paper without valid URL: {title}")
            invalid_items.append(row)
            results["skipped_for_incompatibility"] += 1
            continue

        if item_url in existing_urls:  # O(1) set lookup
            logging.debug(f"Skipping duplicate URL: {item_url}")
            results["skipped"] += 1
            continue

        # Add to batch for bulk upload
        items_to_upload.append(item)
    if invalid_items:
        invalid_data = pd.DataFrame(invalid_items)
        invalid_data_path = os.path.join(dir_collect, "invalid_items_no_url.csv")
        invalid_data.to_csv(invalid_data_path, index=False)
        logging.info(
            f"Found {len(invalid_items)} invalid items without valid URLs, saving them into {invalid_data_path}..."
        )
    # Upload all items in bulk (automatically batched into groups of 50)
    if items_to_upload:
        logging.info(f"Uploading {len(items_to_upload)} new papers in bulk...")
        bulk_results = zotero_api.post_items_bulk(items_to_upload)
        results["success"] = bulk_results["success"]
        results["failed"] = bulk_results["failed"]
    else:
        logging.info("No new papers to upload")

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

    # Extract Zotero configuration (handle both lowercase and capitalized keys)
    zotero_config = api_config.get("Zotero") or api_config.get("zotero")
    if not zotero_config:
        logging.error("Zotero configuration not found in api.config.yml")
        logging.error("Please ensure your api.config.yml has a 'zotero:' section with:")
        logging.error("  - api_key: Your Zotero API key")
        logging.error("  - user_id: Your Zotero user ID")
        logging.error("  - user_mode: 'user' or 'group'")
        return

    api_key = zotero_config.get("api_key")
    user_id = zotero_config.get("user_id")
    user_role = zotero_config.get("user_mode", "user")

    if not api_key:
        logging.error("Zotero API key not found in api.config.yml")
        return

    if not user_id:
        logging.error("Zotero user_id not found in api.config.yml")
        logging.error("Please add 'user_id' to the zotero section in api.config.yml")
        logging.error(
            "You can find your user ID at: https://www.zotero.org/settings/keys"
        )
        return

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

    # Pre-fetch all item type templates
    templates_cache = prefetch_templates(data)

    # Push new items
    logging.info("=" * 60)
    logging.info("Starting upload of new papers...")
    results = push_new_items_to_zotero(
        data, zotero_api, collection_key, existing_urls, templates_cache, main_config
    )

    # Log summary
    logging.info("=" * 60)
    logging.info("Upload complete!")
    logging.info(f"✅ Successfully uploaded: {results['success']} papers")
    logging.info(f"❌ Failed to upload: {results['failed']} papers")
    logging.info(f"⏭️  Skipped (duplicates/none): {results['skipped']} papers")
    logging.info(
        f"⏭️  Skipped (non URL): {results['skipped_for_incompatibility']} papers"
    )
    logging.info(f"Process completed at {datetime.now()}")


if __name__ == "__main__":
    main()
