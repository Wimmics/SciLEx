"""Fetchers for outgoing references and incoming citers with fallback chains.

Outgoing references (what a paper cites) — three tiers:
  1. SemanticScholar /references  (fast, rich)
  2. CrossRef /works/{doi}        (free, no key; mailto for polite pool)
  3. OpenCitations /references    (1 req/sec; last resort)

Incoming citers (who cites a paper) — two tiers:
  1. SemanticScholar /citations   (fast, rich)
  2. OpenCitations /citations     (1 req/sec; CrossRef has no free citedBy API)
"""

import json
import logging
import os
import urllib.parse

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from scilex.citations.citations_tools import getCitations, getReferences

logger = logging.getLogger(__name__)

SS_REFERENCES_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/references"
)
SS_CITATIONS_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/citations"
CROSSREF_WORKS_URL = "https://api.crossref.org/works/{doi}"


# ---------------------------------------------------------------------------
# Low-level SS request helpers (two variants for different rate limits)
# ---------------------------------------------------------------------------


def _is_retryable_ss_error(exc: BaseException) -> bool:
    """Return True only for transient SemanticScholar errors worth retrying.

    Retries on 429 (rate-limited), 5xx (server errors), Timeout, and
    ConnectionError.  Does NOT retry on 4xx client errors (401, 403, 404)
    because those will not improve on retry.

    Args:
        exc: The exception to evaluate.

    Returns:
        True if the request should be retried, False otherwise.
    """
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status == 429 or (status is not None and status >= 500)
    return isinstance(
        exc, requests.exceptions.Timeout | requests.exceptions.ConnectionError
    )


@retry(
    retry=retry_if_exception(_is_retryable_ss_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
@sleep_and_retry
@limits(calls=1, period=1)  # SS public: 1 req/sec
def _fetch_ss_no_key(doi: str) -> list[str]:
    """Fetch reference DOIs from SemanticScholar without an API key."""
    return _do_ss_request(doi, api_key=None)


@retry(
    retry=retry_if_exception(_is_retryable_ss_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
@sleep_and_retry
@limits(calls=10, period=1)  # SS with key: 10 req/sec (conservative vs 100 max)
def _fetch_ss_with_key(doi: str, api_key: str) -> list[str]:
    """Fetch reference DOIs from SemanticScholar with an API key."""
    return _do_ss_request(doi, api_key=api_key)


def _do_ss_request(doi: str, api_key: str | None) -> list[str]:
    """Execute the SemanticScholar references HTTP request.

    Args:
        doi: Clean DOI string (no https://doi.org/ prefix).
        api_key: Optional SS API key.

    Returns:
        List of cited DOI strings (lowercase, stripped).

    Raises:
        requests.exceptions.RequestException: On HTTP errors.
    """
    url = SS_REFERENCES_URL.format(doi=urllib.parse.quote(doi, safe="/"))
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {"fields": "externalIds", "limit": 500}

    resp = requests.get(url, headers=headers, params=params, timeout=15)

    if resp.status_code == 404:
        logger.debug(f"SS: paper not found for DOI {doi}")
        return []

    resp.raise_for_status()
    data = resp.json().get("data") or []

    result = []
    for item in data:
        cited_ids = item.get("citedPaper", {}).get("externalIds") or {}
        cited_doi = cited_ids.get("DOI")
        if cited_doi:
            result.append(cited_doi.strip())

    return result


def fetch_references_ss(doi: str, api_key: str | None = None) -> list[str]:
    """Return list of DOIs cited by *doi* via SemanticScholar.

    Args:
        doi: DOI string (with or without https://doi.org/ prefix).
        api_key: Optional SemanticScholar API key for higher rate limits.

    Returns:
        List of cited DOI strings, or empty list if not found / error.
    """
    clean_doi = doi.replace("https://doi.org/", "").strip()
    try:
        if api_key:
            return _fetch_ss_with_key(clean_doi, api_key) or []
        else:
            return _fetch_ss_no_key(clean_doi) or []
    except (requests.exceptions.RequestException, OSError) as e:
        logger.warning(f"SS fetch failed for DOI {clean_doi}: {e}")
        return []


def _fetch_references_oc(doi: str) -> list[str]:
    """Return cited DOI list from OpenCitations for a single DOI.

    Args:
        doi: Clean DOI string.

    Returns:
        List of cited DOI strings.
    """
    success, response, _ = getReferences(doi)
    if not success or response is None:
        return []
    try:
        data = response.json()
        return [
            item["cited"].replace("https://doi.org/", "").strip()
            for item in data
            if item.get("cited")
        ]
    except (ValueError, KeyError) as e:
        logger.warning(f"OC parse error for DOI {doi}: {e}")
        return []


def _is_retryable_crossref_error(exc: BaseException) -> bool:
    """Return True only for transient CrossRef errors worth retrying.

    Retries on 429 (rate-limited) and 5xx (server errors).
    Does NOT retry on 4xx client errors (e.g. 404) — those won't improve.
    """
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status == 429 or (status is not None and status >= 500)
    return isinstance(exc, requests.exceptions.Timeout)


@retry(
    retry=retry_if_exception(_is_retryable_crossref_error),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
@sleep_and_retry
@limits(calls=1, period=1)  # Conservative: 1 req/sec avoids server-side throttling
def _fetch_references_crossref(doi: str, mailto: str | None = None) -> list[str]:
    """Fetch reference DOIs from CrossRef /works/{doi} endpoint.

    Args:
        doi: Clean DOI string (no https://doi.org/ prefix).
        mailto: Optional email address for CrossRef polite pool.

    Returns:
        List of cited DOI strings, or empty list if not found / no refs.
    """
    url = CROSSREF_WORKS_URL.format(doi=urllib.parse.quote(doi, safe="/"))
    params: dict[str, str] = {}
    if mailto:
        params["mailto"] = mailto
    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code in (400, 404):
        logger.debug(f"CrossRef: no record for DOI {doi} (HTTP {resp.status_code})")
        return []
    resp.raise_for_status()
    refs = resp.json().get("message", {}).get("reference", [])
    return [r["DOI"].strip() for r in refs if r.get("DOI")]


def fetch_references_batch(
    dois: list[str],
    api_key: str | None = None,
    cache_path: str | None = None,
    fallback_opencitations: bool = True,
    mailto: str | None = None,
) -> dict[str, list[str]]:
    """Fetch reference DOI lists for many papers with cache and three-tier fallback.

    Fallback chain per paper:
      1. SemanticScholar (primary, fast, rich).
      2. CrossRef /works/{doi} (middle tier, free, no key needed).
      3. OpenCitations (last resort, 1 req/sec).

    Results are cached to a JSON file for resumability across interrupted runs.

    Args:
        dois: List of DOI strings to look up.
        api_key: Optional SemanticScholar API key (enables 10 req/sec vs 1).
        cache_path: Path to JSON cache file. Pass None to skip caching.
        fallback_opencitations: If True, use OpenCitations when CrossRef also
            returns an empty list.
        mailto: Optional email for CrossRef polite pool (higher rate limits).

    Returns:
        Dict mapping each DOI to its list of cited DOIs.
    """
    # Load existing cache
    cache: dict[str, list[str]] = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
            logger.info(f"Loaded {len(cache)} cached entries from {cache_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load cache {cache_path}: {e}")

    results: dict[str, list[str]] = {}
    pending = [d for d in dois if d not in cache]

    logger.info(
        f"Fetching references: {len(dois)} DOIs total, "
        f"{len(cache)} cached, {len(pending)} to fetch"
    )

    for i, doi in enumerate(pending, 1):
        clean_doi = doi.replace("https://doi.org/", "").strip()
        if not clean_doi:
            results[doi] = []
            continue

        # Tier 1: SemanticScholar
        refs = fetch_references_ss(clean_doi, api_key=api_key)

        # Tier 2: CrossRef (when SS returned nothing)
        if not refs:
            logger.debug(f"SS empty for {clean_doi}, trying CrossRef...")
            try:
                refs = _fetch_references_crossref(clean_doi, mailto=mailto) or []
                if refs:
                    logger.debug(f"CrossRef found {len(refs)} refs for {clean_doi}")
            except Exception as e:
                logger.warning(f"CrossRef fetch failed for DOI {clean_doi}: {e}")
                refs = []

        # Tier 3: OpenCitations (when CrossRef also returned nothing)
        if not refs and fallback_opencitations:
            logger.debug(f"CrossRef empty for {clean_doi}, trying OpenCitations...")
            refs = _fetch_references_oc(clean_doi)
            if refs:
                logger.debug(f"OC found {len(refs)} refs for {clean_doi}")

        results[doi] = refs

        # Persist cache incrementally
        if cache_path and i % 10 == 0:
            _save_cache(cache_path, {**cache, **results})

        if i % 50 == 0 or i == len(pending):
            logger.info(f"  Progress: {i}/{len(pending)} fetched")

    # Merge cache + new results
    combined = {**cache, **results}

    if cache_path:
        _save_cache(cache_path, combined)

    # Return only the requested DOIs
    return {doi: combined.get(doi, []) for doi in dois}


def _save_cache(cache_path: str, data: dict[str, list[str]]) -> None:
    """Write cache dict to JSON file, creating parent dirs as needed."""
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Incoming citers — who cites each paper (SS primary, OC fallback)
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception(_is_retryable_ss_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
@sleep_and_retry
@limits(calls=1, period=1)  # SS public: 1 req/sec
def _fetch_ss_citers_no_key(doi: str) -> list[str]:
    """Fetch citing-paper DOIs from SemanticScholar without an API key."""
    return _do_ss_citers_request(doi, api_key=None)


@retry(
    retry=retry_if_exception(_is_retryable_ss_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
@sleep_and_retry
@limits(calls=10, period=1)  # SS with key: 10 req/sec (conservative vs 100 max)
def _fetch_ss_citers_with_key(doi: str, api_key: str) -> list[str]:
    """Fetch citing-paper DOIs from SemanticScholar with an API key."""
    return _do_ss_citers_request(doi, api_key=api_key)


def _do_ss_citers_request(doi: str, api_key: str | None) -> list[str]:
    """Execute the SemanticScholar incoming-citations HTTP request.

    Args:
        doi: Clean DOI string (no https://doi.org/ prefix).
        api_key: Optional SS API key.

    Returns:
        List of citing DOI strings (stripped).

    Raises:
        requests.exceptions.RequestException: On HTTP errors.
    """
    url = SS_CITATIONS_URL.format(doi=urllib.parse.quote(doi, safe="/"))
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {"fields": "externalIds", "limit": 500}

    resp = requests.get(url, headers=headers, params=params, timeout=15)

    if resp.status_code == 404:
        logger.debug(f"SS: paper not found for DOI {doi}")
        return []

    resp.raise_for_status()
    data = resp.json().get("data") or []

    result = []
    for item in data:
        citing_ids = item.get("citingPaper", {}).get("externalIds") or {}
        citing_doi = citing_ids.get("DOI")
        if citing_doi:
            result.append(citing_doi.strip())

    return result


def fetch_citers_ss(doi: str, api_key: str | None = None) -> list[str]:
    """Return list of DOIs that cite *doi* via SemanticScholar.

    Args:
        doi: DOI string (with or without https://doi.org/ prefix).
        api_key: Optional SemanticScholar API key for higher rate limits.

    Returns:
        List of citing DOI strings, or empty list if not found / error.
    """
    clean_doi = doi.replace("https://doi.org/", "").strip()
    try:
        if api_key:
            return _fetch_ss_citers_with_key(clean_doi, api_key) or []
        else:
            return _fetch_ss_citers_no_key(clean_doi) or []
    except Exception as e:
        logger.warning(f"SS citers fetch failed for DOI {clean_doi}: {e}")
        return []


def _fetch_citers_oc(doi: str) -> list[str]:
    """Return list of DOIs citing *doi* from OpenCitations.

    Args:
        doi: Clean DOI string.

    Returns:
        List of citing DOI strings.
    """
    success, response, _ = getCitations(doi)
    if not success or response is None:
        return []
    try:
        data = response.json()
        return [
            item["citing"].replace("https://doi.org/", "").strip()
            for item in data
            if item.get("citing")
        ]
    except (ValueError, KeyError) as e:
        logger.warning(f"OC citers parse error for DOI {doi}: {e}")
        return []


def fetch_citers_batch(
    dois: list[str],
    api_key: str | None = None,
    cache_path: str | None = None,
    fallback_opencitations: bool = True,
) -> dict[str, list[str]]:
    """Fetch citing-paper DOI lists for many papers with cache and fallback.

    Fallback chain per paper:
      1. SemanticScholar /citations (primary, fast, rich).
      2. OpenCitations /citations/{doi} (fallback; CrossRef has no free
         citedBy endpoint).

    Results are cached to a JSON file for resumability.

    Args:
        dois: List of DOI strings to look up.
        api_key: Optional SemanticScholar API key (enables 10 req/sec vs 1).
        cache_path: Path to JSON cache file. Pass None to skip caching.
        fallback_opencitations: If True, use OpenCitations when SS returns
            an empty list.

    Returns:
        Dict mapping each DOI to its list of citing DOIs.
    """
    cache: dict[str, list[str]] = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
            logger.info(f"Loaded {len(cache)} cached citer entries from {cache_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load citers cache {cache_path}: {e}")

    results: dict[str, list[str]] = {}
    pending = [d for d in dois if d not in cache]

    logger.info(
        f"Fetching citers: {len(dois)} DOIs total, "
        f"{len(cache)} cached, {len(pending)} to fetch"
    )

    for i, doi in enumerate(pending, 1):
        clean_doi = doi.replace("https://doi.org/", "").strip()
        if not clean_doi:
            results[doi] = []
            continue

        # Tier 1: SemanticScholar
        citers = fetch_citers_ss(clean_doi, api_key=api_key)

        # Tier 2: OpenCitations
        if not citers and fallback_opencitations:
            logger.debug(f"SS empty for {clean_doi}, trying OpenCitations...")
            citers = _fetch_citers_oc(clean_doi)
            if citers:
                logger.debug(f"OC found {len(citers)} citers for {clean_doi}")

        results[doi] = citers

        if cache_path and i % 10 == 0:
            _save_cache(cache_path, {**cache, **results})

        if i % 50 == 0 or i == len(pending):
            logger.info(f"  Progress: {i}/{len(pending)} fetched")

    combined = {**cache, **results}

    if cache_path:
        _save_cache(cache_path, combined)

    return {doi: combined.get(doi, []) for doi in dois}
