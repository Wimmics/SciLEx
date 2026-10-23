"""Core of the HuggingFace CSV enrichment (no CLI, no ``sys.argv``).

``run_enrichment`` reads the aggregated CSV, searches HuggingFace for each
paper, adds the ``tags``, ``hf_url`` and ``github_repo`` columns and writes the
CSV back. It receives its configuration and options as parameters, so both the
CLI (``scilex.enrich_with_hf``) and the web API call it the same way.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

import pandas as pd
from tqdm import tqdm

from scilex.config import SciLExConfig
from scilex.constants import MISSING_VALUE, is_valid
from scilex.HuggingFace.hf_client import HFClient
from scilex.HuggingFace.metadata_extractor import MetadataExtractor
from scilex.HuggingFace.tag_formatter import TagFormatter
from scilex.HuggingFace.title_matcher import TitleMatcher
from scilex.io_utils import (
    load_aggregated_data,
    resolve_aggregate_path,
    write_aggregated_csv,
)

logger = logging.getLogger(__name__)

ENRICHMENT_COLUMNS = ("tags", "hf_url", "github_repo")

# progress_callback(processed, total, stats)
ProgressCallback = Callable[[int, int, dict], None]


@dataclass
class EnrichmentOptions:
    """Options of one enrichment run.

    Attributes:
        dry_run: Log the matches without modifying or writing the CSV.
        limit: Maximum number of papers to process (None or 0 = all).
        threshold: Fuzzy title matching threshold (0-100). When given (for
            example by ``--threshold``) it takes precedence over the config key
            ``hf_enrichment.fuzzy_match_threshold`` (default 85).
        collect_dir: Collect directory holding the aggregated CSV (overrides
            ``output_dir`` + ``collect_name`` from the config).
        workers: Papers searched concurrently. When given (for example by
            ``--workers``) it takes precedence over the config key
            ``hf_enrichment.workers`` (default 4). Network calls stay capped by
            the HF client's rate limiter, so more workers only hide latency.
    """

    dry_run: bool = False
    limit: int | None = None
    threshold: int | None = None
    collect_dir: str | None = None
    workers: int | None = None


@dataclass
class EnrichmentResult:
    """Outcome of ``run_enrichment``.

    Attributes:
        total: Papers in the CSV.
        processed: Papers examined (matched + skipped).
        matched: Papers for which HuggingFace resources were found.
        updated: Papers actually written to the CSV (0 in dry-run).
        skipped: Papers without match, without usable title, or in error.
        output_path: CSV path (written unless dry-run); None otherwise.
        disabled: True when enrichment is disabled in the config (nothing done).
    """

    total: int = 0
    processed: int = 0
    matched: int = 0
    updated: int = 0
    skipped: int = 0
    output_path: str | None = None
    disabled: bool = False


def _match_via_papers_api(
    title: str,
    hf_client: HFClient,
    matcher: TitleMatcher,
    extractor: MetadataExtractor,
) -> dict | None:
    """Search the HF Papers API and return extracted metadata, or None."""
    logging.debug(f"Trying Papers API for: {title[:50]}...")
    papers = hf_client.search_papers_by_title(title, limit=10)
    if not papers:
        return None

    best_paper, score = matcher.find_best_match(title, papers, key="title")
    if not best_paper:
        return None

    logging.info(
        f"✓ Papers API match: '{title[:40]}...' → "
        f"{best_paper['title'][:40]}... (score: {score})"
    )
    paper_id = best_paper.get("id")

    # Paper info (actual GitHub repo, ai_keywords, github_stars)
    paper_info = hf_client.get_paper_info(paper_id)

    # Linked resources (citing models/datasets for metadata)
    linked_resources = hf_client.get_paper_linked_resources(paper_id)
    metadata = extractor.extract_paper_resources(best_paper, linked_resources)

    if paper_info:
        metadata["github_stars"] = paper_info.get("githubStars")
        metadata["ai_keywords"] = paper_info.get("ai_keywords", [])
        # Paper's actual GitHub repo (NOT from citing models)
        metadata["paper_github_repo"] = paper_info.get("githubRepo")

    # Rename datasets from citing resources to citing_datasets
    if "datasets" in metadata:
        metadata["citing_datasets"] = metadata.pop("datasets")

    return metadata


def _match_via_models_api(
    title: str,
    hf_client: HFClient,
    matcher: TitleMatcher,
    extractor: MetadataExtractor,
) -> dict | None:
    """Search the HF Models API and return extracted metadata, or None."""
    logging.debug(f"Falling back to Models API for: {title[:50]}...")
    models = hf_client.search_models_by_title(title, limit=3)
    if not models:
        return None

    best_model, score = matcher.find_best_match(title, models, key="modelId")
    if not best_model:
        return None

    logging.info(
        f"✓ Models API match: '{title[:40]}...' → "
        f"{best_model['modelId']} (score: {score})"
    )
    metadata = extractor.extract_model_metadata(best_model)
    metadata["modelId"] = best_model.get("modelId")
    return metadata


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

    # STRATEGY 1: Papers API (PRIMARY)
    if use_papers_api:
        metadata = _match_via_papers_api(title, hf_client, matcher, extractor)
        if metadata is not None:
            match_source = "papers_api"

    # STRATEGY 2: Models API (FALLBACK)
    if metadata is None:
        metadata = _match_via_models_api(title, hf_client, matcher, extractor)
        if metadata is not None:
            match_source = "models_api"

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


def _enrich_rows(
    data: pd.DataFrame,
    hf_client: HFClient,
    matcher: TitleMatcher,
    extractor: MetadataExtractor,
    formatter: TagFormatter,
    options: EnrichmentOptions,
    use_papers_api: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[tuple[object, dict]], dict]:
    """Search HuggingFace for each row, without modifying ``data``.

    Rows are searched concurrently (``options.workers`` threads); ``data`` is
    only read and results come back in row order.

    Args:
        data: Aggregated papers.
        hf_client: HFClient instance.
        matcher: TitleMatcher instance.
        extractor: MetadataExtractor instance.
        formatter: TagFormatter instance.
        options: Run options (``limit``, ``dry_run`` and ``workers`` are used here).
        use_papers_api: Enable the Papers API search.
        progress_callback: Optional ``callback(processed, total, stats)``,
            called after every row.

    Returns:
        ``(updates, stats)``: ``updates`` is the list of ``(row_label, result)``
        for matched rows, in row order; ``stats`` has the keys ``total``,
        ``matched``, ``skipped``.
    """
    stats = {"total": len(data), "matched": 0, "skipped": 0}
    updates: list[tuple[object, dict]] = []
    rows = data.head(options.limit) if options.limit else data

    def search_row(item):
        """Run one paper's search; errors are returned, not raised."""
        idx, row = item
        try:
            result = process_paper_for_csv(
                row,
                hf_client,
                matcher,
                extractor,
                formatter,
                use_papers_api=use_papers_api,
            )
            return idx, row, result, None
        except Exception as error:
            return idx, row, None, error

    # map() yields in row order; counting and callbacks stay on this thread.
    with ThreadPoolExecutor(max_workers=max(1, options.workers or 4)) as executor:
        outcomes = executor.map(search_row, rows.iterrows())
        for idx, row, result, error in tqdm(
            outcomes, total=len(rows), desc="Processing papers"
        ):
            if error is not None:
                logging.error(f"Error processing row {idx}: {error}")
                stats["skipped"] += 1
            elif result is None:
                stats["skipped"] += 1
            else:
                stats["matched"] += 1
                updates.append((idx, result))
                if options.dry_run:
                    logging.info(f"[DRY RUN] Would enrich: {row['title'][:50]}...")
                    logging.info(f"  Tags: {result['tags']}")
                    logging.info(f"  HF URL: {result['hf_url']}")
                    logging.info(f"  GitHub: {result['github_repo']}")

            if progress_callback:
                progress_callback(stats["matched"] + stats["skipped"], len(data), stats)

    return updates, stats


def run_enrichment(
    config: SciLExConfig,
    options: EnrichmentOptions | None = None,
    progress_callback: ProgressCallback | None = None,
) -> EnrichmentResult:
    """Enrich the aggregated CSV with HuggingFace metadata.

    Args:
        config: Loaded configuration (``hf_enrichment`` section, HuggingFace
            token in the API config, collection location).
        options: Run options (defaults to ``EnrichmentOptions()``).
        progress_callback: Optional ``callback(processed, total, stats)``.

    Returns:
        EnrichmentResult with counters and the CSV path.

    Raises:
        FileNotFoundError: If the aggregated CSV does not exist.
    """
    options = options or EnrichmentOptions()
    main_config = config.main

    hf_config = main_config.get("hf_enrichment", {})
    if not hf_config.get("enabled", True):
        logging.warning("HuggingFace enrichment is disabled in config. Exiting.")
        return EnrichmentResult(disabled=True)

    use_papers_api = hf_config.get("use_papers_api", True)
    if options.workers is None:
        options = replace(options, workers=hf_config.get("workers", 4))

    logging.info("Initializing HuggingFace enrichment system...")
    hf_client = HFClient(
        token=config.api.get("HuggingFace", {}).get("token"),
        cache_path=hf_config.get("cache_path", "output/hf_cache.db"),
        cache_ttl_days=hf_config.get("cache_ttl_days", 30),
    )
    matcher = TitleMatcher(
        threshold=(
            options.threshold
            if options.threshold is not None
            else hf_config.get("fuzzy_match_threshold", 85)
        )
    )
    extractor = MetadataExtractor()
    formatter = TagFormatter()

    csv_path = resolve_aggregate_path(main_config, options.collect_dir)
    logging.info(f"Loading CSV: {csv_path}")
    data = load_aggregated_data(
        main_config, options.collect_dir, preserve_missing_marker=True
    )
    logging.info(f"Loaded {len(data)} papers")

    for column in ENRICHMENT_COLUMNS:
        if column not in data.columns:
            data[column] = MISSING_VALUE

    logging.info(f"Processing papers (limit: {options.limit})...")
    updates, stats = _enrich_rows(
        data,
        hf_client,
        matcher,
        extractor,
        formatter,
        options,
        use_papers_api=use_papers_api,
        progress_callback=progress_callback,
    )

    updated = 0
    if not options.dry_run:
        for idx, result in updates:
            for column in ENRICHMENT_COLUMNS:
                data.at[idx, column] = result[column]
            updated += 1

    processed = stats["matched"] + stats["skipped"]
    if progress_callback:
        # Final progress report
        progress_callback(processed, len(data), {**stats, "updated": updated})

    output_path = None
    if not options.dry_run:
        write_aggregated_csv(data, csv_path)
        output_path = str(csv_path)
        logging.info(f"✓ Updated CSV written: {csv_path}")

    return EnrichmentResult(
        total=stats["total"],
        processed=processed,
        matched=stats["matched"],
        updated=updated,
        skipped=stats["skipped"],
        output_path=output_path,
    )
