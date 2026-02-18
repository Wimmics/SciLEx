# Configuration Guide

This guide explains how to configure SciLEx for your research needs.

## Configuration Files

SciLEx uses up to three configuration files:

1. **`scilex/scilex.config.yml`** - Search and collection settings (required)
2. **`scilex/api.config.yml`** - API credentials and rate limits (required)
3. **`scilex/scilex.advanced.yml`** - Advanced overrides (optional, for power users)

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

# Optional: Bonus keywords boost relevance without filtering
bonus_keywords: ["temporal reasoning", "multi-hop"]

# Years to search
years: [2023, 2024, 2025]

# APIs to use (see API guide for options)
apis:
  - SemanticScholar
  - OpenAlex
  - Arxiv

# Collection settings
collect_name: "my_collection"
semantic_scholar_mode: "regular"  # or "bulk" (requires special access)
```

### API Configuration (api.config.yml)

YAML keys must use PascalCase to match API names:

```yaml
# Semantic Scholar (optional key improves rate limits)
SemanticScholar:
  api_key: "your-key-here"

# IEEE (required)
IEEE:
  api_key: "your-ieee-key"

# Elsevier (required)
Elsevier:
  api_key: "your-elsevier-key"
  inst_token: null  # Optional institutional token

# Springer (required)
Springer:
  api_key: "your-springer-key"

# PubMed (optional - 3 req/sec free, 10 req/sec with key)
PubMed:
  api_key: "your-ncbi-key"

# OpenAlex (optional - 100 req/day free, 100k/day with key)
OpenAlex:
  api_key: "your-openalex-key"

# Zotero (for export)
Zotero:
  api_key: "your-zotero-key"
  user_id: "your-user-id"
  user_mode: "user"  # or "group"
```

Rate limits use a dual-value system (without_key / with_key) and are auto-selected
based on whether an API key is configured. Override only if needed:

```yaml
# Optional rate limit overrides (requests per second)
rate_limits:
  SemanticScholar: 1.0
  OpenAlex: 10.0
  Arxiv: 0.33
  PubMed: 10.0  # With key (3.0 without)
```

### Advanced Configuration (scilex.advanced.yml)

For power users. Copy `scilex/scilex.advanced.yml.example` and uncomment settings to override.
Covers: custom relevance weights, itemtype bypass, abstract quality validation, open-access
filtering, max_articles_per_query.

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

### Bonus Keywords (Relevance Boost)

Boost relevance scores without filtering. Papers matching bonus keywords score higher
but are not excluded if they don't match:

```yaml
bonus_keywords:
  - "temporal reasoning"
  - "multi-hop"
  - "context windows"
```

Bonus keyword matches are weighted at 0.5x compared to mandatory keywords.

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
quality_filters:
  # Citation fetching and filtering
  aggregate_get_citations: true
  apply_citation_filter: true
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
quality_filters:
  max_papers: 10
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
quality_filters:
  aggregate_get_citations: true
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
- OpenAlex (key optional but recommended for higher quota)
- Arxiv
- DBLP
- HAL
- PubMed (key optional but recommended for higher rate)
- Istex

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
