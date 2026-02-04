# Installation Guide

## Prerequisites

- Python 3.13+
- uv package manager (or pip)
- 4GB RAM minimum

## Installation

### 1. Install Dependencies

```bash
cd SciLEx
uv sync
```

Or with pip:
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp src/api.config.yml.example src/api.config.yml
nano src/api.config.yml
```

Add your API keys:

```yaml
# Semantic Scholar (optional but recommended)
semantic_scholar:
  api_key: "your-key-here"

# IEEE (required if using)
ieee:
  api_key: "your-key"

# Elsevier (required if using)
elsevier:
  api_key: "your-key"

# Springer (required if using)
springer:
  api_key: "your-key"

# Zotero (for export)
zotero:
  api_key: "your-key"
  user_id: "your-id"
  collection_id: "collection-id"
```

Get API keys from:
- [Semantic Scholar](https://www.semanticscholar.org/product/api)
- [IEEE](https://developer.ieee.org/getting_started)
- [Elsevier](https://dev.elsevier.com/)
- [Springer](https://dev.springernature.com/)

### 3. Configure Search

```bash
cp src/scilex.config.yml.example src/scilex.config.yml
nano src/scilex.config.yml
```

Basic configuration:
```yaml
keywords:
  - ["machine learning"]
  - []

years: [2023, 2024]

apis:
  - OpenAlex
  - Arxiv

fields: ["title", "abstract"]
```

## Verify Installation

```bash
# Test that dependencies are installed
python -c "import pandas, requests, yaml; print('OK')"

# Run a test collection
python src/run_collection.py
```

## Common Issues

### Python Version Error
Install Python 3.13+ from [python.org](https://www.python.org)

### Module Not Found
```bash
uv sync
# or
pip install -r requirements.txt
```

### API Key Invalid
- Check for typos in `api.config.yml`
- Verify key is active on API provider's dashboard

## Next Steps

- [Quick Start](quick-start.md) - Run your first collection
- [Configuration](configuration.md) - Detailed config options
- [Troubleshooting](troubleshooting.md) - More solutions