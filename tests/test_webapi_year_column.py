"""The web API derives years from mixed date formats."""

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from scilex.webapi.scilex_api import _add_year_column  # noqa: E402
from scilex.webapi.web_interface import add_year_column  # noqa: E402


@pytest.mark.parametrize("add_year", [_add_year_column, add_year_column])
def test_bare_year_after_full_date_is_kept(add_year):
    df = pd.DataFrame({"date": ["2024-02-20", "2024", "NA", "2023-09-05"]})
    add_year(df)
    assert df["year"].tolist()[:2] == [2024, 2024]
    assert pd.isna(df["year"][2])
    assert df["year"][3] == 2023
