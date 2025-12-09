#!/usr/bin/env python3
"""HuggingFace integration for SciLEx - Find models/datasets/repos for papers.

This script:
1. Fetches papers from Zotero collection (paginated)
2. For each paper: searches HuggingFace Hub for matching resources
3. Extracts metadata (architecture, datasets, GitHub repos)
4. Updates Zotero items with new tags
5. Stores GitHub URLs in archiveLocation field

Usage:
    python src/getHF_collect.py [--dry-run] [--collection NAME] [--limit N]

Examples:
    # Normal run (updates Zotero)
    python src/getHF_collect.py

    # Dry run (show matches without updating)
    python src/getHF_collect.py --dry-run

    # Process specific collection
    python src/getHF_collect.py --collection "ML_Papers"

    # Process first 100 papers only
    python src/getHF_collect.py --limit 100
"""

import sys
from pathlib import Path

# Add project root to path for imports to work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ruff: noqa: E402
import argparse
import json
import logging

import requests
from tqdm import tqdm

from src.constants import is_valid
from src.crawlers.utils import load_all_configs
from src.HuggingFace.hf_client import HFClient
from src.HuggingFace.metadata_extractor import MetadataExtractor
from src.HuggingFace.tag_formatter import TagFormatter
from src.HuggingFace.title_matcher import TitleMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_configs() -> tuple[dict, dict]:
    """Load scilex.config.yml and api.config.yml."""
    config_files = {
        "main_config": "scilex.config.yml",
        "api_config": "api.config.yml",
    }
    configs = load_all_configs(config_files)
    return configs["main_config"], configs["api_config"]


def fetch_papers_from_zotero(
    user_id: str,
    user_role: str,
    api_key: str,
    collection_key: str,
    limit: int | None = None,
) -> list[dict]:
    """Fetch papers from Zotero collection (paginated).

    Args:
        user_id: Zotero user/group ID
        user_role: "user" or "group"
        api_key: Zotero API key
        collection_key: Target collection key
        limit: Optional limit on number of papers to fetch

    Returns:
        List of paper dictionaries (only non-attachment items)
    """
    logging.info(f"Fetching papers from Zotero collection: {collection_key}")

    if user_role == "group":
        base_url = f"https://api.zotero.org/groups/{user_id}"
    else:
        base_url = f"https://api.zotero.org/users/{user_id}"

    headers = {"Zotero-API-Key": api_key}

    papers = []
    start = 0
    batch_size = 100

    with tqdm(desc="Fetching papers", unit=" papers") as pbar:
        while True:
            url = f"{base_url}/collections/{collection_key}/items/top?limit={batch_size}&start={start}"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                logging.error(f"Failed to fetch papers: {response.status_code}")
                break

            batch = response.json()

            if not batch:
                break

            # Filter out attachments
            filtered = [
                p
                for p in batch
                if p.get("data", {}).get("itemType") != "attachment"
                and is_valid(p.get("data", {}).get("title"))
            ]

            papers.extend(filtered)
            pbar.update(len(filtered))

            if limit and len(papers) >= limit:
                papers = papers[:limit]
                break

            if len(batch) < batch_size:
                break

            start += batch_size

    logging.info(f"Fetched {len(papers)} papers from Zotero")
    return papers


def process_paper(
    paper: dict,
    hf_client: HFClient,
    matcher: TitleMatcher,
    extractor: MetadataExtractor,
    formatter: TagFormatter,
    max_models: int = 3,
    use_papers_api: bool = True,
) -> dict | None:
    """Process a single paper: search HF, extract metadata, format tags.

    Dual-strategy approach:
    1. Try Papers API first (if use_papers_api=True)
    2. Fall back to Models API (if Papers API fails)

    Args:
        paper: Zotero paper dictionary
        hf_client: HFClient instance
        matcher: TitleMatcher instance
        extractor: MetadataExtractor instance
        formatter: TagFormatter instance
        max_models: Maximum models to consider (for Models API fallback)
        use_papers_api: Enable Papers API search (default: True)

    Returns:
        Dictionary with updates to apply to Zotero, or None if no matches
    """
    paper_data = paper["data"]
    title = paper_data.get("title", "")

    if not is_valid(title):
        return None

    metadata = None
    match_source = None
    paper_info = None

    # STRATEGY 1: Papers API (PRIMARY)
    if use_papers_api:
        logging.debug(f"Trying Papers API for: {title[:50]}...")
        papers = hf_client.search_papers_by_title(title, limit=10)

        if papers:
            # Find best matching paper
            best_paper, score = matcher.find_best_match(title, papers, key="title")

            if best_paper:
                logging.info(
                    f"✓ Papers API match: '{title[:40]}...' → "
                    f"{best_paper['title'][:40]}... (score: {score})"
                )
                paper_id = best_paper.get("id")

                # Get paper info (actual GitHub repo, ai_keywords, github_stars)
                paper_info = hf_client.get_paper_info(paper_id)

                # Get linked resources (citing models/datasets for metadata)
                linked_resources = hf_client.get_paper_linked_resources(paper_id)
                metadata = extractor.extract_paper_resources(
                    best_paper, linked_resources
                )

                # Add paper info data to metadata
                if paper_info:
                    metadata["github_stars"] = paper_info.get("githubStars")
                    metadata["ai_keywords"] = paper_info.get("ai_keywords", [])
                    # Paper's actual GitHub repo (NOT from citing models)
                    metadata["paper_github_repo"] = paper_info.get("githubRepo")

                # Rename datasets from citing resources to citing_datasets
                if "datasets" in metadata:
                    metadata["citing_datasets"] = metadata.pop("datasets")

                match_source = "papers_api"

    # STRATEGY 2: Models API (FALLBACK)
    if metadata is None:
        logging.debug(f"Falling back to Models API for: {title[:50]}...")
        models = hf_client.search_models_by_title(title, limit=max_models)

        if models:
            # Find best matching model
            best_model, score = matcher.find_best_match(title, models, key="modelId")

            if best_model:
                logging.info(
                    f"✓ Models API match: '{title[:40]}...' → "
                    f"{best_model['modelId']} (score: {score})"
                )
                metadata = extractor.extract_model_metadata(best_model)
                match_source = "models_api"
                # Store model_id for later use
                metadata["modelId"] = best_model.get("modelId")

    # No match found
    if metadata is None:
        logging.debug(f"No HF match found for: {title[:50]}...")
        return None

    # Format tags from metadata
    new_tags = formatter.format_all_tags(metadata)

    if not new_tags:
        logging.debug(f"No new tags to add for: {title[:50]}...")
        return None

    # Prepare Zotero updates
    updates = {
        "tags": [{"tag": t} for t in new_tags],
    }

    # Add HF URL based on match source
    if match_source == "papers_api":
        paper_id = metadata.get("paper_id")
        if paper_id:
            updates["archive"] = f"https://huggingface.co/papers/{paper_id}"
    else:  # models_api
        model_id = metadata.get("modelId")
        if model_id:
            updates["archive"] = f"https://huggingface.co/{model_id}"

    # Add GitHub repo URL - use paper's actual repo, not citing models
    if match_source == "papers_api":
        # Paper's actual GitHub repo from paper info
        github_repo = metadata.get("paper_github_repo")
        if github_repo:
            updates["archiveLocation"] = github_repo
    else:  # models_api
        github_url = metadata.get("github_url")
        if github_url:
            updates["archiveLocation"] = github_url

    return updates


def apply_updates_to_zotero(
    paper_key: str,
    updates: dict,
    user_id: str,
    user_role: str,
    api_key: str,
    dry_run: bool = False,
) -> bool:
    """Apply updates to Zotero paper item.

    Args:
        paper_key: Zotero item key
        updates: Dictionary of fields to update
        user_id: Zotero user/group ID
        user_role: "user" or "group"
        api_key: Zotero API key
        dry_run: If True, log changes without updating Zotero

    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        logging.info(f"[DRY RUN] Would update paper {paper_key}:")
        logging.info(f"  Tags: {updates.get('tags', [])}")
        logging.info(f"  Archive: {updates.get('archive', 'N/A')}")
        logging.info(f"  Archive Location: {updates.get('archiveLocation', 'N/A')}")
        return True

    # Build URL
    if user_role == "group":
        base_url = f"https://api.zotero.org/groups/{user_id}"
    else:
        base_url = f"https://api.zotero.org/users/{user_id}"

    # Fetch current item data
    headers = {"Zotero-API-Key": api_key}
    response = requests.get(
        f"{base_url}/items/{paper_key}", headers=headers, timeout=30
    )

    if response.status_code != 200:
        logging.error(f"Failed to fetch item data for {paper_key}")
        return False

    item_json = response.json()
    last_version = item_json["version"]

    # Merge existing tags with new tags using REPLACE logic for same prefixes
    existing_tags = item_json["data"].get("tags", [])
    new_tags = updates.get("tags", [])

    # HF tag prefixes that should REPLACE (not extend)
    hf_prefixes = [
        "TASK:",
        "PTM:",
        "ARCHI:",
        "DATASET:",
        "FRAMEWORK:",
        "GITHUB_STARS:",
        "CITED_BY_DATASET:",
    ]

    # Find which prefixes are in new tags
    new_prefixes_present = set()
    for new_tag in new_tags:
        tag_upper = new_tag["tag"].upper()
        for prefix in hf_prefixes:
            if tag_upper.startswith(prefix):
                new_prefixes_present.add(prefix)
                break

    # Remove existing tags with same prefixes (REPLACE logic)
    merged_tags = []
    for existing_tag in existing_tags:
        tag_upper = existing_tag["tag"].upper()
        should_remove = False
        for prefix in new_prefixes_present:
            if tag_upper.startswith(prefix):
                should_remove = True
                break
        if not should_remove:
            merged_tags.append(existing_tag)

    # Add new tags (deduplicate case-insensitive)
    existing_upper = {t["tag"].upper() for t in merged_tags}
    for new_tag in new_tags:
        if new_tag["tag"].upper() not in existing_upper:
            merged_tags.append(new_tag)
            existing_upper.add(new_tag["tag"].upper())

    # Prepare PATCH body
    patch_body = {}

    if merged_tags != existing_tags:
        patch_body["tags"] = merged_tags

    if "archive" in updates:
        patch_body["archive"] = updates["archive"]

    if "archiveLocation" in updates:
        patch_body["archiveLocation"] = updates["archiveLocation"]

    if not patch_body:
        logging.debug(f"No changes to apply for {paper_key}")
        return True

    # PATCH item
    headers["If-Unmodified-Since-Version"] = str(last_version)
    headers["Content-Type"] = "application/json"

    response = requests.patch(
        f"{base_url}/items/{paper_key}",
        headers=headers,
        data=json.dumps(patch_body),
        timeout=30,
    )

    if response.status_code in [200, 204]:
        logging.info(f"✓ Updated paper {paper_key}")
        return True
    else:
        logging.error(
            f"✗ Failed to update paper {paper_key}: "
            f"{response.status_code} {response.text}"
        )
        return False


def main():
    """Main entry point for HuggingFace enrichment script."""
    parser = argparse.ArgumentParser(
        description="Enrich Zotero papers with HuggingFace metadata"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show matches without updating Zotero"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Zotero collection name (default: from config)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum papers to process"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="Fuzzy matching threshold (0-100, default: 85)",
    )

    args = parser.parse_args()

    # Load configs
    main_config, api_config = load_configs()

    # Get Zotero credentials
    zotero_config = api_config["Zotero"]
    user_id = zotero_config["user_id"]
    user_role = zotero_config["user_mode"]
    api_key = zotero_config["api_key"]

    # Get collection name
    collection_name = args.collection or main_config["collect_name"]

    # Get HF config
    hf_config = main_config.get("hf_enrichment", {})
    hf_enabled = hf_config.get("enabled", True)
    use_papers_api = hf_config.get("use_papers_api", True)

    if not hf_enabled:
        logging.warning("HuggingFace enrichment is disabled in config. Exiting.")
        return

    hf_token = api_config.get("HuggingFace", {}).get("token")

    # Initialize clients
    logging.info("Initializing HuggingFace enrichment system...")
    hf_client = HFClient(
        token=hf_token,
        cache_path=hf_config.get("cache_path", "output/hf_cache.db"),
        cache_ttl_days=hf_config.get("cache_ttl_days", 30),
    )
    matcher = TitleMatcher(threshold=args.threshold)
    extractor = MetadataExtractor()
    formatter = TagFormatter()

    # Find collection by name
    logging.info(f"Looking for collection: {collection_name}")
    if user_role == "group":
        url = f"https://api.zotero.org/groups/{user_id}/collections"
    else:
        url = f"https://api.zotero.org/users/{user_id}/collections"

    headers = {"Zotero-API-Key": api_key}
    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        logging.error(f"Failed to fetch collections: {response.status_code}")
        return

    collections = response.json()
    collection_key = None

    for coll in collections:
        if coll["data"]["name"] == collection_name:
            collection_key = coll["data"]["key"]
            logging.info(f"Found collection: {collection_name} (key: {collection_key})")
            break

    if not collection_key:
        logging.error(f"Collection '{collection_name}' not found in Zotero")
        return

    # Fetch papers
    papers = fetch_papers_from_zotero(
        user_id, user_role, api_key, collection_key, limit=args.limit
    )

    if not papers:
        logging.warning("No papers found in collection")
        return

    # Process papers
    logging.info(f"Processing {len(papers)} papers...")

    stats = {
        "total": len(papers),
        "matched": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }

    for paper in tqdm(papers, desc="Processing papers", unit=" paper"):
        try:
            updates = process_paper(
                paper,
                hf_client,
                matcher,
                extractor,
                formatter,
                max_models=hf_config.get("max_models", 3),
                use_papers_api=use_papers_api,
            )

            if updates is None:
                stats["skipped"] += 1
                continue

            stats["matched"] += 1

            success = apply_updates_to_zotero(
                paper["key"], updates, user_id, user_role, api_key, dry_run=args.dry_run
            )

            if success:
                stats["updated"] += 1
            else:
                stats["failed"] += 1

        except Exception as e:
            logging.error(f"Error processing paper {paper['key']}: {e}")
            stats["failed"] += 1

    # Print summary
    logging.info("=" * 60)
    logging.info("HuggingFace Enrichment Summary")
    logging.info("=" * 60)
    logging.info(f"Total papers processed: {stats['total']}")
    logging.info(f"Papers with HF matches: {stats['matched']}")
    logging.info(f"Papers updated: {stats['updated']}")
    logging.info(f"Papers skipped: {stats['skipped']}")
    logging.info(f"Failed updates: {stats['failed']}")
    logging.info("=" * 60)

    if args.dry_run:
        logging.info("✓ Dry run complete. No changes made to Zotero.")
    else:
        logging.info("✓ HuggingFace enrichment complete!")


if __name__ == "__main__":
    main()
