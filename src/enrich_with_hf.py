#!/usr/bin/env python3
"""Enrich aggregated papers with HuggingFace metadata (CSV-based).

This script:
1. Reads aggregated_results.csv
2. For each paper: searches HuggingFace for matching resources
3. Adds columns: tags, hf_url, github_repo
4. Writes updated CSV back

Usage:
    python src/enrich_with_hf.py [--dry-run] [--limit N]

Examples:
    # Normal run (updates CSV)
    python src/enrich_with_hf.py

    # Dry run (show matches without updating)
    python src/enrich_with_hf.py --dry-run

    # Process first 100 papers only
    python src/enrich_with_hf.py --limit 100
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ruff: noqa: E402
import argparse
import logging
import os

import pandas as pd
from tqdm import tqdm

from src.config_defaults import DEFAULT_AGGREGATED_FILENAME, DEFAULT_OUTPUT_DIR
from src.constants import MISSING_VALUE, is_valid, normalize_path_component
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
logger = logging.getLogger(__name__)


def load_csv_with_auto_delimiter(csv_path: str) -> pd.DataFrame:
    """Load CSV with automatic delimiter detection.

    Tries semicolon, tab, and comma delimiters in order.

    Args:
        csv_path: Path to CSV file

    Returns:
        Loaded DataFrame

    Raises:
        ValueError: If CSV cannot be loaded with any delimiter
    """
    for delimiter in [";", "\t", ","]:
        try:
            data = pd.read_csv(csv_path, delimiter=delimiter)
            if "itemType" in data.columns and "title" in data.columns:
                logger.info(f"Loaded CSV with delimiter: '{delimiter}'")
                return data
        except Exception as e:
            logger.debug(f"Failed with delimiter '{delimiter}': {e}")
            continue

    raise ValueError(f"Could not load CSV with any delimiter: {csv_path}")


def process_paper_for_csv(
    paper_row: pd.Series,
    hf_client: HFClient,
    matcher: TitleMatcher,
    extractor: MetadataExtractor,
    formatter: TagFormatter,
    use_papers_api: bool = True,
) -> dict | None:
    """Process a single CSV row: search HF, extract metadata, format tags.

    Dual-strategy approach:
    1. Try Papers API first (if use_papers_api=True)
    2. Fall back to Models API (if Papers API fails)

    Args:
        paper_row: pandas Series with paper data
        hf_client: HFClient instance
        matcher: TitleMatcher instance
        extractor: MetadataExtractor instance
        formatter: TagFormatter instance
        use_papers_api: Enable Papers API search (default: True)

    Returns:
        Dictionary with:
        {
            "tags": "TASK:TextClassification;PTM:BERT;DATASET:Squad",
            "hf_url": "https://huggingface.co/papers/...",
            "github_repo": "https://github.com/..."
        }
        or None if no matches found
    """
    title = paper_row.get("title")

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
        models = hf_client.search_models_by_title(title, limit=3)

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

    # Build result dictionary
    result = {
        "tags": ";".join(new_tags),  # Semicolon-separated for CSV
        "hf_url": MISSING_VALUE,
        "github_repo": MISSING_VALUE,
    }

    # Add HF URL based on match source
    if match_source == "papers_api":
        paper_id = metadata.get("paper_id")
        if paper_id:
            result["hf_url"] = f"https://huggingface.co/papers/{paper_id}"
    else:  # models_api
        model_id = metadata.get("modelId")
        if model_id:
            result["hf_url"] = f"https://huggingface.co/{model_id}"

    # Add GitHub repo URL - use paper's actual repo, not citing models
    if match_source == "papers_api":
        # Paper's actual GitHub repo from paper info
        github_repo = metadata.get("paper_github_repo")
        if github_repo:
            result["github_repo"] = github_repo
    else:  # models_api
        github_url = metadata.get("github_url")
        if github_url:
            result["github_repo"] = github_url

    return result


def main():
    """Main entry point for CSV enrichment."""
    parser = argparse.ArgumentParser(
        description="Enrich aggregated CSV with HuggingFace metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without updating CSV",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum papers to process",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="Fuzzy matching threshold (0-100, default: 85)",
    )

    args = parser.parse_args()

    try:
        # Load configs
        config_files = {
            "main_config": "scilex.config.yml",
            "api_config": "api.config.yml",
        }
        configs = load_all_configs(config_files)
        main_config = configs["main_config"]
        api_config = configs["api_config"]

        # Get HF config
        hf_config = main_config.get("hf_enrichment", {})
        hf_enabled = hf_config.get("enabled", True)

        if not hf_enabled:
            logging.warning("HuggingFace enrichment is disabled in config. Exiting.")
            return

        hf_token = api_config.get("HuggingFace", {}).get("token")
        use_papers_api = hf_config.get("use_papers_api", True)

        # Initialize HF clients
        logging.info("Initializing HuggingFace enrichment system...")
        hf_client = HFClient(
            token=hf_token,
            cache_path=hf_config.get("cache_path", "output/hf_cache.db"),
            cache_ttl_days=hf_config.get("cache_ttl_days", 30),
        )
        matcher = TitleMatcher(
            threshold=hf_config.get("fuzzy_match_threshold", args.threshold)
        )
        extractor = MetadataExtractor()
        formatter = TagFormatter()

        # Load CSV
        output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
        aggregate_file = main_config.get("aggregate_file", DEFAULT_AGGREGATED_FILENAME)
        collect_dir = os.path.join(
            output_dir, normalize_path_component(main_config["collect_name"])
        )
        csv_path = os.path.join(collect_dir, normalize_path_component(aggregate_file))

        logging.info(f"Loading CSV: {csv_path}")
        data = load_csv_with_auto_delimiter(csv_path)
        logging.info(f"Loaded {len(data)} papers")

        # Add new columns if they don't exist
        if "tags" not in data.columns:
            data["tags"] = MISSING_VALUE
        if "hf_url" not in data.columns:
            data["hf_url"] = MISSING_VALUE
        if "github_repo" not in data.columns:
            data["github_repo"] = MISSING_VALUE

        # Process papers
        logging.info(f"Processing papers (limit: {args.limit})...")

        stats = {
            "total": len(data),
            "matched": 0,
            "updated": 0,
            "skipped": 0,
        }

        for idx, row in tqdm(
            data.iterrows(), total=len(data), desc="Processing papers"
        ):
            if args.limit and idx >= args.limit:
                break

            try:
                result = process_paper_for_csv(
                    row,
                    hf_client,
                    matcher,
                    extractor,
                    formatter,
                    use_papers_api=use_papers_api,
                )

                if result is None:
                    stats["skipped"] += 1
                    continue

                stats["matched"] += 1

                if not args.dry_run:
                    data.at[idx, "tags"] = result["tags"]
                    data.at[idx, "hf_url"] = result["hf_url"]
                    data.at[idx, "github_repo"] = result["github_repo"]
                    stats["updated"] += 1
                else:
                    logging.info(f"[DRY RUN] Would enrich: {row['title'][:50]}...")
                    logging.info(f"  Tags: {result['tags']}")
                    logging.info(f"  HF URL: {result['hf_url']}")
                    logging.info(f"  GitHub: {result['github_repo']}")

            except Exception as e:
                logging.error(f"Error processing row {idx}: {e}")
                stats["skipped"] += 1
                continue

        # Write updated CSV
        if not args.dry_run:
            data.to_csv(csv_path, sep=";", index=False)
            logging.info(f"✓ Updated CSV written: {csv_path}")

        # Print summary
        logging.info("=" * 60)
        logging.info("HuggingFace CSV Enrichment Summary")
        logging.info("=" * 60)
        logging.info(f"Total papers: {stats['total']}")
        logging.info(f"Matched: {stats['matched']}")
        logging.info(f"Updated: {stats['updated']}")
        logging.info(f"Skipped: {stats['skipped']}")
        logging.info("=" * 60)

        if args.dry_run:
            logging.info("✓ Dry run complete. No changes made to CSV.")
        else:
            logging.info("✓ HuggingFace CSV enrichment complete!")

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during enrichment: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
