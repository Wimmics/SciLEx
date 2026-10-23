"""Relevance and quality scores must reach every export (issue #33)."""

import pandas as pd

from scilex.export_to_bibtex import format_bibtex_entry
from scilex.Zotero.zotero_api import prepare_zotero_item

TEMPLATE = {"itemType": "journalArticle", "title": "", "url": "", "DOI": ""}


def _row(**extra):
    base = {"itemType": "journalArticle", "title": "T", "DOI": "10.1/x"}
    base.update(extra)
    return pd.Series(base)


def test_zotero_tags_carry_scores():
    row = _row(relevance_score=7.4, quality_score=83)
    item = prepare_zotero_item(row, "COLL", {"journalArticle": dict(TEMPLATE)})
    tags = {t["tag"] for t in item["tags"]}
    assert "REL_SCORE:7" in tags
    assert "QUALI_SCORE:8" in tags


def test_zotero_scores_clamped():
    row = _row(relevance_score=42, quality_score=-5)
    item = prepare_zotero_item(row, "COLL", {"journalArticle": dict(TEMPLATE)})
    tags = {t["tag"] for t in item["tags"]}
    assert "REL_SCORE:10" in tags
    assert "QUALI_SCORE:0" in tags


def test_zotero_no_score_tags_when_missing():
    item = prepare_zotero_item(_row(), "COLL", {"journalArticle": dict(TEMPLATE)})
    tags = {t["tag"] for t in item.get("tags", [])}
    assert not any(t.startswith(("REL_SCORE", "QUALI_SCORE")) for t in tags)


def test_bibtex_exports_relevance_score():
    entry = format_bibtex_entry(_row(relevance_score=7.34), "key1")
    assert "relevancescore = {7.34}" in entry
