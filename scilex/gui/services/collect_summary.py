"""Data behind the Collect screen, free of any UI code.

Per-API status rows, aggregation phases, pre-flight summary, resume detection
and the summary of a finished run read from the collection folder.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from scilex.config import SciLExConfig
from scilex.pipeline import jobs as job_states

logger = logging.getLogger(__name__)

# Phases reported by run_aggregation's progress callback, in order.
AGGREGATION_PHASES = [
    ("initializing", "Loading configuration"),
    ("aggregating", "Loading and deduplicating"),
    ("filtering", "Applying filters"),
    ("citations", "Fetching citations"),
    ("ranking", "Ranking papers"),
    ("completed", "Writing results"),
]
CONFIG_USED_FILENAME = "config_used.yml"


@dataclass(frozen=True)
class ApiRow:
    """One line of the per-API status table."""

    api: str
    queries_done: int
    queries_total: int
    papers: int
    errors: int
    state: str  # waiting | running | done | partial | failed
    reason: str = ""


def _api_error_lines(api: str, logs: list[str]) -> list[str]:
    needle = api.lower()
    return [
        line
        for line in logs
        if needle in line.lower() and ("[ERROR]" in line or "[CRITICAL]" in line)
    ]


def api_rows(
    api_stats: dict, logs: list[str], job_status: str | None, active: bool
) -> list[ApiRow]:
    """Build the table rows from ``job.api_stats`` (``completed/total/articles``).

    Errors are the ERROR log lines mentioning the API (the collector reports
    no error count in its progress callback).
    """
    rows = []
    for api, stats in sorted(api_stats.items()):
        done, total = stats.get("completed", 0), stats.get("total", 0)
        papers = stats.get("articles", 0)
        error_lines = _api_error_lines(api, logs)
        reason = error_lines[-1].split("] ", 1)[-1] if error_lines else ""
        if total and done >= total:
            state = "done"
        elif active:
            state = "running" if done else "waiting"
        elif job_status == job_states.FAILED and error_lines:
            state = "failed"
        elif done:
            state = "partial"
            reason = reason or f"{done}/{total} queries"
        else:
            state = "failed" if error_lines else "partial"
            reason = reason or "No query completed"
        rows.append(ApiRow(api, done, total, papers, len(error_lines), state, reason))
    return rows


def phase_steps(current_phase: str | None, finished: bool) -> list[tuple[str, str]]:
    """Return ``(label, state)`` per aggregation phase: done / current / pending."""
    names = [name for name, _ in AGGREGATION_PHASES]
    index = names.index(current_phase) if current_phase in names else -1
    steps = []
    for position, (_, label) in enumerate(AGGREGATION_PHASES):
        if finished or position < index:
            state = "done"
        elif position == index:
            state = "current"
        else:
            state = "pending"
        steps.append((label, state))
    return steps


def preflight_line(config: SciLExConfig) -> str:
    """One-line description of what the run will do."""
    main = config.main
    apis = main.get("apis", [])
    years = main.get("years", [])
    groups = [group for group in main.get("keywords", []) if group]
    year_text = f"{min(years)}-{max(years)}" if years else "no year"
    group_text = " + ".join(str(len(group)) for group in groups) or "no"
    return (
        f"Will query {len(apis)} API(s) ({', '.join(apis) or 'none'}) for {year_text}, "
        f"{group_text} keyword(s) in {len(groups)} group(s)."
    )


@dataclass(frozen=True)
class ResumeInfo:
    """An interrupted collection that can be resumed."""

    done: int
    total: int


def detect_resume(collection_dir: Path) -> ResumeInfo | None:
    """Return resume info if the last collection did not finish, else None.

    Reads ``config_used.yml`` and the per-query ``_complete`` sentinels, like
    ``scilex status``.
    """
    config_path = collection_dir / CONFIG_USED_FILENAME
    if not config_path.is_file():
        return None
    try:
        from scilex.collect_status import build_status

        used = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        totals = build_status(str(collection_dir), used)["totals"]
    except Exception:
        logger.warning("Cannot read collection state of %s", collection_dir)
        return None
    started = totals["done"] + totals["partial"] > 0
    if started and totals["done"] < totals["total"]:
        return ResumeInfo(totals["done"], totals["total"])
    return None


def resume_config(collection_dir: Path, config: SciLExConfig) -> SciLExConfig:
    """Return ``config`` with the main settings of the interrupted collection.

    Same as ``scilex-collect --resume``: the snapshot ``config_used.yml`` wins
    over the current ``scilex.yml`` (completed queries are then skipped), the
    API keys stay those of the current configuration.

    Raises:
        FileNotFoundError: If the collection has no saved configuration.
    """
    config_path = collection_dir / CONFIG_USED_FILENAME
    if not config_path.is_file():
        raise FileNotFoundError(f"No saved configuration in {collection_dir}")
    main = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    main["output_dir"] = config.main["output_dir"]
    return SciLExConfig.from_dicts(main, config.api)


@dataclass(frozen=True)
class CollectionSummary:
    """Numbers of a finished run and its report files."""

    collected: int | None
    after_dedup: int | None
    kept: int | None
    prisma_report: Path | None
    aggregation_report: Path | None


def _to_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_summary(collection_dir: Path) -> CollectionSummary | None:
    """Read the summary of the last aggregation, or None if there is nothing."""
    stats: dict[str, str] = {}
    stats_path = collection_dir / "aggregation_stats.csv"
    if stats_path.is_file():
        with open(stats_path, newline="", encoding="utf-8") as handle:
            stats = {row["stat"]: row["value"] for row in csv.DictReader(handle)}
    final_count = None
    summary_path = collection_dir / "filtering_summary.json"
    if summary_path.is_file():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            final_count = _to_int(data.get("final_count"))
        except (OSError, ValueError):
            logger.warning("Unreadable %s", summary_path)
    if not stats and final_count is None:
        return None
    kept = (
        final_count if final_count is not None else _to_int(stats.get("papers_output"))
    )
    prisma = collection_dir / "prisma_report.md"
    report = collection_dir / "aggregation_report.md"
    return CollectionSummary(
        collected=_to_int(stats.get("papers_loaded")),
        after_dedup=_to_int(stats.get("papers_after_dedup")),
        kept=kept,
        prisma_report=prisma if prisma.is_file() else None,
        aggregation_report=report if report.is_file() else None,
    )
