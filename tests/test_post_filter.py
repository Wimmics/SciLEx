"""Tests for scilex.pipeline.post_filter — shared post-aggregation filtering."""

import pandas as pd

from scilex.pipeline.post_filter import apply_post_filters


def _make_df(papers):
    return pd.DataFrame(papers)


class TestApplyPostFilters:
    def test_empty_df_returns_empty(self):
        df = _make_df([])
        result = apply_post_filters(df, {})
        assert len(result) == 0

    def test_no_filters_returns_all(self):
        df = _make_df([{"title": "a"}, {"title": "b"}])
        result = apply_post_filters(df, {})
        assert len(result) == 2

    def test_itemtype_filter(self):
        df = _make_df(
            [
                {"itemType": "journalArticle"},
                {"itemType": "conferencePaper"},
                {"itemType": "preprint"},
            ]
        )
        result = apply_post_filters(
            df,
            {
                "enable_itemtype_filter": True,
                "allowed_item_types": ["journalArticle", "conferencePaper"],
            },
        )
        assert len(result) == 2
        assert set(result["itemType"]) == {"journalArticle", "conferencePaper"}

    def test_itemtype_filter_with_item_type_column(self):
        """Supports alternative column name 'item_type'."""
        df = _make_df(
            [
                {"item_type": "journalArticle"},
                {"item_type": "preprint"},
            ]
        )
        result = apply_post_filters(
            df,
            {
                "enable_itemtype_filter": True,
                "allowed_item_types": ["journalArticle"],
            },
        )
        assert len(result) == 1

    def test_min_abstract_words(self):
        df = _make_df(
            [
                {"abstract": "short"},
                {"abstract": "this is a longer abstract with more words for testing"},
            ]
        )
        result = apply_post_filters(df, {"min_abstract_words": 5})
        assert len(result) == 1

    def test_max_abstract_words(self):
        df = _make_df(
            [
                {"abstract": "short"},
                {"abstract": "this is a longer abstract with more words for testing"},
            ]
        )
        result = apply_post_filters(df, {"max_abstract_words": 3})
        assert len(result) == 1

    def test_relevance_ranking(self):
        df = _make_df(
            [
                {"title": "low", "relevance_score": 2.0},
                {"title": "high", "relevance_score": 8.0},
                {"title": "mid", "relevance_score": 5.0},
            ]
        )
        result = apply_post_filters(df, {"apply_relevance_ranking": True})
        assert result.iloc[0]["title"] == "high"
        assert result.iloc[2]["title"] == "low"

    def test_max_papers(self):
        df = _make_df([{"title": f"paper{i}"} for i in range(10)])
        result = apply_post_filters(df, {"max_papers": 3})
        assert len(result) == 3

    def test_combined_filters(self):
        df = _make_df(
            [
                {
                    "itemType": "journalArticle",
                    "abstract": "a long enough abstract here",
                    "relevance_score": 5.0,
                },
                {
                    "itemType": "preprint",
                    "abstract": "a long enough abstract here",
                    "relevance_score": 8.0,
                },
                {
                    "itemType": "journalArticle",
                    "abstract": "short",
                    "relevance_score": 9.0,
                },
                {
                    "itemType": "journalArticle",
                    "abstract": "another long enough abstract text",
                    "relevance_score": 3.0,
                },
            ]
        )
        result = apply_post_filters(
            df,
            {
                "enable_itemtype_filter": True,
                "allowed_item_types": ["journalArticle"],
                "min_abstract_words": 3,
                "apply_relevance_ranking": True,
                "max_papers": 1,
            },
        )
        assert len(result) == 1
        assert result.iloc[0]["relevance_score"] == 5.0

    def test_does_not_modify_original(self):
        df = _make_df([{"title": "a"}, {"title": "b"}])
        original_len = len(df)
        apply_post_filters(df, {"max_papers": 1})
        assert len(df) == original_len
