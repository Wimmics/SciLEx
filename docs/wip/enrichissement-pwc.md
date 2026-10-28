# WIP — Enrichissement Papers with Code (ADR 0006)

## État
- [ ] Lot core (orchestrateur) : `scilex/PapersWithCode/`, `pipeline/enrichment_pwc.py`,
  `enrich_with_pwc.py`, appelants (GUI analyses, webapi, `__main__`), pyproject, tests HF → PwC
- [ ] Lot config (agent) : schema/loader/migrate/defaults, exemples, configuration.md,
  field_catalog, keys_editor, web_interface + tests
- [ ] Lot exports (agent) : BibTeX `pwcurl`, RDF, Zotero, docs + tests

## Contrat entre lots
- Dict legacy `pwc_enrichment` (repli lecture `hf_enrichment`), champs
  `enabled, fuzzy_match_threshold, cache_path, cache_ttl_days, workers`.
- Colonne CSV `pwc_url` (repli `hf_url`), `tags`, `github_repo`.

## Prochaine étape
Lancer les lots, puis suite de tests complète + ruff.
