"""Screening decisions of a review, kept in ``output/<name>/screening.csv``.

Decisions live in their own file so that re-running the aggregation never
erases them. A paper is identified by :func:`paper_key`: its normalised DOI,
otherwise its normalised title plus year. Decisions whose paper disappeared
from the results are kept and reported as orphans.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from scilex.constants import extract_year, is_valid, normalize_doi
from scilex.gui.services.workspace import Review

SCREENING_FILENAME = "screening.csv"
INCLUDE, EXCLUDE, MAYBE = "include", "exclude", "maybe"
DECISIONS = (INCLUDE, EXCLUDE, MAYBE)
FIELDS = ("paper_key", "decision", "note", "updated_at")


@dataclass
class Decision:
    """Screening decision on one paper."""

    paper_key: str
    decision: str
    note: str = ""
    updated_at: str = ""


def paper_key(row) -> str:
    """Stable key of a paper (a results row or a mapping with DOI/title/date)."""
    doi = row.get("DOI")
    if is_valid(doi):
        normalised = normalize_doi(doi)
        if normalised:
            return f"doi:{normalised}"
    title = str(row.get("title") or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    year = extract_year(row.get("date")) if is_valid(row.get("date")) else None
    return f"title:{title}|{year or ''}"


def screening_path(review: Review) -> Path:
    """Path of the review's screening file."""
    return review.collection_dir / SCREENING_FILENAME


def load_results(review: Review) -> pd.DataFrame:
    """Load the aggregated results with a ``paper_key`` column added."""
    from scilex.io_utils import load_aggregated_data

    data = load_aggregated_data(
        {"collect_name": review.name}, collect_dir=str(review.collection_dir)
    )
    data = data.loc[:, [c for c in data.columns if not str(c).startswith("Unnamed")]]
    data["paper_key"] = [paper_key(row) for _, row in data.iterrows()]
    return data


def load_decisions(review: Review) -> dict[str, Decision]:
    """Read the screening file; returns an empty dict if there is none."""
    path = screening_path(review)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["paper_key"]: Decision(**{f: row.get(f, "") or "" for f in FIELDS})
            for row in csv.DictReader(handle)
            if row.get("decision") in DECISIONS
        }


def save_decisions(review: Review, decisions: dict[str, Decision]) -> None:
    """Write all decisions atomically (temporary file then rename)."""
    path = screening_path(review)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for decision in decisions.values():
            writer.writerow(decision.__dict__)
    tmp.replace(path)


def set_decision(
    review: Review, key: str, decision: str | None, note: str = ""
) -> None:
    """Record (or clear, with ``decision=None``) the decision on one paper."""
    decisions = load_decisions(review)
    if decision is None:
        decisions.pop(key, None)
    else:
        if decision not in DECISIONS:
            raise ValueError(f"Unknown decision {decision!r}")
        decisions[key] = Decision(
            key, decision, note, datetime.now().isoformat(timespec="seconds")
        )
    save_decisions(review, decisions)


def orphan_keys(review: Review, results: pd.DataFrame) -> list[str]:
    """Decisions whose paper is no longer in the results."""
    present = set(results["paper_key"])
    return [key for key in load_decisions(review) if key not in present]


def included_results(
    review: Review, results: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Rows of the results marked as included."""
    results = load_results(review) if results is None else results
    included = {k for k, d in load_decisions(review).items() if d.decision == INCLUDE}
    return results[results["paper_key"].isin(included)]
