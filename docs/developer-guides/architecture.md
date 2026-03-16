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
CSV Output / Zotero Export
```

## Core Components

### 1. Collection System

**Location**: `src/crawlers/collector_collection.py`

Orchestrates parallel API collection:
- Creates jobs from config (keywords × years × APIs)
- Runs collectors in parallel (multiprocessing)
- Tracks progress and handles errors
- Skips completed queries (idempotent)

**API Collectors** (`src/crawlers/collectors.py`):
- Base class: `API_collector`
- 11 active implementations: SemanticScholar, OpenAlex, IEEE, Elsevier, Springer, arXiv, HAL, DBLP, ISTEX, OpenAIRE, ORKG
- 1 deprecated: GoogleScholar
- Each handles query building, pagination, and response parsing

### 2. Aggregation Pipeline

**Location**: `src/aggregate_collect.py`

Processes collected papers:
1. Load JSON files from all APIs
2. Convert to unified format
3. Deduplicate (DOI, URL, fuzzy title)
4. Apply keyword filtering
5. Score quality
6. Filter by citations
7. Rank by relevance
8. Output to CSV

**Parallel Mode** (`src/crawlers/aggregate_parallel.py`):
- Multiprocessing for speed
- Batch processing (5000 papers/batch)
- Auto-detects CPU count

### 3. Format Converters

**Location**: `src/crawlers/aggregate.py`

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

**Location**: `src/aggregate_collect.py`

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

Hierarchical priority:
1. Default values (in code)
2. Config files (YAML)
3. Environment variables
4. Command-line arguments

## Error Handling

- Specific exception types (no bare `except`)
- 30-second timeouts on all API calls
- Retry logic with exponential backoff
- State files for recovery

## Directory Structure

```
src/
├── crawlers/
│   ├── collectors.py          # All API collector classes (monolithic)
│   ├── collector_collection.py  # Orchestration and job management
│   ├── aggregate.py           # Format converters (one per API)
│   └── aggregate_parallel.py  # Parallel aggregation
├── citations/
│   └── citations_tools.py
├── Zotero/
│   └── push_to_Zotero.py
├── API tests/                 # Manual API test scripts
├── run_collecte.py            # Main collection entry point
├── aggregate_collect.py       # Main aggregation entry point
├── push_to_Zotero_collect.py  # Zotero export entry point
├── scilex.config.yml          # Search configuration
└── api.config.yml.example     # API credentials template

scilex/                        # Package stubs (in development)
├── api.config.yml             # Active API credentials (not committed)
└── ...

output/
└── collect_*/                 # Timestamped collections
    ├── {API}/                 # Per-API results
    └── aggregated_data.csv    # Final output
```

## Adding New Components

### New API Collector

1. Create collector class in `src/crawlers/collectors.py`
2. Implement abstract methods
3. Add format converter in `src/crawlers/aggregate.py`
4. Register in `api_collectors` dict in `src/crawlers/collector_collection.py`
5. Add to config examples

See [Adding Collectors](adding-collectors.md) for details.

### New Filter

1. Add filter function in `src/aggregate_collect.py`
2. Add config options
3. Insert in filtering pipeline
4. Update documentation

## Testing

Tests in `tests/`:
- `test_dual_keyword_logic.py` - Keyword matching
- `test_openaire_collector.py` / `test_openaire_aggregation.py` - OpenAIRE
- `test_orkg_collector.py` / `test_orkg_aggregation.py` - ORKG
- Unit tests for collectors and format converters

Run: `uv run python -m pytest tests/`
