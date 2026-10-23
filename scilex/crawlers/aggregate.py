#!/usr/bin/env python3
"""
Created on Fri Feb 10 10:57:49 2023

@author: cringwal
         aollagnier

@version: 1.0.1
"""

import contextlib
import logging

import pandas as pd

from scilex.constants import MISSING_VALUE, is_valid
from scilex.crawlers.converter_utils import (
    dig,
    fill_record,
    first_of,
    first_valid,
    get_valid,
    item_type_from_text,
    join_authors,
    join_values,
    map_item_type,
    new_record,
    page_range,
)

_SS_SINGLE_TYPE_TO_ITEM_TYPE = {
    "JournalArticle": "journalArticle",
    "Conference": "conferencePaper",
    "Conferences": "conferencePaper",
    "Book": "book",
}
# When several types are listed, the first one found in this order wins.
_SS_MULTI_TYPE_PRIORITY = (
    ("Book", "book"),
    ("Conference", "conferencePaper"),
    ("JournalArticle", "journalArticle"),
)
_ISTEX_GENRE_TO_ITEM_TYPE = {
    "research-article": "journalArticle",
    "article": "journalArticle",
    "conference": "conferencePaper",
    "book-chapter": "bookSection",
}
_DBLP_TYPE_TO_ITEM_TYPE = {
    "Journal Articles": "journalArticle",
    "Conference and Workshop Papers": "conferencePaper",
    "Informal Publications": "Manuscript",
    "Informal and Other Publications": "Manuscript",
}
_OPENALEX_TYPE_TO_ITEM_TYPE = {
    "journal-article": "journalArticle",
    "article": "journalArticle",
    "book": "book",
    "book-chapter": "bookSection",
    "proceedings-article": "conferencePaper",
}
_IEEE_CONTENT_TYPE_TO_ITEM_TYPE = {
    "Journals": "journalArticle",
    "Conferences": "conferencePaper",
}
# Springer and Elsevier describe the type in free text: first pattern found wins.
_SPRINGER_TYPE_PATTERNS = (
    ("Conference", "conferencePaper"),
    ("Article", "journalArticle"),
    ("Chapter", "bookSection"),
)
_ELSEVIER_TYPE_PATTERNS = _SPRINGER_TYPE_PATTERNS
_HAL_DOC_TYPE_TO_ITEM_TYPE = {
    "ART": "journalArticle",
    "COMM": "conferencePaper",
    "PROCEEDINGS": "conferencePaper",
    "Informal Publications": "Manuscript",
}


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
    for col in column_names:
        value = df_row.get(col)
        if is_valid(value):
            # Apply weighted scoring
            if col in critical_fields:
                quality += 5
            elif col in important_fields:
                quality += 3
                if col == "volume":
                    has_volume = True
                elif col == "issue":
                    has_issue = True
            else:
                quality += 1

    # Apply bonuses
    if has_volume and has_issue:
        quality += 1  # Bonus for complete bibliographic info

    return quality


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


def _apply_semantic_scholar_venue(record, venue):
    """Set itemType and journal/conference name from a Semantic Scholar venue dict."""
    venue_type = get_valid(venue, "type")
    venue_name = get_valid(venue, "name")
    if venue_type == "journal":
        record["itemType"] = "journalArticle"
        fill_record(record, journalAbbreviation=venue_name)
    elif venue_type == "conference":
        record["itemType"] = "conferencePaper"
        fill_record(record, conferenceName=venue_name)


def _semantic_scholar_item_type(publication_types):
    """Pick one Zotero itemType from Semantic Scholar's publicationTypes list."""
    if not isinstance(publication_types, list):
        return MISSING_VALUE
    if len(publication_types) == 1:
        return map_item_type(
            publication_types[0], _SS_SINGLE_TYPE_TO_ITEM_TYPE, MISSING_VALUE
        )
    for publication_type, item_type in _SS_MULTI_TYPE_PRIORITY:
        if publication_type in publication_types:
            return item_type
    return MISSING_VALUE


def SemanticScholartoZoteroFormat(row):
    """Convert a Semantic Scholar paper to the internal Zotero-style record."""
    record = new_record(
        "SemanticScholar",
        item_type=_semantic_scholar_item_type(get_valid(row, "publicationTypes")),
    )

    # publicationVenue is richer than the legacy venue field, so it goes first.
    publication_venue = get_valid(row, "publicationVenue")
    fill_record(
        record,
        publisher=get_valid(publication_venue, "publisher"),
        serie=get_valid(publication_venue, "issn"),
    )
    _apply_semantic_scholar_venue(record, publication_venue)
    _apply_semantic_scholar_venue(record, get_valid(row, "venue"))

    journal = get_valid(row, "journal")
    if journal is not None:
        journal_pages = get_valid(journal, "pages")
        if journal_pages is not None and record["itemType"] == "book":
            record["itemType"] = "bookSection"
        if not is_valid(record["itemType"]):
            # Journal metadata without a known type (e.g. reviews): assume article.
            record["itemType"] = "journalArticle"
        fill_record(
            record,
            pages=journal_pages,
            journalAbbreviation=get_valid(journal, "name"),
            volume=get_valid(journal, "volume"),
        )

    if not is_valid(record["itemType"]):
        # Zotero rejects items without a type.
        record["itemType"] = "Manuscript"

    author_entries = get_valid(row, "authors")
    author_names = [
        get_valid(author, "name")
        for author in (author_entries if isinstance(author_entries, list) else [])
    ]
    fill_record(
        record,
        title=get_valid(row, "title"),
        abstract=get_valid(row, "abstract"),
        archiveID=get_valid(row, "paper_id"),
        date=get_valid(row, "publication_date"),
        url=get_valid(row, "url"),
        authors=join_authors(author_names),
    )
    if get_valid(row, "DOI") is not None:
        record["DOI"] = clean_doi(row["DOI"])

    open_access_pdf = get_valid(row, "open_access_pdf")
    if open_access_pdf is not None:
        record["pdf_url"] = open_access_pdf
        record["rights"] = "open_access"

    # Citation data kept as fallback for the citation step (0 is a real value).
    fill_record(
        record,
        ss_citation_count=get_valid(row, "citationCount"),
        ss_reference_count=get_valid(row, "referenceCount"),
    )
    return record


def IstextoZoteroFormat(row):
    """Convert an Istex record to the internal Zotero-style record."""
    record = new_record("Istex")

    genre = get_valid(row, "genre")
    if isinstance(genre, list) and len(genre) != 1:
        # Several genres are ambiguous: leave the type to the default.
        genre = None
    record["itemType"] = map_item_type(
        first_of(genre), _ISTEX_GENRE_TO_ITEM_TYPE, MISSING_VALUE
    )

    author_entries = get_valid(row, "author")
    dois = get_valid(row, "doi")
    dois = dois if isinstance(dois, list) else [dois]
    host = get_valid(row, "host")
    pages = get_valid(host, "pages")
    series = get_valid(row, "series")
    publisher = first_of(get_valid(host, "publisherId")) or get_valid(host, "publisher")
    fill_record(
        record,
        title=get_valid(row, "title"),
        abstract=get_valid(row, "abstract"),
        archiveID=get_valid(row, "arkIstex"),
        date=get_valid(row, "publicationDate"),
        language=first_of(get_valid(row, "language")),
        serie=get_valid(series, "title"),
        volume=get_valid(host, "volume"),
        issue=get_valid(host, "issue"),
        journalAbbreviation=get_valid(host, "title"),
        publisher=publisher,
        url=get_valid(row, "url"),
        rights=dig(row, "accessCondition", "contentType") or None,
        authors=join_authors(
            [get_valid(a, "name") for a in author_entries]
            if isinstance(author_entries, list)
            else None
        ),
    )
    if get_valid(row, "doi") is not None:
        record["DOI"] = ";".join(clean_doi(doi) for doi in dois)
    if isinstance(pages, dict):
        record["pages"] = page_range(pages.get("first"), pages.get("last"))

    fulltext = get_valid(row, "fulltext")
    for entry in fulltext if isinstance(fulltext, list) else []:
        if get_valid(entry, "extension") == "pdf" and get_valid(entry, "uri"):
            record["pdf_url"] = entry["uri"]
            break

    if not is_valid(record["itemType"]):
        record["itemType"] = "Manuscript"
    return record


def ArxivtoZoteroFormat(row):
    """Convert an arXiv entry to the internal Zotero-style record."""
    # arXiv is always open access; an entry is a preprint unless a journal is given.
    record = new_record("Arxiv", item_type="preprint")
    record["rights"] = "open_access"
    record["publisher"] = "arXiv"

    fill_record(
        record,
        abstract=get_valid(row, "abstract"),
        title=get_valid(row, "title"),
        date=get_valid(row, "published"),
        authors=join_authors(get_valid(row, "authors")),
    )
    if get_valid(row, "doi") is not None:
        record["DOI"] = clean_doi(row["doi"])

    arxiv_id = get_valid(row, "id")
    if arxiv_id is not None:
        arxiv_id = str(arxiv_id)
        record["archiveID"] = arxiv_id
        if arxiv_id.startswith("http"):
            # e.g. https://arxiv.org/abs/2301.12345 or http://arxiv.org/abs/cs/0601078v1
            record["url"] = arxiv_id
            url_id = arxiv_id.rstrip("/")
            if "/abs/" in url_id:
                url_id = url_id.split("/abs/")[-1]
            elif "/pdf/" in url_id:
                url_id = url_id.split("/pdf/")[-1].replace(".pdf", "")
        else:
            url_id = arxiv_id.split("/")[-1]
            record["url"] = f"https://arxiv.org/abs/{url_id}"
        record["pdf_url"] = f"https://arxiv.org/pdf/{url_id}.pdf"

    categories = get_valid(row, "categories")
    if isinstance(categories, list):
        record["journalAbbreviation"] = ", ".join(categories)
    elif isinstance(categories, str):
        record["journalAbbreviation"] = categories

    journal = get_valid(row, "journal")
    if journal is not None:
        record["journalAbbreviation"] = journal
        record["itemType"] = "journalArticle"
    return record


def _dblp_author_names(authors_field):
    """Return author names from DBLP's single-dict or list `author` entry."""
    author_entries = dig(authors_field, "author")
    if isinstance(author_entries, dict):
        author_entries = [author_entries]
    if not isinstance(author_entries, list):
        return []
    return [get_valid(entry, "text") for entry in author_entries]


def DBLPtoZoteroFormat(row):
    """Convert a DBLP hit to the internal Zotero-style record."""
    info = get_valid(row, "info")
    if not isinstance(info, dict):
        info = {}
    record = new_record("DBLP")

    venue = get_valid(info, "venue")
    item_type = map_item_type(info.get("type"), _DBLP_TYPE_TO_ITEM_TYPE, "Manuscript")
    record["itemType"] = item_type
    fill_record(
        record,
        archiveID=get_valid(row, "@id"),
        title=get_valid(info, "title"),
        date=get_valid(info, "year"),
        authors=join_authors(_dblp_author_names(info.get("authors"))),
        pages=get_valid(info, "pages"),
        volume=get_valid(info, "volume"),
        issue=get_valid(info, "number"),
        publisher=get_valid(info, "publisher"),
        rights=get_valid(info, "access"),
        url=get_valid(info, "url"),
    )
    if get_valid(info, "doi") is not None:
        record["DOI"] = clean_doi(info["doi"])
    if item_type == "journalArticle":
        fill_record(record, journalAbbreviation=venue)
    elif item_type == "conferencePaper":
        fill_record(record, conferenceName=venue)
    return record


def HALtoZoteroFormat(row):
    """Convert a HAL document to the internal Zotero-style record."""
    doc_type = get_valid(row, "docType_s")
    item_type = map_item_type(doc_type, _HAL_DOC_TYPE_TO_ITEM_TYPE, "Manuscript")
    record = new_record("HAL", item_type=item_type)
    # HAL is open access by default.
    record["rights"] = "open_access"

    hal_id = get_valid(row, "halId_s")
    year = get_valid(row, "submittedDateY_i")
    pdf_candidates = get_valid(row, "files_s")
    pdf_url = next(
        (
            file_url
            for file_url in (pdf_candidates if isinstance(pdf_candidates, list) else [])
            if isinstance(file_url, str) and file_url.endswith(".pdf")
        ),
        None,
    )
    author_entries = get_valid(row, "authFullNameIdHal_fs")
    author_names = [
        entry.split("_FacetSep_")[0].strip()
        for entry in (author_entries if isinstance(author_entries, list) else [])
        if isinstance(entry, str)
    ]
    fill_record(
        record,
        archiveID=hal_id,
        title=first_of(get_valid(row, "title_s")),
        abstract=first_of(get_valid(row, "abstract_s")),
        serie=get_valid(row, "bookTitle_s"),
        conferenceName=get_valid(row, "conferenceTitle_s"),
        journalAbbreviation=get_valid(row, "journalTitle_t"),
        date=None if year is None else str(year),
        volume=get_valid(row, "volume_s"),
        issue=get_valid(row, "issue_s"),
        pages=get_valid(row, "page_s"),
        publisher=first_of(get_valid(row, "publisher_s")),
        url=None if hal_id is None else f"https://hal.science/{hal_id}",
        pdf_url=pdf_url,
        language=first_of(get_valid(row, "language_s")),
        authors=join_authors(author_names),
    )
    if get_valid(row, "doiId_id") is not None:
        record["DOI"] = clean_doi(row["doiId_id"])
    if doc_type == "ART":
        fill_record(record, journalAbbreviation=get_valid(row, "venue"))
    return record


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


def _openalex_urls(row):
    """Return (url, pdf_url): best OA location, then primary location, then DOI."""
    best_location = get_valid(row, "best_oa_location")
    if best_location is not None:
        pdf_url = get_valid(best_location, "pdf_url")
        landing_page = get_valid(best_location, "landing_page_url")
        return (landing_page if landing_page is not None else pdf_url), pdf_url

    primary_location = get_valid(row, "primary_location")
    if primary_location is not None:
        return (
            get_valid(primary_location, "landing_page_url"),
            get_valid(primary_location, "pdf_url"),
        )

    doi = get_valid(row, "doi")
    if isinstance(doi, str):
        if doi.startswith("http"):
            return doi, None
        if doi.startswith("10."):
            return f"https://doi.org/{doi}", None
    return None, None


def OpenAlextoZoteroFormat(row):
    """Convert an OpenAlex work to the internal Zotero-style record."""
    record = new_record(
        "OpenAlex",
        item_type=map_item_type(
            get_valid(row, "type"), _OPENALEX_TYPE_TO_ITEM_TYPE, MISSING_VALUE
        ),
    )

    url, pdf_url = _openalex_urls(row)
    open_access = get_valid(row, "open_access")
    rights = None
    if isinstance(open_access, dict) and "is_oa" in open_access:
        rights = "open_access" if open_access["is_oa"] else "restricted"

    authorships = get_valid(row, "authorships")
    author_names = [
        dig(authorship, "author", "display_name")
        for authorship in (authorships if isinstance(authorships, list) else [])
    ]

    biblio = get_valid(row, "biblio")
    # primary_location.source replaces the deprecated host_venue.
    source = dig(row, "primary_location", "source", default={})
    source_name = get_valid(source, "display_name")
    source_type = get_valid(source, "type")

    fill_record(
        record,
        archiveID=get_valid(row, "id"),
        DOI=clean_doi(get_valid(row, "doi")),
        title=get_valid(row, "title"),
        date=get_valid(row, "publication_date"),
        language=get_valid(row, "language"),
        url=url,
        pdf_url=pdf_url,
        abstract=reconstruct_abstract_from_inverted_index(
            get_valid(row, "abstract_inverted_index")
        ),
        rights=rights,
        authors=join_authors(author_names),
        volume=get_valid(biblio, "volume"),
        issue=get_valid(biblio, "issue"),
        pages=page_range(
            get_valid(biblio, "first_page"), get_valid(biblio, "last_page")
        ),
        publisher=get_valid(source, "host_organization_name"),
        serie=get_valid(source, "issn_l"),
    )

    if source_name is not None:
        if source_type == "conference":
            record["itemType"] = "conferencePaper"
            record["conferenceName"] = source_name
        elif source_type == "journal":
            record["itemType"] = "journalArticle"
            record["journalAbbreviation"] = source_name
        elif source_type == "repository" and not is_valid(
            record["journalAbbreviation"]
        ):
            # Preprint servers (arXiv, bioRxiv, medRxiv, ...).
            record["journalAbbreviation"] = source_name

    cited_by_count = get_valid(row, "cited_by_count")
    if cited_by_count is not None:
        with contextlib.suppress(TypeError, ValueError):
            record["oa_citation_count"] = int(cited_by_count)

    if not is_valid(record["itemType"]):
        record["itemType"] = "Manuscript"
    return record


def IEEEtoZoteroFormat(row):
    """Convert an IEEE Xplore article to the internal Zotero-style record."""
    record = new_record(
        "IEEE",
        item_type=map_item_type(
            get_valid(row, "content_type"),
            _IEEE_CONTENT_TYPE_TO_ITEM_TYPE,
            "Manuscript",
        ),
    )

    authors_field = get_valid(row, "authors")
    if isinstance(authors_field, dict):
        authors_field = authors_field.get("authors")
    author_names = [
        get_valid(author, "full_name")
        for author in (authors_field if isinstance(authors_field, list) else [])
    ]

    fill_record(
        record,
        archiveID=get_valid(row, "article_number"),
        date=first_valid(row, "publication_date", "publication_year"),
        title=get_valid(row, "title"),
        abstract=get_valid(row, "abstract"),
        url=get_valid(row, "html_url"),
        rights=get_valid(row, "access_type"),
        DOI=clean_doi(get_valid(row, "doi")),
        publisher=get_valid(row, "publisher"),
        volume=get_valid(row, "volume"),
        issue=get_valid(row, "issue"),
        journalAbbreviation=get_valid(row, "publication_title"),
        authors=join_authors(author_names),
        pages=page_range(get_valid(row, "start_page"), get_valid(row, "end_page")),
        pdf_url=get_valid(row, "pdf_url"),
    )
    return record


def _springer_urls(url_field):
    """Return (url, pdf_url) from Springer's list of URL objects (or plain string)."""
    if isinstance(url_field, str):
        return url_field, None
    if not isinstance(url_field, list):
        return None, None

    url = None
    pdf_url = None
    for url_object in url_field:
        if isinstance(url_object, dict):
            url_format = url_object.get("format")
            value = url_object.get("value")
            if url_format == "html" and value:
                url = value
            elif url_format == "pdf" and value:
                pdf_url = value
        elif isinstance(url_object, str) and url is None:
            url = url_object
    if url is None:
        # No html URL: fall back to the first available value.
        url = next(
            (
                get_valid(url_object, "value")
                for url_object in url_field
                if get_valid(url_object, "value") is not None
            ),
            None,
        )
    return url, pdf_url


def SpringertoZoteroFormat(row):
    """Convert a Springer record to the internal Zotero-style record."""
    record = new_record(
        "Springer",
        item_type=item_type_from_text(
            get_valid(row, "contentType"), _SPRINGER_TYPE_PATTERNS, "Manuscript"
        ),
    )

    url, pdf_url = _springer_urls(get_valid(row, "url"))
    creators = get_valid(row, "creators")
    author_names = [
        get_valid(creator, "creator")
        for creator in (creators if isinstance(creators, list) else [])
    ]

    fill_record(
        record,
        archiveID=get_valid(row, "identifier"),
        date=get_valid(row, "publicationDate"),
        title=get_valid(row, "title"),
        abstract=get_valid(row, "abstract"),
        url=url,
        pdf_url=pdf_url,
        rights=get_valid(row, "openaccess"),
        DOI=clean_doi(get_valid(row, "doi")),
        publisher=get_valid(row, "publisher"),
        volume=get_valid(row, "volume"),
        # Springer calls the issue "number".
        issue=first_valid(row, "number", "issue"),
        journalAbbreviation=get_valid(row, "publicationName"),
        authors=join_authors(author_names),
        pages=page_range(get_valid(row, "startingPage"), get_valid(row, "endingPage")),
    )
    return record


def ElseviertoZoteroFormat(row):
    """Convert an Elsevier (Scopus) entry to the internal Zotero-style record."""
    record = new_record(
        "Elsevier",
        item_type=item_type_from_text(
            get_valid(row, "subtypeDescription"), _ELSEVIER_TYPE_PATTERNS, "Manuscript"
        ),
    )
    fill_record(
        record,
        archiveID=get_valid(row, "source-id"),
        date=get_valid(row, "prism:coverDate"),
        title=get_valid(row, "dc:title"),
        abstract=get_valid(row, "dc:description"),
        url=get_valid(row, "prism:url"),
        rights=get_valid(row, "openaccess"),
        DOI=clean_doi(get_valid(row, "prism:doi")),
        publisher=get_valid(row, "publisher"),
        volume=get_valid(row, "prism:volume"),
        issue=get_valid(row, "prism:issueIdentifier"),
        journalAbbreviation=get_valid(row, "prism:publicationName"),
        authors=get_valid(row, "dc:creator"),
        pages=get_valid(row, "prism:pageRange"),
    )
    return record


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
        "tags": MISSING_VALUE,
    }

    # Set archive name
    zotero_temp["archive"] = "PubMedCentral"

    # PMC is always open access
    zotero_temp["rights"] = "open-access"

    # Title
    if is_valid(row.get("title")):
        zotero_temp["title"] = row["title"]

    # Authors - PMC returns list of "Surname GivenNames" strings
    authors = row.get("authors")
    if authors:
        if isinstance(authors, list) and len(authors) > 0:
            zotero_temp["authors"] = ";".join(authors)
        elif isinstance(authors, str) and is_valid(authors):
            zotero_temp["authors"] = authors

    # Abstract
    if is_valid(row.get("abstract")):
        zotero_temp["abstract"] = row["abstract"]

    # DOI
    if is_valid(row.get("doi")):
        zotero_temp["DOI"] = row["doi"]

    # PMC ID (archiveID) - use PMID if PMC ID not available
    if is_valid(row.get("pmc_id")):
        pmc_id = row["pmc_id"]
        zotero_temp["archiveID"] = pmc_id

        # Construct URL from PMC ID
        if pmc_id.startswith("PMC"):
            zotero_temp["url"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
            # PMC provides direct PDF access for all articles
            zotero_temp["pdf_url"] = (
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            )
    elif is_valid(row.get("pmid")):
        # Fallback to PMID if no PMC ID
        zotero_temp["archiveID"] = row["pmid"]
        zotero_temp["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"

    # Publication date (YYYY-MM-DD format from collector)
    if is_valid(row.get("date")):
        zotero_temp["date"] = row["date"]

    # Journal name
    if is_valid(row.get("journal")):
        zotero_temp["journalAbbreviation"] = row["journal"]

    # Volume
    if is_valid(row.get("volume")):
        zotero_temp["volume"] = row["volume"]

    # Issue
    if is_valid(row.get("issue")):
        zotero_temp["issue"] = row["issue"]

    # Pages
    if is_valid(row.get("pages")):
        zotero_temp["pages"] = row["pages"]

    # Publisher
    if is_valid(row.get("publisher")):
        zotero_temp["publisher"] = row["publisher"]

    # Language
    if is_valid(row.get("language")):
        zotero_temp["language"] = row["language"]

    # ItemType - Most PMC articles are journal articles
    zotero_temp["itemType"] = "journalArticle"

    return zotero_temp


def PubMedtoZoteroFormat(row):
    """Convert PubMed results to Zotero format.

    PubMed provides comprehensive biomedical literature metadata (35M+ papers)
    including both open-access and paywalled content. When PMCID is available,
    PDF URLs are automatically generated for PMC open-access subset.

    Args:
        row: Dictionary containing PubMed article data from collector

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
        "tags": MISSING_VALUE,
    }

    # Set archive name
    zotero_temp["archive"] = "PubMed"

    # Rights - only set to open-access if PMCID present
    if is_valid(row.get("pmcid")):
        zotero_temp["rights"] = "open-access"

    # Title
    if is_valid(row.get("title")):
        zotero_temp["title"] = row["title"]

    # Authors - PubMed returns list of "LastName ForeName" strings
    if "authors" in row and row["authors"]:
        authors = row["authors"]
        if isinstance(authors, list) and len(authors) > 0:
            zotero_temp["authors"] = ";".join(authors)
        elif isinstance(authors, str) and authors != "":
            zotero_temp["authors"] = authors

    # Abstract
    if is_valid(row.get("abstract")):
        zotero_temp["abstract"] = row["abstract"]

    # DOI
    if is_valid(row.get("doi")):
        zotero_temp["DOI"] = row["doi"]

    # PMID (archiveID) - primary identifier
    if is_valid(row.get("pmid")):
        pmid = row["pmid"]
        zotero_temp["archiveID"] = pmid
        # Construct PubMed URL
        zotero_temp["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    # PDF URL - populated by collector when PMCID present
    if is_valid(row.get("pdf_url")):
        zotero_temp["pdf_url"] = row["pdf_url"]

    # Publication date (YYYY-MM-DD format from collector)
    if is_valid(row.get("date")):
        zotero_temp["date"] = row["date"]

    # Journal name
    if is_valid(row.get("journal")):
        zotero_temp["journalAbbreviation"] = row["journal"]

    # Volume
    if is_valid(row.get("volume")):
        zotero_temp["volume"] = row["volume"]

    # Issue
    if is_valid(row.get("issue")):
        zotero_temp["issue"] = row["issue"]

    # Pages
    if is_valid(row.get("pages")):
        zotero_temp["pages"] = row["pages"]

    # Language
    if is_valid(row.get("language")):
        zotero_temp["language"] = row["language"]

    # MeSH terms as tags (optional)
    if "mesh_terms" in row and row["mesh_terms"]:
        mesh_terms = row["mesh_terms"]
        if isinstance(mesh_terms, list) and len(mesh_terms) > 0:
            zotero_temp["tags"] = ";".join(mesh_terms)

    # ItemType - map from publication_type
    pub_type = row.get("publication_type", "")
    if pub_type:
        # Map PubMed publication types to Zotero itemTypes
        type_mapping = {
            "Journal Article": "journalArticle",
            "Review": "journalArticle",
            "Book": "book",
            "Book Chapter": "bookSection",
        }
        zotero_temp["itemType"] = type_mapping.get(pub_type, "journalArticle")
    else:
        # Default to journal article
        zotero_temp["itemType"] = "journalArticle"

    return zotero_temp


def OpenAIREtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": MISSING_VALUE,
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": "OpenAIRE",
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

    try:
        entity = row["metadata"]["oaf:entity"]["oaf:result"]
    except (KeyError, TypeError):
        return zotero_temp

    # Title
    try:
        zotero_temp["title"] = entity["title"]["$"]
    except (KeyError, TypeError):
        pass

    # Authors — creator can be a dict (single) or list
    try:
        creators = entity["creator"]
        if isinstance(creators, dict):
            creators = [creators]
        names = [c.get("$", "") for c in creators if c.get("$")]
        if names:
            zotero_temp["authors"] = ";".join(names)
    except (KeyError, TypeError):
        pass

    # Date
    try:
        zotero_temp["date"] = entity["dateofacceptance"]["$"]
    except (KeyError, TypeError):
        pass

    # Abstract — description can be a dict {"$": "..."} or a plain string
    try:
        desc = entity["description"]
        if isinstance(desc, dict):
            zotero_temp["abstract"] = desc["$"]
        elif isinstance(desc, str) and desc:
            zotero_temp["abstract"] = desc
    except (KeyError, TypeError):
        pass

    # DOI — pid can be dict or list; filter by @classid == "doi"
    try:
        pids = entity.get("pid", [])
        if isinstance(pids, dict):
            pids = [pids]
        doi_raw = next(
            (p["$"] for p in pids if p.get("@classid") == "doi" and p.get("$")),
            None,
        )
        if doi_raw:
            zotero_temp["DOI"] = clean_doi(doi_raw)
    except (KeyError, TypeError):
        pass

    # Journal
    try:
        zotero_temp["journalAbbreviation"] = entity["journal"]["$"]
    except (KeyError, TypeError):
        pass

    # Language
    try:
        zotero_temp["language"] = entity["language"]["@classid"]
    except (KeyError, TypeError):
        pass

    # Rights
    try:
        classname = entity["bestaccessright"]["@classname"]
        if "Open" in classname:
            zotero_temp["rights"] = "open_access"
        else:
            zotero_temp["rights"] = "restricted"
    except (KeyError, TypeError):
        pass

    # Archive ID — originalId can be str or list
    try:
        original_id = entity["originalId"]
        if isinstance(original_id, list):
            original_id = original_id[0]
        zotero_temp["archiveID"] = original_id
    except (KeyError, TypeError):
        pass

    # URL — children.instance can be dict or list
    try:
        instances = entity["children"]["instance"]
        if isinstance(instances, dict):
            instances = [instances]
        url_val = next(
            (
                inst["webresource"]["url"]["$"]
                for inst in instances
                if inst.get("webresource", {}).get("url", {}).get("$")
            ),
            None,
        )
        if url_val:
            zotero_temp["url"] = url_val
    except (KeyError, TypeError):
        pass

    # Item type
    try:
        resource_type = entity["resourcetype"]["@classname"]
        type_mapping = {
            "Article": "journalArticle",
            "publication": "journalArticle",  # OpenAIRE generic type
            "Conference object": "conferencePaper",
            "Book": "book",
            "Book part": "bookSection",
            "Preprint": "preprint",
        }
        zotero_temp["itemType"] = type_mapping.get(resource_type, "journalArticle")
    except (KeyError, TypeError):
        pass

    return zotero_temp


def ORKGtoZoteroFormat(row):
    zotero_temp = {
        "title": MISSING_VALUE,
        "publisher": MISSING_VALUE,
        "itemType": "journalArticle",
        "authors": MISSING_VALUE,
        "language": MISSING_VALUE,
        "abstract": MISSING_VALUE,
        "archiveID": MISSING_VALUE,
        "archive": "ORKG",
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

    orkg_id = row.get("id", MISSING_VALUE)
    zotero_temp["archiveID"] = orkg_id

    # Title
    title = row.get("title")
    if title:
        zotero_temp["title"] = title

    # DOI
    try:
        doi_list = row["identifiers"]["doi"]
        if doi_list:
            zotero_temp["DOI"] = clean_doi(doi_list[0])
    except (KeyError, TypeError):
        pass

    # Publication info
    pub_info = row.get("publication_info", {})

    # Date
    year = pub_info.get("published_year")
    if year is not None:
        zotero_temp["date"] = str(year)

    # Journal
    published_in = pub_info.get("published_in")
    if published_in:
        if isinstance(published_in, dict):
            label = published_in.get("label")
            if label:
                zotero_temp["journalAbbreviation"] = label
        elif isinstance(published_in, str):
            zotero_temp["journalAbbreviation"] = published_in

    # URL — fallback to ORKG paper page
    url_val = pub_info.get("url", "")
    if url_val:
        zotero_temp["url"] = url_val
    elif is_valid(orkg_id):
        zotero_temp["url"] = f"https://orkg.org/paper/{orkg_id}"

    # Authors
    try:
        authors = row.get("authors", [])
        names = [a["name"] for a in authors if a.get("name")]
        if names:
            zotero_temp["authors"] = ";".join(names)
    except (KeyError, TypeError):
        pass

    return zotero_temp


# ============================================================================
# FORMAT CONVERTERS REGISTRY
# ============================================================================

FORMAT_CONVERTERS = {
    "SemanticScholar": SemanticScholartoZoteroFormat,
    "OpenAlex": OpenAlextoZoteroFormat,
    "IEEE": IEEEtoZoteroFormat,
    "Elsevier": ElseviertoZoteroFormat,
    "Springer": SpringertoZoteroFormat,
    "HAL": HALtoZoteroFormat,
    "DBLP": DBLPtoZoteroFormat,
    "Istex": IstextoZoteroFormat,
    "Arxiv": ArxivtoZoteroFormat,
    "PubMed": PubMedtoZoteroFormat,
    "PubMedCentral": PubMedCentraltoZoteroFormat,
    "OpenAIRE": OpenAIREtoZoteroFormat,
    "ORKG": ORKGtoZoteroFormat,
}
"""Maps API names to their format converter functions."""


def get_converter(api_name: str):
    """Get format converter for a given API name.

    Args:
        api_name: Name of the API (e.g., 'SemanticScholar', 'OpenAlex')

    Returns:
        Converter function, or None if not found.
    """
    return FORMAT_CONVERTERS.get(api_name)
