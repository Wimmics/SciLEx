# Basic Workflow Guide

Standard workflow for collecting and aggregating papers.

## Workflow Steps

1. **Collection** - Query APIs and download metadata
2. **Aggregation** - Deduplicate and filter
3. **Export** - Push to Zotero (optional)

## Step 1: Collection

### Configure Search

Edit `src/scilex.config.yml`:

```yaml
keywords:
  - ["machine learning"]
  - []

years: [2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex

fields: ["title", "abstract"]
```

### Run Collection

```bash
uv run python src/run_collecte.py
```

Results saved to `output/collect_YYYYMMDD_HHMMSS/`

Output structure:
```
output/collect_20241113_143022/
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
uv run python src/aggregate_collect.py
```

Process:
1. Loads JSON files
2. Converts to unified format
3. Deduplicates (DOI, URL, fuzzy title)
4. Applies keyword filtering
5. Scores quality
6. Saves to CSV

### With Citations

Enable in `src/scilex.config.yml`:
```yaml
aggregate_get_citations: true
```

Then run aggregation. Citations are fetched from cache → Semantic Scholar → OpenCitations.

### Output

CSV saved to `output/collect_*/aggregated_data.csv`

Columns:
- `title`, `authors`, `year`, `DOI`, `abstract`
- `itemType` - Publication type
- `publicationTitle` - Journal/conference
- `citation_count` - Citations (if enabled)
- `quality_score` - Metadata completeness (0-100)
- `relevance_score` - Relevance (0-10)

## Step 3: Export to Zotero

### Configure

Edit `scilex/api.config.yml`:

```yaml
zotero:
  api_key: "your-key"
  user_mode: "user"  # or "group"
```

### Run Export

```bash
uv run python src/push_to_Zotero_collect.py
```

Papers uploaded in batches. Duplicates skipped by URL.

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
# src/scilex.config.yml
keywords:
  - ["knowledge graph"]
  - ["LLM", "large language model"]

years: [2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex

aggregate_get_citations: true

quality_filters:
  enable_itemtype_filter: true
  allowed_item_types:
    - journalArticle
    - conferencePaper
  apply_relevance_ranking: true
  max_papers: 300
```

Run:
```bash
uv run python src/run_collecte.py
uv run python src/aggregate_collect.py
uv run python src/push_to_Zotero_collect.py
```

## Analyze Results

```python
import pandas as pd

df = pd.read_csv('output/collect_*/aggregated_data.csv', delimiter=';')

print(f"Total papers: {len(df)}")
print(f"\nPapers by year:")
print(df['year'].value_counts().sort_index())
print(f"\nTop cited:")
print(df.nlargest(10, 'nb_citation')[['title', 'nb_citation']])
```

## Log Levels

```bash
# Default (clean output)
uv run python src/run_collecte.py

# Detailed progress
LOG_LEVEL=INFO uv run python src/run_collecte.py

# Full debugging
LOG_LEVEL=DEBUG uv run python src/run_collecte.py
```

## Next Steps

- [Advanced Filtering](advanced-filtering.md) - Filtering options
- [Configuration](../getting-started/configuration.md) - All config parameters
- [API Comparison](../reference/api-comparison.md) - API details
