![Scilex](img/projectLogoScilex.png)

# SciLEx - Science Literature Exploration

A comprehensive Python framework for systematic literature reviews and academic paper exploration. SciLEx automates the entire workflow from paper discovery through citation network analysis and Zotero integration.

**Originally developed for PhD research and published in:**
> Celian Ringwald. Learning Pattern-Based Extractors from Natural Language and Knowledge Graphs: Applying Large Language Models to Wikipedia and Linked Open Data. AAAI-24 - 38th AAAI Conference on Artificial Intelligence, Feb 2024, Vancouver, France. pp.23411-23412, ⟨10.1609/aaai.v38i21.30406⟩. ⟨hal-04526050⟩

---

## Core Capabilities

SciLEx provides end-to-end tools to:

- **🔍 Crawl academic papers** from 9+ APIs (SemanticScholar, OpenAlex, IEEE, Elsevier, Springer, HAL, DBLP, Arxiv, Istex)
- **📊 Aggregate & deduplicate** papers across multiple sources with fuzzy matching
- **📈 Extract citation networks** using OpenCitations API
- **🏷️ Enrich metadata** from PaperWithCode (models, datasets) and custom tags
- **💾 Integrate with Zotero** for reference management with proper organization
- **🔗 Manage DOI and ORCID** lookups for author identification

## Quick Start

### 1. Prerequisites

- Python 3.13+
- [Zotero Desktop](https://www.zotero.org/download/) and [Zotero Connector](https://www.zotero.org/download/)
- [Zotero API Key](https://www.zotero.org/settings/keys)
- Optional API keys (see [Setup Guide](#setup))

### 2. Setup

**Clone and install:**
```bash
git clone <repository>
cd SciLEx
uv sync  # or: pip install -r requirements.txt
```

**Configure APIs:**
```bash
cp src/api.config.yml.example src/api.config.yml
# Edit with your API credentials
```

**Configure collection:**
```bash
cp src/scilex.config.yml.example src/scilex.config.yml
# Set keywords, years, APIs, and output directory
```

### 3. Run Collection Workflow

```bash
# 1. Collect papers from APIs
python src/run_collecte.py

# 2. Aggregate and deduplicate
python src/aggregate_collect.py

# 3. Enrich with citations (optional)
python src/citations/get_citations.py

# 4. Push to Zotero
python src/push_to_Zotero_collect.py

# 5. Add PaperWithCode metadata (optional)
python src/getLPWC_collect.py
```

---

## Setup & Configuration

### API Configuration

Create `src/api.config.yml` with your credentials. **Required APIs:**

| API | Key Required | How to Get |
|-----|--------------|-----------|
| Zotero | Yes | [Create API key](https://www.zotero.org/settings/keys) |
| IEEE | Yes | [Register here](https://developer.ieee.org/) |
| Elsevier | Yes | [Register here](https://dev.elsevier.com/) |
| Springer | Yes | [Register here](https://dev.springernature.com/) |

**Optional/Free APIs:**
- SemanticScholar (optional key for higher rate limits)
- OpenAlex, HAL, DBLP, Arxiv (no key required)
- GoogleScholar (no key required, slower)

See `src/api.config.yml.example` for detailed rate limit configuration.

### Collection Configuration

Edit `src/scilex.config.yml`:

```yaml
keywords:
  - ["machine learning", "deep learning"]  # Search group 1
  - ["knowledge graph"]                      # Search group 2
  # Papers matching terms from BOTH groups

years: [2023, 2024]
apis: ['SemanticScholar', 'OpenAlex', 'IEEE']

collect: true
aggregate_txt_filter: true
aggregate_get_citations: false  # Set true for citation enrichment
```

See `src/scilex.config.yml.example` for all options.

---

## Architecture Overview

### Data Flow

```
Collection Phase
├─ Query each API with keyword combinations
├─ Store raw responses per API
└─ Create resumable state file

         ↓

Aggregation Phase
├─ Convert all APIs to unified Zotero format
├─ Deduplicate across APIs (DOI, URL, fuzzy title)
├─ Apply quality filters and text validation
└─ Generate aggregated_data.csv

         ↓

Enhancement Phases (Optional)
├─ Citation enrichment (OpenCitations API)
├─ PaperWithCode integration (models, datasets)
└─ Custom tagging and ORCID lookups

         ↓

Push Phase
├─ Detect duplicates in Zotero
├─ Create properly formatted items
└─ Organize in collections
```

### Directory Structure

```
SciLEx/
├── src/
│   ├── crawlers/              # Collection engine
│   │   ├── collector_collection.py
│   │   ├── collectors.py      # Per-API collectors
│   │   ├── aggregate.py       # Deduplication & format conversion
│   │   └── utils.py
│   ├── Zotero/                # Zotero integration
│   │   ├── zotero_api.py      # Reusable API client
│   │   └── push_to_Zotero.py  # Main push script
│   ├── citations/             # Citation network analysis
│   ├── PWC/                   # PaperWithCode extraction
│   ├── API tests/             # Individual API tests
│   ├── tagging/               # Custom tagging
│   ├── text_analysis/         # Text mining
│   ├── constants.py           # Centralized constants & helpers
│   ├── run_collecte.py        # Main entry point
│   └── aggregate_collect.py   # Aggregation entry point
├── output/                    # Collection results
│   └── collect_YYYYMMDD_HHMMSS/
│       ├── state_details.json
│       ├── SemanticScholar/
│       ├── aggregated_data.csv
│       └── aggregated_data_with_citations.csv
├── CLAUDE.md                  # Technical documentation (for Claude Code)
├── README.md                  # This file
└── pyproject.toml
```

---

## Supported APIs

| API | Key Required | Free Tier | Rate Limit | Abstracts | DOI | Citations |
|-----|--------------|-----------|-----------|-----------|-----|-----------|
| **SemanticScholar** | Optional | Yes | 1 req/sec (100+ with key) | ✓ | ✓ | ✓ |
| **OpenAlex** | No | Yes | 10 req/sec, 100k/day | Partial | ✓ | ✓ |
| **IEEE** | Yes | Limited | 10 req/sec, 200/day | ✓ | ✓ | ✓ |
| **Elsevier** | Yes | Limited | 6 req/sec | Partial | ✓ | ✓ |
| **Springer** | Yes | Limited | 1.5 req/sec | ✓ | ✓ | Partial |
| **HAL** | No | Yes | 10 req/sec | ✓ | Partial | No |
| **DBLP** | No | Yes | 10 req/sec | No | ✓ | No |
| **Arxiv** | No | Yes | 3 req/sec | ✓ | ✓ | No |
| **Istex** | No | Yes | 10 req/sec | ✓ | ✓ | No |
| **GoogleScholar** | No | Yes | 2 req/sec | ✓ | Rare | ✓ |

**Recommendation:** Start with free APIs (SemanticScholar, OpenAlex, HAL, DBLP, Arxiv) for testing. Add paid APIs as needed.

---

## Common Tasks

### Optimize Your Keywords

```bash
python src/optimize_keywords.py
```

Analyzes your config and suggests reductions:
- Removes redundant terms
- Estimates API call load
- Provides cost-saving recommendations

### Test a Single API

```bash
python "src/API tests/SemanticScholardAPI.py"
python "src/API tests/OpenAlexAPI.py"
# etc...
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint and auto-fix
uv run ruff check --fix .
```

### Resume Interrupted Collection

The collection system automatically saves state to `state_details.json`. To resume:

```bash
python src/run_collecte.py
# Automatically skips completed APIs and continues with remaining ones
```

### Push Existing Aggregated Data to Zotero

```bash
# Without citation enrichment:
python src/push_to_Zotero_collect.py

# Or first enrich with citations:
python src/citations/get_citations.py
python src/push_to_Zotero_collect.py
```

---

## Output Formats

### Aggregated CSV Schema

All papers are stored in unified CSV format:

```
title           | authors          | abstract                    | DOI      | URL | year | itemType | ...
Machine Learning| Alice, Bob      | Advanced techniques for... | 10.1234 | ... | 2024 | journalArticle | ...
```

**Key fields:**
- `title`, `authors`, `abstract`
- `DOI` (for citation lookups)
- `URL` (for duplicate detection)
- `year`, `itemType`, `publicationTitle`, `publisher`
- `volume`, `issue`, `pages`, `keywords`, `fieldsOfStudy`

### Citation Enriched Output

After running `citations/get_citations.py`:

```
... | citation_count | references_count |
... | 42            | 18              |
```

---

## Troubleshooting

### API Key Errors

**Error:** "Invalid API key for IEEE"

**Fix:** Check `src/api.config.yml` has correct keys. Comment out APIs you don't have keys for - the collection will continue with available APIs.

### Multiprocessing Issues

**Error:** "RuntimeError: attempt to start new process before current process finished"

**Fix:** Already fixed in this version. Make sure you have the latest code with `if __name__ == "__main__":` guard in `src/run_collecte.py`.

### Out of Memory During Aggregation

**Cause:** Large number of papers (100k+)

**Fix:** Process in chunks - edit `src/aggregate_collect.py` to process APIs separately.

### Zotero Push Fails

**Issue:** Some papers not appearing in Zotero

**Steps:**
1. Check Zotero API key is valid: `https://api.zotero.org/users/<user_id>/keys`
2. Verify collection name in config matches Zotero
3. Check logs for duplicate or format errors
4. Run `python src/Zotero/getZotero.py` to verify connection

---

## Recent Improvements

**Phase 1-6 Refactoring Complete** (See REFACTORING_PROGRESS.md for details):

✅ Fixed critical exception handling (no more bare `except:`)  
✅ Added timeouts to all API calls (prevents infinite hangs)  
✅ Centralized missing value handling (`MISSING_VALUE` constant)  
✅ Created reusable `ZoteroAPI` class (417 lines → 159 lines refactored)  
✅ Fixed multiprocessing on macOS/Windows (spawn mode compatible)  
✅ Added API key validation and progress tracking  
✅ Proper logging throughout (goodbye debug print statements)  

---

## How to Contribute

We welcome contributions! Ways to improve SciLEx:

1. **Add a new API collector** - Follow the pattern in `src/crawlers/collectors.py`
2. **Improve metadata extraction** - Enhance format converters in `src/crawlers/aggregate.py`
3. **Add new features** - Citation analysis, visualization, analytics tools
4. **Improve documentation** - Examples, tutorials, troubleshooting guides

See [CLAUDE.md](CLAUDE.md) for detailed technical architecture and contribution guidelines.

---

## Project Organization

- **ScriptBox Content:** API tests, collectors, Zotero scripts, enhancement tools
- **Issues:** Report bugs and suggest features via GitHub issues
- **Discussions:** Technical questions about implementation
- **Pull Requests:** Code contributions welcome with test coverage

---

## License

See LICENSE file.

---

## Citation

If you use SciLEx in your research, please cite:

```bibtex
@inproceedings{ringwald2024learning,
  title={Learning Pattern-Based Extractors from Natural Language and Knowledge Graphs},
  author={Ringwald, Celian},
  booktitle={38th AAAI Conference on Artificial Intelligence},
  pages={23411-23412},
  year={2024}
}
```

---

## Support

- **Questions?** Check [CLAUDE.md](CLAUDE.md) for technical details
- **Issues?** Review logs in `output/` directory and check troubleshooting section
- **Contributing?** See guidelines in [CLAUDE.md](CLAUDE.md)

---

**Last Updated:** 2025-01-29  
**Status:** Production Ready ✅
