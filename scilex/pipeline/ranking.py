"""Relevance ranking for the aggregation pipeline."""

import logging
import math

import pandas as pd

from scilex.config_defaults import (
    DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS,
    DEFAULT_RELEVANCE_WEIGHTS,
)


def count_keyword_matches(row, keyword_groups, bonus_keywords=None):
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

    all_keywords = []
    for group in keyword_groups:
        if isinstance(group, list):
            all_keywords.extend(group)

    title = str(row.get("title", "")).lower()
    abstract = str(row.get("abstract", "")).lower()
    combined_text = f"{title} {abstract}"

    match_count = 0
    for keyword in all_keywords:
        keyword_lower = keyword.lower()
        match_count += combined_text.count(keyword_lower)

    if bonus_keywords:
        bonus_match_count = 0
        for keyword in bonus_keywords:
            keyword_lower = keyword.lower()
            bonus_match_count += combined_text.count(keyword_lower)
        match_count += bonus_match_count * 0.5

    return match_count


def calculate_relevance_score(
    row, keyword_groups, has_citations=False, config=None, bonus_keywords=None
):
    """Calculate composite relevance score for a paper.

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
    if config is None:
        config = {}

    quality_filters = config.get("quality_filters", {})
    weights = quality_filters.get("relevance_weights", DEFAULT_RELEVANCE_WEIGHTS)

    # 1. Keyword relevance (normalize to 0-10)
    keyword_matches = count_keyword_matches(row, keyword_groups, bonus_keywords)
    keyword_score = min(keyword_matches, 10)

    # 2. Metadata quality (normalize to 0-10)
    quality = row.get("quality_score", 0)
    try:
        quality_score = min(float(quality) / 5, 10)
    except (ValueError, TypeError):
        quality_score = 0

    # 3. Publication type (0 or 10 based on config)
    item_type = str(row.get("itemType", "")).strip()
    itemtype_weights = quality_filters.get(
        "itemtype_relevance_weights", DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS
    )
    itemtype_score = 10 if itemtype_weights.get(item_type, False) else 0

    # 4. Citation impact (minimal weight to avoid recency bias)
    citation_score = 0
    if has_citations:
        citation_count = pd.to_numeric(row.get("nb_citation", 0), errors="coerce")
        if pd.notna(citation_count) and citation_count > 0:
            citation_score = min(math.log(1 + float(citation_count)) * 2.17, 10)

    final_score = (
        keyword_score * weights.get("keywords", 0.45)
        + quality_score * weights.get("quality", 0.25)
        + itemtype_score * weights.get("itemtype", 0.20)
        + citation_score * weights.get("citations", 0.10)
    )

    return round(final_score, 2)


def apply_relevance_ranking(
    df,
    keyword_groups,
    top_n=None,
    has_citations=False,
    config=None,
    bonus_keywords=None,
):
    """Apply composite relevance ranking to DataFrame.

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

    df["relevance_score"] = df.apply(
        lambda row: calculate_relevance_score(
            row, keyword_groups, has_citations, config, bonus_keywords
        ),
        axis=1,
    )

    df_ranked = df.sort_values("relevance_score", ascending=False).copy()

    logging.info("Relevance scoring complete (normalized 0-10 scale)")
    logging.info(
        f"  Score range: {df_ranked['relevance_score'].min():.2f} - {df_ranked['relevance_score'].max():.2f}"
    )
    logging.info(f"  Mean score: {df_ranked['relevance_score'].mean():.2f}")
    logging.info(f"  Median score: {df_ranked['relevance_score'].median():.2f}")

    if top_n and top_n < len(df_ranked):
        initial_count = len(df_ranked)
        df_ranked = df_ranked.head(top_n)
        logging.info(
            f"Filtered to top {top_n} most relevant papers (removed {initial_count - top_n:,})"
        )

    return df_ranked
