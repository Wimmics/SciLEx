# Review + refactor complet du package `scilex`

Démarré : 2026-10-23. Branche : `dev`. Base : 972 tests verts, 1 skip. Politique : ADR 0001.

## Prochaine étape
Vague 1 (fichiers hors fusion) en cours ; fusion origin/main en cours (worktree `../SciLEx-merge`).
Vague 2 après fusion.

## Constats principaux (review du 2026-10-23)
### Bugs
- BibTeX : `escape_bibtex` double-échappe (`%`, `&`, `~` cassés) ; url/keywords/authors non échappés ; suffixe de clé > 26 collisions invalide ; `format_pages` ignore les tirets Unicode.
- Citations : `--no-cache` utilise quand même un cache par défaut non initialisé ; échecs OpenCitations mis en cache 30 j ; retries tenacity jamais déclenchés ; DOI non normalisés (casse, préfixe) ; checkpoint chargé à chaque run (`resume_from=False is not None`) ; checkpoint « dernier index » qui saute des papiers.
- Pipeline : mots-clés à casse mixte jamais trouvés dans l'abstract (mode 1 groupe) ; fallbacks de citations inopérants (init `""`) ; validation d'abstract faite 2 fois avec 2 définitions ; `is_valid(list)` lève ; merge config `quality_filters: null` plante, deep-merge non récursif.
- Agrégation : DOI non nettoyés pour PubMed/PMC ; erreurs de convertisseurs avalées en debug ; nombreux `row["x"]` non gardés ; `txt_filters=False` renvoie un DataFrame vide ; archive gagnante mal déduite en double fusion DOI+titre.
- Collecte : `rate_limits` de la config jamais lus (mauvais chemin) ; Springer compte double ; requête crashée marquée complète ; buffer de pages perdu sur exception ; clés API loguées en debug ; erreurs PubMed avalées => troncature silencieuse.
- HF : `bert` capture roberta/scibert… ; `github_repo` inventé ; rate-limit appliqué aussi aux hits de cache.
- Zotero : échecs partiels comptés comme succès ; `ZoteroAPI("", "", "")` lève ; token d'écriture régénéré aux retries (doublons) ; collections non paginées (>100).
- Web : traversée de chemin via `collect_name` (sauf DELETE) ; logs de jobs mélangés (handler sur root) ; jobs concurrents écrasent `scilex.config.yml` ; transitions d'état non synchronisées ; clés API renvoyées au navigateur ; CORS `*` + bind 0.0.0.0.
### Duplication / code mort
- `aggregate_collect.py` n'est pas mince : moteur de citations (~750 l.) à déplacer dans `citations/fetcher.py`.
- 13 gabarits de 18 clés copiés dans `aggregate.py` ; boucle de pagination copiée 3 fois ; PubMed/PMC quasi identiques.
- Chargeur CSV agrégé triplé ; listes d'API triplées côté web ; dédup legacy O(n²) mort ; `run_job_collects`, `post_item`, etc. morts.
- CLAUDE.md : `scilex-init`, export Turtle, `scilex/rdf/`, `citations/fetcher.py` n'existent pas.

## Lots
- Vague 1 (depuis dev, fichiers disjoints de la fusion) : V1-A BibTeX · V1-B citations (cache/tools) · V1-C HuggingFace · V1-D API web.
- Vague 2 (après fusion) : convertisseurs `aggregate.py` · `aggregate_parallel` · collecteurs/base · moteur de citations + pipeline · Zotero/push + chargeur partagé · doc CLAUDE.md.

## État
- [x] Lint autofix (adab616b)
- [x] Review (6 zones)
- [ ] Fusion origin/main
- [ ] Vague 1
- [ ] Vague 2
