#!/usr/bin/env python3
"""
Created on Fri Feb 10 10:57:49 2023

@author: cringwal
         aollagnier

@version: 1.0.1
"""

import logging
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from pandas.core.dtypes.inference import is_dict_like

from src.constants import MISSING_VALUE, is_valid


def safe_get(obj, key, default=None):
    """Safely get a value from a dictionary-like object, filtering out empty strings."""
    if isinstance(obj, dict) and key in obj and obj[key] != "":
        return obj[key]
    return default


def safe_has_key(obj, key):
    """Safely check if an object has a key."""
    return isinstance(obj, dict) and key in obj


def clean_doi(doi_value):
    """
    Extract clean DOI from URL-formatted DOI or return as-is.

    Converts: "https://doi.org/10.1007/..." → "10.1007/..."
    Keeps: "10.1007/..." → "10.1007/..."

    Args:
        doi_value: DOI string (may be URL-formatted or clean)

    Returns:
        Clean DOI string without URL prefix, or MISSING_VALUE if invalid
    """
    if not is_valid(doi_value):
        return MISSING_VALUE

    doi_str = str(doi_value).strip()

    # Remove common DOI URL prefixes
    prefixes = [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ]

    for prefix in prefixes:
        if doi_str.lower().startswith(prefix.lower()):
            return doi_str[len(prefix) :]

    # Already clean or unknown format
    return doi_str


############
# FUNCTION FOR AGGREGATIONS OF DATA
############


def getquality(df_row, column_names):
    """Calculate quality score based on weighted field importance.

    Field importance weights:
    - Critical fields (DOI, title, authors, date): 5 points each
    - Important fields (abstract, journal, volume, issue, publisher): 3 points each
    - Nice-to-have fields (pages, rights, language, url, etc.): 1 point each

    Special rules:
    - Penalize Google Scholar records without DOI (-2 points)
    - Bonus for having both volume and issue (+1 point)
    """
    # Define field importance weights
    critical_fields = {"DOI", "title", "authors", "date"}
    important_fields = {
        "abstract",
        "journalAbbreviation",
        "volume",
        "issue",
        "publisher",
    }
    # All other fields get weight 1

    quality = 0
    has_volume = False
    has_issue = False
    is_google_scholar = False
    has_doi = False

    for col in column_names:
        value = df_row.get(col)
        if is_valid(value):
            # Apply weighted scoring
            if col in critical_fields:
                quality += 5
                if col == "DOI":
                    has_doi = True
            elif col in important_fields:
                quality += 3
                if col == "volume":
                    has_volume = True
                elif col == "issue":
                    has_issue = True
            else:
                quality += 1

            # Track if this is a Google Scholar record
            if col == "archive" and "GoogleScholar" in str(value):
                is_google_scholar = True

    # Apply bonuses and penalties
    if has_volume and has_issue:
        quality += 1  # Bonus for complete bibliographic info

    if is_google_scholar and not has_doi:
        quality = max(0, quality - 2)  # Penalize GScholar without DOI

    return quality


def filter_data(df_input, filter_):
    return df_input[df_input["abstract"].str.contains("triple", case=False, na=False)]


def _find_best_duplicate_index(duplicates_df, column_names):
    """Find the best duplicate record, preferring most recent then quality."""
    quality_list = []
    year_list = []

    for i in range(len(duplicates_df)):
        idx = duplicates_df.index[i]
        record = duplicates_df.loc[idx]

        # Get quality score
        qual = getquality(record, column_names)
        quality_list.append(qual)

        # Extract year from date field
        year = 0  # Default for missing/invalid years
        date_str = record.get("date", "")
        if is_valid(date_str):
            try:
                # Try to extract year from ISO date or year string
                if isinstance(date_str, str):
                    # Handle ISO dates (YYYY-MM-DD) or just year (YYYY)
                    year_match = date_str.split("-")[0]
                    if year_match.isdigit():
                        year = int(year_match)
            except (ValueError, AttributeError, IndexError):
                year = 0
        year_list.append(year)

    # Find best duplicate: prioritize most recent year, then quality
    best_idx = 0
    best_year = year_list[0]
    best_quality = quality_list[0]

    for i in range(1, len(duplicates_df)):
        current_year = year_list[i]
        current_quality = quality_list[i]

        # Prefer most recent year (higher year wins)
        if current_year > best_year:
            best_idx = i
            best_year = current_year
            best_quality = current_quality
        # If same year, prefer higher quality
        elif current_year == best_year and current_quality > best_quality:
            best_idx = i
            best_quality = current_quality

    return best_idx


def _merge_duplicate_archives(archive_list, chosen_archive):
    """Merge archive list with chosen archive marked with asterisk."""
    archive_str = ";".join(archive_list)
    return archive_str.replace(chosen_archive, chosen_archive + "*")


def _fill_missing_values(row, column_values_dict, column_names):
    """Fill missing values in row from alternative duplicates."""
    for col in column_names:
        if not is_valid(row.get(col)):
            row[col] = MISSING_VALUE

        if row[col] == MISSING_VALUE:
            for value in column_values_dict[col]:
                if is_valid(value):
                    row[col] = value
                    break
    return row


def deduplicate(df_input):
    """
    Remove duplicate papers by DOI and exact title matching.

    Args:
        df_input: Input DataFrame

    Returns:
        Deduplicated DataFrame
    """
    df_output = df_input.copy()
    check_columns = ["DOI", "title"]
    column_names = list(df_output.columns.values)

    for col in check_columns:
        if col not in df_output.columns:
            continue

        # Find duplicates - exclude missing values
        non_na_df = df_output[df_output[col].apply(is_valid)]
        duplicate_counts = non_na_df.groupby([col])[col].count()
        duplicate_values = duplicate_counts[duplicate_counts > 1].index

        if len(duplicate_values) == 0:
            continue

        logging.info(f"Found {len(duplicate_values)} duplicates by {col}")

        for dup_value in duplicate_values:
            duplicates_temp = df_output[df_output[col] == dup_value]
            column_values = {key: [] for key in column_names}
            archive_list = []

            # Collect data from all duplicates
            for idx in duplicates_temp.index:
                archive_list.append(str(df_output.loc[idx]["archive"]))
                for col_name in column_names:
                    value = df_output.loc[idx, col_name]
                    column_values[col_name].append(
                        MISSING_VALUE if not is_valid(value) else value
                    )

            # Find best duplicate
            best_idx = _find_best_duplicate_index(duplicates_temp, column_names)
            best_record = duplicates_temp.iloc[best_idx].copy()
            chosen_archive = str(best_record["archive"])

            # Update archives field
            best_record["archive"] = _merge_duplicate_archives(
                archive_list, chosen_archive
            )

            # Fill missing values from other duplicates
            best_record = _fill_missing_values(best_record, column_values, column_names)

            # Replace duplicates with merged record
            df_output = df_output.drop(duplicates_temp.index)
            df_output = pd.concat(
                [df_output, best_record.to_frame().T], ignore_index=True
            )

    return df_output


def SemanticScholartoZoteroFormat(row):
    # print(">>SemanticScholartoZoteroFormat")
    # bookSection?
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }
    zotero_temp["archive"] = "SemanticScholar"
    #### publicationTypes is a list Zotero only take one value

    if (
        "publicationTypes" in row
        and row["publicationTypes"] != ""
        and row["publicationTypes"] is not None
    ):
        if len(row["publicationTypes"]) == 1:
            if row["publicationTypes"][0] == "JournalArticle":
                zotero_temp["itemType"] = "journalArticle"
            elif (
                row["publicationTypes"][0] == "Conference"
                or row["publicationTypes"][0] == "Conferences"
            ):
                zotero_temp["itemType"] = "conferencePaper"
            elif row["publicationTypes"][0] == "Book":
                zotero_temp["itemType"] = "book"

                # print("NEED TO ADD FOLLOWING TYPE >",row["publicationTypes"][0])

        if len(row["publicationTypes"]) > 1:
            if "Book" in row["publicationTypes"]:
                zotero_temp["itemType"] = "book"
            elif "Conference" in row["publicationTypes"]:
                zotero_temp["itemType"] = "conferencePaper"
            elif "JournalArticle" in row["publicationTypes"]:
                zotero_temp["itemType"] = "journalArticle"
            else:
                pass
                # print("NEED TO ADD FOLLOWING TYPES >",row["publicationTypes"])

    # Handle publicationVenue (newer, richer field from Semantic Scholar API)
    # Priority: publicationVenue > venue (publicationVenue has more structured data)
    if safe_get(row, "publicationVenue"):
        pub_venue = row["publicationVenue"]
        venue_type = safe_get(pub_venue, "type")
        venue_name = safe_get(pub_venue, "name")

        # Extract publisher from publicationVenue if available
        if safe_get(pub_venue, "publisher"):
            zotero_temp["publisher"] = pub_venue["publisher"]

        # Extract ISSN as series if available
        if safe_get(pub_venue, "issn"):
            zotero_temp["serie"] = pub_venue["issn"]

        if venue_type:
            if venue_type == "journal":
                zotero_temp["itemType"] = "journalArticle"
                if venue_name:
                    zotero_temp["journalAbbreviation"] = venue_name
            elif venue_type == "conference":
                zotero_temp["itemType"] = "conferencePaper"
                if venue_name:
                    zotero_temp["conferenceName"] = venue_name

    # Fallback to older venue field if publicationVenue not available
    if safe_get(row, "venue"):
        venue_type = safe_get(row["venue"], "type")
        venue_name = safe_get(row["venue"], "name")
        if venue_type:
            if venue_type == "journal":
                zotero_temp["itemType"] = "journalArticle"
                if venue_name:
                    zotero_temp["journalAbbreviation"] = venue_name
            elif venue_type == "conference":
                zotero_temp["itemType"] = "conferencePaper"
                if venue_name:
                    zotero_temp["conferenceName"] = venue_name

    if safe_get(row, "journal"):
        journal_pages = safe_get(row["journal"], "pages")
        journal_name = safe_get(row["journal"], "name")
        journal_volume = safe_get(row["journal"], "volume")

        if journal_pages:
            zotero_temp["pages"] = journal_pages
            if zotero_temp["itemType"] == "book":
                zotero_temp["itemType"] = "bookSection"
        if not is_valid(zotero_temp.get("itemType")):
            # if the journal field is defined but we dont know the itemType yet (for ex Reviews), we assume it's journal article
            zotero_temp["itemType"] = "journalArticle"
        if journal_name:
            zotero_temp["journalAbbreviation"] = journal_name
        if journal_volume:
            zotero_temp["volume"] = journal_volume

    if not is_valid(zotero_temp.get("itemType")):
        # default to Manuscript type to make sure there is a type, otherwise the push to Zotero doesn't work
        zotero_temp["itemType"] = "Manuscript"

    if row["title"]:
        zotero_temp["title"] = row["title"]
    auth_list = []
    for auth in row["authors"]:
        if auth["name"] != "" and auth["name"] is not None:
            auth_list.append(auth["name"])
    if len(auth_list) > 0:
        zotero_temp["authors"] = ";".join(auth_list)

    if safe_get(row, "abstract"):
        zotero_temp["abstract"] = row["abstract"]

    paper_id = safe_get(row, "paper_id")
    if paper_id:
        zotero_temp["archiveID"] = paper_id

    if safe_get(row, "publication_date"):
        zotero_temp["date"] = row["publication_date"]

    if safe_get(row, "DOI"):
        zotero_temp["DOI"] = clean_doi(row["DOI"])

    if safe_get(row, "url"):
        zotero_temp["url"] = row["url"]

    if safe_get(row, "open_access_pdf"):
        zotero_temp["pdf_url"] = row["open_access_pdf"]
        zotero_temp["rights"] = "open_access"

    # Preserve Semantic Scholar citation data for fallback
    if safe_get(row, "citationCount"):
        zotero_temp["ss_citation_count"] = row["citationCount"]

    if safe_get(row, "referenceCount"):
        zotero_temp["ss_reference_count"] = row["referenceCount"]

    return zotero_temp


def IstextoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }
    # Genre pas clair
    zotero_temp["archive"] = "Istex"
    if row["genre"] != "" and len(row["genre"]) == 1:
        if row["genre"][0] == "research-article":
            zotero_temp["itemType"] = "journalArticle"
        if row["genre"][0] == "conference":
            zotero_temp["itemType"] = "conferencePaper"
        if row["genre"][0] == "article":
            zotero_temp["itemType"] = "journalArticle"  # Fixed: was bookSection
        if row["genre"][0] == "book-chapter":
            zotero_temp["itemType"] = "bookSection"

    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]
    auth_list = []
    for auth in row["author"]:
        if auth["name"] != "" and auth["name"] is not None:
            auth_list.append(auth["name"])

    if len(auth_list) > 0:
        zotero_temp["authors"] = ";".join(auth_list)

    # NO ABSTRACT ?
    if "abstract" in row and row["abstract"] != "" and row["abstract"] is not None:
        zotero_temp["abstract"] = row["abstract"]

    if row["arkIstex"] != "" and row["arkIstex"] is not None:
        zotero_temp["archiveID"] = row["arkIstex"]

    if row["publicationDate"] != "" and row["publicationDate"] is not None:
        zotero_temp["date"] = row["publicationDate"]

    if ("doi" in row) and (len(row["doi"]) > 0):
        list_doi = []
        for doi in row["doi"]:
            list_doi.append(clean_doi(doi))
        zotero_temp["DOI"] = ";".join(list_doi)

    # Extract language - allow multiple languages, take first one
    if "language" in row and row["language"]:
        if isinstance(row["language"], list) and len(row["language"]) > 0:
            zotero_temp["language"] = row["language"][0]
        elif isinstance(row["language"], str):
            zotero_temp["language"] = row["language"]

    if (
        "series" in row
        and isinstance(row["series"], dict)
        and row["series"].get("title")
    ):
        zotero_temp["serie"] = row["series"]["title"]
    if "host" in row:
        if "volume" in row["host"]:
            zotero_temp["volume"] = row["host"]["volume"]

        if "issue" in row["host"]:
            zotero_temp["issue"] = row["host"]["issue"]

        if "title" in row["host"]:
            zotero_temp["journalAbbreviation"] = row["host"]["title"]

        if "pages" in row["host"] and isinstance(row["host"]["pages"], dict):
            pages_obj = row["host"]["pages"]
            # Fix typo: was checking "fist" but accessing "first"
            if pages_obj.get("first") and pages_obj.get("last"):
                zotero_temp["pages"] = f"{pages_obj['first']}-{pages_obj['last']}"

        # Extract publisher - allow multiple publisherIds, take first one
        if "publisherId" in row["host"] and row["host"]["publisherId"]:
            publisher_ids = row["host"]["publisherId"]
            if isinstance(publisher_ids, list) and len(publisher_ids) > 0:
                zotero_temp["publisher"] = publisher_ids[0]
            elif isinstance(publisher_ids, str):
                zotero_temp["publisher"] = publisher_ids

        # Also try to get publisher from host.publisher if publisherId is missing
        if not is_valid(zotero_temp.get("publisher")) and "publisher" in row["host"]:
            if is_valid(row["host"]["publisher"]):
                zotero_temp["publisher"] = row["host"]["publisher"]
    # NO URL ?
    if "url" in row and row["url"] != "" and row["url"] is not None:
        zotero_temp["url"] = row["url"]

    if "accessCondition" in row:
        if row["accessCondition"] != "" and row["accessCondition"] is not None:
            if (
                row["accessCondition"]["contentType"] != ""
                and row["accessCondition"]["contentType"] is not None
            ):
                zotero_temp["rights"] = row["accessCondition"]["contentType"]

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def ArxivtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }
    zotero_temp["archive"] = "Arxiv"
    # arXiv is always open access
    zotero_temp["rights"] = "open_access"
    # Set publisher for arXiv preprints
    zotero_temp["publisher"] = "arXiv"

    if row["abstract"] != "" and row["abstract"] is not None:
        zotero_temp["abstract"] = row["abstract"]
    if row["authors"] != "" and row["authors"] is not None:
        zotero_temp["authors"] = ";".join(row["authors"])
    if row["doi"] != "" and row["doi"] is not None:
        zotero_temp["DOI"] = clean_doi(row["doi"])
    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]
    if row["id"] != "" and row["id"] is not None:
        zotero_temp["archiveID"] = row["id"]
        # Construct URL from arXiv ID (e.g., "2301.12345" -> "https://arxiv.org/abs/2301.12345")
        arxiv_id = row["id"]
        # Handle full URLs or just IDs
        if arxiv_id.startswith("http"):
            zotero_temp["url"] = arxiv_id
        else:
            # Clean the ID if it contains the full path
            if "/" in arxiv_id:
                arxiv_id = arxiv_id.split("/")[-1]
            zotero_temp["url"] = f"https://arxiv.org/abs/{arxiv_id}"
            # Generate PDF URL
            zotero_temp["pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    if row["published"] != "" and row["published"] is not None:
        zotero_temp["date"] = row["published"]

    # Extract categories for journalAbbreviation (e.g., "cs.AI, cs.CL")
    if "categories" in row and row["categories"]:
        if isinstance(row["categories"], list):
            zotero_temp["journalAbbreviation"] = ", ".join(row["categories"])
        elif isinstance(row["categories"], str):
            zotero_temp["journalAbbreviation"] = row["categories"]

    # Determine itemType based on journal field
    # If journal metadata exists, paper was published (journal article)
    # Otherwise, it's a preprint
    if row["journal"] != "" and row["journal"] is not None:
        zotero_temp["journalAbbreviation"] = row["journal"]
        zotero_temp["itemType"] = "journalArticle"
    else:
        zotero_temp["itemType"] = "preprint"

    return zotero_temp


def DBLPtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }
    zotero_temp["archiveID"] = row["@id"]
    row = row["info"]
    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]
    zotero_temp["archive"] = "DBLP"
    zotero_temp["title"] = row["title"]
    zotero_temp["date"] = row["year"]
    auth_list = []
    if "authors" in row:
        if type(row["authors"]["author"]) is dict:
            auth_list.append(row["authors"]["author"]["text"])
        else:
            for auth in row["authors"]["author"]:
                if auth["text"] != "" and auth["text"] is not None:
                    auth_list.append(auth["text"])
    # auth_list.append(row["authors"]["author"]["text"] )
    if len(auth_list) > 0:
        zotero_temp["authors"] = ";".join(auth_list)
    if "doi" in row:
        zotero_temp["DOI"] = clean_doi(row["doi"])
    if "pages" in row:
        zotero_temp["pages"] = row["pages"]

    # Extract volume if available
    if "volume" in row and is_valid(row["volume"]):
        zotero_temp["volume"] = row["volume"]

    # Extract number/issue if available
    if "number" in row and is_valid(row["number"]):
        zotero_temp["issue"] = row["number"]

    # Extract publisher if available
    if "publisher" in row and is_valid(row["publisher"]):
        zotero_temp["publisher"] = row["publisher"]

    if ("access" in row) and (row["access"] != "" and row["access"] is not None):
        zotero_temp["rights"] = row["access"]

    # Safely extract URL
    if "url" in row and is_valid(row["url"]):
        zotero_temp["url"] = row["url"]

    if row["type"] == "Journal Articles":
        zotero_temp["itemType"] = "journalArticle"
        if "venue" in row:
            zotero_temp["journalAbbreviation"] = row["venue"]
    if row["type"] == "Conference and Workshop Papers":
        zotero_temp["itemType"] = "conferencePaper"
        if "venue" in row:
            zotero_temp["conferenceName"] = row["venue"]
    if row["type"] == "Informal Publications":
        zotero_temp["itemType"] = "Manuscript"
    if row["type"] == "Informal and Other Publications":
        zotero_temp["itemType"] = "Manuscript"

        # print("NEED TO ADD FOLLOWING TYPE >",row["type"][0])

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def HALtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }
    zotero_temp["archiveID"] = row["halId_s"]
    zotero_temp["archive"] = "HAL"

    # Extract title (array field)
    if "title_s" in row and row["title_s"]:
        if isinstance(row["title_s"], list) and len(row["title_s"]) > 0:
            zotero_temp["title"] = row["title_s"][0]
        elif isinstance(row["title_s"], str):
            zotero_temp["title"] = row["title_s"]

    # Extract abstract (array field)
    if "abstract_s" in row and row["abstract_s"]:
        if isinstance(row["abstract_s"], list) and len(row["abstract_s"]) > 0:
            zotero_temp["abstract"] = row["abstract_s"][0]
        elif isinstance(row["abstract_s"], str):
            zotero_temp["abstract"] = row["abstract_s"]

    if "bookTitle_s" in row:
        zotero_temp["serie"] = row["bookTitle_s"]

    if "doiId_id" in row:
        zotero_temp["DOI"] = clean_doi(row["doiId_id"])
    if "conferenceTitle_s" in row:
        zotero_temp["conferenceName"] = row["conferenceTitle_s"]

    if "journalTitle_t" in row:
        zotero_temp["journalAbbreviation"] = row["journalTitle_t"]

    # Extract date
    if "submittedDateY_i" in row:
        zotero_temp["date"] = str(row["submittedDateY_i"])

    # Extract volume
    if "volume_s" in row and is_valid(row["volume_s"]):
        zotero_temp["volume"] = row["volume_s"]

    # Extract issue
    if "issue_s" in row and is_valid(row["issue_s"]):
        zotero_temp["issue"] = row["issue_s"]

    # Extract pages
    if "page_s" in row and is_valid(row["page_s"]):
        zotero_temp["pages"] = row["page_s"]

    # Extract publisher
    if "publisher_s" in row and is_valid(row["publisher_s"]):
        if isinstance(row["publisher_s"], list) and len(row["publisher_s"]) > 0:
            zotero_temp["publisher"] = row["publisher_s"][0]
        elif isinstance(row["publisher_s"], str):
            zotero_temp["publisher"] = row["publisher_s"]

    # Construct URL from HAL ID
    if "halId_s" in row and row["halId_s"]:
        zotero_temp["url"] = f"https://hal.science/{row['halId_s']}"

    # Extract PDF URLs from files_s field
    if "files_s" in row and row["files_s"]:
        files = row["files_s"]
        if isinstance(files, list):
            for file_url in files:
                if isinstance(file_url, str) and file_url.endswith(".pdf"):
                    zotero_temp["pdf_url"] = file_url
                    break

    # Extract language
    if "language_s" in row and is_valid(row["language_s"]):
        if isinstance(row["language_s"], list) and len(row["language_s"]) > 0:
            zotero_temp["language"] = row["language_s"][0]
        elif isinstance(row["language_s"], str):
            zotero_temp["language"] = row["language_s"]

    # HAL is open access by default
    zotero_temp["rights"] = "open_access"

    # Extract authors from authFullNameIdHal_fs field
    if "authFullNameIdHal_fs" in row:
        auth_list = []
        for auth in row["authFullNameIdHal_fs"]:
            if auth and auth.strip():
                # Split on "_FacetSep_" separator and take author name
                clean_name = auth.split("_FacetSep_")[0].strip()
                if clean_name:
                    auth_list.append(clean_name)
        if len(auth_list) > 0:
            zotero_temp["authors"] = ";".join(auth_list)

    if row["docType_s"] == "ART":
        zotero_temp["itemType"] = "journalArticle"
        if "venue" in row:
            zotero_temp["journalAbbreviation"] = row["venue"]
    if row["docType_s"] == "COMM":
        zotero_temp["itemType"] = "conferencePaper"
    if row["docType_s"] == "PROCEEDINGS":
        zotero_temp["itemType"] = "conferencePaper"
    if row["docType_s"] == "Informal Publications":
        zotero_temp["itemType"] = "Manuscript"

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def reconstruct_abstract_from_inverted_index(inverted_index):
    """Reconstruct abstract text from OpenAlex's inverted index format.

    Args:
        inverted_index: Dictionary mapping words to their positions
                       e.g., {"word": [0, 5], "another": [1]}

    Returns:
        str: Reconstructed abstract text, or None if empty/invalid

    """
    if not inverted_index:
        return None

    try:
        # Find maximum position to size the word array
        max_position = max(max(positions) for positions in inverted_index.values())
        words = [""] * (max_position + 1)

        # Place each word at its positions
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word

        # Join words with spaces
        return " ".join(words)
    except (ValueError, TypeError, KeyError):
        # Handle malformed inverted index gracefully
        return None


# Abstract must be recomposed...
def OpenAlextoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }

    zotero_temp["archive"] = "OpenAlex"
    zotero_temp["archiveID"] = row["id"]
    zotero_temp["DOI"] = clean_doi(row["doi"])
    zotero_temp["title"] = row["title"]
    zotero_temp["date"] = row["publication_date"]

    # Extract language if available
    if "language" in row and is_valid(row["language"]):
        zotero_temp["language"] = row["language"]

    # Extract URL and PDF URL - prefer best_oa_location, then primary_location, then construct from DOI
    if "best_oa_location" in row and row["best_oa_location"]:
        oa_location = row["best_oa_location"]
        if "landing_page_url" in oa_location and oa_location["landing_page_url"]:
            zotero_temp["url"] = oa_location["landing_page_url"]
        elif "pdf_url" in oa_location and oa_location["pdf_url"]:
            zotero_temp["url"] = oa_location["pdf_url"]
        # Store PDF URL separately if available
        if "pdf_url" in oa_location and oa_location["pdf_url"]:
            zotero_temp["pdf_url"] = oa_location["pdf_url"]
    elif "primary_location" in row and row["primary_location"]:
        primary = row["primary_location"]
        if "landing_page_url" in primary and primary["landing_page_url"]:
            zotero_temp["url"] = primary["landing_page_url"]
    # Fallback: construct URL from DOI if available
    elif is_valid(row.get("doi")):
        doi = row["doi"]
        # Handle both full DOI URLs and just DOI identifiers
        if doi.startswith("http"):
            zotero_temp["url"] = doi
        elif doi.startswith("10."):
            zotero_temp["url"] = f"https://doi.org/{doi}"

    # Extract abstract from inverted index
    if "abstract_inverted_index" in row and row["abstract_inverted_index"]:
        reconstructed = reconstruct_abstract_from_inverted_index(
            row["abstract_inverted_index"]
        )
        if reconstructed:
            zotero_temp["abstract"] = reconstructed

    # Standardize rights field to "open_access" or "restricted"
    if (
        row["open_access"] != ""
        and row["open_access"] is not None
        and "is_oa" in row["open_access"]
    ):
        zotero_temp["rights"] = (
            "open_access" if row["open_access"]["is_oa"] else "restricted"
        )

    # Extract authors - fix inefficient loop (was setting inside loop)
    auth_list = []
    if "authorships" in row and row["authorships"]:
        for auth in row["authorships"]:
            if auth.get("author") and auth["author"].get("display_name"):
                display_name = auth["author"]["display_name"]
                if display_name and display_name != "":
                    auth_list.append(display_name)
    if auth_list:
        zotero_temp["authors"] = ";".join(auth_list)

    if row["type"] == "journal-article":
        zotero_temp["itemType"] = "journalArticle"
    if row["type"] == "article":
        zotero_temp["itemType"] = "journalArticle"
    if row["type"] == "book":
        zotero_temp["itemType"] = "book"
    if row["type"] == "book-chapter":
        zotero_temp["itemType"] = "bookSection"
    if row["type"] == "proceedings-article":
        zotero_temp["itemType"] = "conferencePaper"
    # if row["type"] == "preprint":

    # print("NEED TO ADD FOLLOWING TYPE >",row["type"])

    if "biblio" in row:
        if row["biblio"]["volume"] and row["biblio"]["volume"] != "":
            zotero_temp["volume"] = row["biblio"]["volume"]
        if row["biblio"]["issue"] and row["biblio"]["issue"] != "":
            zotero_temp["issue"] = row["biblio"]["issue"]
        if (
            row["biblio"]["first_page"]
            and row["biblio"]["first_page"] != ""
            and row["biblio"]["last_page"]
            and row["biblio"]["last_page"] != ""
        ):
            zotero_temp["pages"] = (
                row["biblio"]["first_page"] + "-" + row["biblio"]["last_page"]
            )

    if "host_venue" in row:
        if "publisher" in row["host_venue"] and row["host_venue"]["publisher"]:
            zotero_temp["publisher"] = row["host_venue"]["publisher"]

        if "display_name" in row["host_venue"] and "type" in row["host_venue"]:
            if row["host_venue"]["type"] == "conference":
                zotero_temp["itemType"] = "conferencePaper"
                zotero_temp["conferenceName"] = row["host_venue"]["display_name"]

            elif row["host_venue"]["type"] == "journal":
                zotero_temp["journalAbbreviation"] = row["host_venue"]["display_name"]
                zotero_temp["itemType"] = "journalArticle"
            else:
                pass

            # print("NEED TO ADD FOLLOWING TYPE >",row["host_venue"]["type"])

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def IEEEtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }

    zotero_temp["archive"] = "IEEE"
    zotero_temp["archiveID"] = row["article_number"]

    if (
        "publication_date" in row
        and row["publication_date"] != ""
        and row["publication_date"] is not None
    ):
        zotero_temp["date"] = row["publication_date"]
    elif (
        "publication_year" in row
        and row["publication_year"] != ""
        and row["publication_year"] is not None
    ):
        zotero_temp["date"] = row["publication_year"]
    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]
    if row["abstract"] != "" and row["abstract"] is not None:
        zotero_temp["abstract"] = row["abstract"]
    if ("html_url" in row) and (row["html_url"] != "" and row["html_url"] is not None):
        zotero_temp["url"] = row["html_url"]
    if row["access_type"] != "" and row["access_type"] is not None:
        zotero_temp["rights"] = row["access_type"]
    if "doi" in row:
        zotero_temp["DOI"] = clean_doi(row["doi"])
    if "publisher" in row:
        zotero_temp["publisher"] = row["publisher"]
    if ("volume" in row) and (row["volume"] != "" and row["volume"] is not None):
        zotero_temp["volume"] = row["volume"]
    if "issue" in row and row["issue"] != "" and row["issue"] is not None:
        zotero_temp["issue"] = row["issue"]

    if "publication_title" in row:
        if row["publication_title"] != "" and row["publication_title"] is not None:
            zotero_temp["journalAbbreviation"] = row["publication_title"]
    # Extract authors - fix inefficient loop (was setting inside loop)
    auth_list = []
    if isinstance(row["authors"], list):
        for auth in row["authors"]:
            if auth.get("full_name") and auth["full_name"] != "":
                auth_list.append(auth["full_name"])
    elif is_dict_like(row["authors"]) and "authors" in row["authors"]:
        for auth in row["authors"]["authors"]:
            if auth.get("full_name") and auth["full_name"] != "":
                auth_list.append(auth["full_name"])
    if auth_list:
        zotero_temp["authors"] = ";".join(auth_list)
    if "start_page" in row and (
        row["start_page"]
        and row["start_page"] != ""
        and row["end_page"]
        and row["end_page"] != ""
    ):
        zotero_temp["pages"] = row["start_page"] + "-" + row["end_page"]
    # Extract PDF URL
    if "pdf_url" in row and is_valid(row["pdf_url"]):
        zotero_temp["pdf_url"] = row["pdf_url"]
    if row["content_type"] == "Journals":
        zotero_temp["itemType"] = "journalArticle"
    if row["content_type"] == "Conferences":
        zotero_temp["itemType"] = "conferencePaper"

        # print("NEED TO ADD FOLLOWING TYPE >",row["content_type"])

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def SpringertoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }

    zotero_temp["archive"] = "Springer"
    zotero_temp["archiveID"] = row["identifier"]

    if (
        "publicationDate" in row
        and row["publicationDate"] != ""
        and row["publicationDate"] is not None
    ):
        zotero_temp["date"] = row["publicationDate"]
    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]
    if row["abstract"] != "" and row["abstract"] is not None:
        zotero_temp["abstract"] = row["abstract"]

    # Extract URL from Springer API - try multiple possible field names
    if "url" in row and is_valid(row["url"]):
        # url can be a list of URL objects in Springer API
        if isinstance(row["url"], list) and len(row["url"]) > 0:
            # Get the first URL or look for HTML format
            for url_obj in row["url"]:
                if isinstance(url_obj, dict):
                    if url_obj.get("format") == "html" or "value" in url_obj:
                        zotero_temp["url"] = url_obj.get("value", "")
                        break
                elif isinstance(url_obj, str):
                    zotero_temp["url"] = url_obj
                    break
        elif isinstance(row["url"], str):
            zotero_temp["url"] = row["url"]

    if "openaccess" in row:
        if row["openaccess"] != "" and row["openaccess"] is not None:
            zotero_temp["rights"] = row["openaccess"]
    if "doi" in row:
        zotero_temp["DOI"] = clean_doi(row["doi"])
    if "publisher" in row:
        zotero_temp["publisher"] = row["publisher"]

    # Extract volume from Springer API
    if "volume" in row and is_valid(row["volume"]):
        zotero_temp["volume"] = row["volume"]

    # Extract issue from Springer API (field name is "number" in Springer API)
    if "number" in row and is_valid(row["number"]):
        zotero_temp["issue"] = row["number"]
    elif "issue" in row and is_valid(row["issue"]):
        zotero_temp["issue"] = row["issue"]

    if row["publicationName"] != "" and row["publicationName"] is not None:
        zotero_temp["journalAbbreviation"] = row["publicationName"]

    # Extract authors - fix inefficient loop (was setting inside loop)
    auth_list = []
    if "creators" in row and row["creators"]:
        for auth in row["creators"]:
            if auth.get("creator") and auth["creator"] != "":
                auth_list.append(auth["creator"])
    if auth_list:
        zotero_temp["authors"] = ";".join(auth_list)

    if "startingPage" in row and "endingPage" in row:
        if row["startingPage"] != "" and row["endingPage"] != "":
            zotero_temp["pages"] = row["startingPage"] + "-" + row["endingPage"]

    if "Conference" in row["contentType"]:
        zotero_temp["itemType"] = "conferencePaper"
    elif "Article" in row["contentType"]:
        zotero_temp["itemType"] = "journalArticle"
    elif "Chapter" in row["contentType"]:
        zotero_temp["itemType"] = "bookSection"
    # if("Conference" in  row["content_type"]):
    #    zotero_temp["itemType"]="conferencePaper"
    # elif("Article" in  row["content_type"]):
    #     zotero_temp["itemType"]="journalArticle"
    # elif("Chapter" in  row["content_type"]):
    #     zotero_temp["itemType"]="bookSection"

    else:
        pass
        # print("NEED TO ADD FOLLOWING TYPE >",row["content_type"])

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def ElseviertoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }

    zotero_temp["archive"] = "Elsevier"
    if "source-id" in row:
        zotero_temp["archiveID"] = row["source-id"]

    if (
        "prism:coverDate" in row
        and row["prism:coverDate"] != ""
        and row["prism:coverDate"] is not None
    ):
        zotero_temp["date"] = row["prism:coverDate"]
    if "dc:title" in row and row["dc:title"] != "" and row["dc:title"] is not None:
        zotero_temp["title"] = row["dc:title"]

    # Extract abstract from Scopus API (dc:description field)
    if "dc:description" in row and is_valid(row["dc:description"]):
        zotero_temp["abstract"] = row["dc:description"]

    if row["prism:url"] != "" and row["prism:url"] is not None:
        zotero_temp["url"] = row["prism:url"]
    if row["openaccess"] != "" and row["openaccess"] is not None:
        zotero_temp["rights"] = row["openaccess"]
    if "prism:doi" in row:
        zotero_temp["DOI"] = clean_doi(row["prism:doi"])
    if "publisher" in row:
        zotero_temp["publisher"] = row["publisher"]
    if "prism:volume" in row:
        if row["prism:volume"] != "" and row["prism:volume"] is not None:
            zotero_temp["volume"] = row["prism:volume"]
    if (
        "prism:issueIdentifier" in row
        and row["prism:issueIdentifier"] != ""
        and row["prism:issueIdentifier"] is not None
    ):
        zotero_temp["issue"] = row["prism:issueIdentifier"]

    if (
        "prism:publicationName" in row
        and row["prism:publicationName"] != ""
        and row["prism:publicationName"] is not None
    ):
        zotero_temp["journalAbbreviation"] = row["prism:publicationName"]
    # auth_list=[]
    # for auth in row["creators"]:
    #    if(auth["creator"]!="" and auth["creator"] is not None):
    #         auth_list.append( auth["creator"])
    #    if(len(auth_list)>0):
    #     zotero_temp["authors"]";".join(auth_list)
    if ("dc:creator" in row) and (row["dc:creator"] and row["dc:creator"] != ""):
        zotero_temp["authors"] = row["dc:creator"]
    if row["prism:pageRange"] and row["prism:pageRange"] != "":
        zotero_temp["pages"] = row["prism:pageRange"]

    if (
        "subtypeDescription" in row
        and row["subtypeDescription"] is not None
        and row["subtypeDescription"] != ""
    ):
        if "Conference" in row["subtypeDescription"]:
            zotero_temp["itemType"] = "conferencePaper"
        elif "Article" in row["subtypeDescription"]:
            zotero_temp["itemType"] = "journalArticle"
        elif "Chapter" in row["subtypeDescription"]:
            zotero_temp["itemType"] = "bookSection"
        else:
            pass
            # print("NEED TO ADD FOLLOWING TYPE >",row["subtypeDescription"])

    # Default itemType if not set
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    return zotero_temp


def GoogleScholartoZoteroFormat(row):
    """
    Convert Google Scholar (scholarly package) results to Zotero format.

    Note: Google Scholar data from scholarly package can be incomplete.
    Many fields may be missing (DOI, publisher, volume, etc.).
    """
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
    }

    zotero_temp["archive"] = "GoogleScholar"

    # Title
    if safe_get(row, "title"):
        zotero_temp["title"] = row["title"]

    # Authors - scholarly returns authors as a list of names
    if safe_get(row, "authors"):
        authors = row["authors"]
        if isinstance(authors, list):
            # Filter out empty author names
            auth_list = [auth for auth in authors if auth and auth != ""]
            if len(auth_list) > 0:
                zotero_temp["authors"] = ";".join(auth_list)
        elif isinstance(authors, str):
            # Sometimes it might be a string
            zotero_temp["authors"] = authors

    # Abstract
    if safe_get(row, "abstract"):
        zotero_temp["abstract"] = row["abstract"]

    # Venue - try to determine item type from venue
    if safe_get(row, "venue"):
        venue = row["venue"].lower()
        # Try to infer type from venue name
        if any(keyword in venue for keyword in ["journal", "ieee", "acm", "springer"]):
            zotero_temp["itemType"] = "journalArticle"
            zotero_temp["journalAbbreviation"] = row["venue"]
        elif any(
            keyword in venue
            for keyword in ["conference", "proceedings", "workshop", "symposium"]
        ):
            zotero_temp["itemType"] = "conferencePaper"
            zotero_temp["conferenceName"] = row["venue"]
        elif any(keyword in venue for keyword in ["book", "chapter"]):
            zotero_temp["itemType"] = "bookSection"
        else:
            # Default to journal article if venue exists but type unclear
            zotero_temp["itemType"] = "journalArticle"
            zotero_temp["journalAbbreviation"] = row["venue"]

    # If no venue or item type still not set, default to Manuscript
    if not is_valid(zotero_temp.get("itemType")):
        zotero_temp["itemType"] = "Manuscript"

    # Year/Date
    if safe_get(row, "year"):
        zotero_temp["date"] = str(row["year"])

    # URL - prefer eprint_url (full text) over regular url
    if safe_get(row, "eprint_url"):
        zotero_temp["url"] = row["eprint_url"]
        # If eprint_url exists, it means the paper has open access
        zotero_temp["rights"] = "open_access"
    elif safe_get(row, "url"):
        zotero_temp["url"] = row["url"]
        zotero_temp["rights"] = "restricted"

    # Scholar ID (use as archive ID)
    if safe_get(row, "scholar_id"):
        scholar_id = row["scholar_id"]
        if isinstance(scholar_id, list) and len(scholar_id) > 0:
            zotero_temp["archiveID"] = scholar_id[0]
        elif isinstance(scholar_id, str):
            zotero_temp["archiveID"] = scholar_id

    # Note: Google Scholar (via scholarly) typically does not provide:
    # - DOI (rarely available)
    # - Publisher information
    # - Volume/Issue numbers
    # - Page numbers
    # These fields will remain as MISSING_VALUE

    return zotero_temp


def PubMedCentraltoZoteroFormat(row):
    """Convert PubMed Central (PMC) results to Zotero format.

    PMC provides open-access biomedical literature with comprehensive metadata.
    All PMC articles have full-text access and typically include complete
    bibliographic information.

    Args:
        row: Dictionary containing PMC article data from collector

    Returns:
        dict: Zotero-formatted article metadata
    """
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": MISSING_VALUE,
        "date": MISSING_VALUE,
        "DOI": MISSING_VALUE,
        "url": MISSING_VALUE,
        "pdf_url": MISSING_VALUE,
        "rights": MISSING_VALUE,
        "pages": MISSING_VALUE,
        "journalAbbreviation": MISSING_VALUE,
        "volume": MISSING_VALUE,
        "serie": MISSING_VALUE,
        "issue": MISSING_VALUE,
    }

    # Set archive name
    zotero_temp["archive"] = "PubMedCentral"

    # PMC is always open access
    zotero_temp["rights"] = "open-access"

    # Title
    if row["title"] != "" and row["title"] is not None:
        zotero_temp["title"] = row["title"]

    # Authors - PMC returns list of "Surname GivenNames" strings
    if "authors" in row and row["authors"]:
        authors = row["authors"]
        if isinstance(authors, list) and len(authors) > 0:
            zotero_temp["authors"] = ";".join(authors)
        elif isinstance(authors, str) and authors != "":
            zotero_temp["authors"] = authors

    # Abstract
    if row["abstract"] != "" and row["abstract"] is not None:
        zotero_temp["abstract"] = row["abstract"]

    # DOI
    if row["doi"] != "" and row["doi"] is not None:
        zotero_temp["DOI"] = row["doi"]

    # PMC ID (archiveID) - use PMID if PMC ID not available
    if "pmc_id" in row and row["pmc_id"] != "" and row["pmc_id"] is not None:
        pmc_id = row["pmc_id"]
        zotero_temp["archiveID"] = pmc_id

        # Construct URL from PMC ID
        if pmc_id.startswith("PMC"):
            zotero_temp["url"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
            # PMC provides direct PDF access for all articles
            zotero_temp["pdf_url"] = (
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            )
    elif "pmid" in row and row["pmid"] != "" and row["pmid"] is not None:
        # Fallback to PMID if no PMC ID
        zotero_temp["archiveID"] = row["pmid"]
        zotero_temp["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"

    # Publication date (YYYY-MM-DD format from collector)
    if row["date"] != "" and row["date"] is not None:
        zotero_temp["date"] = row["date"]

    # Journal name
    if row["journal"] != "" and row["journal"] is not None:
        zotero_temp["journalAbbreviation"] = row["journal"]

    # Volume
    if row["volume"] != "" and row["volume"] is not None:
        zotero_temp["volume"] = row["volume"]

    # Issue
    if row["issue"] != "" and row["issue"] is not None:
        zotero_temp["issue"] = row["issue"]

    # Pages
    if row["pages"] != "" and row["pages"] is not None:
        zotero_temp["pages"] = row["pages"]

    # Publisher
    if row["publisher"] != "" and row["publisher"] is not None:
        zotero_temp["publisher"] = row["publisher"]

    # Language
    if row["language"] != "" and row["language"] is not None:
        zotero_temp["language"] = row["language"]

    # ItemType - Most PMC articles are journal articles
    zotero_temp["itemType"] = "journalArticle"

    return zotero_temp
