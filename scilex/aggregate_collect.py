import argparse
import csv
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
from dateutil import parser as date_parser
from tqdm import tqdm

import scilex.citations.citations_tools as cit_tools
from scilex.abstract_validation import (
    filter_by_abstract_quality,
    validate_dataframe_abstracts,
)
from scilex.config_defaults import (
    DEFAULT_AGGREGATED_FILENAME,
    DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RELEVANCE_WEIGHTS,
    MIN_ABSTRACT_QUALITY_SCORE,
)
from scilex.constants import (
    MISSING_VALUE,
    CitationFilterConfig,
    is_valid,
    normalize_path_component,
)
from scilex.crawlers.aggregate import (
    ArxivtoZoteroFormat,
    DBLPtoZoteroFormat,
    ElseviertoZoteroFormat,
    HALtoZoteroFormat,
    IEEEtoZoteroFormat,
    IstextoZoteroFormat,
    OpenAIREtoZoteroFormat,
    OpenAlextoZoteroFormat,
    ORKGtoZoteroFormat,
    PubMedCentraltoZoteroFormat,
    PubMedtoZoteroFormat,
    SemanticScholartoZoteroFormat,
    SpringertoZoteroFormat,
)
from scilex.crawlers.utils import load_all_configs, load_yaml_config
from scilex.duplicate_tracking import (
    analyze_and_report_duplicates,
    generate_itemtype_distribution_report,
)
from scilex.keyword_validation import (
    check_keyword_in_text as _kv_check_keyword_in_text,
    check_keyword_in_text_flexible as _kv_check_keyword_flexible,
    generate_keyword_validation_report,
)
from scilex.logging_config import log_section, setup_logging
from scilex.quality_validation import (
    apply_quality_filters,
    generate_data_completeness_report,
)

# Set up logging configuration with environment variable support
setup_logging()

# Format converters dispatcher - replaces eval() for security
FORMAT_CONVERTERS = {
    "SemanticScholar": SemanticScholartoZoteroFormat,
    "OpenAlex": OpenAlextoZoteroFormat,
    "IEEE": IEEEtoZoteroFormat,
    "Elsevier": ElseviertoZoteroFormat,
    "Springer": SpringertoZoteroFormat,
    "HAL": HALtoZoteroFormat,
    "DBLP": DBLPtoZoteroFormat,
    "Istex": IstextoZoteroFormat,
    "Arxiv": ArxivtoZoteroFormat,
    "PubMed": PubMedtoZoteroFormat,
    "PubMedCentral": PubMedCentraltoZoteroFormat,
    "OpenAIRE": OpenAIREtoZoteroFormat,
    "ORKG": ORKGtoZoteroFormat,
}

# ============================================================================
# Filtering Progress Tracker
# ============================================================================


class FilteringTracker:
    """Track filtering stages and generate comprehensive reports."""

    def __init__(self):
        self.stages = []
        self.initial_count = 0

    def set_initial(self, count, description="Raw papers collected"):
        """Set initial paper count."""
        self.initial_count = count
        self.stages.append(
            {
                "stage": "Initial",
                "description": description,
                "papers": count,
                "removed": 0,
                "removal_rate": 0.0,
            }
        )

    def add_stage(self, stage_name, papers_remaining, description=""):
        """Add a filtering stage with paper count."""
        if not self.stages:
            self.set_initial(papers_remaining, "Starting point")
            return

        prev_count = self.stages[-1]["papers"]
        removed = prev_count - papers_remaining
        removal_rate = (removed / prev_count * 100) if prev_count > 0 else 0.0

        self.stages.append(
            {
                "stage": stage_name,
                "description": description,
                "papers": papers_remaining,
                "removed": removed,
                "removal_rate": removal_rate,
            }
        )

    def generate_report(self):
        """Generate comprehensive filtering summary report."""
        if not self.stages or self.initial_count == 0:
            return "No filtering data available"

        lines = []
        lines.append("\n" + "=" * 80)
        lines.append("FILTERING PIPELINE SUMMARY")
        lines.append("=" * 80)

        for i, stage_info in enumerate(self.stages):
            stage = stage_info["stage"]
            desc = stage_info["description"]
            papers = stage_info["papers"]
            removed = stage_info["removed"]
            removal_rate = stage_info["removal_rate"]

            # Calculate cumulative removal
            cumulative_removed = self.initial_count - papers
            cumulative_rate = (
                (cumulative_removed / self.initial_count * 100)
                if self.initial_count > 0
                else 0.0
            )

            lines.append("")
            if i == 0:
                lines.append(f"[{stage}] {desc}")
                lines.append(f"  Papers: {papers:,}")
            else:
                lines.append(f"[{stage}] {desc}")
                lines.append(f"  Papers remaining: {papers:,}")
                lines.append(f"  Removed this stage: {removed:,} ({removal_rate:.1f}%)")
                lines.append(
                    f"  Cumulative removal: {cumulative_removed:,} ({cumulative_rate:.1f}%)"
                )

        final_count = self.stages[-1]["papers"]
        total_removed = self.initial_count - final_count
        total_removal_rate = (
            (total_removed / self.initial_count * 100)
            if self.initial_count > 0
            else 0.0
        )

        lines.append("")
        lines.append("-" * 80)
        lines.append("FINAL RESULTS:")
        lines.append(f"  Started with: {self.initial_count:,} papers")
        lines.append(f"  Final output: {final_count:,} papers")
        lines.append(
            f"  Total removed: {total_removed:,} papers ({total_removal_rate:.1f}%)"
        )
        lines.append(f"  Retention rate: {100 - total_removal_rate:.1f}%")
        lines.append("=" * 80)

        return "\n".join(lines)


def _keyword_matches_in_abstract(keyword, abstract_text):
    """Check if keyword appears in abstract text (handles both dict and string formats)."""
    if isinstance(abstract_text, dict) and "p" in abstract_text:
        abstract_content = " ".join(abstract_text["p"]).lower()
    else:
        abstract_content = str(abstract_text).lower()

    return keyword.lower() in abstract_content


def _check_keywords_in_text(keywords_list, text):
    """Exact match: check if any keyword from a list appears verbatim in text.

    Used for mandatory query-term filtering (Group 1 / Group 2 keywords).
    """
    return any(_kv_check_keyword_in_text(kw, text) for kw in keywords_list)


def _check_keywords_flexible(keywords_list, text):
    """Flexible match: check if any bonus keyword appears in text.

    Uses word-level fallback so 'Cultural Heritage' matches even when
    'cultural' and 'heritage' appear separately in the abstract.
    """
    return any(_kv_check_keyword_flexible(kw, text) for kw in keywords_list)


def _record_passes_text_filter(
    record,
    keywords,
    keyword_groups=None,
    bonus_keywords=None,
):
    """Check if record contains required keywords in title or abstract.

    Dual-group mode (2 groups):
      Group1 (exact) AND (Group2 (exact) OR any bonus keyword (flexible))
      If no bonus_keywords are configured, Group2 exact match is still required.

    Single-group mode: any keyword from the group (exact match).

    Args:
        record: Paper record dictionary
        keywords: List of keywords from the query (for backward compatibility)
        keyword_groups: Optional list of keyword groups from config (for dual-group mode)
        bonus_keywords: Optional list of domain terms used as flexible fallback
                        for Group 2 when no exact Group 2 match is found.

    Returns:
        bool: True if keyword requirements are met
    """
    if not keywords and not keyword_groups:
        return True

    abstract = record.get("abstract", MISSING_VALUE)
    title = record.get("title", "")

    combined_text = f"{title} {abstract if is_valid(abstract) else ''}"

    # ========================================================================
    # DUAL KEYWORD GROUP MODE
    # ========================================================================
    if keyword_groups and len(keyword_groups) == 2:
        group1, group2 = keyword_groups

        if not group1 or not group2:
            all_keywords = [kw for g in keyword_groups for kw in g if g]
            if not all_keywords:
                return True
            keywords = all_keywords
        else:
            group1_match = _check_keywords_in_text(group1, combined_text)
            if not group1_match:
                return False

            # Group 2: exact match first, then bonus keyword flexible fallback
            group2_match = _check_keywords_in_text(group2, combined_text)
            if group2_match:
                return True
            if bonus_keywords:
                return _check_keywords_flexible(bonus_keywords, combined_text)
            return False

    # ========================================================================
    # SINGLE KEYWORD GROUP MODE
    # ========================================================================
    if keyword_groups:
        keywords = [kw for group in keyword_groups for kw in group if group]

    return _check_keywords_in_text(keywords, combined_text)


# Global lock for thread-safe rate limiting
_rate_limit_lock = threading.Lock()

# Global lock for thread-safe stats updates
_stats_lock = threading.Lock()


def _calculate_paper_age_months(date_str):
    """Calculate paper age in months from publication date.

    Args:
        date_str: Publication date string (various formats)

    Returns:
        int: Age in months, or None if date invalid/missing
    """
    if not is_valid(date_str):
        return None

    try:
        # Parse date string (handles multiple formats)
        pub_date = date_parser.parse(str(date_str))
        now = datetime.now()

        # Calculate difference in months
        months_diff = (now.year - pub_date.year) * 12 + (now.month - pub_date.month)
        return max(0, months_diff)  # Ensure non-negative

    except (ValueError, TypeError, date_parser.ParserError):
        return None


def _calculate_required_citations(months_since_pub):
    """Calculate required citation threshold based on paper age.

    Formula: Graduated thresholds with grace period for recent papers
    Uses centralized constants from CitationFilterConfig.

    Args:
        months_since_pub: Paper age in months

    Returns:
        int: Required citation count
    """
    if months_since_pub is None or pd.isna(months_since_pub):
        return CitationFilterConfig.GRACE_PERIOD_CITATIONS  # No date = no filtering

    if months_since_pub <= CitationFilterConfig.GRACE_PERIOD_MONTHS:
        return CitationFilterConfig.GRACE_PERIOD_CITATIONS
    elif months_since_pub <= CitationFilterConfig.EARLY_THRESHOLD_MONTHS:
        return CitationFilterConfig.EARLY_CITATIONS
    elif months_since_pub <= CitationFilterConfig.MEDIUM_THRESHOLD_MONTHS:
        return CitationFilterConfig.MEDIUM_CITATIONS
    elif months_since_pub <= CitationFilterConfig.MATURE_THRESHOLD_MONTHS:
        # Gradual increase from MATURE_BASE_CITATIONS to 8
        return CitationFilterConfig.MATURE_BASE_CITATIONS + int(
            (months_since_pub - CitationFilterConfig.MEDIUM_THRESHOLD_MONTHS) / 4
        )
    else:
        # 36+ months: ESTABLISHED_BASE_CITATIONS+ (incremental for older papers)
        return CitationFilterConfig.ESTABLISHED_BASE_CITATIONS + int(
            (months_since_pub - CitationFilterConfig.MATURE_THRESHOLD_MONTHS) / 12
        )


def _apply_time_aware_citation_filter(df, citation_col="nb_citation", date_col="date"):
    """Apply time-aware citation filtering to DataFrame.

    Papers are filtered based on citation count relative to their age:
    - Papers without DOI: Bypass filter (citations couldn't be looked up)
    - Recent papers (0-18 months): No filtering (0 citations OK)
    - Older papers: Increasing citation requirements

    Args:
        df: DataFrame with papers
        citation_col: Column name for citation count
        date_col: Column name for publication date

    Returns:
        pd.DataFrame: Filtered DataFrame with citation_threshold column added
    """
    logging.info("Applying time-aware citation filtering...")

    # ========================================================================
    # STEP 1: Separate papers without DOI (they bypass citation filtering)
    # ========================================================================
    # Papers without DOI couldn't have their citations looked up, so it's unfair
    # to filter them based on citation count. They bypass the filter entirely.
    has_valid_doi = df["DOI"].apply(is_valid)
    df_no_doi = df[~has_valid_doi].copy()
    df_with_doi = df[has_valid_doi].copy()

    no_doi_count = len(df_no_doi)
    if no_doi_count > 0:
        logging.info(
            f"  Papers without DOI: {no_doi_count:,} (bypassing citation filter)"
        )

    # If no papers have DOI, return all papers unchanged
    if len(df_with_doi) == 0:
        logging.info("  No papers with DOI - skipping citation filtering")
        df["paper_age_months"] = df[date_col].apply(_calculate_paper_age_months)
        df["citation_threshold"] = 0  # No threshold for papers without DOI
        return df

    # ========================================================================
    # STEP 2: Apply citation filter only to papers WITH DOI
    # ========================================================================

    # Calculate age and required citations
    df_with_doi["paper_age_months"] = df_with_doi[date_col].apply(
        _calculate_paper_age_months
    )
    df_with_doi["citation_threshold"] = df_with_doi["paper_age_months"].apply(
        _calculate_required_citations
    )

    # Convert citation count to numeric (handle empty/invalid values)
    df_with_doi[citation_col] = (
        pd.to_numeric(df_with_doi[citation_col], errors="coerce").fillna(0).astype(int)
    )

    # Apply filtering to papers with DOI only
    initial_with_doi = len(df_with_doi)
    df_filtered = df_with_doi[
        df_with_doi[citation_col] >= df_with_doi["citation_threshold"]
    ].copy()
    removed_count = initial_with_doi - len(df_filtered)

    # ========================================================================
    # STEP 3: Merge filtered papers with DOI-less papers (which bypassed filter)
    # ========================================================================
    if no_doi_count > 0:
        # Add placeholder columns to DOI-less papers for consistency
        df_no_doi["paper_age_months"] = df_no_doi[date_col].apply(
            _calculate_paper_age_months
        )
        df_no_doi["citation_threshold"] = 0  # No threshold (bypassed)
        df_no_doi[citation_col] = 0  # Unknown citations

        # Combine: filtered papers with DOI + all papers without DOI
        df_filtered = pd.concat([df_filtered, df_no_doi], ignore_index=True)

    initial_count = len(df)

    # Calculate zero-citation statistics (only for papers with DOI)
    # Guard against empty df_filtered: apply() on empty Series returns float64,
    # which causes pandas to drop all columns during boolean indexing.
    if len(df_filtered) > 0:
        zero_citation_count = (
            df_filtered[df_filtered["DOI"].apply(is_valid)][citation_col] == 0
        ).sum()
    else:
        zero_citation_count = 0
    zero_citation_rate = (
        (zero_citation_count / initial_with_doi * 100) if initial_with_doi > 0 else 0.0
    )

    # Log statistics
    logging.info("Time-aware citation filter applied:")
    logging.info(f"  Initial papers: {initial_count:,}")
    logging.info(f"  Papers with DOI (filtered): {initial_with_doi:,}")
    logging.info(f"  Papers without DOI (bypassed): {no_doi_count:,}")
    logging.info(
        f"  Papers with 0 citations (with DOI): {zero_citation_count:,} ({zero_citation_rate:.1f}%)"
    )
    logging.info(
        f"  Removed (from DOI papers): {removed_count:,} ({removed_count / initial_with_doi * 100:.1f}% of DOI papers)"
        if initial_with_doi > 0
        else f"  Removed (from DOI papers): {removed_count:,}"
    )
    logging.info(f"  Remaining: {len(df_filtered):,}")

    # Breakdown by age group
    age_groups = [
        (0, 18, "0-18 months (grace period)"),
        (18, 21, "18-21 months (≥1 citation)"),
        (21, 24, "21-24 months (≥3 citations)"),
        (24, 36, "24-36 months (≥5-8 citations)"),
        (36, 999, "36+ months (≥10 citations)"),
    ]

    logging.info("Breakdown by age group:")
    for min_age, max_age, label in age_groups:
        group = df_filtered[
            (df_filtered["paper_age_months"] >= min_age)
            & (df_filtered["paper_age_months"] < max_age)
        ]
        if len(group) > 0:
            avg_citations = group[citation_col].mean()
            zero_in_group = (group[citation_col] == 0).sum()
            zero_pct = (zero_in_group / len(group) * 100) if len(group) > 0 else 0
            logging.info(
                f"  {label}: {len(group):,} papers (avg {avg_citations:.1f} citations, {zero_in_group} with 0 = {zero_pct:.0f}%)"
            )

    # Add warning for high zero-citation rates
    if zero_citation_rate > CitationFilterConfig.HIGH_ZERO_CITATION_RATE:
        logging.warning("\n" + "=" * 70)
        logging.warning(
            f"HIGH ZERO-CITATION RATE: {zero_citation_rate:.1f}% of papers have 0 citations"
        )
        logging.warning("This may indicate:")
        logging.warning(
            "  • Very recent dataset (expected for preprints < 18 months old)"
        )
        logging.warning(
            "  • OpenCitations coverage gaps (limited for preprints/recent papers)"
        )
        logging.warning(
            "  • Consider using Semantic Scholar citations for better coverage"
        )
        logging.warning("=" * 70 + "\n")

    # Drop temporary age column (keep citation_threshold for transparency)
    df_filtered = df_filtered.drop(columns=["paper_age_months"])

    return df_filtered


def _count_keyword_matches(row, keyword_groups, bonus_keywords=None):
    """Count total keyword matches in title and abstract.

    Args:
        row: DataFrame row (paper record)
        keyword_groups: List of mandatory keyword groups from config
        bonus_keywords: Optional list of bonus keywords (counted at 0.5 weight)

    Returns:
        float: Total number of keyword matches found (bonus keywords weighted at 0.5)
    """
    if not keyword_groups and not bonus_keywords:
        return 0

    # Flatten mandatory keyword groups
    all_keywords = []
    for group in keyword_groups:
        if isinstance(group, list):
            all_keywords.extend(group)

    # Combine title and abstract
    title = str(row.get("title", "")).lower()
    abstract = str(row.get("abstract", "")).lower()
    combined_text = f"{title} {abstract}"

    # Count matches for mandatory keywords (full weight)
    match_count = 0
    for keyword in all_keywords:
        keyword_lower = keyword.lower()
        match_count += combined_text.count(keyword_lower)

    # Count matches for bonus keywords (half weight = 0.5 per match)
    if bonus_keywords:
        bonus_match_count = 0
        for keyword in bonus_keywords:
            keyword_lower = keyword.lower()
            bonus_match_count += combined_text.count(keyword_lower)
        # Add bonus matches at 0.5 weight each
        match_count += bonus_match_count * 0.5

    return match_count


def _calculate_relevance_score(
    row, keyword_groups, has_citations=False, config=None, bonus_keywords=None
):
    """Calculate composite relevance score for a paper using normalized components.

    Components (all normalized to 0-10 scale):
    1. Keyword relevance: Content relevance to search terms
    2. Metadata quality: Completeness and richness of metadata
    3. Publication type: Scholarly publication venue
    4. Citation impact: Research impact (minimal weight to avoid recency bias)

    Args:
        row: DataFrame row (paper record)
        keyword_groups: List of mandatory keyword groups from config
        has_citations: Whether citation data is available
        config: Configuration dict containing quality_filters
        bonus_keywords: Optional list of bonus keywords (weighted at 0.5)

    Returns:
        float: Relevance score (0-10 scale, higher = more relevant)
    """
    import math

    # Get configuration or use defaults
    if config is None:
        config = {}

    quality_filters = config.get("quality_filters", {})

    # Get component weights (must sum to 1.0)
    weights = quality_filters.get("relevance_weights", DEFAULT_RELEVANCE_WEIGHTS)

    # 1. Keyword relevance (normalize to 0-10)
    keyword_matches = _count_keyword_matches(row, keyword_groups, bonus_keywords)
    # Cap at 10 matches for normalization (can be adjusted based on data)
    keyword_score = min(keyword_matches, 10)

    # 2. Metadata quality (normalize to 0-10)
    quality = row.get("quality_score", 0)
    if quality != MISSING_VALUE and quality != "":
        try:
            # Quality typically 0-50, so divide by 5
            quality_score = min(float(quality) / 5, 10)
        except (ValueError, TypeError):
            quality_score = 0
    else:
        quality_score = 0

    # 3. Publication type (0 or 10 based on config)
    item_type = str(row.get("itemType", "")).strip()
    itemtype_weights = quality_filters.get(
        "itemtype_relevance_weights", DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS
    )
    # Check if this itemType is in the list of valued types
    itemtype_score = 10 if itemtype_weights.get(item_type, False) else 0

    # 4. Citation impact (minimal weight to avoid recency bias)
    citation_score = 0
    if has_citations:
        citation_count = pd.to_numeric(row.get("nb_citation", 0), errors="coerce")
        if pd.notna(citation_count) and citation_count > 0:
            # log-scaled but with minimal influence
            # log(1+100) ≈ 4.6, so multiply by 2.17 to reach 10
            citation_score = min(math.log(1 + float(citation_count)) * 2.17, 10)

    # Apply percentage weights
    final_score = (
        keyword_score * weights.get("keywords", 0.45)
        + quality_score * weights.get("quality", 0.25)
        + itemtype_score * weights.get("itemtype", 0.20)
        + citation_score * weights.get("citations", 0.10)
    )

    return round(final_score, 2)


def _apply_relevance_ranking(
    df,
    keyword_groups,
    top_n=None,
    has_citations=False,
    config=None,
    bonus_keywords=None,
):
    """Apply composite relevance ranking to DataFrame.

    Calculates relevance score for each paper and optionally filters to top N.

    Args:
        df: DataFrame with papers
        keyword_groups: List of mandatory keyword groups from config
        top_n: Optional - keep only top N most relevant papers
        has_citations: Whether citation data is available
        config: Configuration dict containing quality_filters
        bonus_keywords: Optional list of bonus keywords (weighted at 0.5)

    Returns:
        pd.DataFrame: Ranked DataFrame with relevance_score column
    """
    logging.info("Calculating normalized relevance scores (0-10 scale)...")

    # Calculate scores
    df["relevance_score"] = df.apply(
        lambda row: _calculate_relevance_score(
            row, keyword_groups, has_citations, config, bonus_keywords
        ),
        axis=1,
    )

    # Sort by relevance (descending)
    df_ranked = df.sort_values("relevance_score", ascending=False).copy()

    logging.info("Relevance scoring complete (normalized 0-10 scale)")
    logging.info(
        f"  Score range: {df_ranked['relevance_score'].min():.2f} - {df_ranked['relevance_score'].max():.2f}"
    )
    logging.info(f"  Mean score: {df_ranked['relevance_score'].mean():.2f}")
    logging.info(f"  Median score: {df_ranked['relevance_score'].median():.2f}")

    # Optionally filter to top N
    if top_n and top_n < len(df_ranked):
        initial_count = len(df_ranked)
        df_ranked = df_ranked.head(top_n)
        logging.info(
            f"Filtered to top {top_n} most relevant papers (removed {initial_count - top_n:,})"
        )

    return df_ranked


def _tag_papers_with_bonus_keywords(df, bonus_keywords):
    """Add a bonus_keyword_tags column listing matched bonus keywords per paper.

    Each matched keyword is prefixed with 'BK:' and tags are pipe-separated,
    e.g. 'BK:Cultural Heritage|BK:Digital Humanities'.
    Uses the same word-level fallback as the main text filter so compound
    keywords like 'Cultural Heritage' are matched even when the words appear
    separately in the abstract.

    Args:
        df: DataFrame with 'title' and 'abstract' columns
        bonus_keywords: List of bonus keyword strings from config

    Returns:
        pd.DataFrame: DataFrame with new 'bonus_keyword_tags' column
    """
    if not bonus_keywords:
        df = df.copy()
        df["bonus_keyword_tags"] = ""
        return df

    def _tags_for_row(row):
        title = str(row.get("title", "") or "")
        abstract = str(row.get("abstract", "") or "")
        combined = title + " " + abstract
        matched = [
            f"BK:{kw}"
            for kw in bonus_keywords
            if _kv_check_keyword_flexible(kw, combined)
        ]
        return "|".join(matched)

    df = df.copy()
    df["bonus_keyword_tags"] = df.apply(_tags_for_row, axis=1)
    return df


def _generate_bonus_keyword_stats(df, bonus_keywords):
    """Log a distribution report for bonus keyword tags.

    Args:
        df: DataFrame with 'bonus_keyword_tags' column
        bonus_keywords: List of bonus keyword strings from config
    """
    if not bonus_keywords or "bonus_keyword_tags" not in df.columns:
        return

    total = len(df)
    tagged = (df["bonus_keyword_tags"] != "").sum()

    lines = [
        "",
        "=" * 60,
        "BONUS KEYWORD TAG DISTRIBUTION",
        "=" * 60,
        f"  Papers with at least one tag : {tagged:,} / {total:,} ({tagged/total*100:.1f}%)",
        "",
    ]

    for kw in bonus_keywords:
        tag = f"BK:{kw}"
        count = df["bonus_keyword_tags"].str.contains(tag, regex=False).sum()
        bar = "#" * min(int(count / max(total, 1) * 40), 40)
        lines.append(f"  {kw:<35s} {count:5,}  {bar}")

    lines.append("=" * 60)
    logging.info("\n".join(lines))


def _apply_itemtype_bypass(df, bypass_item_types):
    """
    Separate papers into bypass and non-bypass groups based on itemType.

    Papers with itemTypes in bypass_item_types skip subsequent quality filters.
    This speeds up processing for high-quality publication types.

    Args:
        df: Input DataFrame
        bypass_item_types: List of itemType values that bypass filters
                          (e.g., ["journalArticle", "conferencePaper"])

    Returns:
        tuple: (bypass_df, non_bypass_df)
            - bypass_df: Papers that bypass filters (high-quality types)
            - non_bypass_df: Papers that need filtering
    """
    if not bypass_item_types:
        # No bypass configured - all papers need filtering
        return pd.DataFrame(), df

    # Check if itemType column exists
    if "itemType" not in df.columns:
        logging.warning("itemType column not found - bypas filter skipped")
        return pd.DataFrame(), df

    # Split into bypass and non-bypass groups
    bypass_df = df[df["itemType"].isin(bypass_item_types)].copy()
    non_bypass_df = df[~df["itemType"].isin(bypass_item_types)].copy()

    logging.info(
        f"ItemType bypass: {len(bypass_df)} papers bypass filters ({', '.join(bypass_item_types)})"
    )
    logging.info(f"ItemType bypass: {len(non_bypass_df)} papers require filtering")

    return bypass_df, non_bypass_df


def _apply_itemtype_filter(df, allowed_types, enabled):
    """
    Filter papers to only keep specified itemTypes (whitelist mode).

    This filter runs EARLY in the pipeline (after deduplication, before quality filters)
    to remove unwanted publication types. Papers with missing/NA itemType are removed
    in strict mode.

    Args:
        df: Input DataFrame
        allowed_types: List of allowed itemType values (whitelist)
                      e.g., ["journalArticle", "conferencePaper"]
        enabled: Boolean flag to enable/disable filtering

    Returns:
        tuple: (filtered_df, stats_dict)
            - filtered_df: DataFrame with only allowed itemTypes
            - stats_dict: Statistics about filtering operation
    """
    stats = {
        "enabled": enabled,
        "total_before": len(df),
        "total_after": 0,
        "removed": 0,
        "removed_missing_itemtype": 0,
        "kept_by_type": {},
        "removed_by_type": {},
    }

    # If disabled, return original DataFrame
    if not enabled:
        logging.info("ItemType filtering: DISABLED - all itemTypes allowed")
        stats["total_after"] = len(df)
        return df, stats

    # Check if itemType column exists
    if "itemType" not in df.columns:
        logging.warning(
            "ItemType filtering: itemType column not found - filtering skipped"
        )
        stats["total_after"] = len(df)
        return df, stats

    # Warn if allowed_types is empty
    if not allowed_types:
        logging.warning(
            "ItemType filtering: allowed_item_types list is EMPTY - all papers will be removed!"
        )
        stats["total_after"] = 0
        stats["removed"] = len(df)
        return pd.DataFrame(columns=df.columns), stats

    logging.info(
        f"ItemType filtering: ENABLED - whitelist mode with {len(allowed_types)} allowed types"
    )
    logging.info(f"ItemType filtering: Allowed types: {', '.join(allowed_types)}")

    # Identify papers with missing itemType (strict mode - remove these)
    missing_mask = (
        df["itemType"].isna() | (df["itemType"] == "") | (df["itemType"] == "NA")
    )
    missing_count = missing_mask.sum()

    # Filter: Keep only papers with itemType in allowed list
    # Papers with missing itemType will be excluded (strict mode)
    filtered_df = df[df["itemType"].isin(allowed_types) & ~missing_mask].copy()

    # Calculate statistics
    stats["total_after"] = len(filtered_df)
    stats["removed"] = stats["total_before"] - stats["total_after"]
    stats["removed_missing_itemtype"] = missing_count

    # Count kept papers by type
    if not filtered_df.empty:
        kept_counts = filtered_df["itemType"].value_counts()
        stats["kept_by_type"] = kept_counts.to_dict()

    # Count removed papers by type (excluding missing)
    removed_df = df[~df.index.isin(filtered_df.index) & ~missing_mask]
    if not removed_df.empty:
        removed_counts = removed_df["itemType"].value_counts()
        stats["removed_by_type"] = removed_counts.to_dict()

    # Log detailed statistics
    logging.info(f"ItemType filtering: {stats['total_before']} papers before filtering")
    logging.info(
        f"ItemType filtering: {stats['total_after']} papers after filtering (KEPT)"
    )
    logging.info(
        f"ItemType filtering: {stats['removed']} papers removed ({stats['removed'] / stats['total_before'] * 100:.1f}%)"
    )

    if stats["removed_missing_itemtype"] > 0:
        logging.info(
            f"  - {stats['removed_missing_itemtype']} papers removed: missing/NA itemType"
        )

    if stats["kept_by_type"]:
        logging.info("  Papers KEPT by itemType:")
        for item_type, count in sorted(
            stats["kept_by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            logging.info(f"    - {item_type}: {count} papers")

    if stats["removed_by_type"]:
        logging.info("  Papers REMOVED by itemType:")
        for item_type, count in sorted(
            stats["removed_by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            logging.info(f"    - {item_type}: {count} papers")

    return filtered_df, stats


def _fill_missing_urls_from_doi(df):
    """Fill missing URLs using DOI resolver (https://doi.org/).

    Papers without URLs but with valid DOIs get a URL generated from their DOI.
    The DOI resolver (doi.org) permanently redirects to the actual paper URL.

    Args:
        df: DataFrame with 'url' and 'DOI' columns

    Returns:
        pd.DataFrame: DataFrame with missing URLs filled from DOIs
        dict: Statistics about the URL filling operation
    """
    if "url" not in df.columns or "DOI" not in df.columns:
        logging.warning("Cannot fill URLs: missing 'url' or 'DOI' column")
        return df, {"filled": 0, "already_valid": 0, "no_doi": 0}

    stats = {"filled": 0, "already_valid": 0, "no_doi": 0}

    def generate_url_from_doi(row):
        url = row.get("url")
        doi = row.get("DOI")

        # URL already valid
        if is_valid(url):
            stats["already_valid"] += 1
            return url

        # No DOI to generate URL from
        if not is_valid(doi):
            stats["no_doi"] += 1
            return url  # Keep original (MISSING_VALUE)

        # Generate URL from DOI
        doi_str = str(doi).strip()
        # Remove existing prefix if present
        if doi_str.lower().startswith("https://doi.org/"):
            doi_str = doi_str[16:]
        elif doi_str.lower().startswith("http://doi.org/"):
            doi_str = doi_str[15:]

        stats["filled"] += 1
        return f"https://doi.org/{doi_str}"

    df = df.copy()
    df["url"] = df.apply(generate_url_from_doi, axis=1)

    logging.info(
        f"URL fallback: {stats['filled']} URLs generated from DOIs, "
        f"{stats['already_valid']} already valid, "
        f"{stats['no_doi']} papers without DOI"
    )

    return df, stats


def _use_semantic_scholar_citations_fallback(df):
    """Use Semantic Scholar citation data as fallback when OpenCitations data is missing or zero.

    Args:
        df: DataFrame with both OpenCitations and Semantic Scholar citation data

    Returns:
        pd.DataFrame: DataFrame with citation data filled from Semantic Scholar where needed
    """
    if "ss_citation_count" not in df.columns:
        logging.info(
            "Semantic Scholar citation data not available (only papers from SS API have this)"
        )
        return df

    # Count how many papers have SS citation data
    has_ss_data = df["ss_citation_count"].notna().sum()
    logging.info(f"Found Semantic Scholar citation data for {has_ss_data:,} papers")

    if has_ss_data == 0:
        return df

    # Use SS citation count as fallback when OpenCitations returns 0 or is missing
    initial_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()

    # Create fallback: use SS data when OpenCitations is 0 or missing
    df["nb_citation"] = df.apply(
        lambda row: row["ss_citation_count"]
        if (pd.isna(row["nb_citation"]) or row["nb_citation"] == 0)
        and pd.notna(row["ss_citation_count"])
        else row["nb_citation"],
        axis=1,
    )

    df["nb_cited"] = df.apply(
        lambda row: row["ss_reference_count"]
        if (pd.isna(row["nb_cited"]) or row["nb_cited"] == 0)
        and pd.notna(row["ss_reference_count"])
        else row["nb_cited"],
        axis=1,
    )

    # Count improvements
    final_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()
    improved_count = initial_zero_count - final_zero_count

    logging.info("Semantic Scholar fallback applied:")
    logging.info(f"  Papers with 0 citations before: {initial_zero_count:,}")
    logging.info(f"  Papers with 0 citations after: {final_zero_count:,}")
    logging.info(
        f"  Improved: {improved_count:,} papers ({improved_count / has_ss_data * 100:.1f}% of papers with SS data)"
    )

    return df


def _use_openalex_citations_fallback(df):
    """Use OpenAlex citation data as fallback when citation count is still missing or zero.

    OpenAlex provides cited_by_count (nb_citation only — no reference count).
    Applied after the SS fallback so it only fills gaps SS could not cover.

    Args:
        df: DataFrame with OpenAlex citation data

    Returns:
        pd.DataFrame: DataFrame with nb_citation filled from OpenAlex where needed
    """
    if "oa_citation_count" not in df.columns:
        logging.info(
            "OpenAlex citation data not available (only papers from OpenAlex API have this)"
        )
        return df

    has_oa_data = df["oa_citation_count"].notna().sum()
    logging.info(f"Found OpenAlex citation data for {has_oa_data:,} papers")

    if has_oa_data == 0:
        return df

    initial_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()

    # Fill nb_citation from OpenAlex when still 0 or missing
    df["nb_citation"] = df.apply(
        lambda row: row["oa_citation_count"]
        if (pd.isna(row["nb_citation"]) or row["nb_citation"] == 0)
        and pd.notna(row["oa_citation_count"])
        else row["nb_citation"],
        axis=1,
    )

    final_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()
    improved_count = initial_zero_count - final_zero_count

    logging.info("OpenAlex fallback applied:")
    logging.info(f"  Papers with 0 citations before: {initial_zero_count:,}")
    logging.info(f"  Papers with 0 citations after: {final_zero_count:,}")
    logging.info(
        f"  Improved: {improved_count:,} papers ({improved_count / has_oa_data * 100:.1f}% of papers with OA data)"
    )

    return df


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
    api_config=None,
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

    crossref_mailto = (api_config or {}).get("CrossRef", {}).get("mailto")

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


def _write_aggregation_report(
    dir_collect,
    collect_name,
    run_date,
    duration_seconds,
    main_config,
    parallel_stats,
    filtering_tracker,
    citation_stats,
    url_stats,
    df_clean,
):
    """Write aggregation report (Markdown + CSV) to dir_collect."""
    flat_stats = {}

    # --- Identity ---
    flat_stats["collect_name"] = collect_name
    flat_stats["run_date"] = run_date.strftime("%Y-%m-%d %H:%M:%S")
    flat_stats["duration_seconds"] = round(duration_seconds, 1)
    flat_stats["apis"] = ";".join(main_config.get("apis", []))
    flat_stats["years"] = ";".join(str(y) for y in main_config.get("years", []))

    # --- Loading ---
    ls = parallel_stats.get("loading", {})
    flat_stats["files_loaded"] = ls.get("files_loaded", 0)
    flat_stats["papers_loaded"] = ls.get("total_papers", 0)
    flat_stats["load_time_seconds"] = round(ls.get("elapsed_seconds", 0), 1)

    # --- Text filter ---
    ps = parallel_stats.get("processing", {})
    flat_stats["papers_after_text_filter"] = ps.get("papers_filtered", 0)
    flat_stats["papers_rejected_text"] = ps.get("papers_rejected", 0)

    # --- Dedup ---
    ds = parallel_stats.get("deduplication", {})
    flat_stats["papers_after_dedup"] = ds.get("final_count", 0)
    flat_stats["doi_duplicates_removed"] = ds.get("doi_removed", 0)
    flat_stats["title_duplicates_removed"] = ds.get("title_removed", 0)

    # --- Filtering stages ---
    flat_stats["papers_initial_post_dedup"] = filtering_tracker.initial_count
    flat_stats["papers_final"] = (
        filtering_tracker.stages[-1]["papers"] if filtering_tracker.stages else len(df_clean)
    )

    # --- URL fallback ---
    flat_stats["urls_filled_from_doi"] = url_stats.get("filled", 0)
    flat_stats["urls_already_valid"] = url_stats.get("already_valid", 0)

    # --- Citation fetching ---
    if citation_stats:
        for key, val in citation_stats.items():
            flat_stats[f"citation_{key}"] = val
        total_with_doi = len(df_clean) - citation_stats.get("no_doi", 0)
        cache_total = citation_stats.get("cache_hit", 0) + citation_stats.get("cache_miss", 0)
        flat_stats["citation_cache_hit_rate_pct"] = round(
            citation_stats.get("cache_hit", 0) / cache_total * 100, 1
        ) if cache_total > 0 else 0.0

    # --- Output quality ---
    flat_stats["papers_output"] = len(df_clean)
    if "DOI" in df_clean.columns:
        flat_stats["papers_with_doi"] = int(df_clean["DOI"].apply(is_valid).sum())
    if "abstract" in df_clean.columns:
        flat_stats["papers_with_abstract"] = int(df_clean["abstract"].apply(is_valid).sum())
    if "relevance_score" in df_clean.columns:
        flat_stats["relevance_score_mean"] = round(float(df_clean["relevance_score"].mean()), 2)
        flat_stats["relevance_score_min"] = round(float(df_clean["relevance_score"].min()), 2)
        flat_stats["relevance_score_max"] = round(float(df_clean["relevance_score"].max()), 2)
        flat_stats["relevance_score_median"] = round(float(df_clean["relevance_score"].median()), 2)
    if "nb_citation" in df_clean.columns:
        nb_cit = pd.to_numeric(df_clean["nb_citation"], errors="coerce").fillna(0)
        flat_stats["avg_citations"] = round(float(nb_cit.mean()), 1)
        flat_stats["max_citations"] = int(nb_cit.max())

    # =========================================================================
    # Write CSV (flat key-value)
    # =========================================================================
    csv_path = os.path.join(dir_collect, "aggregation_stats.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stat", "value"])
        for key, val in flat_stats.items():
            writer.writerow([key, val])

    # =========================================================================
    # Build Markdown
    # =========================================================================
    apis = main_config.get("apis", [])
    years = main_config.get("years", [])
    keywords = main_config.get("keywords", [])
    bonus_keywords = main_config.get("bonus_keywords") or []

    md = []
    md.append(f"# Aggregation Report — {collect_name}")
    md.append("")
    md.append(f"**Date:** {run_date.strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"**Duration:** {duration_seconds:.1f} s ({duration_seconds / 60:.1f} min)  ")
    md.append("")

    # --- Configuration ---
    md.append("## Configuration")
    md.append("")
    md.append(f"| Setting | Value |")
    md.append(f"|---------|-------|")
    md.append(f"| APIs | {', '.join(apis)} |")
    md.append(f"| Years | {', '.join(str(y) for y in years)} |")
    if isinstance(keywords, list) and keywords:
        if isinstance(keywords[0], list):
            for i, group in enumerate(keywords):
                md.append(f"| Keyword Group {i + 1} | {', '.join(group)} |")
        else:
            md.append(f"| Keywords | {', '.join(str(k) for k in keywords)} |")
    if bonus_keywords:
        md.append(f"| Bonus Keywords | {', '.join(bonus_keywords)} |")
    md.append("")

    # --- Collection loading ---
    md.append("## Collection Loading")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| JSON files loaded | {ls.get('files_loaded', 0):,} |")
    md.append(f"| Papers loaded | {ls.get('total_papers', 0):,} |")
    md.append(f"| Load time | {ls.get('elapsed_seconds', 0):.1f} s |")
    md.append(
        f"| Papers after text filter | {ps.get('papers_filtered', 0):,} "
        f"({(1 - ps.get('rejection_rate', 0)) * 100:.1f}% pass rate) |"
    )
    md.append(f"| DOI duplicates removed | {ds.get('doi_removed', 0):,} |")
    md.append(f"| Title duplicates removed | {ds.get('title_removed', 0):,} |")
    md.append(f"| Papers after deduplication | {ds.get('final_count', 0):,} |")
    md.append("")

    # --- Filtering pipeline ---
    md.append("## Filtering Pipeline")
    md.append("")
    if filtering_tracker.stages:
        initial = filtering_tracker.initial_count
        md.append("| Stage | Description | Papers | Removed | Stage Rate | Cumulative Removed |")
        md.append("|-------|-------------|--------|---------|------------|-------------------|")
        for info in filtering_tracker.stages:
            cum_removed = initial - info["papers"]
            cum_rate = (cum_removed / initial * 100) if initial > 0 else 0.0
            desc = info["description"][:60] + "…" if len(info["description"]) > 60 else info["description"]
            md.append(
                f"| {info['stage']} | {desc} | {info['papers']:,} | "
                f"{info['removed']:,} | {info['removal_rate']:.1f}% | "
                f"{cum_removed:,} ({cum_rate:.1f}%) |"
            )
    md.append("")

    # --- API coverage ---
    md.append("## API Coverage (Final Output)")
    md.append("")
    if "archive" in df_clean.columns:
        api_counts: dict[str, int] = {}
        for archive_str in df_clean["archive"].fillna(""):
            for api in archive_str.replace("*", "").split(";"):
                api = api.strip()
                if api:
                    api_counts[api] = api_counts.get(api, 0) + 1
        if api_counts:
            md.append("| API | Papers in Final Output |")
            md.append("|-----|----------------------|")
            for api_name, count in sorted(api_counts.items(), key=lambda x: x[1], reverse=True):
                md.append(f"| {api_name} | {count:,} |")
    md.append("")

    # --- Citation fetching ---
    if citation_stats:
        cs = citation_stats
        cache_total = cs.get("cache_hit", 0) + cs.get("cache_miss", 0)
        hit_rate = (cs.get("cache_hit", 0) / cache_total * 100) if cache_total > 0 else 0.0

        md.append("## Citation Fetching")
        md.append("")
        md.append("| Metric | Count |")
        md.append("|--------|-------|")
        md.append(f"| Successful | {cs.get('success', 0):,} |")
        md.append(f"| Errors | {cs.get('error', 0):,} |")
        md.append(f"| Timeouts | {cs.get('timeout', 0):,} |")
        md.append(f"| Without DOI (bypassed) | {cs.get('no_doi', 0):,} |")
        md.append(f"| Cache hits | {cs.get('cache_hit', 0):,} ({hit_rate:.1f}% hit rate) |")
        md.append(f"| Semantic Scholar (in-memory) | {cs.get('ss_used', 0):,} |")
        md.append(f"| OpenAlex (in-memory) | {cs.get('oa_used', 0):,} |")
        md.append(f"| CrossRef batch API | {cs.get('cr_used', 0):,} |")
        md.append(f"| OpenCitations API | {cs.get('opencitations_used', 0):,} |")
        md.append("")

    # --- URL fallback ---
    md.append("## URL Enrichment")
    md.append("")
    md.append("| Metric | Count |")
    md.append("|--------|-------|")
    md.append(f"| URLs generated from DOI | {url_stats.get('filled', 0):,} |")
    md.append(f"| URLs already present | {url_stats.get('already_valid', 0):,} |")
    md.append(f"| No DOI available | {url_stats.get('no_doi', 0):,} |")
    md.append("")

    # --- Output quality ---
    md.append("## Output Quality Metrics")
    md.append("")
    n = len(df_clean)
    md.append("| Metric | Value |")
    md.append("|--------|-------|")
    md.append(f"| Total papers output | {n:,} |")
    if "DOI" in df_clean.columns:
        doi_count = int(df_clean["DOI"].apply(is_valid).sum())
        md.append(f"| Papers with DOI | {doi_count:,} ({doi_count / n * 100:.1f}%) |")
    if "abstract" in df_clean.columns:
        abs_count = int(df_clean["abstract"].apply(is_valid).sum())
        md.append(f"| Papers with abstract | {abs_count:,} ({abs_count / n * 100:.1f}%) |")
    if "relevance_score" in df_clean.columns:
        md.append(f"| Relevance score — mean | {df_clean['relevance_score'].mean():.2f} |")
        md.append(f"| Relevance score — median | {df_clean['relevance_score'].median():.2f} |")
        md.append(f"| Relevance score — min | {df_clean['relevance_score'].min():.2f} |")
        md.append(f"| Relevance score — max | {df_clean['relevance_score'].max():.2f} |")
    if "nb_citation" in df_clean.columns:
        nb_cit = pd.to_numeric(df_clean["nb_citation"], errors="coerce").fillna(0)
        md.append(f"| Avg citations per paper | {nb_cit.mean():.1f} |")
        md.append(f"| Max citations | {int(nb_cit.max()):,} |")
    md.append("")
    md.append(
        f"*Report generated by SciLEx `aggregate_collect` — {run_date.strftime('%Y-%m-%d %H:%M:%S')}*"
    )

    md_path = os.path.join(dir_collect, "aggregation_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    logging.info(f"Aggregation report written → {md_path}")
    logging.info(f"Aggregation stats written  → {csv_path}")

    return md_path, csv_path


def _load_aggregate_config(collection_arg, src_dir):
    """
    Load main config for aggregation.

    If --collection is given, loads config_used.yml from that collection directory
    (accepts a collection name relative to output_dir, or a full path).
    Otherwise falls back to scilex.config.yml.

    Returns (main_config, api_config).
    """
    import yaml

    if collection_arg is not None:
        # Resolve name vs full path
        if os.path.isabs(collection_arg) or os.sep in collection_arg or "/" in collection_arg:
            collect_dir = collection_arg
        else:
            # Name only — look up output_dir from current scilex.config.yml
            current_config_path = os.path.join(src_dir, "scilex.config.yml")
            try:
                current_cfg = load_yaml_config(current_config_path)
                output_dir_base = current_cfg.get("output_dir", DEFAULT_OUTPUT_DIR)
            except FileNotFoundError:
                output_dir_base = DEFAULT_OUTPUT_DIR
            collect_dir = os.path.join(output_dir_base, collection_arg)

        config_path = os.path.join(collect_dir, "config_used.yml")
        if not os.path.isfile(config_path):
            print(f"Error: Cannot find saved config at {config_path}")
            print(
                "Make sure the collection name or path is correct and the collection has been started at least once."
            )
            sys.exit(1)
        main_config = load_yaml_config(config_path)
        logging.info(f"Aggregating collection '{main_config.get('collect_name')}' from {collect_dir}")
    else:
        configs = load_all_configs({"main_config": "scilex.config.yml", "api_config": "api.config.yml"})
        main_config = configs["main_config"]

    # api_config always comes from the standard location
    api_config_path = os.path.join(src_dir, "api.config.yml")
    try:
        api_config = load_yaml_config(api_config_path)
    except FileNotFoundError:
        api_config = {}

    return main_config, api_config


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Aggregate collected papers and fetch citations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Aggregate the collection defined in scilex.config.yml\n"
            "  python -m scilex aggregate\n\n"
            "  # Aggregate a specific previous collection by name\n"
            "  python -m scilex aggregate --collection CulturalHeritageAItools\n\n"
            "  # Aggregate a specific previous collection by full path\n"
            "  python -m scilex aggregate --collection C:\\output\\CulturalHeritageAItools\n"
        ),
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

    src_dir = os.path.dirname(os.path.abspath(__file__))
    main_config, api_config = _load_aggregate_config(args.collection, src_dir)

    run_start = datetime.now()
    logger = logging.getLogger(__name__)

    # Log aggregation start
    log_section(logger, "SciLEx Data Aggregation")

    txt_filters = True  # Text filtering is always enabled (False path unimplemented)
    get_citation = main_config.get("aggregate_get_citations", True) and not args.skip_citations
    output_dir = main_config.get("output_dir", DEFAULT_OUTPUT_DIR)
    collect_name = normalize_path_component(main_config.get("collect_name"))
    dir_collect = os.path.join(output_dir, collect_name)
    # Get output filename from config, with fallback and normalize path
    output_filename = normalize_path_component(
        main_config.get("aggregate_file", DEFAULT_AGGREGATED_FILENAME)
    )

    # Path to config snapshot
    config_used_path = os.path.join(dir_collect, "config_used.yml")

    logger.info(f"Collection directory: {dir_collect}")
    logger.info(f"Text filtering: {'enabled' if txt_filters else 'disabled'}")
    logger.info(
        f"Citation fetching: {'enabled' if get_citation else 'disabled (use --skip-citations to disable)'}"
    )

    # ── Collection completeness report (always printed before aggregation) ──
    from scilex.collect_status import build_status, print_status
    _status = build_status(dir_collect, main_config)
    print_status(_status)

    all_data = []

    # Initialize filtering tracker
    filtering_tracker = FilteringTracker()

    # Load configuration
    quality_filters = main_config.get("quality_filters", {})

    # Load optional advanced config if it exists (from src/ directory)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    advanced_config_path = os.path.join(src_dir, "scilex.advanced.yml")
    if os.path.isfile(advanced_config_path):
        import yaml

        with open(advanced_config_path) as f:
            advanced_config = yaml.safe_load(f) or {}
            # Merge advanced quality filters with main quality filters
            if "quality_filters" in advanced_config:
                quality_filters.update(advanced_config["quality_filters"])
                logger.info(f"Loaded advanced filters from {advanced_config_path}")
            # Merge any other advanced settings
            for key, value in advanced_config.items():
                if key != "quality_filters" and key not in main_config:
                    main_config[key] = value

    # Auto-populate year_range from main config if empty
    if quality_filters.get("validate_year_range", False):
        year_range = quality_filters.get("year_range", [])
        if not year_range:
            # Use years from main config
            year_range = main_config.get("years", [])
            quality_filters["year_range"] = year_range
            logging.info(f"Auto-populated year_range from main config: {year_range}")

    # Load keyword groups from config for proper dual-group filtering
    keyword_groups = main_config.get("keywords", [])

    # Load optional bonus keywords (used for relevance scoring only)
    bonus_keywords = main_config.get("bonus_keywords", None)

    # Load collection metadata from config snapshot
    if not os.path.isfile(config_used_path):
        logging.error(f"No collection metadata found in: {dir_collect}")
        logging.error(f"  - config_used.yml not found at: {config_used_path}")
        logging.error("")
        logging.error("Please run collection first:")
        logging.error("  python src/run_collection.py")
        logging.error("")
        logging.error("Or check 'collect_name' in scilex.config.yml")
        sys.exit(1)

    logging.info("Loading config_used.yml for aggregation")
    import yaml

    try:
        with open(config_used_path, encoding="utf-8") as f:
            config_used = yaml.safe_load(f)
        logging.debug("Config snapshot loaded successfully")
    except yaml.YAMLError as e:
        logging.error(f"Failed to parse config_used.yml: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error loading config_used.yml: {e}")
        sys.exit(1)

    # =========================================================================
    # PRE-STEP: ABSTRACT ENRICHMENT
    # =========================================================================

    if not args.no_abstract_enrichment:
        from scilex.abstract_enrichment import enrich_collection_abstracts

        ss_key = api_config.get("SemanticScholar", {}).get("api_key") if api_config else None
        enrich_stats = enrich_collection_abstracts(
            dir_collect,
            ss_api_key=ss_key,
            num_workers=args.enrich_workers,
            cache_only=args.cache_only_enrichment,
        )
        if enrich_stats["dois_found"] > 0:
            logging.info(
                f"Abstract enrichment complete: "
                f"{enrich_stats['enriched']}/{enrich_stats['dois_found']} abstracts available "
                f"({enrich_stats.get('cache_hits', 0)} from cache, "
                f"{enrich_stats.get('newly_fetched', 0)} newly fetched), "
                f"{enrich_stats['patched_records']} records updated in source files"
            )
    else:
        logging.info("Abstract enrichment skipped (--no-abstract-enrichment)")

    # =========================================================================
    # RUN PARALLEL AGGREGATION
    # =========================================================================

    logging.info("Using parallel aggregation mode")
    from scilex.crawlers.aggregate_parallel import parallel_aggregate

    # In cache-only mode, load the SQLite abstract cache once here and pass it
    # to the aggregation pipeline so workers can inject abstracts on the fly —
    # no source-file scan required.
    cached_abstracts: dict | None = None
    if getattr(args, "cache_only_enrichment", False):
        from scilex.abstract_enrichment import load_all_cached_abstracts
        logging.info("Loading abstract cache for inline injection during aggregation…")
        cached_abstracts = load_all_cached_abstracts(dir_collect)
        logging.info(f"  {len(cached_abstracts):,} cached abstracts loaded")

    # Build early-filter dict: cheap checks pushed into batch workers so papers
    # that fail year or itemType criteria never reach text-filtering or dedup.
    pre_filters: dict = {}

    enable_itemtype_filter = quality_filters.get("enable_itemtype_filter", False)
    allowed_item_types = quality_filters.get("allowed_item_types", [])
    if enable_itemtype_filter and allowed_item_types:
        pre_filters["allowed_item_types"] = set(allowed_item_types)

    # Year range: always derive from the main config's "years" list (the same list
    # used during collection). quality_filters.year_range can override it explicitly.
    _year_list = quality_filters.get("year_range") or main_config.get("years", [])
    if _year_list:
        pre_filters["year_range"] = set(int(y) for y in _year_list)

    if pre_filters:
        logging.info(
            f"Pre-filters configured for batch workers: "
            + (f"itemTypes={sorted(pre_filters.get('allowed_item_types', set()))} " if "allowed_item_types" in pre_filters else "")
            + (f"years={sorted(pre_filters.get('year_range', set()))}" if "year_range" in pre_filters else "")
        )

    # Run parallel aggregation with config_used
    df, parallel_stats = parallel_aggregate(
        dir_collect=dir_collect,
        config_used=config_used,
        txt_filters=txt_filters,
        num_workers=args.parallel_workers,
        batch_size=args.batch_size,
        keyword_groups=keyword_groups,
        load_workers=args.load_workers,
        bonus_keywords=bonus_keywords if bonus_keywords else None,
        cached_abstracts=cached_abstracts,
        pre_filters=pre_filters if pre_filters else None,
    )

    # Output performance statistics if requested
    if args.profile:
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

    # Note: parallel_aggregate already includes simple deduplication
    df_clean = df

    # Initialize filtering tracker with post-deduplication count
    filtering_tracker.set_initial(len(df_clean), "Papers after deduplication")

    # =========================================================================
    # STEP 0: Fill Missing URLs from DOIs
    # =========================================================================
    # Generate URLs from DOIs for papers that have DOI but no URL
    # This uses the DOI resolver (https://doi.org/) which redirects to the paper
    logging.info("\n=== URL Fallback from DOI ===")
    df_clean, url_stats = _fill_missing_urls_from_doi(df_clean)

    # =========================================================================
    # STEP 1: ItemType Filtering (Whitelist Mode)
    # =========================================================================
    # Apply itemType filtering FIRST, before any other filters
    # This runs independently of bypass mechanism and filters papers early
    enable_itemtype_filter = quality_filters.get("enable_itemtype_filter", False)
    allowed_item_types = quality_filters.get("allowed_item_types", [])

    if enable_itemtype_filter:
        logging.info("\n=== ItemType Filtering (Whitelist Mode) ===")
        df_clean, itemtype_stats = _apply_itemtype_filter(
            df_clean, allowed_item_types, enable_itemtype_filter
        )

        # Track itemType filtering stage
        filtering_tracker.add_stage(
            "ItemType Filter",
            len(df_clean),
            f"Whitelist filtering: Only {len(allowed_item_types)} allowed itemTypes kept",
        )

        # Exit early if all papers were filtered out
        if len(df_clean) == 0:
            logging.warning(
                "All papers filtered out by itemType filter. No papers to process."
            )
            logging.warning(
                "Check your allowed_item_types configuration in scilex.config.yml"
            )
            sys.exit(1)
    else:
        logging.info("ItemType filtering: DISABLED (all itemTypes allowed)")

    # Track duplicate sources BEFORE further filtering (so analysis is meaningful)
    if quality_filters.get("track_duplicate_sources", True):
        logging.info("Analyzing duplicate sources and API overlap...")
        analyzer, metadata_quality = analyze_and_report_duplicates(
            df_clean,
            generate_report=quality_filters.get("generate_quality_report", True),
        )

    # Generate itemType distribution report
    if quality_filters.get("generate_quality_report", True):
        logging.info("Generating itemType distribution report...")
        itemtype_report = generate_itemtype_distribution_report(df_clean)
        print(itemtype_report)

    # Calculate and save quality scores for all papers
    logging.info("Calculating quality scores...")
    from scilex.crawlers.aggregate import getquality

    df_clean["quality_score"] = df_clean.apply(
        lambda row: getquality(row, df_clean.columns.tolist()), axis=1
    )
    logging.info("Quality scores calculated and added to dataset")

    # Apply ItemType bypass filter if configured
    bypass_item_types = (
        quality_filters.get("bypass_item_types", []) if quality_filters else []
    )
    enable_bypass = (
        quality_filters.get("enable_itemtype_bypass", False)
        if quality_filters
        else False
    )

    if enable_bypass and bypass_item_types:
        logging.info("\n=== ItemType Bypass Filter ===")
        df_bypass, df_non_bypass = _apply_itemtype_bypass(df_clean, bypass_item_types)

        # Track bypass split as a single stage
        # Note: df_bypass papers auto-pass to output, df_non_bypass papers continue through filters
        filtering_tracker.add_stage(
            "ItemType Bypass Split",
            len(df_non_bypass),  # Papers continuing through quality validation pipeline
            f"Split: {len(df_bypass):,} high-quality papers auto-pass ({', '.join(bypass_item_types)}), "
            f"{len(df_non_bypass):,} papers continue through quality validation",
        )
    else:
        # No bypass configured - all papers go through filters
        df_bypass = pd.DataFrame()
        df_non_bypass = df_clean

    # Apply quality filters to non-bypass papers only
    if quality_filters and len(df_non_bypass) > 0:
        logging.info("Applying quality filters to non-bypass papers...")
        generate_report = quality_filters.get("generate_quality_report", True)
        df_filtered, quality_report = apply_quality_filters(
            df_non_bypass, quality_filters, generate_report
        )
        logging.info(
            f"After quality filtering: {len(df_filtered)} papers remaining (from {len(df_non_bypass)} non-bypass papers)"
        )

        # Merge bypass papers back with filtered papers
        if len(df_bypass) > 0:
            df_clean = pd.concat([df_bypass, df_filtered], ignore_index=True)
            logging.info(
                f"Merged: {len(df_bypass)} bypass + {len(df_filtered)} filtered = {len(df_clean)} total papers"
            )
        else:
            df_clean = df_filtered

        # Track quality filtering stage
        filtering_tracker.add_stage(
            "Quality Filter",
            len(df_clean),
            "Papers meeting quality requirements (DOI, abstract, year, author count, etc.)",
        )
    elif len(df_bypass) > 0:
        # Only bypass papers, no filtering needed
        df_clean = df_bypass

    # Generate data completeness report
    if quality_filters.get("generate_quality_report", True):
        completeness_report = generate_data_completeness_report(df_clean)
        logging.info(completeness_report)

    # Generate keyword validation report
    keywords = main_config.get("keywords", [])
    if keywords and quality_filters.get("generate_quality_report", True):
        keyword_report = generate_keyword_validation_report(
            df_clean,
            keywords,
            bonus_keywords=bonus_keywords if bonus_keywords else None,
        )
        logging.info(keyword_report)

    # Abstract quality validation and filtering (Phase 2)
    if quality_filters.get("validate_abstracts", False):
        logging.info("Validating abstract quality...")
        min_quality_score = quality_filters.get(
            "min_abstract_quality_score", MIN_ABSTRACT_QUALITY_SCORE
        )
        df_clean, abstract_stats = validate_dataframe_abstracts(
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

        # Track abstract quality filtering stage
        filtering_tracker.add_stage(
            "Abstract Quality Filter",
            len(df_clean),
            f"Abstracts meeting quality threshold (min score: {min_quality_score})",
        )

    citation_stats_report = None

    if get_citation and len(df_clean) > 0:
        # Set up checkpoint path
        checkpoint_path = os.path.join(dir_collect, "citation_checkpoint.json")

        # Fetch citations in parallel with checkpointing and caching
        extras, nb_citeds, nb_citations, stats = _fetch_citations_parallel(
            df_clean,
            num_workers=args.workers,
            checkpoint_interval=args.checkpoint_interval,
            checkpoint_path=checkpoint_path,
            resume_from=args.resume,
            use_cache=not args.no_cache,  # Cache enabled by default
            api_config=api_config,
        )

        citation_stats_report = stats

        # Assign results to DataFrame (efficient bulk assignment)
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

        # Use Semantic Scholar citations as fallback if enabled
        if quality_filters.get("use_semantic_scholar_citations", True):
            logging.info(
                "Using Semantic Scholar citations as fallback for missing/zero OpenCitations data..."
            )
            df_clean = _use_semantic_scholar_citations_fallback(df_clean)

        if quality_filters.get("use_openalex_citations", True):
            logging.info(
                "Using OpenAlex citations as fallback for missing/zero citation data..."
            )
            df_clean = _use_openalex_citations_fallback(df_clean)

        # Apply time-aware citation filtering if enabled in config
        if quality_filters.get("apply_citation_filter", True):
            df_clean = _apply_time_aware_citation_filter(df_clean)

            # Track citation filtering stage
            filtering_tracker.add_stage(
                "Citation Filter",
                len(df_clean),
                "Papers meeting time-aware citation thresholds",
            )

        # Clean up checkpoint file on success
        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
                logging.info("Checkpoint file removed after successful completion")
            except OSError:
                pass
    elif get_citation and len(df_clean) == 0:
        logging.warning("Skipping citation fetching - no papers to process")

    # Apply relevance ranking (final step before saving)
    if quality_filters.get("apply_relevance_ranking", True):
        top_n = quality_filters.get("max_papers", None)  # Optional: limit to top N
        df_clean = _apply_relevance_ranking(
            df_clean,
            keyword_groups=keyword_groups,
            top_n=top_n,
            has_citations=get_citation and len(df_clean) > 0,
            config=main_config,  # Pass the main config for access to quality_filters
            bonus_keywords=bonus_keywords,
        )

        # Track relevance ranking stage
        filtering_tracker.add_stage(
            "Relevance Ranking",
            len(df_clean),
            f"{'Top ' + str(top_n) + ' ' if top_n else ''}Papers ranked by normalized relevance score (0-10 scale)",
        )

    # Display comprehensive filtering summary
    filtering_summary = filtering_tracker.generate_report()
    logging.info(filtering_summary)

    # Tag papers with bonus keywords and report distribution
    if bonus_keywords:
        logging.info("Tagging papers with bonus keywords...")
        df_clean = _tag_papers_with_bonus_keywords(df_clean, bonus_keywords)
        _generate_bonus_keyword_stats(df_clean, bonus_keywords)
    else:
        df_clean["bonus_keyword_tags"] = ""

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

    # Write aggregation report
    run_duration = (datetime.now() - run_start).total_seconds()
    _write_aggregation_report(
        dir_collect=dir_collect,
        collect_name=collect_name,
        run_date=run_start,
        duration_seconds=run_duration,
        main_config=main_config,
        parallel_stats=parallel_stats,
        filtering_tracker=filtering_tracker,
        citation_stats=citation_stats_report,
        url_stats=url_stats,
        df_clean=df_clean,
    )


if __name__ == "__main__":
    main()
