![Scilex](img/projectLogoScilex.png)

# 🚀 SciLEx Tutorial

## 0. 🔑 Obtain the API Keys You Need

\:heavy\_plus\_sign: [Create a Zotero API key](https://www.zotero.org/support/dev/web_api/v3/start)
\:heavy\_plus\_sign: Create accounts for the following APIs:

* [Semantic Scholar](https://www.semanticscholar.org/product/api/tutorial) (optional – allows a higher rate limit ⬆️, but takes time ⏳)
* [Springer](https://dev.springernature.com/) (mandatory if selected as a source 📚)
* [IEEE](https://developer.ieee.org/) (mandatory if selected as a source ⚡)
* [Elsevier](https://dev.elsevier.com/) (mandatory if selected as a source 🧪)

---

## 1. 🛠 Clone the Repository and Install Requirements

**Option 1: Using uv (recommended - fast):**
```bash
git clone https://github.com/datalogism/SciLEx.git
cd SciLEx
uv sync
```

**Option 2: Using pip (traditional):**
```bash
git clone https://github.com/datalogism/SciLEx.git
cd SciLEx
pip install -r requirements.txt
```

---

## 2. 📝 Create and Configure Your Files

1. **Copy the API configuration template:**

   ```bash
   cp src/api.config.yml.example src/api.config.yml
   ```

2. **Edit `src/api.config.yml` with your API credentials:**

   * **Zotero API Key**: [Create here](https://www.zotero.org/settings/keys)
   * **IEEE API Key**: [Register at IEEE Developer Portal](https://developer.ieee.org/)
   * **Elsevier API Key**: [Register at Elsevier Developer Portal](https://dev.elsevier.com/)
   * **Springer API Key**: [Register at Springer Nature Developer Portal](https://dev.springernature.com/)
   * **Semantic Scholar API Key**: Optional, [register here](https://www.semanticscholar.org/product/api/tutorial)

3. **Update your main configuration in [`src/scilex.config.yml`](src/scilex.config.yml):**

```yaml
aggregate_txt_filter: true         # Filter articles based on the given keywords 🔍
aggregate_get_citations: true      # Collect all citations during aggregation 📑
aggregate_file: 'aggregated_data.csv'  # Aggregated results will be saved here 💾
apis:
  - DBLP
  - Arxiv
  - OpenAlex
  - SemanticScholar
collect: true                       # Flag to enable or disable collection ✅
collect_name: graphrag              # Name for this collection 🏷
email: YOUR_MAIL                    # Email used for API requests 📧
fields:                             # Fields to search for keywords 🧩
  - title
  - abstract
keywords:                            # Two keyword groups for collection 💡
  - ["RAG", "LLM", "agent"]         # Group 1: Any of these keywords
  - ["Knowledge Graph"]             # Group 2: Must also match this (dual mode)
                                     # OR: Set second group to [] for single mode
max_articles_per_query: 1000        # Articles per query (-1 = unlimited, 1000 recommended)
output_dir: output
years:
  - 2023
  - 2024
  - 2025

# Semantic Scholar API mode (only if using SemanticScholar)
semantic_scholar_mode: bulk      # "regular" (default, works with standard API keys)
                                    # "bulk" (requires higher-tier access, 10x faster)

# Optional: Quality filters (see scilex.config.yml.example for details)
quality_filters:
  # ItemType Filtering (Whitelist) - NEW!
  enable_itemtype_filter: false          # Enable to only keep specific publication types
  allowed_item_types:                    # Only these types will be kept (others removed)
    - journalArticle                     # Example: Focus on peer-reviewed work only
    - conferencePaper

  enable_itemtype_bypass: true           # Fast-track trusted publications (~50% speedup)
  bypass_item_types: [journalArticle, conferencePaper]
  apply_citation_filter: true            # Time-aware citation filtering
  apply_relevance_ranking: true          # Composite scoring
  max_papers: 1000                       # Keep top N most relevant (null = keep all)
```

---

## 3. ▶️ Run Your Collection

Once the previous steps are complete, run the collection from the library source:

```bash
python src/run_collecte.py
```

You'll see real-time progress bars for each API. Expected time: ~5-15 minutes per API.

**Optional:** Control logging verbosity:
```bash
LOG_LEVEL=INFO python src/run_collecte.py   # Detailed logs
LOG_LEVEL=DEBUG python src/run_collecte.py  # Full debugging
```

---

## 4. 📦 Aggregate the Collection

After collecting all papers, create the final aggregated file:

```bash
python src/aggregate_collect.py
```

**Common flags:**
```bash
--skip-citations        # Skip citation fetching (faster)
--workers N             # Parallel workers for citations (default: 3)
--profile               # Show performance statistics
--resume                # Resume from checkpoint if interrupted
--no-cache              # Disable citation cache (slower, not recommended)
```

---

## 5. 📂 View the Results

Results are saved in a dedicated directory inside `./output_dir`. Each directory is named according to the `collect_name` in your configuration:

```
output/collect_name_YYYYMMDD_HHMMSS/
├── SemanticScholar/      # Individual API results 📚
├── OpenAlex/
├── DBLP/
│   ├── 0/                # Query ID
│   │   ├── page_1        # Result pages (JSON)
│   │   └── page_2
├── config_used.yml       # Local copy of the configuration 📝
├── aggregated_data.csv   # Aggregated results 💾
└── citation_cache.db     # Citation cache for faster re-runs
```

**CSV Output:** Contains `title`, `authors`, `abstract`, `DOI`, `URL`, `year`, `itemType`, and enrichment fields like `citation_count`, `quality_score`, `relevance_score`.

---

## 6. 🔄 Push Results to Zotero

If you have your Zotero API key, you can push the `aggregated_data.csv` content to a Zotero library. Note that free Zotero accounts have storage limits, so manual filtering is recommended.

```bash
python src/push_to_zotero.py
```

This will create a new collection based on the `collect_name` defined in your configuration 🏁.

**Performance:** 500 papers upload in ~10-15 seconds (optimized with bulk API).

---

## 🐛 Troubleshooting

**Empty results?** Check keywords aren't too specific, try single group mode (`keywords: [["term1", "term2"], []]`)

**Rate limit errors (429)?** Reduce rate limits in `api.config.yml` (e.g., `DBLP: 1.0`)

