# SciLEx Documentation

SciLEx is a Python toolkit for systematic literature reviews and academic paper collection. It collects papers from multiple academic APIs, deduplicates results, and exports to Zotero.

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
```

## Supported APIs

- **Semantic Scholar** - AI/CS papers with citations
- **OpenAlex** - Open catalog, broad coverage
- **IEEE Xplore** - Engineering and computer science
- **Elsevier** - Scientific journals
- **Springer** - Academic books and journals
- **arXiv** - Preprints in physics, CS, math
- **HAL** - French open archive
- **DBLP** - Computer science bibliography
- ~~**Google Scholar**~~ - Deprecated (unreliable, requires Tor)
- **ISTEX** - French scientific archives

## Key Features

### Multi-API Collection
Query multiple academic databases in parallel with automatic rate limiting.

### Filtering Pipeline
5-phase filtering system:
1. ItemType filtering - Focus on publication types
2. Keyword matching - Dual-group AND/OR logic
3. Quality scoring - Metadata completeness
4. Citation filtering - Time-aware thresholds
5. Relevance ranking - Multi-signal scoring

### Performance
- Parallel aggregation with multiprocessing
- SQLite citation cache
- Circuit breaker pattern for failed APIs
- Bulk Zotero uploads

## Basic Usage

```bash
# 1. Configure search
cp scilex/scilex.config.yml.example scilex/scilex.config.yml

# 2. Set up API keys
cp scilex/api.config.yml.example scilex/api.config.yml

# 3. Run collection
scilex-collect

# 4. Aggregate results
scilex-aggregate

# 5. Export to Zotero (optional)
scilex-push-zotero
```

## System Requirements

- Python 3.13+
- uv or pip
- 4GB RAM minimum
- Internet connection