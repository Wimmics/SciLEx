import logging

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
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
@limits(calls=10, period=1)
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
@limits(calls=10, period=1)
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
                logging.debug(f"Found {len(citations['cited'])} references for {clean_doi}")
        except (ValueError, KeyError) as e:
            logging.warning(f"Error parsing references JSON for DOI {clean_doi}: {e}")
            stats["ref_status"] = "error"

    return citations, stats


def countCitations(citations):
    return {
        "nb_citations": len(citations["citing"]),
        "nb_cited": len(citations["cited"]),
    }
