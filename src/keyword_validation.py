"""
Keyword validation module for SciLEx.

This module validates that collected papers actually contain the search keywords,
helping identify API false positives and assess collection quality.
"""

import logging

import pandas as pd

from src.constants import is_missing


def normalize_text(text: str) -> str:
    """Normalize text for keyword matching (lowercase, handle dict format)."""
    if is_missing(text):
        return ""

    # Handle dict format (some APIs return {"p": ["paragraph1", "paragraph2"]})
    if isinstance(text, dict) and "p" in text:
        text = " ".join(text["p"])

    return str(text).lower()


def check_keyword_in_text(keyword: str, text: str) -> bool:
    """
    Check if keyword appears in text (case-insensitive, handles phrases).

    Args:
        keyword: Keyword or phrase to search for
        text: Text to search in

    Returns:
        True if keyword found, False otherwise
    """
    if is_missing(text) or not keyword:
        return False

    normalized_text = normalize_text(text)
    normalized_keyword = keyword.lower()

    return normalized_keyword in normalized_text


def check_keywords_in_paper(
    record: dict,
    keywords: list[list[str]],
) -> tuple[bool, list[str]]:
    """
    Check if paper contains search keywords in title or abstract.

    Args:
        record: Paper record dictionary
        keywords: Keyword groups (same format as scilex config)
                  [[group1_kw1, group1_kw2], [group2_kw1, group2_kw2]]

    Returns:
        (found, matched_keywords): Whether keywords found and list of matched keywords
    """
    title = record.get("title", "")
    abstract = record.get("abstract", "")
    combined_text = f"{title} {abstract}"

    matched_keywords = []

    # Handle single keyword group
    if len(keywords) == 1 or (len(keywords) == 2 and not keywords[1]):
        keyword_group = keywords[0]
        for kw in keyword_group:
            if check_keyword_in_text(kw, combined_text):
                matched_keywords.append(kw)

        return len(matched_keywords) > 0, matched_keywords

    # Handle two keyword groups (must match from both groups)
    if len(keywords) == 2 and keywords[0] and keywords[1]:
        group1_matches = []
        group2_matches = []

        for kw in keywords[0]:
            if check_keyword_in_text(kw, combined_text):
                group1_matches.append(kw)

        for kw in keywords[1]:
            if check_keyword_in_text(kw, combined_text):
                group2_matches.append(kw)

        matched_keywords = group1_matches + group2_matches
        # Must have match from BOTH groups
        return (len(group1_matches) > 0 and len(group2_matches) > 0), matched_keywords

    return False, []


def generate_keyword_validation_report(
    df: pd.DataFrame,
    keywords: list[list[str]],
) -> str:
    """
    Generate a report on keyword presence in collected papers.

    Args:
        df: DataFrame with paper records
        keywords: Keyword groups from config

    Returns:
        String containing the validation report
    """
    if len(df) == 0:
        return "No papers to validate."

    total_papers = len(df)
    papers_with_keywords = 0
    papers_without_keywords = 0
    keyword_counts = {}

    # Initialize keyword counts
    for group in keywords:
        for kw in group:
            keyword_counts[kw] = 0

    # Check each paper
    for idx, row in df.iterrows():
        found, matched = check_keywords_in_paper(row.to_dict(), keywords)

        if found:
            papers_with_keywords += 1
            for kw in matched:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        else:
            papers_without_keywords += 1

    # Build report
    report_lines = [
        "\n" + "=" * 70,
        "KEYWORD VALIDATION REPORT",
        "=" * 70,
        f"Total papers: {total_papers}",
        f"Papers with keywords: {papers_with_keywords} ({papers_with_keywords / total_papers * 100:.1f}%)",
        f"Papers WITHOUT keywords: {papers_without_keywords} ({papers_without_keywords / total_papers * 100:.1f}%)",
        "",
    ]

    # Show matching mode
    report_lines.append("Matching mode: EXACT (case-insensitive substring)")
    report_lines.append("")

    # Show keyword group structure
    if len(keywords) == 2 and keywords[0] and keywords[1]:
        report_lines.append("Keyword groups (papers must match from BOTH groups):")
        report_lines.append(f"  Group 1: {', '.join(keywords[0])}")
        report_lines.append(f"  Group 2: {', '.join(keywords[1])}")
    else:
        report_lines.append(
            f"Keywords (papers must match ANY): {', '.join(keywords[0] if keywords else [])}"
        )

    report_lines.append("")
    report_lines.append("Individual keyword frequencies:")

    # Sort keywords by frequency
    for kw, count in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = count / total_papers * 100
        report_lines.append(f"  '{kw}': {count} ({percentage:.1f}%)")

    report_lines.append("")
    report_lines.append("Interpretation:")
    false_positive_rate = papers_without_keywords / total_papers * 100

    if false_positive_rate > 30:
        report_lines.append(
            f"  ⚠️  WARNING: {false_positive_rate:.1f}% of papers don't contain keywords!"
        )
        report_lines.append("      This suggests high false positive rate from APIs.")
        report_lines.append("      Consider more specific keywords or different APIs.")
    elif false_positive_rate > 10:
        report_lines.append(
            f"  ⚠️  MODERATE: {false_positive_rate:.1f}% of papers don't contain keywords."
        )
        report_lines.append("      Some API false positives detected.")
    else:
        report_lines.append(
            f"  ✓ GOOD: {false_positive_rate:.1f}% false positive rate is acceptable."
        )

    report_lines.append("=" * 70 + "\n")
    return "\n".join(report_lines)


def filter_by_keywords(
    df: pd.DataFrame, keywords: list[list[str]], strict: bool = False
) -> pd.DataFrame:
    """
    Filter DataFrame to keep only papers containing keywords.

    Args:
        df: DataFrame with paper records
        keywords: Keyword groups from config
        strict: If True, requires exact keyword match. If False (default),
                keeps all papers (for validation reporting only)

    Returns:
        Filtered DataFrame
    """
    if not strict or len(df) == 0:
        return df

    keep_mask = []

    for idx, row in df.iterrows():
        found, _ = check_keywords_in_paper(row.to_dict(), keywords)
        keep_mask.append(found)

    df_filtered = df[keep_mask].copy()

    removed = len(df) - len(df_filtered)
    if removed > 0:
        logging.info(
            f"Filtered out {removed} papers ({removed / len(df) * 100:.1f}%) "
            f"that don't contain search keywords"
        )

    return df_filtered
