# SciLEx - Installation & Usage Guide

## Installation

### From the GitHub repository

```bash
pip install git+https://github.com/Wimmics/SciLEx.git
```

### From a local clone

```bash
git clone https://github.com/Wimmics/SciLEx.git
cd SciLEx
pip install .
```

### With development dependencies

```bash
pip install ".[dev]"
```

## Configuration

Before running SciLEx, you need two configuration files in your working directory:

**1. `scilex.config.yml`** - Main configuration (search parameters):

```yaml
collect: true
collect_name: my_review
output_dir: output
apis:
  - DBLP
  - Arxiv
  - OpenAlex
  - SemanticScholar
keywords:
  - ["keyword1", "keyword2"]
  - ["keyword3", "keyword4"]
fields:
  - title
  - abstract
years:
  - 2023
  - 2024
  - 2025
aggregate_txt_filter: true
aggregate_get_citations: true
aggregate_file: '/FileAggreg.csv'
```

**2. `api.config.yml`** - API keys (copy from `api.config.yml.example`):

```yaml
zotero:
    api_key: "YOUR_ZOTERO_API_KEY"
    user_mode: "user"
sem_scholar:
    api_key: "YOUR_SEMANTIC_SCHOLAR_API_KEY"
springer:
    api_key: "YOUR_SPRINGER_API_KEY"
ieee:
    api_key: "YOUR_IEEE_API_KEY"
elsevier:
    api_key: "YOUR_ELSEVIER_API_KEY"
```

> Not all API keys are required. DBLP, Arxiv, OpenAlex and HAL work without keys.

## Usage Example

### Running a literature collection

```bash
python -m scilex.run_collecte
```

This will crawl the configured APIs with your keywords/years and save raw results to the `output/` directory.

### Aggregating and deduplicating results

```bash
python -m scilex.aggregate_collect
```

This reads the collected data, deduplicates entries, optionally fetches citation counts, and produces a consolidated `FileAggreg.csv`.

### Using SciLEx modules in your own scripts

```python
from scilex.crawlers.collector_collection import CollectCollection
from scilex.crawlers.utils import load_all_configs

# Load your config files
configs = load_all_configs({
    "main_config": "scilex.config.yml",
    "api_config": "api.config.yml",
})

# Run a collection
collection = CollectCollection(configs["main_config"], configs["api_config"])
collection.create_collects_jobs()
```

```python
from scilex.citations import citations_tools as cit_tools

# Get citations for a DOI
citations = cit_tools.getRefandCitFormatted("10.1609/aaai.v38i21.30406")
counts = cit_tools.countCitations(citations)
print(f"Cited by: {counts['nb_citations']}, References: {counts['nb_cited']}")
```

## Developer Guide

### Setting up a development environment

```bash
git clone https://github.com/Wimmics/SciLEx.git
cd SciLEx
pip install -e ".[dev]"
```

The `-e` (editable) flag installs the package in development mode: any change you make in `src/scilex/` is immediately reflected without reinstalling.

### Project structure

```
SciLEx/
├── pyproject.toml          # Package metadata & dependencies
├── src/
│   └── scilex/
│       ├── __init__.py     # Package version
│       ├── crawlers/       # API collectors & aggregation
│       ├── citations/      # Citation network tools
│       ├── Zotero/         # Zotero integration
│       ├── PWC/            # PaperWithCode integration
│       ├── doi/            # DOI resolution
│       ├── orcid/          # ORCID author data
│       ├── tagging/        # Tagging utilities
│       └── text_analysis/  # Text mining tools
├── tests/
└── scilex.config.yml       # Main config (your working copy)
```

### Running tests

```bash
pytest
```

### Linting

```bash
ruff check src/
ruff format src/
```

### After modifying the code

If installed in editable mode (`-e`), changes are picked up automatically. No rebuild needed.

If installed normally (without `-e`), reinstall after changes:

```bash
pip install .
```

### Bumping the version

Update the version in **both** files:

- `pyproject.toml` &rarr; `version = "X.Y.Z"`
- `src/scilex/__init__.py` &rarr; `__version__ = "X.Y.Z"`

### Building a distributable package

```bash
pip install build
python -m build
```

This produces `dist/scilex-X.Y.Z.tar.gz` and `dist/scilex-X.Y.Z-py3-none-any.whl` that can be shared or uploaded to PyPI.
