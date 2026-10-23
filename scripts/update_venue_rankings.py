"""Download the full CORE and SCImago SJR rankings into scilex/data/venue_rankings.

Usage: python scripts/update_venue_rankings.py [--core-source CORE2023]

Output files use the simplified schemas read by scilex.pipeline.venue_ranking:
core_conferences.csv (title,acronym,rank) and sjr_journals.csv (title,quartile).
"""

import argparse
import csv
import io
from pathlib import Path

import requests

CORE_EXPORT_URL = (
    "https://portal.core.edu.au/conf-ranks/?search=&by=all&source={source}"
    "&sort=arank&page=1&do=Export"
)
SJR_URL = "https://www.scimagojr.com/journalrank.php?out=xls"
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "scilex" / "data" / "venue_rankings"
)
VALID_CORE_RANKS = {"A*", "A", "B", "C"}
REQUEST_TIMEOUT_SECONDS = 120
USER_AGENT = {"User-Agent": "SciLEx venue ranking updater"}


def fetch_core(source):
    """Return CORE rows ``(title, acronym, rank)``; the export has no header.

    Columns: id, title, acronym, source, rank, note, dblp, for, comments, rating.
    """
    response = requests.get(
        CORE_EXPORT_URL.format(source=source),
        headers=USER_AGENT,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    rows = []
    for record in csv.reader(io.StringIO(response.text)):
        if len(record) >= 5 and record[4].strip() in VALID_CORE_RANKS:
            rows.append((record[1].strip(), record[2].strip(), record[4].strip()))
    return rows


def fetch_sjr():
    """Return SJR rows ``(title, best quartile)`` (semicolon-separated export)."""
    response = requests.get(
        SJR_URL, headers=USER_AGENT, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text), delimiter=";")
    return [
        (row["Title"].strip(), row["SJR Best Quartile"].strip())
        for row in reader
        if row.get("SJR Best Quartile", "").strip() in {"Q1", "Q2", "Q3", "Q4"}
    ]


def write_csv(path, header, rows):
    """Write ``rows`` under ``header`` to ``path``."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    """Download both rankings and overwrite the shipped CSV files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-source", default="CORE2023")
    args = parser.parse_args()
    write_csv(
        OUTPUT_DIR / "core_conferences.csv",
        ("title", "acronym", "rank"),
        fetch_core(args.core_source),
    )
    write_csv(OUTPUT_DIR / "sjr_journals.csv", ("title", "quartile"), fetch_sjr())


if __name__ == "__main__":
    main()
