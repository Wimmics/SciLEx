"""Merge snowballed papers with the existing corpus."""

import logging

import pandas as pd

from scilex.constants import is_valid

logger = logging.getLogger(__name__)


def merge_with_corpus(
    corpus_df: pd.DataFrame,
    snowball_df: pd.DataFrame,
    doi_column: str = "DOI",
) -> pd.DataFrame:
    """Merge snowballed papers into the corpus, deduplicating by DOI.

    Adds a ``snowball_depth`` column: 0 for original corpus papers,
    1 for snowballed papers.

    Args:
        corpus_df: Original aggregated DataFrame.
        snowball_df: Snowballed papers DataFrame.
        doi_column: Column containing DOIs.

    Returns:
        Merged DataFrame with duplicates removed (corpus papers take priority).
    """
    if snowball_df.empty:
        corpus_df["snowball_depth"] = 0
        return corpus_df

    corpus_df["snowball_depth"] = 0
    snowball_df["snowball_depth"] = 1

    # Remove snowball papers already in corpus (by DOI)
    corpus_dois = set()
    if doi_column in corpus_df.columns:
        corpus_dois = {
            str(d).strip().lower() for d in corpus_df[doi_column] if is_valid(d)
        }

    if doi_column in snowball_df.columns:
        snowball_df = snowball_df[
            ~snowball_df[doi_column].apply(
                lambda x: str(x).strip().lower() in corpus_dois
                if is_valid(x)
                else False
            )
        ]

    n_new = len(snowball_df)
    merged = pd.concat([corpus_df, snowball_df], ignore_index=True)

    logger.info(
        f"Merged: {len(corpus_df)} corpus + {n_new} new snowball = {len(merged)} total"
    )
    return merged
