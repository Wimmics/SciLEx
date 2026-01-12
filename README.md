![Scilex](img/projectLogoScilex.png)
# SciLEx

**SciLEx** (Science Literature Exploration) is a Python toolkit for systematic literature reviews. Crawl 9+ academic APIs, deduplicate papers, analyze citation networks, and push to Zotero with advanced quality filtering.

I developed SciLEx scripts in the context of a systematic review conducted during my PhD, introduced in:
> Celian Ringwald. Learning Pattern-Based Extractors from Natural Language and Knowledge Graphs: Applying Large Language Models to Wikipedia and Linked Open Data. AAAI-24 - 38th AAAI Conference on Artificial Intelligence, Feb 2024, Vancouver, Canada. pp.23411-23412, ⟨10.1609/aaai.v38i21.30406⟩. ⟨hal-04526050⟩

---

## Key Features

- Multi-API collection with parallel processing (SemanticScholar, OpenAlex, IEEE, Arxiv, Springer, HAL, DBLP, Istex, GoogleScholar)
- Smart deduplication using DOI, URL, and fuzzy title matching
- Parallel aggregation with configurable workers (default mode)
- Citation network extraction via OpenCitations + Semantic Scholar with SQLite caching
- Quality filtering pipeline with time-aware citation thresholds, relevance ranking, and itemType filtering
- HuggingFace enrichment (NEW): Extract ML models, datasets, GitHub stats, and AI keywords
- Bulk Zotero upload in batches of 50 items
- Idempotent collections for safe re-runs (automatically skips completed queries)

---

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Configure APIs and search parameters
cp src/api.config.yml.example src/api.config.yml
cp src/scilex.config.yml.example src/scilex.config.yml
cp src/scilex.advanced.yml.example src/scilex.advanced.yml

# Edit with your API keys and keywords

# 3. Main workflow
uv run python src/run_collecte.py           # Collect papers from APIs
uv run python src/aggregate_collect.py      # Deduplicate & filter (parallel by default)
uv run python src/push_to_zotero.py         # Push to Zotero (optimized)

# 4. Optional: Enrich with HuggingFace metadata
uv run python src/getHF_collect.py          # Add ML models, datasets, GitHub stats

```

---

## Core Commands

### Collection & Aggregation

```bash
# Basic collection
uv run python src/run_collecte.py

# Aggregation with all features (default: parallel mode)
uv run python src/aggregate_collect.py
# Optional flags:
#   --auto-install-spacy: Skip spacy model prompt
#   --skip-citations: Skip citation fetching
#   --workers N: Citation workers (default: 3)
#   --parallel-workers N: Aggregation workers (default: auto)
#   --profile: Show performance stats
```

### Zotero Integration

```bash
uv run python src/push_to_zotero.py

# Legacy script (DEPRECATED)
uv run python src/push_to_Zotero_collect.py
```

### HuggingFace Enrichment (NEW)

```bash
# Full enrichment
uv run python src/getHF_collect.py

# Dry run (preview matches without updating)
uv run python src/getHF_collect.py --dry-run --limit 10

# Process specific collection
uv run python src/getHF_collect.py --collection "ML_Papers"
```

### Code Quality

```bash
# Format and lint
uvx ruff format .
uvx ruff check --fix .
```

---

## Supported APIs

| API | Key Required | Rate Limit | Abstract | Citations | Best For |
|-----|--------------|------------|----------|-----------|----------|
| **SemanticScholar** | Optional | 1/sec (100/page regular, 1000/page bulk) | ✓ | ✓ | CS/AI papers, citation networks |
| **OpenAlex** | No | 10/sec, 100k/day | ~60% | ✓ | Broad coverage, ORCID data |
| **IEEE** | Yes | 10/sec, 200/day | ✓ | ✓ | Engineering, CS conferences |
| **Arxiv** | No | 3/sec | ✓ | ✗ | Preprints, physics, CS |
| **Springer** | Yes | 1.5/sec | ✓ | Partial | Journals, books |
| **Elsevier** | Yes | 6/sec | Partial | ✓ | Medical, life sciences |
| **HAL** | No | 10/sec | ✓ | ✗ | French research, theses |
| **DBLP** | No | 10/sec | ✗ (copyright) | ✗ | CS bibliography, 95%+ DOI coverage |
| **Istex** | No | Conservative | ✓ | ✗ | French institutional access |

**Notes:**
- **SemanticScholar bulk mode**: 10x faster collection but requires higher-tier API access
- **DBLP**: No abstracts by design (copyright restrictions), but excellent bibliographic metadata
- Rate limits are configurable in `api.config.yml`

---

## Advanced Features

### Quality Filtering Pipeline

1. **ItemType filtering** (whitelist mode): Keep only journalArticle, conferencePaper, book, bookSection
2. **Dual keyword enforcement**: Papers must match keywords from BOTH groups (if dual-group mode configured)
3. **Abstract quality scoring**: Metadata completeness (DOI, title, authors weighted higher)
4. **Time-aware citation filtering**:
   - 0-18 months: 0 citations required (grace period)
   - 18-21 months: 1+ citation
   - 21-24 months: 3+ citations
   - 24-36 months: 5-8+ citations (gradual increase)
   - 36+ months: 10+ citations (established papers)
5. **Relevance ranking**: Composite score (keywords 45%, quality 25%, itemType 20%, citations 10%)

### Performance Optimizations

- Parallel aggregation (default mode, configurable workers)
- SQLite citation caching with 30-day TTL
- Circuit breaker pattern for failed API endpoints
- Bulk Zotero upload in batches of 50 items

### HuggingFace Enrichment

- Fuzzy title matching with 85% threshold
- Extracts: TASK, PTM (pre-trained models), ARCHI, DATASET, FRAMEWORK, GITHUB_STARS
- Updates Zotero fields: `archive` (HF URL), `archiveLocation` (GitHub repo)
- Match rate: 30-50%, with SQLite caching (30-day TTL)

---

## Configuration

### `src/scilex.config.yml` - Collection Parameters

- **`keywords`**: Single or dual group mode
  - Single: `[["term1", "term2"], []]` (ANY match)
  - Dual: `[["group1"], ["group2"]]` (AND logic between groups)
- **`years`**: List of years to search (e.g., [2020, 2021, 2022, 2023, 2024])
- **`apis`**: Which APIs to query (e.g., ['SemanticScholar', 'IEEE', 'OpenAlex'])
- **`semantic_scholar_mode`**: "regular" (100/page) or "bulk" (1000/page)
- **`aggregate_get_citations`**: Enable automatic citation fetching
- **`quality_filters`**: Relevance weights, max_papers limit, citation thresholds

### `src/api.config.yml` - API Credentials

- **Zotero**: `api_key`, `user_id`, `collection_id`
- **IEEE, Elsevier, Springer**: `api_key` (required)
- **SemanticScholar, HuggingFace**: `token` (optional, improves rate limits)
- **`rate_limits`**: Per-API request limits (configurable)

---

## Documentation & Contributing

- **Output structure**: `output/collect_YYYYMMDD_HHMMSS/` with timestamped collections
- **Idempotent design**: Safe re-runs automatically skip completed queries
- **Built for**: Systematic reviews in AI/ML research (PhD context)

### Contributing

- Report issues: [GitHub Issues](https://github.com/datalogism/SciLEx/issues)

### Requirements

- Python ≥3.13
- uv package manager
