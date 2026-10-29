"""Post-aggregation filters for web UI and API consumers.

Consolidates filtering logic that was duplicated between
scilex_api.py and web_interface.py.
"""

import pandas as pd

from scilex.quality_validation import count_words


def apply_post_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply user-facing filters to an aggregated DataFrame.

    Supports:
        enable_itemtype_filter / allowed_item_types: Whitelist by itemType
        min_abstract_words / max_abstract_words: Abstract length range
        apply_relevance_ranking: Sort by relevance_score descending
        max_papers: Limit output to N papers

    Args:
        df: Aggregated DataFrame to filter.
        filters: Dictionary of filter settings.

    Returns:
        Filtered DataFrame.
    """
    if df.empty:
        return df

    df = df.copy()

    # ItemType whitelist filter
    if filters.get("enable_itemtype_filter") and filters.get("allowed_item_types"):
        allowed = filters["allowed_item_types"]
        # Support both column names (itemType from pipeline, item_type from some APIs)
        col = "itemType" if "itemType" in df.columns else "item_type"
        if col in df.columns:
            df = df[df[col].isin(allowed)]

    # Abstract length filters
    if "abstract" in df.columns:
        min_words = filters.get("min_abstract_words")
        max_words = filters.get("max_abstract_words")
        # Computed on the current (already itemType-filtered) frame so the mask
        # is index-aligned; "NA"/NaN abstracts count as 0 words.
        word_counts = df["abstract"].apply(count_words)

        keep = pd.Series(True, index=df.index)
        if min_words:
            keep &= word_counts >= min_words
        if max_words:
            keep &= word_counts <= max_words
        df = df[keep]

    # Sort by relevance
    if filters.get("apply_relevance_ranking") and "relevance_score" in df.columns:
        df = df.sort_values("relevance_score", ascending=False)

    # Limit paper count
    max_papers = filters.get("max_papers")
    if max_papers:
        df = df.head(max_papers)

    return df
