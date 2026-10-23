# GUI lots 1 à 5 (wip)

Mandat utilisateur (2026-10-23) : enchaîner les lots 1 à 5 sans redemander ; agents Sonnet en parallèle ; à la fin, un agent Sonnet teste la GUI comme un humain (Chrome headless, sans voler le focus).

## Fondations communes (faites, sur dev)
- `pages/review.py` charge `scilex.gui.pages.<step>.render(ctx, review)` si le module existe.
- `JobRunner.start_task(review, kind, body)` : tâche de fond générique (logs, statut, annulation via `job.cancel_event`, `job.result`) ; `latest_for(review_id, kind)`.
- `components/job_panel.py` : `JobPanel(ctx, review, kind, on_change=, on_finished=)`.
- `services/screening.py` : `paper_key`, `load_results`, `load/save/set_decision`, `orphan_keys`, `included_results` ; fichier `output/<nom>/screening.csv`.
- Fixture `ctx` dans `tests/gui/conftest.py`.

## Vague 1 (6 agents, worktrees)
| Agent | Lot | Fichiers |
|---|---|---|
| A | 1 Configure | pages/configure.py, services/config_editor.py |
| B | 1 API keys | pages/keys.py, services/keys_editor.py |
| C | 2 Collect complet | pages/collect.py, services/jobs.py (start_pipeline) |
| D | 3 Screen | pages/screen.py, services/screening.py |
| E | 4 Export | pages/export.py, services/exports.py |
| F | 5 Analyses | pages/analyses.py, services/analyses.py |

## État (2026-10-23)
- Vague 1 fusionnée dans `gui-integration` puis `dev` (976297c4) : 1942 tests OK.
- Corrections d'intégration : clé Springer meta/openaccess conservée ; revue au scilex.yml invalide gardée avec bandeau ; faux pipeline de test écrit un CSV valide.
- Guide utilisateur à jour (122fbd53).
- Vague 2 en cours : Configure éditeur brut (YAML cassé, clés inconnues) ; Analyses onglet Citations + annulation ; relecture de code en lecture seule.

## Ensuite
Fusion vague 2, corrections de la relecture, rebuild de l'app, agent testeur headless, ff de dev.
