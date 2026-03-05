"""
Constants and helper functions for SciLEx.

This module centralizes commonly used constants and provides helper functions
for consistent data validation across the codebase.
"""

import pandas as pd

# Missing value indicator
MISSING_VALUE = "NA"


# Circuit breaker configuration
class CircuitBreakerConfig:
    """Circuit breaker pattern configuration for API resilience."""

    FAILURE_THRESHOLD = 5  # Open circuit after N consecutive failures
    TIMEOUT_SECONDS = 60  # Wait time before attempting retry from OPEN state
    MAX_RETRIES = 3  # Maximum number of retry attempts per request


# Rate limit backoff configuration
class RateLimitBackoffConfig:
    """Rate limit backoff strategies for different APIs."""

    # Default exponential backoff: 2s, 4s, 8s
    DEFAULT_BASE_WAIT = 2
    DEFAULT_USE_EXPONENTIAL = True

    # API-specific configurations
    # Format: {api_name: (base_wait_seconds, use_exponential_backoff)}
    API_SPECIFIC = {
        "DBLP": (30, False),  # DBLP: Fixed 30s wait (no exponential)
        "Springer": (15, True),  # Springer: 15s, 30s, 60s
        "IEEE": (10, True),  # IEEE: 10s, 20s, 40s
        "Elsevier": (20, True),  # Elsevier: 20s, 40s, 80s
        # Others use default (2s exponential)
    }


# Citation filter configuration
class CitationFilterConfig:
    """Time-aware citation filtering thresholds for paper quality assessment."""

    # Age thresholds (in months)
    GRACE_PERIOD_MONTHS = 18  # Very recent papers (0-18 months) - no filtering
    EARLY_THRESHOLD_MONTHS = 21  # Early stage papers (18-21 months)
    MEDIUM_THRESHOLD_MONTHS = 24  # Medium age papers (21-24 months)
    MATURE_THRESHOLD_MONTHS = 36  # Mature papers (24-36 months)

    # Citation count requirements by age group
    GRACE_PERIOD_CITATIONS = 0  # 0-18 months: 0 citations required
    EARLY_CITATIONS = 1  # 18-21 months: 1+ citations required
    MEDIUM_CITATIONS = 3  # 21-24 months: 3+ citations required
    MATURE_BASE_CITATIONS = 5  # 24-36 months: starts at 5, increases to 8
    ESTABLISHED_BASE_CITATIONS = 10  # 36+ months: starts at 10, increases gradually

    # Warning threshold for zero-citation rate
    HIGH_ZERO_CITATION_RATE = 80  # Warn if >80% of papers have 0 citations


class ZoteroConstants:
    """Zotero-related constants."""

    DEFAULT_COLLECTION_NAME = "new_models"
    API_BASE_URL = "https://api.zotero.org"
    WRITE_TOKEN_LENGTH = 32


def is_valid(value) -> bool:
    """
    Check if a value is not null, NaN, or the missing value string.

    This function provides a consistent way to check for missing data across
    the codebase, handling both string "NA" values and pandas NaN values.

    Args:
        value: The value to check

    Returns:
        bool: True if the value is valid (not missing), False otherwise

    Examples:
        >>> is_valid("some text")
        True
        >>> is_valid("NA")
        False
        >>> is_valid("")
        False
        >>> is_valid(None)
        False
        >>> is_valid(pd.NA)
        False
    """
    if pd.isna(value):
        return False

    str_value = str(value).strip()
    return str_value != "" and str_value.upper() != MISSING_VALUE.upper()


def is_missing(value) -> bool:
    """
    Check if a value is missing (null, NaN, or the missing value string).

    This is the inverse of is_valid() for cases where checking for
    missing values is more intuitive.

    Args:
        value: The value to check

    Returns:
        bool: True if the value is missing, False otherwise
    """
    return not is_valid(value)


def safe_str(value, default: str = MISSING_VALUE) -> str:
    """
    Safely convert a value to string, returning default if value is missing.

    Args:
        value: The value to convert
        default: The default string to return if value is missing

    Returns:
        str: String representation of value, or default if missing
    """
    if is_missing(value):
        return default
    return str(value)


def normalize_path_component(path_component: str) -> str:
    """
    Remove leading/trailing slashes from path components.

    Ensures os.path.join() works correctly by preventing absolute path behavior
    when config values mistakenly contain leading slashes (e.g., "/aggregated_results.csv").

    Python's os.path.join() treats paths starting with "/" as absolute paths and
    discards all previous path components. This function strips leading and trailing
    slashes to ensure path components are always treated as relative paths.

    Args:
        path_component: Path component from config or user input

    Returns:
        str: Normalized path component without leading/trailing slashes

    Examples:
        >>> normalize_path_component("/aggregated_results.csv")
        'aggregated_results.csv'
        >>> normalize_path_component("collect_name/")
        'collect_name'
        >>> normalize_path_component("/dirname/")
        'dirname'
        >>> normalize_path_component("normal_path")
        'normal_path'
    """
    return path_component.strip("/")
