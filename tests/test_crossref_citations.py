"""Tests for CrossRef batch citation lookup.

Tests the getCrossRefCitationsBatch function and its integration
into the citation pipeline (Cache → SS → CrossRef → OpenCitations).
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# getCrossRefCitationsBatch unit tests (mocked, no network)
# ============================================================================


class TestGetCrossRefCitationsBatch:
    """Test the batch CrossRef lookup function."""

    def _get_fn(self):
        from scilex.citations.citations_tools import getCrossRefCitationsBatch

        return getCrossRefCitationsBatch

    @patch("scilex.citations.citations_tools.requests.get")
    def test_basic_batch_lookup(self, mock_get):
        """Batch lookup returns correct DOI→(cit, ref) mapping."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1234/test.001",
                        "is-referenced-by-count": 42,
                        "references-count": 15,
                    },
                    {
                        "DOI": "10.1234/test.002",
                        "is-referenced-by-count": 7,
                        "references-count": 30,
                    },
                ]
            }
        }
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        result = fn.__wrapped__.__wrapped__.__wrapped__(
            ["10.1234/test.001", "10.1234/test.002"]
        )

        assert result == {
            "10.1234/test.001": (42, 15),
            "10.1234/test.002": (7, 30),
        }

    @patch("scilex.citations.citations_tools.requests.get")
    def test_missing_dois_omitted(self, mock_get):
        """DOIs not found in CrossRef are simply omitted from result."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1234/found",
                        "is-referenced-by-count": 5,
                        "references-count": 10,
                    },
                ]
            }
        }
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        result = fn.__wrapped__.__wrapped__.__wrapped__(
            ["10.1234/found", "10.9999/not-in-crossref"]
        )

        assert "10.1234/found" in result
        assert "10.9999/not-in-crossref" not in result

    @patch("scilex.citations.citations_tools.requests.get")
    def test_empty_input_returns_empty(self, mock_get):
        """Empty DOI list returns empty dict without API call."""
        fn = self._get_fn()
        result = fn.__wrapped__.__wrapped__.__wrapped__([])

        assert result == {}
        mock_get.assert_not_called()

    @patch("scilex.citations.citations_tools.requests.get")
    def test_doi_case_normalization(self, mock_get):
        """Result keys are lowercased for consistent lookup."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1234/UPPER.Case",
                        "is-referenced-by-count": 3,
                        "references-count": 8,
                    },
                ]
            }
        }
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        result = fn.__wrapped__.__wrapped__.__wrapped__(["10.1234/UPPER.Case"])

        assert "10.1234/upper.case" in result

    @patch("scilex.citations.citations_tools.requests.get")
    def test_mailto_included_in_url(self, mock_get):
        """When mailto is provided, it appears in the request URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        fn.__wrapped__.__wrapped__.__wrapped__(
            ["10.1234/test"], mailto="user@example.org"
        )

        url = mock_get.call_args[0][0]
        assert "mailto=user@example.org" in url

    @patch("scilex.citations.citations_tools.requests.get")
    def test_no_mailto_excluded_from_url(self, mock_get):
        """When mailto is None, it does not appear in the URL."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        fn.__wrapped__.__wrapped__.__wrapped__(["10.1234/test"])

        url = mock_get.call_args[0][0]
        assert "mailto" not in url

    @patch("scilex.citations.citations_tools.requests.get")
    def test_url_contains_filter_and_select(self, mock_get):
        """Request URL contains proper filter and select parameters."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        fn.__wrapped__.__wrapped__.__wrapped__(["10.1234/a", "10.1234/b"])

        url = mock_get.call_args[0][0]
        assert "filter=doi:10.1234/a,doi:10.1234/b" in url
        assert "select=DOI,is-referenced-by-count,references-count" in url
        assert "rows=2" in url

    @patch("scilex.citations.citations_tools.requests.get")
    def test_missing_count_fields_default_to_zero(self, mock_get):
        """If CrossRef omits count fields, they default to 0."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1234/sparse",
                        # no is-referenced-by-count or references-count
                    },
                ]
            }
        }
        mock_get.return_value = mock_resp

        fn = self._get_fn()
        result = fn.__wrapped__.__wrapped__.__wrapped__(["10.1234/sparse"])

        assert result["10.1234/sparse"] == (0, 0)


# ============================================================================
# getCrossRefCitation (single-DOI wrapper) unit tests
# ============================================================================


class TestGetCrossRefCitation:
    """Test the single-DOI CrossRef lookup wrapper."""

    @patch("scilex.citations.citations_tools.getCrossRefCitationsBatch")
    def test_returns_tuple_when_found(self, mock_batch):
        """Returns (cit, ref) tuple when DOI is found."""
        mock_batch.return_value = {"10.1234/test": (42, 15)}

        from scilex.citations.citations_tools import getCrossRefCitation

        result = getCrossRefCitation("10.1234/test")
        assert result == (42, 15)
        mock_batch.assert_called_once_with(["10.1234/test"], mailto=None)

    @patch("scilex.citations.citations_tools.getCrossRefCitationsBatch")
    def test_returns_none_when_not_found(self, mock_batch):
        """Returns None when DOI is not in CrossRef."""
        mock_batch.return_value = {}

        from scilex.citations.citations_tools import getCrossRefCitation

        result = getCrossRefCitation("10.9999/missing")
        assert result is None

    @patch("scilex.citations.citations_tools.getCrossRefCitationsBatch")
    def test_returns_none_on_exception(self, mock_batch):
        """Returns None when batch call raises an exception."""
        mock_batch.side_effect = Exception("API error")

        from scilex.citations.citations_tools import getCrossRefCitation

        result = getCrossRefCitation("10.1234/test")
        assert result is None

    @patch("scilex.citations.citations_tools.getCrossRefCitationsBatch")
    def test_passes_mailto(self, mock_batch):
        """Passes mailto parameter to batch function."""
        mock_batch.return_value = {"10.1234/test": (5, 3)}

        from scilex.citations.citations_tools import getCrossRefCitation

        getCrossRefCitation("10.1234/test", mailto="user@example.org")
        mock_batch.assert_called_once_with(["10.1234/test"], mailto="user@example.org")


# ============================================================================
# CROSSREF_BATCH_SIZE constant
# ============================================================================


class TestCrossRefBatchSize:
    def test_batch_size_is_20(self):
        from scilex.citations.citations_tools import CROSSREF_BATCH_SIZE

        assert CROSSREF_BATCH_SIZE == 20


# ============================================================================
# Integration: CrossRef tier in _fetch_citation_for_paper
# ============================================================================


# Mock config loading for aggregate_collect import
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
def _patch_aggregate_configs():
    """Ensure aggregate_collect can be imported by mocking config loading."""
    if "scilex.aggregate_collect" not in sys.modules:
        with (
            patch("scilex.crawlers.utils.load_all_configs", return_value=_MOCK_CONFIGS),
            patch("scilex.logging_config.setup_logging"),
        ):
            import scilex.aggregate_collect  # noqa: F401
    yield


def _get_fetch_fn():
    from scilex.aggregate_collect import _fetch_citation_for_paper

    return _fetch_citation_for_paper


class TestCrossRefTierInPipeline:
    """Test that CrossRef tier is correctly used between SS and OpenCitations."""

    @patch("scilex.aggregate_collect.cit_tools.getRefandCitFormatted")
    @patch(
        "scilex.aggregate_collect.cit_tools.getCrossRefCitation", return_value=(25, 12)
    )
    @patch("scilex.citations.cache.cache_citation")
    @patch("scilex.citations.cache.get_cached_citation", return_value=None)
    def test_crossref_used_when_found(
        self, mock_cache_get, mock_cache_set, mock_cr, mock_oc
    ):
        """When CrossRef returns data, it is used (no OC call)."""
        fetch = _get_fetch_fn()
        extras = [""] * 5
        nb_citeds = [""] * 5
        nb_citations = [""] * 5
        stats = {
            "success": 0,
            "timeout": 0,
            "error": 0,
            "no_doi": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "ss_used": 0,
            "cr_used": 0,
            "opencitations_used": 0,
        }

        result = fetch(
            index=2,
            doi="10.1234/test",
            stats=stats,
            checkpoint_interval=None,
            checkpoint_path=None,
            extras=extras,
            nb_citeds=nb_citeds,
            nb_citations=nb_citations,
            cache_path="/tmp/test.db",
            ss_citation_count=None,
            ss_reference_count=None,
            crossref_mailto=None,
        )

        assert result["status"] == "cr_used"
        assert stats["cr_used"] == 1
        assert nb_citations[2] == 25
        assert nb_citeds[2] == 12
        mock_oc.assert_not_called()  # No OpenCitations call
        mock_cache_set.assert_called_once()  # Cached for future runs

    @patch("scilex.aggregate_collect.cit_tools.getRefandCitFormatted")
    @patch("scilex.aggregate_collect.cit_tools.getCrossRefCitation", return_value=None)
    @patch("scilex.citations.cache.cache_citation")
    @patch("scilex.citations.cache.get_cached_citation", return_value=None)
    def test_cr_miss_falls_through_to_opencitations(
        self, mock_cache_get, mock_cache_set, mock_cr, mock_oc
    ):
        """When CrossRef returns None, falls through to OpenCitations."""
        mock_oc.return_value = (
            {"citing": ["a"], "cited": ["b", "c"]},
            {"cit_status": "success", "ref_status": "success"},
        )

        fetch = _get_fetch_fn()
        extras = [""] * 5
        nb_citeds = [""] * 5
        nb_citations = [""] * 5
        stats = {
            "success": 0,
            "timeout": 0,
            "error": 0,
            "no_doi": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "ss_used": 0,
            "cr_used": 0,
            "opencitations_used": 0,
        }

        result = fetch(
            index=1,
            doi="10.1234/not-in-cr",
            stats=stats,
            checkpoint_interval=None,
            checkpoint_path=None,
            extras=extras,
            nb_citeds=nb_citeds,
            nb_citations=nb_citations,
            cache_path="/tmp/test.db",
            ss_citation_count=None,
            ss_reference_count=None,
            crossref_mailto=None,
        )

        assert result["status"] == "success"
        assert stats["opencitations_used"] == 1
        assert stats["cr_used"] == 0
        mock_oc.assert_called_once()

    @patch(
        "scilex.aggregate_collect.cit_tools.getCrossRefCitation", return_value=(25, 12)
    )
    @patch("scilex.citations.cache.cache_citation")
    @patch("scilex.citations.cache.get_cached_citation", return_value=None)
    def test_ss_takes_priority_over_crossref(
        self, mock_cache_get, mock_cache_set, mock_cr
    ):
        """SS data (tier 2) is used — CrossRef is never called."""
        fetch = _get_fetch_fn()
        extras = [""] * 3
        nb_citeds = [""] * 3
        nb_citations = [""] * 3
        stats = {
            "success": 0,
            "timeout": 0,
            "error": 0,
            "no_doi": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "ss_used": 0,
            "cr_used": 0,
            "opencitations_used": 0,
        }

        result = fetch(
            index=0,
            doi="10.1234/test",
            stats=stats,
            checkpoint_interval=None,
            checkpoint_path=None,
            extras=extras,
            nb_citeds=nb_citeds,
            nb_citations=nb_citations,
            cache_path="/tmp/test.db",
            ss_citation_count=30,
            ss_reference_count=10,
            crossref_mailto=None,
        )

        assert result["status"] == "ss_used"
        assert stats["ss_used"] == 1
        assert stats["cr_used"] == 0
        mock_cr.assert_not_called()  # CrossRef never reached
        # SS values used
        assert nb_citations[0] == 30
        assert nb_citeds[0] == 10

    @patch("scilex.aggregate_collect.cit_tools.getRefandCitFormatted")
    @patch(
        "scilex.aggregate_collect.cit_tools.getCrossRefCitation", return_value=(25, 12)
    )
    @patch("scilex.citations.cache.cache_citation")
    @patch("scilex.citations.cache.get_cached_citation", return_value=None)
    def test_crossref_mailto_passed_through(
        self, mock_cache_get, mock_cache_set, mock_cr, mock_oc
    ):
        """CrossRef is called with the mailto parameter."""
        fetch = _get_fetch_fn()
        extras = [""] * 3
        nb_citeds = [""] * 3
        nb_citations = [""] * 3
        stats = {
            "success": 0,
            "timeout": 0,
            "error": 0,
            "no_doi": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "ss_used": 0,
            "cr_used": 0,
            "opencitations_used": 0,
        }

        fetch(
            index=0,
            doi="10.1234/test",
            stats=stats,
            checkpoint_interval=None,
            checkpoint_path=None,
            extras=extras,
            nb_citeds=nb_citeds,
            nb_citations=nb_citations,
            cache_path="/tmp/test.db",
            ss_citation_count=None,
            ss_reference_count=None,
            crossref_mailto="user@example.org",
        )

        mock_cr.assert_called_once_with("10.1234/test", mailto="user@example.org")
