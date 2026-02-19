"""Tests for scilex.constants utility functions."""

import numpy as np
import pandas as pd
import pytest

from scilex.constants import (
    MISSING_VALUE,
    is_missing,
    is_valid,
    normalize_path_component,
    safe_str,
)


class TestIsValid:
    """Tests for is_valid() - checks if value is not null/NaN/missing."""

    @pytest.mark.parametrize(
        "value",
        [
            "some text",
            "hello world",
            "10.1234/test",
            "0",
            "false",
            " text ",
            123,
            0,
            True,
            False,
        ],
    )
    def test_valid_values_return_true(self, value):
        assert is_valid(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "NA",
            "na",
            "Na",
            "nA",
            "",
            "   ",
            None,
            pd.NA,
            float("nan"),
            np.nan,
        ],
    )
    def test_invalid_values_return_false(self, value):
        assert is_valid(value) is False

    def test_missing_value_constant_is_invalid(self):
        assert is_valid(MISSING_VALUE) is False

    def test_whitespace_only_is_invalid(self):
        assert is_valid("  \t\n  ") is False


class TestIsMissing:
    """Tests for is_missing() - inverse of is_valid()."""

    def test_missing_na_string(self):
        assert is_missing("NA") is True

    def test_missing_none(self):
        assert is_missing(None) is True

    def test_missing_empty_string(self):
        assert is_missing("") is True

    def test_not_missing_valid_text(self):
        assert is_missing("valid text") is False

    def test_not_missing_number(self):
        assert is_missing(42) is False

    def test_inverse_of_is_valid(self):
        """is_missing should always be the inverse of is_valid."""
        test_values = ["NA", None, "", "valid", 42, pd.NA, float("nan")]
        for val in test_values:
            assert is_missing(val) == (not is_valid(val))


class TestSafeStr:
    """Tests for safe_str() - safely convert to string with default."""

    def test_valid_value_converts_to_string(self):
        assert safe_str("hello") == "hello"

    def test_number_converts_to_string(self):
        assert safe_str(42) == "42"

    def test_none_returns_default(self):
        assert safe_str(None) == MISSING_VALUE

    def test_na_string_returns_default(self):
        assert safe_str("NA") == MISSING_VALUE

    def test_empty_string_returns_default(self):
        assert safe_str("") == MISSING_VALUE

    def test_nan_returns_default(self):
        assert safe_str(float("nan")) == MISSING_VALUE

    def test_custom_default(self):
        assert safe_str(None, default="Unknown") == "Unknown"

    def test_custom_default_with_na(self):
        assert safe_str("NA", default="N/A") == "N/A"


class TestNormalizePathComponent:
    """Tests for normalize_path_component()."""

    def test_leading_slash(self):
        assert (
            normalize_path_component("/aggregated_results.csv")
            == "aggregated_results.csv"
        )

    def test_trailing_slash(self):
        assert normalize_path_component("collect_name/") == "collect_name"

    def test_both_slashes(self):
        assert normalize_path_component("/dirname/") == "dirname"

    def test_normal_path(self):
        assert normalize_path_component("normal_path") == "normal_path"

    def test_empty_string(self):
        assert normalize_path_component("") == ""
