"""Text-based keyword filtering for the aggregation pipeline."""

from scilex.constants import MISSING_VALUE, is_valid


def keyword_matches_in_abstract(keyword, abstract_text):
    """Check if keyword appears in abstract text (handles both dict and string formats)."""
    if isinstance(abstract_text, dict) and "p" in abstract_text:
        abstract_content = " ".join(abstract_text["p"]).lower()
    else:
        abstract_content = str(abstract_text).lower()

    return keyword in abstract_content


def check_keywords_in_text(keywords_list, text):
    """Check if any keyword from a list matches the text.

    Args:
        keywords_list: List of keywords to check
        text: Text to search in (combined title + abstract)

    Returns:
        bool: True if at least one keyword matches
    """
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords_list)


def record_passes_text_filter(
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
            group1_match = check_keywords_in_text(group1, combined_text)
            group2_match = check_keywords_in_text(group2, combined_text)
            return group1_match and group2_match

    # ========================================================================
    # SINGLE KEYWORD GROUP MODE: Require match from ANY keyword
    # ========================================================================
    if keyword_groups:
        keywords = [kw for group in keyword_groups for kw in group if group]

    # Exact substring matching (case-insensitive)
    title_lower = title.lower()
    for keyword in keywords:
        keyword_lower = keyword.lower()

        if keyword_lower in title_lower:
            return True

        if is_valid(abstract) and keyword_matches_in_abstract(keyword, abstract):
            return True

    return False
