# Codebase Cleanup Summary - January 2026

## Overview

**Date:** 2026-01-22
**Branch:** `feature/pubmed`
**Commits:** 7 commits (37bdeac..93d7145)
**Files Changed:** 54 files (625 insertions, 27 deletions)

This cleanup removed deprecated code, improved consistency, and updated all documentation to reflect current best practices.

## What Was Changed

### 1. Code Organization (Commits: 37bdeac, 16c26e9, 8839e83)

**Deprecated Modules Moved to `.deprecated/modules/`:**
- `PWC/` (6 files) - Legacy PaperWithCode integration (replaced by `enrich_with_hf.py`)
- `tagging/` (13 files) - Manual Zotero tagging scripts (not part of automated pipeline)
- `orcid/` (2 files) - ORCID author lookup (integrated into collectors)
- `doi/` (1 file) - DOI fetching (integrated into collectors)
- `text_analysis/` (3 files) - Abstract analysis tools (standalone research tools)
- `annotation_agreement/` (1 file) - Inter-annotator agreement calculator (research tool)
- `api_tests/` (10 files) - Standalone API testing scripts (replaced by proper collectors + unit tests)

**Deprecated Scripts Moved to `.deprecated/scripts/`:**
- `getLPWC_collect.py` - Legacy PaperWithCode enrichment (replaced by `enrich_with_hf.py`)
- `optimize_keywords.py` - Keyword optimization tool (standalone utility)

**Total Deprecated:** 38 files preserved in `.deprecated/` for recovery if needed

### 2. File Naming Consistency (Commit: 0e6b6e9)

**Renamed Files:**
- `src/run_collecte.py` → `src/run_collection.py` (English consistency)

**Impact:** Main entry point now uses consistent English naming throughout codebase

### 3. Documentation Updates (Commits: 983cbd7, 7c412b0, 93d7145)

**Updated Files:**
- `CLAUDE.md` (+503 lines) - Complete rewrite with current commands, architecture, and workflows
- `docs/migration-guide.md` (new, 86 lines) - Migration guide for users
- `CONTRIBUTING.md` - Updated with migration guide link
- `Tuto_firstContact.md` - Updated command references
- `docs/getting-started/installation.md` - Updated command references
- `docs/getting-started/quick-start.md` - Updated workflow commands
- `docs/getting-started/troubleshooting.md` - Updated command references
- `docs/user-guides/basic-workflow.md` - Updated all workflow examples
- `docs/developer-guides/architecture.md` - Updated file references
- `docs/index.md` - Updated main entry point reference
- `src/crawlers/readMe.md` - Updated command examples

**Documentation Coverage:**
- All 11 documentation files now use `run_collection.py` (not `run_collecte.py`)
- All workflow examples updated to show current 4-step pipeline
- CLAUDE.md now serves as comprehensive developer reference

### 4. Code Quality (Commit: 8525eff)

**Formatting:**
- Applied `ruff format .` across entire codebase
- Applied `ruff check --fix .` for auto-fixable linting issues
- 2 files reformatted: `src/crawlers/collectors/springer.py`, `src/push_to_zotero.py`
- 1 linting error auto-fixed

**Test Status:**
- All 11 tests passing (pytest)
- No tests broken by cleanup
- Import verification: All core modules import successfully

## Verification Steps Completed

### 1. Code Quality Checks
```bash
uvx ruff format .        # OK: 2 files reformatted
uvx ruff check --fix .   # OK: 1 error fixed, deprecated files have expected syntax errors
uv run python -m pytest tests/ -v  # OK: 11/11 tests passing
```

### 2. Import Verification
```bash
python -c "from crawlers.collector_collection import CollectCollection; from Zotero.zotero_api import ZoteroAPI"
# Result: All imports OK
```

### 3. Smoke Test
```bash
uv run python src/run_collection.py --help
# Result: Script loads successfully, no import errors
```

## Breaking Changes

### For Users

1. **Main script renamed:**
   - Old: `uv run python src/run_collecte.py`
   - New: `uv run python src/run_collection.py`
   - Action: Update any scripts, aliases, or documentation referencing old name

2. **Deprecated scripts removed from `src/`:**
   - `getLPWC_collect.py` → Use `enrich_with_hf.py` instead
   - `optimize_keywords.py` → Copy from `.deprecated/scripts/` if needed

3. **Deprecated modules removed from `src/`:**
   - All moved to `.deprecated/modules/`
   - Recovery: `cp -r .deprecated/modules/PWC src/` (if needed)

### For Developers

1. **Import paths unchanged:**
   - All imports still work (no breaking changes)
   - Core modules in `src/` untouched

2. **Test suite unchanged:**
   - All existing tests pass
   - No test rewrites needed

## What Was NOT Changed

- No changes to core pipeline logic (`collectors/`, `aggregate.py`, etc.)
- No changes to configuration format (`*.config.yml`)
- No changes to output format (`aggregated_results.csv`)
- No changes to Zotero integration
- No changes to API integrations
- All deprecated code preserved in `.deprecated/` (38 files)

## Commit History

```
93d7145 docs: add migration guide for cleanup changes
8525eff style: format and lint code after cleanup
7c412b0 docs: update all documentation with current commands
983cbd7 docs: add deprecated code section to CLAUDE.md
0e6b6e9 refactor: rename run_collecte.py to run_collection.py for consistency
8839e83 refactor: move deprecated scripts to .deprecated/
16c26e9 refactor: move deprecated modules to .deprecated/
37bdeac docs: create deprecated code inventory
```

## Next Steps for Users

1. **Update Your Workflow:**
   - Replace `run_collecte.py` with `run_collection.py` in scripts/aliases
   - Review [migration-guide.md](migration-guide.md) for detailed changes

2. **Test Your Setup:**
   ```bash
   uv run python src/run_collection.py  # Test collection
   uv run python -m pytest tests/ -v     # Run test suite
   ```

3. **Recover Deprecated Code (if needed):**
   ```bash
   # Example: Restore PaperWithCode module
   cp -r .deprecated/modules/PWC src/
   ```

4. **Review New Features:**
   - BibTeX export: `uv run python src/export_to_bibtex.py`
   - HuggingFace enrichment: `uv run python src/enrich_with_hf.py`
   - PubMed Central API: Add `'PubMedCentral'` to `apis` in config

## Questions or Issues?

- See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines
- See [migration-guide.md](migration-guide.md) for migration instructions
- Open an issue on GitHub for support

## Metrics

- **Code Reduction:** 38 files moved to `.deprecated/`
- **Documentation Coverage:** 11/11 files updated
- **Test Coverage:** 11/11 tests passing
- **Breaking Changes:** 1 (filename rename)
- **Recovery Time:** < 1 minute (copy from `.deprecated/`)
