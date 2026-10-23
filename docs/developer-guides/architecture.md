# Architecture Overview

SciLEx architecture and core components.

## System Overview

```
scilex.yml (review) + keys.yml (API keys)
    ↓ scilex/settings (validate, presets, defaults)

Collection System → APIs → JSON Storage
    ↓
Aggregation Pipeline → Filtering
    ↓
CSV Output / Zotero Export
```

## Core Components

### 1. Collection System

**Location**: `scilex/crawlers/collector_collection.py`

Orchestrates parallel API collection:
- Creates jobs from config (keywords × years × APIs)
- Runs collectors in parallel (multiprocessing)
- Tracks progress and handles errors
- Skips completed queries (idempotent)

**API Collectors** (`scilex/crawlers/collectors/`, one module per API):
- Base class: `API_collector`
- 11 active implementations: SemanticScholar, OpenAlex, IEEE, Elsevier, Springer, arXiv, HAL, DBLP, ISTEX, OpenAIRE, ORKG
- 1 deprecated: GoogleScholar
- Each handles query building, pagination, and response parsing

### 2. Aggregation Pipeline

**Location**: `scilex/aggregate_collect.py` (CLI) and `scilex/pipeline/` (logic)

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
- One converter function per API
- Maps to Zotero-compatible format
- Uses `MISSING_VALUE` sentinel for missing fields (never `None` or `""`)

Converters registered in `FORMAT_CONVERTERS` dict:
- `SemanticScholartoZoteroFormat`
- `IstextoZoteroFormat`
- `ArxivtoZoteroFormat`
- `DBLPtoZoteroFormat`
- `HALtoZoteroFormat`
- `OpenAlextoZoteroFormat`
- `IEEEtoZoteroFormat`
- `SpringertoZoteroFormat`
- `ElseviertoZoteroFormat`
- `OpenAIREtoZoteroFormat`
- `ORKGtoZoteroFormat`

### 4. Filtering Engine

**Location**: `scilex/aggregate_collect.py` (CLI) and `scilex/pipeline/` (logic)

5-phase filtering:
1. ItemType filter
2. Keyword filter
3. Quality filter
4. Citation filter
5. Relevance ranking

### 5. Citation System

**Location**: `src/citations/citations_tools.py`

Three-tier strategy:
1. SQLite cache (instant)
2. Semantic Scholar data (if available)
3. OpenCitations API (rate-limited)

Cache location: `output/citation_cache.db`

### 6. Zotero Integration

**Location**: `src/Zotero/push_to_Zotero.py`

API client for Zotero:
- Bulk uploads (50 items/batch)
- Duplicate detection by URL
- Collection management

## Data Flow

### Collection

```
Config → Job Generation → Parallel Workers → API Calls → JSON Files
```

Each job:
- API name
- Keyword combination
- Year
- Output path

Output: `output/collect_YYYYMMDD_HHMMSS/{API}/{query_id}/page_*`

### Aggregation

```
JSON Files → Format Conversion → Deduplication → Filtering → CSV
```

Output: `aggregated_data.csv` with columns:
- Core: title, authors, year, DOI, abstract
- Publication: itemType, publicationTitle, volume, issue
- Metadata: nb_citation, quality_score, relevance_score, archive

## Design Patterns

### Factory Pattern
API collectors created dynamically:
```python
api_collectors = {
    'SemanticScholar': SemanticScholar_collector,
    'OpenAlex': OpenAlex_collector,
    'OpenAIRE': OpenAIRE_collector,
    'ORKG': ORKG_collector,
    ...
}
collector = api_collectors[api_name](config)
```

### Circuit Breaker
Fails fast for broken APIs:
- Tracks consecutive failures
- Opens circuit after 5 failures
- Skips requests when open

### Repository Pattern
Abstracts data storage:
- JSON for raw collection data
- CSV for aggregated results
- SQLite for citation cache

## Performance Features

- **Parallel Collection**: Multiple APIs simultaneously
- **Parallel Aggregation**: Batch processing with multiprocessing
- **Citation Caching**: SQLite cache avoids redundant API calls
- **Circuit Breaker**: Skip broken APIs quickly
- **Rate Limiting**: Per-API throttling
- **Bulk Operations**: Zotero uploads in batches

## Configuration System

Two user-facing files, validated by `scilex/settings/`:

- `scilex.yml` (one per review): pydantic models in `settings/schema.py` (unknown keys are rejected),
  named presets in `settings/presets.py`.
- `keys.yml` (shared, `~/.config/scilex/keys.yml`): API keys and rate limits, overridable with
  `SCILEX_<API>_<FIELD>` environment variables.

Priority for `scilex.yml` values: code defaults < preset < `scilex.yml` < command-line options.

`settings/loader.py` discovers and merges the files and `to_legacy()` converts them to the internal
`(main_config, api_config)` dictionaries consumed by `SciLExConfig`, the pipeline and the web API.
`settings/resolve.py` (`resolve_legacy_configs`) is the single entry point that also falls back to the
legacy `scilex.config.yml` + `scilex.advanced.yml` + `api.config.yml` files. `settings/migrate.py` converts
those to the new format (`scilex config migrate`).

To add an option: add it to the schema (`settings/schema.py`), map it in `to_legacy()`, handle it in
`settings/migrate.py`, document it in `scilex.yml.example` and in `docs/reference/configuration.md`.

See the [Configuration Reference](../reference/configuration.md).

## Error Handling

- Specific exception types (no bare `except`)
- 30-second timeouts on all API calls
- Retry logic with exponential backoff
- State files for recovery

## Directory Structure

```
scilex/
├── settings/                  # scilex.yml / keys.yml: schema, presets, loader, resolve, migrate, cli, advanced
├── config.py, config_defaults.py   # SciLExConfig and code defaults
├── crawlers/
│   ├── collectors/            # One collector class per API (inherit API_collector)
│   ├── collector_collection.py  # Orchestration and job management
│   ├── aggregate.py           # Format converters (one per API)
│   ├── aggregate_parallel.py  # Parallel aggregation
│   ├── converter_utils.py     # Shared converter helpers
│   └── key_pool.py            # API key rotation
├── pipeline/                  # Aggregation steps (filters, ranking, enrichment, reports)
├── citations/                 # Citation cache, fetchers, reference fetcher
├── Zotero/, rdf/, HuggingFace/, vpn/, templates/
├── run_collection.py          # scilex-collect
├── aggregate_collect.py       # scilex-aggregate
├── push_to_zotero.py          # scilex-push-zotero
├── export_to_bibtex.py, export_to_turtle.py, enrich_with_hf.py, init_templates.py
└── webapi/                    # FastAPI server

scilex.yml.example, keys.yml.example   # templates at the repository root

output/
└── <name>/                    # One folder per review (name in scilex.yml)
    ├── {API}/                 # Per-API raw results
    ├── config_used.yml        # Internal snapshot used by --resume
    └── aggregated_results.csv # Final output
```

## Adding New Components

### New API Collector

1. Create a collector class in `scilex/crawlers/collectors/<api_name>.py`
2. Implement abstract methods
3. Add format converter in `scilex/crawlers/aggregate.py`
4. Register in `api_collectors` dict in `scilex/crawlers/collector_collection.py`
5. Add to `keys.yml.example` and the `search.apis` list of `scilex.yml.example`

See [Adding Collectors](adding-collectors.md) for details.

### New Filter

1. Add the filter in `scilex/pipeline/`
2. Add the config option (schema, `to_legacy`, migrate, example, docs: see Configuration System)
3. Insert in filtering pipeline
4. Update documentation

## Testing

Tests in `tests/`:
- `test_dual_keyword_logic.py` - Keyword matching
- `test_openaire_collector.py` / `test_openaire_aggregation.py` - OpenAIRE
- `test_orkg_collector.py` / `test_orkg_aggregation.py` - ORKG
- Unit tests for collectors and format converters

Run: `uv run python -m pytest tests/`
