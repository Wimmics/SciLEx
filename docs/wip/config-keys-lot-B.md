# Clés de configuration du lot B

Lues via `config.get(clé, DEFAULT_<CLÉ>)` ; absentes de `QUALITY_FILTER_SCHEMA`.

| Clé | Type | Défaut | Rôle | Section suggérée |
|-----|------|--------|------|------------------|
| `generate_prisma_report` | bool | `true` | Écrit `prisma_report.md` (PRISMA 2020 + Mermaid) à la fin de `scilex-aggregate` (#49) | `output` / `aggregation` |
| `since` | str `YYYY-MM-DD` ou null | `null` | Re-collecte incrémentale (#31) : années = année(since)..année courante, filtre natif par API (OpenAlex, Semantic Scholar, arXiv, PubMed) sinon post-filtre à l'agrégation ; collecte écrite dans `<collect_name>_since_<date>/`, fusionnée automatiquement par `scilex-aggregate` (déduplication). Option CLI `scilex-collect --since`. | `collection` |

## Hors clés de config (#48)

`scilex-init --template/--list-templates/--save-profile` : pas de nouvelle clé. Variable d'environnement
`SCILEX_PROFILES_DIR` (défaut `~/.config/scilex/profiles`). Modèles : `scilex/templates/*.yml` au format
config actuel (l'adaptateur de la refonte devra les convertir). Les seuils de citations ne sont pas
configurables (constantes `CitationFilterConfig`) : les modèles jouent sur `apply_citation_filter`.
