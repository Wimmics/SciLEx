"""Configuration defaults for SciLEx.

This module centralizes all sensible defaults that users rarely need to change.
The main configuration file only needs to specify essential research parameters.
Users can optionally override these defaults with their own values.

When a configuration value is not specified in scilex.config.yml, the system
will use the corresponding default from this module.
"""

import os

# ============================================================================
# OUTPUT AND FILE SETTINGS
# ============================================================================

# Compute project root (parent of src/) to ensure consistent paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")
"""Base directory for all collection and aggregation output.
Absolute path to ensure consistency regardless of working directory."""

DEFAULT_AGGREGATED_FILENAME = "aggregated_results.csv"
"""Filename for aggregated and deduplicated papers."""

DEFAULT_ENABLE_TEXT_FILTER = True
"""Always apply text filters during aggregation (filter low-quality papers)."""

# ============================================================================
# ABSTRACT QUALITY THRESHOLDS
# ============================================================================

MIN_ABSTRACT_WORDS = 50
"""Minimum abstract length in words. Detects truncated or stub abstracts.
Typical range: 50-100 words. Set to 0 to disable."""

MAX_ABSTRACT_WORDS = 1000
"""Maximum abstract length in words. Detects copy-paste errors or non-abstracts.
Typical range: 500-1000 words. Set to 0 to disable."""

MIN_ABSTRACT_QUALITY_SCORE = 50
"""Minimum acceptable quality score for abstracts (0-100 scale).
Used when validate_abstracts is enabled."""

# ============================================================================
# AUTHOR AND METADATA VALIDATION
# ============================================================================

MIN_AUTHOR_COUNT = 2
"""Minimum number of authors required for a paper record.
Set to 1 for at least one author, 2 to exclude single-author papers."""

# ============================================================================
# RELEVANCE SCORING WEIGHTS
# ============================================================================

DEFAULT_RELEVANCE_WEIGHTS = {
    "keywords": 0.45,  # 45% - Content relevance to search terms (primary)
    "quality": 0.25,  # 25% - Metadata completeness and richness
    "itemtype": 0.20,  # 20% - Publication venue quality (scholarly types)
    "citations": 0.10,  # 10% - Research impact (minimized for recency bias)
}
"""Component weights for composite relevance scoring (must sum to 1.0).
Each component is normalized to 0-10 scale before weighting.
Prioritizes content relevance and quality over citations."""

DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS = {
    "journalArticle": True,  # Peer-reviewed journal articles
    "conferencePaper": True,  # Conference proceedings papers
    "bookSection": True,  # Book chapters
    "book": True,  # Complete books and monographs
}
"""ItemTypes that receive full weight (10 points) in relevance scoring.
Papers with these types are considered high-quality scholarly publications.
Papers with missing or unlisted itemTypes receive 0 points."""

# ============================================================================
# DEFAULT ITEMTYPE BYPASS AND FILTERING
# ============================================================================

DEFAULT_ENABLE_ITEMTYPE_BYPASS = True
"""Enable fast-track validation bypass for trusted publication types.
Papers with bypass itemTypes skip subsequent quality filters."""

DEFAULT_BYPASS_ITEM_TYPES = [
    "journalArticle",
    "conferencePaper",
]
"""Publication types that bypass subsequent quality filters.
Trusted sources: journalArticle, conferencePaper (peer-reviewed, high quality)."""

DEFAULT_ENABLE_ITEMTYPE_FILTER = False
"""Enable whitelist filtering - only keep papers with allowed itemTypes.
When enabled, all other papers are removed (strict mode)."""

DEFAULT_ALLOWED_ITEM_TYPES = [
    "journalArticle",  # Peer-reviewed journal articles
    "conferencePaper",  # Conference proceedings
    "bookSection",  # Book chapters
    "book",  # Books and monographs
]
"""ItemTypes to keep when itemtype filtering is enabled.
All other papers will be removed from aggregated results."""

# ============================================================================
# QUALITY FILTER REQUIREMENTS
# ============================================================================

DEFAULT_REQUIRE_ABSTRACT = True
"""Require papers to have an abstract.
Set to True for literature reviews, False for bibliometric studies."""

DEFAULT_REQUIRE_DOI = False
"""Require papers to have a DOI for citation tracking.
Set to False if using APIs like Google Scholar (often lack DOIs)."""

DEFAULT_REQUIRE_YEAR = True
"""Require publication year to be present.
Essential for temporal analysis and citation filtering."""

DEFAULT_REQUIRE_OPEN_ACCESS = False
"""Require papers to be open access (free to read).
Optional filter - reduces collection size significantly."""

# ============================================================================
# VALIDATION FEATURES
# ============================================================================

DEFAULT_VALIDATE_YEAR_RANGE = True
"""Validate papers fall within configured year range.
Uses years from main config - removes papers outside timeframe."""

DEFAULT_GENERATE_QUALITY_REPORT = True
"""Generate quality validation report during aggregation.
Reports show: papers filtered, reasons, data completeness stats."""

DEFAULT_VALIDATE_ABSTRACTS = False
"""Validate abstract quality (detect truncation, boilerplate, encoding issues).
Set to True to get detailed abstract quality reports."""

DEFAULT_FILTER_BY_ABSTRACT_QUALITY = False
"""Filter out papers with poor abstract quality.
Only applies if validate_abstracts is True."""

# ============================================================================
# CITATION AND RELEVANCE FEATURES
# ============================================================================

DEFAULT_APPLY_CITATION_FILTER = True
"""Apply time-aware citation filtering based on paper age.
Focuses on impactful papers while keeping recent work."""

DEFAULT_USE_SEMANTIC_SCHOLAR_CITATIONS = True
"""Use Semantic Scholar citation data as fallback for OpenCitations.
Improves citation completeness for preprints and recent papers."""

DEFAULT_APPLY_RELEVANCE_RANKING = True
"""Apply composite relevance scoring to rank papers by importance.
Papers sorted by relevance_score (higher = more relevant)."""

DEFAULT_MAX_PAPERS = 1000
"""Maximum number of papers to keep after all filtering.
Set to None to keep all papers that pass filters.
Recommended: 500-1000 for focused reviews, None for comprehensive studies."""

DEFAULT_TRACK_DUPLICATE_SOURCES = True
"""Track which APIs found which papers and analyze overlap.
Generates reports showing API value and optimization recommendations."""

# ============================================================================
# COLLECTION WORKFLOW SETTINGS
# ============================================================================

DEFAULT_COLLECT_ENABLED = True
"""Enable collection phase by default.
Set to False to skip collection and only aggregate existing data."""

DEFAULT_SEMANTIC_SCHOLAR_MODE = "regular"
"""Semantic Scholar API endpoint mode.
Options: 'regular' (default, recommended) or 'bulk' (requires special access)."""

# ============================================================================
# API RATE LIMITS (requests per second)
# ============================================================================

DEFAULT_RATE_LIMITS = {
    "SemanticScholar": {"without_key": 1.0, "with_key": 1.0},
    "OpenAlex": {"without_key": 10.0, "with_key": 10.0},
    "Arxiv": {"without_key": 0.33, "with_key": 0.33},  # 1 req per 3 seconds
    "IEEE": {"without_key": 2.0, "with_key": 2.0},
    "Elsevier": {"without_key": 2.0, "with_key": 9.0},  # Scopus: 9 req/sec with key
    "Springer": {"without_key": 1.67, "with_key": 1.67},  # 100 req/min
    "HAL": {"without_key": 10.0, "with_key": 10.0},  # No documented limit
    "DBLP": {"without_key": 1.0, "with_key": 1.0},  # 1-2s between requests
    "Crossref": {
        "without_key": 5.0,
        "with_key": 10.0,
    },  # public: 5 req/sec, polite pool (mailto): 10 req/sec
    "Istex": {"without_key": 5.0, "with_key": 5.0},  # No documented limit
    "PubMed": {
        "without_key": 3.0,
        "with_key": 10.0,
    },  # NCBI: 3/sec free, 10/sec with key
    "PubMedCentral": {"without_key": 3.0, "with_key": 10.0},  # Same NCBI limits
}
"""Rate limits for each API provider (requests per second).
Each entry has without_key/with_key values. The correct rate is auto-selected
based on whether the collector has an API key configured."""

# ============================================================================
# QUALITY FILTER CONFIGURATION SCHEMA (for reference)
# ============================================================================

QUALITY_FILTER_SCHEMA = {
    "enable_itemtype_bypass": bool,
    "bypass_item_types": list,
    "enable_itemtype_filter": bool,
    "allowed_item_types": list,
    "require_abstract": bool,
    "require_doi": bool,
    "require_year": bool,
    "require_open_access": bool,
    "min_author_count": int,
    "min_abstract_words": int,
    "max_abstract_words": int,
    "validate_year_range": bool,
    "validate_abstracts": bool,
    "min_abstract_quality_score": int,
    "filter_by_abstract_quality": bool,
    "generate_quality_report": bool,
    "apply_citation_filter": bool,
    "use_semantic_scholar_citations": bool,
    "apply_relevance_ranking": bool,
    "relevance_weights": dict,
    "itemtype_relevance_weights": dict,
    "max_papers": (int, type(None)),
    "track_duplicate_sources": bool,
}
"""Schema documenting all available quality filter options."""


def get_default_quality_filters():
    """Return all default quality filter settings as a dictionary."""
    return {
        "enable_itemtype_bypass": DEFAULT_ENABLE_ITEMTYPE_BYPASS,
        "bypass_item_types": DEFAULT_BYPASS_ITEM_TYPES,
        "enable_itemtype_filter": DEFAULT_ENABLE_ITEMTYPE_FILTER,
        "allowed_item_types": DEFAULT_ALLOWED_ITEM_TYPES,
        "require_abstract": DEFAULT_REQUIRE_ABSTRACT,
        "require_doi": DEFAULT_REQUIRE_DOI,
        "require_year": DEFAULT_REQUIRE_YEAR,
        "require_open_access": DEFAULT_REQUIRE_OPEN_ACCESS,
        "min_author_count": MIN_AUTHOR_COUNT,
        "min_abstract_words": MIN_ABSTRACT_WORDS,
        "max_abstract_words": MAX_ABSTRACT_WORDS,
        "validate_year_range": DEFAULT_VALIDATE_YEAR_RANGE,
        "validate_abstracts": DEFAULT_VALIDATE_ABSTRACTS,
        "min_abstract_quality_score": MIN_ABSTRACT_QUALITY_SCORE,
        "filter_by_abstract_quality": DEFAULT_FILTER_BY_ABSTRACT_QUALITY,
        "generate_quality_report": DEFAULT_GENERATE_QUALITY_REPORT,
        "apply_citation_filter": DEFAULT_APPLY_CITATION_FILTER,
        "use_semantic_scholar_citations": DEFAULT_USE_SEMANTIC_SCHOLAR_CITATIONS,
        "apply_relevance_ranking": DEFAULT_APPLY_RELEVANCE_RANKING,
        "relevance_weights": DEFAULT_RELEVANCE_WEIGHTS,
        "itemtype_relevance_weights": DEFAULT_ITEMTYPE_RELEVANCE_WEIGHTS,
        "max_papers": DEFAULT_MAX_PAPERS,
        "track_duplicate_sources": DEFAULT_TRACK_DUPLICATE_SOURCES,
    }


def get_rate_limit(api_name: str, has_api_key: bool = False) -> float:
    """Get rate limit for a specific API, selecting with_key/without_key rate.

    Args:
        api_name: Name of the API (e.g., 'SemanticScholar', 'IEEE')
        has_api_key: Whether the collector has an API key configured

    Returns:
        Rate limit in requests per second
    """
    entry = DEFAULT_RATE_LIMITS.get(api_name)
    if entry is None:
        return 5.0
    if isinstance(entry, dict):
        return entry["with_key"] if has_api_key else entry["without_key"]
    # Backward compat: if someone passes a plain float
    return float(entry)  # type: ignore[arg-type]
