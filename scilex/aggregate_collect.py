import argparse
import csv
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from dateutil import parser as date_parser

import pandas as pd
from tqdm import tqdm

import scilex.citations.citations_tools as cit_tools
from scilex.abstract_validation import (
    filter_by_abstract_quality,
    validate_dataframe_abstracts,
)
from scilex.config_defaults import (
    DEFAULT_AGGREGATED_FILENAME,
    DEFAULT_ENABLE_TEXT_FILTER,
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
    GoogleScholartoZoteroFormat,
    HALtoZoteroFormat,
    IEEEtoZoteroFormat,
    IstextoZoteroFormat,
    OpenAlextoZoteroFormat,
    PubMedCentraltoZoteroFormat,
    PubMedtoZoteroFormat,
    SemanticScholartoZoteroFormat,
    SpringertoZoteroFormat,
)
from scilex.crawlers.utils import load_all_configs
from scilex.duplicate_tracking import (
    analyze_and_report_duplicates,
    generate_itemtype_distribution_report,
)
from scilex.keyword_validation import generate_keyword_validation_report
from scilex.logging_config import log_section, setup_logging
from scilex.quality_validation import (
    apply_quality_filters,
    generate_data_completeness_report,
)

# Set up logging configuration with environment variable support
setup_logging()

config_files = {"main_config": "scilex.config.yml", "api_config": "api.config.yml"}
# Load configurations
configs = load_all_configs(config_files)
# Access individual configurations
main_config = configs["main_config"]
api_config = configs["api_config"]

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
    "GoogleScholar": GoogleScholartoZoteroFormat,
    "PubMed": PubMedtoZoteroFormat,
    "PubMedCentral": PubMedCentraltoZoteroFormat,
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

    return keyword in abstract_content


def _check_keywords_in_text(keywords_list, text):
    """Check if any keyword from a list matches the text.

    Args:
        keywords_list: List of keywords to check
        text: Text to search in (combined title + abstract)

    Returns:
        bool: True if at least one keyword matches
    """
    text_lower = text.lower()

    # Exact substring matching (case-insensitive)
    return any(keyword.lower() in text_lower for keyword in keywords_list)


def _record_passes_text_filter(
    record,
    keywords,
    keyword_groups=None,
):
    """Check if record contains required keywords in title or abstract.

    For dual keyword group mode (2 groups): Requires match from BOTH Group1 AND Group2
    For single keyword group mode (1 group): Requires match from ANY keyword in group

    Args:
        record: Paper record dictionary
        keywords: List of keywords from the query (for backward compatibility)
        keyword_groups: Optional list of keyword groups from config (for dual-group mode)

    Returns:
        bool: True if keyword requirements are met
    """
    if not keywords and not keyword_groups:
        return True

    abstract = record.get("abstract", MISSING_VALUE)
    title = record.get("title", "")

    # Combine title and abstract for matching
    combined_text = f"{title} {abstract if is_valid(abstract) else ''}"

    # ========================================================================
    # DUAL KEYWORD GROUP MODE: Require match from BOTH groups
    # ========================================================================
    if keyword_groups and len(keyword_groups) == 2:
        group1, group2 = keyword_groups

        # Must have at least one keyword from each group
        if not group1 or not group2:
            # Fallback to single-group mode if one group is empty
            all_keywords = [kw for g in keyword_groups for kw in g if g]
            if not all_keywords:
                return True
            keywords = all_keywords
        else:
            # Check Group 1
            group1_match = _check_keywords_in_text(group1, combined_text)

            # Check Group 2
            group2_match = _check_keywords_in_text(group2, combined_text)

            # Both groups must match
            return group1_match and group2_match

    # ========================================================================
    # SINGLE KEYWORD GROUP MODE: Require match from ANY keyword
    # ========================================================================
    # Flatten keyword groups into single list (or use provided keywords)
    if keyword_groups:
        keywords = [kw for group in keyword_groups for kw in group if group]

    # Exact substring matching (case-insensitive)
    title_lower = title.lower()
    for keyword in keywords:
        keyword_lower = keyword.lower()

        # Check in title
        if keyword_lower in title_lower:
            return True

        # Check in abstract (if valid)
        if is_valid(abstract) and _keyword_matches_in_abstract(keyword, abstract):
            return True

    # No match found
    return False


# Global lock for thread-safe rate limiting
_rate_limit_lock = threading.Lock()


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
    zero_citation_count = (
        df_filtered[df_filtered["DOI"].apply(is_valid)][citation_col] == 0
    ).sum()
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
):
    """
    Fetch citations for a single paper (thread-safe with three-tier strategy).

    Three-tier strategy: Cache → Semantic Scholar → OpenCitations
    1. Check citation cache first (instant, no API call)
    2. If cache miss, check Semantic Scholar data (already in memory, no API call)
    3. If SS data unavailable, call OpenCitations API

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

    Returns:
        dict: Result with index and status
    """
    if not is_valid(doi):
        stats["no_doi"] += 1
        return {"index": index, "status": "no_doi"}

    try:
        # Check cache first (5x speedup on cache hits)
        from scilex.citations.cache import cache_citation, get_cached_citation

        cached_data = get_cached_citation(str(doi), cache_path)
        if cached_data is not None:
            # Cache hit - use cached data
            stats["cache_hit"] += 1
            extras[index] = cached_data["citations"]
            nb_citeds[index] = cached_data["nb_cited"]
            nb_citations[index] = cached_data["nb_citations"]

            # Track API stats from cache
            api_stats = cached_data["api_stats"]
            if (
                api_stats["cit_status"] == "success"
                and api_stats["ref_status"] == "success"
            ):
                stats["success"] += 1

            return {"index": index, "status": "cache_hit"}

        # Cache miss - check Semantic Scholar data before calling OpenCitations
        stats["cache_miss"] += 1

        # Tier 2: Check if Semantic Scholar data is available (no API call needed)
        if ss_citation_count is not None or ss_reference_count is not None:
            stats["ss_used"] += 1

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

            stats["success"] += 1
            return {"index": index, "status": "ss_used"}

        # Tier 3: No SS data available - call OpenCitations API
        stats["opencitations_used"] += 1
        citations, api_stats = cit_tools.getRefandCitFormatted(str(doi))

        # Add source marker to api_stats
        api_stats["source"] = "opencitations"

        # Track statistics
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
        stats["error"] += 1
        return {"index": index, "status": "error"}


def _fetch_citations_parallel(
    df_clean,
    num_workers=3,
    checkpoint_interval=100,
    checkpoint_path=None,
    resume_from=None,
    use_cache=True,
):
    """
    Fetch citations in parallel using ThreadPoolExecutor with caching.

    Args:
        df_clean: DataFrame with papers
        num_workers: Number of parallel workers
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

        # Show cache stats
        cache_stats = get_cache_stats(cache_path)
        logging.info(
            f"Cache stats: {cache_stats['active_entries']} active entries, "
            f"{cache_stats['expired_entries']} expired"
        )

        # Clean up expired entries
        if cache_stats["expired_entries"] > 0:
            removed = cleanup_expired_cache(cache_path)
            logging.info(f"Cleaned up {removed} expired cache entries")

    # Initialize result lists
    extras = [""] * total_papers
    nb_citeds = [""] * total_papers
    nb_citations = [""] * total_papers

    # Initialize statistics (thread-safe using dict)
    stats = {
        "success": 0,
        "timeout": 0,
        "error": 0,
        "no_doi": 0,
        "cache_hit": 0,
        "cache_miss": 0,
        "ss_used": 0,
        "opencitations_used": 0,
    }

    # Load from checkpoint if resuming
    start_index = 0
    if resume_from is not None:
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            start_index = checkpoint["last_index"] + 1
            stats = checkpoint["stats"]
            # Restore already processed data
            for i in range(start_index):
                extras[i] = checkpoint["extras"][i]
                nb_citeds[i] = checkpoint["nb_citeds"][i]
                nb_citations[i] = checkpoint["nb_citations"][i]
            logging.info(f"Resuming from paper {start_index}")

    papers_with_doi = df_clean["DOI"].apply(is_valid).sum()
    logging.info(
        f"Fetching citation data for {papers_with_doi}/{total_papers} papers with valid DOIs"
    )
    if use_cache:
        logging.info(
            "Using citation cache (30-day TTL) - expect ~60-80% cache hits on repeated runs"
        )
    logging.info(
        f"Using {num_workers} parallel workers for citation fetching"
    )
    logging.info(
        "Rate limits: OpenCitations API at 1 req/sec "
        "(cache hits and Semantic Scholar data bypass this limit)"
    )

    # Create progress bar and ThreadPoolExecutor for parallel fetching
    with (
        tqdm(
            total=total_papers,
            initial=start_index,
            desc="Fetching citations",
            unit="paper",
            position=0,
            leave=True,
        ) as pbar,
        ThreadPoolExecutor(max_workers=num_workers) as executor,
    ):
        # Submit all tasks
        future_to_index = {}
        for position, (_df_index, row) in enumerate(
            df_clean.iloc[start_index:].iterrows(), start=start_index
        ):
            doi = row.get("DOI")

            # Extract Semantic Scholar citation data if available
            ss_cit_count, ss_ref_count = _get_ss_citations_if_available(row)

            future = executor.submit(
                _fetch_citation_for_paper,
                position,
                doi,
                stats,
                checkpoint_interval,
                checkpoint_path,
                extras,
                nb_citeds,
                nb_citations,
                cache_path,
                ss_cit_count,
                ss_ref_count,
            )
            future_to_index[future] = position

        # Process completed tasks
        for future in as_completed(future_to_index):
            future.result()  # Wait for task completion (raises exceptions if any)
            pbar.update(1)

            # Update progress bar with statistics (three-tier breakdown)
            postfix = {
                "✓": stats["success"],
                "✗": stats["error"],
                "⏱": stats["timeout"],
                "⊘": stats["no_doi"],
            }
            if use_cache:
                postfix["💾"] = stats["cache_hit"]  # Cache hits
                postfix["🔬"] = stats["ss_used"]  # Semantic Scholar used
                postfix["🔗"] = stats["opencitations_used"]  # OpenCitations API calls
            pbar.set_postfix(postfix)

    # Calculate statistics and percentages
    total_with_doi = total_papers - stats["no_doi"]
    cache_hit_rate = 0
    ss_usage_rate = 0
    opencitations_rate = 0

    if use_cache and (stats["cache_hit"] + stats["cache_miss"]) > 0:
        cache_hit_rate = (
            stats["cache_hit"] / (stats["cache_hit"] + stats["cache_miss"]) * 100
        )

    if total_with_doi > 0:
        ss_usage_rate = stats["ss_used"] / total_with_doi * 100
        opencitations_rate = stats["opencitations_used"] / total_with_doi * 100

    logging.info(
        f"Citation fetching complete: {stats['success']} successful, "
        f"{stats['error']} errors, {stats['timeout']} timeouts, "
        f"{stats['no_doi']} without DOI"
    )

    if use_cache:
        logging.info(
            f"Cache performance: {stats['cache_hit']} hits, {stats['cache_miss']} misses "
            f"({cache_hit_rate:.1f}% hit rate)"
        )

    # Three-tier strategy breakdown
    logging.info("Citation source breakdown (for papers with DOI):")
    logging.info(f"  💾 Cache hits: {stats['cache_hit']} papers")
    logging.info(
        f"  🔬 Semantic Scholar: {stats['ss_used']} papers ({ss_usage_rate:.1f}%)"
    )
    logging.info(
        f"  🔗 OpenCitations API: {stats['opencitations_used']} papers ({opencitations_rate:.1f}%)"
    )

    # Calculate API call savings
    api_calls_saved = stats["cache_hit"] + stats["ss_used"]
    if total_with_doi > 0:
        savings_rate = api_calls_saved / total_with_doi * 100
        logging.info(
            f"  💰 API calls saved: {api_calls_saved}/{total_with_doi} ({savings_rate:.1f}%)"
        )

    return extras, nb_citeds, nb_citations, stats


def main():
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
        help="Number of parallel workers for citation fetching (default: 1)",
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

    # Log aggregation start
    log_section(logger, "SciLEx Data Aggregation")

    txt_filters = main_config.get("aggregate_txt_filter", DEFAULT_ENABLE_TEXT_FILTER)
    get_citation = (
        main_config.get("aggregate_get_citations", True) and not args.skip_citations
    )
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
    # RUN PARALLEL AGGREGATION
    # =========================================================================

    logging.info("Using parallel aggregation mode")
    from scilex.crawlers.aggregate_parallel import parallel_aggregate

    # Run parallel aggregation with config_used
    df, parallel_stats = parallel_aggregate(
        dir_collect=dir_collect,
        config_used=config_used,
        txt_filters=txt_filters,
        num_workers=args.parallel_workers,
        batch_size=args.batch_size,
        keyword_groups=keyword_groups,
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
        )
        logging.info(keyword_report)

    # Abstract quality validation (Phase 2)
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

        # Optionally filter by abstract quality
        if quality_filters.get("filter_by_abstract_quality", False):
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
        )

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


if __name__ == "__main__":
    main()
