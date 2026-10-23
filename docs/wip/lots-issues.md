# WIP — Traitement des issues par lots (session scilex-d8)

Plan : `docs/decisions/0002-plan-lots-issues-ouvertes.md`.
Coordination : scilex-90 (refactor, ADR 0003 config) lancera C2 après nos lots ; scilex-86 (/simplify) après nous.

## Contraintes convenues avec scilex-90
- Ne pas modifier `scilex/config.py`, `scilex/__main__.py`, `scilex/*.yml.example`.
- `config_defaults.py`, `run_collection.py` : ajouts localisés uniquement (nouvelles constantes, pas de renommage).
- Chaque lot liste ses nouvelles clés de config dans `docs/wip/config-keys-lot-<X>.md` (pour C2).

## État
| Lot | Branche | Worktree | État |
|---|---|---|---|
| 0 | lot-0-bibtex2rdf | ../SciLEx-wt/lot-0 | dans dev |
| D | lot-d-new-apis | ../SciLEx-wt/lot-d | dans dev |
| A | lot-a-data-quality | ../SciLEx-wt/lot-a | dans dev (CORE réel, SJR vide : Cloudflare) |
| B | lot-b-pipeline-ux | (supprimé) | dans dev |
| C | lot-c-ai-research | (supprimé) | dans dev |

## Règle découverte
Les nouvelles clés ne vont PAS dans `get_default_quality_filters()` / `QUALITY_FILTER_SCHEMA`
(invariant legacy ↔ scilex/settings testé par scilex-90) : constante `DEFAULT_*` + `.get(clé, défaut)`.

## Prochaine étape
Tous les lots sont dans dev (1682 tests verts), worktrees supprimés. scilex-90 (C2) et scilex-86 (/simplify) prévenus.
Reste : push / PR / fermeture des issues, à confirmer avec l'utilisateur.
