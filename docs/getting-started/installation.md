# Installation Guide

## Prerequisites

- Python >=3.10
- uv package manager (recommended) or pip
- 4GB RAM minimum

## Installation

### 1. Install Dependencies

```bash
cd SciLEx

# Recommended: install with uv
uv sync

# Or with pip
pip install -e .

# For development (includes pytest, ruff, coverage)
pip install -e ".[dev]"
```

### 2. Configure API Keys

```bash
cp scilex/api.config.yml.example scilex/api.config.yml
nano scilex/api.config.yml
```

Add your API keys (PascalCase names required):

```yaml
# Semantic Scholar (optional but recommended)
SemanticScholar:
  api_key: "your-key-here"

# IEEE (required if using)
IEEE:
  api_key: "your-key"

# Elsevier (required if using)
Elsevier:
  api_key: "your-key"
  inst_token: null  # Optional institutional token

# Springer (required if using)
Springer:
  api_key: "your-key"

# PubMed (optional - boosts rate from 3 to 10 req/sec)
PubMed:
  api_key: "your-ncbi-key"

# OpenAlex (optional - boosts daily quota from 100 to 100k)
OpenAlex:
  api_key: "your-openalex-key"

# Zotero (for export)
Zotero:
  api_key: "your-key"
  user_id: "your-id"
  user_mode: "user"  # or "group"
```

Get API keys from:
- [Semantic Scholar](https://www.semanticscholar.org/product/api)
- [IEEE](https://developer.ieee.org/getting_started)
- [Elsevier](https://dev.elsevier.com/)
- [Springer](https://dev.springernature.com/)
- [PubMed / NCBI](https://www.ncbi.nlm.nih.gov/account/settings/)
- [OpenAlex](https://openalex.org/settings/api)

### 3. Configure Search

```bash
cp scilex/scilex.config.yml.example scilex/scilex.config.yml
nano scilex/scilex.config.yml
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
```

## Verify Installation

```bash
# Test that dependencies are installed
python -c "import pandas, requests, yaml; print('OK')"

# Run a test collection
scilex-collect
```

## Common Issues

### Python Version Error
Install Python 3.10+ from [python.org](https://www.python.org)

### Module Not Found
```bash
uv sync
# or
pip install -e .
```

### API Key Invalid
- Check for typos in `api.config.yml`
- Ensure YAML keys use PascalCase (e.g., `SemanticScholar:`, not `semantic_scholar:`)
- Verify key is active on API provider's dashboard

## Next Steps

- [Quick Start](quick-start.md) - Run your first collection
- [Configuration](configuration.md) - Detailed config options
- [Troubleshooting](troubleshooting.md) - More solutions
