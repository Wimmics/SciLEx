# Configuration Guide

This guide explains how to configure SciLEx for your research needs.

## Configuration Files

SciLEx uses two main configuration files:

1. **`scilex/scilex.config.yml`** - Search and collection settings
2. **`scilex/api.config.yml`** - API credentials and rate limits

## Basic Configuration

### Search Configuration (scilex.config.yml)

```yaml
# Keywords - Two modes available:
# Single group: Papers matching ANY keyword
keywords:
  - ["machine learning", "deep learning"]
  - []

# Dual groups: Papers matching keywords from BOTH groups
keywords:
  - ["knowledge graph", "ontology"]      # Group 1
  - ["large language model", "LLM"]      # Group 2

# Years to search
years: [2022, 2023, 2024]

# APIs to use (see API guide for options)
apis:
  - SemanticScholar
  - OpenAlex
  - Arxiv

# Fields to search in
fields: ["title", "abstract"]

# Collection settings
collect: true
collect_name: "my_collection"
output_dir: "output"
```

### API Configuration (api.config.yml)

```yaml
# Semantic Scholar (optional key improves rate limits)
semantic_scholar:
  api_key: "your-key-here"

# IEEE (required)
ieee:
  api_key: "your-ieee-key"

# Elsevier (required)
elsevier:
  api_key: "your-elsevier-key"
  inst_token: "optional-institutional-token"

# Springer (required)
springer:
  api_key: "your-springer-key"

# Zotero (for export)
zotero:
  api_key: "your-zotero-key"
  user_id: "your-user-id"
  collection_id: "target-collection"

# Rate limits (requests per second)
rate_limits:
  SemanticScholar: 1.0
  OpenAlex: 10.0
  IEEE: 10.0
  Arxiv: 3.0
```

## Keyword Configuration

### Single Group Mode (OR Logic)

Papers match if they contain ANY keyword:

```yaml
keywords:
  - ["neural network", "deep learning", "CNN", "RNN"]
  - []  # Empty second group
```

### Dual Group Mode (AND Logic)

Papers must contain at least one keyword from EACH group:

```yaml
keywords:
  - ["climate", "weather", "temperature"]     # Topic
  - ["prediction", "forecast", "model"]       # Method
```

## Filtering Configuration

### Basic Quality Filters

```yaml
quality_filters:
  # Filter by publication type
  enable_itemtype_filter: true
  allowed_item_types:
    - journalArticle
    - conferencePaper

  # Abstract quality
  validate_abstracts: true
  min_abstract_quality_score: 60
  filter_by_abstract_quality: true
```

### Citation Filtering

```yaml
# Enable citation fetching
aggregate_get_citations: true

quality_filters:
  # Filter by citations (time-aware)
  apply_citation_filter: true
  min_citations_per_year: 2
```

### Relevance Ranking

```yaml
quality_filters:
  # Rank and limit results
  apply_relevance_ranking: true
  max_papers: 500  # Keep top 500 papers

  # Scoring weights (must sum to 1.0)
  relevance_weights:
    keywords: 0.45
    quality: 0.25
    itemtype: 0.20
    citations: 0.10
```

## Common Configurations

### Quick Test

```yaml
keywords: [["test"], []]
years: [2024]
apis: ["OpenAlex"]
max_results_per_api: 10
```

### Comprehensive Search

```yaml
keywords:
  - ["artificial intelligence", "AI"]
  - []
years: [2020, 2021, 2022, 2023, 2024]
apis:
  - SemanticScholar
  - OpenAlex
  - IEEE
  - Arxiv
aggregate_get_citations: true
quality_filters:
  apply_relevance_ranking: true
  max_papers: 1000
```

### Focused Conference Papers

```yaml
keywords: [["neural networks"], []]
years: [2023, 2024]
apis: ["SemanticScholar", "DBLP"]
quality_filters:
  enable_itemtype_filter: true
  allowed_item_types:
    - conferencePaper
```

## API Selection

### APIs Without Keys

These APIs work without configuration:
- OpenAlex
- Arxiv
- DBLP
- HAL
- ~~GoogleScholar~~ (deprecated - unreliable, requires Tor proxy)

### APIs Requiring Keys

Must be configured in `api.config.yml`:
- SemanticScholar (optional but recommended)
- IEEE
- Elsevier
- Springer

## Environment Variables

Optional environment variables:

```bash
# Set log level
export LOG_LEVEL=INFO

# Disable colored output
export LOG_COLOR=false
```

## Tips

1. **Start Small**: Test with one year and one API
2. **Use Open APIs First**: No keys needed
3. **Add APIs Gradually**: Test each one separately
4. **Check Rate Limits**: Respect API quotas
5. **Save Working Configs**: Keep successful configurations for reuse

## Next Steps

- See [Quick Start](quick-start.md) for your first collection
- See [Advanced Filtering](../user-guides/advanced-filtering.md) for filtering options
- See [API Comparison](../reference/api-comparison.md) for API details