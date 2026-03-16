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
cp src/api.config.yml.example scilex/api.config.yml
nano scilex/api.config.yml
```

Add your API keys. Note that key names use snake_case:

```yaml
# Semantic Scholar (optional but recommended for higher rate limits)
sem_scholar:
  api_key: "your-key-here"

# IEEE (required if using IEEE Xplore)
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
  user_mode: "user"  # or "group" for group libraries
```

Get API keys from:
- [Semantic Scholar](https://www.semanticscholar.org/product/api)
- [IEEE](https://developer.ieee.org/getting_started)
- [Elsevier](https://dev.elsevier.com/)
- [Springer](https://dev.springernature.com/)

The following APIs do **not** require a key: OpenAlex, arXiv, DBLP, HAL, ISTEX, OpenAIRE, ORKG.

### 3. Configure Search

Edit `src/scilex.config.yml` with your search parameters:

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
uv run python -c "import pandas, requests, yaml; print('OK')"

# Run a test collection
uv run python src/run_collecte.py
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
- Check for typos in `scilex/api.config.yml`
- Verify the key name matches exactly (e.g., `sem_scholar` not `semantic_scholar`)
- Verify the key is active on the API provider's dashboard

## Next Steps

- [Quick Start](quick-start.md) - Run your first collection
- [Configuration](configuration.md) - Detailed config options
- [Troubleshooting](troubleshooting.md) - More solutions
