"""Suggest new search keywords based on cluster analysis.

Extracts frequent terms from clustered papers that are not in the
current search configuration and outputs suggestions as Markdown
and a YAML snippet ready to paste into scilex.config.yml.

Usage:
    scilex-suggest-keywords [--input PATH] [--top-k N] [--min-freq N]

Output is written to:
    {output_dir}/{collect_name}/graph_analysis/keyword_suggestions.md
    {output_dir}/{collect_name}/graph_analysis/keyword_suggestions.yml
"""

import argparse
import logging
import os
import sys

import pandas as pd

from scilex.config_defaults import DEFAULT_OUTPUT_DIR
from scilex.constants import normalize_path_component
from scilex.crawlers.utils import load_all_configs
from scilex.keyword_suggestions.extractor import extract_suggestions
from scilex.keyword_suggestions.report import generate_keyword_report
from scilex.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load scilex.config.yml."""
    configs = load_all_configs({"main_config": "scilex.config.yml"})
    return configs["main_config"]


def main():
    """Entry point for keyword suggestions."""
    parser = argparse.ArgumentParser(
        description="Suggest new search keywords from cluster analysis"
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to clusters CSV (overrides auto-detection)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=30,
        help="Maximum number of suggestions (default: 30)",
    )
    parser.add_argument(
        "--min-freq",
        type=int,
        default=2,
        help="Minimum term frequency (default: 2)",
    )
    args = parser.parse_args()

    try:
        config = load_config()

        if "collect_name" not in config:
            raise ValueError("collect_name not specified in scilex.config.yml")

        output_dir = config.get("output_dir", DEFAULT_OUTPUT_DIR)
        collect_name = normalize_path_component(config["collect_name"])
        collect_dir = os.path.join(output_dir, collect_name)
        analysis_dir = os.path.join(collect_dir, "graph_analysis")

        # Find clusters CSV
        if args.input:
            csv_path = args.input
        else:
            candidates = [
                os.path.join(analysis_dir, "clusters_cocitation.csv"),
                os.path.join(analysis_dir, "clusters_coupling.csv"),
            ]
            csv_path = next(
                (p for p in candidates if os.path.exists(p)),
                None,
            )
            if csv_path is None:
                raise FileNotFoundError(
                    f"No clusters CSV found in {analysis_dir}. "
                    "Run scilex-analyze first."
                )

        logger.info(f"Input: {csv_path}")

        # Load clusters data
        df = pd.read_csv(csv_path, dtype=str)
        if "cluster_id" in df.columns:
            df["cluster_id"] = (
                pd.to_numeric(df["cluster_id"], errors="coerce").fillna(-1).astype(int)
            )

        # Get existing keywords from config
        existing_keywords = config.get("keywords", [])
        if isinstance(existing_keywords, str):
            existing_keywords = [k.strip() for k in existing_keywords.split(",")]
        logger.info(f"Existing keywords: {len(existing_keywords)}")

        # Extract suggestions
        suggestions = extract_suggestions(
            df,
            existing_keywords,
            top_k=args.top_k,
            min_freq=args.min_freq,
        )

        if not suggestions:
            print("\nNo new keyword suggestions found.")
            return

        # Generate reports
        md_path, yml_path = generate_keyword_report(
            suggestions, analysis_dir, collect_name=collect_name
        )

        print(f"\nKeyword suggestions: {md_path}")
        print(f"YAML snippet: {yml_path}")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during keyword suggestion: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
