"""Tests for scilex.keyword_validation module."""

import pandas as pd

from scilex.keyword_validation import (
    check_keyword_in_text,
    check_keywords_in_paper,
    filter_by_keywords,
    normalize_text,
)


# -------------------------------------------------------------------------
# normalize_text
# -------------------------------------------------------------------------
class TestNormalizeText:
    def test_simple_lowercase(self):
        assert normalize_text("Hello World") == "hello world"

    def test_na_returns_empty(self):
        assert normalize_text("NA") == ""

    def test_none_returns_empty(self):
        assert normalize_text(None) == ""

    def test_dict_format_paragraphs(self):
        text = {"p": ["First paragraph.", "Second paragraph."]}
        assert normalize_text(text) == "first paragraph. second paragraph."

    def test_dict_without_p_key(self):
        # Non-paragraph dict should be stringified
        text = {"other": "value"}
        result = normalize_text(text)
        assert "other" in result

    def test_numeric_input(self):
        assert normalize_text(42) == "42"


# -------------------------------------------------------------------------
# check_keyword_in_text
# -------------------------------------------------------------------------
class TestCheckKeywordInText:
    def test_keyword_found(self):
        assert (
            check_keyword_in_text("machine learning", "A paper about machine learning")
            is True
        )

    def test_keyword_case_insensitive(self):
        assert (
            check_keyword_in_text("Machine Learning", "machine learning study") is True
        )

    def test_keyword_not_found(self):
        assert (
            check_keyword_in_text("quantum computing", "A paper about biology") is False
        )

    def test_empty_text(self):
        assert check_keyword_in_text("test", "") is False

    def test_na_text(self):
        assert check_keyword_in_text("test", "NA") is False

    def test_none_text(self):
        assert check_keyword_in_text("test", None) is False

    def test_empty_keyword(self):
        assert check_keyword_in_text("", "some text") is False

    def test_phrase_matching(self):
        assert (
            check_keyword_in_text(
                "knowledge graph", "Building a knowledge graph system"
            )
            is True
        )

    def test_partial_word_match(self):
        # "learn" should match inside "learning"
        assert check_keyword_in_text("learn", "deep learning approach") is True


# -------------------------------------------------------------------------
# check_keywords_in_paper
# -------------------------------------------------------------------------
class TestCheckKeywordsInPaper:
    def test_single_group_match(self):
        record = {
            "title": "Machine learning for NLP",
            "abstract": "We use deep learning.",
        }
        keywords = [["machine learning", "deep learning"], []]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is True
        assert "machine learning" in matched

    def test_single_group_no_match(self):
        record = {"title": "Biology study", "abstract": "Cells and proteins."}
        keywords = [["machine learning"], []]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is False
        assert matched == []

    def test_dual_group_both_match(self):
        record = {
            "title": "Knowledge graph completion with LLM",
            "abstract": "We use large language models.",
        }
        keywords = [["knowledge graph"], ["LLM", "large language model"]]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is True
        assert len(matched) >= 2  # At least one from each group

    def test_dual_group_only_first_matches(self):
        record = {"title": "Knowledge graph survey", "abstract": "Graph methods."}
        keywords = [["knowledge graph"], ["LLM"]]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is False

    def test_dual_group_only_second_matches(self):
        record = {"title": "LLM benchmark", "abstract": "Large language models."}
        keywords = [["knowledge graph"], ["LLM"]]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is False

    def test_empty_keywords(self):
        record = {"title": "Test", "abstract": "Test"}
        found, matched = check_keywords_in_paper(record, [[]])
        # Single group with no keywords - no match possible
        assert found is False

    def test_match_in_abstract_only(self):
        record = {"title": "A study", "abstract": "We use machine learning techniques."}
        keywords = [["machine learning"], []]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is True

    def test_match_in_title_only(self):
        record = {"title": "Machine learning survey", "abstract": "NA"}
        keywords = [["machine learning"], []]
        found, matched = check_keywords_in_paper(record, keywords)
        assert found is True


# -------------------------------------------------------------------------
# filter_by_keywords
# -------------------------------------------------------------------------
class TestFilterByKeywords:
    def _make_df(self):
        return pd.DataFrame(
            [
                {
                    "title": "ML for graphs",
                    "abstract": "Machine learning on knowledge graphs",
                },
                {"title": "Biology paper", "abstract": "Protein folding analysis"},
                {"title": "LLM survey", "abstract": "Large language model benchmarks"},
            ]
        )

    def test_non_strict_returns_all(self):
        df = self._make_df()
        result = filter_by_keywords(df, [["machine learning"], []], strict=False)
        assert len(result) == 3

    def test_strict_filters_papers(self):
        df = self._make_df()
        result = filter_by_keywords(df, [["machine learning"], []], strict=True)
        assert len(result) == 1
        assert "ML for graphs" in result["title"].values

    def test_strict_dual_group(self):
        df = self._make_df()
        result = filter_by_keywords(
            df, [["machine learning"], ["knowledge graph"]], strict=True
        )
        assert len(result) == 1

    def test_empty_df(self):
        df = pd.DataFrame(columns=["title", "abstract"])
        result = filter_by_keywords(df, [["test"], []], strict=True)
        assert len(result) == 0

    def test_no_matches_strict(self):
        df = self._make_df()
        result = filter_by_keywords(df, [["quantum computing"], []], strict=True)
        assert len(result) == 0
