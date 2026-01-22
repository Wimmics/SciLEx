# Migration Guide - January 2026 Cleanup

## Summary

**Date:** 2026-01-22
**Changes:** Removed deprecated modules, renamed files for consistency, updated docs

## Breaking Changes

### 1. Filename Change
- **Old:** `python src/run_collecte.py`
- **New:** `python src/run_collection.py`

**Action:** Update your scripts/aliases.

### 2. Deprecated Scripts Removed

| Old Script | Replacement | Action |
|-----------|-------------|--------|
| `getLPWC_collect.py` | `enrich_with_hf.py` | Use HuggingFace enrichment instead |
| `optimize_keywords.py` | N/A | Standalone tool, see `.deprecated/scripts/` |

### 3. Deprecated Modules Removed

Moved to `.deprecated/modules/`:
- `PWC/` → Use `enrich_with_hf.py` for ML metadata
- `tagging/` → Manual Zotero operations (not automated)
- `orcid/`, `doi/`, `text_analysis/` → Integrated into collectors
- `annotation_agreement/` → Research tool (not pipeline)
- `API tests/` → Use proper collectors + unit tests

**Action:** If you need these, copy from `.deprecated/` directory.

## New Features

### BibTeX Export
Alternative to Zotero push:

```bash
uv run python src/export_to_bibtex.py
```

Generates `aggregated_results.bib` with full metadata and PDF links.

### PubMed Central API
New collector for biomedical papers:

```yaml
apis: ['PubMedCentral', ...]
```

### HuggingFace Enrichment
Add ML metadata to papers before export:

```bash
uv run python src/enrich_with_hf.py
```

## Updated Workflow

```bash
# 1. Collect
uv run python src/run_collection.py

# 2. Aggregate
uv run python src/aggregate_collect.py

# 3. Enrich (optional)
uv run python src/enrich_with_hf.py

# 4. Export (choose one)
uv run python src/push_to_zotero.py       # Zotero
uv run python src/export_to_bibtex.py     # BibTeX
```

## Recovery

All deprecated code preserved in `.deprecated/` directory. To restore:

```bash
cp -r .deprecated/modules/PWC src/
```

## Questions?

See [CONTRIBUTING.md](../CONTRIBUTING.md) or open an issue.
