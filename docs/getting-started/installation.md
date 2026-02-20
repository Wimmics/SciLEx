# Installation Guide

## Prerequisites

- Python >=3.10
- uv package manager (recommended) or pip
- 4GB RAM minimum

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/SciLEx.git
cd SciLEx
```

### 2. Install Dependencies

Choose **one** of the two methods below.

#### Option A: uv (recommended)

```bash
uv sync                        # Install deps + project into .venv
```

Commands are run via `uv run` (no venv activation needed):

```bash
uv run scilex-collect           # Example: run collection
```

For developers (adds pytest, ruff, coverage):

```bash
uv sync --dev
```

#### Option B: pip

```bash
python -m venv .venv            # Create virtual environment
source .venv/bin/activate       # Activate it (macOS/Linux)
# .venv\Scripts\activate        # Windows

pip install -e .                # Install SciLEx
```

After activation, commands are available directly:

```bash
scilex-collect                  # Example: run collection
```

For developers (adds pytest, ruff, coverage):

```bash
pip install -e ".[dev]"
```

### 3. Configure API Keys

```bash
cp scilex/api.config.yml.example scilex/api.config.yml
```

Edit `scilex/api.config.yml` and add your API keys:

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

### 4. Configure Search

```bash
cp scilex/scilex.config.yml.example scilex/scilex.config.yml
```

Edit `scilex/scilex.config.yml` with a minimal search:

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
# With uv
uv run python -c "import pandas, requests, yaml; print('OK')"
uv run scilex-collect

# With pip (venv must be activated)
python -c "import pandas, requests, yaml; print('OK')"
scilex-collect
```

## Common Issues

### Python Version Error
Install Python 3.10+ from [python.org](https://www.python.org)

### Command Not Found

**uv users:** Always prefix commands with `uv run`:
```bash
uv run scilex-collect
```

**pip users:** Make sure your virtual environment is activated:
```bash
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows
scilex-collect
```

### Module Not Found

Reinstall the project:
```bash
# uv
uv sync

# pip (with venv activated)
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
