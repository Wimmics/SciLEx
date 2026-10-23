import argparse
import logging
import sys

from scilex.config import SciLExConfig  # noqa: F811
from scilex.logging_config import log_section, setup_logging  # noqa: F811
from scilex.pipeline.bonus_keywords import (  # noqa: F811
    generate_bonus_keyword_stats,
    tag_papers_with_bonus_keywords,
)
from scilex.pipeline.citation_filter import (  # noqa: F811
    apply_time_aware_citation_filter,
    calculate_paper_age_months,
    calculate_required_citations,
)
from scilex.pipeline.enrichment import (  # noqa: F811
    fill_missing_urls_from_doi,
    use_openalex_citations_fallback,
    use_semantic_scholar_citations_fallback,
)
from scilex.pipeline.itemtype_filter import (  # noqa: F811
    apply_itemtype_bypass,
    apply_itemtype_filter,
)
from scilex.pipeline.ranking import (  # noqa: F811
    apply_relevance_ranking,
    calculate_relevance_score,
    count_keyword_matches,
)
from scilex.pipeline.report import write_aggregation_report  # noqa: F811
from scilex.pipeline.text_filter import (  # noqa: F811
    check_keywords_flexible,
    check_keywords_in_text,
    keyword_matches_in_abstract,
    record_passes_text_filter,
)

# Backward-compatible aliases (old names with leading _)
_keyword_matches_in_abstract = keyword_matches_in_abstract
_check_keywords_in_text = check_keywords_in_text
_check_keywords_flexible = check_keywords_flexible
_record_passes_text_filter = record_passes_text_filter
_tag_papers_with_bonus_keywords = tag_papers_with_bonus_keywords
_generate_bonus_keyword_stats = generate_bonus_keyword_stats
_write_aggregation_report = write_aggregation_report
_calculate_paper_age_months = calculate_paper_age_months
_calculate_required_citations = calculate_required_citations
_apply_time_aware_citation_filter = apply_time_aware_citation_filter
_count_keyword_matches = count_keyword_matches
_calculate_relevance_score = calculate_relevance_score
_apply_relevance_ranking = apply_relevance_ranking
_apply_itemtype_bypass = apply_itemtype_bypass
_apply_itemtype_filter = apply_itemtype_filter
_fill_missing_urls_from_doi = fill_missing_urls_from_doi
_use_semantic_scholar_citations_fallback = use_semantic_scholar_citations_fallback
_use_openalex_citations_fallback = use_openalex_citations_fallback
from scilex.citations.fetcher import (  # noqa: E402,F401
    _fetch_citation_for_paper,
    _fetch_citations_parallel,
)


def main():
    """CLI entry point for aggregation. Thin wrapper around run_aggregation()."""
    from scilex.pipeline.orchestrator import AggregationOptions, run_aggregation

    # Set up logging
    setup_logging()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Aggregate collected papers and fetch citations"
    )
    parser.add_argument(
        "--collection",
        metavar="COLLECT",
        default=None,
        help=(
            "Aggregate a specific collection by name or full path. "
            "Loads config_used.yml from that directory. "
            "If omitted, uses collect_name from scilex.config.yml."
        ),
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from checkpoint if available"
    )
    parser.add_argument(
        "--skip-citations", action="store_true", help="Skip citation fetching entirely"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable citation caching (slower - not recommended)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of parallel workers for citation fetching (default: 2)",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=100,
        help="Save checkpoint every N papers (default: 100)",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=None,
        help="Number of parallel workers for batch processing (default: auto-detect CPU count - 1)",
    )
    parser.add_argument(
        "--load-workers",
        type=int,
        default=None,
        help="Number of parallel workers for JSON file loading (default: 4). "
        "Increase for fast local filesystems; keep low for WSL2/network paths.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Papers per batch for parallel processing (default: 5000)",
    )
    parser.add_argument(
        "--profile", action="store_true", help="Output detailed performance statistics"
    )
    parser.add_argument(
        "--no-abstract-enrichment",
        action="store_true",
        help=(
            "Skip abstract enrichment step entirely. By default, records without abstracts "
            "(e.g. from Elsevier, ORKG) are enriched via Semantic Scholar / OpenAlex "
            "before aggregation, and the fetched abstracts are saved back to the "
            "source JSON files."
        ),
    )
    parser.add_argument(
        "--cache-only-enrichment",
        action="store_true",
        help=(
            "Apply only already-cached abstracts during enrichment — no network calls. "
            "Useful for fast re-aggregations when the cache is already warm. "
            "Ignored if --no-abstract-enrichment is set."
        ),
    )
    parser.add_argument(
        "--enrich-workers",
        type=int,
        default=4,
        help="Parallel workers for abstract enrichment HTTP requests (default: 4)",
    )
    args = parser.parse_args()

    logger = logging.getLogger(__name__)

    # Load configuration (from a previous collection's snapshot if --collection)
    try:
        config = SciLExConfig.from_collection(args.collection)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Log aggregation start
    log_section(logger, "SciLEx Data Aggregation")

    # Build options from CLI args
    options = AggregationOptions(
        skip_citations=args.skip_citations,
        workers=args.workers,
        resume=args.resume,
        no_cache=args.no_cache,
        checkpoint_interval=args.checkpoint_interval,
        parallel_workers=args.parallel_workers,
        batch_size=args.batch_size,
        profile=args.profile,
        no_abstract_enrichment=args.no_abstract_enrichment,
        cache_only_enrichment=args.cache_only_enrichment,
        enrich_workers=args.enrich_workers,
        load_workers=args.load_workers,
    )

    # Run the pipeline
    run_aggregation(config, options)


if __name__ == "__main__":
    main()
