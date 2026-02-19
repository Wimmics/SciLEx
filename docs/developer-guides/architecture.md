# Architecture Overview

SciLEx architecture and core components.

## System Overview

```
User Config (YAML)
    ↓
Collection System → APIs → JSON Storage
    ↓
Aggregation Pipeline → Filtering
    ↓
CSV Output / BibTeX / Zotero Export
```

## Core Components

### 1. Collection System

**Location**: `scilex/crawlers/collector_collection.py`

Orchestrates parallel API collection:
- Creates jobs from config (keywords × years × APIs)
- Runs collectors in parallel (threading, 1 thread per API)
- Tracks progress via Queue and tqdm
- Skips completed queries (idempotent)

**API Collectors** (`scilex/crawlers/collectors/`):
- Base class: `API_collector` in `base.py`
- 10 active implementations (SemanticScholar, OpenAlex, IEEE, Arxiv, Springer, Elsevier, PubMed, HAL, DBLP, Istex)
- Each handles query building, pagination, parsing

### 2. Aggregation Pipeline

**Location**: `scilex/aggregate_collect.py`

Processes collected papers:
1. Load JSON files from all APIs
2. Convert to unified format
3. Deduplicate (DOI, URL, fuzzy title)
4. Apply keyword filtering
5. Score quality
6. Filter by citations
7. Rank by relevance
8. Output to CSV

**Parallel Mode** (`scilex/crawlers/aggregate_parallel.py`):
- Multiprocessing for speed
- Batch processing (5000 papers/batch)
- Auto-detects CPU count

### 3. Format Converters

**Location**: `scilex/crawlers/aggregate.py`

Convert API-specific formats to unified schema:
- One converter per API
- Maps to Zotero-compatible format
- Uses `MISSING_VALUE` for missing fields

### 4. Filtering Engine

**Location**: `scilex/aggregate_collect.py`

5-phase filtering:
1. ItemType filter
2. Keyword filter (`scilex/keyword_validation.py`)
3. Quality filter (`scilex/quality_validation.py`)
4. Citation filter
5. Relevance ranking

### 5. Validation Modules

- **`scilex/keyword_validation.py`** - Single/dual keyword matching logic
- **`scilex/quality_validation.py`** - Quality scoring, abstract validation, author counting
- **`scilex/abstract_validation.py`** - Detect truncation, boilerplate, encoding issues
- **`scilex/duplicate_tracking.py`** - API overlap analysis and dedup statistics

### 6. Citation System

**Location**: `scilex/citations/citations_tools.py`

Four-tier strategy:
1. SQLite cache (instant)
2. Semantic Scholar data (if available, in-memory)
3. CrossRef live per-DOI API call (~3-10 req/sec with polite pool)
4. OpenCitations API (1 req/sec fallback, only for CrossRef misses)

Cache location: `output/citation_cache.db`

### 7. HuggingFace Enrichment

**Location**: `scilex/HuggingFace/`

Modular enrichment system:
- `hf_client.py` - HuggingFace API client
- `title_matcher.py` - Fuzzy title matching
- `tag_formatter.py` - Tag formatting (TASK:, PTM:, DATASET:, etc.)
- `metadata_extractor.py` - Extract ML metadata

Entry point: `scilex/enrich_with_hf.py` (CLI and programmatic)

### 8. Zotero Integration

**Location**: `scilex/Zotero/zotero_api.py`

API client for Zotero:
- Bulk uploads (50 items/batch)
- Duplicate detection by URL
- Collection management

### 9. Infrastructure

- **`scilex/config_defaults.py`** - All defaults, dual-value rate limits, quality schema
- **`scilex/constants.py`** - MISSING_VALUE, is_valid(), circuit breaker config
- **`scilex/logging_config.py`** - Centralized logging, progress tracking
- **`scilex/crawlers/circuit_breaker.py`** - Circuit breaker pattern for API resilience

## Data Flow

### Collection

```
Config → Job Generation → Thread Workers (1 per API) → API Calls → JSON Files
```

Each job:
- API name
- Keyword combination
- Year
- Output path

Output: `output/{collect_name}/{API}/{query_id}/page_*`

### Aggregation

```
JSON Files → Format Conversion → Deduplication → Filtering → CSV
```

Output: `aggregated_results.csv` with columns:
- Core: title, authors, year, DOI, abstract
- Publication: itemType, publicationTitle, volume, issue
- Metadata: nb_citation, quality_score, relevance_score

## Design Patterns

### Factory Pattern
API collectors created dynamically:
```python
api_collectors = {
    'SemanticScholar': SemanticScholar_collector,
    'OpenAlex': OpenAlex_collector,
    ...
}
collector = api_collectors[api_name](config)
```

### Circuit Breaker
Fails fast for broken APIs:
- Tracks consecutive failures
- Opens circuit after 5 failures
- Skips requests when open
- Auto-retries after timeout (60s)

### Repository Pattern
Abstracts data storage:
- JSON for raw collection data
- CSV for aggregated results
- SQLite for citation cache

## Configuration System

Hierarchical priority:
1. Default values (`config_defaults.py`)
2. Main config (`scilex.config.yml`)
3. Advanced config (`scilex.advanced.yml`) — merges/overrides main config
4. API config (`api.config.yml`)
5. Environment variables
6. Command-line arguments

Build system defined in `pyproject.toml` (hatchling build backend, CLI entry points, dependencies, ruff/pytest config).

## Performance Features

- **Threaded Collection**: Multiple APIs simultaneously (1 thread per API)
- **Parallel Aggregation**: Batch processing with multiprocessing
- **Citation Caching**: SQLite cache avoids redundant API calls
- **Circuit Breaker**: Skip broken APIs quickly
- **Rate Limiting**: Per-API throttling with dual-value system (with/without key)
- **Bulk Operations**: Zotero uploads in batches

## Error Handling

- Specific exception types (no bare `except`)
- 30-second timeouts on all API calls
- Retry logic with exponential backoff
- State files for recovery
- API key sanitization in error messages

## Directory Structure

```
scilex/
├── crawlers/
│   ├── collectors/               # API collector classes (one per API)
│   │   ├── base.py               # API_collector base class
│   │   ├── semantic_scholar.py
│   │   ├── openalex.py
│   │   ├── pubmed.py
│   │   └── ...                   # 10 collectors total
│   ├── collector_collection.py   # Collection orchestrator (threading)
│   ├── aggregate.py              # Format converters
│   ├── aggregate_parallel.py     # Parallel aggregation
│   └── circuit_breaker.py        # Circuit breaker pattern
├── citations/
│   └── citations_tools.py
├── HuggingFace/
│   ├── hf_client.py
│   ├── title_matcher.py
│   ├── tag_formatter.py
│   └── metadata_extractor.py
├── Zotero/
│   └── zotero_api.py
├── constants.py                  # Shared constants, is_valid()
├── config_defaults.py            # All defaults, rate limits
├── keyword_validation.py         # Keyword matching logic
├── quality_validation.py         # Quality scoring
├── abstract_validation.py        # Abstract quality detection
├── duplicate_tracking.py         # API overlap analysis
├── logging_config.py             # Centralized logging
├── run_collection.py             # Main collection script
├── aggregate_collect.py          # Main aggregation script
├── enrich_with_hf.py             # HuggingFace CSV enrichment
├── push_to_zotero.py             # Zotero upload
└── export_to_bibtex.py           # BibTeX export

output/
└── {collect_name}/               # Named by collect_name in config
    ├── {API}/                    # Per-API results
    └── aggregated_results.csv    # Final output
```

## Adding New Components

### New API Collector

1. Create collector class in `scilex/crawlers/collectors/` inheriting `API_collector`
2. Implement: `__init__()`, `query_build()`, `run()`, `parsePageResults()`
3. Add format converter in `scilex/crawlers/aggregate.py`
4. Register in `api_collectors` dict in `collector_collection.py`
5. Add rate limit defaults in `config_defaults.py`
6. Add to config examples

See [Adding Collectors](adding-collectors.md) for details.

### New Filter

1. Add filter function in `aggregate_collect.py`
2. Add config options in `config_defaults.py`
3. Insert in filtering pipeline
4. Update documentation

## Testing

376 tests across 16 files, 38% overall coverage. See `tests/README.md` for details.

```bash
uv run python -m pytest tests/                                        # All tests
uv run python -m pytest tests/ --cov=scilex --cov-report=term-missing # With coverage
```

Shared fixtures in `tests/conftest.py`. PubMed XML fixtures in `tests/fixtures/pubmed/`.
