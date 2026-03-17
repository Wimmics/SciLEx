"""Tests for scilex/citations/citations_tools.py (mocked network calls)."""

from unittest.mock import MagicMock, patch

import pytest

from scilex.citations.citations_tools import (
    countCitations,
    getRefandCitFormatted,
)


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


class TestCountCitations:
    def test_empty_citations(self):
        citations = {"citing": [], "cited": []}
        result = countCitations(citations)
        assert result == {"nb_citations": 0, "nb_cited": 0}

    def test_non_empty_citations(self):
        citations = {"citing": ["10.1/a", "10.1/b"], "cited": ["10.2/x"]}
        result = countCitations(citations)
        assert result["nb_citations"] == 2
        assert result["nb_cited"] == 1

    def test_returns_dict(self):
        result = countCitations({"citing": [], "cited": []})
        assert isinstance(result, dict)

    def test_large_counts(self):
        citations = {"citing": [f"doi_{i}" for i in range(100)], "cited": [f"doi_{i}" for i in range(50)]}
        result = countCitations(citations)
        assert result["nb_citations"] == 100
        assert result["nb_cited"] == 50


class TestGetRefandCitFormatted:
    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_success_returns_dois(self, mock_refs, mock_cits):
        mock_cits.return_value = (
            True,
            _mock_response([{"citing": "10.1/a"}, {"citing": "10.1/b"}]),
            "success",
        )
        mock_refs.return_value = (
            True,
            _mock_response([{"cited": "10.2/x"}]),
            "success",
        )
        citations, stats = getRefandCitFormatted("10.9999/test")
        assert len(citations["citing"]) == 2
        assert len(citations["cited"]) == 1
        assert stats["cit_status"] == "success"
        assert stats["ref_status"] == "success"

    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_failure_returns_empty_lists(self, mock_refs, mock_cits):
        mock_cits.return_value = (False, None, "error")
        mock_refs.return_value = (False, None, "timeout")
        citations, stats = getRefandCitFormatted("10.9999/fail")
        assert citations["citing"] == []
        assert citations["cited"] == []
        assert stats["cit_status"] == "error"
        assert stats["ref_status"] == "timeout"

    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_doi_prefix_stripped(self, mock_refs, mock_cits):
        mock_cits.return_value = (False, None, "error")
        mock_refs.return_value = (False, None, "error")
        getRefandCitFormatted("https://doi.org/10.1/test")
        # Verify getCitations was called with clean DOI (no prefix)
        call_arg = mock_cits.call_args[0][0]
        assert "https://doi.org/" not in call_arg
        assert call_arg == "10.1/test"

    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_empty_response_lists(self, mock_refs, mock_cits):
        mock_cits.return_value = (True, _mock_response([]), "success")
        mock_refs.return_value = (True, _mock_response([]), "success")
        citations, stats = getRefandCitFormatted("10.9999/empty")
        assert citations["citing"] == []
        assert citations["cited"] == []

    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_invalid_json_handled(self, mock_refs, mock_cits):
        bad_response = MagicMock()
        bad_response.json.side_effect = ValueError("bad json")
        mock_cits.return_value = (True, bad_response, "success")
        mock_refs.return_value = (True, bad_response, "success")
        citations, stats = getRefandCitFormatted("10.9999/badjson")
        assert citations["citing"] == []
        assert stats["cit_status"] == "error"

    @patch("scilex.citations.citations_tools.getCitations")
    @patch("scilex.citations.citations_tools.getReferences")
    def test_returns_tuple(self, mock_refs, mock_cits):
        mock_cits.return_value = (False, None, "error")
        mock_refs.return_value = (False, None, "error")
        result = getRefandCitFormatted("10.9999/tuple")
        assert isinstance(result, tuple)
        assert len(result) == 2
