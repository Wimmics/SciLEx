"""Extract keyword suggestions from clustered papers.

Identifies terms that are frequent in the corpus but absent from the
user's current search configuration, grouped by cluster.
"""

import logging
import re
from collections import Counter

import pandas as pd

from scilex.constants import is_valid
from scilex.pipeline_utils import parse_keyword_values

logger = logging.getLogger(__name__)

_TITLE_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "with",
        "from",
        "by",
        "as",
        "it",
        "its",
        "this",
        "that",
        "which",
        "how",
        "what",
        "when",
        "where",
        "who",
        "using",
        "based",
        "via",
        "through",
        "between",
        "into",
    }
)


def extract_suggestions(
    df: pd.DataFrame,
    existing_keywords: list[str],
    top_k: int = 30,
    min_freq: int = 2,
) -> list[dict]:
    """Extract keyword suggestions not in the current search config.

    Args:
        df: Clusters DataFrame with ``cluster_id``, and optionally
            ``tags``/``keywords``, ``title``.
        existing_keywords: Keywords already in ``scilex.config.yml``.
        top_k: Maximum number of suggestions to return.
        min_freq: Minimum frequency across corpus.

    Returns:
        List of suggestion dicts: ``{"term", "frequency", "cluster_ids"}``,
        sorted by frequency descending.
    """
    existing_lower = {k.strip().lower() for k in existing_keywords}

    # Count terms from keywords/tags columns
    term_freq: Counter[str] = Counter()
    term_clusters: dict[str, set[int]] = {}

    for _, row in df.iterrows():
        cluster_id = int(row.get("cluster_id", -1))

        # Extract from tags/keywords
        for col in ("tags", "keywords", "keyword"):
            if col not in df.columns:
                continue
            val = row.get(col)
            if not is_valid(val):
                continue
            for kw in parse_keyword_values(str(val)):
                _register_term(kw, cluster_id, term_freq, term_clusters)

        # Extract bigrams from titles
        title = row.get("title")
        if is_valid(title):
            for bigram in _title_bigrams(str(title)):
                _register_term(bigram, cluster_id, term_freq, term_clusters)

    # Filter: remove existing keywords and low-frequency terms
    suggestions = []
    for term, freq in term_freq.most_common():
        if term.lower() in existing_lower:
            continue
        if freq < min_freq:
            continue
        if len(term) < 3:
            continue
        suggestions.append(
            {
                "term": term,
                "frequency": freq,
                "cluster_ids": sorted(term_clusters.get(term, set())),
            }
        )
        if len(suggestions) >= top_k:
            break

    logger.info(
        f"Keyword suggestions: {len(term_freq)} unique terms, "
        f"{len(suggestions)} suggestions after filtering"
    )
    return suggestions


def _register_term(
    term: str,
    cluster_id: int,
    term_freq: Counter,
    term_clusters: dict[str, set[int]],
) -> None:
    """Register a term in the frequency counter and cluster mapping."""
    if not term or len(term) < 3:
        return
    term_freq[term] += 1
    if term not in term_clusters:
        term_clusters[term] = set()
    term_clusters[term].add(cluster_id)


def _title_bigrams(title: str) -> list[str]:
    """Extract lowercase bigrams from a title string.

    Filters out common stopwords to produce meaningful bigrams.
    """
    words = re.findall(r"[a-zA-Z]+", title.lower())
    words = [w for w in words if w not in _TITLE_STOPWORDS and len(w) > 2]

    bigrams = []
    for i in range(len(words) - 1):
        bigrams.append(f"{words[i]} {words[i + 1]}")
    return bigrams
