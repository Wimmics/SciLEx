"""Pipeline orchestrator — programmatic entry points for SciLEx pipelines.

Provides run_aggregation() and run_collection() as pure function calls,
replacing the need for sys.argv manipulation or subprocess calls.
"""

import contextlib
import csv
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import yaml

from scilex.abstract_validation import (
    filter_by_abstract_quality,
    validate_dataframe_abstracts,
)
from scilex.config import SciLExConfig
from scilex.config_defaults import (
    DEFAULT_AGGREGATED_FILENAME,
    DEFAULT_OUTPUT_DIR,
    MIN_ABSTRACT_QUALITY_SCORE,
)
from scilex.constants import normalize_path_component
from scilex.crawlers.collector_collection import CollectCollection
from scilex.duplicate_tracking import (
    analyze_and_report_duplicates,
    generate_itemtype_distribution_report,
)
from scilex.keyword_validation import generate_keyword_validation_report
from scilex.pipeline.citation_filter import apply_time_aware_citation_filter
from scilex.pipeline.enrichment import (
    fill_missing_urls_from_doi,
    use_openalex_citations_fallback,
    use_semantic_scholar_citations_fallback,
)
from scilex.pipeline.itemtype_filter import apply_itemtype_bypass, apply_itemtype_filter
from scilex.pipeline.ranking import apply_relevance_ranking
from scilex.pipeline.tracker import FilteringTracker
from scilex.quality_validation import (
    apply_quality_filters,
    generate_data_completeness_report,
)

logger = logging.getLogger(__name__)


@dataclass
class AggregationOptions:
    """Options for run_aggregation(), replacing argparse arguments."""

    skip_citations: bool = False
    workers: int = 2
    resume: bool = False
    no_cache: bool = False
    checkpoint_interval: int = 100
    parallel_workers: int | None = None
    batch_size: int = 5000
    profile: bool = False


def run_collection(
    config: SciLExConfig,
    progress_callback: Callable | None = None,
    cancel_event=None,
) -> None:
    """Run paper collection programmatically.

    Args:
        config: Loaded SciLExConfig instance.
        progress_callback: Optional callback(api_stats, completed, total).
        cancel_event: Optional threading.Event to signal cancellation.
    """
    main_config = config.main
    api_config = config.api

    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    # CollectCollection handles writing config_used.yml to the correct
    # {output_dir}/{collect_name}/ subdirectory — no duplicate write needed here.

    # Run collection
    collector = CollectCollection(
        main_config,
        api_config,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )
    collector.create_collects_jobs()


def run_aggregation(
    config: SciLExConfig,
    options: AggregationOptions | None = None,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> pd.DataFrame:
    """Run the full aggregation pipeline programmatically.

    This is the core function that replaces the body of aggregate_collect.main().
    It can be called from CLI, web API, or tests without sys.argv manipulation.

    Args:
        config: Loaded SciLExConfig instance.
        options: Aggregation options (defaults applied if None).
        progress_callback: Optional callback(phase, progress_pct, message).

    Returns:
        pd.DataFrame: The aggregated and filtered results.
    """
    if options is None:
        options = AggregationOptions()

    main_config = config.main
    api_config = config.api
    # Use the SciLExConfig property which merges user overrides with defaults
    quality_filters = config.quality_filters

    # Resolve paths
    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    collect_name = normalize_path_component(main_config.get("collect_name"))
    dir_collect = os.path.join(output_dir, collect_name)
    output_filename = normalize_path_component(
        main_config.get("aggregate_file", DEFAULT_AGGREGATED_FILENAME)
    )

    get_citation = (
        main_config.get("aggregate_get_citations", True) and not options.skip_citations
    )

    logger.info(f"Collection directory: {dir_collect}")
    logger.info(f"Citation fetching: {'enabled' if get_citation else 'disabled'}")

    if progress_callback:
        progress_callback("initializing", 5, "Loading configuration...")

    # Auto-populate year_range from main config if empty
    if quality_filters.get("validate_year_range", False):
        year_range = quality_filters.get("year_range", [])
        if not year_range:
            year_range = main_config.get("years", [])
            quality_filters["year_range"] = year_range
            logging.info(f"Auto-populated year_range from main config: {year_range}")

    keyword_groups = main_config.get("keywords", [])
    bonus_keywords = main_config.get("bonus_keywords", None)

    # Load collection metadata from config snapshot
    config_used_path = os.path.join(dir_collect, "config_used.yml")
    if not os.path.isfile(config_used_path):
        raise FileNotFoundError(
            f"No collection metadata found in: {dir_collect}. "
            f"Run collection first or check 'collect_name' in scilex.config.yml"
        )

    with open(config_used_path, encoding="utf-8") as f:
        config_used = yaml.safe_load(f)

    if progress_callback:
        progress_callback("aggregating", 10, "Running parallel aggregation...")

    # =========================================================================
    # RUN PARALLEL AGGREGATION
    # =========================================================================
    from scilex.crawlers.aggregate_parallel import parallel_aggregate

    df, parallel_stats = parallel_aggregate(
        dir_collect=dir_collect,
        config_used=config_used,
        txt_filters=True,
        num_workers=options.parallel_workers,
        batch_size=options.batch_size,
        keyword_groups=keyword_groups,
    )

    if options.profile:
        logging.info("\n" + "=" * 70)
        logging.info("PERFORMANCE STATISTICS")
        logging.info("=" * 70)
        for stage, stats in parallel_stats.items():
            logging.info(f"\n{stage.upper()}:")
            for key, value in stats.items():
                if isinstance(value, float):
                    logging.info(f"  {key}: {value:.2f}")
                else:
                    logging.info(
                        f"  {key}: {value:,}"
                        if isinstance(value, int)
                        else f"  {key}: {value}"
                    )
        logging.info("=" * 70 + "\n")

    df_clean = df
    filtering_tracker = FilteringTracker()
    filtering_tracker.set_initial(len(df_clean), "Papers after deduplication")

    if progress_callback:
        progress_callback("filtering", 30, "Applying filters...")

    # =========================================================================
    # STEP 0: Fill Missing URLs from DOIs
    # =========================================================================
    logging.info("\n=== URL Fallback from DOI ===")
    df_clean, _url_stats = fill_missing_urls_from_doi(df_clean)

    # =========================================================================
    # STEP 1: ItemType Filtering (Whitelist Mode)
    # =========================================================================
    enable_itemtype_filter = quality_filters.get("enable_itemtype_filter", False)
    allowed_item_types = quality_filters.get("allowed_item_types", [])

    if enable_itemtype_filter:
        logging.info("\n=== ItemType Filtering (Whitelist Mode) ===")
        df_clean, _itemtype_stats = apply_itemtype_filter(
            df_clean, allowed_item_types, enable_itemtype_filter
        )
        filtering_tracker.add_stage(
            "ItemType Filter",
            len(df_clean),
            f"Whitelist filtering: Only {len(allowed_item_types)} allowed itemTypes kept",
        )
        if len(df_clean) == 0:
            logging.warning(
                "All papers filtered out by itemType filter. No papers to process."
            )
            return df_clean
    else:
        logging.info("ItemType filtering: DISABLED (all itemTypes allowed)")

    # Track duplicate sources
    if quality_filters.get("track_duplicate_sources", True):
        logging.info("Analyzing duplicate sources and API overlap...")
        analyze_and_report_duplicates(
            df_clean,
            generate_report=quality_filters.get("generate_quality_report", True),
        )

    if quality_filters.get("generate_quality_report", True):
        logging.info("Generating itemType distribution report...")
        itemtype_report = generate_itemtype_distribution_report(df_clean)
        print(itemtype_report)

    # Calculate quality scores
    logging.info("Calculating quality scores...")
    from scilex.crawlers.aggregate import getquality

    df_clean["quality_score"] = df_clean.apply(
        lambda row: getquality(row, df_clean.columns.tolist()), axis=1
    )

    if progress_callback:
        progress_callback("filtering", 45, "Applying quality filters...")

    # =========================================================================
    # STEP 2: ItemType Bypass + Quality Filters
    # =========================================================================
    bypass_item_types = quality_filters.get("bypass_item_types", [])
    enable_bypass = quality_filters.get("enable_itemtype_bypass", False)

    if enable_bypass and bypass_item_types:
        logging.info("\n=== ItemType Bypass Filter ===")
        df_bypass, df_non_bypass = apply_itemtype_bypass(df_clean, bypass_item_types)
        filtering_tracker.add_stage(
            "ItemType Bypass Split",
            len(df_non_bypass),
            f"Split: {len(df_bypass):,} high-quality papers auto-pass ({', '.join(bypass_item_types)}), "
            f"{len(df_non_bypass):,} papers continue through quality validation",
        )
    else:
        df_bypass = pd.DataFrame()
        df_non_bypass = df_clean

    if quality_filters and len(df_non_bypass) > 0:
        logging.info("Applying quality filters to non-bypass papers...")
        generate_report = quality_filters.get("generate_quality_report", True)
        df_filtered, _quality_report = apply_quality_filters(
            df_non_bypass, quality_filters, generate_report
        )
        logging.info(
            f"After quality filtering: {len(df_filtered)} papers remaining "
            f"(from {len(df_non_bypass)} non-bypass papers)"
        )

        if len(df_bypass) > 0:
            df_clean = pd.concat([df_bypass, df_filtered], ignore_index=True)
            logging.info(
                f"Merged: {len(df_bypass)} bypass + {len(df_filtered)} filtered = {len(df_clean)} total papers"
            )
        else:
            df_clean = df_filtered

        filtering_tracker.add_stage(
            "Quality Filter",
            len(df_clean),
            "Papers meeting quality requirements (DOI, abstract, year, author count, etc.)",
        )
    elif len(df_bypass) > 0:
        df_clean = df_bypass

    # Reports
    if quality_filters.get("generate_quality_report", True):
        completeness_report = generate_data_completeness_report(df_clean)
        logging.info(completeness_report)

    keywords = main_config.get("keywords", [])
    if keywords and quality_filters.get("generate_quality_report", True):
        keyword_report = generate_keyword_validation_report(df_clean, keywords)
        logging.info(keyword_report)

    # Abstract quality validation
    if quality_filters.get("validate_abstracts", False):
        logging.info("Validating abstract quality...")
        min_quality_score = quality_filters.get(
            "min_abstract_quality_score", MIN_ABSTRACT_QUALITY_SCORE
        )
        df_clean, _abstract_stats = validate_dataframe_abstracts(
            df_clean,
            min_quality_score=min_quality_score,
            generate_report=quality_filters.get("generate_quality_report", True),
        )
        df_clean = filter_by_abstract_quality(
            df_clean, min_quality_score=min_quality_score
        )
        logging.info(
            f"After abstract quality filtering: {len(df_clean)} papers remaining"
        )
        filtering_tracker.add_stage(
            "Abstract Quality Filter",
            len(df_clean),
            f"Abstracts meeting quality threshold (min score: {min_quality_score})",
        )

    if progress_callback:
        progress_callback("citations", 55, "Fetching citations...")

    # =========================================================================
    # STEP 3: Citation Fetching & Filtering
    # =========================================================================
    if get_citation and len(df_clean) > 0:
        from scilex.aggregate_collect import _fetch_citations_parallel

        checkpoint_path = os.path.join(dir_collect, "citation_checkpoint.json")
        crossref_mailto = api_config.get("CrossRef", {}).get("mailto")

        extras, nb_citeds, nb_citations, stats = _fetch_citations_parallel(
            df_clean,
            num_workers=options.workers,
            checkpoint_interval=options.checkpoint_interval,
            checkpoint_path=checkpoint_path,
            resume_from=options.resume,
            use_cache=not options.no_cache,
            crossref_mailto=crossref_mailto,
        )

        df_clean["extra"] = extras
        df_clean["nb_cited"] = nb_citeds
        df_clean["nb_citation"] = nb_citations

        # Warn if high failure rate
        total_with_doi = stats["success"] + stats["error"] + stats["timeout"]
        if total_with_doi > 0:
            failure_rate = (stats["error"] + stats["timeout"]) / total_with_doi * 100
            if failure_rate > 10:
                logging.warning(
                    f"High failure rate: {failure_rate:.1f}% of API calls failed"
                )

        if quality_filters.get("use_semantic_scholar_citations", True):
            df_clean = use_semantic_scholar_citations_fallback(df_clean)

        if quality_filters.get("use_openalex_citations", True):
            df_clean = use_openalex_citations_fallback(df_clean)

        if quality_filters.get("apply_citation_filter", True):
            df_clean = apply_time_aware_citation_filter(df_clean)
            filtering_tracker.add_stage(
                "Citation Filter",
                len(df_clean),
                "Papers meeting time-aware citation thresholds",
            )

        # Clean up checkpoint
        with contextlib.suppress(OSError):
            os.remove(checkpoint_path)
    elif get_citation and len(df_clean) == 0:
        logging.warning("Skipping citation fetching - no papers to process")

    if progress_callback:
        progress_callback("ranking", 85, "Applying relevance ranking...")

    # =========================================================================
    # STEP 4: Relevance Ranking
    # =========================================================================
    if quality_filters.get("apply_relevance_ranking", True):
        top_n = quality_filters.get("max_papers", None)
        df_clean = apply_relevance_ranking(
            df_clean,
            keyword_groups=keyword_groups,
            top_n=top_n,
            has_citations=get_citation and len(df_clean) > 0,
            config=main_config,
            bonus_keywords=bonus_keywords,
        )
        filtering_tracker.add_stage(
            "Relevance Ranking",
            len(df_clean),
            f"{'Top ' + str(top_n) + ' ' if top_n else ''}Papers ranked by normalized relevance score (0-10 scale)",
        )

    # =========================================================================
    # REPORTS & OUTPUT
    # =========================================================================
    filtering_summary = filtering_tracker.generate_report()
    logging.info(filtering_summary)

    # Save filtering summary as JSON
    final_count = (
        filtering_tracker.stages[-1]["papers"] if filtering_tracker.stages else 0
    )
    summary_data = {
        "initial_count": filtering_tracker.initial_count,
        "final_count": final_count,
        "stages": filtering_tracker.stages,
    }
    summary_path = os.path.join(dir_collect, "filtering_summary.json")
    try:
        with open(summary_path, "w") as f:
            json.dump(summary_data, f, indent=2)
        logging.info(f"Filtering summary saved to {summary_path}")
    except OSError as e:
        logging.warning(f"Could not save filtering summary: {e}")

    # Save to CSV
    output_path = os.path.join(dir_collect, output_filename)
    logging.info(f"Saving {len(df_clean)} aggregated papers to {output_path}")
    df_clean.to_csv(
        output_path,
        sep=";",
        quotechar='"',
        quoting=csv.QUOTE_NONNUMERIC,
    )
    logging.info(f"Aggregation complete! Results saved to {output_path}")

    if progress_callback:
        progress_callback("completed", 100, "Aggregation completed!")

    return df_clean
