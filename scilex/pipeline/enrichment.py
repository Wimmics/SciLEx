"""URL and citation enrichment fallback functions for the aggregation pipeline."""

import logging

import pandas as pd

from scilex.constants import is_valid


def fill_missing_urls_from_doi(df):
    """Fill missing URLs using DOI resolver (https://doi.org/).

    Papers without URLs but with valid DOIs get a URL generated from their DOI.

    Args:
        df: DataFrame with 'url' and 'DOI' columns

    Returns:
        tuple: (DataFrame with URLs filled, stats dict)
    """
    if "url" not in df.columns or "DOI" not in df.columns:
        logging.warning("Cannot fill URLs: missing 'url' or 'DOI' column")
        return df, {"filled": 0, "already_valid": 0, "no_doi": 0}

    stats = {"filled": 0, "already_valid": 0, "no_doi": 0}

    def generate_url_from_doi(row):
        url = row.get("url")
        doi = row.get("DOI")

        if is_valid(url):
            stats["already_valid"] += 1
            return url

        if not is_valid(doi):
            stats["no_doi"] += 1
            return url

        doi_str = str(doi).strip()
        if doi_str.lower().startswith("https://doi.org/"):
            doi_str = doi_str[16:]
        elif doi_str.lower().startswith("http://doi.org/"):
            doi_str = doi_str[15:]

        stats["filled"] += 1
        return f"https://doi.org/{doi_str}"

    df = df.copy()
    df["url"] = df.apply(generate_url_from_doi, axis=1)

    logging.info(
        f"URL fallback: {stats['filled']} URLs generated from DOIs, "
        f"{stats['already_valid']} already valid, "
        f"{stats['no_doi']} papers without DOI"
    )

    return df, stats


def use_semantic_scholar_citations_fallback(df):
    """Use Semantic Scholar citation data as fallback when OpenCitations data is missing.

    Args:
        df: DataFrame with both OpenCitations and Semantic Scholar citation data

    Returns:
        pd.DataFrame: DataFrame with citation data filled from Semantic Scholar
    """
    if "ss_citation_count" not in df.columns:
        logging.info(
            "Semantic Scholar citation data not available (only papers from SS API have this)"
        )
        return df

    has_ss_data = df["ss_citation_count"].notna().sum()
    logging.info(f"Found Semantic Scholar citation data for {has_ss_data:,} papers")

    if has_ss_data == 0:
        return df

    initial_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()

    df["nb_citation"] = df.apply(
        lambda row: row["ss_citation_count"]
        if (pd.isna(row["nb_citation"]) or row["nb_citation"] == 0)
        and pd.notna(row["ss_citation_count"])
        else row["nb_citation"],
        axis=1,
    )

    df["nb_cited"] = df.apply(
        lambda row: row["ss_reference_count"]
        if (pd.isna(row["nb_cited"]) or row["nb_cited"] == 0)
        and pd.notna(row["ss_reference_count"])
        else row["nb_cited"],
        axis=1,
    )

    final_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()
    improved_count = initial_zero_count - final_zero_count

    improved_pct = (improved_count / has_ss_data * 100) if has_ss_data > 0 else 0.0
    logging.info("Semantic Scholar fallback applied:")
    logging.info(f"  Papers with 0 citations before: {initial_zero_count:,}")
    logging.info(f"  Papers with 0 citations after: {final_zero_count:,}")
    logging.info(
        f"  Improved: {improved_count:,} papers ({improved_pct:.1f}% of papers with SS data)"
    )

    return df


def use_openalex_citations_fallback(df):
    """Use OpenAlex citation data as fallback when citation count is still missing.

    Args:
        df: DataFrame with OpenAlex citation data

    Returns:
        pd.DataFrame: DataFrame with nb_citation filled from OpenAlex
    """
    if "oa_citation_count" not in df.columns:
        logging.info(
            "OpenAlex citation data not available (only papers from OpenAlex API have this)"
        )
        return df

    has_oa_data = df["oa_citation_count"].notna().sum()
    logging.info(f"Found OpenAlex citation data for {has_oa_data:,} papers")

    if has_oa_data == 0:
        return df

    initial_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()

    df["nb_citation"] = df.apply(
        lambda row: row["oa_citation_count"]
        if (pd.isna(row["nb_citation"]) or row["nb_citation"] == 0)
        and pd.notna(row["oa_citation_count"])
        else row["nb_citation"],
        axis=1,
    )

    final_zero_count = ((df["nb_citation"] == 0) | df["nb_citation"].isna()).sum()
    improved_count = initial_zero_count - final_zero_count

    improved_pct = (improved_count / has_oa_data * 100) if has_oa_data > 0 else 0.0
    logging.info("OpenAlex fallback applied:")
    logging.info(f"  Papers with 0 citations before: {initial_zero_count:,}")
    logging.info(f"  Papers with 0 citations after: {final_zero_count:,}")
    logging.info(
        f"  Improved: {improved_count:,} papers ({improved_pct:.1f}% of papers with OA data)"
    )

    return df
