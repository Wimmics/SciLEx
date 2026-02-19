import logging

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

api_citations = "https://opencitations.net/index/coci/api/v1/citations/"
api_references = "https://opencitations.net/index/coci/api/v1/references/"


@retry(
    retry=retry_if_exception_type(
        (requests.exceptions.Timeout, requests.exceptions.RequestException)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False,
)
@sleep_and_retry
@limits(calls=1, period=1)  # OpenCitations public API limit: 1 req/sec
def getCitations(doi):
    """
    Fetch citation data for a given DOI from OpenCitations API.

    Args:
        doi: The DOI to fetch citations for

    Returns:
        tuple: (success: bool, data: Response|None, error_type: str)
            - success: True if request succeeded
            - data: Response object if success, None otherwise
            - error_type: "timeout", "error", or "success"
    """
    logging.debug(f"Requesting citations for DOI: {doi}")
    try:
        resp = requests.get(api_citations + doi, timeout=10)  # Reduced from 30s
        resp.raise_for_status()
        return (True, resp, "success")
    except requests.exceptions.Timeout:
        logging.warning(f"Timeout while fetching citations for DOI: {doi}")
        return (False, None, "timeout")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Request failed for citations DOI {doi}: {e}")
        return (False, None, "error")


@retry(
    retry=retry_if_exception_type(
        (requests.exceptions.Timeout, requests.exceptions.RequestException)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False,
)
@sleep_and_retry
@limits(calls=1, period=1)  # OpenCitations public API limit: 1 req/sec
def getReferences(doi):
    """
    Fetch reference data for a given DOI from OpenCitations API.

    Args:
        doi: The DOI to fetch references for

    Returns:
        tuple: (success: bool, data: Response|None, error_type: str)
            - success: True if request succeeded
            - data: Response object if success, None otherwise
            - error_type: "timeout", "error", or "success"
    """
    logging.debug(f"Requesting references for DOI: {doi}")
    try:
        resp = requests.get(api_references + doi, timeout=10)  # Reduced from 30s
        resp.raise_for_status()
        return (True, resp, "success")
    except requests.exceptions.Timeout:
        logging.warning(f"Timeout while fetching references for DOI: {doi}")
        return (False, None, "timeout")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Request failed for references DOI {doi}: {e}")
        return (False, None, "error")


def getRefandCitFormatted(doi_str):
    """
    Fetch both citations and references for a DOI and return formatted results.

    Args:
        doi_str: The DOI string (may include https://doi.org/ prefix)

    Returns:
        tuple: (citations_dict, stats_dict)
            - citations_dict: Dictionary with 'citing' and 'cited' lists of DOIs
            - stats_dict: Dictionary with 'cit_status' and 'ref_status' ('success', 'timeout', or 'error')
    """
    clean_doi = doi_str.replace("https://doi.org/", "")
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
    retry=retry_if_exception_type(
        (requests.exceptions.Timeout, requests.exceptions.RequestException)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
@sleep_and_retry
@limits(calls=3, period=1)  # Conservative: 3 req/sec (each covers ~20 DOIs)
def getCrossRefCitationsBatch(dois, mailto=None):
    """Fetch citation counts for multiple DOIs in a single CrossRef API call.

    Uses the CrossRef works endpoint with DOI filter and field selection
    to retrieve citation and reference counts in bulk. Much faster than
    per-DOI lookups via OpenCitations (~60 DOIs/sec vs 1 DOI/sec).

    Args:
        dois: List of DOI strings (max ~20 per batch for URL length safety).
        mailto: Email for CrossRef polite pool (10 req/sec vs 5 req/sec).

    Returns:
        dict: {doi_lowercase: (citation_count, reference_count)} for found DOIs.
            DOIs not found in CrossRef are simply omitted from the result.
    """
    if not dois:
        return {}

    filter_str = ",".join(f"doi:{doi}" for doi in dois)
    url = (
        f"https://api.crossref.org/works?"
        f"filter={filter_str}"
        f"&select=DOI,is-referenced-by-count,references-count"
        f"&rows={len(dois)}"
    )
    if mailto:
        url += f"&mailto={mailto}"

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    items = resp.json()["message"]["items"]

    return {
        item["DOI"].lower(): (
            item.get("is-referenced-by-count", 0),
            item.get("references-count", 0),
        )
        for item in items
    }


def getCrossRefCitation(doi, mailto=None):
    """Fetch citation counts for a single DOI from CrossRef.

    Wrapper around getCrossRefCitationsBatch for per-DOI usage in the
    four-tier citation pipeline (Cache -> SS -> CrossRef -> OpenCitations).

    Args:
        doi: DOI string.
        mailto: Email for CrossRef polite pool.

    Returns:
        tuple: (citation_count, reference_count) or None if DOI not found.
    """
    try:
        result = getCrossRefCitationsBatch([doi], mailto=mailto)
        doi_lower = doi.lower()
        if doi_lower in result:
            return result[doi_lower]
    except Exception as e:
        logging.debug(f"CrossRef lookup failed for DOI {doi}: {e}")
    return None
