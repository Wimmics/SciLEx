# 0003 — Configuration simplifiée : un fichier par revue, clés hors projet (2026-10-23)

## Contexte
Configurer une revue demande aujourd'hui 3 fichiers YAML situés **dans le package**
(`scilex/scilex.config.yml`, `scilex/scilex.advanced.yml`, `scilex/api.config.yml`), plus des
valeurs par défaut cachées dans `config_defaults.py`. Problèmes relevés par l'utilisateur :
trop de fichiers, options obscures (23 clés à plat dans `quality_filters`), emplacement absurde
pour un package installé, erreurs silencieuses (une faute de frappe est ignorée). Règles de fusion
surprenantes : `advanced` écrase `quality_filters` mais ne fait que compléter les autres clés.

## Décision

### 1. Deux fichiers, chacun à sa place
- **`scilex.yml`** : un par revue, dans le dossier de travail. Découverte :
  `--config PATH` > `$SCILEX_CONFIG` > `./scilex.yml` > ancien format (voir §5).
- **`keys.yml`** : clés API et limites de débit, partagé entre revues, jamais dans un projet.
  Découverte : `--keys PATH` > `$SCILEX_KEYS` > `~/.config/scilex/keys.yml` > ancien
  `scilex/api.config.yml` (avec avertissement). Les variables d'environnement
  `SCILEX_<API>_<CHAMP>` (ex. `SCILEX_SEMANTICSCHOLAR_API_KEY`) priment sur le fichier.
- `scilex.advanced.yml` disparaît : tout va dans `scilex.yml`, sous la section concernée.

### 2. Format de `scilex.yml` (organisé par étape du pipeline)
On n'écrit que ce qui diffère des défauts. Format complet :

```yaml
name: my_review                 # ex-collect_name (obligatoire)
output_dir: output
preset: literature_review       # literature_review | bibliometrics (optionnel)

search:
  keywords:                     # 1 groupe (OU) ou 2 groupes (groupe1 ET groupe2)
    - [RAG, Retrieval Augmented Generation]
    - [Knowledge Graph]
  bonus_keywords: []
  years: [2023, 2024, 2025]     # accepte aussi "2023-2025"
  apis: [SemanticScholar, OpenAlex, Arxiv]
  max_articles_per_query: null
  semantic_scholar_mode: regular   # regular | bulk

filters:
  item_types: null              # null = tous ; sinon liste blanche (ex-enable_itemtype_filter + allowed_item_types)
  always_keep: [journalArticle, conferencePaper]  # types jamais filtrés (ex-enable_itemtype_bypass + bypass_item_types)
  require: [abstract, year]     # parmi abstract, doi, year, open_access (ex-4 booléens require_*)
  min_authors: 2
  abstract_words: [50, 1000]    # [min, max]
  abstract_quality: null        # score 0-100 ; null = pas de validation (ex-validate_abstracts + min_abstract_quality_score)
  check_year_range: true
  citations: true               # filtre de citations selon l'âge (ex-apply_citation_filter)

citations:
  fetch: true                   # ex-aggregate_get_citations
  fallbacks: [semantic_scholar, openalex]   # ex-use_semantic_scholar_citations / use_openalex_citations

ranking:
  enabled: true                 # ex-apply_relevance_ranking
  max_papers: 1000              # null = pas de limite
  weights: {keywords: 0.45, quality: 0.25, itemtype: 0.20, citations: 0.10}
  itemtype_weights: {}          # surcharge partielle

enrichment:
  huggingface: false            # true, ou bloc {enabled, use_papers_api, fuzzy_match_threshold, cache_path, cache_ttl_days}

report:
  quality_report: true          # ex-generate_quality_report
  track_duplicates: true        # ex-track_duplicate_sources

collect:                        # options rares
  vpn: null                     # bloc VPN (rotation), tel qu'introduit par origin/main
```

### 3. Presets
Précédence : défauts du code < preset < `scilex.yml` < options CLI.
- *aucun preset* : reproduit exactement les défauts actuels de `config_defaults.py` (pas de changement de comportement).
- `literature_review` : `require: [abstract, year]`, `citations: true`, `abstract_quality: 60`.
- `bibliometrics` : `require: []`, `citations: false`, `abstract_quality: null`, `ranking.max_papers: null`.

### 4. Validation stricte
Modèles pydantic avec `extra="forbid"`. Une clé inconnue ou une valeur invalide arrête le
programme avec un message lisible : chemin de la clé, valeur reçue, suggestion la plus proche
(`difflib`) — ex. `filters.max_paper : clé inconnue. Vouliez-vous dire ranking.max_papers ?`

### 5. Compatibilité et migration
- Le chargeur produit en interne **le même dictionnaire « legacy »** (`main_config`, `api_config`)
  qu'aujourd'hui : `SciLExConfig`, le pipeline, l'API web (`from_dicts`) et les `config_used.yml`
  (format interne, non édité à la main) ne changent pas.
- L'ancien format (`scilex/scilex.config.yml` + `scilex.advanced.yml`) reste lu, avec un
  avertissement qui indique `scilex config migrate`.
- `--resume` / `--collection` continuent de lire `config_used.yml`.

### 6. Commandes
- `scilex init` : assistant interactif, écrit un `scilex.yml` court (et `keys.yml` si absent).
- `scilex config show` : config effective, avec la provenance de chaque valeur (défaut/preset/fichier/CLI).
- `scilex config migrate [--from DIR] [--write]` : convertit l'ancien format ; sans `--write`, affiche le résultat.
- `scilex config check` : valide sans rien lancer.
- Tous les CLI (`scilex-collect`, `-aggregate`, `-enrich`, `-push-zotero`, `-export-bibtex`) acceptent `--config` et `--keys`.

### 7. Code
Nouveau paquet `scilex/settings/` : `schema.py` (modèles), `presets.py`, `loader.py`
(découverte, fusion, env, `to_legacy()`), `migrate.py` (legacy → nouveau), `cli.py`.
`SciLExConfig.from_files()` délègue au chargeur. `load_all_configs` devient un mince adaptateur.

## Précisions issues de l'implémentation (C1, 8269b2ee)
- Les défauts du schéma recopient `config_defaults.py` (`require: [abstract, year]`,
  `always_keep: [journalArticle, conferencePaper]`, `min_authors: 2`) : sans preset, aucun changement.
- `collect.vpn` → `main_config["vpn"]` ; le rotateur VPN lit encore `api_config` : C2 le rebranche.
- HF : bloc émis si activé, sinon `{"enabled": False}` ; un ancien fichier sans `hf_enrichment` migre en `huggingface: true`.
- `output_dir` vaut `output` (relatif au dossier de travail) au lieu d'un chemin absolu dans le package.
- Les listes de types sont ignorées quand le drapeau correspondant est désactivé.
- Les suggestions `difflib` comparent le dernier segment du chemin de la clé.

## Conséquences
- Une revue = un dossier avec un `scilex.yml` versionnable ; les clés ne fuient plus dans un dépôt.
- Les noms `quality_filters.*` restent valables en interne ; seuls les fichiers humains changent.
- Hors périmètre : refonte des consommateurs internes pour lire le nouveau modèle directement
  (possible plus tard, l'adaptateur `to_legacy()` isole le changement).
