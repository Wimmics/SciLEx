# Quick Start Guide

Get your first paper collection running. This assumes you've [installed SciLEx](installation.md).

## Quick Start

### 1. Create Configuration

```bash
cat > scilex/test_collection.yml << 'EOF'
keywords:
  - ["machine learning"]
  - []

years: [2024]

apis:
  - OpenAlex
  - Arxiv

collect_name: "test"
EOF
```

### 2. Run Collection

```bash
scilex-collect --config scilex/test_collection.yml
```

You'll see progress like:
```
Progress: 1/4 (25%) collections completed
Progress: 2/4 (50%) collections completed
...
```

### 3. Aggregate Results

```bash
scilex-aggregate
```

Results saved to `output/{collect_name}/aggregated_results.csv`

### 4. View Results

```bash
# View first few papers
head output/test/aggregated_results.csv
```

Or open in spreadsheet software.

## Real Collection Example

For a proper research collection:

```yaml
# scilex/scilex.config.yml
keywords:
  - ["knowledge graph", "ontology"]      # Domain
  - ["large language model", "LLM"]      # Technology

years: [2022, 2023, 2024]

apis:
  - SemanticScholar
  - OpenAlex
  - Arxiv

quality_filters:
  aggregate_get_citations: true
  enable_itemtype_filter: true
  allowed_item_types:
    - journalArticle
    - conferencePaper
  apply_relevance_ranking: true
  max_papers: 500
```

Then run:
```bash
scilex-collect
scilex-aggregate
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