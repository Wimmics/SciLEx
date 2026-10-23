"""Read, validate and write a review's ``scilex.yml`` for the form editor.

UI-independent. The editor works on a plain nested dict (the "editable"
dict): code defaults, then the review's preset, then the values of the file.
Saving writes back **only** what differs from defaults (and preset), so the
file stays short; YAML comments of the previous file are not kept.
"""

from __future__ import annotations

import copy
import os
import re
import types
import typing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

import yaml
from pydantic import BaseModel, ValidationError

from scilex.config_defaults import COLLECTOR_API_NAMES
from scilex.gui.services.workspace import Review
from scilex.settings.loader import _deep_merge, _flatten, _normalize_layer
from scilex.settings.presets import PRESETS, get_preset
from scilex.settings.schema import (
    ScilexSettings,
    SettingsError,
    _suggest,
    default_settings_dict,
    format_validation_error,
    known_paths,
)

API_NAMES: tuple[str, ...] = COLLECTOR_API_NAMES
MAX_KEYWORD_GROUPS = 2
_YEAR_RANGE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$")

# Keys always written, even when equal to their (empty) default.
REQUIRED_PATHS = (
    ("name",),
    ("search", "keywords"),
    ("search", "years"),
    ("search", "apis"),
)

FIELD_HELP: dict[str, str] = {
    "name": "Name of the review; the collection is written to <output folder>/<name>.",
    "output_dir": "Folder receiving the collected data, relative to the review folder.",
    "preset": "Starting point for the filters: 'literature_review' (default rules) or 'bibliometrics' (no filter, no size cap).",
    "search.bonus_keywords": "Optional terms that raise the relevance score of a paper (they never exclude any).",
    "search.max_articles_per_query": "Stop after this many articles per query and API. Empty means no limit.",
    "search.semantic_scholar_mode": "'bulk' is about 10x faster but needs approval from Semantic Scholar.",
    "search.since": "Incremental re-collection: only papers published from this date (YYYY-MM-DD).",
    "filters.item_types": "Document types to keep (e.g. journalArticle). Empty means all types.",
    "filters.always_keep": "Document types kept whatever the other filters say.",
    "filters.require": "Fields a paper must have to be kept.",
    "filters.min_authors": "Minimum number of authors.",
    "filters.abstract_words": "Allowed abstract length as 'min, max' words.",
    "filters.abstract_quality": "Minimum abstract quality score (0-100). Empty disables the check.",
    "filters.check_year_range": "Drop papers published outside the years of the search.",
    "filters.citations": "Apply the time-aware minimum citation threshold.",
    "citations.fetch": "Fetch citation counts (slower, but needed by the citation filter and ranking).",
    "citations.fallbacks": "Sources tried, in order, when the first one has no citation count.",
    "citations.discrepancy_threshold": "Relative gap above which two citation counts are flagged as inconsistent.",
    "ranking.enabled": "Compute a 0-10 relevance score and sort papers by it.",
    "ranking.max_papers": "Keep at most this many top-ranked papers. Empty means no cap.",
    "ranking.weights": "Weight of each ranking criterion (>= 0).",
    "ranking.itemtype_weights": "Advanced: YAML mapping of document type -> true/false.",
    "ranking.venue_ranking": "Use CORE/SJR venue rankings in the score.",
    "enrichment.recover_dois": "Try to find the DOI of papers lacking one.",
    "enrichment.doi_recovery_min_similarity": "Minimum title similarity (0-1) to accept a recovered DOI.",
    "enrichment.unpaywall": "Look up open-access links (needs an email in the API keys).",
    "enrichment.author_hindex": "Fetch author h-index values.",
    "enrichment.huggingface.enabled": "Attach HuggingFace papers/models/datasets information.",
    "report.quality_report": "Write a data quality report.",
    "report.track_duplicates": "Remember which APIs returned each duplicate.",
    "report.prisma": "Write a PRISMA-style flow report.",
    "collect.enabled": "Turn off to only aggregate data already collected.",
    "collect.vpn": "Advanced: VPN rotation block as YAML (empty = none).",
    "llm_screening.enabled": "Screen papers with an LLM through OpenRouter (needs an OpenRouter key).",
    "llm_screening.topic": "Plain-language description of what is relevant. Required when enabled.",
    "llm_screening.threshold": "Minimum score to keep a paper. Empty means no threshold.",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _read_file_layer(path: Path) -> dict:
    """Parse ``path`` into a mapping (``{}`` when empty)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SettingsError(f"{path}: not valid YAML ({exc})") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SettingsError(f"{path}: expected a mapping at the top level")
    return raw


def _expand_years(value: Any) -> Any:
    """Turn ``"2020-2023"`` or ``2020`` into a list; other values are untouched."""
    if isinstance(value, str):
        match = _YEAR_RANGE.match(value)
        if match and int(match.group(1)) <= int(match.group(2)):
            return list(range(int(match.group(1)), int(match.group(2)) + 1))
    elif isinstance(value, int) and not isinstance(value, bool):
        return [value]
    return value


def _normalize_file_layer(layer: dict) -> dict:
    """Expand the shorthands of a file so the form sees canonical values."""
    layer = _normalize_layer(layer)
    search = layer.get("search")
    if isinstance(search, dict):
        keywords = search.get("keywords")
        if (
            isinstance(keywords, list)
            and keywords
            and all(isinstance(k, str) for k in keywords)
        ):
            search["keywords"] = [keywords]
        if "years" in search:
            search["years"] = _expand_years(search["years"])
        since = search.get("since")
        if isinstance(since, datetime):
            search["since"] = since.date().isoformat()
        elif isinstance(since, date):
            search["since"] = since.isoformat()
    return layer


def base_dict(preset: str | None = None) -> dict:
    """Return the values in force without the file: defaults, then ``preset``."""
    base = default_settings_dict()
    base["name"] = ""
    base["search"].update({"keywords": [[]], "years": [], "apis": []})
    if preset in PRESETS:
        _deep_merge(base, _normalize_layer(get_preset(preset)))
    base.setdefault("preset", None)
    return base


def load_editable(review: Review) -> dict:
    """Return the review's values: defaults < preset < ``scilex.yml``.

    Raises:
        SettingsError: If the file is not valid YAML.
        FileNotFoundError: If the review has no ``scilex.yml``.
    """
    layer = _normalize_file_layer(_read_file_layer(review.config_path))
    preset = layer.get("preset")
    merged = base_dict(preset if isinstance(preset, str) else None)
    _deep_merge(merged, layer)
    return merged


def origins(review: Review) -> dict[str, str]:
    """Return ``{dotted.path: "preset" | "file"}`` for the non-default values."""
    layer = _normalize_file_layer(_read_file_layer(review.config_path))
    result: dict[str, str] = {}
    preset = layer.get("preset")
    if isinstance(preset, str) and preset in PRESETS:
        for dotted in _flatten(_normalize_layer(get_preset(preset))):
            result[dotted] = "preset"
    for dotted in _flatten(layer):
        result[dotted] = "file"
    return result


def origin_of(path: str, known: dict[str, str]) -> str:
    """Origin of ``path`` (a leaf or a section) given :func:`origins`."""
    if path in known:
        return known[path]
    inner = [origin for key, origin in known.items() if key.startswith(f"{path}.")]
    if "file" in inner:
        return "file"
    return "preset" if inner else "default"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(data: dict) -> list[tuple[str, str]]:
    """Validate ``data`` with the pydantic model.

    Returns:
        ``(dotted_path, message)`` pairs; empty when the data is valid.
    """
    try:
        ScilexSettings.model_validate(data)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            path = ".".join(str(part) for part in error["loc"])
            kind = error["type"]
            if kind == "missing":
                message = "this value is required"
            elif kind == "extra_forbidden":
                message = "unknown key"
            else:
                message = error["msg"].removeprefix("Value error, ")
            problems.append((path, message))
        return problems
    return []


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

_SAME = object()


def _diff(value: Any, base: Any) -> Any:
    """Return the part of ``value`` that differs from ``base`` (``_SAME`` if none)."""
    if isinstance(value, dict) and isinstance(base, dict):
        changed = {}
        for key, item in value.items():
            if key not in base:
                changed[key] = copy.deepcopy(item)
                continue
            inner = _diff(item, base[key])
            if inner is not _SAME:
                changed[key] = inner
        return changed if changed else _SAME
    return _SAME if value == base else copy.deepcopy(value)


def _compact_years(years: Any) -> Any:
    """Write a run of 3+ consecutive years as ``"YYYY-YYYY"``."""
    if (
        isinstance(years, list)
        and len(years) >= 3
        and all(isinstance(y, int) for y in years)
        and years == list(range(years[0], years[-1] + 1))
    ):
        return f"{years[0]}-{years[-1]}"
    return years


def to_file_dict(data: dict) -> dict:
    """Return the minimal dict to write for ``data`` (non-defaults + required)."""
    preset = data.get("preset")
    changed = _diff(data, base_dict(preset if isinstance(preset, str) else None))
    result: dict = {} if changed is _SAME else changed
    for path in REQUIRED_PATHS:
        source, target = data, result
        for key in path[:-1]:
            source = source[key]
            target = target.setdefault(key, {})
        target[path[-1]] = copy.deepcopy(source[path[-1]])
    result["search"]["years"] = _compact_years(sorted(set(result["search"]["years"])))
    ordered = {
        key: result[key] for key in ("name", "output_dir", "preset") if key in result
    }
    ordered.update({key: value for key, value in result.items() if key not in ordered})
    return ordered


def save(review: Review, data: dict) -> Path:
    """Validate ``data`` and write it atomically to the review's ``scilex.yml``.

    Raises:
        SettingsError: If ``data`` is invalid (nothing is written).
    """
    problems = validate(data)
    if problems:
        raise SettingsError(
            "\n".join(f"{path}: {message}" for path, message in problems)
        )
    text = yaml.safe_dump(to_file_dict(data), sort_keys=False, allow_unicode=True)
    target = review.config_path
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, target)
    return target


# ---------------------------------------------------------------------------
# Raw text editing (repair of a file the form cannot handle)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextCheck:
    """Result of checking the raw text of a ``scilex.yml``."""

    problems: list[str]  # readable messages; empty when the text is valid
    unknown_keys: list[tuple[str, str | None]]  # (dotted path, suggestion)

    @property
    def valid(self) -> bool:
        """Whether the text can be saved as is."""
        return not self.problems


def read_text(review: Review) -> str:
    """Return the raw text of the review's ``scilex.yml`` (``""`` if absent)."""
    try:
        return review.config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def check_text(text: str) -> TextCheck:
    """Check ``text`` as a ``scilex.yml``: YAML syntax, then the schema.

    Unknown keys are listed in ``unknown_keys`` with a "did you mean" hint.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        reason = getattr(exc, "problem", None) or str(exc)
        return TextCheck([f"Invalid YAML, {where}{reason}"], [])
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return TextCheck(["The top level of scilex.yml must be a mapping."], [])
    layer = _normalize_file_layer(copy.deepcopy(raw))
    preset = layer.get("preset")
    merged = base_dict(preset if isinstance(preset, str) else None)
    _deep_merge(merged, layer)
    try:
        ScilexSettings.model_validate(merged)
    except ValidationError as exc:
        candidates = known_paths()
        unknown = [
            (dotted, _suggest(dotted, candidates))
            for dotted in (
                ".".join(str(part) for part in error["loc"])
                for error in exc.errors()
                if error["type"] == "extra_forbidden"
            )
        ]
        return TextCheck(format_validation_error(exc, merged).splitlines(), unknown)
    return TextCheck([], [])


def write_text(review: Review, text: str) -> Path:
    """Write ``text`` verbatim and atomically (comments are kept).

    Raises:
        SettingsError: If ``text`` does not pass :func:`check_text`.
    """
    check = check_text(text)
    if not check.valid:
        raise SettingsError("\n".join(check.problems))
    target = review.config_path
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, target)
    return target


def remove_unknown_keys(review: Review) -> list[str]:
    """Rewrite the file without its unknown keys; return the removed paths.

    Raises:
        SettingsError: If the file is not valid YAML or other problems remain.
    """
    text = read_text(review)
    check = check_text(text)
    raw = yaml.safe_load(text) if text.strip() else {}
    if not isinstance(raw, dict) or check.problems and not check.unknown_keys:
        raise SettingsError("\n".join(check.problems))
    removed = []
    for dotted, _ in check.unknown_keys:
        *parents, last = dotted.split(".")
        node: Any = raw
        for key in parents:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict) and last in node:
            del node[last]
            removed.append(dotted)
    temporary = review.config_path.with_name(review.config_path.name + ".tmp")
    temporary.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    os.replace(temporary, review.config_path)
    return removed


# ---------------------------------------------------------------------------
# Form description (drives the generic form)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    """How the form edits one field."""

    kind: str  # bool int float str choice multichoice strlist intlist floatmap yaml
    nullable: bool = False
    options: tuple = ()


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """Strip ``Annotated`` and ``| None``; return ``(core, nullable)``."""
    nullable = False
    while True:
        origin = get_origin(annotation)
        if origin is typing.Annotated:
            annotation = get_args(annotation)[0]
        elif origin in (typing.Union, types.UnionType):
            args = [a for a in get_args(annotation) if a is not type(None)]
            nullable = nullable or len(args) < len(get_args(annotation))
            if len(args) != 1:
                return annotation, nullable
            annotation = args[0]
        else:
            return annotation, nullable


def describe_field(annotation: Any) -> FieldSpec:
    """Map a pydantic field annotation to a :class:`FieldSpec`."""
    core, nullable = _unwrap(annotation)
    origin = get_origin(core)
    if core is bool:
        return FieldSpec("bool", nullable)
    if core is int:
        return FieldSpec("int", nullable)
    if core is float:
        return FieldSpec("float", nullable)
    if core is str:
        return FieldSpec("str", nullable)
    if origin is Literal:
        return FieldSpec("choice", nullable, get_args(core))
    if origin is list:
        item, _ = _unwrap(get_args(core)[0])
        if get_origin(item) is Literal:
            return FieldSpec("multichoice", nullable, get_args(item))
        if item is int:
            return FieldSpec("intlist", nullable)
        return FieldSpec("strlist", nullable)
    if origin is dict:
        value, _ = _unwrap(get_args(core)[1])
        return FieldSpec("floatmap" if value is float else "yaml", nullable)
    return FieldSpec("yaml", nullable)


def sections() -> list[tuple[str, type[BaseModel]]]:
    """Top-level sub-models of the settings, in file order, except ``search``."""
    result = []
    for name, field in ScilexSettings.model_fields.items():
        core, _ = _unwrap(field.annotation)
        if name != "search" and isinstance(core, type) and issubclass(core, BaseModel):
            result.append((name, core))
    return result


def years_as_range(years: Any) -> tuple[int, int] | None:
    """Return ``(first, last)`` if ``years`` is a run of consecutive years."""
    if (
        isinstance(years, list)
        and years
        and all(isinstance(y, int) and not isinstance(y, bool) for y in years)
        and sorted(years) == list(range(min(years), max(years) + 1))
    ):
        return min(years), max(years)
    return None
