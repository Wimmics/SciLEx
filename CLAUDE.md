# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SciLEx (Science Literature Exploration) is a Python toolkit for systematic literature reviews. It crawls 10 academic APIs, deduplicates papers, extracts citation networks, and pushes to Zotero with quality filtering.

## Quick Reference - Commands

```bash
# Setup
uv sync                                      # Install dependencies
cp src/api.config.yml.example src/api.config.yml    # Create API config
cp src/scilex.config.yml.example src/scilex.config.yml  # Create collection config

# Main workflow
uv run python src/run_collection.py                   # 1. Collect papers from APIs
uv run python src/aggregate_collect.py              # 2. Deduplicate & filter (parallel)
uv run python src/enrich_with_hf.py                 # 3. (Optional) HuggingFace CSV enrichment
uv run python src/push_to_zotero.py                 # 4. Push to Zotero (OR export to BibTeX below)
uv run python src/export_to_bibtex.py               # 4. (Alternative) Export to BibTeX file

# Aggregation flags
uv run python src/aggregate_collect.py --skip-citations     # Skip citation fetching
uv run python src/aggregate_collect.py --workers 5          # Citation workers (default: 3)
uv run python src/aggregate_collect.py --profile            # Performance stats

# Code quality (run before committing)
uvx ruff format .                            # Format code
uvx ruff check --fix .                       # Lint and fix

# Testing
uv run python -m pytest tests/                      # Run all tests
uv run python -m pytest tests/test_dual_keyword_logic.py   # Run specific test

# Debug logging
LOG_LEVEL=DEBUG uv run python src/run_collection.py  # Full diagnostic details
LOG_LEVEL=INFO uv run python src/run_collection.py   # Key milestones only
```

## Architecture

### Core Pipeline (6 phases)

```
1. Collection  →  2. Aggregation  →  3. Citations  →  4. HF Enrich  →  5. Output
run_collection.py   aggregate.py       citations/       enrich_with_hf   push_to_zotero.py
                                     (optional)       (optional)       OR export_to_bibtex.py
```

## Deprecated Code

The following modules/scripts have been moved to `.deprecated/` and are no longer maintained:
- `PWC/` - Replaced by HuggingFace enrichment
- `tagging/` - Manual Zotero operations (not automated)
- `orcid/`, `doi/`, `text_analysis/` - Functionality integrated into collectors
- `annotation_agreement/` - Research tool (not pipeline)
- `API tests/` - Replaced by unit tests
- `getLPWC_collect.py` - Use `enrich_with_hf.py` instead
- `optimize_keywords.py` - Standalone tool (not integrated)

See `.deprecated/INVENTORY.md` for details.

### Key Files

| File | Purpose |
|------|---------|
| `src/run_collection.py` | Main collection orchestrator |
| `src/aggregate_collect.py` | Deduplication, filtering, relevance ranking |
| `src/enrich_with_hf.py` | HuggingFace CSV enrichment (adds HF metadata to aggregated CSV) |
| `src/push_to_zotero.py` | Bulk upload to Zotero (50 items/batch) |
| `src/export_to_bibtex.py` | Export aggregated papers to BibTeX format |
| `src/getHF_collect.py` | HuggingFace metadata enrichment (legacy Zotero-based) |
| `src/constants.py` | `MISSING_VALUE`, `is_valid()`, config classes |
| `src/crawlers/collectors/base.py` | `API_collector` base class |
| `src/crawlers/collector_collection.py` | `CollectCollection` orchestrator |
| `src/crawlers/aggregate.py` | Format converters for all APIs |
| `src/Zotero/zotero_api.py` | `ZoteroAPI` client class |
| `src/citations/citations_tools.py` | Citation fetching (cache → SS → OpenCitations) |

### Collector Classes (`src/crawlers/collectors/`)

Each API has its own collector inheriting from `API_collector`:
- `semantic_scholar.py`, `openalex.py`, `ieee.py`, `elsevier.py`, `springer.py`
- `arxiv.py`, `hal.py`, `dblp.py`, `istex.py`, `google_scholar.py`

**To add a new API:**
1. Create collector in `src/crawlers/collectors/` inheriting `API_collector`
2. Implement: `__init__()`, `query_build()`, `run()`, `parsePageResults()`
3. Add format converter in `src/crawlers/aggregate.py` (use `MISSING_VALUE`, `is_valid()`)
4. Register in `api_collectors` dict in `src/crawlers/collector_collection.py`

### Data Flow

```
output/
└── collect_YYYYMMDD_HHMMSS/
    ├── config_used.yml              # Config snapshot
    ├── SemanticScholar/
    │   └── 0/                       # Query ID
    │       ├── page_1               # JSON results
    │       └── page_2
    ├── OpenAlex/
    └── aggregated_results.csv       # Final deduplicated output
```

## Configuration

### `src/scilex.config.yml` - Search Parameters

```yaml
keywords:
  # Single group (OR): [["term1", "term2"], []]
  # Dual groups (AND): [["group1"], ["group2"]]
years: [2022, 2023, 2024]
apis: ['SemanticScholar', 'OpenAlex', 'IEEE']
semantic_scholar_mode: "regular"  # "bulk" = 10x faster but needs higher-tier access
aggregate_get_citations: true     # Enable citation fetching
```

## BibTeX Export (Alternative to Zotero)

Export aggregated papers to BibTeX format for LaTeX, Overleaf, and citation managers. Use as alternative to Zotero push for better pipeline integration.

```bash
# Export to BibTeX (generates aggregated_results.bib in collection directory)
uv run python src/export_to_bibtex.py
```

### Features

- **Citation Keys**: DOI-based (e.g., `10_1021_acsomega_2c06948`) - unique and portable
- **PDF Links**: Direct download URLs in `file` field when available
- **Full Abstracts**: No truncation (previously limited to 500 chars)
- **Field Mapping**:
  - `authors` → `author` (semicolon-separated → "and" separated)
  - `journalAbbreviation` → `journal` (for articles)
  - `conferenceName` → `booktitle` (for proceedings)
  - `volume`, `issue`, `pages`, `publisher` → corresponding BibTeX fields
  - `pdf_url` → `file` (direct PDF downloads)
  - `DOI`, `url`, `abstract` → corresponding BibTeX fields
  - `language` → `language` (paper language)
  - `rights` → `copyright` (license/rights information)
  - `archive` → `archiveprefix` (source API name)
  - `archiveID` → `eprint` (original API ID)
  - `tags` → `keywords` (HuggingFace tags if enriched)
  - `hf_url` → `note` (HuggingFace paper URL)
  - `github_repo` → `howpublished` (GitHub repository)

### Output

- **File**: `output/collect_YYYYMMDD_HHMMSS/aggregated_results.bib`
- **Format**: Single BibTeX file with all papers
- **Compatibility**: Works with JabRef, Zotero, Overleaf, LaTeX

### Entry Types

| CSV ItemType | BibTeX Entry | Usage |
|---|---|---|
| journalArticle | @article | Journal papers |
| conferencePaper | @inproceedings | Conference proceedings |
| bookSection | @incollection | Book chapters |
| book | @book | Books |
| preprint | @misc | Preprints (arXiv) |
| Manuscript | @unpublished | Unpublished manuscripts |

### PDF Link Sources

**For Users:**

The `file` field in BibTeX entries contains **direct PDF download URLs** when available. This is different from the `url` field:
- **`file`**: Direct link to download the PDF (e.g., `https://arxiv.org/pdf/2307.03172.pdf`)
- **`url`**: Landing page on the publisher's website (for humans to browse)

**Coverage:**
- **~40-60% of papers** will have PDF links (only open-access papers)
- **Best sources**: arXiv (100%), SemanticScholar open-access, OpenAlex open-access
- **Limited/No PDFs**: Paywalled journals, IEEE (institutional access required), Springer (rare)

**PDF Sources by API:**

| API | PDF Availability | Example Sources |
|-----|------------------|-----------------|
| **arXiv** | ✅ Always (100%) | arxiv.org, bioRxiv, medRxiv preprints |
| **SemanticScholar** | ✅ Good (~60%) | Open-access journals, preprint servers, institutional repos |
| **OpenAlex** | ✅ Good (~50%) | DOAJ, PubMed Central, institutional repos |
| **HAL** | ✅ Good (~70%) | French institutional repositories |
| **IEEE** | ⚠️ Rare | Requires subscription (direct API field when available) |
| **Springer** | ❌ Rarely | Paywalled content |
| **Elsevier** | ❌ Rarely | Paywalled content |
| **Others** | ❌ No | No PDF fields in API response |

**For Developers:**

The `pdf_url` field is populated during aggregation in `src/crawlers/aggregate.py`:

| API | Source Field | Implementation |
|-----|-------------|----------------|
| **SemanticScholar** | `row["open_access_pdf"]` | Line 414: Direct from API (includes bioRxiv, medRxiv, etc.) |
| **arXiv** | Constructed | Line 594: `https://arxiv.org/pdf/{arxiv_id}.pdf` |
| **OpenAlex** | `oa_location["pdf_url"]` | Line 901: From `best_oa_location` field |
| **HAL** | `files_s[0]` | Lines 780-786: First `.pdf` file in list |
| **IEEE** | `row["pdf_url"]` | Line 1075: Direct from API (when available) |
| **Others** | N/A | Default: `MISSING_VALUE` |

**Technical Notes:**
- Only valid URLs are included (validated via `is_valid()` from `src/constants.py`)
- SemanticScholar's `open_access_pdf` field indexes multiple preprint servers (bioRxiv, medRxiv, SSRN)
- OpenAlex uses the "best" open-access location (preference: repository > publisher)

### BibTeX Field Reference

Complete reference for all BibTeX fields in exported entries:

#### Core Bibliographic Fields

| Field | Description | Example | When Present |
|-------|-------------|---------|--------------|
| `title` | Paper title | `Deep Learning for NLP` | Always |
| `author` | Authors (BibTeX "and" format) | `John Smith and Jane Doe` | Always (or "Unknown") |
| `year` | Publication year | `2024` | When date available |
| `journal` | Journal name | `Nature` | Article entries only |
| `booktitle` | Conference name | `ACL 2024` | Inproceedings only |
| `volume` | Volume number | `15` | When available |
| `number` | Issue number | `3` | When available |
| `pages` | Page range | `123--145` | When available |
| `publisher` | Publisher name | `Springer` | Books/chapters only |

#### Links and Access **[CRITICAL FOR AGENTIC PIPELINES]**

| Field | Description | Purpose | Example |
|-------|-------------|---------|---------|
| **`file`** | **Direct PDF download URL** | **Automated PDF retrieval** | `https://arxiv.org/pdf/2307.03172.pdf` |
| **`url`** | **Paper landing page URL** | **Human browsing, metadata** | `https://arxiv.org/abs/2307.03172` |

**Key Difference:**
- **`file`**: Use this for **downloading PDFs programmatically** in agentic pipelines. This is a direct link to the PDF file that can be fetched with HTTP GET.
- **`url`**: Use this for **metadata retrieval** or **human interaction**. This is the publisher's landing page, which may require clicking "Download PDF" buttons or authentication.

**Availability:**
- `file` is present for ~40-60% of papers (open access sources: arXiv, SemanticScholar, OpenAlex, HAL)
- `url` is present for ~95% of papers (DOI resolution or direct API URLs)

**Example for Agentic Pipeline:**
```python
# ✓ CORRECT: Download PDF directly
if 'file' in entry:
    pdf_content = requests.get(entry['file']).content

# ✗ WRONG: This is a landing page, not a PDF
if 'url' in entry:
    pdf_content = requests.get(entry['url']).content  # Returns HTML, not PDF!
```

#### Identifiers and Metadata

| Field | Description | Example | Use Case |
|-------|-------------|---------|----------|
| `doi` | Digital Object Identifier | `10.1038/s41586-024-07146-0` | Permanent citation |
| `abstract` | Full paper abstract (no truncation) | `In this paper we...` | Text analysis |
| `language` | Paper language | `en` | Language filtering |
| `copyright` | License/rights | `CC-BY-4.0` | Usage permissions |

#### Source Tracking

| Field | Description | Example | Purpose |
|-------|-------------|---------|---------|
| `archiveprefix` | Source API name | `SemanticScholar` | Provenance tracking |
| `eprint` | Original API ID | `2307.03172` | Cross-referencing |

#### HuggingFace Enrichment (Optional)

| Field | Description | Example | When Present |
|-------|-------------|---------|--------------|
| `keywords` | ML tags from HuggingFace | `TASK:NER, PTM:BERT` | After `enrich_with_hf.py` |
| `note` | HuggingFace paper URL | `HuggingFace: https://...` | After enrichment |
| `howpublished` | GitHub repository | `https://github.com/...` | After enrichment |

#### Example Entry with All Fields

```bibtex
@article{10_48550_arxiv_2307_03172,
  title = {Llama 2: Open Foundation and Fine-Tuned Chat Models},
  author = {Hugo Touvron and Louis Martin and Kevin Stone},
  year = {2023},
  journal = {arXiv},
  doi = {10.48550/arXiv.2307.03172},
  url = {https://arxiv.org/abs/2307.03172},
  file = {https://arxiv.org/pdf/2307.03172.pdf},
  abstract = {In this work, we develop and release Llama 2...},
  language = {en},
  archiveprefix = {arXiv},
  eprint = {2307.03172},
  keywords = {TASK:TextGeneration, PTM:Llama2, FRAMEWORK:PyTorch},
  note = {HuggingFace: https://huggingface.co/papers/2307.03172},
  howpublished = {https://github.com/facebookresearch/llama}
}
```

### `src/api.config.yml` - API Keys & Rate Limits

```yaml
SemanticScholar:
  api_key: "your-key"  # Optional but recommended
IEEE:
  api_key: "your-key"  # Required
rate_limits:
  SemanticScholar: 1.0  # req/sec
  OpenAlex: 10.0
```

## HuggingFace Enrichment (CSV-Based)

Enriches aggregated papers with HF metadata (tags, URLs, GitHub repos) BEFORE pushing to Zotero or exporting to BibTeX.

### Workflow

```bash
# Enrich CSV with HuggingFace metadata
uv run python src/enrich_with_hf.py

# Then choose output format:
uv run python src/push_to_zotero.py      # Push to Zotero (with tags)
# OR
uv run python src/export_to_bibtex.py    # Export to BibTeX (with keywords)
```

### What It Does

1. Reads `aggregated_results.csv`
2. For each paper: searches HuggingFace Hub for matches
3. Adds three columns to CSV:
   - `tags`: Semicolon-separated HF tags (e.g., `"TASK:NER;PTM:BERT;DATASET:Squad"`)
   - `hf_url`: HuggingFace paper/model URL
   - `github_repo`: GitHub repository URL
4. Writes updated CSV back to same path

### Usage

```bash
# Normal run (updates CSV in-place)
uv run python src/enrich_with_hf.py

# Dry run (preview matches without updating)
uv run python src/enrich_with_hf.py --dry-run --limit 10

# Process specific number of papers
uv run python src/enrich_with_hf.py --limit 100
```

### Configuration

Existing config in `src/scilex.config.yml` (no changes needed):
```yaml
hf_enrichment:
  enabled: true                      # Enable/disable enrichment
  use_papers_api: true               # Use Papers API (recommended)
  fuzzy_match_threshold: 85          # Match threshold (0-100)
  cache_path: "output/hf_cache.db"   # SQLite cache location
  cache_ttl_days: 30                 # Cache expiration
```

### Tag Format

Tags follow the PapersWithCode convention with these prefixes:
- `TASK:` - ML task (e.g., `TASK:TextClassification`)
- `PTM:` - Pre-trained model (e.g., `PTM:BERT`)
- `DATASET:` - Training dataset (e.g., `DATASET:Squad`)
- `FRAMEWORK:` - ML framework (e.g., `FRAMEWORK:PyTorch`)
- `GITHUB_STARS:` - GitHub popularity (e.g., `GITHUB_STARS:366`)
- `CITED_BY_DATASET:` - Datasets citing the paper (e.g., `CITED_BY_DATASET:Glue`)
- (no prefix) - AI-extracted keywords from paper

### BibTeX Export with HF Metadata

When exporting to BibTeX after enrichment, HF tags are included:
```bibtex
@article{10_1021_acsomega_2c06948,
  title = {Paper Title},
  keywords = {TASK:TextClassification, PTM:BERT, FRAMEWORK:PyTorch},
  note = {HuggingFace: https://huggingface.co/papers/2307.03172},
  howpublished = {https://github.com/author/repo}
}
```

### Zotero Push with HF Metadata

When pushing to Zotero after enrichment:
- `tags` → Zotero item tags (multiple tags from HF)
- `github_repo` → Zotero `archiveLocation` field
- Original `archive` field preserved (API source)

### Key Features

- **Cache Sharing**: Uses same cache as `getHF_collect.py` (faster re-runs)
- **Backward Compatible**: Old CSVs without HF columns still work
- **Flexible Output**: Enriched CSV can go to Zotero OR BibTeX
- **No Data Loss**: Original `archive` field (API source) preserved

## Code Patterns

### Missing Value Handling

```python
from src.constants import MISSING_VALUE, is_valid, is_missing, safe_str

# Always use these instead of hardcoded "NA" or None checks
if is_valid(paper.get("DOI")):
    doi = paper["DOI"]
else:
    doi = MISSING_VALUE
```

### API Calls

```python
# All collectors use api_call_decorator() which provides:
# - Rate limiting (from api.config.yml)
# - Circuit breaker (fail-fast after 5 consecutive failures)
# - Retry with exponential backoff
# - 30-second timeout

response = self.api_call_decorator(url)
response.raise_for_status()  # Always check status
```

### Multiprocessing

- Uses **spawn mode** (safe on macOS/Windows)
- Worker functions at **module level** (not class methods)
- Always use `pool.close()` + `pool.join()` for cleanup

## Quality Filtering Pipeline

The aggregation applies these filters in order:

1. **URL from DOI** - Generate URLs for papers missing URL but having DOI
2. **ItemType filter** - Whitelist: journalArticle, conferencePaper, book, bookSection
3. **Dual keyword enforcement** - Papers must match BOTH keyword groups (if dual-group mode)
4. **Quality scoring** - Metadata completeness (DOI, title, authors weighted higher)
5. **Time-aware citation filter** - Graduated thresholds (0-18mo: 0 cites, 36mo+: 10+ cites)
6. **Relevance ranking** - Composite score: keywords 45%, quality 25%, itemType 20%, citations 10%

## Supported APIs

| API | Key Required | Rate Limit | Notes |
|-----|--------------|------------|-------|
| SemanticScholar | Optional | 1/sec | Best for CS/AI, citations |
| OpenAlex | No | 10/sec | Broad coverage, ~60% abstracts |
| IEEE | Yes | 10/sec, 200/day | Engineering, CS conferences |
| Arxiv | No | 3/sec | Preprints, no citations |
| Springer | Yes | 1.5/sec | Journals, books |
| Elsevier | Yes | 6/sec | Medical, requires inst_token |
| PubMed | Optional | 3/sec (10/sec with key) | 35M biomedical papers, provides PMC landing page URLs (100% coverage for papers with PMCID) |
| ~~PubMed Central~~ | ~~Optional~~ | ~~3/sec (10/sec with key)~~ | ~~Deprecated - use PubMed with OA Service instead~~ |
| HAL | No | 10/sec | French research |
| DBLP | No | 10/sec | No abstracts (copyright), 95%+ DOI |
| Istex | No | Conservative | French institutional |
| GoogleScholar | No | 2/sec | Uses Tor proxy, slow |

## Known Issues

### Case Sensitivity in API Names
API directory names must match config exactly. If collector creates `Istex/` but config has `ISTEX`, papers are excluded.

**Fix:** Rename directory or update `self.api_name` in collector to match config.

### Google Scholar Setup
Requires Tor for reliable operation:
```bash
brew install tor && brew services start tor  # macOS
```

## PubMed Integration

**Architecture:**
- PubMed as primary biomedical source (35M papers)
- Direct PMC landing page URLs (no API calls for PDFs)
- No separate PMC collector needed

**PDF Access:**
PubMed collector provides PMC landing page URLs:
1. Search PubMed E-utilities for papers
2. Extract PMCID from metadata
3. Construct PMC landing page URL: `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{id}/`
4. Papers with PMCID get clickable URLs to article pages
5. Users can download PDFs via "Download PDF" button on landing page

**Coverage:**
- All biomedical literature (open-access + paywalled metadata)
- 100% of papers with PMCID get valid PMC URLs (vs 20-30% with old FTP approach)
- HTTP landing pages work in all browsers (FTP URLs often blocked)
- ~10x faster collection (no OA Service API calls)
- Complete metadata for systematic reviews

**Fields:**
- PMID: Primary identifier
- PMCID: When available (links to PDF)
- MeSH terms: Medical subject headings (optional)
- DOI, abstract, authors: Standard fields

**Usage:**

```bash
# Enable PubMed in scilex.config.yml
apis:
  - SemanticScholar
  - OpenAlex
  - PubMed  # Biomedical literature

# Run collection
uv run python src/run_collection.py
uv run python src/aggregate_collect.py
uv run python src/push_to_zotero.py
```

**Migrating from PubMedCentral:**

If your config uses `PubMedCentral`:

1. Update `scilex.config.yml`:
   ```yaml
   apis: ['PubMed']  # was: ['PubMedCentral']
   ```

2. Benefits:
   - 5x more papers (35M vs 7M)
   - Same PDF coverage for open-access
   - Metadata for paywalled papers (systematic reviews)

3. No other changes needed - existing workflows remain the same

## HuggingFace Enrichment

Enriches papers with ML metadata (replaces deprecated PaperWithCode):

```bash
uv run python src/getHF_collect.py --dry-run --limit 10  # Preview
uv run python src/getHF_collect.py                        # Full run
```

**Updates Zotero fields:**
- `archive`: HuggingFace paper URL
- `archiveLocation`: GitHub repo
- Tags: `TASK:`, `PTM:`, `DATASET:`, `FRAMEWORK:`, `GITHUB_STARS:`

**Match rate:** 30-50% (HF focuses on popular ML papers)

## Performance Notes

- **Parallel aggregation** (default): 100x faster than serial mode
- **Citation caching**: SQLite cache with 30-day TTL in `output/citation_cache.db`
- **Bulk Zotero upload**: 50 items/batch, 15-20x faster than legacy script
- **Circuit breaker**: Fails fast after 5 consecutive API failures

## Tests

```bash
uv run python -m pytest tests/                           # All tests
uv run python -m pytest tests/test_dual_keyword_logic.py # Keyword logic tests
uv run python -m pytest tests/test_pagination_bug.py     # Pagination tests
```
