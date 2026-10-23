"""Fetch metadata for candidate DOIs via Semantic Scholar batch API.

Uses the POST /paper/batch endpoint to retrieve metadata for up to
500 papers per request, then converts each to the internal format
using SemanticScholartoZoteroFormat.
"""

import logging
import urllib.parse

import requests
from ratelimit import limits, sleep_and_retry

from scilex.crawlers.aggregate import SemanticScholartoZoteroFormat

logger = logging.getLogger(__name__)

SS_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"

SS_FIELDS = (
    "title,abstract,authors,url,DOI,publicationTypes,publicationVenue,"
    "publicationDate,journal,venue,externalIds,openAccessPdf,"
    "citationCount,referenceCount,paperId"
)

# Maximum DOIs per batch request (SS API limit)
BATCH_SIZE = 500


@sleep_and_retry
@limits(calls=1, period=1)
def _batch_request_no_key(ids: list[str]) -> list[dict]:
    """POST batch request without API key (1 req/sec)."""
    return _do_batch_request(ids, api_key=None)


@sleep_and_retry
@limits(calls=10, period=1)
def _batch_request_with_key(ids: list[str], api_key: str) -> list[dict]:
    """POST batch request with API key (10 req/sec)."""
    return _do_batch_request(ids, api_key=api_key)


def _do_batch_request(ids: list[str], api_key: str | None) -> list[dict]:
    """Execute the SS /paper/batch POST request.

    Args:
        ids: List of paper identifiers (e.g. ``["DOI:10.1234/..."]``).
        api_key: Optional SS API key.

    Returns:
        List of paper dicts (may contain None for not-found papers).
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    resp = requests.post(
        SS_BATCH_URL,
        headers=headers,
        params={"fields": SS_FIELDS},
        json={"ids": ids},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_metadata_batch(
    candidate_dois: list[str],
    api_key: str | None = None,
) -> list[dict]:
    """Fetch metadata for candidate DOIs and convert to internal format.

    Args:
        candidate_dois: List of DOI strings to look up.
        api_key: Optional SS API key for higher rate limits.

    Returns:
        List of paper dicts in internal (Zotero-like) format.
        Papers not found by SS are silently skipped.
    """
    results = []
    total = len(candidate_dois)

    for start in range(0, total, BATCH_SIZE):
        batch_dois = candidate_dois[start : start + BATCH_SIZE]
        ids = [f"DOI:{urllib.parse.quote(d, safe='/')}" for d in batch_dois]

        try:
            if api_key:
                raw_papers = _batch_request_with_key(ids, api_key)
            else:
                raw_papers = _batch_request_no_key(ids)
        except requests.exceptions.RequestException as e:
            logger.warning(f"SS batch request failed: {e}")
            continue

        for paper in raw_papers:
            if paper is None:
                continue
            try:
                # Map SS field names for the converter
                if "paperId" in paper and "paper_id" not in paper:
                    paper["paper_id"] = paper["paperId"]
                if "publicationDate" in paper and "publication_date" not in paper:
                    paper["publication_date"] = paper["publicationDate"]
                if "openAccessPdf" in paper:
                    oap = paper["openAccessPdf"]
                    if isinstance(oap, dict) and oap.get("url"):
                        paper["open_access_pdf"] = oap["url"]
                if "authors" not in paper:
                    paper["authors"] = []

                converted = SemanticScholartoZoteroFormat(paper)
                results.append(converted)
            except Exception as e:
                doi = paper.get("DOI", paper.get("externalIds", {}).get("DOI", "?"))
                logger.debug(f"Failed to convert paper {doi}: {e}")

        end = min(start + BATCH_SIZE, total)
        logger.info(f"Fetched {end}/{total} candidates ({len(results)} converted)")

    return results
