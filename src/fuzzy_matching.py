"""
Fuzzy matching module for SciLEx using thefuzz and spacy.

This module provides fuzzy title matching to catch duplicate papers with:
- Typos and spelling variations
- Different punctuation or formatting
- Encoding issues (é vs e, etc.)
- Minor wording differences

Uses thefuzz (maintained fuzzywuzzy fork) for fast fuzzy matching
and spacy for intelligent text normalization.
"""

import logging

import pandas as pd
import spacy
from thefuzz import fuzz

from src.constants import is_missing

# Load spacy model once (lazy loading)
_nlp = None
_nlp_checked = False  # Track if we've already checked/warned


def get_nlp(suppress_warning: bool = False):
    """
    Lazy load spacy model to avoid startup penalty.

    Args:
        suppress_warning: If True, don't log warning on first failure (used during pre-installation check)

    Returns:
        Spacy nlp object or None if not available
    """
    global _nlp, _nlp_checked

    if _nlp is None and not _nlp_checked:
        try:
            _nlp = spacy.load("en_core_web_sm")
            _nlp_checked = True
        except OSError:
            _nlp_checked = True
            # Only log warning if not suppressed (e.g., during pre-installation check)
            if not suppress_warning:
                logging.warning(
                    "Spacy model 'en_core_web_sm' not found. "
                    "Install with: python -m spacy download en_core_web_sm. "
                    "Falling back to simple normalization."
                )
            _nlp = None
    return _nlp


def reload_spacy_model():
    """
    Force reload of spacy model (call after installation).

    Returns:
        True if model loaded successfully, False otherwise
    """
    global _nlp, _nlp_checked

    _nlp = None
    _nlp_checked = False

    try:
        _nlp = spacy.load("en_core_web_sm")
        _nlp_checked = True
        return True
    except OSError:
        _nlp_checked = True
        _nlp = None
        return False


def normalize_title_simple(title: str) -> str:
    """
    Simple title normalization (fallback when spacy not available).

    Args:
        title: Original title string

    Returns:
        Normalized title string
    """
    if is_missing(title):
        return ""

    # Convert to lowercase
    normalized = str(title).lower()

    # Remove punctuation except spaces and hyphens
    import re

    normalized = re.sub(r"[^\w\s-]", " ", normalized)

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)

    # Remove common stop words
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
    words = normalized.split()
    words = [w for w in words if w not in stop_words]

    return " ".join(words).strip()


def normalize_title(title: str) -> str:
    """
    Normalize title using spacy for better accuracy.

    Normalization steps:
    - Tokenization
    - Lemmatization (handle plural/tense variations)
    - Stop word removal
    - Punctuation removal

    Args:
        title: Original title string

    Returns:
        Normalized title string
    """
    if is_missing(title):
        return ""

    nlp = get_nlp()

    # Fallback to simple normalization if spacy not available
    if nlp is None:
        return normalize_title_simple(title)

    # Process with spacy
    doc = nlp(title.lower())

    # Extract lemmatized tokens, excluding stop words and punctuation
    tokens = [
        token.lemma_
        for token in doc
        if not token.is_stop and not token.is_punct and not token.is_space
    ]

    return " ".join(tokens).strip()


def calculate_title_similarity(
    title1: str, title2: str, use_token_sort: bool = True
) -> float:
    """
    Calculate similarity score between two titles using thefuzz.

    Args:
        title1: First title
        title2: Second title
        use_token_sort: If True, use token_sort_ratio (handles word order differences)
                       If False, use simple ratio (faster but strict word order)

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (identical)
    """
    if is_missing(title1) or is_missing(title2):
        return 0.0

    # Normalize both titles
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    # Handle edge cases
    if not norm1 or not norm2:
        return 0.0

    if norm1 == norm2:
        return 1.0

    # Use thefuzz for similarity calculation
    # token_sort_ratio is more forgiving of word order differences
    # ("Deep Learning Networks" vs "Networks for Deep Learning" -> high similarity)
    if use_token_sort:
        similarity = fuzz.token_sort_ratio(norm1, norm2)
    else:
        similarity = fuzz.ratio(norm1, norm2)

    # Convert from 0-100 scale to 0-1 scale
    return similarity / 100.0


def are_titles_fuzzy_duplicates(
    title1: str, title2: str, threshold: float = 0.90
) -> tuple[bool, float]:
    """
    Check if two titles are fuzzy duplicates.

    Args:
        title1: First title
        title2: Second title
        threshold: Similarity threshold (0.0-1.0). Default 0.90 (90% similar)
                  Common values:
                  - 0.95: Very strict (only minor typos)
                  - 0.90: Recommended (catches typos and formatting)
                  - 0.85: Lenient (may have false positives)

    Returns:
        (is_duplicate, similarity_score): Tuple of whether titles match and their similarity
    """
    similarity = calculate_title_similarity(title1, title2)
    is_duplicate = similarity >= threshold

    return is_duplicate, similarity


def find_fuzzy_title_matches(
    target_title: str, candidate_titles: list[str], threshold: float = 0.90
) -> list[tuple[int, str, float]]:
    """
    Find all titles that fuzzy-match the target title.

    Args:
        target_title: Title to match against
        candidate_titles: List of candidate titles
        threshold: Similarity threshold

    Returns:
        List of (index, title, similarity_score) for matches above threshold,
        sorted by similarity (highest first)
    """
    matches = []

    for idx, candidate in enumerate(candidate_titles):
        is_match, similarity = are_titles_fuzzy_duplicates(
            target_title, candidate, threshold
        )
        if is_match:
            matches.append((idx, candidate, similarity))

    # Sort by similarity (highest first)
    matches.sort(key=lambda x: x[2], reverse=True)

    return matches


class FuzzyDuplicationReport:
    """Tracks fuzzy duplicate detection statistics."""

    def __init__(self):
        self.total_comparisons = 0
        self.fuzzy_duplicates_found = 0
        self.exact_duplicates_found = 0
        self.similarity_scores = []

    def add_comparison(self, similarity: float, is_duplicate: bool):
        """Record a title comparison."""
        self.total_comparisons += 1
        if is_duplicate:
            if similarity == 1.0:
                self.exact_duplicates_found += 1
            else:
                self.fuzzy_duplicates_found += 1
            self.similarity_scores.append(similarity)

    def generate_report(self) -> str:
        """Generate human-readable fuzzy matching report."""
        if self.total_comparisons == 0:
            return "No fuzzy matching performed."

        total_duplicates = self.exact_duplicates_found + self.fuzzy_duplicates_found

        if total_duplicates == 0:
            return (
                f"Fuzzy matching: {self.total_comparisons} comparisons, "
                f"no fuzzy duplicates found."
            )

        avg_similarity = (
            sum(self.similarity_scores) / len(self.similarity_scores)
            if self.similarity_scores
            else 0.0
        )

        report_lines = [
            "\n" + "=" * 70,
            "FUZZY TITLE MATCHING REPORT",
            "=" * 70,
            f"Total title comparisons: {self.total_comparisons}",
            f"Exact duplicates found: {self.exact_duplicates_found}",
            f"Fuzzy duplicates found: {self.fuzzy_duplicates_found}",
            f"Total duplicates: {total_duplicates}",
            "",
            f"Average similarity of duplicates: {avg_similarity:.2%}",
            "",
            "Fuzzy duplicates are papers with similar but not identical titles,",
            "such as typos, different punctuation, or encoding variations.",
            "=" * 70 + "\n",
        ]

        return "\n".join(report_lines)


def get_fuzzy_duplicate_candidates(
    df: pd.DataFrame, title: str, threshold: float = 0.90, title_column: str = "title"
) -> pd.DataFrame:
    """
    Get all records in DataFrame that fuzzy-match the given title.

    Useful for finding duplicate candidates during aggregation.

    Args:
        df: DataFrame to search
        title: Title to match
        threshold: Similarity threshold
        title_column: Name of title column

    Returns:
        DataFrame containing matching records
    """
    if len(df) == 0 or title_column not in df.columns:
        return pd.DataFrame()

    matches = []

    for idx, row in df.iterrows():
        candidate_title = row.get(title_column)
        is_match, _ = are_titles_fuzzy_duplicates(title, candidate_title, threshold)
        if is_match:
            matches.append(idx)

    return df.loc[matches] if matches else pd.DataFrame()
