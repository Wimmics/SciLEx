"""
Keyword validation module for SciLEx.

This module validates that collected papers actually contain the search keywords,
helping identify API false positives and assess collection quality.
"""

import logging

import pandas as pd

from scilex.constants import is_missing

_STOP_WORDS = {"of", "the", "a", "an", "and", "or", "in", "on", "at", "to", "for"}


def normalize_text(text: str) -> str:
    """Normalize text for keyword matching (lowercase, handle dict format)."""
    if is_missing(text):
        return ""

    # Handle dict format (some APIs return {"p": ["paragraph1", "paragraph2"]})
    if isinstance(text, dict) and "p" in text:
        text = " ".join(text["p"])

    return str(text).lower()


def check_keyword_in_text(keyword: str, text: str) -> bool:
    """Exact case-insensitive substring match.

    Used for mandatory query-term filtering (Group 1 / Group 2 keywords).
    The keyword must appear verbatim (lowercased) somewhere in the text.
    """
    if is_missing(text) or not keyword:
        return False
    return keyword.lower() in normalize_text(text)


def check_keyword_in_text_flexible(keyword: str, text: str) -> bool:
    """Flexible match: exact phrase first, word-level fallback for compound keywords.

    Used for bonus keywords where the words may appear separately in the text.
    For single-word keywords behaves identically to check_keyword_in_text.
    For multi-word keywords: exact phrase OR every meaningful constituent word
    (length > 2, not a stop word) present anywhere in the text.
    """
    if is_missing(text) or not keyword:
        return False

    text_lower = normalize_text(text)
    kw_lower = keyword.lower()

    if kw_lower in text_lower:
        return True

    words = kw_lower.split()
    if len(words) < 2:
        return False
    meaningful = [w for w in words if len(w) > 2 and w not in _STOP_WORDS]
    return bool(meaningful) and all(w in text_lower for w in meaningful)


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
    bonus_keywords: list[str] | None = None,
) -> str:
    """
    Generate a report on keyword presence in collected papers.

    Each keyword's frequency is counted independently — a keyword is counted
    whenever it appears in a paper's title/abstract, regardless of whether the
    other group also matches.  Group-level summaries (papers matching Group 1
    only, Group 2 only, or both) are shown separately.

    Args:
        df: DataFrame with paper records
        keywords: Keyword groups from config
        bonus_keywords: Optional bonus keyword list (flexible matching)

    Returns:
        String containing the validation report
    """
    if len(df) == 0:
        return "No papers to validate."

    total_papers = len(df)
    dual_group_mode = len(keywords) == 2 and bool(keywords[0]) and bool(keywords[1])

    # -----------------------------------------------------------------------
    # Count each keyword independently (not gated on other group)
    # -----------------------------------------------------------------------
    keyword_counts: dict[str, int] = {}
    for group in keywords:
        for kw in group:
            keyword_counts[kw] = 0

    bonus_counts: dict[str, int] = {}
    if bonus_keywords:
        for kw in bonus_keywords:
            bonus_counts[kw] = 0

    group1_only = 0
    group2_only = 0
    both_groups = 0
    neither = 0

    for _, row in df.iterrows():
        record = row.to_dict()
        title = record.get("title", "")
        abstract = record.get("abstract", "")
        combined = f"{title} {abstract}"

        if dual_group_mode:
            g1_hit = False
            g2_hit = False
            for kw in keywords[0]:
                if check_keyword_in_text(kw, combined):
                    keyword_counts[kw] += 1
                    g1_hit = True
            for kw in keywords[1]:
                if check_keyword_in_text(kw, combined):
                    keyword_counts[kw] += 1
                    g2_hit = True
            if g1_hit and g2_hit:
                both_groups += 1
            elif g1_hit:
                group1_only += 1
            elif g2_hit:
                group2_only += 1
            else:
                neither += 1
        else:
            group = keywords[0] if keywords else []
            hit = False
            for kw in group:
                if check_keyword_in_text(kw, combined):
                    keyword_counts[kw] += 1
                    hit = True
            if hit:
                both_groups += 1  # reuse counter as "papers with any keyword"
            else:
                neither += 1

        if bonus_keywords:
            for kw in bonus_keywords:
                if check_keyword_in_text_flexible(kw, combined):
                    bonus_counts[kw] += 1

    # -----------------------------------------------------------------------
    # Build report
    # -----------------------------------------------------------------------
    report_lines = [
        "\n" + "=" * 70,
        "KEYWORD VALIDATION REPORT",
        "=" * 70,
        f"Total papers: {total_papers}",
        "",
        "Matching mode: EXACT per-keyword (case-insensitive substring)",
        "Note: each keyword counted independently; group summaries shown below.",
        "",
    ]

    if dual_group_mode:
        report_lines += [
            "Keyword groups (filter requires Group 1 AND (Group 2 OR bonus)):",
            f"  Group 1: {', '.join(keywords[0])}",
            f"  Group 2: {', '.join(keywords[1])}",
            "",
            "Group-level paper breakdown:",
            f"  Both Group 1 AND Group 2 matched : {both_groups:>6}  ({both_groups / total_papers * 100:.1f}%)",
            f"  Group 1 only (Group 2 via bonus) : {group1_only:>6}  ({group1_only / total_papers * 100:.1f}%)",
            f"  Group 2 only (no Group 1 match)  : {group2_only:>6}  ({group2_only / total_papers * 100:.1f}%)",
            f"  Neither group matched            : {neither:>6}  ({neither / total_papers * 100:.1f}%)",
            "",
        ]
    else:
        report_lines += [
            f"Keywords: {', '.join(keywords[0] if keywords else [])}",
            "",
            f"  Papers with any keyword : {both_groups:>6}  ({both_groups / total_papers * 100:.1f}%)",
            f"  Papers with no keyword  : {neither:>6}  ({neither / total_papers * 100:.1f}%)",
            "",
        ]

    report_lines.append("Individual keyword frequencies (independent counts):")
    report_lines.append("  Group 1:")
    g1_kws = keywords[0] if keywords else []
    for kw, count in sorted(
        [(k, keyword_counts[k]) for k in g1_kws], key=lambda x: x[1], reverse=True
    ):
        report_lines.append(f"    '{kw}': {count} ({count / total_papers * 100:.1f}%)")

    if dual_group_mode:
        report_lines.append("  Group 2:")
        for kw, count in sorted(
            [(k, keyword_counts[k]) for k in keywords[1]],
            key=lambda x: x[1],
            reverse=True,
        ):
            report_lines.append(
                f"    '{kw}': {count} ({count / total_papers * 100:.1f}%)"
            )

    if bonus_keywords and bonus_counts:
        report_lines.append("  Bonus keywords (flexible match):")
        for kw, count in sorted(bonus_counts.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(
                f"    '{kw}': {count} ({count / total_papers * 100:.1f}%)"
            )

    report_lines.append("")
    report_lines.append("Interpretation:")
    if neither > 0:
        rate = neither / total_papers * 100
        if rate > 30:
            report_lines.append(
                f"  Warning: {rate:.1f}% of papers matched neither keyword group."
            )
            report_lines.append(
                "      These passed via bonus-keyword fallback or are API false positives."
            )
        elif rate > 10:
            report_lines.append(
                f"  Moderate: {rate:.1f}% of papers matched neither group."
            )
        else:
            report_lines.append(f"  Good: {rate:.1f}% of papers matched neither group.")
    else:
        report_lines.append("  All papers matched at least one keyword group.")

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

    for _, row in df.iterrows():
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
