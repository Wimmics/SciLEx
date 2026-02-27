# SciLEx Documentation

SciLEx is a Python toolkit for systematic literature reviews. It collects papers from 10 academic APIs, deduplicates results, applies a 5-phase quality filtering pipeline, and exports to Zotero or BibTeX.

```{toctree}
:maxdepth: 2
:caption: Getting Started

getting-started/installation
getting-started/quick-start
getting-started/configuration
getting-started/troubleshooting
```

```{toctree}
:maxdepth: 2
:caption: User Guides

user-guides/basic-workflow
user-guides/advanced-filtering
user-guides/python-scripting
```

```{toctree}
:maxdepth: 2
:caption: Developer Guides

developer-guides/architecture
developer-guides/adding-collectors
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/api-comparison
reference/bibtex-export
```

## Supported APIs (10)

- **Semantic Scholar** — AI/CS papers with citations
- **OpenAlex** — Open catalog, broad coverage
- **IEEE Xplore** — Engineering and computer science
- **Elsevier** — Scientific journals
- **Springer** — Academic books and journals
- **arXiv** — Preprints in physics, CS, math
- **PubMed** — Biomedical literature (35M+ papers)
- **HAL** — French open archive
- **DBLP** — Computer science bibliography
- **ISTEX** — French scientific archives

See [API Comparison](reference/api-comparison.md) for rate limits, key requirements, and coverage details.

## Quick Links

- [Installation](getting-started/installation.md) — Setup with uv or pip
- [Quick Start](getting-started/quick-start.md) — Your first collection in 5 minutes
- [Advanced Filtering](user-guides/advanced-filtering.md) — 5-phase filtering pipeline with flowchart
- [BibTeX Export](reference/bibtex-export.md) — Field reference and PDF link sources

## System Requirements

- Python >=3.10
- uv or pip
- Internet connection
