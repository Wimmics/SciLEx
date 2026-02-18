# Basic Workflow Guide

Standard workflow for collecting, aggregating, enriching, and exporting papers.

## Workflow Steps

1. **Collection** - Query APIs and download metadata
2. **Aggregation** - Deduplicate and filter
3. **Enrichment** - Add HuggingFace ML metadata (optional)
4. **Export** - Push to Zotero or export to BibTeX

## Step 1: Collection

### Configure Search

Edit `scilex/scilex.config.yml`:

```yaml
keywords:
  - ["machine learning"]
  - []

years: [2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex
```

### Run Collection

```bash
scilex-collect
```

Results saved to `output/{collect_name}/` (name from config).

Output structure:
```
output/my_research_project/
├── config_used.yml
├── SemanticScholar/
│   ├── 0/              # Query 0: keyword[0] + year[0]
│   │   ├── page_1
│   │   └── page_2
├── OpenAlex/
```

### Idempotent Behavior

Re-running collection skips already completed queries. Safe to re-run without wasting API quotas.

## Step 2: Aggregation

### Basic Aggregation

```bash
scilex-aggregate
```

Process:
1. Loads JSON files
2. Converts to unified format
3. Deduplicates (DOI, URL, fuzzy title)
4. Applies keyword filtering
5. Scores quality
6. Saves to CSV

### With Citations

Enable in config:
```yaml
quality_filters:
  aggregate_get_citations: true
```

Then run aggregation. Citations fetched from cache → Semantic Scholar → OpenCitations.

### Output

CSV saved to `output/{collect_name}/aggregated_results.csv`

Columns:
- `title`, `authors`, `year`, `DOI`, `abstract`
- `itemType` - Publication type
- `publicationTitle` - Journal/conference
- `citation_count` - Citations (if enabled)
- `quality_score` - Metadata completeness (0-100)
- `relevance_score` - Relevance (0-10)

## Step 3: Enrichment (Optional)

Add HuggingFace ML metadata to papers before export:

```bash
# Full enrichment (updates CSV in-place)
scilex-enrich

# Preview matches first
scilex-enrich --dry-run --limit 10
```

Adds columns: `tags` (ML tags), `hf_url` (HF paper URL), `github_repo` (GitHub link).

## Step 4: Export

### Option A: Push to Zotero

Configure `scilex/api.config.yml`:

```yaml
Zotero:
  api_key: "your-key"
  user_id: "your-id"
  user_mode: "user"
```

```bash
scilex-push-zotero
```

Papers uploaded in batches. Duplicates skipped by URL.

### Option B: Export to BibTeX

```bash
scilex-export-bibtex
```

Generates `aggregated_results.bib` in the collection directory.

## Filtering Pipeline

Aggregation applies filters:

1. **ItemType** - Keep allowed publication types
2. **Keywords** - Match search terms
3. **Deduplication** - Remove duplicates
4. **Quality** - Remove low-quality metadata
5. **Citations** - Time-aware thresholds
6. **Relevance** - Score and limit to top N

Check logs to see papers filtered at each step.

## Complete Example

```yaml
# scilex/scilex.config.yml
keywords:
  - ["knowledge graph"]
  - ["LLM", "large language model"]

years: [2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex

quality_filters:
  aggregate_get_citations: true
  enable_itemtype_filter: true
  allowed_item_types:
    - journalArticle
    - conferencePaper
  apply_relevance_ranking: true
  max_papers: 300
```

Run:
```bash
scilex-collect
scilex-aggregate
scilex-enrich          # Optional: add HF metadata
scilex-push-zotero     # Or: scilex-export-bibtex
```

## Analyze Results

```python
import pandas as pd

df = pd.read_csv('output/my_research_project/aggregated_results.csv', delimiter=';')

print(f"Total papers: {len(df)}")
print(f"\nPapers by year:")
print(df['year'].value_counts().sort_index())
print(f"\nTop cited:")
print(df.nlargest(10, 'nb_citation')[['title', 'nb_citation']])
```

## Log Levels

```bash
# Default (clean output)
scilex-collect

# Detailed progress
LOG_LEVEL=INFO scilex-collect

# Full debugging
LOG_LEVEL=DEBUG scilex-collect
```

## Next Steps

- [Advanced Filtering](advanced-filtering.md) - Filtering options
- [Configuration](../getting-started/configuration.md) - All config parameters
- [API Comparison](../reference/api-comparison.md) - API details
