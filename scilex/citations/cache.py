"""
SQLite-based citation caching system.

Provides persistent caching for citation data to avoid redundant API calls.
Features:
- DOI-based lookups
- 30-day TTL (Time To Live)
- Thread-safe operations
- Automatic cache cleanup
"""

import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Thread-local storage for database connections (thread-safe)
_thread_local = threading.local()

# Default cache TTL: 30 days
DEFAULT_TTL_DAYS = 30


def get_cache_path(output_dir: str = "output") -> Path:
    """Get the path to the citation cache database.

    Args:
        output_dir: Base output directory

    Returns:
        Path to citation_cache.db file
    """
    cache_dir = Path(output_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "citation_cache.db"


def _get_connection(cache_path: Path) -> sqlite3.Connection:
    """Get thread-local database connection (thread-safe).

    Args:
        cache_path: Path to SQLite database

    Returns:
        sqlite3.Connection for current thread
    """
    if not hasattr(_thread_local, "connection") or _thread_local.connection is None:
        _thread_local.connection = sqlite3.connect(
            str(cache_path),
            check_same_thread=False,  # Allow multi-threading
            timeout=30.0,  # 30 second timeout for locks
        )
        # Enable WAL mode for better concurrency
        _thread_local.connection.execute("PRAGMA journal_mode=WAL")
        _thread_local.connection.execute("PRAGMA synchronous=NORMAL")
    return _thread_local.connection


def initialize_cache(cache_path: Path | None = None) -> Path:
    """Initialize citation cache database with schema.

    Args:
        cache_path: Optional path to cache database (default: output/citation_cache.db)

    Returns:
        Path to initialized cache database
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    # Create citations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            doi TEXT PRIMARY KEY,
            citations_json TEXT NOT NULL,
            nb_cited INTEGER,
            nb_citations INTEGER,
            cit_status TEXT,
            ref_status TEXT,
            cached_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)

    # Create index on expiration time for fast cleanup
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_expires_at ON citations(expires_at)
    """)

    conn.commit()
    logging.debug(f"Citation cache initialized at {cache_path}")

    return cache_path


def get_cached_citation(doi: str, cache_path: Path | None = None) -> dict | None:
    """Retrieve cached citation data for a DOI.

    Args:
        doi: DOI string
        cache_path: Optional path to cache database

    Returns:
        Dict with citation data if found and not expired, None otherwise
        Format: {
            "citations": <json string>,
            "nb_cited": <int>,
            "nb_citations": <int>,
            "api_stats": {
                "cit_status": <str>,
                "ref_status": <str>
            }
        }
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    # Query with expiration check
    cursor.execute(
        """
        SELECT citations_json, nb_cited, nb_citations, cit_status, ref_status
        FROM citations
        WHERE doi = ? AND expires_at > ?
    """,
        (doi, datetime.now().isoformat()),
    )

    row = cursor.fetchone()
    if row is None:
        return None

    return {
        "citations": row[0],  # JSON string
        "nb_cited": row[1],
        "nb_citations": row[2],
        "api_stats": {"cit_status": row[3], "ref_status": row[4]},
    }


def cache_citation(
    doi: str,
    citations_json: str,
    nb_cited: int,
    nb_citations: int,
    api_stats: dict[str, str],
    cache_path: Path | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Store citation data in cache.

    Args:
        doi: DOI string
        citations_json: Citation data as JSON string
        nb_cited: Number of cited papers
        nb_citations: Number of citing papers
        api_stats: API call statistics {"cit_status": ..., "ref_status": ...}
        cache_path: Optional path to cache database
        ttl_days: Time to live in days (default: 30)
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    now = datetime.now()
    expires_at = now + timedelta(days=ttl_days)

    # Insert or replace (UPSERT)
    cursor.execute(
        """
        INSERT OR REPLACE INTO citations
        (doi, citations_json, nb_cited, nb_citations, cit_status, ref_status, cached_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            doi,
            citations_json,
            nb_cited,
            nb_citations,
            api_stats.get("cit_status", "unknown"),
            api_stats.get("ref_status", "unknown"),
            now.isoformat(),
            expires_at.isoformat(),
        ),
    )

    conn.commit()
    logging.debug(f"Cached citation data for DOI: {doi}")


def get_cached_citations_batch(dois: list[str], cache_path: Path | None = None) -> dict:
    """Retrieve cached citations for multiple DOIs in one SQL query.

    Uses WHERE doi IN (...) with chunking to stay within SQLite's parameter
    limit (~999). Much faster than N individual queries for large DOI lists.

    Args:
        dois: List of DOI strings to look up.
        cache_path: Optional path to cache database.

    Returns:
        dict: {doi: {"citations": ..., "nb_cited": ..., "nb_citations": ...,
               "api_stats": {...}}} for found DOIs. DOIs not in cache (or
               expired) are omitted.
    """
    if not dois:
        return {}

    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    results = {}
    chunk_size = 500  # SQLite parameter limit safety margin

    for i in range(0, len(dois), chunk_size):
        chunk = dois[i : i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        cursor.execute(
            f"""
            SELECT doi, citations_json, nb_cited, nb_citations, cit_status, ref_status
            FROM citations
            WHERE doi IN ({placeholders}) AND expires_at > ?
            """,
            (*chunk, now),
        )
        for row in cursor.fetchall():
            results[row[0]] = {
                "citations": row[1],
                "nb_cited": row[2],
                "nb_citations": row[3],
                "api_stats": {"cit_status": row[4], "ref_status": row[5]},
            }

    logging.debug(f"Batch cache lookup: {len(results)}/{len(dois)} hits")
    return results


def cache_citations_batch(
    entries: list[dict],
    cache_path: Path | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Store multiple citation results in one transaction.

    Uses executemany() with INSERT OR REPLACE for efficient bulk writes.

    Args:
        entries: List of dicts, each with keys:
            doi, citations_json, nb_cited, nb_citations, api_stats
        cache_path: Optional path to cache database.
        ttl_days: Time to live in days (default: 30).
    """
    if not entries:
        return

    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    now = datetime.now()
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    now_iso = now.isoformat()

    rows = [
        (
            e["doi"],
            e["citations_json"],
            e["nb_cited"],
            e["nb_citations"],
            e["api_stats"].get("cit_status", "unknown"),
            e["api_stats"].get("ref_status", "unknown"),
            now_iso,
            expires_at,
        )
        for e in entries
    ]

    cursor.executemany(
        """
        INSERT OR REPLACE INTO citations
        (doi, citations_json, nb_cited, nb_citations, cit_status, ref_status, cached_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    logging.debug(f"Batch cached {len(entries)} citation entries")


def cleanup_expired_cache(cache_path: Path | None = None) -> int:
    """Remove expired entries from cache.

    Args:
        cache_path: Optional path to cache database

    Returns:
        Number of entries removed
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    # Delete expired entries
    cursor.execute(
        """
        DELETE FROM citations WHERE expires_at <= ?
    """,
        (datetime.now().isoformat(),),
    )

    removed_count = cursor.rowcount
    conn.commit()

    if removed_count > 0:
        logging.info(f"Cleaned up {removed_count} expired cache entries")

    return removed_count


def get_cache_stats(cache_path: Path | None = None) -> dict:
    """Get cache statistics.

    Args:
        cache_path: Optional path to cache database

    Returns:
        Dict with cache statistics
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    # Total entries
    cursor.execute("SELECT COUNT(*) FROM citations")
    total = cursor.fetchone()[0]

    # Active (non-expired) entries
    cursor.execute(
        """
        SELECT COUNT(*) FROM citations WHERE expires_at > ?
    """,
        (datetime.now().isoformat(),),
    )
    active = cursor.fetchone()[0]

    # Expired entries
    expired = total - active

    return {
        "total_entries": total,
        "active_entries": active,
        "expired_entries": expired,
        "cache_path": str(cache_path),
    }


def clear_cache(cache_path: Path | None = None) -> int:
    """Clear entire cache (delete all entries).

    Args:
        cache_path: Optional path to cache database

    Returns:
        Number of entries removed
    """
    if cache_path is None:
        cache_path = get_cache_path()

    conn = _get_connection(cache_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM citations")
    count = cursor.fetchone()[0]

    cursor.execute("DELETE FROM citations")
    conn.commit()

    logging.info(f"Cleared {count} entries from citation cache")
    return count


def close_connections():
    """Close thread-local database connections (cleanup)."""
    if hasattr(_thread_local, "connection") and _thread_local.connection is not None:
        _thread_local.connection.close()
        _thread_local.connection = None
