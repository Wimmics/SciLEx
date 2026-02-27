# Python Scripting Guide

Use SciLEx as a Python library to integrate paper collection into your own scripts and workflows.

## Setup

All SciLEx modules rely on YAML config files. Load them using `load_all_configs()`:

```python
from scilex.crawlers.utils import load_all_configs

config_files = {
    "main_config": "scilex.config.yml",
    "api_config": "api.config.yml",
}
configs = load_all_configs(config_files)
main_config = configs["main_config"]
api_config = configs["api_config"]
```

Or build configs entirely in Python (no YAML files needed):

```python
main_config = {
    "keywords": [["machine learning", "deep learning"], ["healthcare"]],
    "years": [2024, 2025],
    "apis": ["SemanticScholar", "OpenAlex"],
    "output_dir": "output",
    "collect_name": "collect_20250101_120000",
    "collect": True,
    "aggregate_get_citations": False,
    "aggregate_file": "aggregated_results.csv",
}

api_config = {
    "SemanticScholar": {"api_key": "your-key-here"},
    "OpenAlex": {},
}
```

## Collect Papers

Run API collection programmatically using `CollectCollection`:

```python
import os
import yaml
from scilex.crawlers.collector_collection import CollectCollection

# Ensure output directory exists
output_dir = main_config.get("output_dir", "output")
if not os.path.isdir(output_dir):
    os.makedirs(output_dir)
    # Save config snapshot (required for aggregation)
    with open(os.path.join(output_dir, "config_used.yml"), "w") as f:
        yaml.dump(main_config, f)

# Run collection
collector = CollectCollection(main_config, api_config)
collector.create_collects_jobs()
```

## Aggregate and Filter

The aggregation module uses `argparse` and reads config at import time. Invoke it via `sys.argv`:

```python
import sys

# Set arguments before importing
sys.argv = ["aggregate", "--skip-citations", "--workers", "3"]

from scilex.aggregate_collect import main as aggregate_main

aggregate_main()
```

Then read the results:

```python
import pandas as pd

csv_path = "output/collect_20250101_120000/aggregated_results.csv"
df = pd.read_csv(csv_path, delimiter=";")

print(f"Total papers: {len(df)}")
print(f"Papers by year:\n{df['year'].value_counts().sort_index()}")
print(f"\nTop 10 cited:")
print(df.nlargest(10, "nb_citation")[["title", "nb_citation"]])
```

## Enrich with HuggingFace

Add ML metadata (tags, GitHub repos) to your aggregated CSV:

```python
import sys

sys.argv = ["enrich", "--limit", "50"]  # Process first 50 papers

from scilex.enrich_with_hf import main as enrich_main

enrich_main()
```

For a dry run (preview matches without modifying the CSV):

```python
import sys

sys.argv = ["enrich", "--dry-run", "--limit", "10"]

from scilex.enrich_with_hf import main as enrich_main

enrich_main()
```

## Export to BibTeX

### High-level export

```python
from scilex.export_to_bibtex import main as bibtex_main

bibtex_main()
# Creates: output/{collect_name}/aggregated_results.bib
```

### Granular control with `format_bibtex_entry()`

Generate BibTeX for individual papers:

```python
import pandas as pd
from scilex.export_to_bibtex import (
    format_bibtex_entry,
    generate_citation_key,
    load_aggregated_data,
    load_config,
)

config = load_config()
data = load_aggregated_data(config)

used_keys = set()
entries = []

for row in data.itertuples(index=False):
    doi = getattr(row, "DOI", None)
    key = generate_citation_key(doi, row, used_keys)
    entry = format_bibtex_entry(row, key)
    entries.append(entry)

# Write to custom output path
with open("my_papers.bib", "w") as f:
    f.write("\n\n".join(entries))

print(f"Exported {len(entries)} entries")
```

## Push to Zotero

### High-level push

```python
from scilex.push_to_zotero import main as zotero_main

zotero_main()
```

### Direct Zotero API usage

For fine-grained control over Zotero operations:

```python
from scilex.Zotero.zotero_api import ZoteroAPI, prepare_zotero_item
from scilex.push_to_zotero import load_aggregated_data, prefetch_templates

# Initialize client
zotero = ZoteroAPI(
    user_id="your-user-id",
    user_role="user",  # or "group"
    api_key="your-api-key",
)

# Get or create a collection
collection = zotero.get_or_create_collection("My Review")
collection_key = collection["data"]["key"]

# Load and prepare papers
config = {
    "output_dir": "output",
    "collect_name": "collect_20250101_120000",
    "aggregate_file": "aggregated_results.csv",
}
data = load_aggregated_data(config)
templates = prefetch_templates(data)

# Get existing URLs to skip duplicates
existing_urls = zotero.get_existing_item_urls(collection_key)

# Prepare and upload individual items
for row in data.itertuples(index=False):
    item = prepare_zotero_item(row, collection_key, templates)
    if item and item.get("url") not in existing_urls:
        result = zotero.post_items_bulk([item])
        print(f"Uploaded: {getattr(row, 'title', 'Unknown')[:60]}")
```

## Full Pipeline Script

A complete end-to-end script combining all steps:

```python
"""Full SciLEx pipeline: collect, aggregate, enrich, export."""

import os
import sys

import yaml

# ── 1. Configuration ──────────────────────────────────────────────

main_config = {
    "keywords": [["large language model", "LLM"], ["evaluation", "benchmark"]],
    "years": [2024, 2025],
    "apis": ["SemanticScholar", "OpenAlex", "Arxiv"],
    "output_dir": "output",
    "collect_name": "llm_benchmarks",
    "collect": True,
    "aggregate_get_citations": False,
    "aggregate_file": "aggregated_results.csv",
    "quality_filters": {
        "enable_itemtype_filter": True,
        "allowed_item_types": ["journalArticle", "conferencePaper", "preprint"],
        "apply_relevance_ranking": True,
        "max_papers": 200,
    },
}

api_config = {
    "SemanticScholar": {},
    "OpenAlex": {},
}

# ── 2. Collection ─────────────────────────────────────────────────

from scilex.crawlers.collector_collection import CollectCollection

output_dir = main_config["output_dir"]
os.makedirs(output_dir, exist_ok=True)

config_path = os.path.join(output_dir, "config_used.yml")
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        yaml.dump(main_config, f)

collector = CollectCollection(main_config, api_config)
collector.create_collects_jobs()
print("Collection complete.")

# ── 3. Aggregation ────────────────────────────────────────────────

sys.argv = ["aggregate", "--skip-citations"]

from scilex.aggregate_collect import main as aggregate_main

aggregate_main()
print("Aggregation complete.")

# ── 4. Enrich (optional) ──────────────────────────────────────────

sys.argv = ["enrich"]

from scilex.enrich_with_hf import main as enrich_main

enrich_main()
print("Enrichment complete.")

# ── 5. Export ─────────────────────────────────────────────────────

from scilex.export_to_bibtex import main as bibtex_main

bibtex_main()
print("BibTeX export complete.")

# ── 6. Analyze results ────────────────────────────────────────────

import pandas as pd

csv_path = os.path.join(
    output_dir, main_config["collect_name"], "aggregated_results.csv"
)
df = pd.read_csv(csv_path, delimiter=";")

print(f"\nResults: {len(df)} papers")
print(f"Sources: {df['archive'].value_counts().to_dict()}")
print(f"Years: {df['year'].value_counts().sort_index().to_dict()}")
```

## Important Notes

- **Config files**: The `aggregate_collect` and `enrich_with_hf` modules load config at import time via `load_all_configs()`. Make sure your YAML config files exist in the `scilex/` directory before importing these modules.
- **Working directory**: `load_all_configs()` looks for config files relative to the current working directory. Run scripts from the project root.
- **Threading**: Collection uses threading (1 thread per API). Safe to call without `__main__` guard, but recommended for scripts.
- **sys.argv**: Modules that use `argparse` parse `sys.argv` in their `main()`. Set `sys.argv` before calling `main()` to pass arguments programmatically.

## Next Steps

- [Basic Workflow](basic-workflow.md) - CLI-based workflow
- [Advanced Filtering](advanced-filtering.md) - Filtering options
- [Configuration](../getting-started/configuration.md) - All config parameters
