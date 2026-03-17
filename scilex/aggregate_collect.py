import argparse
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm

import scilex.citations.citations_tools as cit_tools
from scilex.config import SciLExConfig  # noqa: F811
from scilex.constants import is_valid
from scilex.logging_config import log_section, setup_logging  # noqa: F811
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
from scilex.pipeline.text_filter import (  # noqa: F811
    check_keywords_in_text,
    keyword_matches_in_abstract,
    record_passes_text_filter,
)

# Backward-compatible aliases (old names with leading _)
_keyword_matches_in_abstract = keyword_matches_in_abstract
_check_keywords_in_text = check_keywords_in_text
_record_passes_text_filter = record_passes_text_filter
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


# Global lock for thread-safe rate limiting
_rate_limit_lock = threading.Lock()

# Global lock for thread-safe stats updates
_stats_lock = threading.Lock()


def _load_checkpoint(checkpoint_path):
    """Load checkpoint data if exists."""
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logging.warning(f"Could not load checkpoint: {e}")
    return None


def _save_checkpoint(checkpoint_path, data):
    """Save checkpoint data."""
    try:
        with open(checkpoint_path, "w") as f:
            json.dump(data, f)
        logging.debug(f"Checkpoint saved to {checkpoint_path}")
    except OSError as e:
        logging.warning(f"Could not save checkpoint: {e}")


def _get_ss_citations_if_available(row):
    """Extract Semantic Scholar citation data from a paper row.

    Args:
        row: Pandas Series representing a paper with potential SS citation fields

    Returns:
        tuple: (citation_count, reference_count) or (None, None) if not available
    """
    ss_citation_count = row.get("ss_citation_count")
    ss_reference_count = row.get("ss_reference_count")

    # Check if SS data exists (even if 0 - zero citations is valid for recent papers)
    has_ss_data = pd.notna(ss_citation_count) or pd.notna(ss_reference_count)

    if has_ss_data:
        # Return the values, defaulting to 0 if one is missing
        # Note: 0 is a valid value meaning "API confirmed 0 citations"
        citation_count = int(ss_citation_count) if pd.notna(ss_citation_count) else 0
        reference_count = int(ss_reference_count) if pd.notna(ss_reference_count) else 0
        return (citation_count, reference_count)

    return (None, None)


def _get_oa_citations_if_available(row):
    """Extract OpenAlex citation data from a paper row.

    OpenAlex provides cited_by_count (how many papers cite this one) but
    not a reference count. Returns citation count only; reference count
    is set to 0 (unknown).

    Args:
        row: Pandas Series representing a paper with potential OA citation fields

    Returns:
        int or None: Citation count if available, None otherwise
    """
    oa_citation_count = row.get("oa_citation_count")

    if pd.notna(oa_citation_count):
        return int(oa_citation_count)

    return None


def _fetch_citation_for_paper(
    index,
    doi,
    stats,
    checkpoint_interval,
    checkpoint_path,
    extras,
    nb_citeds,
    nb_citations,
    cache_path=None,
    ss_citation_count=None,
    ss_reference_count=None,
    crossref_mailto=None,
):
    """
    Fetch citations for a single paper (thread-safe with four-tier strategy).

    Four-tier strategy: Cache → Semantic Scholar → CrossRef → OpenCitations
    1. Check citation cache first (instant, no API call)
    2. If cache miss, check Semantic Scholar data (already in memory, no API call)
    3. If SS data unavailable, call CrossRef API (~3 req/sec)
    4. If CrossRef miss, call OpenCitations API (slowest, 1 req/sec)

    Args:
        index: Paper index in DataFrame
        doi: DOI string or None
        stats: Shared dictionary for statistics tracking
        checkpoint_interval: Save checkpoint every N papers
        checkpoint_path: Path to checkpoint file
        extras: List to store citation data
        nb_citeds: List to store cited count
        nb_citations: List to store citing count
        cache_path: Optional path to citation cache database
        ss_citation_count: Semantic Scholar citation count (if available)
        ss_reference_count: Semantic Scholar reference count (if available)
        crossref_mailto: Email for CrossRef polite pool (optional)

    Returns:
        dict: Result with index and status
    """
    if not is_valid(doi):
        with _stats_lock:
            stats["no_doi"] += 1
        return {"index": index, "status": "no_doi"}

    try:
        # Check cache first (5x speedup on cache hits)
        from scilex.citations.cache import cache_citation, get_cached_citation

        cached_data = get_cached_citation(str(doi), cache_path)
        if cached_data is not None:
            # Cache hit - use cached data
            extras[index] = cached_data["citations"]
            nb_citeds[index] = cached_data["nb_cited"]
            nb_citations[index] = cached_data["nb_citations"]

            # Track API stats from cache
            api_stats = cached_data["api_stats"]
            with _stats_lock:
                stats["cache_hit"] += 1
                if (
                    api_stats["cit_status"] == "success"
                    and api_stats["ref_status"] == "success"
                ):
                    stats["success"] += 1

            return {"index": index, "status": "cache_hit"}

        # Cache miss - check Semantic Scholar data before calling OpenCitations
        with _stats_lock:
            stats["cache_miss"] += 1

        # Tier 2: Check if Semantic Scholar data is available (no API call needed)
        if ss_citation_count is not None or ss_reference_count is not None:
            # Use SS data (already in memory)
            nb_cited = ss_reference_count if ss_reference_count is not None else 0
            nb_citation = ss_citation_count if ss_citation_count is not None else 0

            # Create a minimal citations structure (SS doesn't provide detailed citation list)
            citations = {
                "citing_dois": [],  # SS API doesn't provide detailed citation DOIs
                "cited_dois": [],  # SS API doesn't provide detailed reference DOIs
                "nb_cited": nb_cited,
                "nb_citations": nb_citation,
                "source": "semantic_scholar",
            }

            # Store results
            extras[index] = str(citations)
            nb_citeds[index] = nb_cited
            nb_citations[index] = nb_citation

            # Create success api_stats for caching
            api_stats = {
                "cit_status": "success",
                "ref_status": "success",
                "source": "semantic_scholar",
            }

            # Cache SS data for future runs (30-day TTL)
            cache_citation(
                doi=str(doi),
                citations_json=str(citations),
                nb_cited=nb_cited,
                nb_citations=nb_citation,
                api_stats=api_stats,
                cache_path=cache_path,
            )

            with _stats_lock:
                stats["ss_used"] += 1
                stats["success"] += 1
            return {"index": index, "status": "ss_used"}

        # Tier 3: Live CrossRef API call (~3 req/sec, much faster than OC)
        cr_result = cit_tools.getCrossRefCitation(str(doi), mailto=crossref_mailto)
        if cr_result is not None:
            cr_cit, cr_ref = cr_result

            citations = {
                "citing_dois": [],
                "cited_dois": [],
                "nb_cited": cr_ref,
                "nb_citations": cr_cit,
                "source": "crossref",
            }

            extras[index] = str(citations)
            nb_citeds[index] = cr_ref
            nb_citations[index] = cr_cit

            api_stats = {
                "cit_status": "success",
                "ref_status": "success",
                "source": "crossref",
            }

            cache_citation(
                doi=str(doi),
                citations_json=str(citations),
                nb_cited=cr_ref,
                nb_citations=cr_cit,
                api_stats=api_stats,
                cache_path=cache_path,
            )

            with _stats_lock:
                stats["cr_used"] += 1
                stats["success"] += 1
            return {"index": index, "status": "cr_used"}

        # Tier 4: No SS or CrossRef data - call OpenCitations API (slowest)
        with _stats_lock:
            stats["opencitations_used"] += 1
        citations, api_stats = cit_tools.getRefandCitFormatted(str(doi))

        # Add source marker to api_stats
        api_stats["source"] = "opencitations"

        # Track statistics
        with _stats_lock:
            if (
                api_stats["cit_status"] == "success"
                and api_stats["ref_status"] == "success"
            ):
                stats["success"] += 1
            elif "timeout" in [api_stats["cit_status"], api_stats["ref_status"]]:
                stats["timeout"] += 1
            else:
                stats["error"] += 1

        # Calculate citation counts
        nb_ = cit_tools.countCitations(citations)
        nb_cited = nb_["nb_cited"]
        nb_citation = nb_["nb_citations"]

        # Store results
        extras[index] = str(citations)
        nb_citeds[index] = nb_cited
        nb_citations[index] = nb_citation

        # Cache the results for future runs (30-day TTL)
        cache_citation(
            doi=str(doi),
            citations_json=str(citations),
            nb_cited=nb_cited,
            nb_citations=nb_citation,
            api_stats=api_stats,
            cache_path=cache_path,
        )

        # Checkpoint save (thread-safe)
        if checkpoint_interval and (index + 1) % checkpoint_interval == 0:
            with _rate_limit_lock:
                checkpoint_data = {
                    "last_index": index,
                    "stats": dict(stats),
                    "extras": extras[: index + 1],
                    "nb_citeds": nb_citeds[: index + 1],
                    "nb_citations": nb_citations[: index + 1],
                }
                _save_checkpoint(checkpoint_path, checkpoint_data)
                logging.info(f"Checkpoint saved at paper {index + 1}")

        return {"index": index, "status": "success"}

    except Exception as e:
        logging.error(f"Unexpected error fetching citations for DOI {doi}: {e}")
        with _stats_lock:
            stats["error"] += 1
        return {"index": index, "status": "error"}


def _store_citation_result(
    index, extras, nb_citeds, nb_citations, citations_data, nb_cited, nb_citation
):
    """Store citation result into the result arrays.

    Args:
        index: Paper index in the arrays.
        extras: List to store citation data strings.
        nb_citeds: List to store cited counts.
        nb_citations: List to store citing counts.
        citations_data: Citation data (dict or string) to store.
        nb_cited: Number of cited papers.
        nb_citation: Number of citing papers.
    """
    extras[index] = str(citations_data)
    nb_citeds[index] = nb_cited
    nb_citations[index] = nb_citation


def _update_pbar_postfix(pbar, stats, use_cache):
    """Update progress bar postfix with current statistics."""
    postfix = {
        "✓": stats["success"],
        "✗": stats["error"],
        "⏱": stats["timeout"],
        "⊘": stats["no_doi"],
    }
    if use_cache:
        postfix["💾"] = stats["cache_hit"]
        postfix["🔬"] = stats["ss_used"]
        postfix["🅰"] = stats["oa_used"]
        postfix["📚"] = stats["cr_used"]
        postfix["🔗"] = stats["opencitations_used"]
    pbar.set_postfix(postfix)


def _fetch_citations_parallel(
    df_clean,
    num_workers=3,
    checkpoint_interval=100,
    checkpoint_path=None,
    resume_from=None,
    use_cache=True,
    crossref_mailto=None,
):
    """Fetch citations using phase-based batch processing.

    Processes papers through five sequential phases, each resolving a subset.
    Unresolved papers flow to the next phase. Much faster than per-paper
    processing because phases 1-2b use bulk/in-memory operations.

    Phases:
        1.  Batch cache lookup (1 SQL query, instant)
        2.  Semantic Scholar check (in-memory, instant)
        2b. OpenAlex citation count (in-memory, instant)
        3.  CrossRef batch API (N/20 HTTP requests, ~3 req/sec per batch)
        4.  OpenCitations fallback (ThreadPoolExecutor, 1 req/sec per DOI)

    Args:
        df_clean: DataFrame with papers
        num_workers: Number of parallel workers (used for Phase 4)
        checkpoint_interval: Save checkpoint every N papers
        checkpoint_path: Path to checkpoint file
        resume_from: Index to resume from (if resuming)
        use_cache: Whether to use citation caching (default: True)

    Returns:
        tuple: (extras list, nb_citeds list, nb_citations list, stats dict)
    """
    total_papers = len(df_clean)

    # Initialize citation cache
    cache_path = None
    if use_cache:
        from scilex.citations.cache import (
            cleanup_expired_cache,
            get_cache_stats,
            initialize_cache,
        )

        cache_path = initialize_cache()
        logging.info(f"Citation cache initialized at {cache_path}")

        cache_stats = get_cache_stats(cache_path)
        logging.info(
            f"Cache stats: {cache_stats['active_entries']} active entries, "
            f"{cache_stats['expired_entries']} expired"
        )

        if cache_stats["expired_entries"] > 0:
            removed = cleanup_expired_cache(cache_path)
            logging.info(f"Cleaned up {removed} expired cache entries")

    # Initialize result lists
    extras = [""] * total_papers
    nb_citeds = [""] * total_papers
    nb_citations = [""] * total_papers

    # Initialize statistics
    stats = {
        "success": 0,
        "timeout": 0,
        "error": 0,
        "no_doi": 0,
        "cache_hit": 0,
        "cache_miss": 0,
        "ss_used": 0,
        "oa_used": 0,
        "cr_used": 0,
        "opencitations_used": 0,
    }

    # Load from checkpoint if resuming
    start_index = 0
    if resume_from is not None:
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            start_index = checkpoint["last_index"] + 1
            stats = checkpoint["stats"]
            stats.setdefault("cr_used", 0)
            stats.setdefault("oa_used", 0)
            stats.setdefault("opencitations_used", 0)
            checkpoint_len = min(
                start_index,
                len(checkpoint.get("extras", [])),
                len(checkpoint.get("nb_citeds", [])),
                len(checkpoint.get("nb_citations", [])),
            )
            for i in range(checkpoint_len):
                extras[i] = checkpoint["extras"][i]
                nb_citeds[i] = checkpoint["nb_citeds"][i]
                nb_citations[i] = checkpoint["nb_citations"][i]
            if checkpoint_len < start_index:
                logging.warning(
                    f"Checkpoint data truncated: expected {start_index} entries, "
                    f"found {checkpoint_len}. Re-fetching missing entries."
                )
            logging.info(f"Resuming from paper {start_index}")

    papers_with_doi = df_clean["DOI"].apply(is_valid).sum()
    logging.info(
        f"Fetching citation data for {papers_with_doi}/{total_papers} papers with valid DOIs"
    )
    if use_cache:
        logging.info("Using citation cache (30-day TTL) — batch mode for phases 1-3")
    logging.info(f"Using {num_workers} workers for OpenCitations fallback (phase 4)")
    logging.info(
        "Phase strategy: Cache → SS → OpenAlex → CrossRef (batch) → OpenCitations (threaded)"
    )

    # ========================================================================
    # Prepare paper data: collect citation metadata for each paper
    # ========================================================================
    paper_data = []  # (position, doi, ss_cit, ss_ref, oa_cit)
    for position, (_df_index, row) in enumerate(
        df_clean.iloc[start_index:].iterrows(), start=start_index
    ):
        doi = row.get("DOI")
        ss_cit_count, ss_ref_count = _get_ss_citations_if_available(row)
        oa_cit_count = _get_oa_citations_if_available(row)
        paper_data.append((position, doi, ss_cit_count, ss_ref_count, oa_cit_count))

    # Separate papers: has_doi vs no_doi
    papers_no_doi = []
    papers_with_valid_doi = []
    for pos, doi, ss_cit, ss_ref, oa_cit in paper_data:
        if is_valid(doi):
            papers_with_valid_doi.append((pos, str(doi), ss_cit, ss_ref, oa_cit))
        else:
            papers_no_doi.append(pos)

    # ========================================================================
    # Single tqdm progress bar spanning all phases
    # ========================================================================
    with tqdm(
        total=total_papers,
        initial=start_index,
        desc="Citations [init]",
        unit="paper",
        position=0,
        leave=True,
    ) as pbar:
        # Resolve no-DOI papers immediately
        for _pos in papers_no_doi:
            stats["no_doi"] += 1
            pbar.update(1)
        _update_pbar_postfix(pbar, stats, use_cache)

        # Track which papers still need resolution
        # Key: position, Value: (doi, ss_cit, ss_ref, oa_cit)
        remaining = {
            pos: (doi, ss_cit, ss_ref, oa_cit)
            for pos, doi, ss_cit, ss_ref, oa_cit in papers_with_valid_doi
        }

        # ====================================================================
        # PHASE 1: Batch cache lookup
        # ====================================================================
        if use_cache and cache_path and remaining:
            pbar.set_description("Citations [cache]")
            from scilex.citations.cache import get_cached_citations_batch

            all_dois = [doi for doi, _, _, _ in remaining.values()]
            cached = get_cached_citations_batch(all_dois, cache_path)

            resolved_positions = []
            for pos, (doi, _ss_cit, _ss_ref, _oa_cit) in remaining.items():
                if doi in cached:
                    data = cached[doi]
                    _store_citation_result(
                        pos,
                        extras,
                        nb_citeds,
                        nb_citations,
                        data["citations"],
                        data["nb_cited"],
                        data["nb_citations"],
                    )
                    api_stats = data["api_stats"]
                    stats["cache_hit"] += 1
                    if (
                        api_stats["cit_status"] == "success"
                        and api_stats["ref_status"] == "success"
                    ):
                        stats["success"] += 1
                    resolved_positions.append(pos)
                    pbar.update(1)

            for pos in resolved_positions:
                del remaining[pos]
            stats["cache_miss"] += len(remaining)
            _update_pbar_postfix(pbar, stats, use_cache)
            logging.debug(
                f"Phase 1 (cache): {len(resolved_positions)} hits, "
                f"{len(remaining)} remaining"
            )

        # ====================================================================
        # PHASE 2: Semantic Scholar (in-memory, no API call)
        # ====================================================================
        if remaining:
            pbar.set_description("Citations [SS]")
            from scilex.citations.cache import cache_citations_batch

            resolved_positions = []
            cache_entries = []
            for pos, (doi, ss_cit, ss_ref, _oa_cit) in remaining.items():
                if ss_cit is not None or ss_ref is not None:
                    nb_cited = ss_ref if ss_ref is not None else 0
                    nb_citation = ss_cit if ss_cit is not None else 0
                    citations = {
                        "citing_dois": [],
                        "cited_dois": [],
                        "nb_cited": nb_cited,
                        "nb_citations": nb_citation,
                        "source": "semantic_scholar",
                    }
                    _store_citation_result(
                        pos,
                        extras,
                        nb_citeds,
                        nb_citations,
                        citations,
                        nb_cited,
                        nb_citation,
                    )
                    stats["ss_used"] += 1
                    stats["success"] += 1
                    resolved_positions.append(pos)
                    pbar.update(1)

                    # Prepare for batch caching
                    if use_cache and cache_path:
                        cache_entries.append(
                            {
                                "doi": doi,
                                "citations_json": str(citations),
                                "nb_cited": nb_cited,
                                "nb_citations": nb_citation,
                                "api_stats": {
                                    "cit_status": "success",
                                    "ref_status": "success",
                                    "source": "semantic_scholar",
                                },
                            }
                        )

            for pos in resolved_positions:
                del remaining[pos]

            # Batch cache SS results
            if cache_entries and use_cache and cache_path:
                cache_citations_batch(cache_entries, cache_path)

            _update_pbar_postfix(pbar, stats, use_cache)
            logging.debug(
                f"Phase 2 (SS): {len(resolved_positions)} resolved, "
                f"{len(remaining)} remaining"
            )

        # ====================================================================
        # PHASE 2b: OpenAlex citation count (in-memory, no API call)
        # ====================================================================
        if remaining:
            pbar.set_description("Citations [OpenAlex]")
            from scilex.citations.cache import cache_citations_batch

            resolved_positions = []
            cache_entries = []
            for pos, (doi, _ss_cit, _ss_ref, oa_cit) in remaining.items():
                if oa_cit is not None:
                    nb_cited = 0  # OpenAlex doesn't provide reference count
                    nb_citation = oa_cit
                    citations = {
                        "citing_dois": [],
                        "cited_dois": [],
                        "nb_cited": nb_cited,
                        "nb_citations": nb_citation,
                        "source": "openalex",
                    }
                    _store_citation_result(
                        pos,
                        extras,
                        nb_citeds,
                        nb_citations,
                        citations,
                        nb_cited,
                        nb_citation,
                    )
                    stats["oa_used"] += 1
                    stats["success"] += 1
                    resolved_positions.append(pos)
                    pbar.update(1)

                    # Prepare for batch caching
                    if use_cache and cache_path:
                        cache_entries.append(
                            {
                                "doi": doi,
                                "citations_json": str(citations),
                                "nb_cited": nb_cited,
                                "nb_citations": nb_citation,
                                "api_stats": {
                                    "cit_status": "success",
                                    "ref_status": "success",
                                    "source": "openalex",
                                },
                            }
                        )

            for pos in resolved_positions:
                del remaining[pos]

            # Batch cache OA results
            if cache_entries and use_cache and cache_path:
                cache_citations_batch(cache_entries, cache_path)

            _update_pbar_postfix(pbar, stats, use_cache)
            logging.debug(
                f"Phase 2b (OpenAlex): {len(resolved_positions)} resolved, "
                f"{len(remaining)} remaining"
            )

        # ====================================================================
        # PHASE 3: CrossRef batch API (N/20 HTTP requests)
        # ====================================================================
        if remaining:
            pbar.set_description("Citations [CrossRef]")

            remaining_dois = [(pos, doi) for pos, (doi, _, _, _) in remaining.items()]
            batch_size = cit_tools.CROSSREF_BATCH_SIZE

            for batch_start in range(0, len(remaining_dois), batch_size):
                batch = remaining_dois[batch_start : batch_start + batch_size]
                batch_dois = [doi for _, doi in batch]

                try:
                    cr_results = cit_tools.getCrossRefCitationsBatch(
                        batch_dois, mailto=crossref_mailto
                    )
                except Exception as e:
                    logging.debug(f"CrossRef batch request failed: {e}")
                    cr_results = {}
                cr_results = cr_results or {}

                cache_entries = []
                for pos, doi in batch:
                    doi_lower = doi.lower()
                    if doi_lower in cr_results:
                        cr_cit, cr_ref = cr_results[doi_lower]
                        citations = {
                            "citing_dois": [],
                            "cited_dois": [],
                            "nb_cited": cr_ref,
                            "nb_citations": cr_cit,
                            "source": "crossref",
                        }
                        _store_citation_result(
                            pos,
                            extras,
                            nb_citeds,
                            nb_citations,
                            citations,
                            cr_ref,
                            cr_cit,
                        )
                        stats["cr_used"] += 1
                        stats["success"] += 1
                        # Remove from remaining
                        if pos in remaining:
                            del remaining[pos]
                        pbar.update(1)

                        if use_cache and cache_path:
                            cache_entries.append(
                                {
                                    "doi": doi,
                                    "citations_json": str(citations),
                                    "nb_cited": cr_ref,
                                    "nb_citations": cr_cit,
                                    "api_stats": {
                                        "cit_status": "success",
                                        "ref_status": "success",
                                        "source": "crossref",
                                    },
                                }
                            )

                # Batch cache CrossRef results
                if cache_entries and use_cache and cache_path:
                    from scilex.citations.cache import cache_citations_batch

                    cache_citations_batch(cache_entries, cache_path)

                # Checkpoint after each CrossRef batch
                if checkpoint_path:
                    checkpoint_data = {
                        "last_index": max(pos for pos, _ in batch),
                        "stats": dict(stats),
                        "extras": extras[: max(pos for pos, _ in batch) + 1],
                        "nb_citeds": nb_citeds[: max(pos for pos, _ in batch) + 1],
                        "nb_citations": nb_citations[
                            : max(pos for pos, _ in batch) + 1
                        ],
                    }
                    _save_checkpoint(checkpoint_path, checkpoint_data)

                # Update postfix after each batch so stats refresh live
                _update_pbar_postfix(pbar, stats, use_cache)

            logging.debug(
                f"Phase 3 (CrossRef): {stats['cr_used']} resolved, "
                f"{len(remaining)} remaining for OpenCitations"
            )

        # ====================================================================
        # PHASE 4: OpenCitations fallback (threaded, 1 req/sec per DOI)
        # ====================================================================
        if remaining:
            pbar.set_description("Citations [OpenCitations]")

            oc_papers = list(remaining.items())  # [(pos, (doi, ...)), ...]

            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_pos = {}
                for pos, (doi, _, _, _) in oc_papers:
                    future = executor.submit(
                        _fetch_citation_for_paper,
                        pos,
                        doi,
                        stats,
                        checkpoint_interval,
                        checkpoint_path,
                        extras,
                        nb_citeds,
                        nb_citations,
                        cache_path,
                        None,  # ss_citation_count — already checked in phase 2
                        None,  # ss_reference_count
                        None,  # crossref_mailto — already checked in phase 3
                    )
                    future_to_pos[future] = pos

                for future in as_completed(future_to_pos):
                    future.result()
                    pbar.update(1)
                    _update_pbar_postfix(pbar, stats, use_cache)

        pbar.set_description("Citations [done]")

    # ========================================================================
    # Log statistics
    # ========================================================================
    total_with_doi = total_papers - stats["no_doi"]
    cache_hit_rate = 0
    ss_usage_rate = 0
    oa_usage_rate = 0
    cr_usage_rate = 0
    opencitations_rate = 0

    if use_cache and (stats["cache_hit"] + stats["cache_miss"]) > 0:
        cache_hit_rate = (
            stats["cache_hit"] / (stats["cache_hit"] + stats["cache_miss"]) * 100
        )

    if total_with_doi > 0:
        ss_usage_rate = stats["ss_used"] / total_with_doi * 100
        oa_usage_rate = stats["oa_used"] / total_with_doi * 100
        cr_usage_rate = stats["cr_used"] / total_with_doi * 100
        opencitations_rate = stats["opencitations_used"] / total_with_doi * 100

    logging.info(
        f"Citation fetching complete: ✓ {stats['success']} successful, "
        f"✗ {stats['error']} errors, ⏱ {stats['timeout']} timeouts, "
        f"⊘ {stats['no_doi']} without DOI"
    )

    if use_cache:
        logging.info(
            f"Cache performance: {stats['cache_hit']} hits, {stats['cache_miss']} misses "
            f"({cache_hit_rate:.1f}% hit rate)"
        )

    logging.info("Citation resolution by phase (sequential fallthrough):")
    logging.info(f"  💾 Cache hits: {stats['cache_hit']} papers")
    logging.info(
        f"  🔬 Semantic Scholar: {stats['ss_used']} papers ({ss_usage_rate:.1f}%)"
    )
    logging.info(f"  🅰 OpenAlex: {stats['oa_used']} papers ({oa_usage_rate:.1f}%)")
    logging.info(f"  📚 CrossRef: {stats['cr_used']} papers ({cr_usage_rate:.1f}%)")
    logging.info(
        f"  🔗 OpenCitations API: {stats['opencitations_used']} papers ({opencitations_rate:.1f}%)"
    )

    api_calls_saved = (
        stats["cache_hit"] + stats["ss_used"] + stats["oa_used"] + stats["cr_used"]
    )
    if total_with_doi > 0:
        savings_rate = api_calls_saved / total_with_doi * 100
        logging.info(
            f"  💰 OpenCitations API calls avoided: {api_calls_saved}/{total_with_doi} ({savings_rate:.1f}%)"
        )

    return extras, nb_citeds, nb_citations, stats


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
        help="Number of parallel workers (default: auto-detect CPU count - 1)",
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
    args = parser.parse_args()

    logger = logging.getLogger(__name__)

    # Load configuration
    config = SciLExConfig.from_files()

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
    )

    # Run the pipeline
    run_aggregation(config, options)


if __name__ == "__main__":
    main()
