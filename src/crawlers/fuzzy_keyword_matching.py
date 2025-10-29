"""
Fuzzy keyword matching module for validating papers against search keywords.

This module provides fuzzy matching to validate whether papers returned by APIs
actually match the search keywords, even with variations like:
- Stemming differences (algorithm vs algorithms)
- Abbreviations (machine learning vs ML)
- Related terms (neural network vs deep network)
- Minor typos or formatting differences

Uses thefuzz and spacy for intelligent text matching.
"""

import logging
from typing import List, Tuple, Optional
from thefuzz import fuzz
from src.fuzzy_matching import normalize_title, get_nlp
from src.constants import is_valid, is_missing


def normalize_text(text: str) -> str:
    """
    Normalize text for keyword matching (reuses title normalization).

    Args:
        text: Text to normalize

    Returns:
        Normalized text string
    """
    return normalize_title(text)


def extract_ngrams(text: str, n: int) -> List[str]:
    """
    Extract n-gram phrases from text.

    Args:
        text: Input text
        n: Number of words per phrase

    Returns:
        List of n-gram phrases
    """
    if is_missing(text):
        return []

    words = text.split()
    if len(words) < n:
        return [text] if text else []

    ngrams = []
    for i in range(len(words) - n + 1):
        ngram = ' '.join(words[i:i+n])
        ngrams.append(ngram)

    return ngrams


def calculate_keyword_similarity(keyword: str, text_phrase: str) -> float:
    """
    Calculate similarity between keyword and a text phrase.

    Args:
        keyword: Search keyword to match
        text_phrase: Phrase from paper text

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if is_missing(keyword) or is_missing(text_phrase):
        return 0.0

    # Normalize both
    norm_keyword = normalize_text(keyword)
    norm_phrase = normalize_text(text_phrase)

    if not norm_keyword or not norm_phrase:
        return 0.0

    if norm_keyword == norm_phrase:
        return 1.0

    # Use token_sort_ratio for word order flexibility
    similarity = fuzz.token_sort_ratio(norm_keyword, norm_phrase)

    return similarity / 100.0


def keyword_matches_text_fuzzy(
    keyword: str,
    text: str,
    threshold: float = 0.85,
    check_exact_first: bool = True
) -> Tuple[bool, float, str]:
    """
    Check if keyword fuzzy-matches any phrase in text.

    Args:
        keyword: Keyword to search for
        text: Text to search in (title or abstract)
        threshold: Similarity threshold (0.0-1.0)
        check_exact_first: If True, check exact substring match before fuzzy

    Returns:
        Tuple of (is_match, best_similarity, matched_phrase)
    """
    if is_missing(keyword) or is_missing(text):
        return False, 0.0, ""

    keyword_lower = keyword.lower()
    text_lower = text.lower()

    # Quick exact match check (much faster)
    if check_exact_first and keyword_lower in text_lower:
        return True, 1.0, keyword

    # Fuzzy matching using n-grams
    keyword_word_count = len(keyword.split())

    # Extract candidate phrases with similar word count
    # Check n-grams from (n-1) to (n+2) to catch variations
    best_similarity = 0.0
    best_phrase = ""

    for n in range(max(1, keyword_word_count - 1), keyword_word_count + 3):
        ngrams = extract_ngrams(text_lower, n)

        for ngram in ngrams:
            similarity = calculate_keyword_similarity(keyword, ngram)

            if similarity > best_similarity:
                best_similarity = similarity
                best_phrase = ngram

            # Early exit if we find excellent match
            if similarity >= 0.95:
                return True, similarity, ngram

    is_match = best_similarity >= threshold
    return is_match, best_similarity, best_phrase


def check_keywords_in_text_fuzzy(
    keywords: List[str],
    text: str,
    threshold: float = 0.85,
    require_all: bool = False
) -> Tuple[bool, List[Tuple[str, float, str]]]:
    """
    Check if keywords match text using fuzzy matching.

    Args:
        keywords: List of keywords to search for
        text: Text to search in
        threshold: Fuzzy matching threshold
        require_all: If True, ALL keywords must match (AND logic)
                    If False, ANY keyword must match (OR logic)

    Returns:
        Tuple of (overall_match, list of (keyword, similarity, matched_phrase))
    """
    if not keywords or is_missing(text):
        return False, []

    matches = []

    for keyword in keywords:
        is_match, similarity, phrase = keyword_matches_text_fuzzy(
            keyword, text, threshold
        )

        if is_match:
            matches.append((keyword, similarity, phrase))

    # Determine overall match based on logic
    if require_all:
        overall_match = len(matches) == len(keywords)
    else:
        overall_match = len(matches) > 0

    return overall_match, matches


def check_dual_keywords_fuzzy(
    keywords_group1: List[str],
    keywords_group2: List[str],
    text: str,
    threshold: float = 0.85
) -> Tuple[bool, List[Tuple[str, float, str]]]:
    """
    Check dual keyword groups (must match from BOTH groups).

    Args:
        keywords_group1: First keyword group
        keywords_group2: Second keyword group
        text: Text to search in
        threshold: Fuzzy matching threshold

    Returns:
        Tuple of (match_from_both_groups, all_matches)
    """
    if is_missing(text):
        return False, []

    # Check first group (OR logic within group)
    match1, matches1 = check_keywords_in_text_fuzzy(
        keywords_group1, text, threshold, require_all=False
    )

    # Check second group (OR logic within group)
    match2, matches2 = check_keywords_in_text_fuzzy(
        keywords_group2, text, threshold, require_all=False
    )

    # Both groups must have at least one match
    overall_match = match1 and match2
    all_matches = matches1 + matches2

    return overall_match, all_matches


class FuzzyKeywordMatchReport:
    """Tracks fuzzy keyword matching statistics during aggregation."""

    def __init__(self):
        self.exact_matches = 0
        self.fuzzy_matches = 0
        self.no_matches = 0
        self.fuzzy_match_examples = []

    def add_exact_match(self):
        """Record an exact keyword match."""
        self.exact_matches += 1

    def add_fuzzy_match(self, keyword: str, similarity: float, matched_phrase: str):
        """Record a fuzzy keyword match."""
        self.fuzzy_matches += 1

        # Store first 10 examples for reporting
        if len(self.fuzzy_match_examples) < 10:
            self.fuzzy_match_examples.append({
                'keyword': keyword,
                'similarity': similarity,
                'matched_phrase': matched_phrase
            })

    def add_no_match(self):
        """Record a paper with no keyword matches."""
        self.no_matches += 1

    def generate_report(self) -> str:
        """Generate human-readable fuzzy keyword matching report."""
        total = self.exact_matches + self.fuzzy_matches + self.no_matches

        if total == 0:
            return "No fuzzy keyword matching performed."

        fuzzy_rate = (self.fuzzy_matches / total * 100) if total > 0 else 0

        report_lines = [
            "\n" + "=" * 70,
            "FUZZY KEYWORD MATCHING REPORT",
            "=" * 70,
            f"Total papers evaluated: {total}",
            f"Exact keyword matches: {self.exact_matches}",
            f"Fuzzy keyword matches: {self.fuzzy_matches} ({fuzzy_rate:.1f}%)",
            f"No keyword matches (filtered): {self.no_matches}",
            ""
        ]

        if self.fuzzy_match_examples:
            report_lines.append("Example fuzzy matches:")
            for example in self.fuzzy_match_examples[:5]:
                report_lines.append(
                    f"  - Keyword: '{example['keyword']}' → "
                    f"Matched: '{example['matched_phrase']}' "
                    f"(similarity: {example['similarity']:.2%})"
                )
            report_lines.append("")

        report_lines.extend([
            "Fuzzy matching helps catch keyword variations like abbreviations,",
            "plural forms, and related terms that exact matching would miss.",
            "=" * 70 + "\n"
        ])

        return "\n".join(report_lines)
