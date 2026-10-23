#!/usr/bin/env python3
"""Enrich aggregated papers with HuggingFace metadata (CSV-based).

This script:
1. Reads aggregated_results.csv
2. For each paper: searches HuggingFace for matching resources
3. Adds columns: tags, hf_url, github_repo
4. Writes updated CSV back

Usage:
    python src/enrich_with_hf.py [--collect-dir DIR] [--dry-run] [--limit N]

Examples:
    # Normal run (collect dir from config)
    python src/enrich_with_hf.py

    # Pass collect dir directly
    python src/enrich_with_hf.py --collect-dir output/my_collect

    # Dry run (show matches without updating)
    python src/enrich_with_hf.py --collect-dir output/my_collect --dry-run

    # Process first 100 papers only
    python src/enrich_with_hf.py --collect-dir output/my_collect --limit 100
"""

import argparse
import logging
import sys

from scilex.config import SciLExConfig
from scilex.logging_config import setup_logging
from scilex.pipeline.enrichment_hf import (  # noqa: F401  (re-exported)
    EnrichmentOptions,
    _match_via_models_api,
    _match_via_papers_api,
    process_paper_for_csv,
    run_enrichment,
)
from scilex.settings.cli import add_config_arguments, apply_config_arguments

logger = logging.getLogger(__name__)


def main():
    """Command-line entry point for CSV enrichment."""
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
    parser.add_argument(
        "--collect-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Path to the collect directory containing the aggregated CSV "
        "(overrides output_dir + collect_name from config)",
    )

    add_config_arguments(parser)
    args = parser.parse_args()
    apply_config_arguments(args)
    setup_logging()

    try:
        config = SciLExConfig.from_files()
        options = EnrichmentOptions(
            dry_run=args.dry_run,
            limit=args.limit,
            threshold=args.threshold,
            collect_dir=args.collect_dir,
        )
        result = run_enrichment(config, options)
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during enrichment: {e}", exc_info=True)
        sys.exit(1)

    if result.disabled:
        return

    logging.info("=" * 60)
    logging.info("HuggingFace CSV Enrichment Summary")
    logging.info("=" * 60)
    logging.info(f"Total papers: {result.total}")
    logging.info(f"Matched: {result.matched}")
    logging.info(f"Updated: {result.updated}")
    logging.info(f"Skipped: {result.skipped}")
    logging.info("=" * 60)

    if args.dry_run:
        logging.info("✓ Dry run complete. No changes made to CSV.")
    else:
        logging.info("✓ HuggingFace CSV enrichment complete!")


if __name__ == "__main__":
    main()
