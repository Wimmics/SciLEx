"""
Constants and helper functions for SciLEx.

This module centralizes commonly used constants and provides helper functions
for consistent data validation across the codebase.
"""

import pandas as pd

# Missing value indicator
MISSING_VALUE = "NA"

# API limits and configuration
class APILimits:
    """API-related constants."""
    PAGE_SIZE = 100
    MAX_RESULTS = 10000
    RATE_LIMIT_CALLS = 10
    RATE_LIMIT_PERIOD = 1  # second

# Zotero constants
class ZoteroConstants:
    """Zotero-related constants."""
    DEFAULT_COLLECTION_NAME = "new_models"
    API_BASE_URL = "https://api.zotero.org"
    WRITE_TOKEN_LENGTH = 32

# Item type mappings
class ItemTypes:
    """Document type constants."""
    JOURNAL_ARTICLE = "journalArticle"
    CONFERENCE_PAPER = "conferencePaper"
    BOOK_SECTION = "bookSection"
    MANUSCRIPT = "Manuscript"
    BOOK = "book"


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
