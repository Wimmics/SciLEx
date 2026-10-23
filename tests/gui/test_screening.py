"""Tests of the screening decisions file."""

from pathlib import Path

import pandas as pd

from scilex.gui.services import screening
from scilex.gui.services.workspace import Review


def make_review(tmp_path: Path) -> Review:
    review = Review(folder=tmp_path, name="rag", output_root=tmp_path / "output")
    review.collection_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "itemType": ["journalArticle", "conferencePaper"],
            "title": ["Graph RAG", "Metabolomics KG"],
            "DOI": ["https://doi.org/10.1/ABC", "NA"],
            "date": ["2024-01-01", "2023"],
        }
    ).to_csv(review.results_path, sep=";")
    return review


def test_paper_key_prefers_doi_then_title_and_year():
    assert screening.paper_key({"DOI": "10.1/ABC", "title": "x"}) == "doi:10.1/abc"
    key = screening.paper_key(
        {"DOI": "NA", "title": "Metabolomics: KG!", "date": "2023"}
    )
    assert key == "title:metabolomics kg|2023"


def test_decisions_round_trip_and_survive_reaggregation(tmp_path):
    review = make_review(tmp_path)
    results = screening.load_results(review)
    first, second = results["paper_key"]
    screening.set_decision(review, first, screening.INCLUDE, "core paper")
    screening.set_decision(review, second, screening.EXCLUDE)

    decisions = screening.load_decisions(review)
    assert decisions[first].note == "core paper"
    assert list(screening.included_results(review)["title"]) == ["Graph RAG"]

    # Re-aggregation drops the second paper: its decision becomes an orphan.
    pd.DataFrame(
        {
            "itemType": ["journalArticle"],
            "title": ["Graph RAG"],
            "DOI": ["10.1/abc"],
            "date": ["2024"],
        }
    ).to_csv(review.results_path, sep=";")
    assert screening.orphan_keys(review, screening.load_results(review)) == [second]

    screening.set_decision(review, second, None)
    assert second not in screening.load_decisions(review)
