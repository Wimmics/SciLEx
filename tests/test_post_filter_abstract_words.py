"""post_filter: abstract word counts ignore NA and stay index-aligned (no warnings)."""

import warnings

import pandas as pd

from scilex.pipeline.post_filter import apply_post_filters


def test_na_abstract_counts_as_zero_words():
    df = pd.DataFrame({"abstract": ["NA", "one two three"], "title": ["a", "b"]})
    result = apply_post_filters(df, {"min_abstract_words": 1})
    assert result["title"].tolist() == ["b"]


def test_itemtype_then_word_filter_emits_no_reindex_warning():
    df = pd.DataFrame(
        {
            "itemType": ["journalArticle", "preprint", "journalArticle"],
            "abstract": ["one two three", "one two three", "one"],
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = apply_post_filters(
            df,
            {
                "enable_itemtype_filter": True,
                "allowed_item_types": ["journalArticle"],
                "min_abstract_words": 2,
                "max_abstract_words": 10,
            },
        )
    assert result.index.tolist() == [0]
