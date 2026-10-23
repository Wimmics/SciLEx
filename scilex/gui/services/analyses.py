"""Analyses of the desktop GUI: charts, keywords, enrichment, snowball, graph, summaries.

Each ``run_*`` function reproduces the body of the matching ``scilex-*`` command
on the configuration of one review. The commands themselves cannot be called
(they parse ``sys.argv``, read global configuration and call ``sys.exit``), so
the building blocks they use are called directly with ``config.main`` / ``config.api``.
All outputs go to the review's collection directory.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from scilex.config import SciLExConfig
from scilex.pipeline_utils import (
    extract_corpus_dois,
    find_clusters_csv,
    resolve_collect_dir,
)

logger = logging.getLogger(__name__)

CHARTS_DIRNAME = "chart_aggregated_papers"
GRAPH_DIRNAME = "graph_analysis"
SNOWBALL_FILENAME = "aggregated_results_snowball.csv"

ProgressFn = Callable[[int, str], None]


class AnalysisError(Exception):
    """A user-facing problem: missing input, nothing found."""


@dataclass
class AnalysisResult:
    """What a run produced: a message and the files it wrote."""

    message: str
    files: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisInfo:
    """Static description of one analysis tab."""

    name: str
    title: str
    description: str
    needs: str  # "results", "citations" or "clusters"


ANALYSES = (
    AnalysisInfo(
        "report",
        "Charts",
        "Draw charts of the aggregated papers: sources, publication types, years, keywords.",
        "results",
    ),
    AnalysisInfo(
        "keywords",
        "Keywords",
        "Suggest new search keywords from frequent terms in the paper clusters (run Graph first).",
        "clusters",
    ),
    AnalysisInfo(
        "enrich",
        "HuggingFace",
        "Add HuggingFace tags, model links and GitHub repositories to the aggregated papers.",
        "results",
    ),
    AnalysisInfo(
        "snowball",
        "Snowball",
        "Find papers outside the corpus that are often cited by, or cite, the corpus papers.",
        "citations",
    ),
    AnalysisInfo(
        "graph",
        "Graph",
        "Build citation graphs and detect communities of related papers.",
        "citations",
    ),
    AnalysisInfo(
        "summaries",
        "Summaries",
        "Write a statistical report of each community found by Graph (run Graph first).",
        "clusters",
    ),
)


def collect_dir_of(config: SciLExConfig) -> Path:
    """Return the collection directory of the configured review."""
    return Path(resolve_collect_dir(config.main))


def graph_dir_of(collect_dir: Path) -> Path:
    """Return the directory of the graph analysis outputs."""
    return collect_dir / GRAPH_DIRNAME


# --- outputs already on disk -------------------------------------------------


def existing_outputs(collect_dir: Path, name: str) -> list[Path]:
    """List the output files of analysis ``name`` already present in ``collect_dir``."""
    graph_dir = graph_dir_of(collect_dir)
    patterns: dict[str, tuple[Path, list[str]]] = {
        "report": (collect_dir / CHARTS_DIRNAME, ["*.png"]),
        "keywords": (graph_dir, ["keyword_suggestions.md", "keyword_suggestions.yml"]),
        "snowball": (collect_dir, [SNOWBALL_FILENAME]),
        "graph": (graph_dir, ["clusters_*.csv", "*_graph.gexf", "*_graph.graphml"]),
        "summaries": (graph_dir, ["summary_report.md"]),
    }
    if name not in patterns:
        return []
    directory, globs = patterns[name]
    return sorted(path for glob in globs for path in directory.glob(glob))


def missing_prerequisite(collect_dir: Path, needs: str) -> str | None:
    """Return a message when the input of an analysis is absent, else None."""
    if needs == "results":
        if not (collect_dir / "aggregated_results.csv").is_file():
            return "Run the collection first (step Collect): no aggregated results."
    elif needs == "citations":
        if not any(
            (collect_dir / name).is_file()
            for name in ("citations_cache.json", "citers_cache.json")
        ):
            return (
                "No citation data yet. Run `scilex-enrich-citations` "
                "(citations are fetched when aggregation does not skip them)."
            )
    elif needs == "clusters":
        try:
            find_clusters_csv(str(graph_dir_of(collect_dir)))
        except FileNotFoundError:
            return "No clusters yet. Run the Graph analysis first."
    return None


# --- runners -----------------------------------------------------------------


def run_report(config: SciLExConfig, progress: ProgressFn) -> AnalysisResult:
    """Generate the charts of the aggregated results (``scilex-report``)."""
    from scilex import report_charts as charts

    collect_dir = collect_dir_of(config)
    try:
        df = charts.load_data(collect_dir)
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    out_dir = collect_dir / CHARTS_DIRNAME
    out_dir.mkdir(exist_ok=True)
    steps = (
        ("API sources", charts.plot_chord_diagram),
        ("publication types", charts.plot_itemtype_pie),
        ("years", charts.plot_year_stacked_bar),
        ("keywords", charts.plot_keyword_bars),
        ("keyword heatmap", charts.plot_keyword_heatmap),
    )
    for index, (label, plot) in enumerate(steps):
        progress(int(100 * index / len(steps)), f"Drawing {label}…")
        plot(df, out_dir)
    files = existing_outputs(collect_dir, "report")
    return AnalysisResult(f"{len(files)} charts for {len(df)} papers.", files)


def _read_clusters(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)
    if "cluster_id" in df.columns:
        df["cluster_id"] = (
            pd.to_numeric(df["cluster_id"], errors="coerce").fillna(-1).astype(int)
        )
    if "pagerank" in df.columns:
        df["pagerank"] = pd.to_numeric(df["pagerank"], errors="coerce").fillna(0.0)
    return df


def _existing_keywords(config: SciLExConfig) -> list[str]:
    keywords = config.main.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",")]
    return list(keywords)


def run_keywords(
    config: SciLExConfig, progress: ProgressFn, *, top_k: int = 30, min_freq: int = 2
) -> AnalysisResult:
    """Suggest new keywords from the clusters (``scilex-suggest-keywords``)."""
    from scilex.keyword_suggestions.extractor import extract_suggestions
    from scilex.keyword_suggestions.report import generate_keyword_report

    collect_dir = collect_dir_of(config)
    analysis_dir = str(graph_dir_of(collect_dir))
    try:
        csv_path = find_clusters_csv(analysis_dir)
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    progress(30, "Extracting frequent terms…")
    suggestions = extract_suggestions(
        _read_clusters(csv_path),
        _existing_keywords(config),
        top_k=top_k,
        min_freq=min_freq,
    )
    if not suggestions:
        return AnalysisResult("No new keyword suggestions found.")
    generate_keyword_report(
        suggestions, analysis_dir, collect_name=config.main["collect_name"]
    )
    return AnalysisResult(
        f"{len(suggestions)} keyword suggestions.",
        existing_outputs(collect_dir, "keywords"),
    )


def run_enrich(
    config: SciLExConfig,
    progress: ProgressFn,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    threshold: int | None = None,
) -> AnalysisResult:
    """Enrich the aggregated CSV with HuggingFace metadata (``scilex-enrich``)."""
    from scilex.pipeline.enrichment_hf import EnrichmentOptions, run_enrichment

    options = EnrichmentOptions(
        dry_run=dry_run, limit=limit or None, threshold=threshold or None
    )

    def on_progress(processed: int, total: int, stats: dict) -> None:
        progress(int(100 * processed / max(total, 1)), f"{processed}/{total} papers")

    try:
        result = run_enrichment(config, options, on_progress)
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    if result.disabled:
        raise AnalysisError("HuggingFace enrichment is disabled in scilex.yml.")
    verb = "would be updated" if dry_run else "updated"
    files = [Path(result.output_path)] if result.output_path else []
    return AnalysisResult(
        f"{result.matched} of {result.total} papers matched, {result.updated} {verb}.",
        files,
    )


def run_snowball(
    config: SciLExConfig,
    progress: ProgressFn,
    *,
    direction: str = "both",
    top_k: int = 200,
    min_frequency: int = 2,
    dry_run: bool = False,
) -> AnalysisResult:
    """Extend the corpus through citation links (``scilex-snowball``)."""
    from scilex.crawlers.key_pool import first_key
    from scilex.graph_analysis.loader import load_citation_caches
    from scilex.io_utils import load_aggregated_data
    from scilex.snowball.candidates import extract_candidates
    from scilex.snowball.fetcher import fetch_metadata_batch
    from scilex.snowball.filter import apply_snowball_filters
    from scilex.snowball.merge import merge_with_corpus

    collect_dir = collect_dir_of(config)
    try:
        corpus_df = load_aggregated_data(config.main)
        references, citers = load_citation_caches(str(collect_dir))
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    progress(10, "Looking for candidates…")
    candidates = extract_candidates(
        references,
        citers,
        extract_corpus_dois(corpus_df),
        direction=direction,
        top_k=top_k,
        min_frequency=min_frequency,
    )
    if not candidates:
        return AnalysisResult("No candidates found. Try a lower minimum frequency.")
    if dry_run:
        preview = "\n".join(f"{doi}  ({freq})" for doi, freq in candidates[:50])
        return AnalysisResult(f"{len(candidates)} candidates (dry run).\n{preview}")
    progress(30, f"Fetching metadata of {len(candidates)} candidates…")
    api_key = first_key(config.api.get("SemanticScholar", {}).get("api_key"))
    papers = fetch_metadata_batch([doi for doi, _ in candidates], api_key=api_key)
    filtered = apply_snowball_filters(papers)
    if filtered.empty:
        return AnalysisResult("No paper passed the quality filters.")
    merged = merge_with_corpus(corpus_df, filtered)
    output_csv = collect_dir / SNOWBALL_FILENAME
    merged.to_csv(output_csv, index=False)
    return AnalysisResult(
        f"{len(filtered)} new papers added ({len(merged)} in total).", [output_csv]
    )


def run_graph(
    config: SciLExConfig,
    progress: ProgressFn,
    *,
    graph_type: str = "cocitation",
    resolution: float = 1.0,
    min_weight: int = 1,
    fmt: str = "gexf",
) -> AnalysisResult:
    """Build citation graphs, detect communities and export them (``scilex-analyze``)."""
    from scilex.graph_analysis.community import compute_centrality, detect_communities
    from scilex.graph_analysis.export import export_clusters_csv, export_graph
    from scilex.graph_analysis.graphs import (
        build_bibliographic_coupling_graph,
        build_cocitation_graph,
    )
    from scilex.graph_analysis.loader import load_citation_caches
    from scilex.io_utils import load_aggregated_data

    collect_dir = collect_dir_of(config)
    analysis_dir = graph_dir_of(collect_dir)
    try:
        df = load_aggregated_data(config.main)
        references, citers = load_citation_caches(str(collect_dir))
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    analysis_dir.mkdir(exist_ok=True)
    corpus_dois = extract_corpus_dois(df)

    builders = {
        "cocitation": lambda: build_cocitation_graph(
            references, citers, corpus_dois, min_weight=min_weight
        ),
        "coupling": lambda: build_bibliographic_coupling_graph(
            references, corpus_dois, min_weight=min_weight
        ),
    }
    names = list(builders) if graph_type == "both" else [graph_type]
    for index, name in enumerate(names):
        progress(int(100 * index / len(names)), f"Analysing {name} graph…")
        graph = builders[name]()
        partition = detect_communities(graph, resolution=resolution)
        pagerank = compute_centrality(graph)
        export_clusters_csv(
            df, partition, pagerank, os.path.join(analysis_dir, f"clusters_{name}.csv")
        )
        export_graph(
            graph,
            partition,
            pagerank,
            os.path.join(analysis_dir, f"{name}_graph.{fmt}"),
            fmt=fmt,
        )
    return AnalysisResult(
        f"Graph analysis done ({', '.join(names)}).",
        existing_outputs(collect_dir, "graph"),
    )


def run_summaries(config: SciLExConfig, progress: ProgressFn) -> AnalysisResult:
    """Write the community summary report (``scilex-summarize``)."""
    from scilex.summarize.report import generate_report
    from scilex.summarize.stats import compute_cluster_stats

    collect_dir = collect_dir_of(config)
    analysis_dir = graph_dir_of(collect_dir)
    try:
        csv_path = find_clusters_csv(str(analysis_dir))
    except FileNotFoundError as exc:
        raise AnalysisError(str(exc)) from exc
    progress(30, "Computing cluster statistics…")
    stats = compute_cluster_stats(_read_clusters(csv_path))
    if not stats:
        return AnalysisResult("No clusters found in the data.")
    report_path = analysis_dir / "summary_report.md"
    generate_report(stats, str(report_path), collect_name=config.main["collect_name"])
    return AnalysisResult(f"Summary of {len(stats)} clusters.", [report_path])


RUNNERS: dict[str, Callable[..., AnalysisResult]] = {
    "report": run_report,
    "keywords": run_keywords,
    "enrich": run_enrich,
    "snowball": run_snowball,
    "graph": run_graph,
    "summaries": run_summaries,
}
