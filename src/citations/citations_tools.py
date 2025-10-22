import logging

import requests
from ratelimit import limits, sleep_and_retry

api_citations = "https://opencitations.net/index/coci/api/v1/citations/"
api_references = "https://opencitations.net/index/coci/api/v1/references/"


@sleep_and_retry
@limits(calls=10, period=1)
def getCitations(doi):
    """
    Fetch citation data for a given DOI from OpenCitations API.

    Args:
        doi: The DOI to fetch citations for

    Returns:
        requests.Response or None: The API response, or None if the request failed
    """
    logging.debug(f"Requesting citations for DOI: {doi}")
    try:
        resp = requests.get(api_citations + doi, timeout=30)
        resp.raise_for_status()
        return resp
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while fetching citations for DOI: {doi}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for citations DOI {doi}: {e}")
    return None


@sleep_and_retry
@limits(calls=10, period=1)
def getReferences(doi):
    """
    Fetch reference data for a given DOI from OpenCitations API.

    Args:
        doi: The DOI to fetch references for

    Returns:
        requests.Response or None: The API response, or None if the request failed
    """
    logging.debug(f"Requesting references for DOI: {doi}")
    try:
        resp = requests.get(api_references + doi, timeout=30)
        resp.raise_for_status()
        return resp
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while fetching references for DOI: {doi}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed for references DOI {doi}: {e}")
    return None


def getRefandCitFormatted(doi_str):
    """
    Fetch both citations and references for a DOI and return formatted results.

    Args:
        doi_str: The DOI string (may include https://doi.org/ prefix)

    Returns:
        dict: Dictionary with 'citing' and 'cited' lists of DOIs
    """
    clean_doi = doi_str.replace("https://doi.org/", "")
    citation = getCitations(clean_doi)
    reference = getReferences(clean_doi)
    citations = {"citing": [], "cited": []}

    # Process citations
    if citation is not None:
        try:
            resp_cit = citation.json()
            if len(resp_cit) > 0:
                for cit in resp_cit:
                    citations["citing"].append(cit["citing"])
        except (ValueError, KeyError) as e:
            logging.error(f"Error parsing citations JSON for DOI {clean_doi}: {e}")

    # Process references
    if reference is not None:
        try:
            resp_ref = reference.json()
            if len(resp_ref) > 0:
                for ref in resp_ref:
                    citations["cited"].append(ref["cited"])
                logging.debug(f"Found {len(citations['cited'])} references for {clean_doi}")
        except (ValueError, KeyError) as e:
            logging.error(f"Error parsing references JSON for DOI {clean_doi}: {e}")

    return citations


def countCitations(citations):
    return {
        "nb_citations": len(citations["citing"]),
        "nb_cited": len(citations["cited"]),
    }
