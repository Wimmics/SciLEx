"""
Parallel aggregation module for paper processing.

Processing stages:
1. Parallel file loading (threading): Load JSON files, I/O bound
2. Parallel batch processing (multiprocessing): Convert formats, apply filters
3. Deduplication (serial): DOI-based and normalized title matching (O(n))
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool, cpu_count

import pandas as pd
from tqdm import tqdm

from src.constants import is_valid

# ============================================================================
# HELPER FUNCTIONS: FILESYSTEM DISCOVERY & QUERY RECONSTRUCTION
# ============================================================================


def discover_api_directories(dir_collect: str) -> dict[str, list[str]]:
    """
    Discover API directories and query indices from filesystem.

    Scans the collection directory to find:
    - API subdirectories (e.g., SemanticScholar, OpenAlex)
    - Query index subdirectories within each API (e.g., 0, 1, 2)

    Args:
        dir_collect: Base collection directory path

    Returns:
        Dictionary mapping API names to sorted query index lists
        Example: {"SemanticScholar": ["0", "1", "2"], "OpenAlex": ["0", "1"]}
    """
    api_to_queries = {}

    if not os.path.exists(dir_collect):
        logging.warning(f"Collection directory not found: {dir_collect}")
        return api_to_queries

    # Scan for API directories
    for api_dir in os.listdir(dir_collect):
        api_path = os.path.join(dir_collect, api_dir)

        # Skip files (only process directories)
        if not os.path.isdir(api_path):
            continue

        # Skip special files/directories
        if api_dir in ["config_used.yml", "citation_cache.db"]:
            continue

        # Scan for query index directories
        query_indices = []
        try:
            for query_idx in os.listdir(api_path):
                query_path = os.path.join(api_path, query_idx)

                if os.path.isdir(query_path):
                    # Verify it's a numeric directory
                    try:
                        int(query_idx)  # Validate it's a number
                        query_indices.append(query_idx)
                    except ValueError:
                        # Skip non-numeric directories
                        continue

        except PermissionError:
            logging.warning(f"Permission denied accessing: {api_path}")
            continue

        if query_indices:
            # Sort numerically (0, 1, 2, ... not 0, 1, 10, 2)
            query_indices.sort(key=int)
            api_to_queries[api_dir] = query_indices

    logging.info(
        f"Discovered {len(api_to_queries)} APIs with "
        f"{sum(len(q) for q in api_to_queries.values())} total queries"
    )

    return api_to_queries


def reconstruct_query_to_keywords_mapping(
    config_used: dict,
) -> dict[str, dict[str, list[str]]]:
    """
    Reconstruct query index → keywords mapping from config_used.yml.

    Reproduces the same cartesian product used during collection to map
    query indices to their corresponding keyword combinations.

    Args:
        config_used: Configuration dictionary from config_used.yml

    Returns:
        Nested dictionary mapping API → query_index → keywords
        Example: {
            "SemanticScholar": {
                "0": ["LLM", "Knowledge Graph"],
                "1": ["LLM", "knowledge graphs"],
                ...
            },
            "OpenAlex": {...}
        }
    """
    import itertools

    # Extract configuration
    keywords = config_used.get("keywords", [[]])
    years = config_used.get("years", [])
    apis = config_used.get("apis", [])

    # Step 1: Generate keyword combinations (same logic as queryCompositor)
    keyword_combinations = []
    two_list_k = False

    # Check for dual keyword group mode
    if len(keywords) == 2 and len(keywords[0]) > 0 and len(keywords[1]) > 0:
        # Dual keyword mode: cartesian product of both groups
        two_list_k = True
        keyword_combinations = [
            list(pair) for pair in itertools.product(keywords[0], keywords[1])
        ]
    elif (len(keywords) == 2 and len(keywords[0]) > 0 and len(keywords[1]) == 0) or (
        len(keywords) == 1 and len(keywords[0]) > 0
    ):
        # Single keyword mode
        keyword_combinations = keywords[0]

    logging.debug(f"Reconstructed {len(keyword_combinations)} keyword combinations")

    # Step 2: Generate cartesian product (keywords × years × apis)
    combinations = itertools.product(keyword_combinations, years, apis)

    # Step 3: Group by API and create query lists
    queries_by_api = {}

    if two_list_k:
        # Dual keyword mode: keyword_group is already a list [kw1, kw2]
        for keyword_group, year, api in combinations:
            if api not in queries_by_api:
                queries_by_api[api] = []
            queries_by_api[api].append(
                {
                    "keyword": keyword_group,  # Already a list
                    "year": year,
                }
            )
    else:
        # Single keyword mode: wrap single keyword in list
        for keyword_group, year, api in combinations:
            if api not in queries_by_api:
                queries_by_api[api] = []
            queries_by_api[api].append(
                {
                    "keyword": [keyword_group],  # Wrap in list
                    "year": year,
                }
            )

    # Step 4: Create index → keywords mapping
    mapping = {}
    for api, queries in queries_by_api.items():
        mapping[api] = {}
        for idx, query in enumerate(queries):
            mapping[api][str(idx)] = query["keyword"]

    logging.debug(
        f"Reconstructed mapping for {len(mapping)} APIs with "
        f"{sum(len(q) for q in mapping.values())} total query indices"
    )

    return mapping


# ============================================================================
# PHASE 1: PARALLEL FILE LOADING
# ============================================================================


def _load_json_file(
    file_path: str, api_name: str, keywords: list[str]
) -> tuple[list[dict], str, list[str], int]:
    """
    Load a single JSON file and return its papers.

    Args:
        file_path: Path to JSON file
        api_name: API name (e.g., 'SemanticScholar')
        keywords: List of keywords for this query

    Returns:
        Tuple of (papers_list, api_name, keywords, num_papers)
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        papers = data.get("results", [])
        return (papers, api_name, keywords, len(papers))

    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error in {file_path}: {e}")
        return ([], api_name, keywords, 0)

    except Exception as e:
        logging.error(f"Error loading {file_path}: {e}")
        return ([], api_name, keywords, 0)


def parallel_load_all_files(
    dir_collect: str,
    config_used: dict,
    num_workers: int | None = None,
) -> tuple[list[tuple[dict, str, list[str]]], dict]:
    """
    Load all JSON files in parallel using threading.

    Args:
        dir_collect: Base collection directory path
        config_used: Configuration dictionary from config_used.yml
        num_workers: Number of parallel workers (default: cpu_count * 2 for I/O)

    Returns:
        Tuple of:
        - List of (paper_dict, api_name, keywords) tuples
        - Statistics dictionary
    """
    if num_workers is None:
        # For I/O-bound tasks, use more threads than CPU cores
        num_workers = min(32, (cpu_count() or 1) * 2)

    logging.info(f"Parallel file loading with {num_workers} workers (threading)")

    # Collect all file paths and metadata
    file_tasks = []

    logging.info("Using config_used.yml for keyword mapping")

    # Step 1: Discover API directories and query indices from filesystem
    api_to_queries = discover_api_directories(dir_collect)

    # Step 2: Reconstruct query → keywords mapping from config
    query_to_keywords = reconstruct_query_to_keywords_mapping(config_used)

    # Step 3: Collect file tasks using reconstructed mapping
    for api_name in api_to_queries:
        # Skip APIs not in reconstructed mapping (shouldn't happen, but defensive)
        if api_name not in query_to_keywords:
            logging.warning(
                f"API '{api_name}' found in filesystem but not in config reconstruction. Skipping."
            )
            continue

        for query_index in api_to_queries[api_name]:
            # Get keywords for this query index
            keywords = query_to_keywords[api_name].get(query_index, [])

            if not keywords:
                logging.warning(
                    f"No keywords found for {api_name}/query_{query_index}. Using empty list."
                )

            # Get directory for this API/query combination
            query_dir = os.path.join(dir_collect, api_name, query_index)

            if not os.path.exists(query_dir):
                continue

            # Collect all files in this directory
            for filename in os.listdir(query_dir):
                file_path = os.path.join(query_dir, filename)

                if os.path.isfile(file_path):
                    file_tasks.append((file_path, api_name, keywords))

    logging.info(f"Found {len(file_tasks)} JSON files to load")

    # Load files in parallel with progress bar
    start_time = time.time()
    papers_by_api = []
    total_papers = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks
        futures = [
            executor.submit(_load_json_file, file_path, api_name, keywords)
            for file_path, api_name, keywords in file_tasks
        ]

        # Collect results with progress bar
        results = []
        for future in tqdm(
            futures, total=len(file_tasks), desc="Loading JSON files", unit="file"
        ):
            results.append(future.result())

    # Collect results
    for papers_list, api_name, keywords, num_papers in results:
        total_papers += num_papers

        # Store as (paper, api_name, keywords) tuples
        for paper in papers_list:
            papers_by_api.append((paper, api_name, keywords))

    elapsed = time.time() - start_time

    # Statistics
    stats = {
        "files_loaded": len(file_tasks),
        "total_papers": total_papers,
        "elapsed_seconds": elapsed,
        "files_per_second": len(file_tasks) / elapsed if elapsed > 0 else 0,
        "papers_per_second": total_papers / elapsed if elapsed > 0 else 0,
    }

    logging.info(
        f"Loaded {total_papers:,} papers from {len(file_tasks)} files in {elapsed:.1f}s"
    )
    logging.info(
        f"Throughput: {stats['files_per_second']:.1f} files/sec, {stats['papers_per_second']:.1f} papers/sec"
    )

    return papers_by_api, stats


# ============================================================================
# PHASE 2: PARALLEL BATCH PROCESSING
# ============================================================================


def _process_batch_worker(
    args: tuple[list[tuple], str, list],
) -> list[dict]:
    """
    Worker function to process a batch of papers (spawn-safe, module-level).

    Args:
        args: Tuple of (batch, keyword_groups)

    Returns:
        List of processed paper dictionaries
    """
    batch, keyword_groups = args

    # Import format converters (in worker to avoid pickling issues)
    from src.crawlers.aggregate import (
        ArxivtoZoteroFormat,
        DBLPtoZoteroFormat,
        ElseviertoZoteroFormat,
        GoogleScholartoZoteroFormat,
        HALtoZoteroFormat,
        IEEEtoZoteroFormat,
        OpenAlextoZoteroFormat,
        SemanticScholartoZoteroFormat,
        SpringertoZoteroFormat,
    )

    FORMAT_CONVERTERS = {
        "SemanticScholar": SemanticScholartoZoteroFormat,
        "OpenAlex": OpenAlextoZoteroFormat,
        "IEEE": IEEEtoZoteroFormat,
        "Elsevier": ElseviertoZoteroFormat,
        "Springer": SpringertoZoteroFormat,
        "HAL": HALtoZoteroFormat,
        "DBLP": DBLPtoZoteroFormat,
        "Arxiv": ArxivtoZoteroFormat,
        "GoogleScholar": GoogleScholartoZoteroFormat,
    }

    # Import text filtering helper
    from src.aggregate_collect import _record_passes_text_filter

    results = []

    for paper, api_name, keywords in batch:
        # Convert format
        if api_name in FORMAT_CONVERTERS:
            try:
                converted = FORMAT_CONVERTERS[api_name](paper)

                # Apply text filtering
                if _record_passes_text_filter(
                    converted,
                    keywords,
                    keyword_groups=keyword_groups,
                ):
                    results.append(converted)

            except Exception as e:
                logging.debug(f"Error converting paper from {api_name}: {e}")
                continue

    return results


def parallel_process_papers(
    papers_by_api: list[tuple[dict, str, list[str]]],
    batch_size: int = 5000,
    num_workers: int | None = None,
    keyword_groups: list | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Process papers in parallel batches (convert format + text filtering).

    Args:
        papers_by_api: List of (paper_dict, api_name, keywords) tuples
        batch_size: Papers per batch
        num_workers: Number of parallel workers
        keyword_groups: Optional list of keyword groups from config (for dual-group mode)

    Returns:
        Tuple of:
        - DataFrame with processed papers
        - Statistics dictionary
    """
    if num_workers is None:
        num_workers = max(1, cpu_count() - 1)

    logging.info(
        f"Parallel batch processing with {num_workers} workers, batch size {batch_size}"
    )

    # Split into batches
    batches = []
    for i in range(0, len(papers_by_api), batch_size):
        batch = papers_by_api[i : i + batch_size]
        batches.append((batch, keyword_groups))

    logging.info(f"Processing {len(papers_by_api):,} papers in {len(batches)} batches")

    # Process batches in parallel
    start_time = time.time()
    all_results = []

    with Pool(num_workers) as pool:
        results = list(
            tqdm(
                pool.imap_unordered(_process_batch_worker, batches),
                total=len(batches),
                desc="Processing papers",
                unit="batch",
            )
        )

    # Flatten results
    for batch_results in results:
        all_results.extend(batch_results)

    elapsed = time.time() - start_time

    # Create DataFrame
    df = pd.DataFrame(all_results)

    # Statistics
    stats = {
        "papers_processed": len(papers_by_api),
        "papers_filtered": len(df),
        "papers_rejected": len(papers_by_api) - len(df),
        "rejection_rate": (len(papers_by_api) - len(df)) / len(papers_by_api)
        if len(papers_by_api) > 0
        else 0,
        "elapsed_seconds": elapsed,
        "papers_per_second": len(papers_by_api) / elapsed if elapsed > 0 else 0,
    }

    logging.info(f"Processed {len(papers_by_api):,} papers in {elapsed:.1f}s")
    logging.info(
        f"Filtered: {len(df):,} papers ({stats['rejection_rate'] * 100:.1f}% rejected)"
    )
    logging.info(f"Throughput: {stats['papers_per_second']:.1f} papers/sec")

    return df, stats


# ============================================================================
# PHASE 3: SIMPLE HASH-BASED DEDUPLICATION
# ============================================================================


def simple_deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Simple, fast deduplication using hash-based exact matching.

    Strategy:
    1. DOI-based dedup (hash set, O(n))
    2. Normalized title dedup (hash dict, O(n))
    3. Exact substring matching only (fast, sufficient for most cases)

    Normalization:
    - Lowercase
    - Strip whitespace
    - Remove punctuation
    - Examples:
      * "Machine Learning!" → "machine learning"
      * "Deep Learning  " → "deep learning"

    Args:
        df: DataFrame with papers to deduplicate

    Returns:
        Tuple of:
        - Deduplicated DataFrame
        - Statistics dictionary
    """
    logging.info(f"Starting simple deduplication on {len(df):,} papers")
    start_time = time.time()

    initial_count = len(df)
    df_output = df.copy()

    # ========================================================================
    # STEP 1: DOI-based deduplication
    # ========================================================================

    # Separate papers with valid vs missing DOIs
    has_valid_doi = df_output["DOI"].apply(is_valid)
    papers_with_doi = df_output[has_valid_doi].copy()
    papers_without_doi = df_output[~has_valid_doi].copy()

    valid_dois = len(papers_with_doi)

    # Drop duplicates ONLY among papers with valid DOIs
    doi_before = len(papers_with_doi)
    papers_with_doi = papers_with_doi.drop_duplicates(subset=["DOI"], keep="first")
    doi_removed = doi_before - len(papers_with_doi)

    # Recombine: deduplicated papers with DOI + all papers without DOI
    df_output = pd.concat([papers_with_doi, papers_without_doi], ignore_index=True)

    logging.info(
        f"DOI deduplication: {valid_dois:,} valid DOIs, removed {doi_removed:,} duplicates"
    )

    # ========================================================================
    # STEP 2: Normalized title deduplication
    # ========================================================================

    # Create normalized title column (lowercase, stripped, no punctuation)
    df_output["title_normalized"] = (
        df_output["title"]
        .fillna("")
        .str.lower()
        .str.strip()
        .str.replace(r"[^\w\s]", "", regex=True)  # Remove punctuation
        .str.replace(r"\s+", " ", regex=True)  # Normalize whitespace
    )

    # Separate papers with valid vs missing titles
    has_valid_title = df_output["title_normalized"] != ""
    papers_with_title = df_output[has_valid_title].copy()
    papers_without_title = df_output[~has_valid_title].copy()

    valid_titles = len(papers_with_title)

    # Drop duplicates ONLY among papers with valid titles
    title_before = len(papers_with_title)
    papers_with_title = papers_with_title.drop_duplicates(
        subset=["title_normalized"], keep="first"
    )
    title_removed = title_before - len(papers_with_title)

    # Recombine: deduplicated papers with title + all papers without title
    df_output = pd.concat([papers_with_title, papers_without_title], ignore_index=True)

    # Drop the temporary normalized column
    df_output = df_output.drop(columns=["title_normalized"])

    logging.info(
        f"Title deduplication: {valid_titles:,} valid titles, removed {title_removed:,} duplicates"
    )

    # ========================================================================
    # Final statistics
    # ========================================================================

    elapsed = time.time() - start_time
    final_count = len(df_output)
    total_removed = initial_count - final_count

    stats = {
        "initial_count": initial_count,
        "final_count": final_count,
        "total_removed": total_removed,
        "removal_rate": total_removed / initial_count if initial_count > 0 else 0,
        "doi_removed": doi_removed,
        "title_removed": title_removed,
        "elapsed_seconds": elapsed,
        "papers_per_second": initial_count / elapsed if elapsed > 0 else 0,
    }

    logging.info(
        f"Deduplication complete: {initial_count:,} → {final_count:,} papers ({total_removed:,} removed, {stats['removal_rate'] * 100:.1f}%)"
    )
    logging.info(
        f"Deduplication took {elapsed:.2f}s ({stats['papers_per_second']:.1f} papers/sec)"
    )

    # Reset index
    df_output = df_output.reset_index(drop=True)

    return df_output, stats


# ============================================================================
# MAIN PARALLEL AGGREGATION FUNCTION
# ============================================================================


def parallel_aggregate(
    dir_collect: str,
    config_used: dict,
    txt_filters: bool = True,
    num_workers: int | None = None,
    batch_size: int = 5000,
    keyword_groups: list | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Main parallel aggregation function (orchestrates all phases).

    Args:
        dir_collect: Base collection directory
        config_used: Configuration dictionary from config_used.yml
        txt_filters: Enable text filtering
        num_workers: Number of parallel workers
        batch_size: Papers per batch
        keyword_groups: Optional list of keyword groups from config (for dual-group mode)

    Returns:
        Tuple of:
        - Aggregated and deduplicated DataFrame
        - Combined statistics dictionary
    """
    logging.info("=" * 70)
    logging.info("PARALLEL AGGREGATION STARTED")
    logging.info("=" * 70)

    overall_start = time.time()
    combined_stats = {}

    # ========================================================================
    # PHASE 1: PARALLEL FILE LOADING
    # ========================================================================

    logging.info("\n--- Phase 1: Parallel File Loading ---")
    papers_by_api, load_stats = parallel_load_all_files(
        dir_collect,
        config_used=config_used,
        num_workers=num_workers,
    )
    combined_stats["loading"] = load_stats

    if not papers_by_api:
        logging.error("No papers loaded. Check collection directory and state file.")
        return pd.DataFrame(), combined_stats

    # ========================================================================
    # PHASE 2: PARALLEL BATCH PROCESSING
    # ========================================================================

    if txt_filters:
        logging.info(
            "\n--- Phase 2: Parallel Batch Processing (with text filtering) ---"
        )
        df, process_stats = parallel_process_papers(
            papers_by_api,
            batch_size=batch_size,
            num_workers=num_workers,
            keyword_groups=keyword_groups,
        )
        combined_stats["processing"] = process_stats
    else:
        # No filtering - just convert formats
        logging.info("\n--- Phase 2: Format Conversion (no filtering) ---")
        # TODO: Implement format-only conversion without filtering (currently unsupported - use filter_enabled=True)
        df = pd.DataFrame()

    if df.empty:
        logging.warning("No papers after processing. Check filtering criteria.")
        return df, combined_stats

    # ========================================================================
    # PHASE 3: SIMPLE DEDUPLICATION
    # ========================================================================

    logging.info("\n--- Phase 3: Simple Hash-Based Deduplication ---")
    df_dedup, dedup_stats = simple_deduplicate(df)
    combined_stats["deduplication"] = dedup_stats

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================

    overall_elapsed = time.time() - overall_start
    combined_stats["overall"] = {
        "total_elapsed_seconds": overall_elapsed,
        "papers_loaded": load_stats["total_papers"],
        "papers_after_filtering": len(df),
        "papers_final": len(df_dedup),
        "overall_throughput": load_stats["total_papers"] / overall_elapsed
        if overall_elapsed > 0
        else 0,
    }

    logging.info("\n" + "=" * 70)
    logging.info("PARALLEL AGGREGATION COMPLETE")
    logging.info("=" * 70)
    logging.info(
        f"Total time: {overall_elapsed:.1f}s ({overall_elapsed / 60:.1f} minutes)"
    )
    logging.info(f"Papers loaded: {load_stats['total_papers']:,}")
    logging.info(f"Papers after filtering: {len(df):,}")
    logging.info(f"Papers after deduplication: {len(df_dedup):,}")
    logging.info(
        f"Overall throughput: {combined_stats['overall']['overall_throughput']:.1f} papers/sec"
    )
    logging.info("=" * 70 + "\n")

    return df_dedup, combined_stats
