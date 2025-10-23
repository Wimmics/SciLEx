# SciLEx Paper Collection Workflow - Precision Trace Analysis


---

## DATA FLOW SUMMARY

```
scilex.config.yml + api.config.yml
  ↓
Query Matrix Generation (keywords × years × APIs)
  ↓
Parallel API Collection (multiprocessing)
  ↓
JSON Pages (output/{collect_name}/{API}/{query_id}/{page}.json)
  ↓
Format Unification ({API}toZoteroFormat)
  ↓
Deduplication (quality-based merge)
  ↓
Citation Enrichment (OpenCitations, optional)
  ↓
FileAggreg.csv
  ↓
Zotero Library Publication
```

---

## CRITICAL FILE REFERENCES

| Phase | File | Key Lines | Purpose |
|-------|------|-----------|---------|
| Entry | src/run_collecte.py | 75-77 | Instantiate CollectCollection and trigger jobs |
| Setup | src/crawlers/collector_collection.py | 235-255 | Initialize directories and state tracking |
| Query Gen | src/crawlers/collector_collection.py | 91-147 | Generate keyword×year×API combinations |
| Orchestration | src/crawlers/collector_collection.py | 257-289 | Multiprocessing job creation and execution |
| Collection | src/crawlers/collectors.py | 148-298 | Paginated API data retrieval with rate limiting |
| State Update | src/crawlers/collector_collection.py | 157-195 | Atomic state updates with lock |
| Aggregation | src/aggregate_collect.py | 45-123 | Format unification and deduplication |
| Dedup Logic | src/crawlers/aggregate.py | 48-103 | Quality-based duplicate merging |
| Citations | src/citations/citations_tools.py | 31-60 | OpenCitations citation graph retrieval |
| Zotero Auth | src/push_to_Zotero_collect.py | 50-65 | Dynamic user ID authentication |
| Zotero Push | src/push_to_Zotero_collect.py | 163-247 | Item creation with duplicate detection |

---

## DETAILED PHASE DESCRIPTIONS

### Phase 1: Configuration & Initialization

**File**: `src/run_collecte.py:37-75`

1. Load YAML configs: `scilex.config.yml`, `api.config.yml`
2. Extract: output_dir, keywords, years, APIs list
3. Create output directory if needed
4. Instantiate `CollectCollection(main_config, api_config)`

### Phase 2: Collection Setup

**File**: `src/crawlers/collector_collection.py:54-56, 235-255`

1. `CollectCollection.__init__()` → calls `init_collection_collect()`
2. Create timestamped collection directory: `output/{collect_name}/`
3. Generate query matrix via `queryCompositor()`:
   - Cartesian product: keywords × years × APIs
   - Supports single or dual keyword list strategies
   - Groups results by API: `{"API1": [queries], "API2": [queries]}`
4. Initialize `state_details.json` with three-level tracking:
   - Global state (all collections)
   - Per-API state
   - Per-query state (keyword, year, pagination info)

### Phase 3: Parallel Collection Execution

**File**: `src/crawlers/collector_collection.py:257-289`

1. `create_collects_jobs()`: Check state_details for incomplete jobs
2. Group jobs by API to prevent rate limit violations
3. Spawn multiprocessing pool: `min(num_APIs, cpu_count)` processes
4. Each process calls `run_job_collects(api_job_list)`

**Per-API Sequential Execution**: `collector_collection.py:62-89`

- For each query in API's job list:
  - Instantiate API-specific collector (e.g., `IEEE_collector`)
  - Call `collector.runCollect()` → paginated data retrieval
  - Update `state_details.json` atomically (multiprocessing lock)
  - Sleep 2 seconds between queries

### Phase 4: API Collection Mechanics

**File**: `src/crawlers/collectors.py:148-298`
**Method**: `API_collector.runCollect()`

Pagination loop:

1. Check if already complete (state == 1) → skip
2. Calculate offset: `get_offset(page)`
3. Build URL: `get_configurated_url().format(offset)`
4. API call with rate limiting: `api_call_decorator(url)`
   - Uses `@sleep_and_retry` + `@limits(calls=rate_limit, period=1)`
   - Automatic backoff on rate limit hit
5. Parse response: `parsePageResults(response, page)`
6. Save to JSON: `output/{collect_name}/{API}/{query_id}/{page}.json`
7. Update pagination state: `set_lastpage(page + 1)`
8. Check continuation: `has_more_pages = (results == max_per_page)`
9. Return state data: `{state, last_page, total_art, coll_art}`

**Special Cases**:
- **Springer**: Uses `collect_from_endpoints()` instead of standard pagination
- **Arxiv**: Filters None entries post-parse
- **10k result limit** enforced per query

### Phase 5: Aggregation & Deduplication

**File**: `src/aggregate_collect.py:32-123`

1. Read `state_details.json` to locate all collected JSON files
2. For each API → query → page:
   - Load JSON results
   - Convert to unified format: `{API}toZoteroFormat(row)`
   - Apply keyword filter (optional): check title/abstract
   - Collect all entries into list
3. Create DataFrame and deduplicate:
   - `deduplicate(df)`: Quality-based merge on DOI + title
   - For duplicates: select highest quality, merge missing fields
   - Mark selected source with asterisk in archive field
4. Save: `output/{collect_name}/FileAggreg.csv`

### Phase 6: Citation Enrichment (Optional)

**File**: `src/citations/citations_tools.py:31-60`
**Trigger**: `aggregate_get_citations` config flag

For each paper with DOI:

1. `getRefandCitFormatted(doi)`:
   - Call OpenCitations API: `getCitations(doi)` → papers citing this
   - Call OpenCitations API: `getReferences(doi)` → papers cited by this
   - Rate limit: 10 calls/second
2. Store in CSV: `extra` field (JSON string), `nb_cited`, `nb_citation`

### Phase 7: Zotero Push

**File**: `src/push_to_Zotero_collect.py:73-247`

1. Authenticate: `get_zotero_user_id(api_key)` via `/keys/current`
2. Query collections: GET `/users/{id}/collections` or `/groups/{id}/collections`
3. Find or create target collection
4. Fetch existing items to detect duplicates (by URL field)
5. For each aggregated paper:
   - Fetch Zotero template: `/items/new?itemType={type}`
   - Map fields: title, DOI, authors (parse semicolon-separated), abstract, etc.
   - POST to Zotero: `/users/{id}/items` or `/groups/{id}/items`
   - Skip if URL already exists in collection

---

## CONCLUSION

This precision trace provides a complete execution map of the SciLEx paper collection system, from configuration through final publication to Zotero. The system demonstrates:

- **Sophisticated state management** for resumable operations
- **Parallel execution with rate limit safety** through intelligent API grouping
- **Progressive data refinement** through multiple transformation stages
- **Extensible plugin architecture** for adding new academic APIs
- **Quality-based deduplication** that preserves best metadata across sources

The workflow supports systematic literature reviews by automating the collection, deduplication, citation analysis, and reference management of academic papers from multiple sources.
