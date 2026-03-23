"""Time-aware citation filtering for the aggregation pipeline."""

import logging
from datetime import datetime

import pandas as pd
from dateutil import parser as date_parser

from scilex.constants import CitationFilterConfig, is_valid


def calculate_paper_age_months(date_str):
    """Calculate paper age in months from publication date.

    Args:
        date_str: Publication date string (various formats)

    Returns:
        int: Age in months, or None if date invalid/missing
    """
    if not is_valid(date_str):
        return None

    try:
        pub_date = date_parser.parse(str(date_str))
        now = datetime.now()
        months_diff = (now.year - pub_date.year) * 12 + (now.month - pub_date.month)
        return max(0, months_diff)
    except (ValueError, TypeError, date_parser.ParserError):
        return None


def calculate_required_citations(months_since_pub):
    """Calculate required citation threshold based on paper age.

    Uses graduated thresholds with grace period for recent papers.

    Args:
        months_since_pub: Paper age in months

    Returns:
        int: Required citation count
    """
    if months_since_pub is None or pd.isna(months_since_pub):
        return CitationFilterConfig.GRACE_PERIOD_CITATIONS

    if months_since_pub <= CitationFilterConfig.GRACE_PERIOD_MONTHS:
        return CitationFilterConfig.GRACE_PERIOD_CITATIONS
    elif months_since_pub <= CitationFilterConfig.EARLY_THRESHOLD_MONTHS:
        return CitationFilterConfig.EARLY_CITATIONS
    elif months_since_pub <= CitationFilterConfig.MEDIUM_THRESHOLD_MONTHS:
        return CitationFilterConfig.MEDIUM_CITATIONS
    elif months_since_pub <= CitationFilterConfig.MATURE_THRESHOLD_MONTHS:
        return CitationFilterConfig.MATURE_BASE_CITATIONS + int(
            (months_since_pub - CitationFilterConfig.MEDIUM_THRESHOLD_MONTHS) / 4
        )
    else:
        return CitationFilterConfig.ESTABLISHED_BASE_CITATIONS + int(
            (months_since_pub - CitationFilterConfig.MATURE_THRESHOLD_MONTHS) / 12
        )


def apply_time_aware_citation_filter(df, citation_col="nb_citation", date_col="date"):
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

    # Separate papers without DOI (they bypass citation filtering)
    has_valid_doi = df["DOI"].apply(is_valid)
    df_no_doi = df[~has_valid_doi].copy()
    df_with_doi = df[has_valid_doi].copy()

    no_doi_count = len(df_no_doi)
    if no_doi_count > 0:
        logging.info(
            f"  Papers without DOI: {no_doi_count:,} (bypassing citation filter)"
        )

    if len(df_with_doi) == 0:
        logging.info("  No papers with DOI - skipping citation filtering")
        df["paper_age_months"] = df[date_col].apply(calculate_paper_age_months)
        df["citation_threshold"] = 0
        return df

    # Calculate age and required citations
    df_with_doi["paper_age_months"] = df_with_doi[date_col].apply(
        calculate_paper_age_months
    )
    df_with_doi["citation_threshold"] = df_with_doi["paper_age_months"].apply(
        calculate_required_citations
    )

    # Convert citation count to numeric
    df_with_doi[citation_col] = (
        pd.to_numeric(df_with_doi[citation_col], errors="coerce").fillna(0).astype(int)
    )

    # Apply filtering to papers with DOI
    initial_with_doi = len(df_with_doi)
    df_filtered = df_with_doi[
        df_with_doi[citation_col] >= df_with_doi["citation_threshold"]
    ].copy()
    removed_count = initial_with_doi - len(df_filtered)

    # Merge filtered papers with DOI-less papers
    if no_doi_count > 0:
        df_no_doi["paper_age_months"] = df_no_doi[date_col].apply(
            calculate_paper_age_months
        )
        df_no_doi["citation_threshold"] = 0
        df_no_doi[citation_col] = 0
        df_filtered = pd.concat([df_filtered, df_no_doi], ignore_index=True)

    initial_count = len(df)

    # Calculate zero-citation statistics
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

    df_filtered = df_filtered.drop(columns=["paper_age_months"])
    return df_filtered
