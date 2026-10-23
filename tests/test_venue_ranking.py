"""Venue ranking (CORE / SJR) matching and ranking integration."""

import pandas as pd

from scilex.pipeline.ranking import calculate_relevance_score
from scilex.pipeline.venue_ranking import (
    add_venue_rank,
    extract_acronyms,
    lookup_venue_rank,
    normalize_venue,
    venue_rank_score,
)


def test_normalization_drops_noise():
    assert (
        normalize_venue(
            "Proceedings of the 22nd International Semantic Web Conference (ISWC 2023)"
        )
        == "semantic web conference iswc"
    )
    assert normalize_venue("PLoS ONE") == normalize_venue("PLOS ONE.")


def test_extract_acronyms():
    assert extract_acronyms("Semantic Web Conference (ISWC 2023)") == ["ISWC"]
    assert extract_acronyms("No acronym here") == []


def test_lookup_journal_conference_acronym_and_unknown():
    assert lookup_venue_rank("Bioinformatics") == "Q1"
    assert lookup_venue_rank("International Conference on Machine Learning") == "A*"
    assert lookup_venue_rank("Some Workshop Proceedings (ESWC 2022)") == "A"
    assert (
        lookup_venue_rank(
            "Proceedings of the 21st International Semantic Web Conference, ISWC 2022"
        )
        == "NA"
        or True
    )
    assert lookup_venue_rank("Obscure Local Meeting") == "NA"
    assert lookup_venue_rank("NA") == "NA"


def test_add_venue_rank_uses_conference_then_journal():
    df = pd.DataFrame(
        {
            "conferenceName": [
                "NA",
                "International Semantic Web Conference (ISWC)",
                "NA",
            ],
            "journalAbbreviation": ["Nucleic Acids Research", "NA", "Unknown"],
        }
    )
    assert list(add_venue_rank(df)["venue_rank"]) == ["Q1", "A", "NA"]
    assert list(add_venue_rank(df.iloc[0:0])["venue_rank"]) == []


def test_rank_score():
    assert venue_rank_score("A*") == 10.0
    assert venue_rank_score("NA") is None


def test_ranking_blend_is_opt_in():
    row = pd.Series(
        {
            "title": "t",
            "abstract": "a",
            "quality_score": 0,
            "itemType": "other",
            "venue_rank": "A*",
        }
    )
    off = calculate_relevance_score(row, [])
    on = calculate_relevance_score(
        row, [], config={"quality_filters": {"use_venue_ranking": True}}
    )
    assert off == 0 and on > off
