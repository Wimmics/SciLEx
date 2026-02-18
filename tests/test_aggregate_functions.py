"""Tests for pure functions in scilex.crawlers.aggregate module."""

from scilex.constants import MISSING_VALUE
from scilex.crawlers.aggregate import (
    clean_doi,
    getquality,
    reconstruct_abstract_from_inverted_index,
    safe_get,
    safe_has_key,
)


# -------------------------------------------------------------------------
# safe_get
# -------------------------------------------------------------------------
class TestSafeGet:
    def test_existing_key(self):
        assert safe_get({"a": 1}, "a") == 1

    def test_missing_key_returns_default(self):
        assert safe_get({"a": 1}, "b") is None

    def test_custom_default(self):
        assert safe_get({"a": 1}, "b", default="x") == "x"

    def test_empty_string_value_returns_default(self):
        assert safe_get({"a": ""}, "a") is None

    def test_non_dict_returns_default(self):
        assert safe_get("not a dict", "a") is None

    def test_none_input_returns_default(self):
        assert safe_get(None, "a") is None


# -------------------------------------------------------------------------
# safe_has_key
# -------------------------------------------------------------------------
class TestSafeHasKey:
    def test_existing_key(self):
        assert safe_has_key({"a": 1}, "a") is True

    def test_missing_key(self):
        assert safe_has_key({"a": 1}, "b") is False

    def test_non_dict(self):
        assert safe_has_key("string", "a") is False

    def test_none_input(self):
        assert safe_has_key(None, "a") is False


# -------------------------------------------------------------------------
# clean_doi
# -------------------------------------------------------------------------
class TestCleanDoi:
    def test_already_clean(self):
        assert clean_doi("10.1234/test") == "10.1234/test"

    def test_https_prefix(self):
        assert clean_doi("https://doi.org/10.1234/test") == "10.1234/test"

    def test_http_prefix(self):
        assert clean_doi("http://doi.org/10.1234/test") == "10.1234/test"

    def test_dx_doi_prefix(self):
        assert clean_doi("https://dx.doi.org/10.1234/test") == "10.1234/test"

    def test_http_dx_doi_prefix(self):
        assert clean_doi("http://dx.doi.org/10.1234/test") == "10.1234/test"

    def test_na_returns_missing(self):
        assert clean_doi("NA") == MISSING_VALUE

    def test_none_returns_missing(self):
        assert clean_doi(None) == MISSING_VALUE

    def test_empty_returns_missing(self):
        assert clean_doi("") == MISSING_VALUE

    def test_case_insensitive_prefix(self):
        assert clean_doi("HTTPS://DOI.ORG/10.1234/test") == "10.1234/test"

    def test_preserves_complex_doi(self):
        doi = "10.1021/acsomega.2c06948"
        assert clean_doi(doi) == doi


# -------------------------------------------------------------------------
# getquality
# -------------------------------------------------------------------------
class TestGetQuality:
    def test_all_critical_fields(self):
        row = {"DOI": "10.1234", "title": "Test", "authors": "A", "date": "2024"}
        columns = ["DOI", "title", "authors", "date"]
        score = getquality(row, columns)
        assert score == 20  # 4 critical fields * 5

    def test_important_fields(self):
        row = {"abstract": "text", "journalAbbreviation": "J.", "volume": "1"}
        columns = ["abstract", "journalAbbreviation", "volume"]
        score = getquality(row, columns)
        assert score == 9  # 3 important fields * 3

    def test_volume_and_issue_bonus(self):
        row = {"volume": "1", "issue": "2"}
        columns = ["volume", "issue"]
        score = getquality(row, columns)
        assert score == 7  # 2*3 + 1 bonus

    def test_missing_values_not_counted(self):
        row = {"DOI": "NA", "title": "Test"}
        columns = ["DOI", "title"]
        score = getquality(row, columns)
        assert score == 5  # Only title (critical)

    def test_nice_to_have_fields(self):
        row = {"url": "https://example.com", "language": "en"}
        columns = ["url", "language"]
        score = getquality(row, columns)
        assert score == 2  # 2 * 1

    def test_empty_row(self):
        row = {"DOI": "NA", "title": "NA"}
        columns = ["DOI", "title"]
        score = getquality(row, columns)
        assert score == 0

    def test_mixed_fields(self):
        row = {
            "DOI": "10.1234",
            "title": "Test",
            "abstract": "text",
            "url": "https://example.com",
        }
        columns = ["DOI", "title", "abstract", "url"]
        score = getquality(row, columns)
        assert score == 5 + 5 + 3 + 1  # critical + critical + important + nice


# -------------------------------------------------------------------------
# reconstruct_abstract_from_inverted_index
# -------------------------------------------------------------------------
class TestReconstructAbstractFromInvertedIndex:
    def test_simple_reconstruction(self):
        inverted_index = {"Hello": [0], "world": [1]}
        assert reconstruct_abstract_from_inverted_index(inverted_index) == "Hello world"

    def test_word_at_multiple_positions(self):
        inverted_index = {"the": [0, 2], "cat": [1], "dog": [3]}
        result = reconstruct_abstract_from_inverted_index(inverted_index)
        assert result == "the cat the dog"

    def test_empty_index_returns_none(self):
        assert reconstruct_abstract_from_inverted_index({}) is None

    def test_none_input_returns_none(self):
        assert reconstruct_abstract_from_inverted_index(None) is None

    def test_real_world_example(self):
        """OpenAlex-style inverted index."""
        inverted_index = {
            "We": [0],
            "present": [1],
            "a": [2, 7],
            "novel": [3],
            "approach": [4],
            "to": [5],
            "build": [6],
            "knowledge": [8],
            "graph.": [9],
        }
        result = reconstruct_abstract_from_inverted_index(inverted_index)
        assert result == "We present a novel approach to build a knowledge graph."

    def test_single_word(self):
        inverted_index = {"Abstract": [0]}
        assert reconstruct_abstract_from_inverted_index(inverted_index) == "Abstract"
