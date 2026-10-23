# Review + refactor complet du package `scilex`

Démarré : 2026-10-23. Branche : `dev`. Base : 972 tests verts, 1 skip.

## Plan
1. Review en parallèle (6 zones, lecture seule) → constats consolidés ci-dessous.
2. Refactor par lots (worktrees), chaque lot : tests verts + ruff propre, fusion ff-only dans `dev`.

## Zones
- Z1 `crawlers/aggregate.py`, `crawlers/aggregate_parallel.py`
- Z2 `crawlers/collectors/*`, `collector_collection.py`, `circuit_breaker.py`, `run_collection.py`
- Z3 `aggregate_collect.py`, `pipeline/*`, config, validations, `duplicate_tracking.py`
- Z4 `citations/*`, `HuggingFace/*`, `enrich_with_hf.py`
- Z5 `Zotero/*`, `push_to_zotero.py`, `export_to_bibtex.py`, logging, `__main__`
- Z6 `webapi/*`

## État
- [x] Lint autofix (adab616b)
- [ ] Review
- [ ] Refactor
