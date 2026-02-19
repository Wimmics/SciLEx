# Quick Start Guide

Get your first paper collection running. This assumes you've [installed SciLEx](installation.md).

## Quick Start

### 1. Create Configuration

```bash
# Copy example configs
cp scilex/api.config.yml.example scilex/api.config.yml
cp scilex/scilex.config.yml.example scilex/scilex.config.yml
```

Edit `scilex/scilex.config.yml` with a minimal search:

```yaml
keywords:
  - ["machine learning"]
  - []

years: [2024]

apis:
  - OpenAlex
  - Arxiv

collect_name: "test"
```

### 2. Run Collection

```bash
# With uv (no activation needed)
uv run scilex-collect

# With pip (venv must be activated)
scilex-collect
```

You'll see progress like:
```
Progress: 1/4 (25%) collections completed
Progress: 2/4 (50%) collections completed
...
```

### 3. Aggregate Results

```bash
# With uv
uv run scilex-aggregate

# With pip
scilex-aggregate
```

Results saved to `output/{collect_name}/aggregated_results.csv`

### 4. Enrich with HuggingFace (optional)

Adds ML metadata (tags, GitHub repos, HuggingFace URLs) to your papers:

```bash
# With uv
uv run scilex-enrich

# With pip
scilex-enrich
```

This updates the CSV in-place. Use `--dry-run --limit 10` to preview matches first.

### 5. Export Results

Choose **one** output format:

**Push to Zotero** (requires Zotero API key in `api.config.yml`):

```bash
# With uv
uv run scilex-push-zotero

# With pip
scilex-push-zotero
```

**Export to BibTeX** (for LaTeX, Overleaf, JabRef):

```bash
# With uv
uv run scilex-export-bibtex

# With pip
scilex-export-bibtex
```

Output: `output/{collect_name}/aggregated_results.bib`

### 6. View Raw CSV

You can also inspect the aggregated CSV directly:

```bash
head output/test/aggregated_results.csv
```

Or open in spreadsheet software.

## Real Collection Example

For a proper research collection, edit `scilex/scilex.config.yml`:

```yaml
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
# With uv
uv run scilex-collect
uv run scilex-aggregate
uv run scilex-enrich              # Optional: add HuggingFace metadata
uv run scilex-push-zotero         # Export to Zotero
# or: uv run scilex-export-bibtex  # Export to BibTeX

# With pip (venv activated)
scilex-collect
scilex-aggregate
scilex-enrich                     # Optional: add HuggingFace metadata
scilex-push-zotero                # Export to Zotero
# or: scilex-export-bibtex        # Export to BibTeX
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
