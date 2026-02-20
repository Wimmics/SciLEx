"""Tests for functions in scilex.aggregate_collect module.

This module loads config files at import time, so we mock load_all_configs
before importing the functions under test.
"""

import sys
from unittest.mock import patch

import pytest

from scilex.constants import CitationFilterConfig

# Mock the config loading that happens at module level in aggregate_collect
_MOCK_CONFIGS = {
    "main_config": {
        "collect_name": "test_collect",
        "keywords": [["test"], []],
        "years": [2024],
        "apis": ["SemanticScholar"],
        "output_dir": "/tmp/test_output",
    },
    "api_config": {},
}


@pytest.fixture(autouse=True)
def _patch_aggregate_collect_configs():
    """Ensure aggregate_collect can be imported by mocking config loading."""
    # Only patch if not already imported
    if "scilex.aggregate_collect" not in sys.modules:
        with (
            patch("scilex.crawlers.utils.load_all_configs", return_value=_MOCK_CONFIGS),
            patch("scilex.logging_config.setup_logging"),
        ):
            # Force import with mocked configs
            import scilex.aggregate_collect  # noqa: F401

    yield


def _get_functions():
    """Import the functions after configs are mocked."""
    from scilex.aggregate_collect import (
        FilteringTracker,
        _calculate_required_citations,
        _record_passes_text_filter,
    )

    return FilteringTracker, _calculate_required_citations, _record_passes_text_filter


# -------------------------------------------------------------------------
# _calculate_required_citations
# -------------------------------------------------------------------------
class TestCalculateRequiredCitations:
    def test_none_returns_grace_period(self):
        _, calc, _ = _get_functions()
        assert calc(None) == CitationFilterConfig.GRACE_PERIOD_CITATIONS

    def test_nan_returns_grace_period(self):
        _, calc, _ = _get_functions()
        assert calc(float("nan")) == CitationFilterConfig.GRACE_PERIOD_CITATIONS

    def test_grace_period(self):
        """Papers 0-18 months old require 0 citations."""
        _, calc, _ = _get_functions()
        assert calc(0) == 0
        assert calc(12) == 0
        assert calc(18) == 0

    def test_early_threshold(self):
        """Papers 18-21 months old require 1+ citations."""
        _, calc, _ = _get_functions()
        assert calc(19) == CitationFilterConfig.EARLY_CITATIONS
        assert calc(21) == CitationFilterConfig.EARLY_CITATIONS

    def test_medium_threshold(self):
        """Papers 21-24 months old require 3+ citations."""
        _, calc, _ = _get_functions()
        assert calc(22) == CitationFilterConfig.MEDIUM_CITATIONS
        assert calc(24) == CitationFilterConfig.MEDIUM_CITATIONS

    def test_mature_threshold(self):
        """Papers 24-36 months old start at 5, increase gradually."""
        _, calc, _ = _get_functions()
        result = calc(25)
        assert result >= CitationFilterConfig.MATURE_BASE_CITATIONS

    def test_established_threshold(self):
        """Papers 36+ months require 10+ citations."""
        _, calc, _ = _get_functions()
        result = calc(40)
        assert result >= CitationFilterConfig.ESTABLISHED_BASE_CITATIONS

    def test_very_old_paper(self):
        """Very old papers (60+ months) need even more citations."""
        _, calc, _ = _get_functions()
        result_60 = calc(60)
        result_36 = calc(37)
        assert result_60 >= result_36

    def test_monotonic_increase(self):
        """Required citations should never decrease as age increases."""
        _, calc, _ = _get_functions()
        prev = 0
        for months in range(0, 60, 3):
            current = calc(months)
            assert current >= prev, f"Decreased at {months} months: {current} < {prev}"
            prev = current


# -------------------------------------------------------------------------
# _record_passes_text_filter
# -------------------------------------------------------------------------
class TestRecordPassesTextFilter:
    def test_keyword_in_title(self):
        _, _, passes = _get_functions()
        record = {"title": "Machine learning for NLP", "abstract": "NA"}
        assert passes(record, ["machine learning"]) is True

    def test_keyword_in_abstract(self):
        _, _, passes = _get_functions()
        record = {"title": "A study", "abstract": "We use deep learning techniques."}
        assert passes(record, ["deep learning"]) is True

    def test_no_match(self):
        _, _, passes = _get_functions()
        record = {"title": "Biology paper", "abstract": "Protein folding."}
        assert passes(record, ["machine learning"]) is False

    def test_empty_keywords_passes(self):
        _, _, passes = _get_functions()
        record = {"title": "Any paper", "abstract": "Any content."}
        assert passes(record, []) is True

    def test_dual_keyword_groups_both_match(self):
        _, _, passes = _get_functions()
        record = {
            "title": "Knowledge graph with LLM",
            "abstract": "We combine knowledge graphs and large language models.",
        }
        keyword_groups = [["knowledge graph"], ["LLM", "large language model"]]
        assert passes(record, [], keyword_groups=keyword_groups) is True

    def test_dual_keyword_groups_only_first_matches(self):
        _, _, passes = _get_functions()
        record = {
            "title": "Knowledge graph survey",
            "abstract": "We survey graph methods.",
        }
        keyword_groups = [["knowledge graph"], ["LLM"]]
        assert passes(record, [], keyword_groups=keyword_groups) is False

    def test_dual_keyword_groups_one_empty_fallback(self):
        """If one group is empty, falls back to single-group mode."""
        _, _, passes = _get_functions()
        record = {
            "title": "Machine learning paper",
            "abstract": "Deep learning study.",
        }
        keyword_groups = [["machine learning"], []]
        assert passes(record, [], keyword_groups=keyword_groups) is True

    def test_case_insensitive(self):
        _, _, passes = _get_functions()
        record = {"title": "MACHINE LEARNING Paper", "abstract": "NA"}
        assert passes(record, ["machine learning"]) is True


# -------------------------------------------------------------------------
# FilteringTracker
# -------------------------------------------------------------------------
class TestFilteringTracker:
    def test_set_initial(self):
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        tracker.set_initial(100, "Raw papers")
        assert tracker.initial_count == 100
        assert len(tracker.stages) == 1
        assert tracker.stages[0]["papers"] == 100

    def test_add_stage(self):
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        tracker.set_initial(100)
        tracker.add_stage("Dedup", 80, "Removed duplicates")
        assert len(tracker.stages) == 2
        assert tracker.stages[1]["papers"] == 80
        assert tracker.stages[1]["removed"] == 20
        assert tracker.stages[1]["removal_rate"] == 20.0

    def test_add_stage_without_initial(self):
        """First add_stage call sets initial if not yet set."""
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        tracker.add_stage("Initial", 100)
        assert tracker.initial_count == 100

    def test_generate_report(self):
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        tracker.set_initial(100)
        tracker.add_stage("Dedup", 80)
        tracker.add_stage("Quality", 60)
        report = tracker.generate_report()
        assert "FILTERING PIPELINE SUMMARY" in report
        assert "100" in report
        assert "60" in report

    def test_generate_report_empty(self):
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        assert "No filtering data" in tracker.generate_report()

    def test_multiple_stages_cumulative(self):
        Tracker, _, _ = _get_functions()
        tracker = Tracker()
        tracker.set_initial(1000)
        tracker.add_stage("Step 1", 800)
        tracker.add_stage("Step 2", 500)
        tracker.add_stage("Step 3", 300)
        report = tracker.generate_report()
        assert "300" in report
        assert "Retention rate" in report


# -------------------------------------------------------------------------
# _apply_time_aware_citation_filter
# -------------------------------------------------------------------------
class TestApplyTimeAwareCitationFilter:
    def _get_filter(self):
        from scilex.aggregate_collect import _apply_time_aware_citation_filter

        return _apply_time_aware_citation_filter

    def _make_df(self, papers):
        import pandas as pd

        return pd.DataFrame(papers)

    def test_recent_paper_passes_with_zero_citations(self):
        """Papers <18 months old should not be filtered."""
        from datetime import date, timedelta

        recent_date = (date.today() - timedelta(days=6 * 30)).strftime("%Y-%m-%d")
        df = self._make_df([
            {"DOI": "10.1/a", "nb_citation": "0", "date": recent_date},
        ])
        fn = self._get_filter()
        result = fn(df)
        assert len(result) == 1

    def test_old_paper_with_zero_citations_filtered(self):
        """Papers >36 months old with 0 citations should be removed."""
        df = self._make_df([
            {"DOI": "10.1/a", "nb_citation": "0", "date": "2020-01-01"},
        ])
        fn = self._get_filter()
        result = fn(df)
        assert len(result) == 0

    def test_no_doi_bypasses_filter(self):
        """Papers without DOI should not be filtered regardless of citations."""
        df = self._make_df([
            {"DOI": "NA", "nb_citation": "0", "date": "2018-01-01"},
        ])
        fn = self._get_filter()
        result = fn(df)
        assert len(result) == 1

    def test_citation_threshold_column_added(self):
        """The citation_threshold column must be present in output."""
        df = self._make_df([
            {"DOI": "10.1/a", "nb_citation": "100", "date": "2024-01-01"},
        ])
        fn = self._get_filter()
        result = fn(df)
        assert "citation_threshold" in result.columns
