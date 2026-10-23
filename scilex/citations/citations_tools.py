import logging
from urllib.parse import quote

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from scilex.constants import normalize_doi

api_citations = "https://opencitations.net/index/coci/api/v1/citations/"
api_references = "https://opencitations.net/index/coci/api/v1/references/"

_OC_ENDPOINTS = {"citations": api_citations, "references": api_references}
_MAX_RETRY_AFTER_SECONDS = 60
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_backoff = wait_exponential(multiplier=1, min=2, max=10)


def is_retryable_http_error(exc: BaseException) -> bool:
    """Retry only transient failures: timeouts, connection errors, 429 and 5xx."""
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        return (
            response is not None
            and getattr(response, "status_code", None) in _RETRYABLE_STATUS_CODES
        )
    return isinstance(
        exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    )


def wait_retry_after_or_backoff(retry_state) -> float:
    """Honor a numeric Retry-After header (capped at 60 s), else back off."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        retry_after = float(headers.get("Retry-After"))
    except (TypeError, ValueError):
        return _backoff(retry_state)
    return min(max(retry_after, 0.0), _MAX_RETRY_AFTER_SECONDS)


@retry(
    retry=retry_if_exception(is_retryable_http_error),
    stop=stop_after_attempt(3),
    wait=wait_retry_after_or_backoff,
    reraise=True,
)
@sleep_and_retry
@limits(calls=1, period=1)  # OpenCitations public API limit: 1 req/sec
def _oc_request(kind, doi):
    """Perform one OpenCitations GET; raises on any HTTP/network failure."""
    logging.debug(f"Requesting {kind} for DOI: {doi}")
    resp = requests.get(_OC_ENDPOINTS[kind] + quote(doi, safe="/"), timeout=10)
    resp.raise_for_status()
    return resp


def _oc_get(kind, doi):
    """Fetch citations or references for a DOI from OpenCitations.

    Transient failures (timeouts, connection errors, 429, 5xx) are retried up to
    3 times; other 4xx errors fail immediately.

    Args:
        kind: "citations" or "references"
        doi: DOI (any common spelling; normalized before the request)

    Returns:
        tuple: (success: bool, data: Response|None, error_type: str)
            error_type is "success", "timeout" or "error".
    """
    clean_doi = normalize_doi(doi)
    if clean_doi is None:
        return (False, None, "error")
    try:
        return (True, _oc_request(kind, clean_doi), "success")
    except requests.exceptions.Timeout:
        logging.warning(f"Timeout while fetching {kind} for DOI: {clean_doi}")
        return (False, None, "timeout")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Request failed for {kind} DOI {clean_doi}: {e}")
        return (False, None, "error")


def getCitations(doi):
    """Fetch citation data for a DOI from OpenCitations.

    Returns:
        tuple: (success: bool, data: Response|None, error_type: str)
            error_type is "success", "timeout" or "error".
    """
    return _oc_get("citations", doi)


def getReferences(doi):
    """Fetch reference data for a DOI from OpenCitations.

    Returns:
        tuple: (success: bool, data: Response|None, error_type: str)
            error_type is "success", "timeout" or "error".
    """
    return _oc_get("references", doi)


def getRefandCitFormatted(doi_str):
    """
    Fetch both citations and references for a DOI and return formatted results.

    Args:
        doi_str: The DOI string (any common spelling, e.g. with https://doi.org/)

    Returns:
        tuple: (citations_dict, stats_dict)
            - citations_dict: Dictionary with 'citing' and 'cited' lists of DOIs
            - stats_dict: Dictionary with 'cit_status' and 'ref_status' ('success', 'timeout', or 'error')
    """
    clean_doi = normalize_doi(doi_str)
    if clean_doi is None:
        return {"citing": [], "cited": []}, {
            "cit_status": "error",
            "ref_status": "error",
        }
    success_cit, citation, cit_status = getCitations(clean_doi)
    success_ref, reference, ref_status = getReferences(clean_doi)

    citations = {"citing": [], "cited": []}
    stats = {"cit_status": cit_status, "ref_status": ref_status}

    # Process citations
    if success_cit and citation is not None:
        try:
            resp_cit = citation.json()
            if len(resp_cit) > 0:
                for cit in resp_cit:
                    citations["citing"].append(cit["citing"])
        except (ValueError, KeyError) as e:
            logging.warning(f"Error parsing citations JSON for DOI {clean_doi}: {e}")
            stats["cit_status"] = "error"

    # Process references
    if success_ref and reference is not None:
        try:
            resp_ref = reference.json()
            if len(resp_ref) > 0:
                for ref in resp_ref:
                    citations["cited"].append(ref["cited"])
                logging.debug(
                    f"Found {len(citations['cited'])} references for {clean_doi}"
                )
        except (ValueError, KeyError) as e:
            logging.warning(f"Error parsing references JSON for DOI {clean_doi}: {e}")
            stats["ref_status"] = "error"

    return citations, stats


def countCitations(citations):
    return {
        "nb_citations": len(citations["citing"]),
        "nb_cited": len(citations["cited"]),
    }


# ============================================================================
# CrossRef Batch Citation Lookup
# ============================================================================

CROSSREF_BATCH_SIZE = 20
"""Max DOIs per CrossRef batch request (URL length safety)."""


@retry(
    retry=retry_if_exception(is_retryable_http_error),
    stop=stop_after_attempt(3),
    wait=wait_retry_after_or_backoff,
    reraise=True,
)
@sleep_and_retry
@limits(calls=3, period=1)  # Conservative: 3 req/sec (each covers ~20 DOIs)
def getCrossRefCitationsBatch(dois, mailto=None):
    """Fetch citation counts for multiple DOIs in a single CrossRef API call.

    Uses the CrossRef works endpoint with DOI filter and field selection
    to retrieve citation and reference counts in bulk. Much faster than
    per-DOI lookups via OpenCitations (~60 DOIs/sec vs 1 DOI/sec).

    Transient errors (timeouts, connection errors, 429, 5xx) are retried. On a
    400 response the batch is bisected so one malformed DOI only loses itself;
    a lone DOI rejected with 400 is omitted from the result.

    Args:
        dois: List of DOI strings (max ~20 per batch for URL length safety).
        mailto: Email for CrossRef polite pool (10 req/sec vs 5 req/sec).

    Returns:
        dict: {doi_lowercase: (citation_count, reference_count)} for found DOIs.
            DOIs not found in CrossRef are simply omitted from the result.
    """
    clean_dois = [d for d in map(normalize_doi, dois or []) if d is not None]
    if not clean_dois:
        return {}

    filter_str = ",".join(f"doi:{quote(doi, safe='/')}" for doi in clean_dois)
    url = (
        f"https://api.crossref.org/works?"
        f"filter={filter_str}"
        f"&select=DOI,is-referenced-by-count,references-count"
        f"&rows={len(clean_dois)}"
    )
    if mailto:
        url += f"&mailto={mailto}"

    resp = requests.get(url, timeout=30)
    if resp.status_code == 400:
        if len(clean_dois) == 1:
            logging.warning(f"CrossRef rejected DOI {clean_dois[0]} (400); skipping")
            return {}
        middle = len(clean_dois) // 2
        logging.debug(f"CrossRef 400 on batch of {len(clean_dois)}; bisecting")
        results = getCrossRefCitationsBatch(clean_dois[:middle], mailto=mailto)
        results.update(getCrossRefCitationsBatch(clean_dois[middle:], mailto=mailto))
        return results
    resp.raise_for_status()
    items = resp.json()["message"]["items"]

    return {
        item["DOI"].lower(): (
            item.get("is-referenced-by-count", 0),
            item.get("references-count", 0),
        )
        for item in items
    }
