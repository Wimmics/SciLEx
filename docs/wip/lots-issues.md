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
| 0 | lot-0-bibtex2rdf | ../SciLEx-wt/lot-0 | fusion en cours (19 conflits, fait par l'orchestrateur) |
| A | lot-a-data-quality | ../SciLEx-wt/lot-a | agent lancé |
| D | lot-d-new-apis | ../SciLEx-wt/lot-d | agent lancé |
| B | lot-b-pipeline-ux | — | après lot 0 |
| C | lot-c-ai-research | — | après lot 0 |

## Prochaine étape
Finir la fusion du lot 0, la passer dans dev, puis lancer B et C.
