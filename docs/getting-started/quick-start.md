# Quick Start Guide

Get your first paper collection running. This assumes you've [installed SciLEx](installation.md).

## Quick Start

### 1. Create Configuration

Create a `test_collection.yml` file at the project root:

```yaml
keywords:
  - ["machine learning"]
  - []

years: [2024]

apis:
  - OpenAlex
  - Arxiv

fields: ["title", "abstract"]

collect: true
collect_name: "test"
max_results_per_api: 50
```

### 2. Run Collection

```bash
uv run python src/run_collecte.py
```

You'll see progress like:
```
Progress: 1/4 (25%) collections completed
Progress: 2/4 (50%) collections completed
...
```

### 3. Aggregate Results

```bash
uv run python src/aggregate_collect.py
```

Results saved to `output/collect_*/aggregated_data.csv`

### 4. View Results

```bash
# View first few lines
head output/collect_*/aggregated_data.csv
```

Or open in spreadsheet software.

## Real Collection Example

For a proper research collection, edit `src/scilex.config.yml`:

```yaml
keywords:
  - ["knowledge graph", "ontology"]      # Domain
  - ["large language model", "LLM"]      # Technology

years: [2022, 2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex
  - Arxiv

fields: ["title", "abstract"]

aggregate_get_citations: true

quality_filters:
  enable_itemtype_filter: true
  allowed_item_types:
    - journalArticle
    - conferencePaper
  apply_relevance_ranking: true
  max_papers: 500
```

Then run:
```bash
uv run python src/run_collecte.py
uv run python src/aggregate_collect.py
```

## CSV Output Columns

- `title` - Paper title
- `authors` - Author list
- `year` - Publication year
- `DOI` - Digital Object Identifier
- `abstract` - Full abstract
- `itemType` - Publication type
- `citation_count` - Citations (if enabled)
- `quality_score` - Metadata completeness (0-100)
- `relevance_score` - Relevance (0-10)

## Next Steps

- [Configuration Guide](configuration.md) - All config options
- [Basic Workflow](../user-guides/basic-workflow.md) - Detailed workflow
- [Advanced Filtering](../user-guides/advanced-filtering.md) - Filtering options
